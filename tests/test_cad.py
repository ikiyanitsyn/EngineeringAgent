import json
import math

import pytest

from engagent import materials
from engagent.cad import inspect_shape, run_script, templates
from engagent.cad.printcheck import print_check
from engagent.fea.job import load_job, read_json


@pytest.mark.parametrize("name", list(templates.TEMPLATES))
def test_templates_build_one_valid_solid(name, tmp_path):
    info = templates.build_to_step(name, {}, tmp_path / "part.step", "metric")
    assert info["valid"] and info["solids"] == 1 and info["volume"] > 0


def test_template_dimensions_and_units(tmp_path):
    m = templates.build_to_step("beam", {"length": 100, "width": 10, "height": 10}, tmp_path / "m.step", "metric")
    assert m["volume"] == pytest.approx(10000.0)
    assert m["bbox_size"] == pytest.approx([100, 10, 10])
    i = templates.build_to_step("beam", {"length": 4, "width": 0.5, "height": "10 mm"}, tmp_path / "i.step", "imperial")
    assert i["bbox_size"] == pytest.approx([101.6, 12.7, 10.0])
    with pytest.raises(KeyError):
        templates.build("beam", {"lenght": 5})


def test_script_with_params_and_mass(tmp_path):
    script = tmp_path / "geometry.py"
    script.write_text(
        "from build123d import *\nfrom engagent.cad import params, save\n"
        "P = params(length=50.0, dia=10.0, hole_count=1)\n"
        "save(Cylinder(P.dia / 2, P.length), stl=True)\n")
    info = run_script(script, tmp_path / "part.step", {"length": "2 in", "dia": 20})
    assert info["volume"] == pytest.approx(math.pi * 100 * 50.8, rel=1e-6)
    assert (tmp_path / "part.stl").exists()
    full = inspect_shape(tmp_path / "part.step", "al_6061_t6")
    assert full["mass"] == pytest.approx(full["volume"] * 2.7e-9)
    with pytest.raises(RuntimeError, match="unknown parameter"):
        run_script(script, tmp_path / "x.step", {"radius": 3})


def test_print_check_findings(tmp_path):
    templates.build_to_step("enclosure", {"wall": 0.5, "floor": 2}, tmp_path / "thin.step", "metric")
    r = print_check(tmp_path / "thin.step", "fdm", "petg")
    wall = next(c for c in r["checks"] if c["name"].startswith("Wall thickness"))
    assert wall["status"] == "FAIL" and r["min_wall"] == pytest.approx(0.5, abs=0.05)
    templates.build_to_step("enclosure", {}, tmp_path / "ok.step", "metric")
    ok = print_check(tmp_path / "ok.step", "fdm", "petg")
    assert ok["status"] == "PASS" and ok["orientation"] == "+Z" and ok["mass"] > 0
    big = print_check(tmp_path / "ok.step", "fdm", build_volume=[50, 50, 50])
    assert big["status"] == "FAIL"


def test_materials():
    m = materials.get("al_6061_t6")
    assert m.get("E") == pytest.approx(68900) and m.get("density") == pytest.approx(2.7e-9)
    c = materials.get({"base": "steel_s355", "yield": "60 ksi"})
    assert c.get("yield") == pytest.approx(413.7, rel=1e-3) and c.get("E") == 210000
    lam = materials.get({"laminate": {"lamina": "cf_peek_ud", "layup": "[0/90]s"}})
    assert lam.orthotropic and lam.get("E1") == pytest.approx(lam.get("E2"), rel=1e-6)
    with pytest.raises(KeyError, match="did you mean"):
        materials.get("al_6061")
    assert len(materials.list_materials()) >= 35


def test_job_file_reading_and_validation(tmp_path):
    p = tmp_path / "job.json"
    p.write_text('{ // comment\n "analysis": "static", "geometry": {"template": "beam"},\n'
                 ' "material": "steel_generic", "sets": {"a": "xmin"},\n'
                 ' "constraints": [{"type": "fixed", "on": "a"}], }')
    assert read_json(p)["analysis"] == "static"
    with pytest.raises(ValueError, match="no loads defined"):
        load_job(p)
    spec = read_json(p)
    spec["loads"] = [{"type": "force", "on": "missing", "value": [0, 0, 1]}]
    with pytest.raises(ValueError, match="not defined in 'sets'"):
        load_job(spec, tmp_path)
    spec["loads"] = [{"type": "force", "on": "a", "value": [0, 0, 1]}]
    spec.pop("material")
    with pytest.raises(ValueError, match="needs a 'material'"):
        load_job(spec, tmp_path)
    spec["material"] = {"E": 1000}
    with pytest.raises(ValueError, match="lacks nu"):
        load_job(spec, tmp_path)
    spec["material"] = "steel_generic"
    spec["analysis"] = "thermal_steady"
    with pytest.raises(ValueError, match="needs a mechanical analysis"):
        load_job(spec, tmp_path)
    json.dumps(spec)
