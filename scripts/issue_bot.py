"""GitHub Actions bot: an issue (or comment) in, CAD / FEA results out.

Run by .github/workflows/engineer.yml. Plain English goes through a language model
(GitHub Models, free, via the workflow's GITHUB_TOKEN); text that already contains
`ea ...` lines or ```json / ```python blocks runs directly.

Environment: GITHUB_TOKEN, GITHUB_REPOSITORY, GITHUB_EVENT_NAME, GITHUB_EVENT_PATH,
GITHUB_RUN_ID, GITHUB_SERVER_URL, GITHUB_REF_NAME, GITHUB_OUTPUT, GITHUB_STEP_SUMMARY.
"""
from __future__ import annotations

import json
import math
import os
import re
import shutil
import subprocess
import sys
import time
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
os.chdir(ROOT)

from engagent import assistant  # noqa: E402
from engagent.request import parse, run_request, to_markdown  # noqa: E402

MARK = "<!-- engagent-bot -->"
API = "https://api.github.com"
REPO = os.environ.get("GITHUB_REPOSITORY", "")
TOKEN = os.environ.get("GITHUB_TOKEN", "")
SERVER = os.environ.get("GITHUB_SERVER_URL", "https://github.com")
RUN_URL = f"{SERVER}/{REPO}/actions/runs/{os.environ.get('GITHUB_RUN_ID', '')}"
BRANCH = os.environ.get("GITHUB_REF_NAME", "main")


