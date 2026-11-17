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
