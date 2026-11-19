"""The user's own CAD parts in an issue: find them, fetch them safely, list their mounting features.

Parts come in as
* a .zip attachment holding .step/.stp files (GitHub does not accept .step attachments directly), or
* paths of STEP files already in the repository (e.g. uploaded to `inbox/`), written in the message.
Downloaded files are untrusted data: only STEP members are extracted, with size caps and path checks,
and nothing from them is ever executed.
"""
from __future__ import annotations

import json
import re
import shutil
import urllib.request
import zipfile
from pathlib import Path

ATTACH_RX = re.compile(r"https://github\.com/(?:user-attachments/files|[\w.-]+/[\w.-]+/files)/[\w./%-]+", re.I)
STEP_PATH_RX = re.compile(r"(?<![\w/.-])((?:[\w.-]+/)*[\w.-]+\.(?:step|stp))\b", re.I)
MAX_DOWNLOAD = 25 * 1024 * 1024          # GitHub's attachment limit for non-media files
MAX_PART = 60 * 1024 * 1024
MAX_TOTAL = 150 * 1024 * 1024


SHARE_RX = re.compile(r"https://(?:www\.)?(?:dropbox\.com/\S+|drive\.google\.com/\S+|1drv\.ms/\S+|"
                      r"onedrive\.live\.com/\S+|[\w.-]+/\S+?\.(?:step|stp|zip)(?:\?\S*)?)(?=[\s)>\]]|$)", re.I)


def direct_link(url: str) -> str:
    """A cloud share link -> its direct-download form (Dropbox, Google Drive, OneDrive)."""
    if "dropbox.com" in url:
        url = re.sub(r"([?&])dl=0", r"\1dl=1", url)
        return url if "dl=1" in url else url + ("&" if "?" in url else "?") + "dl=1"
    m = re.search(r"drive\.google\.com/(?:file/d/|open\?id=|uc\?id=)([\w-]+)", url)
    if m:
        return f"https://drive.google.com/uc?export=download&id={m.group(1)}"
    if "1drv.ms" in url or "onedrive.live.com" in url:
        return url + ("&" if "?" in url else "?") + "download=1"
    return url


def find_inputs(text: str, root: Path) -> dict:
    """{'urls': [attachment / share links], 'paths': [existing repo STEP paths]} mentioned in the text."""
    urls = list(dict.fromkeys(u.rstrip(").,") for u in ATTACH_RX.findall(text or "")))
    urls += [u.rstrip(").,") for u in SHARE_RX.findall(text or "")
             if "github.com" not in u and u.rstrip(").,") not in urls]
    urls = [u for u in urls if not re.search(r"\.(pdf|png|jpe?g|gif)$", u, re.I)]   # drawings: engagent.drawings
    paths = []
    root = root.resolve()
    for p in STEP_PATH_RX.findall(text or ""):
        q = (root / p).resolve()
        if q.is_file() and root in q.parents and ".git" not in q.parts:
            paths.append(str(q.relative_to(root)))
    return {"urls": urls, "paths": list(dict.fromkeys(paths))}


def _safe_name(name: str) -> str:
    name = Path(name).name                                  # never keep folders from an archive
    name = re.sub(r"\.txt$", "", name, flags=re.I)          # camera.step.txt (GitHub takes .txt) -> camera
    name = re.sub(r"\.(step|stp)$", "", name, flags=re.I)
    stem = re.sub(r"[^A-Za-z0-9_-]+", "_", name).strip("_")[:40] or "part"
    return stem + ".step"


def fetch(url: str, dest: Path, token: str | None = None, alt: dict | None = None) -> list[Path]:
    """Download one attachment into dest; returns the STEP files it holds (zip members extracted safely).
    ``alt``: signed links from the rendered comments, used when a private repository refuses the plain link."""
    from .drawings import get_bytes
    dest.mkdir(parents=True, exist_ok=True)
    tmp = dest / "_download.bin"
    on_github = url.startswith("https://github.com/")
    try:
        data = get_bytes(url if on_github else direct_link(url), token if on_github else None, MAX_DOWNLOAD, alt)
    except ValueError:
        if on_github:
            raise
        raise ValueError("the link gave a web page, not the file - share it as 'anyone with the link can view' "
                         "(Google Drive files over 100 MB need a direct link), or attach the file here") from None
    if len(data) > MAX_DOWNLOAD:
        raise ValueError("the attachment is larger than 25 MB")
    tmp.write_bytes(data)
    try:
        name = url.split("?", 1)[0].rsplit("/", 1)[-1]          # no query string (share links)
        if zipfile.is_zipfile(tmp):
            return _unzip_steps(tmp, dest)
        head = tmp.read_bytes()[:200].lstrip()
        if head.startswith(b"ISO-10303-21"):        # a bare STEP file (if GitHub ever allows it)
            out = dest / _safe_name(name)
            shutil.move(str(tmp), out)
            return [out]
        raise ValueError(f"{name} is neither a .zip nor a STEP file")
    finally:
        tmp.unlink(missing_ok=True)


