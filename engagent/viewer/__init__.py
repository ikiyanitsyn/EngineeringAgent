"""Interactive result viewer: one self-contained HTML file (WebGL 2, no internet needed)."""
from __future__ import annotations

import html
import json
import webbrowser
from pathlib import Path

TEMPLATE = Path(__file__).with_name("template.html")


def build_viewer(job_folder: str | Path, out: str | Path | None = None, open_browser: bool = False) -> Path:
    """Write ``viewer.html`` for a solved job folder (needs view.json from ``engagent fea run``)."""
    folder = Path(job_folder)
    view = folder / "view.json"
    if not view.exists():
        raise FileNotFoundError(f"{view} not found; run the analysis first (engagent fea run {folder})")
    data = json.loads(view.read_text(encoding="utf-8"))
    page = TEMPLATE.read_text(encoding="utf-8")
    payload = json.dumps(data, separators=(",", ":")).replace("</", "<\\/")
    page = page.replace("/*__DATA__*/null", payload, 1)
    page = page.replace("__TITLE__", html.escape(str(data.get("title") or data.get("name") or "FEA")))
    target = Path(out) if out else folder / "viewer.html"
    target.write_text(page, encoding="utf-8")
    if open_browser:
        webbrowser.open(target.resolve().as_uri())
    return target
