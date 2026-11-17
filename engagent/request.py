"""Run a free-form *request*: the format any chatbot (or person) can write.

A request is plain text containing any of:

* command lines starting with ``ea`` (also ``./ea``, ``.\\ea.cmd``, ``engagent``), e.g.::

      ea make l_bracket thickness=6 --print petg
      ea analyze last -m al_6061_t6 --fix hole:6.6@40,20,0 --force hole:6.6@0,20,42 -300,0,0

  ``last`` stands for the job folder made by the previous ``make``/``analyze`` line.
  ``ea units imperial`` switches units for the rest of this request only.
* a fenced ```json block: a complete job.json (see docs/job-reference.md);
* a fenced ```python block: a build123d geometry script ending with ``save(part)``.

A JSON and a Python block in the same request go into the same job folder. Any other
text (explanations, headings) is ignored, so a whole chatbot reply can be pasted as is.
"""
from __future__ import annotations

import contextlib
import io
import json
import os
import re
import shlex
import traceback
from pathlib import Path

from . import quick
from . import units as U

ALLOWED = {"make", "analyze", "analyse", "calc", "gdt", "cad", "fea", "report", "materials",
           "convert", "units", "view", "standard"}
CMD_RE = re.compile(r"^\s*(?:[$>]\s*)?(?:\./ea|\.\\ea\.cmd|ea\.cmd|ea|engagent)\s+(.+?)\s*$")
FENCE_RE = re.compile(r"```[ \t]*([A-Za-z0-9_+-]*)[^\n]*\n(.*?)```", re.S)


def parse(text: str) -> dict:
    """Split a request into command lines and code blocks."""
    text = text.replace("\r\n", "\n")
    blocks = {"json": [], "python": []}
    commands: list[str] = []
    for lang, body in FENCE_RE.findall(text):
        lang = lang.lower()
        stripped = body.strip()
        if lang in ("json", "jsonc", "json5") or (not lang and stripped.startswith("{")):
            blocks["json"].append(stripped)
        elif lang in ("python", "py") or (not lang and "build123d" in stripped):
            blocks["python"].append(body)
    shellish = ("", "bash", "sh", "shell", "powershell", "ps1", "text", "txt", "console", "cmd", "zsh")
    chunks: list[str] = []                       # scanned in document order
    pos = 0
    for m in FENCE_RE.finditer(text):
        chunks.append(text[pos:m.start()])
        if m.group(1).lower() in shellish and not m.group(2).strip().startswith("{"):
            chunks.append(m.group(2))
        pos = m.end()
    chunks.append(text[pos:])
    for chunk in chunks:
        joined = re.sub(r"[ \t]*[\\`^][ \t]*\n[ \t]*", " ", chunk)       # line continuations
        for line in joined.splitlines():
            m = CMD_RE.match(line.strip().strip("`"))
            if m:
                commands.append(m.group(1))
                continue
            for inline in re.findall(r"`\s*(?:\./|\.\\)?ea(?:\.cmd)?\s+([^`]+?)\s*`", line):
                commands.append(inline)
    return {"commands": commands, "json": blocks["json"], "python": blocks["python"]}


def _call(argv: list[str]) -> tuple[int, str, str]:
    from .cli import main
    out, err = io.StringIO(), io.StringIO()
    with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
        try:
            code = main(argv)
        except SystemExit as e:                     # argparse errors
            code = int(e.code or 0) if isinstance(e.code, int) else 2
    return code, out.getvalue(), err.getvalue()


def _job_entry(folder: Path, verdict: str | None, lines: list[str], attention: list[str],
               files: list[str], kind: str) -> dict:
    return {"folder": str(folder), "verdict": verdict, "summary": lines, "attention": attention,
            "files": files, "kind": kind}


