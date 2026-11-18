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


def find_inputs(text: str, root: Path) -> dict:
    """{'urls': [attachment urls], 'paths': [existing repo STEP paths]} mentioned in the text."""
    urls = list(dict.fromkeys(u.rstrip(").,") for u in ATTACH_RX.findall(text or "")))
    paths = []
    root = root.resolve()
    for p in STEP_PATH_RX.findall(text or ""):
        q = (root / p).resolve()
        if q.is_file() and root in q.parents and ".git" not in q.parts:
            paths.append(str(q.relative_to(root)))
    return {"urls": urls, "paths": list(dict.fromkeys(paths))}


def _safe_name(name: str) -> str:
    stem = re.sub(r"[^A-Za-z0-9_-]+", "_", Path(name).stem).strip("_")[:40] or "part"
    return stem + ".step"


def fetch(url: str, dest: Path, token: str | None = None) -> list[Path]:
    """Download one attachment into dest; returns the STEP files it holds (zip members extracted safely)."""
    dest.mkdir(parents=True, exist_ok=True)
    req = urllib.request.Request(url, headers={"User-Agent": "engagent-bot", "Accept": "application/octet-stream",
                                               **({"Authorization": f"Bearer {token}"} if token else {})})
    tmp = dest / "_download.bin"
    with urllib.request.urlopen(req, timeout=120) as r, open(tmp, "wb") as f:
        total = 0
        while chunk := r.read(1 << 16):
            total += len(chunk)
            if total > MAX_DOWNLOAD:
                raise ValueError("the attachment is larger than 25 MB")
            f.write(chunk)
    try:
        name = url.rsplit("/", 1)[-1]
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


QUESTION = ("**Which faces should the adapter join?** Reply in a comment, for example:\n"
            "> join `{a}` F2 to `{b}` F2, aluminium 6061, machined\n\n"
            "Also say anything that matters: the material or 3D-print filament, a maximum thickness or "
            "offset, and the load (e.g. the camera weighs 0.8 kg and the arm accelerates at 2 g). "
            "If a hole size is ambiguous (e.g. *M5 at nominal size or M6 tapped*), say which screw it is.")
