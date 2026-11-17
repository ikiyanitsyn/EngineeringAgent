"""GitHub Actions bot: an issue (or comment) in, CAD / FEA results out.

Run by .github/workflows/engineer.yml. Plain English goes through a language model
(GitHub Models, free, via the workflow's GITHUB_TOKEN); text that already contains
`ea ...` lines or ```json / ```python blocks runs directly.

Environment: GITHUB_TOKEN, GITHUB_REPOSITORY, GITHUB_EVENT_NAME, GITHUB_EVENT_PATH,
GITHUB_RUN_ID, GITHUB_SERVER_URL, GITHUB_REF_NAME, GITHUB_OUTPUT, GITHUB_STEP_SUMMARY.
"""
from __future__ import annotations

import json
import os
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


def main() -> int:
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
    comment_id = None
    if issue:
        c = gh("POST", f"/repos/{REPO}/issues/{issue['number']}/comments",
               {"body": f"{MARK}\n⏳ Working on it - usually 3 to 8 minutes. [Live log]({RUN_URL})"})
        comment_id = c["id"]

    link_base = f"{SERVER}/{REPO}/blob/{BRANCH}"
    head, result, plan, req_text = "", None, "", ""
    direct = parse(latest)
    try:
        if direct["commands"] or direct["json"] or direct["python"]:
            result = run_request(latest, link_base=link_base)
            req_text = latest
        else:
            out = assistant.ask(convo)
            plan = out.get("plan", "")
            if out["kind"] == "question":
                head = (out["reply"].strip() + "\n\n<sub>Reply in a comment below and I will continue. "
                        "Engineering assistance, not sign-off.</sub>")
            else:
                result = out.get("result")
                req_text = out.get("request", "")
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
            head = _result_body(result, plan, direct, req_text, folders, issue)
    except Exception as e:  # still answer the user
        head = f"### ❌ Unexpected error while saving results\n`{type(e).__name__}: {e}`\n\n[Log]({RUN_URL})"
    _finish(head, comment_id, folders)
    return 0


def _result_body(result, plan, direct, req_text, folders, issue) -> str:
    pushed = commit(folders, f"#{issue['number']}" if issue else "manual run")
    parts = []
    if plan:
        parts.append(plan)
    if not direct["commands"] and not direct["json"] and not direct["python"] and req_text:
        cmds = parse(req_text)["commands"]
        if cmds:
            parts.append("<details><summary>Request that was run (copy, edit and post it as a comment to change it)</summary>\n\n```bash\n"
                         + "\n".join("ea " + c for c in cmds) + "\n```\n</details>")
    parts.append(result["markdown"])
    if folders:
        parts.append(f"📦 **[Download all files, including the interactive 3D viewer]({RUN_URL}#artifacts)**"
                     + ("" if pushed else " (files were not committed - see the log)"))
    return "\n\n".join(parts)




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
    sys.exit(main())
