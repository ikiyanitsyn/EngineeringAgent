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
    "aluminum L-bracket with 300 N on it, is it strong enough?",                     # bracket: model
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
     'ea make standoff outer_diameter=12 hole=5.5 height=15 --name "spacer"'),
    ("3d print a 30 mm cube", 'ea make plate length=30 width=30 thickness=30 --print petg --name "cube"'),
    ("a PLA disc 40 mm diameter 3 mm thick", 'ea make standoff outer_diameter=40 hole=0 height=3 --print pla --name "disc"'),
    ("a block 60 x 40 x 10 with M4 holes in the corners",
     'ea make plate length=60 width=40 thickness=10 hole_diameter=4.5 --name "block"'),
    ("plate 80 x 50 x 5 with a 10 mm hole in the middle",
     'ea make plate length=80 width=50 thickness=5 center_hole=10 --name "plate"'),
    ("tube 25 mm od 21 mm id 100 mm long", 'ea make standoff outer_diameter=25 hole=21 height=100 --name "tube"'),
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



def test_missing_analysis_inputs_get_one_question():
    """Live: 'run a simple cantilever ... 500 newtons, steel, 2meters' got a 10x10 default and CAD only."""
    for text in ["run a simple cantilever beam loaded at one end 500 newtons, material is steel, length is 2meters",
                 "steel bar fixed at one end with 500 N at the tip, how much does it bend?"]:
        f = form_from_words(text)
        assert f["action"] == "question" and "cross-section" in f["question"] and "direction" in f["question"]
    req = _req("run a simple cantilever beam loaded at one end 500 newtons, material is steel, length is 2meters"
               "\n\n20 x 40 mm, straight down")
    assert "width=20 height=40 length=2000" in req and "--force xmax 0,0,-500" in req and "--print" not in req


def test_print_check_only_when_printing_is_mentioned():
    assert "--print" not in _req("make me a beam 300 mm long")
    assert "--print petg" in _req("I need a wall hook to 3D print for my coat")


def test_bound_hand_calcs_are_marked_and_kept_by_autocorrect():
    from engagent import quick
    from engagent.cli import _bound_spec
    from engagent.guard import autocorrect
    assert _bound_spec("beam.cantilever_end_load P=1 L=2 E=3 b=4 h=5 upper").startswith("bound:upper beam.")
    job = quick.build_analysis_job("l_bracket", material="al_6061_t6", fix=["hole:6.6@40,20,0"],
                                   forces=[["hole:6.6@0,20,40", "0,300,0"]], params={"thickness": 6},
                                   checks=[_bound_spec("beam.cantilever_end_load P=300 L=40 E=69GPa b=6 h=40")])
    assert job["hand_calcs"][0]["bound"] == "lower" and job["hand_calcs"][0]["name"].startswith("Estimate:")
    req = ('ea analyze last -m steel_s235 --fix xmin --force xmax 0,300,0 --bound '
           '"beam.cantilever_end_load P=300 L=40 E=210GPa b=6 h=40"')
    fixed, notes = autocorrect(req, "same bracket in mild steel, 300 N")
    assert "--bound" in fixed and "steel_generic" in fixed and any("hand check" in n for n in notes)


@pytest.mark.solver
def test_bracket_bound_never_fails_a_correct_fea(monkeypatch, tmp_path):
    """The rigid-base cantilever estimate is ~50x stiffer than the real bracket: consistent, not a FAIL."""
    from engagent import quick
    from engagent.cli import _bound_spec
    monkeypatch.setenv("ENGAGENT_ROOT", str(tmp_path))
    out = quick.analyze("l_bracket", params={"thickness": 6}, material="al_6061_t6", fix=["hole:6.6@40,20,0"],
                        forces=[["hole:6.6@0,20,40", "0,300,0"]], converge=False, report=False,
                        checks=[_bound_spec("beam.cantilever_end_load P=300 L=40 E=69GPa b=6 h=40")])
    r = out["results"]
    hc = next(c for c in r["checks"] if c["id"] == "hand_calc")
    assert hc["status"] == "PASS" and "consistent" in hc["detail"], hc
    assert r["hand_calcs"][0]["ratio"] > 10


