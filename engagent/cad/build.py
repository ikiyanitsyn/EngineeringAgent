"""Run parametric build123d scripts and save their output."""
from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path
from types import SimpleNamespace
from typing import Any

from .. import units as U


def params(**defaults: Any) -> SimpleNamespace:
    """Named parameters for a geometry script, in mm (angles in degrees, counts as given).

    Defaults are plain numbers in mm.  Overrides arrive through the
    ``ENGAGENT_PARAMS`` environment variable (set by ``engagent cad build -p``
    or a job's geometry ``params``) and may be numbers in the active unit
    system or strings with a unit ("0.25 in").  Convention: write lengths as
    floats (``length=100.0``); integers, booleans, strings and names ending in
    ``_deg``, ``_angle``, ``_count``, ``_n`` or ``_ratio`` are passed through unconverted.
    """
    over = json.loads(os.environ.get("ENGAGENT_PARAMS") or "{}")
    system = os.environ.get("ENGAGENT_PARAM_UNITS") or None
    unknown = [k for k in over if k not in defaults]
    if unknown:
        raise KeyError(f"unknown parameter(s) {', '.join(unknown)}; "
                       f"this script accepts: {', '.join(defaults)}")
    out = dict(defaults)
    raw_suffix = ("_deg", "_count", "_n", "_ratio", "_angle")
    for k, v in over.items():
        d = defaults[k]
        if isinstance(d, bool):
            out[k] = bool(v)
        elif isinstance(d, int) or k.endswith(raw_suffix):
            out[k] = type(d)(v) if isinstance(d, (int, float)) else v
        elif isinstance(d, float) and isinstance(v, (int, float, str)):
            out[k] = U.to_internal(v, "length", system)       # lengths: floats, converted to mm
        else:
            out[k] = v
    return SimpleNamespace(**out)


def save(part, name: str | None = None, *, stl: bool = False, threemf: bool = False,
         folder: str | Path | None = None, quiet: bool = False) -> dict:
    """Validate a build123d shape and export it.  Returns the inspection summary.

    Writes ``<name>.step`` (always), optional ``.stl`` / ``.3mf``, and
    ``<name>.cad.json`` with volume, bounding box, mass properties and face list.
    When run through ``engagent cad build`` or a job, the output path is taken
    from the ``ENGAGENT_OUT`` environment variable.
    """
    from .export import export
    from .inspect import inspect_shape
    out_env = os.environ.get("ENGAGENT_OUT")
    if out_env:
        step = Path(out_env)
    else:
        main = sys.modules.get("__main__")
        base = Path(folder) if folder else (Path(getattr(main, "__file__", ".")).resolve().parent
                                            if getattr(main, "__file__", None) else Path.cwd())
        step = base / f"{name or 'part'}.step"
    info = inspect_shape(part)
    if not info["valid"]:
        raise ValueError("the shape is not a valid solid (is_valid is False); fix the geometry "
                         "before exporting")
    if info["solids"] == 0:
        raise ValueError("the shape contains no solid body")
    files = export(part, step, stl=stl or os.environ.get("ENGAGENT_STL") == "1",
                   threemf=threemf or os.environ.get("ENGAGENT_3MF") == "1")
    info["files"] = [str(f) for f in files]
    step.with_suffix(".cad.json").write_text(json.dumps(info, indent=1), encoding="utf-8")
    if not quiet:
        s = os.environ.get("ENGAGENT_PARAM_UNITS") or None
        print(f"CAD OK: {step.name}  solids={info['solids']}  "
              f"volume={U.fmt(info['volume'], 'volume', s)}  "
              f"bbox={U.fmt_vec(info['bbox_size'], 'length', s)}")
    return info


def run_script(script: str | Path, step_out: str | Path | None = None,
               params: dict | None = None, stl: bool = False, threemf: bool = False,
               system: str | None = None, timeout: float = 600.0) -> dict:
    """Execute a geometry script in a subprocess and return its CAD summary."""
    script = Path(script).resolve()
    if not script.exists():
        raise FileNotFoundError(f"geometry script not found: {script}")
    step = Path(step_out).resolve() if step_out else script.with_name("part.step")
    env = dict(os.environ)
    env["ENGAGENT_OUT"] = str(step)
    env["ENGAGENT_PARAMS"] = json.dumps(params or {})
    env["ENGAGENT_PARAM_UNITS"] = U.normalize_system(system)
    env["ENGAGENT_STL"] = "1" if stl else "0"
    env["ENGAGENT_3MF"] = "1" if threemf else "0"
    timeout = float(os.environ.get("ENGAGENT_SCRIPT_TIMEOUT", timeout))   # the issue bot uses a short limit
    try:
        proc = subprocess.run([sys.executable, str(script)], cwd=script.parent, env=env,
                              capture_output=True, text=True, timeout=timeout)
    except subprocess.TimeoutExpired:
        raise RuntimeError(f"geometry script {script.name} took longer than {timeout:g} s (too complex a "
                           f"shape, or a fillet/boolean that does not resolve) - simplify it") from None
    if proc.returncode != 0:
        raise RuntimeError(f"geometry script {script.name} failed:\n{proc.stderr.strip()[-2000:]}")
    meta = step.with_suffix(".cad.json")
    if not step.exists() or not meta.exists():
        raise RuntimeError(f"{script.name} ran but did not call engagent.cad.save(part); "
                           f"end the script with `save(part)`")
    info = json.loads(meta.read_text(encoding="utf-8"))
    info["stdout"] = proc.stdout.strip()[-1000:]
    return info
