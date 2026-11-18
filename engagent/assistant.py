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
import urllib.parse
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


RETRIES = 3                      # tries per model before moving to the next one
RETRY_WAIT = (4.0, 12.0)         # seconds to wait after the 1st and 2nd failed try
# Gemini model ids to try, in order, when the configured one is busy (503), rate limited (429) or retired (404)
GEMINI_FALLBACK_MODELS = ("gemini-3.5-flash", "gemini-flash-latest", "gemini-3.5-flash-lite")


def fallback_models(url: str) -> list[str]:
    """Extra models to try on the same endpoint. ENGAGENT_LLM_FALLBACK_MODELS (comma-separated) overrides."""
    env = os.environ.get("ENGAGENT_LLM_FALLBACK_MODELS")
    if env is not None:
        return [m.strip() for m in env.split(",") if m.strip()]
    return list(GEMINI_FALLBACK_MODELS) if "generativelanguage.googleapis.com" in url else []


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


def _post_ollama(base: str, model: str, messages: list[dict], timeout: float, fmt: dict | None = None) -> str:
    """Ollama's native API: lets us raise the context window and constrain the reply to a JSON schema."""
    payload = {"model": model, "messages": messages, "stream": False,
               "options": {"num_ctx": 8192, "temperature": 0.1}}
    if fmt:
        payload["format"] = fmt
    body = json.dumps(payload).encode()
    req = urllib.request.Request(base + "/api/chat", data=body, method="POST",
                                 headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=min(max(timeout, 900), max(time_left(), 30))) as r:
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


LAST_USED: dict = {}             # {"model": ..., "host": ...} of the most recent successful completion


def time_left() -> float:
    """Seconds left of the overall budget (ENGAGENT_DEADLINE, epoch seconds); unlimited when unset."""
    try:
        return float(os.environ["ENGAGENT_DEADLINE"]) - time.time()
    except (KeyError, ValueError):
        return 1e9


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
    else:
        # other providers: same endpoint and key, next model in the fallback list
        targets += [(s["url"], m) for m in fallback_models(s["url"]) if m != first]
    errors: list[str] = []
    import sys
    rounds = 4 if os.environ.get("ENGAGENT_DEADLINE") else 1      # the bot waits out outages; the CLI does not
    for rnd in range(rounds):                          # whole rounds: a provider-wide 'high demand' (503)
        if rnd:                                       # usually clears within minutes - wait it out
            busy = all(re.search(r"HTTP (5\d\d|429|408)|Timeout|timed out", e) for e in errors[-len(targets):])
            if not busy or time_left() < 300:
                break
            pause = min(60 * rnd, time_left() - 240)
            print(f"[{time.strftime('%H:%M:%S')}] all models busy - waiting {pause:.0f} s and trying again",
                  file=sys.stderr, flush=True)
            time.sleep(pause)
        text = _try_targets(targets, s, messages, timeout, errors)
        if text is not None:
            return text
    _raise_llm(errors, github)


def _try_targets(targets, s, messages, timeout, errors):
    import sys
    for url, m in targets:
        for attempt in range(RETRIES):
            wait = RETRY_WAIT[min(attempt, len(RETRY_WAIT) - 1)]
            left = time_left()
            if left < 20:                             # the request's overall time budget is used up
                errors.append("time budget used up before a model answered")
                raise LLMError("the AI model did not answer in time (" + "; ".join(errors[-3:]) + ")")
            try:
                print(f"[{time.strftime('%H:%M:%S')}] asking {m} (try {attempt + 1})", file=sys.stderr, flush=True)
                text = _post(url, s["key"], m, messages, min(timeout, left))
                LAST_USED.update(model=m, host=urllib.parse.urlparse(url).hostname or "")
                return text
            except urllib.error.HTTPError as e:
                detail = e.read().decode("utf-8", "replace")[:300]
                errors.append(f"{m} at {url}: HTTP {e.code} {detail}")
                if (e.code >= 500 or e.code in (408, 429)) and attempt < RETRIES - 1:
                    time.sleep(wait)                  # busy / rate limited: wait and retry the same model
                    continue
                break                                 # other 4xx or retries used up: next model / endpoint
            except LLMError as e:
                errors.append(str(e))
                break
            except (urllib.error.URLError, TimeoutError, OSError) as e:
                errors.append(f"{m} at {url}: {type(e).__name__}: {e}")
                if attempt < RETRIES - 1:
                    time.sleep(wait)
                    continue
                break
    return None


def _raise_llm(errors, github):
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


