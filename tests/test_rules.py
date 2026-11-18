"""Common requests are read from the user's words with no language model."""
import pytest

from engagent import assistant, structured
from engagent.rules import form_from_words

BEAM = ("Mild steel bar 200 x 10 x 20 mm, bolted to a wall at one end, with a 50 kg weight hanging from the free "
        "end. How much does it bend?")
HOT = ("Steel bar 100 mm long. One end is held at 100 C, the other end is cooled by air at 20 C with h = 25. "
       "How hot does the cooled end get?")


def _req(text):
    f = form_from_words(text)
    assert f, text
    assert structured.magnitudes_from_user(f, text) == []
    req, q = structured.build_request(f, text)
    assert q is None, q
    return req


def test_cantilever_from_words():
    req = _req(BEAM)
    assert "length=200 width=10 height=20" in req and "-m steel_generic --fix xmin --force xmax 0,0,-490.332" in req


def test_hot_bar_from_words():
    assert "-a thermal --temp xmin 100 --convect xmax 25 20" in _req(HOT)


def test_print_requests_from_words():
    assert _req("printable PETG box 100x70x40 with 2.4 mm walls").startswith(
        "ea make enclosure length=100 width=70 height=40 wall=2.4 --print petg")
    assert "ea make wall_hook" in _req("I need a wall hook to 3D print for my coat")
    assert "--print pla" in _req("a phone stand in PLA")
    assert "length=101.6" in _req("print a plate 4 x 2 x 0.25 in")


def test_plate_edges():
    assert "--fix xmin --force zmax 0,0,-20" in _req("aluminium plate 100 x 60 x 4 clamped along one short edge, "
                                                     "20 N pushing down on top. Will it bend much?")
    assert "--fix ymin" in _req("steel plate clamped along one long edge with 2 kg sitting on top, deflection?")
    assert "--pressure zmax 0.01" in _req("aluminium plate clamped on all four edges, 0.1 bar pressure on top, stress?")


@pytest.mark.parametrize("text", [
    "steel bar fixed at one end with 500 N at the tip, how much does it bend?",     # no direction given
    "aluminum L-bracket with 300 N on it, is it strong enough?",                     # bracket: model
    "steel beam 1 m long, both ends supported, 2 kN in the middle - stress?",        # mid-span: model
    "a bar at one end with 50 kg hanging at the end, how much does it bend?",       # no material
    "how strong is a bar",
    "steel bar, one end 100 C, how hot is the other end?",                           # no h
    "make me something nice",
])
def test_unsure_requests_go_to_the_model(text):
    assert form_from_words(text) is None


@pytest.mark.solver
def test_rules_run_end_to_end_without_any_model(monkeypatch, tmp_path):
    for v in ("ENGAGENT_LLM_URL", "ENGAGENT_LLM_KEY", "ENGAGENT_LLM_MODEL", "GITHUB_TOKEN"):
        monkeypatch.delenv(v, raising=False)
    monkeypatch.setenv("ENGAGENT_LLM_URL", "http://127.0.0.1:9/never")    # any model call would fail
    monkeypatch.setenv("ENGAGENT_ROOT", str(tmp_path))
    out = assistant.ask(BEAM)
    assert out["kind"] == "results" and out["by_rules"], out
    fea = out["result"]["jobs"][1]
    assert fea["verdict"] == "PASS", fea
    out = assistant.ask(HOT)
    assert out["kind"] == "results" and out["result"]["jobs"][1]["verdict"] == "PASS"


def test_plate_and_bar_get_automatic_hand_checks():
    from engagent import quick
    job = quick.build_analysis_job("plate", material="al_6061_t6", fix=["ymin"], forces=[["zmax", "0,0,-98.0665"]],
                                   params={"length": 300, "width": 200, "thickness": 6})
    hc = job["hand_calcs"][0]
    assert hc["calc"] == "beam.cantilever_udl" and hc["metric"] == "max_displacement" and hc["tol"] == 0.1
    job = quick.build_analysis_job("beam", material="steel_generic", analysis="thermal", temps=[["xmin", "100"]],
                                   convects=[["xmax", "25", "20"]], params={"length": 100})
    assert [h["output"] for h in job["hand_calcs"]] == ["T_surface", "heat_flow"]


