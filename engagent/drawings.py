"""Engineering drawings (PDF or picture) in a request: fetch them safely, turn them into page images
for a model that can see (e.g. Gemini), so 'make this part from my drawing' needs no typing of dimensions.

Drawings come in as
* a GitHub attachment (a .pdf under user-attachments/files, or a pasted picture under user-attachments/assets)
* a path in the repository, e.g. `inbox/bracket.pdf` (works for private repositories where the bot may
  not be allowed to download attachments).
Downloaded bytes are untrusted: only PDF / PNG / JPEG content is accepted (checked by its first bytes),
sizes are capped, and nothing is executed. PDFs are rendered with poppler's `pdftoppm`.
"""
from __future__ import annotations

import base64
import os
import re
import shutil
import subprocess
import tempfile
import urllib.error
import urllib.request
from pathlib import Path

URL_RX = re.compile(r"https://github\.com/(?:user-attachments/files/[\w./%-]+?\.(?:pdf|png|jpe?g)"
                    r"|user-attachments/assets/[0-9a-f-]{36})\b", re.I)
PATH_RX = re.compile(r"(?<![\w/.-])((?:[\w.-]+/)*[\w.-]+\.(?:pdf|png|jpe?g))\b", re.I)
MAX_BYTES = 25 * 1024 * 1024
MAX_PAGES = 2
DPI = 150                      # an A3 sheet -> about 2480 x 1750 px: title block and dimensions stay legible

NOT_ALLOWED = ("GitHub did not let the bot download the drawing (attachments of a private repository need a "
               "browser login). Upload it to the repository instead - on GitHub: **Add file > Upload files**, "
               "into an `inbox/` folder - and write its path in a comment, e.g. `inbox/bracket.pdf`.")


def find(text: str, root: Path) -> dict:
    """{'urls': [...], 'paths': [...]} of drawings mentioned in the text."""
    urls = list(dict.fromkeys(URL_RX.findall(text or "")))
    root = Path(root).resolve()
    paths = []
    for p in PATH_RX.findall(text or ""):
        q = (root / p).resolve()
        if q.is_file() and root in q.parents and ".git" not in q.parts:
            paths.append(q)
    return {"urls": urls, "paths": list(dict.fromkeys(paths))}


def kind(data: bytes) -> str | None:
    if data[:5] == b"%PDF-":
        return "pdf"
    if data[:8] == b"\x89PNG\r\n\x1a\n":
        return "png"
    if data[:3] == b"\xff\xd8\xff":
        return "jpeg"
    return None


def download(url: str, token: str | None = None) -> bytes:
    req = urllib.request.Request(url, headers={"User-Agent": "engagent-bot", "Accept": "*/*",
                                               **({"Authorization": f"Bearer {token}"} if token else {})})
    try:
        with urllib.request.urlopen(req, timeout=120) as r:
            data = r.read(MAX_BYTES + 1)
    except urllib.error.HTTPError as e:
        if e.code in (401, 403, 404):
            raise ValueError(NOT_ALLOWED) from None
        raise
    if len(data) > MAX_BYTES:
        raise ValueError("the drawing is larger than 25 MB")
    if kind(data) is None:              # a login page instead of the file
        raise ValueError(NOT_ALLOWED)
    return data


def _pdftoppm() -> str | None:
    exe = shutil.which("pdftoppm")
    if exe or not os.environ.get("GITHUB_ACTIONS"):
        return exe
    inst = ["sudo", "timeout", "180", "apt-get", "install", "-y", "-qq", "poppler-utils"]
    subprocess.run(inst, capture_output=True)      # on the runner, only when a PDF actually arrives
    if not shutil.which("pdftoppm"):               # stale package lists: refresh once
        subprocess.run(["sudo", "timeout", "240", "apt-get", "update", "-qq"], capture_output=True)
        subprocess.run(inst, capture_output=True)
    return shutil.which("pdftoppm")


def pages(data: bytes) -> list[bytes]:
    """PNG/JPEG bytes of each page (PDF: the first MAX_PAGES pages rendered)."""
    k = kind(data)
    if k in ("png", "jpeg"):
        return [data]
    if k != "pdf":
        raise ValueError("a drawing must be a PDF, PNG or JPEG")
    exe = _pdftoppm()
    if not exe:
        raise ValueError("cannot render PDF drawings here (poppler's pdftoppm is not installed)")
    with tempfile.TemporaryDirectory(prefix="drawing-") as tmp:
        src = Path(tmp) / "in.pdf"
        src.write_bytes(data)
        r = subprocess.run([exe, "-png", "-r", str(DPI), "-f", "1", "-l", str(MAX_PAGES), str(src),
                            str(Path(tmp) / "page")], capture_output=True, timeout=120)
        out = [p.read_bytes() for p in sorted(Path(tmp).glob("page*.png"))]
        if not out:
            raise ValueError("the PDF could not be read: " + r.stderr.decode(errors="replace")[:200])
        return out


def collect(texts: list[str], root: Path, token: str | None = None) -> tuple[list[bytes], list[str]]:
    """Page images of every drawing mentioned in the messages, and the problems met."""
    imgs, problems = [], []
    for t in texts:
        f = find(t, root)
        for src in f["urls"] + f["paths"]:
            try:
                data = src.read_bytes()[:MAX_BYTES + 1] if isinstance(src, Path) else download(src, token)
                imgs += pages(data)
            except Exception as e:
                problems.append(f"{str(src).rsplit('/', 1)[-1]}: {e}")
    return imgs[:4], list(dict.fromkeys(problems))


def content_parts(text: str, imgs: list[bytes]) -> list[dict]:
    """An OpenAI-style multimodal user message content (text + images), as Gemini's endpoint takes."""
    parts: list[dict] = [{"type": "text", "text": text}]
    for b in imgs:
        mime = "image/jpeg" if kind(b) == "jpeg" else "image/png"
        parts.append({"type": "image_url",
                      "image_url": {"url": f"data:{mime};base64," + base64.b64encode(b).decode()}})
    return parts


HINT = ("\n\n(An engineering drawing of the part is attached as image(s). Read its views, dimensions, "
        "tolerances, title block and notes. Model the part exactly from the drawn dimensions in a ```python "
        "block (millimetres; convert inch drawings), and list the main dimensions you read in the plan so I can "
        "check them. If a dimension needed for the shape is illegible or missing, ask for it instead of "
        "guessing. If the title block names the material, write one plan line `Drawing material: <name>` and use that material in the request. THRU holes must cut the full thickness.)")