OLLAMA_RELEASE = "https://github.com/ollama/ollama/releases/latest/download/ollama-linux-amd64"
_INSTALL_STEPS = [
    # the release archive straight from GitHub (current releases ship .tar.zst only)
    "command -v zstd >/dev/null || sudo apt-get install -y -qq zstd; "
    f"curl -fsSL --retry 3 {OLLAMA_RELEASE}.tar.zst | zstd -d | sudo tar -xf - -C /usr/local",
    f"curl -fsSL --retry 3 {OLLAMA_RELEASE}.tgz | sudo tar -xzf - -C /usr/local",      # older layout
    "curl -fsSL --retry 3 https://ollama.com/install.sh | sh",                          # official script
]


def _install_ollama(say=print) -> None:
    """Install Ollama on Linux, trying several sources so one broken download does not stop the bot."""
    import shutil
    import subprocess
    errors = []
    for attempt in range(2):
        for step in _INSTALL_STEPS:
            r = subprocess.run(["bash", "-o", "pipefail", "-c", step], capture_output=True, text=True)
            if r.returncode == 0 and shutil.which("ollama"):
                subprocess.run("sudo systemctl stop ollama 2>/dev/null || true", shell=True)
                return
            errors.append((r.stderr or r.stdout or "").strip().splitlines()[-1:] or ["failed"])
        time.sleep(5 * (attempt + 1))
    raise LLMError("could not install the free local model runner (Ollama): "
                   + "; ".join(e[0] for e in errors[-3:]) + ". Re-run the request in a few minutes, or add a "
                   "free Gemini key (docs/USER-GUIDE.md section 2A).")


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
            _install_ollama(say)
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


def _inputs_given(user_text: str) -> bool:
    """True when the user's own words already hold an analysis's inputs (mechanical or thermal)."""
    from .guard import analysis_intent, material_from_words, missing_for_analysis
    if not analysis_intent(user_text) or not material_from_words(user_text):
        return False
    t = user_text.lower()
    thermal = re.search(r"\d\s*(°|deg|degrees)?\s*[cf]\b", t) and re.search(
        r"\b(hot|heat|temperature|cool|thermal|warm)", t)
    return bool(thermal) or not missing_for_analysis(user_text)


def _ask_structured(conversation: list[dict], say, run: bool) -> dict:
    """Small local model: fill a JSON form (schema-constrained); the code writes the request."""
    from . import structured
    from .guard import check_request, question
    s = settings()
    base = re.match(r"^(https?://[^/]+:11434)", s["url"]).group(1)
    user_text = "\n".join(m["content"] for m in conversation if m.get("role") == "user")
    say("thinking", 0)
    raw = _post_ollama(base, s["model"], [{"role": "system", "content": structured.prompt()}] + conversation,
                       180, fmt=structured.schema())
    form = structured.parse_form(raw)
    out: dict = {"attempts": 1, "form": form, "plan": ""}
    if form.get("action") not in ("make", "analyze") and _inputs_given(user_text):
        # small models ask needless questions (e.g. for the very temperature the user wants to know).
        # The user's words hold what is needed, so fill the form as an analysis; the code below
        # still asks for anything that is really missing.
        say("fixing", 0)
        sch = structured.schema()
        sch["properties"]["action"] = {"enum": ["analyze"]}
        sch["required"] = ["action", "template", "analysis"]
        raw = _post_ollama(base, s["model"], [{"role": "system", "content": structured.prompt()}] + conversation
                           + [{"role": "assistant", "content": raw},
                              {"role": "user", "content": "Everything needed is in my message - do not ask. Fill "
                               "the form as an analysis using only my numbers. The value I am asking about is the "
                               "result, not an input. Temperatures go in 'temperatures'/'convection' (analysis "
                               "'thermal'), never in 'loads'."}], 180, fmt=sch)
        form = structured.parse_form(raw)
        out.update(attempts=2, form=form)
    return _run_form(form, user_text, say, run, out)


def _run_form(form: dict, user_text: str, say, run: bool, out: dict) -> dict:
    """A filled form (from the rules or a model) -> checked request -> results."""
    from . import structured
    from .guard import check_request, question
    bad = structured.magnitudes_from_user(form, user_text) if form.get("action") == "analyze" else []
    if bad:
        out.update(kind="question", reply=question(bad))
        return out
    if form.get("action") == "job":                      # a whole job (e.g. an assembly) from the rules
        import json as _json
        req, q = "```json\n" + _json.dumps(form["job"], indent=1) + "\n```", None
    else:
        req, q = structured.build_request(form, user_text)
    if form.get("_notes"):
        out["corrections"] = form["_notes"]
    if q:
        out.update(kind="question", reply=q)
        return out
    invented = check_request(req, user_text)
    if invented:
        out.update(kind="question", reply=question(invented), request=req)
        return out
    out.update(request=req if req.startswith("```") else "```bash\n" + req + "\n```", reply=req)
    if not run:
        out["kind"] = "request"
        return out
    say("running", 0)
    res = run_request(out["request"])
    out.update(result=res, kind="results" if not res["errors"] else "error")
    return out


