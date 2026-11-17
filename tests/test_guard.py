"""Analysis must never run on a material or load the user did not give."""
from engagent.guard import check_request

COPIED = ('ea make beam length=200 width=10 height=20 --name cantilever\n'
          'ea analyze last -m steel_s355 --fix xmin --force xmax 0,0,-500 '
          '--check "beam.cantilever_end_load P=500 L=200 E=210GPa b=10 h=20 nu=0.3"')
USER = ("I have a rectangular bar 200 mm long, 10 mm wide and 20 mm tall, bolted to a wall at one "
        "end so it sticks out. How much does the free end bend?")


def test_invented_material_and_load_are_caught():
    missing = check_request(COPIED, USER)
    assert any("material" in m for m in missing) and any("force" in m for m in missing)


def test_values_the_user_gave_pass_including_conversions():
    user = USER + " It is mild steel and a 50 kg weight hangs from the free end."
    assert check_request(COPIED.replace("-500", "-490.3"), user) == []
    assert check_request("ea analyze plate -m al_6061_t6 --fix xmin --pressure zmax 0.6895",
                         "aluminium plate, 100 psi") == []
    assert check_request("ea analyze beam -m al_6061_t6 --fix xmin --force xmax 0,-222.4,0",
                         "aluminum beam, 50 lbf sideways") == []
    assert check_request("ea analyze beam -m steel_generic --temp xmin 100 --convect xmax 25 20",
                         "steel bar, one end at 212 F, air h = 25 at 68 F") == []


def test_cad_defaults_are_not_questioned():
    assert check_request("ea make wall_hook arm_length=50 --print petg", "a wall hook") == []


def test_json_jobs_are_checked_too():
    job = '```json\n{"analysis": "static", "material": "pla", "loads": [{"type": "force", "on": "a", "value": [0, 0, -75]}]}\n```'
    assert len(check_request(job, "a bracket that holds a shelf")) == 2


def test_autocorrect_uses_the_users_material_and_load():
    from engagent.guard import autocorrect
    user = "Bar 200 x 10 x 20 mm bolted to a wall at one end. Mild steel, a 50 kg weight hangs from the free end."
    fixed, notes = autocorrect("ea analyze beam -m steel_s355 --fix xmin --force xmax 0,0,-500", user)
    assert "-m steel_generic" in fixed and "0,0,-490.3" in fixed and len(notes) == 2
    assert check_request(fixed, user) == []
    same, none = autocorrect("ea analyze beam -m steel_s355 --fix xmin --force xmax 0,0,-490.3", "S355 bar, 50 kg")
    assert none == [] and "steel_s355" in same
    untouched, n2 = autocorrect("ea analyze beam -m steel_s355 --fix xmin --force xmax 0,0,-500", "a bar on a wall")
    assert n2 == [] and check_request(untouched, "a bar on a wall")      # nothing to map: still rejected


def test_beam_end_load_is_put_on_the_end_face():
    from engagent import structured
    u = "Mild steel bar 200 x 10 x 20 mm bolted to a wall at one end; a 50 kg weight hangs from the free end."
    form = {"action": "analyze", "template": "beam", "params": {"length": 200}, "material_words": "mild steel",
            "fixed_faces": ["xmin"], "loads": [{"face": "zmax", "kind": "force", "direction": "-z", "magnitude": 50, "unit": "kg"}]}
    req, q = structured.build_request(form, u)
    assert q is None and "--force xmax 0,0,-490.332" in req and form["_notes"]


def test_auto_beam_check_only_for_the_textbook_layout():
    from engagent.quick import build_analysis_job
    j = build_analysis_job("beam", material="steel_generic", fix=["xmin"], forces=[["zmax", "0,0,-100"]], system="metric")
    assert "hand_calcs" not in j
    j = build_analysis_job("beam", material="steel_generic", fix=["xmin"], forces=[["xmax", "0,0,-100"]], system="metric")
    assert j["hand_calcs"][0]["metric"] == "probe.xmax.displacement"