def _unzip_steps(zpath: Path, dest: Path) -> list[Path]:
    dest.mkdir(parents=True, exist_ok=True)
    out, total = [], 0
    with zipfile.ZipFile(zpath) as z:
        for info in z.infolist():
            n = info.filename
            if info.is_dir() or not re.search(r"\.(step|stp)$", n, re.I) or n.startswith("__MACOSX"):
                continue                               # only STEP files; nothing else is extracted
            if info.file_size > MAX_PART:
                raise ValueError(f"{n} is larger than {MAX_PART >> 20} MB")
            total += info.file_size
            if total > MAX_TOTAL:
                raise ValueError("the zip holds more than 150 MB of STEP files")
            target = dest / _safe_name(n)              # flat, sanitised name: no paths from the archive
            k = 2
            while target.exists():
                target = dest / f"{target.stem}_{k}.step"
                k += 1
            with z.open(info) as src, open(target, "wb") as f:
                written = 0
                while chunk := src.read(1 << 16):      # trust the bytes, not the header (zip bombs)
                    written += len(chunk)
                    if written > MAX_PART:
                        raise ValueError(f"{n} expands beyond {MAX_PART >> 20} MB")
                    f.write(chunk)
            if not target.read_bytes()[:200].lstrip().startswith(b"ISO-10303-21"):
                target.unlink()
                raise ValueError(f"{n} is not a STEP file")
            out.append(target)
    if not out:
        raise ValueError("the zip holds no .step / .stp files")
    return out


def list_parts(parts: list[Path], folder: Path) -> tuple[dict, str]:
    """Measure each part, draw labelled pictures, write features.json; returns (data, markdown)."""
    from .cad.features import describe, mount_features, picture
    data, md = {}, []
    (folder / "plots").mkdir(parents=True, exist_ok=True)
    for p in parts:
        name = p.stem
        feat = mount_features(p)
        picture(p, feat, folder / "plots" / f"faces_{name}.png", name)
        data[name] = feat
        md.append("\n".join(describe(feat, name)))
    (folder / "features.json").write_text(json.dumps(data, indent=1), encoding="utf-8")
    return data, "\n\n".join(md)


PICK_MARK = "Which part(s) should I use?"


def choose_parts(parts: list[Path], text: str, limit: int = 4) -> tuple[list[Path], str | None]:
    """Keep the parts named in the text; with many parts and none named, ask which (listing them)."""
    t = (text or "").lower()
    named = [p for p in parts if p.stem.lower() in t]
    if named:
        return named, None
    if len(parts) <= limit:
        return parts, None
    names = sorted(p.stem for p in parts)
    return [], (f"### 📦 {len(parts)} parts found\n**{PICK_MARK}** Reply with one or two names, e.g. "
                f"*use {names[0]}*, plus what to do with it (or I will list its faces first).\n\n"
                + "\n".join(f"- `{n}`" for n in names[:60]) + ("\n- ..." if len(names) > 60 else ""))


QUESTION = ("**Which faces should the adapter join?** Reply in a comment, for example:\n"
            "> join `{a}` F2 to `{b}` F2, aluminium 6061, machined\n\n"
            "Also say anything that matters: the material or 3D-print filament, a maximum thickness or "
            "offset, and the load (e.g. the camera weighs 0.8 kg and the arm accelerates at 2 g). "
            "If a hole size is ambiguous (e.g. *M5 at nominal size or M6 tapped*), say which screw it is.")


# ---------------------------------------------------------------- plain-English FEA of an uploaded part
FIX_WORDS = r"\b(fix|fixed|hold|held|clamp|clamped|bolt|bolted|support|supported|anchor|anchored|mount|mounted)\b"