def test_the_body_names_the_part_not_the_title():
    text = ("Request: steel shelf bracket bar\n\nSteel bar 150 x 12 x 25 mm bolted to a wall at one end, with 20 kg "
            "hanging from the free end. How much does it bend - is it safe?")
    assert "ea make beam length=150 width=12 height=25" in _req(text)
    assert form_from_words("a lid for my electronics box")["template"] == "lid"
    assert form_from_words("a box with a lid, 100x60x40")["template"] == "enclosure"


@pytest.mark.parametrize("text, expected", [
    ("print a washer 20 mm OD, 8.4 mm hole, 2 mm thick in PETG",
     'ea make standoff outer_diameter=20 hole=8.4 height=2 --print petg --name "washer"'),
    ("I need a spacer for an M5 bolt, 12 mm diameter, 15 mm long",
     'ea make standoff outer_diameter=12 hole=5.5 height=15 --print petg --name "spacer"'),
    ("3d print a 30 mm cube", 'ea make plate length=30 width=30 thickness=30 --print petg --name "cube"'),
    ("a PLA disc 40 mm diameter 3 mm thick", 'ea make standoff outer_diameter=40 hole=0 height=3 --print pla --name "disc"'),
    ("a block 60 x 40 x 10 with M4 holes in the corners",
     'ea make plate length=60 width=40 thickness=10 hole_diameter=4.5 --print petg --name "block"'),
    ("plate 80 x 50 x 5 with a 10 mm hole in the middle",
     'ea make plate length=80 width=50 thickness=5 center_hole=10 --print petg --name "plate"'),
    ("tube 25 mm od 21 mm id 100 mm long", 'ea make standoff outer_diameter=25 hole=21 height=100 --print petg --name "tube"'),
])
def test_simple_shapes_from_words(text, expected):
    assert _req(text) == expected


JOINED = ("A steel bar and an aluminium bar, 10 x 10 mm, 50 mm long each, are bonded end to end. The steel end is "
          "fixed at one end and the aluminium end is pulled with 5 kN. How much does it stretch?")


def test_joined_bars_become_a_tied_assembly():
    from engagent.guard import check_request
    import json
    f = form_from_words(JOINED)
    assert f["action"] == "job"
    job = f["job"]
    assert [p["material"] for p in job["parts"]] == ["steel_generic", "al_6061_t6"]
    assert job["parts"][1]["geometry"]["position"] == [50.0, 0, 0]
    assert job["loads"][0]["value"] == [5000.0, 0, 0] and job["interactions"][0]["type"] == "tie"
    assert check_request("```json\n" + json.dumps(job) + "\n```", JOINED) == []
    # a material the user never named is refused
    job["parts"][1]["material"] = "ti_6al4v"
    assert check_request("```json\n" + json.dumps(job) + "\n```", JOINED)


def test_stretch_is_an_analysis_question():
    f = form_from_words("steel bar 100 x 10 x 10 mm fixed at one end, pulled with 2 kN at the free end, how much "
                        "does it stretch?")
    assert f is None or f["action"] != "make"          # never a silent CAD-only answer


@pytest.mark.solver
def test_joined_bars_end_to_end(monkeypatch, tmp_path):
    monkeypatch.setenv("ENGAGENT_LLM_URL", "http://127.0.0.1:9/never")
    monkeypatch.setenv("ENGAGENT_ROOT", str(tmp_path))
    out = assistant.ask(JOINED)
    assert out["kind"] == "results" and out["by_rules"]
    fea = out["result"]["jobs"][0]
    assert fea["verdict"] == "PASS" and any("Series elongation" in l and "PASS" in l for l in fea["summary"])
