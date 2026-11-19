"""Benchmark loop: cases are well formed and the judge scores fairly."""
import json

from engagent import bench


def test_cases_are_well_formed():
    cs = bench.cases()
    assert len(cs) >= 10
    for c in cs:
        exp = json.loads((c / "expected.json").read_text())
        assert exp["source"] and exp["expect"]
        prompt = (c / "prompt.md").read_text()
        for e in exp["expect"]:                      # the answer must never leak into the prompt
            if isinstance(e.get("expected"), float):
                assert f"{e['expected']:.3g}" not in prompt


def test_judge_scores_by_magnitude_and_tolerance():
    assert bench._judge({"expected": -126.0, "tol": 0.15}, 120.0)[0]          # compressive stress, by size
    assert not bench._judge({"expected": 0.94, "tol": 0.05}, 1.2)[0]
    assert bench._judge({"expected": [100, 70, 40], "tol": 0.001}, [100.0, 70.0, 40.0])[0]
    assert not bench._judge({"expected": 1.0, "tol": 0.05}, None)[0]
    assert bench._judge({"expected": True, "tol": 0}, True)[0]


def test_scoreboard_counts_passes():
    rows = [{"case": "a", "outcome": "PASS", "seconds": 3}, {"case": "b", "outcome": "ASKED", "seconds": 1}]
    md = bench.scoreboard(rows)
    assert "1 / 2 PASS" in md and "| b | ASKED |" in md


def test_no_benchmark_answer_leaks_into_the_chatbot_prompt():
    """The prompt's examples must not reuse a benchmark case (a solver could copy it)."""
    import re
    from engagent.prompt import chatbot_prompt
    text = chatbot_prompt("metric")
    for c in bench.cases():
        nums = re.findall(r"\d+(?:\.\d+)?", (c / "prompt.md").read_text())
        key = " ".join(nums)
        assert len(nums) < 3 or key not in " ".join(re.findall(r"\d+(?:\.\d+)?", text)), c.name


def test_judge_bounds_catch_a_missing_feature():
    assert not bench._judge({"metric": "cad.volume", "max": 5900}, 6000.0)[0]   # plain plate, no slots
    assert bench._judge({"metric": "cad.volume", "max": 5900}, 5600.0)[0]
