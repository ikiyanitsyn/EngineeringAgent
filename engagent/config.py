"""Project configuration: active unit system, drawing standard, solver location.

Settings live in ``engagent.config.json`` at the repository root (committed, so a
toggle follows the repo to every machine).  Environment variables override it:
``ENGAGENT_UNITS``, ``ENGAGENT_STANDARD``, ``ENGAGENT_CCX``, ``ENGAGENT_THREADS``.
"""
from __future__ import annotations

import json
import os
import shutil
from pathlib import Path

CONFIG_NAME = "engagent.config.json"
DEFAULTS = {"units": "metric", "standard": "auto", "ccx": "", "threads": 4}
_STANDARDS = ("auto", "iso", "asme")


def root() -> Path:
    """Repository root: nearest parent of the cwd holding the config, else the package parent."""
    env = os.environ.get("ENGAGENT_ROOT")
    if env:
        return Path(env)
    here = Path.cwd().resolve()
    for p in (here, *here.parents):
        if (p / CONFIG_NAME).exists():
            return p
    return Path(__file__).resolve().parent.parent


def config_path() -> Path:
    return root() / CONFIG_NAME


def load() -> dict:
    cfg = dict(DEFAULTS)
    p = config_path()
    if p.exists():
        try:
            cfg.update(json.loads(p.read_text(encoding="utf-8")))
        except (OSError, ValueError):
            pass
    return cfg


def save(cfg: dict) -> Path:
    p = config_path()
    p.write_text(json.dumps({k: cfg.get(k, v) for k, v in DEFAULTS.items()}, indent=2) + "\n",
                 encoding="utf-8")
    return p


def get_units() -> str:
    from .units import ALIASES
    val = os.environ.get("ENGAGENT_UNITS") or load()["units"]
    return ALIASES.get(str(val).lower(), "metric")


def set_units(system: str) -> str:
    from .units import normalize_system
    system = normalize_system(system)
    cfg = load()
    cfg["units"] = system
    save(cfg)
    return system


def get_standard(system: str | None = None) -> str:
    """``'iso'`` or ``'asme'``.  ``auto`` follows the unit system (metric->ISO, imperial->ASME)."""
    val = str(os.environ.get("ENGAGENT_STANDARD") or load()["standard"]).lower()
    if val not in _STANDARDS:
        val = "auto"
    if val == "auto":
        from .units import normalize_system
        return "iso" if normalize_system(system) == "metric" else "asme"
    return val


def set_standard(standard: str) -> str:
    standard = str(standard).lower()
    if standard not in _STANDARDS:
        raise ValueError("standard must be 'auto', 'iso' or 'asme'")
    cfg = load()
    cfg["standard"] = standard
    save(cfg)
    return standard


def threads() -> int:
    try:
        return max(1, int(os.environ.get("ENGAGENT_THREADS") or load()["threads"]))
    except (TypeError, ValueError):
        return 4


def find_ccx() -> str | None:
    """Locate the CalculiX solver executable, or return ``None``."""
    candidates = [os.environ.get("ENGAGENT_CCX"), load().get("ccx")]
    for name in ("ccx", "ccx_static", "ccx_dynamic", "ccx_2.23", "ccx_2.22", "ccx_2.21",
                 "ccx_MT", "ccx.exe", "ccx_static.exe"):
        candidates.append(shutil.which(name))
    home = Path.home()
    for d in (Path("C:/calculix"), home / "calculix", root() / "tools" / "calculix",
              Path("C:/Program Files/CalculiX"), Path("/usr/local/bin"), Path("/opt/homebrew/bin")):
        for name in ("ccx_static.exe", "ccx.exe", "ccx_dynamic.exe", "ccx"):
            candidates.append(str(d / name))
    for c in candidates:
        if c and Path(c).is_file():
            return str(c)
    return None