def run_request(text: str, *, markdown: bool = False, link_base: str | None = None) -> dict:
    """Execute a request.  Returns {'ok', 'jobs', 'outputs', 'errors', 'text', 'markdown'}."""
    req = parse(text)
    jobs: list[dict] = []
    outputs: list[tuple[str, str]] = []
    errors: list[str] = []
    last: str | None = None
    env_before = os.environ.get("ENGAGENT_UNITS")
    if not (req["commands"] or req["json"] or req["python"]):
        errors.append("No commands or code blocks found. A request needs lines starting with `ea` "
                      "(for example `ea make plate length=100 --print petg`) or a ```json / ```python block. "
                      "See docs/CHATBOT-PROMPT.md.")
    try:
        # ---- code blocks: one job folder
        if req["json"] or req["python"]:
            try:
                job = json.loads(_strip_comments(req["json"][0])) if req["json"] else {}
                name = job.get("name") or job.get("title") or ("part" if req["python"] else "job")
                folder = quick.next_job_folder(name)
                if req["python"]:
                    (folder / "geometry.py").write_text(req["python"][0], encoding="utf-8")
                    job.setdefault("geometry", {"script": "geometry.py"})
                job["name"] = folder.name
                (folder / "job.json").write_text(json.dumps(job, indent=1) + "\n", encoding="utf-8")
                (folder / "request.txt").write_text(text, encoding="utf-8")
                entry = _run_folder(folder, job)
                jobs.append(entry)
                last = str(folder)
            except Exception as e:
                errors.append(f"code block: {type(e).__name__}: {e}")
        # ---- command lines
        for cmd in req["commands"]:
            if last:
                cmd = re.sub(r"(?<![\w/.-])last(?![\w/.-])", shlex.quote(last), cmd)
            try:
                argv = shlex.split(cmd, posix=True)
            except ValueError as e:
                errors.append(f"`ea {cmd}`: cannot parse ({e})")
                continue
            if not argv:
                continue
            head = argv[0].lower()
            if head not in ALLOWED:
                errors.append(f"`ea {cmd}`: '{head}' is not allowed in a request (allowed: {', '.join(sorted(ALLOWED))})")
                continue
            if head == "units" and len(argv) > 1:          # request-local toggle, not saved
                os.environ["ENGAGENT_UNITS"] = U.normalize_system(argv[1])
                outputs.append((f"ea {cmd}", f"Units for this request: {os.environ['ENGAGENT_UNITS']}"))
                continue
            if head == "analyse":
                argv[0] = "analyze"
            if head in ("make", "analyze", "analyse"):
                code, out, err = _call(argv + ["--json"])
                try:
                    data = json.loads(out)
                except ValueError:
                    data = {}
                if "error" in data or code == 2 or not data:
                    errors.append(f"`ea {cmd}`: " + (data.get("error") or err.strip() or out.strip() or f"exit code {code}"))
                    continue
                folder = Path(data["folder"])
                (folder / "request.txt").write_text(text, encoding="utf-8")
                last = str(folder)
                if argv[0] == "make":
                    pr = data.get("print") or {}
                    lines = _cad_lines(data.get("cad", {}))
                    att = []
                    if pr:
                        lines.append(f"3D-print check: {pr['status']} - {pr.get('orientation_note', '')}".strip())
                        if pr.get("mass") is not None:
                            lines.append(f"Printed mass about {U.fmt(pr['mass'], 'mass', unit='g' if U.normalize_system(None) == 'metric' else 'oz')}")
                        att = [f"{c['status']}: {c['name']} - {c['detail']}" for c in pr["checks"] if c["status"] in ("FAIL", "WARN")]
                    jobs.append(_job_entry(folder, data.get("verdict"), lines, att, data["files"], "CAD"))
                else:
                    jobs.append(_job_entry(folder, data["verdict"], data["summary"], data["attention"],
                                           data["files"], "FEA"))
            else:
                code, out, err = _call(argv)
                outputs.append((f"ea {cmd}", (out + ("\n" + err if code else "")).strip()))
                if code == 2:
                    errors.append(f"`ea {cmd}`: {err.strip() or out.strip()}")
    finally:
        if env_before is None:
            os.environ.pop("ENGAGENT_UNITS", None)
        else:
            os.environ["ENGAGENT_UNITS"] = env_before
    ok = not errors and all(j["verdict"] != "FAIL" for j in jobs)
    res = {"ok": ok, "jobs": jobs, "outputs": outputs, "errors": errors}
    res["text"] = _text(res)
    res["markdown"] = to_markdown(res, link_base)
    return res


def _strip_comments(s: str) -> str:
    import tempfile
    from .fea.job import read_json
    with tempfile.NamedTemporaryFile("w", suffix=".json", delete=False, encoding="utf-8") as f:
        f.write(s)
    try:
        return json.dumps(read_json(f.name))
    finally:
        os.unlink(f.name)


def _cad_lines(info: dict) -> list[str]:
    if not info:
        return []
    s = U.normalize_system(None)
    out = [f"Size {U.fmt_vec(info['bbox_size'], 'length', s)}, volume {U.fmt(info['volume'], 'volume', s)}",
           f"Valid solid: {'yes' if info.get('valid') else 'NO'}"]
    return out


