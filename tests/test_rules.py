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
