"""Plain English -> request -> results, with any OpenAI-compatible chat model.

Works with free options:

* GitHub Models (free with any GitHub account; automatic inside GitHub Actions):
      ENGAGENT_LLM_URL   https://models.github.ai/inference/chat/completions   (default)
      ENGAGENT_LLM_KEY   a GitHub token (GITHUB_TOKEN in Actions, or a personal token with models:read)
      ENGAGENT_LLM_MODEL openai/gpt-4.1  (default)
* Ollama on your PC:      ENGAGENT_LLM_URL=http://localhost:11434/v1/chat/completions
                          ENGAGENT_LLM_MODEL=qwen2.5-coder:14b      (no key)
* LM Studio:              ENGAGENT_LLM_URL=http://localhost:1234/v1/chat/completions
* Google Gemini (free key from aistudio.google.com):
      ENGAGENT_LLM_URL=https://generativelanguage.googleapis.com/v1beta/openai/chat/completions
      ENGAGENT_LLM_MODEL=gemini-2.5-flash   ENGAGENT_LLM_KEY=<key>
* Groq, OpenRouter, OpenAI, ... any /v1/chat/completions endpoint.

Settings can also live in engagent.config.json under "llm": {"url", "model", "key_env"}.
The key itself is read from an environment variable and never written to disk.
"""
from __future__ import annotations

import json
import os
import re
import time
import urllib.error
import urllib.request

from . import config
from .prompt import chatbot_prompt
from .request import parse, run_request

GITHUB_MODELS = "https://models.github.ai/inference/chat/completions"
DEFAULT_MODEL = "openai/gpt-4.1"
FALLBACK_MODELS = ("openai/gpt-4.1-mini", "openai/gpt-4o-mini")


class LLMError(RuntimeError):
    pass


def settings() -> dict:
    cfg = config.load().get("llm") or {}
    url = os.environ.get("ENGAGENT_LLM_URL") or cfg.get("url") or GITHUB_MODELS
    key_env = cfg.get("key_env") or "ENGAGENT_LLM_KEY"
    key = os.environ.get(key_env) or os.environ.get("ENGAGENT_LLM_KEY")
    if not key and "models.github.ai" in url:
        key = os.environ.get("GITHUB_TOKEN") or os.environ.get("GH_TOKEN")
    model = os.environ.get("ENGAGENT_LLM_MODEL") or cfg.get("model") or \
        (DEFAULT_MODEL if "models.github.ai" in url else "")
    return {"url": url, "key": key, "model": model}


def complete(messages: list[dict], *, model: str | None = None, timeout: float = 180.0) -> str:
    """One chat completion.  Falls back to smaller GitHub models on rate limits."""
    s = settings()
    if not s["model"] and not model:
        raise LLMError("no model set: set ENGAGENT_LLM_MODEL (e.g. qwen2.5-coder:14b for Ollama)")
    if "models.github.ai" in s["url"] and not s["key"]:
        raise LLMError("GitHub Models needs a token: set ENGAGENT_LLM_KEY to a GitHub personal access "
                       "token with the 'models: read' permission (free), or point ENGAGENT_LLM_URL at "
                       "Ollama / LM Studio / another provider. See docs/USER-GUIDE.md.")
    models = [model or s["model"]]
    if "models.github.ai" in s["url"]:
        models += [m for m in FALLBACK_MODELS if m not in models]
    last_err = None
    for m in models:
        for attempt in range(3):
            body = json.dumps({"model": m, "messages": messages, "temperature": 0.1}).encode()
            req = urllib.request.Request(s["url"], data=body, method="POST", headers={
                "Content-Type": "application/json", **({"Authorization": f"Bearer {s['key']}"} if s["key"] else {})})
            try:
                with urllib.request.urlopen(req, timeout=timeout) as r:
                    data = json.loads(r.read().decode("utf-8"))
                msg = data["choices"][0]["message"]
                content = msg.get("content") or ""
                if isinstance(content, list):                 # some providers return parts
                    content = "".join(p.get("text", "") for p in content if isinstance(p, dict))
                return content
            except urllib.error.HTTPError as e:
                detail = e.read().decode("utf-8", "replace")[:400]
                last_err = f"{m}: HTTP {e.code} {detail}"
                if e.code == 429:                             # rate limit: next model
                    break
                if e.code >= 500 and attempt < 2:
                    time.sleep(3 * (attempt + 1))
                    continue
                if e.code in (400, 404) and "model" in detail.lower():
                    break                                     # unknown model: try the next
                raise LLMError(last_err) from e
            except (urllib.error.URLError, TimeoutError, KeyError, ValueError) as e:
                last_err = f"{m}: {type(e).__name__}: {e}"
                if attempt < 2:
                    time.sleep(3 * (attempt + 1))
                    continue
                break
    raise LLMError(f"the language model could not be reached ({last_err})")


def split_reply(reply: str) -> tuple[str, str]:
    """(plan text without code blocks, the request part)."""
    plan = re.sub(r"```.*?```", "", reply, flags=re.S).strip()
    plan = "\n".join(l for l in plan.splitlines() if not re.match(r"^\s*(\./)?ea\s", l)).strip()
    return plan, reply


def ask(conversation: list[dict] | str, *, max_fixes: int = 2, run: bool = True, model: str | None = None,
        on_event=None) -> dict:
    """Turn a conversation (or one message) into results.

    Returns {"kind": "question"|"results"|"error", "reply", "plan", "request", "result", "attempts"}.
    A "question" means the model needs information (e.g. the load); show it to the user.
    """
    say = on_event or (lambda *_: None)
    if isinstance(conversation, str):
        conversation = [{"role": "user", "content": conversation}]
    messages = [{"role": "system", "content": chatbot_prompt()}] + conversation
    out: dict = {"attempts": 0}
    for attempt in range(max_fixes + 1):
        out["attempts"] = attempt + 1
        say("thinking", attempt)
        reply = complete(messages, model=model)
        plan, _ = split_reply(reply)
        out.update(reply=reply, plan=plan)
        req = parse(reply)
        if not (req["commands"] or req["json"] or req["python"]):
            out["kind"] = "question"
            return out
        out["request"] = reply
        if not run:
            out["kind"] = "request"
            return out
        say("running", attempt)
        res = run_request(reply)
        out["result"] = res
        if not res["errors"] or attempt == max_fixes:
            out["kind"] = "results" if not res["errors"] else "error"
            return out
        say("fixing", attempt)
        messages += [{"role": "assistant", "content": reply},
                     {"role": "user", "content": "The tool reported these problems:\n"
                      + "\n".join(f"- {e}" for e in res["errors"])
                      + "\nReply with the complete corrected REQUEST (all lines and blocks again). "
                        "If a face selector matched nothing, use a simpler one (xmin..zmax, plane:, near:)."}]
    return out