def part_fea_request(text: str, folder: Path) -> tuple[str | None, str | None]:
    """'steel, fix F1, 500 N down on F3' about parts measured earlier -> (`ea analyze` request, question).

    Faces are the numbered F-faces of the listing; each is selected by a point ON that face, so the
    selection is exact. Nothing is guessed: a missing material, support, load size or direction is asked.
    """
    from .guard import material_from_words
    from .rules import FORCE_RX, PRESSURE_RX
    from .structured import TO_MPA, TO_N
    feats = json.loads((Path(folder) / "features.json").read_text())
    t = (text or "").lower()
    if not re.search(r"\bf\d+\b", t):
        return None, None
    names = list(feats)
    part = next((n for n in names if n.lower() in t), names[0]) if names else None
    if part is None:
        return None, None
    faces = {f["id"].lower(): f for f in feats[part]["faces"]}

    def sel(ids):
        bad = [i.upper() for i in ids if i not in faces]
        if bad:
            raise ValueError(f"{part} has no face {', '.join(bad)} (faces: {', '.join(f.upper() for f in faces)})")
        return "+".join("near:" + ",".join(f"{v:.4g}" for v in faces[i].get("label_at", faces[i]["centre"]))
                        for i in ids)

    fixed, loads, missing = [], [], []
    for clause in re.split(r"[,;.\n]|\band\b(?=[^,;.]*\b(?:fix|hold|clamp|bolt|support|\d))", t):
        ids = re.findall(r"\bf\d+\b", clause)
        if not ids:
            continue
        f = re.search(FORCE_RX, clause)
        p = re.search(PRESSURE_RX, clause)
        if f or p:
            loads.append((clause, ids, f, p))
        elif re.search(FIX_WORDS, clause):
            fixed += ids
    mat = material_from_words(text)
    if not mat:
        missing.append("the material (e.g. steel, aluminium 6061, PETG)")
    if not fixed:
        missing.append("which face is held (e.g. 'fix F1')")
    if not loads:
        missing.append("the load with its size and unit and the face it acts on (e.g. '500 N down on F3')")
    parts = []
    for clause, ids, f, p in loads:
        if p:
            mag, unit = p.groups()
            parts.append(f"--pressure {sel(ids)} {float(mag) * TO_MPA[{'mpa': 'MPa', 'kpa': 'kPa', 'bar': 'bar', 'psi': 'psi'}[unit]]:g}")
            continue
        mag, unit = f.groups()
        unit = {"n": "N", "newton": "N", "newtons": "N", "kn": "kN", "lbf": "lbf", "lb": "lb", "lbs": "lb",
                "pound": "lb", "pounds": "lb"}.get(unit, "kg")
        P = float(mag) * TO_N[unit]
        d = _direction(clause, faces[ids[0]] if ids[0] in faces else None, unit)
        if d is None:
            missing.append(f"the direction of the {mag} {unit} on {', '.join(i.upper() for i in ids)} "
                           "(e.g. 'down', 'along +X', or 'pushing on' the face)")
            continue
        parts.append(f"--force {sel(ids)} " + ",".join(f"{P * c:.6g}" for c in d))
    if missing:
        return None, ("To run the analysis I still need: " + "; ".join(missing)
                      + ". Reply in a comment, e.g. *steel, fix F1, 500 N down on F3*.")
    step = Path(folder) / f"{part}.step"
    req = (f'ea analyze {step} -m {mat} --fix {sel(list(dict.fromkeys(fixed)))} ' + " ".join(parts)
           + f' --name "{part} check"')
    return req, None


def _direction(clause: str, face: dict | None, unit: str):
    """Unit vector for a load: 'down'/'up', 'along +X' etc., or 'pushing/pulling' the face (its normal)."""
    if re.search(r"\b(down|downward|downwards|hanging|weight)\b", clause) or (unit in ("kg", "lb") and
                                                                              not re.search(r"\bup\b", clause)):
        return (0.0, 0.0, -1.0)
    if re.search(r"\b(up|upward|upwards)\b", clause):
        return (0.0, 0.0, 1.0)
    m = re.search(r"\b(?:along|in|towards?|to)\s*(?:the\s*)?([+-])?\s*([xyz])\b", clause)
    if m:
        v = [0.0, 0.0, 0.0]
        v["xyz".index(m.group(2))] = -1.0 if m.group(1) == "-" else 1.0
        return tuple(v)
    if face is not None and re.search(r"\b(push|pushing|pushes|press|pressing|presses)\b", clause):
        return tuple(-c for c in face["normal"])        # into the face
    if face is not None and re.search(r"\b(pull|pulling|pulls)\b", clause):
        return tuple(face["normal"])                     # out of the face
    return None


QUESTION_ONE = ("**What should I do with it?** Reply in a comment, for example:\n"
                "> steel, fix F1, 500 N down on F2\n\n"
                "to check its strength (say the material, the face(s) held, and each load with its size, unit, "
                "direction and face - 'down', 'along +X', or 'pushing on F3'). To design an adapter to another "
                "part, add that part too and say e.g. *join `{a}` F2 to `other` F1, M6*.")