@pytest.mark.solver
def test_python_block_with_a_misnamed_make_line_builds_once(monkeypatch, tmp_path):
    """Live issue #18: Gemini wrote `ea make` and `ea make part.py --print petg` next to its python block."""
    from engagent.request import run_request
    monkeypatch.setenv("ENGAGENT_ROOT", str(tmp_path))
    txt = ("```python\nfrom build123d import *\nfrom engagent.cad import params, save\n"
           "save(Box(60, 25, 13.5, align=(Align.MIN, Align.MIN, Align.MIN)))\n```\n"
           "```bash\nea make\nea make part.py --print petg --name \"clip\"\n```")
    r = run_request(txt)
    assert r["errors"] == [] and len(r["jobs"]) == 1
    assert any("3D-print check" in l for l in r["jobs"][0]["summary"])


def test_holding_cables_is_not_an_analysis_question():
    from engagent.guard import analysis_intent
    assert not analysis_intent("a clip that holds three 6 mm cables under the desk")
    assert analysis_intent("will it hold 5 kg?") and analysis_intent("is it strong enough")


def test_a_follow_up_comment_never_changes_the_part():
    """Live issue #18: 'the previous answer (a plain standoff) was wrong' made the rules build a standoff."""
    orig = "A 3D-printable cable organizer clip that holds three 6 mm cables and screws under a desk with one M4."
    later = "The previous answer (a plain standoff) was wrong. Try again please."
    assert form_from_words(orig + "\n" + later, first=orig) is None
    c = "run a simple cantilever beam loaded at one end 500 newtons, material is steel, length is 2meters"
    f = form_from_words(c + "\n60 x 120 mm, straight down", first=c)
    assert f["action"] == "analyze" and f["params"]["height"] == 120


def test_simply_supported_beam_uses_half_model_symmetry():
    """Benchmark 002: Gemini clamped both ends (--fix xmin --fix xmax) - 86 % off the textbook."""
    t = ("A steel beam 1 m long with a 40 x 80 mm cross-section (80 mm tall) rests on supports at both ends and "
         "carries 2 kN straight down at the middle. How much does it deflect?")
    f = form_from_words(t)
    assert f["action"] == "raw"
    r = f["request"]
    assert "length=500" in r and "--slide xmin z" in r and "--slide xmax x" in r and "0,0,-1000" in r
    assert "--fix" not in r and "simply_supported_center_load P=2000 L=1000" in r
    fx = form_from_words(t.replace("rests on supports", "is welded"))["request"]   # fixed ends: held fully
    assert "--fix xmin --slide xmax x" in fx and "fixed_fixed_center_load P=2000 L=1000" in fx


def test_an_alloy_number_is_not_a_pressure():
    import re
    from engagent.rules import PRESSURE_RX
    assert not re.findall(PRESSURE_RX, "aluminium 6061 bar, 400 mm long")
    assert re.findall(PRESSURE_RX, "a pipe at 10 bar") == [("10", "bar")]


def test_simply_supported_beam_asks_only_for_what_is_missing():
    f = form_from_words("steel beam 1 m long, both ends supported, 2 kN in the middle - stress?")
    q = f["question"]
    assert f["action"] == "question" and "cross-section" in q and "direction" in q and "length" not in q


def test_column_and_restrained_bar_rules():
    """Benchmarks 003 / 006: Gemini's backup model got the column ends wrong and misused --dT."""
    c = form_from_words(open("benchmarks/003-column-buckling/prompt.md").read())
    assert c["action"] == "raw" and "-a buckling --fix xmin --force xmax -1000,0,0" in c["request"]
    assert "ends=fixed_free" in c["request"]
    r = form_from_words(open("benchmarks/006-restrained-bar-heating/prompt.md").read())
    assert r["action"] == "raw" and "--t0 20 --dT 70" in r["request"] and "--slide xmin x" in r["request"]
    assert "dT=50" in r["request"]


def test_a_bare_moment_is_newton_metres_not_millimetres():
    from engagent.guard import check_request
    u = "Steel shaft 20 mm diameter, 200 mm long, clamped at one end, 100 N m of torque at the other end"
    assert check_request("ea analyze last -m steel_generic --fix zmin --moment zmax 0,0,100000", u)   # 1000x
    assert not check_request("ea analyze last -m steel_generic --fix zmin --moment zmax 0,0,100", u)
    assert not check_request("ea analyze last -m steel_generic --fix zmin --moment zmax 0,0,100000N*mm", u)


def test_a_load_spread_along_a_cantilever_is_a_pressure_not_a_tip_load():
    t = ("A mild steel shelf bar, 300 mm long, 30 mm wide and 10 mm thick (lying flat), is fixed to a wall at one "
         "end. 600 N of books are spread evenly along its top. How far does the free end drop?")
    f = form_from_words(t)
    assert f["action"] == "raw" and "--pressure zmax 0.0666667" in f["request"]
    assert "--force" not in f["request"] and "cantilever_udl w=2 L=300" in f["request"]


