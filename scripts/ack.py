"""Post the bot's "working on it" comment straight away (standard library only, before any setup).

The issue bot then edits this comment with the results. Prints the comment id to GITHUB_OUTPUT.
"""
import json
import os
import urllib.request

import sys

MARK = "<!-- engagent-bot -->"
event = json.load(open(os.environ["GITHUB_EVENT_PATH"], encoding="utf-8"))
issue = event.get("issue")
if "--failed" in sys.argv and os.environ.get("ACK_ID"):      # setup broke: never leave the user waiting
    repo, run = os.environ["GITHUB_REPOSITORY"], os.environ["GITHUB_RUN_ID"]
    url = f"{os.environ.get('GITHUB_SERVER_URL', 'https://github.com')}/{repo}/actions/runs/{run}"
    body = (f"{MARK}\n### ❌ The run failed before it could answer\nUsually a temporary problem on GitHub's side "
            f"(for example a slow package server). Post any comment here (e.g. *try again*) to retry. [Log]({url})")
    req = urllib.request.Request(f"https://api.github.com/repos/{repo}/issues/comments/{os.environ['ACK_ID']}",
                                 data=json.dumps({"body": body}).encode(), method="PATCH",
                                 headers={"Authorization": f"Bearer {os.environ['GITHUB_TOKEN']}",
                                          "Accept": "application/vnd.github+json"})
    urllib.request.urlopen(req, timeout=30)
    sys.exit(0)
if issue:
    repo, run = os.environ["GITHUB_REPOSITORY"], os.environ["GITHUB_RUN_ID"]
    url = f"{os.environ.get('GITHUB_SERVER_URL', 'https://github.com')}/{repo}/actions/runs/{run}"
    body = (f"{MARK}\n⏳ Working on it - common requests take 2 to 4 minutes; up to 15 if the free built-in AI "
            f"model is needed. [Live log]({url})")
    req = urllib.request.Request(f"https://api.github.com/repos/{repo}/issues/{issue['number']}/comments",
                                 data=json.dumps({"body": body}).encode(), method="POST",
                                 headers={"Authorization": f"Bearer {os.environ['GITHUB_TOKEN']}",
                                          "Accept": "application/vnd.github+json"})
    with urllib.request.urlopen(req, timeout=30) as r:
        cid = json.load(r)["id"]
    with open(os.environ["GITHUB_OUTPUT"], "a", encoding="utf-8") as f:
        f.write(f"id={cid}\n")