def gh(method: str, path: str, body: dict | None = None):
    req = urllib.request.Request(API + path, method=method, data=json.dumps(body).encode() if body else None,
                                 headers={"Authorization": f"Bearer {TOKEN}", "Accept": "application/vnd.github+json",
                                          "X-GitHub-Api-Version": "2022-11-28", "Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=60) as r:
        data = r.read()
        return json.loads(data) if data else None


def conversation(issue: dict) -> list[dict]:
    msgs = [{"role": "user", "content": f"{issue.get('title', '')}\n\n{issue.get('body') or ''}".strip()}]
    page = 1
    while True:
        cs = gh("GET", f"/repos/{REPO}/issues/{issue['number']}/comments?per_page=100&page={page}") or []
        for c in cs:
            body = c.get("body") or ""
            if MARK in body:
                if "⏳" in body:
                    continue
                msgs.append({"role": "assistant", "content": body.replace(MARK, "")[:4000]})
            elif c.get("author_association") in ("OWNER", "MEMBER", "COLLABORATOR"):
                msgs.append({"role": "user", "content": body})
        if len(cs) < 100:
            return msgs
        page += 1


def _progress(what: str, n: int) -> None:
    print(f"[{time.strftime('%H:%M:%S')}] {what}" + (f" (attempt {n + 1})" if n else ""), file=sys.stderr, flush=True)


def _ask_with_fallback(convo: list[dict]) -> dict:
    """Configured provider / GitHub Models first; if none answers, a free open model on this runner."""
    try:
        return assistant.ask(convo, on_event=_progress)
    except assistant.LLMError as first:
        if os.environ.get("ENGAGENT_NO_LOCAL_LLM") or ":11434" in (os.environ.get("ENGAGENT_LLM_URL") or ""):
            raise                       # local fallback switched off, or the local model is what just failed
        if assistant.time_left() < 600:  # not enough time left to start the slow local model
            raise assistant.LLMError(f"{first} - and too little time was left to try the local model; "
                                     "post the request again in a few minutes")
        print(f"No hosted model answered ({first}); using a local open model on the runner.", file=sys.stderr)
        model = os.environ.get("ENGAGENT_LOCAL_MODEL") or assistant.LOCAL_DEFAULT_MODEL
        assistant.ensure_ollama(model, say=lambda m: print(m, file=sys.stderr))
        os.environ["ENGAGENT_LLM_URL"] = f"{assistant.OLLAMA}/v1/chat/completions"
        os.environ["ENGAGENT_LLM_MODEL"] = model
        out = assistant.ask(convo)
        out["model_note"] = (f"_Answered by the free open model `{model}` running on the GitHub runner "
                             f"(no key needed). For faster, stronger answers add a free Gemini key - see "
                             f"docs/USER-GUIDE.md section 2A._")
        return out


def commit(folders: list[str], label: str) -> bool:
    if not folders:
        return False
    run = lambda *a: subprocess.run(list(a), cwd=ROOT, capture_output=True, text=True)  # noqa: E731
    run("git", "config", "user.name", "github-actions[bot]")
    run("git", "config", "user.email", "41898282+github-actions[bot]@users.noreply.github.com")
    run("git", "add", "--", *folders)
    if run("git", "diff", "--cached", "--quiet").returncode == 0:
        return False
    run("git", "commit", "-m", f"Engineering results: {label}")
    for i in range(5):
        if run("git", "push", "origin", f"HEAD:{BRANCH}").returncode == 0:
            return True
        run("git", "pull", "--rebase", "origin", BRANCH)
        time.sleep(2 * (i + 1))
    return False


def _inputs():
    event = os.environ.get("GITHUB_EVENT_NAME", "workflow_dispatch")
    payload = json.loads(Path(os.environ["GITHUB_EVENT_PATH"]).read_text()) if os.environ.get("GITHUB_EVENT_PATH") else {}
    issue = payload.get("issue")
    if event == "workflow_dispatch":
        latest = (payload.get("inputs") or {}).get("request", "")
        convo = [{"role": "user", "content": latest}]
    elif event == "issue_comment":
        latest = payload["comment"]["body"]
        convo = conversation(issue)
    else:
        latest = issue.get("body") or ""
        convo = conversation(issue)
    return issue, latest, convo


def needs_model() -> bool:
    """Whether this request needs the local open model (so the workflow can skip its 4.6 GB cache)."""
    from engagent.rules import form_from_words
    _, latest, convo = _inputs()
    d = parse(latest)
    if d["commands"] or d["json"] or d["python"] or os.environ.get("ENGAGENT_LLM_KEY"):
        return False
    from engagent.cadinput import find_inputs
    f = find_inputs(latest, ROOT)
    if f["urls"] or f["paths"] or JOIN_RX.search(latest or ""):   # own parts / adapter design: no model
        return False
    return form_from_words("\n".join(m["content"] for m in convo if m["role"] == "user")) is None


def main() -> int:
    # a time budget for the whole request (model calls, custom CAD code, retries): the user hears back
    # within ~20 minutes even when the AI service is slow; FEA itself is not cut short
    os.environ.setdefault("ENGAGENT_DEADLINE", str(time.time() + float(os.environ.get("ENGAGENT_BUDGET_S", 1200))))
    os.environ.setdefault("ENGAGENT_SCRIPT_TIMEOUT", "150")
    # another request may have committed since this run checked out: take its job numbers into account
    subprocess.run(["git", "pull", "-q", "--rebase", "origin", BRANCH], cwd=ROOT, capture_output=True)
    issue, latest, convo = _inputs()
    comment_id = int(os.environ["ENGAGENT_ACK_ID"]) if os.environ.get("ENGAGENT_ACK_ID", "").isdigit() else None
    if issue and not comment_id:
        c = gh("POST", f"/repos/{REPO}/issues/{issue['number']}/comments",
               {"body": f"{MARK}\n⏳ Working on it - common requests take 1 to 3 minutes; up to 15 if the free built-in AI model is needed. [Live log]({RUN_URL})"})
        comment_id = c["id"]

    cad = _cad_parts(latest, issue, comment_id)       # the user's own STEP parts: list faces, ask what to join
    if cad is not None:
        return cad
    join = _cad_join(latest, convo, issue, comment_id)  # "join camera F2 to arm_flange F2": design the adapter
    if join is not None:
        return join
    check = _adapter_load(latest, convo)                # "0.8 kg, 2 g": FEA of the adapter just designed
    if check:
        latest = check                                  # runs below as ordinary `ea` lines
    link_base = f"{SERVER}/{REPO}/blob/{BRANCH}"
    head, result, plan, req_text, followup = "", None, "", "", ""
    out_by_rules = False
    direct = parse(latest)
    try:
        if direct["commands"] or direct["json"] or direct["python"]:
            result = run_request(latest, link_base=link_base)
            req_text = latest
        else:
            out = _ask_with_fallback(convo)
            out_by_rules = bool(out.get("by_rules"))
            plan = out.get("plan", "")
            if out.get("corrections"):
                plan = (plan + "\n\n**Checked against your words:** " + "; ".join(out["corrections"]) + ".").strip()
            if out.get("model_note"):
                plan = (plan + "\n\n" + out["model_note"]).strip()
            if out["kind"] == "question":
                head = (out["reply"].strip() + ("\n\n" + out["model_note"] if out.get("model_note") else "")
                        + "\n\n<sub>Reply in a comment below and I will continue. "
                        "Engineering assistance, not sign-off.</sub>")
            else:
                result = out.get("result")
                req_text = out.get("request", "")
                followup = out.get("followup", "")
                if result:
                    result["markdown"] = to_markdown(result, link_base)
                if out["attempts"] > 1:
                    plan += f"\n\n_(The first attempt had errors; corrected automatically, {out['attempts']} attempts.)_"
    except assistant.LLMError as e:
        head = (f"### ❌ The language model could not be used\n{e}\n\nYou can still paste a request made by any "
                f"chatbot (see `docs/CHATBOT-PROMPT.md`) or `ea` command lines into a comment.")
    except Exception as e:  # never leave the user without an answer
        head = f"### ❌ Unexpected error\n`{type(e).__name__}: {e}`\n\n[Log]({RUN_URL})"

    folders: list[str] = []
    try:
        if result:
            folders = sorted({os.path.relpath(Path(j["folder"]).resolve(), ROOT) for j in result["jobs"]})
            head = _result_body(result, plan, direct, req_text, folders, issue, followup)
    except Exception as e:  # still answer the user
        head = f"### ❌ Unexpected error while saving results\n`{type(e).__name__}: {e}`\n\n[Log]({RUN_URL})"
    footer = _model_footer(direct, out_by_rules)
    if check:                                           # say what really happened, and show the request
        footer = "\n\n<sub>Answered by: built-in adapter check (no AI model)</sub>"
        head = ("<details><summary>Analysis that was run (copy, edit and post it as a comment to change it)"
                "</summary>\n\n```bash\n" + check + "\n```\n</details>\n\n" + head)
    _finish(head + footer, comment_id, folders)
    return 0


def _cad_parts(latest: str, issue, comment_id):
    """Stage 1 of 'design an adapter between my two parts': fetch the STEP files, list the numbered
    faces and hole patterns with pictures, and ask which faces to join. None when there are no parts."""
    from engagent import cadinput, quick
    d = parse(latest)
    if d["commands"] or d["json"] or d["python"]:      # `ea ...` lines that name a STEP file run as written
        return None
    found = cadinput.find_inputs(latest, ROOT)
    if not (found["urls"] or found["paths"]):
        return None
    folders: list[str] = []
    try:
        folder = quick.next_job_folder("parts")
        parts = []
        for pth in found["paths"]:
            dst = folder / cadinput._safe_name(pth)
            shutil.copy(ROOT / pth, dst)
            parts.append(dst)
        problems = []
        for url in found["urls"]:
            try:
                parts += cadinput.fetch(url, folder / "parts", TOKEN)
            except Exception as e:
                problems.append(f"{url.rsplit('/', 1)[-1]}: {e}")
        for p in list(parts):
            if p.parent != folder:
                shutil.move(str(p), folder / p.name)
                parts[parts.index(p)] = folder / p.name
        shutil.rmtree(folder / "parts", ignore_errors=True)
        if not parts:
            shutil.rmtree(folder, ignore_errors=True)
            head = ("### ❌ I could not read your CAD files\n" + "\n".join(f"- {x}" for x in problems)
                    + "\n\nGitHub does not accept `.step` attachments: put the STEP files in a **.zip** and "
                    "attach that, or upload them to the repository (e.g. an `inbox/` folder) and write their "
                    "paths here, like `inbox/camera.step`.")
        else:
            (folder / "request.txt").write_text(latest, encoding="utf-8")
            data, md = cadinput.list_parts(parts, folder)
            rel = os.path.relpath(folder, ROOT)
            folders = [rel]
            pushed = commit(folders, f"#{issue['number']} parts" if issue else "parts")
            raw = f"{SERVER}/{REPO}/blob/{BRANCH}/{rel}/plots"
            pics = " ".join(f'<img src="{raw}/faces_{n}.png?raw=true" alt="{n}" width="420">' for n in data) \
                if pushed else ""
            names = list(data) + ["other_part"] * 2
            head = ("### 🔩 Your parts, measured\n" + md + "\n\n" + pics
                    + ("\n\n⚠️ " + "; ".join(problems) if problems else "")
                    + "\n\n" + cadinput.QUESTION.format(a=names[0], b=names[1])
                    + f"\n\n<sub>Parts saved in `{rel}`. Engineering assistance, not sign-off.</sub>")
    except Exception as e:
        head = f"### ❌ Unexpected error while reading your parts\n`{type(e).__name__}: {e}`\n\n[Log]({RUN_URL})"
    _finish(head + "\n\n<sub>Answered by: built-in CAD measurement (no AI model)</sub>", comment_id, folders)
    return 0


def _adapter_load(latest: str, convo: list[dict]) -> str | None:
    """'the camera weighs 0.8 kg, 2 g' after an adapter design -> the `ea analyze` request for the plate."""
    from engagent.cad import adapter
    from engagent.guard import material_from_words
    m = re.search(r"(\d+(?:\.\d+)?)\s*(kg|g(?:rams?)?)\b(?!\s*(?:accel|g\b))", latest or "", re.I)
    if not m or parse(latest)["commands"]:
        return None
    last = [x["content"] for x in convo if x["role"] == "assistant" and "Adapter design" in x["content"]]
    f = re.search(r"/(jobs/[^/)\s]+)/adapter\.step", last[-1]) if last else None
    if not f or not (ROOT / f.group(1) / "adapter.json").exists():
        return None
    mass = float(m.group(1)) / (1 if m.group(2).lower() == "kg" else 1000)
    g = re.search(r"(\d+(?:\.\d+)?)\s*(?:g\b|x\s*g\b|g-?force)", latest[m.end():] + " " + latest[:m.start()], re.I)
    mat_words = latest + " " + last[-1]
    mat = material_from_words(latest) or (re.search(r"Material:\*\* `([\w.]+)`", last[-1]) or [None, None])[1] \
        or material_from_words(mat_words) or "al_6061_t6"
    return adapter.fea_request(f.group(1), mat, mass, float(g.group(1)) if g else 1.0)


JOIN_RX = re.compile(r"\bjoin\s+`?([\w.-]+)`?\s+(F\d+)\s+(?:to|and|with|onto|on)\s+`?([\w.-]+)`?\s+(F\d+)", re.I)


def _cad_join(latest: str, convo: list[dict], issue, comment_id):
    """Stage 2: the user picked the faces - plan, build and check a flat adapter plate."""
    from engagent import quick
    from engagent.cad import adapter
    from engagent.cad.export import convert
    from engagent.guard import material_from_words
    m = JOIN_RX.search(latest or "")
    if not m:
        return None
    saved = [re.search(r"Parts saved in `([^`]+)`", x["content"]) for x in convo if x["role"] == "assistant"]
    saved = [x.group(1) for x in saved if x]
    if not saved:
        return None
    src = ROOT / saved[-1]
    a_name, fa, b_name, fb = m.groups()
    folders: list[str] = []
    try:
        steps = {p.stem: p for p in src.glob("*.step")}
        miss = [n for n in (a_name, b_name) if n not in steps]
        if miss:
            raise ValueError(f"no part called {', '.join(miss)} (parts: {', '.join(steps)})")
        import json as _json
        feats = _json.loads((src / "features.json").read_text())
        screws = [x.upper() for x in re.findall(r"\bM\d{1,2}\b", latest, re.I)]
        pick = []
        for name, fid in ((a_name, fa), (b_name, fb)):
            face = next((f for f in feats[name]["faces"] if f["id"].upper() == fid.upper()), None)
            if face is None:
                raise ValueError(f"{name} has no face {fid}")
            cand = [h["screw"] for h in face["holes"] if h["count"] >= 2 and not h["screw"].startswith("bore")]
            sizes = sorted(set(re.findall(r"M\d+", cand[0]))) if cand else []
            given = [x for x in screws if x in sizes]
            pick.append(given[0] if given else (sizes[0] if len(sizes) == 1 else None))
        if None in pick:
            k = pick.index(None)
            n, f = ((a_name, fa), (b_name, fb))[k]
            cand = [h["screw"] for h in next(x for x in feats[n]["faces"] if x["id"].upper() == f.upper())["holes"]]
            head = (f"### ❓ One thing first\nThe holes on `{n}` {f} fit **{cand[0] if cand else 'no standard screw'}**. "
                    f"Which screw is it? Reply e.g. *join {a_name} {fa} to {b_name} {fb}, M6*.")
            _finish(head + "\n\n<sub>Answered by: built-in CAD design (no AI model)</sub>", comment_id, [])
            return 0
        folder = quick.next_job_folder("adapter")
        thick = re.search(r"(\d+(?:\.\d+)?)\s*mm\s*(?:thick|plate)", latest, re.I)
        plan = adapter.plan(steps[a_name], fa, steps[b_name], fb, pick[0], pick[1])
        lines = [f"Joining `{a_name}` {fa} (below) to `{b_name}` {fb} (on top)."]
        name = lambda x: x.replace("part A", f"`{a_name}`").replace("part B", f"`{b_name}`")   # noqa: E731
        (folder / "plots").mkdir(exist_ok=True)
        centred = plan["ok"] and not any(plan["offset"])
        if centred:                                    # a flat plate works on the axis: simplest part
            built = adapter.build(plan, folder, steps[a_name], steps[b_name],
                                  float(thick.group(1)) if thick else None)
            lines += [name(x) for x in adapter.report_lines(plan, built)]
        else:                                          # keep B on A's axis: box adapter, screws inside
            built = adapter.build_box(plan, folder, steps[a_name], steps[b_name])
            lines += ["A flat plate on the axis cannot be assembled (one set of screws would be buried), so "
                      "this is a box adapter with the screws inside and windows to reach them."]
            lines += [name(x) for x in adapter.box_lines(built)]
            if plan["ok"]:                             # the flat alternative, shifted sideways
                alt = folder / "offset_plate"
                alt.mkdir(exist_ok=True)
                ab = adapter.build(plan, alt, steps[a_name], steps[b_name])
                convert(alt / "adapter.step", stl=True, threemf=True)
                lines.append(f"**Alternative:** a flat {ab['size'][0]:.4g} x {ab['size'][1]:.4g} x "
                             f"{ab['thickness']:g} mm plate works if `{b_name}` may sit "
                             f"{math.hypot(*plan['offset']):.3g} mm off-centre (files in `offset_plate/`).")
        convert(folder / "adapter.step", stl=True, threemf=True)
        adapter.picture(folder / "assembly.step", folder / "plots" / "assembly.png", f"{a_name} + adapter + {b_name}")
        mat = material_from_words(latest) or "al_6061_t6"
        lines.append(f"**Material:** `{mat}`" + ("" if material_from_words(latest) else
                     " (default - say another if you prefer, e.g. PETG to 3D print it)") + ".")
        (folder / "request.txt").write_text(latest, encoding="utf-8")
        rel = os.path.relpath(folder, ROOT)
        folders = [rel]
        pushed = commit(folders, f"#{issue['number']} adapter" if issue else "adapter")
        raw = f"{SERVER}/{REPO}/blob/{BRANCH}/{rel}"
        files = [f"[{n}]({raw}/{n})" for n in ("adapter.step", "adapter.stl", "adapter.3mf", "assembly.step")
                 if (folder / n).exists()]
        head = "### 🔩 Adapter design\n" + "\n".join(f"- {x}" for x in lines)
        if files and pushed:
            head += "\n\n**Files:** " + " · ".join(files)
            head += f'\n\n<img src="{raw}/plots/assembly.png?raw=true" alt="assembly" width="560">'
        if True:
            head += ("\n\n**Next:** tell me the weight of the top part and the acceleration (e.g. *0.8 kg, 2 g*) "
                     "and I will check the plate with FEA and a hand calculation (the screws are sized above; their load is shown in the reactions).")
        head += "\n\n<sub>Engineering assistance, not sign-off.</sub>"
    except Exception as e:
        head = f"### ❌ Could not design the adapter\n`{type(e).__name__}: {e}`\n\n[Log]({RUN_URL})"
    _finish(head + "\n\n<sub>Answered by: built-in CAD design (no AI model)</sub>", comment_id, folders)
    return 0


def _model_footer(direct, by_rules) -> str:
    """One line saying what produced the answer (the model that really answered, after any fallback)."""
    if direct["commands"] or direct["json"] or direct["python"]:
        what = "your own `ea` commands (no AI model)"
    elif by_rules:
        what = "built-in rules (no AI model)"
    elif assistant.LAST_USED:
        what = f"`{assistant.LAST_USED['model']}` via {assistant.LAST_USED['host']}"
    else:
        return ""
    return f"\n\n<sub>Answered by: {what}</sub>"


def _result_body(result, plan, direct, req_text, folders, issue, followup="") -> str:
    pushed = commit(folders, f"#{issue['number']}" if issue else "manual run")
    parts = []
    if plan:
        parts.append(plan)
    if not direct["commands"] and not direct["json"] and not direct["python"] and req_text:
        cmds = parse(req_text)["commands"]
        if cmds:
            parts.append("<details><summary>Request that was run (copy, edit and post it as a comment to change it)</summary>\n\n```bash\n"
                         + "\n".join("ea " + c for c in cmds) + "\n```\n</details>")
    def ignored(path: str) -> bool:              # link only files that were committed
        return subprocess.run(["git", "check-ignore", "-q", path], cwd=ROOT).returncode == 0
    parts.append(to_markdown(result, f"{SERVER}/{REPO}/blob/{BRANCH}", skip=ignored))
    pics = _pictures(folders, pushed)
    if pics:
        parts.append(pics)
    if followup:
        parts.append("### ❓ To finish your request\n" + followup
                     + "\n\nReply in a comment below and I will continue.")
    if folders:
        parts.append(f"📦 **[Download all files, including the interactive 3D viewer]({RUN_URL}#artifacts)**"
                     + ("" if pushed else " (files were not committed - see the log)"))
    return "\n\n".join(parts)




def _pictures(folders: list[str], pushed: bool) -> str:
    """Result pictures shown right in the comment (they play on phones too) and the viewer link."""
    if not pushed:
        return ""
    raw = f"{SERVER}/{REPO}/blob/{BRANCH}"
    out = []
    for f in folders:
        plots = ROOT / f / "plots"
        shown = [(n, c) for n, c in (("deformation.gif", "Animated deformation (exaggerated)"),
                                      ("von_mises.png", "von Mises stress"),
                                      ("temperature.png", "Temperature"),
                                      ("mode_1.png", "Mode 1")) if (plots / n).exists()]
        if shown:
            out.append(f"#### Results for `{f}`\n" + " ".join(f'<img src="{raw}/{f}/plots/{n}?raw=true" alt="{c}" '
                                                              f'width="380">' for n, c in shown[:2]))
        if (ROOT / f / "viewer.html").exists():
            out.append(f"🖥️ **Interactive 3D viewer:** [viewer.html]({raw}/{f}/viewer.html) - on a computer, open "
                       f"it and use *Download raw file*, then open the file in your browser (rotate, zoom, play "
                       f"the deformation). On a phone the pictures above show the same results.")
    return "\n\n".join(out)


def _finish(head: str, comment_id, folders: list[str]) -> None:
    body = f"{MARK}\n{head}"[:65000]
    if comment_id:
        gh("PATCH", f"/repos/{REPO}/issues/comments/{comment_id}", {"body": body})
    if os.environ.get("GITHUB_STEP_SUMMARY"):
        Path(os.environ["GITHUB_STEP_SUMMARY"]).write_text(head, encoding="utf-8")
    if os.environ.get("GITHUB_OUTPUT"):
        with open(os.environ["GITHUB_OUTPUT"], "a", encoding="utf-8") as f:
            f.write("folders<<EOF\n" + "\n".join(folders or ["jobs/.none"]) + "\nEOF\n")
    print(head)


if __name__ == "__main__":
    if "--needs-model" in sys.argv:
        need = needs_model()
        print(f"needs the local model: {need}")
        if os.environ.get("GITHUB_OUTPUT"):
            with open(os.environ["GITHUB_OUTPUT"], "a", encoding="utf-8") as f:
                f.write(f"needs={'true' if need else 'false'}\n")
        sys.exit(0)
    sys.exit(main())
