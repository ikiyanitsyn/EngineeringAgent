"""Benchmark FEA jobs against closed-form answers.  Run with:  pytest -m solver"""
import pytest

from engagent.fea.run import run_job
from engagent.fea.starters import STARTERS, starter

pytestmark = pytest.mark.solver

CASES = [(n, "metric") for n in STARTERS] + [("static", "imperial"), ("thermal_steady", "imperial"),
                                              ("thermal_stress", "imperial"), ("modal", "imperial")]


def _run(name, system, folder, **kw):
    job = starter(name, system)
    for fname, text in job.pop("files_needed", {}).items():
        (folder / fname).write_text(text, encoding="utf-8")
    return run_job(job, folder, **kw)


@pytest.mark.parametrize("name,system", CASES, ids=[f"{n}-{s}" for n, s in CASES])
def test_benchmark_matches_hand_calculation(name, system, tmp_path):
    r = _run(name, system, tmp_path)
    assert r["status"] == "ok", r["solver"]["errors"]
    compared = [h for h in r["hand_calcs"] if "diff" in h]
    assert compared, "benchmark has no linked hand calculation"
    for h in compared:
        assert h["status"] == "PASS", f"{h['name']}: {h['diff'] * 100:.2f} % (tol {h['tol'] * 100:g} %)"
    assert not [c for c in r["checks"] if c["status"] == "FAIL"], r["checks"]
    assert r["verdict"] in ("PASS", "REVIEW")


def test_converged_static_job_passes_everything_and_reports(tmp_path):
    from engagent.report import build_report
    from engagent.viewer import build_viewer
    r = _run("static", "metric", tmp_path, converge=True)
    assert r["verdict"] == "PASS", [c for c in r["checks"] if c["status"] != "PASS"]
    eq = next(c for c in r["checks"] if c["id"] == "equilibrium")
    assert eq["status"] == "PASS"
    files = build_report(tmp_path)
    assert {f.suffix for f in files} == {".html", ".pdf"} and all(f.stat().st_size > 20_000 for f in files)
    html = (tmp_path / "report.html").read_text(encoding="utf-8")
    assert "Verification checklist" in html and "Hand calculations" in html
    assert build_viewer(tmp_path).stat().st_size > 50_000


def test_results_are_repeatable(tmp_path):
    runs = []
    for sub in ("a", "b"):
        (tmp_path / sub).mkdir()
        runs.append(_run("static", "metric", tmp_path / sub))
    for key in ("max_displacement", "peak_von_mises", "reaction_total"):
        assert runs[0]["metrics"][key]["value"] == pytest.approx(runs[1]["metrics"][key]["value"], rel=1e-9)


def test_solver_error_is_reported_not_hidden(tmp_path):
    job = starter("static", "metric")
    job["constraints"] = [{"type": "displacement", "on": "fixed", "x": 0}]      # under-constrained
    r = run_job(job, tmp_path)
    assert r["verdict"] == "FAIL" or any(c["status"] == "FAIL" for c in r["checks"])


def test_wrong_load_is_caught_by_hand_calc(tmp_path):
    job = starter("static", "metric")
    job["loads"][0]["value"] = [0, 0, -150]          # load does not match the hand calculation
    r = run_job(job, tmp_path)
    assert r["verdict"] == "FAIL"
    assert next(c for c in r["checks"] if c["id"] == "hand_calc")["status"] == "FAIL"