def test_a_hex_part_is_not_the_round_standoff_template():
    assert form_from_words("Make a printable M3 hex standoff, 5.5 mm across flats and 20 mm long") is None


def test_tube_cantilevers_are_hollow_beams():
    sq = form_from_words("Aluminium 6061 square tube, 40 x 40 mm with a 3 mm wall, 600 mm long, clamped at one end. "
                         "A 500 N load hangs from the free end. Tip deflection?")
    assert "section=rect_tube width=40 height=40 wall=3" in sq["request"] and "b=40 h=40 t=3" in sq["request"]
    rd = form_from_words("Steel round tube 30 mm outside diameter with a 2 mm wall, 500 mm long, clamped at one "
                         "end, 200 N down at the free end. How much does it bend?")
    assert "section=tube width=30" in rd["request"] and "D=30 t=2" in rd["request"]
    assert form_from_words("print a tube 20 mm diameter 30 mm long")["template"] == "standoff"   # CAD: unchanged


def test_pinned_columns_are_held_at_points_not_faces():
    """A face hold clamps a solid end: the old rule modelled fixed-pinned (FEA 2x Euler) under a pinned check."""
    sq = form_from_words("A steel column 1000 mm long with a 20 x 20 mm square section is pinned at both ends and "
                         "carries 5 kN. What is its buckling safety factor?")["request"]
    assert "--pin point:0,0,0 --slide point:1000,0,0 y --slide point:1000,0,0 z" in sq and "--pin xmin" not in sq
    rod = form_from_words("An aluminium 6061 rod, 10 mm diameter and 400 mm long, is pinned at both ends and carries "
                          "1 kN of axial compression. What is its buckling safety factor?")["request"]
    assert "section=round width=10" in rod and "D=10 ends=pinned_pinned" in rod


def test_frequency_questions_are_answered_by_rules():
    c = form_from_words("An aluminium 6061 cantilever 300 x 20 x 5 mm is clamped at one end. What is its first natural "
                        "frequency?")["request"]
    assert "-a modal" in c and "--fix xmin" in c and "support=cantilever" in c
    ss = form_from_words("A steel bar 500 mm long, 20 mm wide and 10 mm thick rests on simple supports at both ends. "
                         "What is its first natural frequency?")["request"]
    assert "length=250" in ss and "--slide xmax x" in ss and "support=simply_supported" in ss
    assert "--pin point" not in ss                    # no point holds in the bending direction (false modes)
    ff = form_from_words("A steel bar 400 mm long, 30 mm wide and 6 mm thick is welded solid at both ends. "
                         "What is its first natural frequency?")["request"]
    assert "--fix xmin --slide xmax x" in ff and "support=fixed_fixed" in ff


def test_l_bracket_sizes_come_from_the_words():
    f = form_from_words("3D print an L-bracket: two legs 40 mm long, 20 mm wide and 4 mm thick at a right angle, with a "
                        "5 mm hole in the middle of each leg.")
    assert f["params"] == {"width": 20.0, "thickness": 4.0, "leg_x": 40.0, "leg_z": 40.0, "hole_diameter": 5.0,
                           "holes_per_leg": 1}


def test_round_plates_under_pressure_are_roark_cases():
    c = form_from_words("A steel disc 200 mm in diameter and 5 mm thick is clamped all the way round its edge. 1 bar "
                        "of pressure acts on one face. How much does the centre deflect?")["request"]
    assert "Cylinder(100, 5" in c and "--fix cyl:100 --pressure zmax 0.1" in c and "edges=clamped" in c
    s = form_from_words("An aluminium 6061 round cover 150 mm diameter and 4 mm thick rests on a ledge (simply "
                        "supported) round its edge, with 50 kPa on top. How much does it deflect?")["request"]
    assert "--slide cyl:75 z" in s and "edges=simply_supported -> deflection@max_displacement" in s and "q=0.05" in s


def test_a_wall_with_one_face_held_and_air_on_the_other():
    f = form_from_words("A 3D-printed PETG enclosure wall is 5 mm thick. The inside face is at 60 C and the outside face "
                        "is cooled by still air at 20 C with h = 10 W/m2K. What temperature is the outside surface?")
    assert "--temp zmin 60 --convect zmax 10 20" in f["request"] and "k=0.21 L=5 h=10" in f["request"]


