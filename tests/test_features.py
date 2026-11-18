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
