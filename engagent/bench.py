"""Benchmark loop, phases 0-1: real engineering cases solved blind, scored against known answers.

Each case in benchmarks/NNN-name/ has
* prompt.md      - the plain-English request an engineer would type (all the solver ever sees)
* expected.json  - the source and the expected results with tolerances (never shown to the solver)

`ea bench` sends each prompt through exactly the path the issue bot uses (rules first, then the
configured model, e.g. the user's Gemini key) and scores the results. The scoreboard
(benchmarks/SCOREBOARD.md) is what the later judge and improver phases will learn from.
"""
from __future__ import annotations

import json
import os
import tempfile
import time
from pathlib import Path


def project_root() -> Path:
    """The repository (benchmarks live next to the package, whatever ENGAGENT_ROOT points at)."""
    return Path(__file__).resolve().parent.parent


def cases(root: Path | None = None, only: str | None = None) -> list[Path]:
    base = Path(root or project_root()) / "benchmarks"
    out = sorted(p for p in base.iterdir() if (p / "prompt.md").exists() and (p / "expected.json").exists())
    return [p for p in out if not only or only in p.name]


def _metric(job_folder: Path, name: str):
    """A value from a job: results.json metrics, or cad.size / cad.valid from the CAD summary."""
    if name.startswith("cad."):
        info = next(iter(sorted(job_folder.glob("*.cad.json"))), None)
        if not info:
            return None
        d = json.loads(info.read_text())
        return {"cad.size": d.get("bbox_size"), "cad.valid": bool(d.get("valid")) and d.get("solids", 1) == 1}.get(name)
    r = job_folder / "results.json"
    if not r.exists():
        return None
    m = json.loads(r.read_text()).get("metrics", {}).get(name)
    return m["value"] if m else None


def _judge(exp: dict, got) -> tuple[bool, str]:
    want, tol = exp["expected"], float(exp.get("tol", 0.05))
    if got is None:
        return False, "no such result"
    if isinstance(want, bool):
        return bool(got) == want, f"{got}"
    if isinstance(want, list):
        ok = len(got) == len(want) and all(abs(abs(g) - abs(w)) <= tol * max(abs(w), 1) for g, w in zip(got, want))
        return ok, "x".join(f"{g:.4g}" for g in got)
    diff = abs(abs(got) - abs(want)) / max(abs(want), 1e-30)
    return diff <= tol, f"{got:.4g} ({diff * 100:.1f} % off, tol {tol * 100:g} %)"


def run_case(case: Path, work: Path) -> dict:
    """Solve one case blind and score it."""
    from . import assistant
    prompt = (case / "prompt.md").read_text(encoding="utf-8").strip()
    expected = json.loads((case / "expected.json").read_text())
    os.environ["ENGAGENT_ROOT"] = str(work)
    t0 = time.time()
    row = {"case": case.name, "source": expected.get("source", "")}
    assistant.LAST_USED.clear()
    try:
        out = assistant.ask(prompt)
    except Exception as e:                       # the service was down, or the model failed
        row.update(outcome="ERROR", detail=f"{type(e).__name__}: {str(e)[:200]}", seconds=time.time() - t0)
        return row
    row["seconds"] = time.time() - t0
    row["request"] = (out.get("request") or out.get("reply") or "")[:4000]   # what the solver ran (for the judge)
    print("    request:\n      " + row["request"].replace("\n", "\n      ")[:2000], flush=True)
    row["answered_by"] = ("rules" if out.get("by_rules") else
                          (assistant.LAST_USED.get("model") or "model"))
    if out.get("kind") == "question":
        row.update(outcome="ASKED", detail=(out.get("reply") or "")[:200].replace("\n", " "))
        return row
    jobs = [Path(j["folder"]) for j in (out.get("result") or {}).get("jobs", [])]
    errors = (out.get("result") or {}).get("errors", [])
    checks = []
    for exp in expected["expect"]:
        got = None
        for j in reversed(jobs):                 # the last job holding the metric (FEA after CAD)
            got = _metric(j, exp["metric"])
            if got is not None:
                break
        ok, detail = _judge(exp, got)
        checks.append({"metric": exp["metric"], "expected": exp["expected"], "ok": ok, "detail": detail})
    row["checks"] = checks
    row["outcome"] = "PASS" if checks and all(c["ok"] for c in checks) else "FAIL"
    row["detail"] = "; ".join(f"{c['metric']}: {c['detail']}" for c in checks) + \
        (f" | errors: {'; '.join(errors)[:200]}" if errors else "")
    return row


def run(only: str | None = None, out_md: Path | None = None) -> list[dict]:
    rows = []
    keep = os.environ.get("ENGAGENT_ROOT")
    try:
        for case in cases(only=only):
            with tempfile.TemporaryDirectory(prefix="bench-") as work:
                print(f"[{time.strftime('%H:%M:%S')}] {case.name} ...", flush=True)
                rows.append(run_case(case, Path(work)))
                print(f"    {rows[-1]['outcome']}: {rows[-1].get('detail', '')}", flush=True)
    finally:
        if keep is None:
            os.environ.pop("ENGAGENT_ROOT", None)
        else:
            os.environ["ENGAGENT_ROOT"] = keep
    if out_md:
        out_md.write_text(scoreboard(rows), encoding="utf-8")
        out_md.with_suffix(".json").write_text(json.dumps(rows, indent=1, default=str), encoding="utf-8")
    return rows


def scoreboard(rows: list[dict]) -> str:
    n = len(rows)
    passed = sum(r["outcome"] == "PASS" for r in rows)
    lines = [f"# Benchmark scoreboard", "",
             f"{time.strftime('%Y-%m-%d %H:%M')} - **{passed} / {n} PASS** "
             f"(solved blind from the plain-English prompt; answers from the cited source).", "",
             "| Case | Outcome | Answered by | Time | Detail | Source |", "|---|---|---|---|---|---|"]
    for r in rows:
        lines.append(f"| {r['case']} | {r['outcome']} | {r.get('answered_by', '-')} | {r.get('seconds', 0):.0f} s | "
                     f"{r.get('detail', '').replace('|', '/')} | {r.get('source', '')} |")
    lines += ["", "PASS = every expected value within tolerance. ASKED = the agent asked a question instead "
              "(fine when the prompt really lacks an input, otherwise a gap). FAIL / ERROR = a gap to fix."]
    return "\n".join(lines) + "\n"