def test_a_spread_load_deflection_check_compares_the_peak():
    from engagent.quick import link_check
    job = {"loads": [{"on": "zmax", "type": "pressure"}], "constraints": [], "analysis": "static", "probes": {}}
    hc = link_check("beam.cantilever_udl w=2 L=300 E=210000 nu=0.3 b=30 h=10", job, None)
    assert hc["metric"] == "max_displacement"         # not the average over the loaded top face


def test_the_local_model_form_has_torque_round_sections_and_side_faces():
    from engagent import structured
    f = {"action": "analyze", "template": "beam", "section": "round", "params": {"length": 200, "diameter": 20},
         "material_words": "steel", "fixed_faces": ["xmin"],
         "loads": [{"face": "xmax", "kind": "torque", "direction": "+x", "magnitude": 100, "unit": "N*m"}]}
    req, q = structured.build_request(f, "Steel shaft 20 mm diameter 200 mm long, clamped, 100 N m of torque")
    assert q is None and "section=round" in req and "--moment xmax 100,0,0" in req
    g = {"action": "analyze", "analysis": "thermal", "template": "standoff",
         "params": {"outer_diameter": 5, "hole": 5, "height": 50}, "material_words": "aluminium 6061",
         "temperatures": [{"face": "zmin", "value": 80, "unit": "C"}],
         "convection": [{"face": "sides", "h": 50, "ambient": 20, "unit": "C"}]}
    req, q = structured.build_request(g, "aluminium 6061 pin 5 mm diameter, wall at 80 C, air at 20 C, h = 50")
    assert "hole=0" in req and "--convect cyl:2.5 50 20" in req


def test_the_form_ignores_a_numeric_section_and_double_booked_faces():
    from engagent import structured
    f = {"action": "analyze", "template": "beam", "params": {"length": 200, "width": 10, "height": 20, "section": 1},
         "material_words": "mild steel", "fixed_faces": ["xmin"],
         "loads": [{"face": "xmax", "kind": "force", "direction": "-z", "magnitude": 50, "unit": "kg"}]}
    req, _ = structured.build_request(f, "Mild steel bar 200 x 10 x 20 mm bolted at one end, 50 kg at the free end")
    assert "section" not in req
    g = {"action": "analyze", "analysis": "thermal", "template": "beam", "params": {"length": 100},
         "material_words": "steel", "temperatures": [{"face": "xmin", "value": 100, "unit": "C"},
                                                     {"face": "xmax", "value": 20, "unit": "C"}],
         "convection": [{"face": "xmax", "h": 25, "ambient": 20, "unit": "C"}]}
    req, _ = structured.build_request(g, "Steel bar 100 mm, one end at 100 C, other end cooled by air at 20 C, h = 25")
    assert "--temp xmax" not in req and "--temp xmin 100" in req and "--convect xmax 25 20" in req


def test_the_air_temperature_is_not_a_held_face():
    from engagent import structured
    g = {"action": "analyze", "analysis": "thermal", "template": "beam", "section": "round",
         "params": {"length": 50, "diameter": 5}, "material_words": "aluminium 6061",
         "temperatures": [{"face": "xmin", "value": 80, "unit": "C"}, {"face": "xmax", "value": 20, "unit": "C"}],
         "convection": [{"face": "sides", "h": 50, "ambient": 20, "unit": "C"}]}
    req, _ = structured.build_request(g, "Aluminium 6061 pin, 5 mm diameter and 50 mm long, sticking out of a wall at "
                                         "80 C. The air is at 20 C with h = 50 W/m2K. Tip temperature?")
    assert "--temp xmax" not in req and "--temp xmin 80" in req


def test_plate_hole_pin_fin_and_free_expansion_rules():
    p = form_from_words("Steel plate 200 x 50 x 5 mm with a 10 mm hole drilled through its centre. It is pulled "
                        "lengthwise with 10 kN. What is the peak stress at the hole?")["request"]
    assert "center_hole=10" in p and "--force xmax 10000,0,0" in p and "kt.plate_hole_tension" in p
    f = form_from_words("Aluminium 6061 pin, 5 mm diameter and 50 mm long, sticking out of a wall that is held at 80 C. "
                        "The surrounding air is at 20 C with h = 50 W/m2K. What temperature is the tip of the pin?")["request"]
    assert "--temp xmin 80 --convect cyl:2.5+xmax 50 20" in f and "thermal.fin_straight" in f
    e = form_from_words("Steel bar 500 x 20 x 20 mm, one end resting against a wall, free to grow otherwise. It is "
                        "heated evenly from 20 C to 100 C. How much does the free end move?")["request"]
    assert "--t0 20 --dT 100" in e and "free_expansion L=500 cte=12 dT=80" in e
