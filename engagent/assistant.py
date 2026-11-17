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
GITHUB_MODELS_AZURE = "https://models.inference.ai.azure.com/chat/completions"   # older endpoint, same token
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


def _post(url: str, key: str | None, model: str, messages: list[dict], timeout: float) -> str:
    body = json.dumps({"model": model, "messages": messages, "temperature": 0.1}).encode()
    headers = {"Content-Type": "application/json", "Accept": "application/json"}
    if key:
        headers["Authorization"] = f"Bearer {key}"
    req = urllib.request.Request(url, data=body, method="POST", headers=headers)
    with urllib.request.urlopen(req, timeout=timeout) as r:
        raw = r.read()
        ctype = r.headers.get("Content-Type", "")
        status = r.status
    try:
        data = json.loads(raw.decode("utf-8"))
    except ValueError:
        snippet = raw[:300].decode("utf-8", "replace").replace("\n", " ")
        raise LLMError(f"{model} at {url}: HTTP {status}, {ctype or 'no content type'}, not JSON: {snippet!r}")
    if "choices" not in data:
        raise LLMError(f"{model} at {url}: unexpected reply {json.dumps(data)[:300]}")
    content = data["choices"][0]["message"].get("content") or ""
    if isinstance(content, list):                      # some providers return parts
        content = "".join(p.get("text", "") for p in content if isinstance(p, dict))
    return content


def complete(messages: list[dict], *, model: str | None = None, timeout: float = 180.0) -> str:
    """One chat completion.  On GitHub Models, falls back to smaller models and the older endpoint."""
    s = settings()
    if not s["model"] and not model:
        raise LLMError("no model set: set ENGAGENT_LLM_MODEL (e.g. qwen2.5-coder:14b for Ollama)")
    github = "models.github.ai" in s["url"]
    if github and not s["key"]:
        raise LLMError("GitHub Models needs a token: set ENGAGENT_LLM_KEY to a GitHub personal access "
                       "token with the 'models: read' permission (free), or point ENGAGENT_LLM_URL at "
                       "Ollama / LM Studio / another provider. See docs/USER-GUIDE.md.")
    first = model or s["model"]
    targets = [(s["url"], first)]
    if github:
        targets += [(s["url"], m) for m in FALLBACK_MODELS if m != first]
        targets += [(GITHUB_MODELS_AZURE, m.split("/", 1)[-1]) for m in (first,) + FALLBACK_MODELS]
    errors: list[str] = []
    for url, m in targets:
        for attempt in range(2):
            try:
                return _post(url, s["key"], m, messages, timeout)
            except urllib.error.HTTPError as e:
                detail = e.read().decode("utf-8", "replace")[:300]
                errors.append(f"{m} at {url}: HTTP {e.code} {detail}")
                if e.code >= 500 and attempt == 0:
                    time.sleep(3)
                    continue
                break                                 # 4xx: try the next model / endpoint
            except LLMError as e:
                errors.append(str(e))
                break
            except (urllib.error.URLError, TimeoutError, OSError) as e:
                errors.append(f"{m} at {url}: {type(e).__name__}: {e}")
                if attempt == 0:
                    time.sleep(3)
                    continue
                break
        if not github:
            break
    import sys
    print("LLM errors:\n  " + "\n  ".join(errors), file=sys.stderr)
    if github and all("not JSON" in e or "Name or service" in e or "HTTP 401" in e or "HTTP 403" in e
                      for e in errors):
        raise LLMError(
            "GitHub Models is not available to this account or network (it did not return a model reply). "
            "Use any other free provider instead: e.g. a free Google Gemini key from "
            "https://aistudio.google.com/apikey with ENGAGENT_LLM_URL="
            "https://generativelanguage.googleapis.com/v1beta/openai/chat/completions and "
            "ENGAGENT_LLM_MODEL=gemini-2.5-flash. In GitHub: Settings > Secrets and variables > Actions "
            "(secret ENGAGENT_LLM_KEY, variables ENGAGENT_LLM_URL and ENGAGENT_LLM_MODEL).")
    raise LLMError("the language model could not be used. " + " | ".join(errors[:3]))


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
