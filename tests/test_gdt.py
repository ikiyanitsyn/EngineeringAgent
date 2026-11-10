import pytest

from engagent import gdt


def um(f, part):
    return round(f[part]["lower_dev"] * 1000), round(f[part]["upper_dev"] * 1000)


@pytest.mark.parametrize("nominal,fit,hole,shaft,kind", [
    (25, "H7/g6", (0, 21), (-20, -7), "clearance"),
    (25, "H7/p6", (0, 21), (22, 35), "interference"),
    (25, "H7/k6", (0, 21), (2, 15), "transition"),
    (25, "H8/f7", (0, 33), (-41, -20), "clearance"),
    (25, "H7/s6", (0, 21), (35, 48), "interference"),
    (10, "H7/h6", (0, 15), (-9, 0), "clearance"),
    (60, "H7/s6", (0, 30), (53, 72), "interference"),
    (100, "H9/d9", (0, 87), (-207, -120), "clearance"),
    (6, "H7/n6", (0, 12), (8, 16), "transition"),
])
def test_iso286_table_values(nominal, fit, hole, shaft, kind):
    f = gdt.fit(nominal, fit, "metric")
    assert um(f, "hole") == hole
    assert um(f, "shaft") == shaft
    assert f["type"] == kind


def test_fit_in_inches():
    f = gdt.fit("1 in", "H7/g6")
    assert f["nominal"] == pytest.approx(25.4)
    assert um(f, "hole") == (0, 21)


def test_fit_errors():
    with pytest.raises(ValueError):
        gdt.fit(600, "H7/g6", "metric")
    with pytest.raises(ValueError):
        gdt.fit(25, "K7/h6", "metric")


def test_general_tolerances():
    assert gdt.general_tolerance(50, "m", "metric") == 0.3
    assert gdt.general_tolerance(5, "f", "metric") == 0.05
    assert gdt.general_tolerance(500, "c", "metric") == 2.0
    assert gdt.general_tolerance(50, "K", "metric", "flatness") == 0.2
    with pytest.raises(ValueError):
        gdt.general_tolerance(3000, "f", "metric")


def test_clearance_and_position():
    assert gdt.clearance_hole("M6")["hole"] == 6.6
    assert gdt.clearance_hole("1/4-20", "normal")["hole"] == pytest.approx(0.281 * 25.4)
    assert gdt.position_tolerance(6, 6.6, "floating", "metric")["position_tolerance"] == pytest.approx(0.6)
    assert gdt.position_tolerance(6, 6.6, "fixed", "metric")["position_tolerance"] == pytest.approx(0.3)
    assert gdt.bonus(0.2, 6.5, 6.6, "hole", "metric")["total"] == pytest.approx(0.3)


def test_stack():
    s = gdt.stack([{"name": "a", "nominal": 50, "tol": 0.1, "direction": 1},
                   {"name": "b", "nominal": 15, "plus": 0, "minus": 0.12, "direction": -1},
                   {"name": "c", "nominal": 34.8, "tol": 0.05, "direction": -1}],
                  "metric", limits={"min": 0.05, "max": 0.5}, monte_carlo=5000)
    assert s["nominal"] == pytest.approx(0.26)
    assert s["worst_case_min"] == pytest.approx(0.05)
    assert s["worst_case_max"] == pytest.approx(0.47)
    assert s["rss_min"] == pytest.approx(0.26 - (0.1**2 + 0.06**2 + 0.05**2) ** 0.5)
    assert s["status"] == "PASS"
    assert abs(s["monte_carlo"]["mean"] - 0.26) < 0.005
    bad = gdt.stack([{"nominal": 10, "tol": 0.5, "direction": 1}, {"nominal": 9.9, "tol": 0.5, "direction": -1}],
                    "metric", limits={"min": 0.0})
    assert bad["status"] == "FAIL"


def test_frames():
    f = gdt.frame("position", 0.2, ["A", "B", "C"], diameter=True, modifier="M", system="metric")
    assert f["plain"] == "position dia 0.2 (MMC) to A-B-C"
    assert f["text"].count("|") == 6
    assert gdt.frame("flatness", "0.002 in", system="imperial")["plain"] == "flatness .002"


def test_review_finds_rule_violations():
    spec = {"standard": "asme", "process": "cnc_milling",
            "datums": [{"label": "A", "feature": "base"}],
            "features": [
                {"name": "base", "type": "surface", "fcf": {"characteristic": "flatness", "tolerance": 0.05, "datums": ["A"]}},
                {"name": "bore", "type": "hole", "nominal": 20, "fit": "H7/g6",
                 "fcf": {"characteristic": "concentricity", "tolerance": 0.05, "datums": ["A"]}},
                {"name": "face", "type": "surface", "fcf": {"characteristic": "position", "tolerance": 0.1, "modifier": "M", "datums": ["B"]}},
                {"name": "holes", "type": "hole", "nominal": 6.6, "tol": 0.1,
                 "fcf": {"characteristic": "position", "tolerance": 0.5, "diameter": True, "datums": ["A"]},
                 "fastener": {"size": "M6", "joint": "fixed"}}]}
    r = gdt.review(spec, "metric")
    msgs = " | ".join(f["message"] for f in r["findings"])
    assert r["status"] == "FAIL"
    assert "must not reference datums" in msgs
    assert "removed from ASME Y14.5-2018" in msgs
    assert "datum B, which is not defined" in msgs
    assert "features of size" in msgs
    assert "fixed-fastener limit" in msgs


def test_review_clean_scheme_passes():
    spec = {"datums": [{"label": "A", "feature": "base"}, {"label": "B", "feature": "edge"}, {"label": "C", "feature": "side"}],
            "features": [
                {"name": "base", "type": "surface", "fcf": {"characteristic": "flatness", "tolerance": 0.1}},
                {"name": "edge", "type": "surface", "fcf": {"characteristic": "perpendicularity", "tolerance": 0.1, "datums": ["A"]}},
                {"name": "side", "type": "surface", "fcf": {"characteristic": "perpendicularity", "tolerance": 0.1, "datums": ["A", "B"]}},
                {"name": "holes", "type": "hole", "nominal": 6.6, "tol": 0.1,
                 "fcf": {"characteristic": "position", "tolerance": 0.25, "diameter": True, "modifier": "M", "datums": ["A", "B", "C"]},
                 "fastener": {"size": "M6", "joint": "fixed"}}]}
    r = gdt.review(spec, "metric")
    assert r["status"] == "PASS", r["findings"]
    assert r["standard"] == "iso"