def ask(conversation: list[dict] | str, *, max_fixes: int = 2, run: bool = True, model: str | None = None,
        on_event=None) -> dict:
    """Turn a conversation (or one message) into results.

    Returns {"kind": "question"|"results"|"error", "reply", "plan", "request", "result", "attempts"}.
    A "question" means the model needs information (e.g. the load); show it to the user.
    """
    say = on_event or (lambda *_: None)
    if isinstance(conversation, str):
        conversation = [{"role": "user", "content": conversation}]
    if os.environ.get("ENGAGENT_NO_RULES") != "1":
        from .rules import form_from_words          # common requests need no model at all
        user_text = "\n".join(m["content"] for m in conversation if m.get("role") == "user")
        first = next((m["content"] for m in conversation if m.get("role") == "user"), user_text)
        form = form_from_words(user_text, first=first)
        if form:
            say("understood", 0)
            out = {"attempts": 0, "form": form, "by_rules": True,
                   "plan": "_Understood directly from your words - no AI model needed._"}
            return _run_form(form, user_text, say, run, out)
    local = ":11434" in settings()["url"]           # small CPU model: shorter instructions, faster
    if local and os.environ.get("ENGAGENT_FREEFORM") != "1":
        return _ask_structured(conversation, say, run)
    messages = [{"role": "system", "content": chatbot_prompt(compact=local)}] + conversation
    from .guard import material_from_words as _mfw
    _mat = _mfw("\n".join(m["content"] for m in conversation if m.get("role") == "user"))
    if _mat:                                          # say which library material the user's words mean, so the
        messages = messages[:-1] + [dict(messages[-1], content=messages[-1]["content"]      # model never asks
                                         + f"\n\n(Library material for my words: `{_mat}` - use exactly this key.)")]
    out: dict = {"attempts": 0}
    for attempt in range(max_fixes + 1):
        out["attempts"] = attempt + 1
        say("thinking", attempt)
        reply = complete(messages, model=model)
        plan, _ = split_reply(reply)
        out.update(reply=reply, plan=plan)
        req = parse(reply)
        if not (req["commands"] or req["json"] or req["python"]):
            user_text = "\n".join(m["content"] for m in conversation if m.get("role") == "user")
            from .guard import analysis_intent, material_from_words, missing_for_analysis, stated_quantities
            if attempt < max_fixes and analysis_intent(user_text) and not missing_for_analysis(user_text):
                mat = material_from_words(user_text)
                say("fixing", attempt)                 # the user already gave everything: insist once
                messages += [{"role": "assistant", "content": reply},
                             {"role": "user", "content":
                              "Everything needed was already given - do not ask, write the REQUEST now. "
                              f"Material: {mat or 'see my words'} (use exactly this library key). "
                              f"Loads I stated: {', '.join(stated_quantities(user_text)) or 'see my words'}. "
                              "A weight hanging down is a force in -Z. Use the supports I described."}]
                continue
            out["kind"] = "question"
            return out
        user_text = "\n".join(m["content"] for m in conversation if m.get("role") == "user")
        from .guard import check_request, question
        from .guard import autocorrect
        fixed, notes = autocorrect(reply, user_text)     # use the user's own material / load
        if notes and not check_request(fixed, user_text):
            reply = fixed
            out["corrections"] = notes
            out["reply"] = reply
        invented = check_request(reply, user_text)
        if invented:                                   # never run on inputs the user did not give
            if attempt < max_fixes:                    # first let the model use what the user said
                from .guard import retry_hint
                say("fixing", attempt)
                messages += [{"role": "assistant", "content": reply},
                             {"role": "user", "content": retry_hint(invented, user_text)}]
                continue
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
        if not res["errors"] or attempt == max_fixes or time_left() < 240:   # no time for another try
            out["kind"] = "results" if not res["errors"] else "error"
            return out
        say("fixing", attempt)
        messages += [{"role": "assistant", "content": reply},
                     {"role": "user", "content": "The tool reported these problems:\n"
                      + "\n".join(f"- {e}" for e in res["errors"])
                      + "\nReply with the complete corrected REQUEST (all lines and blocks again). "
                        "If a face selector matched nothing, use a simpler one (xmin..zmax, plane:, near:)."}]
    return out
