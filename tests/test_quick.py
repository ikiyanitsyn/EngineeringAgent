import json

import pytest

from engagent import quick
from engagent.prompt import chatbot_prompt
from engagent.request import parse


def test_selector_shorthand():
    assert quick.selector("XMIN") == "xmin"
    assert quick.selector("plane:z=12.5") == {"plane": "z", "at": 12.5}
    assert quick.selector("hole:6.6@40,20,0") == {"cylinder": {"diameter": 6.6, "near": [40.0, 20.0, 0.0]}}
    assert quick.selector("cyl:5") == {"cylinder": {"radius": 5.0}}
    assert quick.selector("near:1,2,3") == {"near": [1.0, 2.0, 3.0]}
    assert quick.selector("xmin+cyl:3+plane:y=0") == ["xmin", {"cylinder": {"radius": 3.0}}, {"plane": "y", "at": 0.0}]
    assert quick.selector("faces:3,7") == {"faces": [3, 7]}
    with pytest.raises(ValueError, match="unknown face selector"):
        quick.selector("left side")


def test_numbers_with_units_and_exponents():
    assert quick._nums("0,0,-500") == [0.0, 0.0, -500.0]
    assert quick._nums(" -300,0,0") == [-300.0, 0.0, 0.0]
    assert quick._nums("0,0,-30lbf") == ["0 lbf", "0 lbf", "-30 lbf"]
    assert quick._nums("2.5e3") == [2500.0]


def test_job_numbering(tmp_path):
    a = quick.next_job_folder("My Part!", tmp_path)
    b = quick.next_job_folder("my part", tmp_path)
    assert a.name == "01-my-part" and b.name == "02-my-part"


def test_build_analysis_job_static_and_thermal():
    j = quick.build_analysis_job("beam", material="steel_generic", fix=["xmin"], forces=[["xmax", "0,0,-100"]],
                                 checks=["beam.cantilever_end_load P=100 L=100 E=210GPa b=10 h=10"], system="metric")
    assert j["analysis"] == "static" and j["sets"] == {"xmin": "xmin", "xmax": "xmax"}
    assert j["hand_calcs"][0]["metric"] == "probe.xmax.displacement" and j["criteria"]["yield_sf"] == 1.5
    t = quick.build_analysis_job("beam", material="steel_generic", temps=[["xmin", "100"]],
                                 convects=[["xmax", "25", "20"]], system="metric")
    assert t["analysis"] == "thermal_steady"
    s = quick.build_analysis_job("beam", material="steel_generic", dtemp="120", system="metric")
    assert s["analysis"] == "thermal_stress" and {"type": "minimal"} in s["constraints"]
    with pytest.raises(ValueError, match="needs a material"):
        quick.build_analysis_job("beam", material=None, fix=["xmin"])


def test_parse_chatbot_reply():
    reply = ("Here you go:\n```bash\nea make plate length=100 --print petg\n./ea analyze last -m pla \\\n"
             "  --fix xmin --force xmax 0,0,-5\n```\nAlso:\n```json\n{\"analysis\": \"static\"}\n```\n"
             "```python\nfrom build123d import *\n```\nRun `ea gdt fit 25 H7/g6` too.")
    r = parse(reply)
    assert r["commands"][0] == "make plate length=100 --print petg"
    assert r["commands"][1].startswith("analyze last -m pla") and "--force xmax 0,0,-5" in r["commands"][1]
    assert r["commands"][2] == "gdt fit 25 H7/g6"
    assert json.loads(r["json"][0]) == {"analysis": "static"} and "build123d" in r["python"][0]
    assert parse("just words")["commands"] == []


def test_prompt_is_current():
    from pathlib import Path
    text = chatbot_prompt("metric")
    assert "l_bracket" in text and "al_6061_t6" in text and "--check" in text
    doc = Path(__file__).resolve().parent.parent / "docs" / "CHATBOT-PROMPT.md"
    assert doc.read_text(encoding="utf-8") == text, "regenerate with: ea prompt -o docs/CHATBOT-PROMPT.md"


@pytest.mark.solver
def test_request_end_to_end(tmp_path, monkeypatch):
    from engagent.request import run_request
    monkeypatch.setenv("ENGAGENT_ROOT", str(tmp_path))
    r = run_request("```bash\nea make beam --name bar\nea analyze last -m steel_generic --fix xmin "
                    "--force xmax 0,0,-100 --quick --check \"beam.cantilever_end_load P=100 L=100 E=210GPa b=10 h=10 nu=0.3\"\n"
                    "ea make enclosure --print petg --no-report\nea rm -rf /\n```")
    assert [j["kind"] for j in r["jobs"]] == ["CAD", "FEA", "CAD"]
    assert any("not allowed" in e for e in r["errors"])
    fea = r["jobs"][1]
    assert any("Hand calc" in l and "PASS" in l for l in fea["summary"])
    assert (tmp_path / "jobs" / "01-bar" / "part.stl").exists()