def _run_folder(folder: Path, job: dict) -> dict:
    """Run a job folder written from code blocks: FEA if it has an analysis, else CAD + report."""
    from .report import build_report
    files: list[str] = []
    if job.get("analysis") or job.get("loads") or job.get("constraints"):
        from .fea.run import run_job
        from .viewer import build_viewer
        r = run_job(folder, converge=bool(job.get("converge", True)))
        files += [str(p) for p in build_report(folder)] + [str(build_viewer(folder))]
        from .cad.export import convert
        for st in folder.glob("*.step"):
            files.append(str(st))
            try:
                files += [str(p) for p in convert(st, stl=True)]
            except Exception:
                pass
        return _job_entry(folder, r["verdict"], quick.summary_lines(r), quick.attention_lines(r),
                          files + [str(folder / "job.json")], "FEA")
    from .fea.job import _resolve_geometry
    if "geometry" not in job:
        raise ValueError("the JSON block has neither an analysis nor geometry")
    step = _resolve_geometry(job["geometry"], folder, "part", True, job.get("units"))
    from .cad.export import convert
    files += [str(p) for p in [step] + convert(step, stl=True, threemf=True)]
    from .cad.inspect import inspect_shape
    lines = _cad_lines(inspect_shape(step))
    files += [str(p) for p in build_report(folder)]
    verdict = json.loads((folder / "report.json").read_text())["verdict"]
    return _job_entry(folder, verdict, lines, [], files + [str(folder / "job.json")], "CAD")


# --------------------------------------------------------------------------- formatting
_ICON = {"PASS": "✅ PASS", "REVIEW": "🟡 REVIEW", "FAIL": "❌ FAIL", None: "—"}


def _rel(p: str) -> str:
    from .config import root
    try:
        return str(Path(p).resolve().relative_to(root().resolve())).replace("\\", "/")
    except ValueError:
        return str(p)


def _text(res: dict) -> str:
    out = []
    for j in res["jobs"]:
        out.append(f"== {j['kind']} job {_rel(j['folder'])}: {j['verdict']}")
        out += [f"   {l}" for l in j["summary"]]
        out += [f"   ! {a}" for a in j["attention"]]
        out += [f"   file: {_rel(f)}" for f in j["files"]]
    for cmd, text in res["outputs"]:
        out += [f"== {cmd}", text]
    out += [f"ERROR {e}" for e in res["errors"]]
    return "\n".join(out)


def to_markdown(res: dict, link_base: str | None = None) -> str:
    def link(p: str) -> str:
        r = _rel(p)
        name = Path(r).name
        return f"[{name}]({link_base.rstrip('/')}/{r})" if link_base else f"`{r}`"
    md = []
    if res["errors"]:
        md.append("### ❌ Problems\n" + "\n".join(f"- {e}" for e in res["errors"]))
    for j in res["jobs"]:
        md.append(f"### {_ICON.get(j['verdict'], j['verdict'])} — {j['kind']}: `{_rel(j['folder'])}`")
        if j["summary"]:
            md.append("\n".join(f"- {l}" for l in j["summary"]))
        if j["attention"]:
            md.append("**Needs attention**\n" + "\n".join(f"- {a}" for a in j["attention"][:8]))
        order = {".pdf": 0, ".stl": 1, ".3mf": 2, ".step": 3, ".html": 4, ".json": 5}
        files = sorted(dict.fromkeys(j["files"]), key=lambda f: order.get(Path(f).suffix, 9))
        md.append("**Files:** " + " · ".join(link(f) for f in files))
    for cmd, text in res["outputs"]:
        md.append(f"**`{cmd}`**\n```\n{text[:6000]}\n```")
    if res["jobs"]:
        md.append("<sub>REVIEW = nothing failed but something was not verified (often: no hand calculation "
                  "linked). Engineering assistance, not sign-off.</sub>")
    return "\n\n".join(md) if md else "Nothing to do."


def main_cli(argv=None) -> int:          # pragma: no cover - thin wrapper for `python -m`
    import sys
    text = sys.stdin.read()
    out = run_request(text, markdown=True, link_base=os.environ.get("ENGAGENT_LINK_BASE"))
    print(out["markdown"])
    return 0 if out["ok"] else 1


if __name__ == "__main__":               # pragma: no cover
    raise SystemExit(main_cli())
