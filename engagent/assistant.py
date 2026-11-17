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


OLLAMA = "http://localhost:11434"
# open models that follow the request format well, best first (any installed model is used otherwise)
OLLAMA_PREFERRED = ("qwen2.5-coder:32b", "qwen2.5-coder:14b", "qwen2.5:14b", "qwen2.5-coder:7b", "qwen2.5:7b",
                    "llama3.1:8b", "qwen2.5-coder:3b", "llama3.2:3b")
LOCAL_DEFAULT_MODEL = "qwen2.5-coder:7b"


def ollama_models(timeout: float = 2.0) -> list[str]:
    """Models installed in a running Ollama on this machine ([] if none is running)."""
    try:
        with urllib.request.urlopen(f"{OLLAMA}/api/tags", timeout=timeout) as r:
            return [m["name"] for m in json.loads(r.read().decode()).get("models", [])]
    except Exception:
        return []


def pick_local_model(names: list[str]) -> str | None:
    for want in OLLAMA_PREFERRED:
        if want in names or f"{want}:latest" in names:
            return want
    return names[0] if names else None


def settings() -> dict:
    """Which model to use: explicit settings > a running local Ollama > GitHub Models (token)."""
    cfg = config.load().get("llm") or {}
    url = os.environ.get("ENGAGENT_LLM_URL") or cfg.get("url")
    if not url and not os.environ.get("ENGAGENT_LLM_KEY"):
        local = pick_local_model(ollama_models())
        if local:
            return {"url": f"{OLLAMA}/v1/chat/completions",
                    "model": os.environ.get("ENGAGENT_LLM_MODEL") or cfg.get("model") or local, "key": None}
    url = url or GITHUB_MODELS
    key_env = cfg.get("key_env") or "ENGAGENT_LLM_KEY"
    key = os.environ.get(key_env) or os.environ.get("ENGAGENT_LLM_KEY")
    if not key and "models.github.ai" in url:
        key = os.environ.get("GITHUB_TOKEN") or os.environ.get("GH_TOKEN")
    model = os.environ.get("ENGAGENT_LLM_MODEL") or cfg.get("model") or \
        (DEFAULT_MODEL if "models.github.ai" in url else "")
    return {"url": url, "key": key, "model": model}


def _post_ollama(base: str, model: str, messages: list[dict], timeout: float) -> str:
    """Ollama's native API: lets us raise the context window (its default is too small for the prompt)."""
    body = json.dumps({"model": model, "messages": messages, "stream": False,
                       "options": {"num_ctx": 8192, "temperature": 0.1}}).encode()
    req = urllib.request.Request(base + "/api/chat", data=body, method="POST",
                                 headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=max(timeout, 900)) as r:
        data = json.loads(r.read().decode("utf-8"))
    if "message" not in data:
        raise LLMError(f"{model} at {base}: unexpected reply {json.dumps(data)[:300]}")
    return data["message"].get("content") or ""


def _post(url: str, key: str | None, model: str, messages: list[dict], timeout: float) -> str:
    m = re.match(r"^(https?://[^/]+:11434)(/|$)", url)
    if m:
        return _post_ollama(m.group(1), model, messages, timeout)
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


def ensure_ollama(model: str = LOCAL_DEFAULT_MODEL, say=print) -> str:
    """Make a local open model available on this Linux machine (used on GitHub runners).

    Installs Ollama if needed, starts a server whose models live in ~/.ollama/models (so a CI
    cache can keep them), pulls the model, and returns its name. Needs internet once per model.
    """
    import shutil
    import subprocess
    home = os.path.expanduser("~/.ollama/models")
    os.makedirs(home, exist_ok=True)
    if not ollama_models():
        if not shutil.which("ollama"):
            say("installing Ollama (free, open-source model runner) ...")
            subprocess.run("curl -fsSL https://ollama.com/install.sh | sh", shell=True, check=True,
                           stdout=subprocess.DEVNULL)
            subprocess.run("sudo systemctl stop ollama 2>/dev/null || true", shell=True)
        env = dict(os.environ, OLLAMA_MODELS=home, OLLAMA_CONTEXT_LENGTH="8192", OLLAMA_KEEP_ALIVE="30m")
        subprocess.Popen(["ollama", "serve"], env=env, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                         start_new_session=True)
        for _ in range(60):
            time.sleep(1)
            try:
                urllib.request.urlopen(f"{OLLAMA}/api/tags", timeout=2)
                break
            except Exception:
                continue
        else:
            raise LLMError("the local model server (Ollama) did not start")
    if model not in ollama_models() and f"{model}:latest" not in ollama_models():
        if os.environ.get("GITHUB_ACTIONS") == "true" and shutil.disk_usage(home).free < 20e9:
            # hosted runners ship ~10 GB of SDKs we never use; the model and its cache copy need the room
            subprocess.run("sudo rm -rf /usr/share/dotnet /usr/local/lib/android /opt/ghc /usr/local/.ghcup "
                           "/opt/hostedtoolcache/CodeQL 2>/dev/null || true", shell=True)
        say(f"downloading the open model {model} (once; cached afterwards) ...")
        subprocess.run(["ollama", "pull", model], check=True, stdout=subprocess.DEVNULL,
                       env=dict(os.environ, OLLAMA_MODELS=home))
    return model


def split_reply(reply: str) -> tuple[str, str]:
    """(plan text without code blocks, the request part)."""
    plan = re.sub(r"```.*?```", "", reply, flags=re.S).strip()
    plan = "\n".join(l for l in plan.splitlines() if not re.match(r"^\s*(\./)?ea\s", l)).strip()
    return plan, reply


def _has_analysis(reply: str) -> bool:
    req = parse(reply)
    return any(c.split()[0] in ("analyze", "analyse") for c in req["commands"] if c.split()) or \
        any('"analysis"' in j or '"loads"' in j for j in req["json"])


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
        user_text = "\n".join(m["content"] for m in conversation if m.get("role") == "user")
        from .guard import check_request, question
        invented = check_request(reply, user_text)
        if invented:                                   # never run on inputs the user did not give
            out.update(kind="question", reply=question(invented), plan="", invented=invented,
                       request=reply)
            return out
        out["request"] = reply
        if not run:
            out["kind"] = "request"
            return out
        from .guard import analysis_intent, missing_for_analysis
        if analysis_intent(user_text) and not _has_analysis(reply):
            gaps = missing_for_analysis(user_text)
            if gaps:                                   # deliver the part, and ask what the analysis needs
                out["followup"] = question(gaps).replace("Before I run the analysis",
                                                         "To answer your question with an analysis")
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
