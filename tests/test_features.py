"""The user's own parts: hole patterns, screw sizes, safe handling of uploaded files."""
import io
import zipfile
from pathlib import Path

import pytest

from engagent import cadinput
from engagent.cad.features import describe, mount_features, screw_for

EX = Path(__file__).resolve().parent.parent / "examples" / "22-camera-adapter"


def test_screw_sizes_are_never_guessed_when_ambiguous():
    assert screw_for(6.6) == "M6 clearance, medium"
    assert "M6 tapped" in screw_for(5.0) and "M5 at nominal size" in screw_for(5.0)
    assert screw_for(31.5) == "bore 31.5 mm"
    assert screw_for(7.7) == "no standard metric screw matches"


def test_robot_flange_and_camera_patterns():
    arm = mount_features(EX / "arm_flange.step")
    top = next(f for f in arm["faces"] if f["normal"][2] > 0.9)
    pat = next(h for h in top["holes"] if h["count"] == 4)
    assert "50 mm bolt circle" in pat["pattern"] and pat["diameter"] == 5.0     # ISO 9409-1-50-4-M6
    cam = mount_features(EX / "camera.step")
    bottom = next(f for f in cam["faces"] if f["normal"][2] < -0.9)
    assert bottom["holes"][0]["pattern"] == "4 holes in a 30 x 40 mm rectangle"
    assert all(f["area"] >= 0.03 * cam["faces"][0]["area"] for f in cam["faces"])  # no hole floors listed
    text = "\n".join(describe(cam, "camera"))
    assert "F2" in text and "rectangle" in text


def test_inputs_found_in_text(tmp_path):
    (tmp_path / "inbox").mkdir()
    (tmp_path / "inbox" / "cam.step").write_text("ISO-10303-21;")
    t = ("parts: inbox/cam.step and inbox/missing.step, zip: "
         "https://github.com/user-attachments/files/123/parts.zip and ../../etc/passwd.step")
    f = cadinput.find_inputs(t, tmp_path)
    assert f["paths"] == ["inbox/cam.step"] and f["urls"] == ["https://github.com/user-attachments/files/123/parts.zip"]


def _zip(members: dict) -> Path:
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as z:
        for n, data in members.items():
            z.writestr(n, data)
    return buf


def test_unzip_keeps_only_step_files_with_safe_names(tmp_path):
    zp = tmp_path / "in.zip"
    zp.write_bytes(_zip({"../../evil.step": "ISO-10303-21;\nDATA;", "notes.txt": "x", "run.py": "import os",
                         "sub/Camera Body.STP": "ISO-10303-21;\n", "__MACOSX/._x.step": "junk"}).getvalue())
    out = cadinput._unzip_steps(zp, tmp_path / "parts")
    names = sorted(p.name for p in out)
    assert names == ["Camera_Body.step", "evil.step"]
    assert all(p.parent == tmp_path / "parts" for p in out)            # nothing escapes the folder
    assert not (tmp_path / "run.py").exists() and not (tmp_path.parent / "evil.step").exists()


def test_unzip_rejects_non_step_content_and_oversize(tmp_path, monkeypatch):
    zp = tmp_path / "bad.zip"
    zp.write_bytes(_zip({"fake.step": "not a step file"}).getvalue())
    with pytest.raises(ValueError, match="not a STEP"):
        cadinput._unzip_steps(zp, tmp_path / "a")
    monkeypatch.setattr(cadinput, "MAX_PART", 100)
    zp.write_bytes(_zip({"big.step": "ISO-10303-21;" + "x" * 500}).getvalue())
    with pytest.raises(ValueError, match="larger than|expands beyond"):
        cadinput._unzip_steps(zp, tmp_path / "b")


def test_adapter_plan_is_assemblable_and_holes_line_up(tmp_path):
    from build123d import import_step
    from engagent.cad import adapter
    p = adapter.plan(EX / "arm_flange.step", "F2", EX / "camera.step", "F2", "M6", "M6")
    # centred, the camera's M6 screws sit on the flange ring and the flange screws under the camera
    assert p["centred"]["a_free"] is False and p["centred"]["b_free"] is False
    assert p["ok"] and p["gap"] >= p["need_gap"]
    b = adapter.build(p, tmp_path, EX / "arm_flange.step", EX / "camera.step")
    a, plate, cam = sorted(import_step(str(tmp_path / "assembly.step")).solids(), key=lambda s: s.bounding_box().min.Z)

    def holes(solid, r):
        return {(round(f.axis_of_rotation.position.X, 2), round(f.axis_of_rotation.position.Y, 2))
                for f in solid.faces() if "CYL" in str(f.geom_type) and f.is_circular_concave and abs(f.radius - r) < 0.01}
    through = holes(plate, 3.3)
    assert holes(a, 2.5) <= through and holes(cam, 2.5) <= through      # every tapped hole meets a plate hole
    assert not (a & plate) or (a & plate).volume < 1e-6
    assert not (plate & cam) or (plate & cam).volume < 1e-6
    # screws stop short of the bottom of the 10 mm deep tapped holes, and say when engagement is short
    grip = b["thickness"] - 6.5
    for s in b["screws"]:
        L = int(s.split(" x ")[2].split(" ")[0])
        assert L - grip <= 10 - 1
    assert "thread engaged" in b["screws"][0]


def test_box_adapter_keeps_parts_on_axis_and_holes_line_up(tmp_path):
    import json
    from build123d import import_step
    from engagent.cad import adapter
    p = adapter.plan(EX / "arm_flange.step", "F2", EX / "camera.step", "F2", "M6", "M6")
    b = adapter.build_box(p, tmp_path, EX / "arm_flange.step", EX / "camera.step")
    a, box, cam = sorted(import_step(str(tmp_path / "assembly.step")).solids(), key=lambda s: s.bounding_box().min.Z)

    def holes(solid, r):
        return {(round(f.axis_of_rotation.position.X, 2), round(f.axis_of_rotation.position.Y, 2))
                for f in solid.faces() if "CYL" in str(f.geom_type) and f.is_circular_concave and abs(f.radius - r) < 0.01}
    assert holes(a, 2.5) <= holes(box, 3.3) and holes(cam, 2.5) <= holes(box, 3.3)
    assert box.is_valid and (not (a & box) or (a & box).volume < 1e-6) and (not (box & cam) or (box & cam).volume < 1e-6)
    import numpy as np
    ha, hc = np.array(sorted(holes(a, 2.5))), np.array(sorted(holes(cam, 2.5)))
    assert np.allclose(ha.mean(axis=0), hc.mean(axis=0), atol=1e-3)   # camera pattern centred on the flange axis
    info = json.loads((tmp_path / "adapter.json").read_text())
    assert info["kind"] == "box" and info["z_b"] > info["z_a"]
    inner = b["thickness"] - 2 * b["plate_t"]
    assert all(inner >= int(s.split(" x ")[2].split(" ")[0]) + 6 for s in b["screws"])   # screw + head stand upright
    req = adapter.fea_request(tmp_path, "al_6061_t6", 0.8, 2)
    assert f",{info['z_b']:.4g} " in req.replace("+", " ") and "order" in req
