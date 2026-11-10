"""Run CalculiX and parse its .frd / .dat / .sta output."""
from __future__ import annotations

import os
import re
import subprocess
import time
from dataclasses import dataclass, field
from pathlib import Path

import numpy as np

from .. import config


class SolverError(RuntimeError):
    pass


@dataclass
class RunLog:
    ok: bool
    seconds: float
    errors: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    version: str = ""
    command: str = ""
    tail: str = ""


def run_ccx(inp: Path, timeout: float = 3600.0, serial_solver: bool = False) -> RunLog:
    """Run ``ccx <jobname>`` in the deck's folder; never raises on solver errors."""
    exe = config.find_ccx()
    if not exe:
        raise SolverError(
            "CalculiX (ccx) was not found. Install it with scripts/setup.ps1 (Windows) or "
            "scripts/setup.sh (Linux/macOS), or set ENGAGENT_CCX to the executable path.")
    inp = Path(inp)
    env = dict(os.environ)
    env["OMP_NUM_THREADS"] = str(config.threads())
    # CalculiX 2.21 + multithreaded SPOOLES returns wrong, run-to-run varying eigenvalues in
    # *BUCKLE / *FREQUENCY steps, so eigenvalue jobs always use the serial equation solver.
    env["CCX_NPROC_EQUATION_SOLVER"] = "1" if serial_solver else str(config.threads())
    for ext in (".frd", ".dat", ".sta", ".cvg", ".12d"):
        p = inp.with_suffix(ext)
        if p.exists():
            p.unlink()
    t0 = time.time()
    try:
        proc = subprocess.run([exe, "-i", inp.stem], cwd=inp.parent, env=env, timeout=timeout,
                              capture_output=True, text=True, errors="replace")
        out = (proc.stdout or "") + "\n" + (proc.stderr or "")
        rc = proc.returncode
    except subprocess.TimeoutExpired as e:
        out = (e.stdout or "") if isinstance(e.stdout, str) else ""
        out += f"\n*ERROR: solver timed out after {timeout:.0f} s"
        rc = -1
    (inp.parent / (inp.stem + ".log")).write_text(out, encoding="utf-8")
    errors = _collect(out, "*ERROR")
    warnings = [w for w in _collect(out, "*WARNING")
                if "a nonlinear geometric analysis is requested but no time increment" not in w]
    frd = inp.with_suffix(".frd")
    if rc != 0 and not errors:
        errors.append(f"solver exited with code {rc}")
    if not frd.exists() or frd.stat().st_size < 200:
        errors.append("no result file (.frd) was written")
    if "best solution and residuals are in the frd file" in out or "too many attempts" in out:
        errors.append("nonlinear solution did not converge")
    m = re.search(r"Version\s+([\d.]+)", out)
    return RunLog(ok=not errors, seconds=time.time() - t0, errors=errors, warnings=warnings,
                  version=m.group(1) if m else "", command=f"{Path(exe).name} -i {inp.stem}",
                  tail="\n".join(out.strip().splitlines()[-25:]))


def _collect(out: str, key: str) -> list[str]:
    msgs, lines = [], out.splitlines()
    for i, line in enumerate(lines):
        if key in line:
            msg = " ".join(s.strip() for s in lines[i:i + 3] if s.strip())
            msg = re.sub(r"\s+", " ", msg)[:300]
            if msg not in msgs:
                msgs.append(msg)
    return msgs[:40]


# --------------------------------------------------------------------------- .frd
@dataclass
class Frame:
    step: int
    value: float                      # time, frequency or buckling factor
    fields: dict[str, np.ndarray]     # name -> (N, ncomp)


FIELD_NAMES = {"DISP": "U", "STRESS": "S", "NDTEMP": "T", "FORC": "RF", "FLUX": "HFL",
               "PE": "PEEQ", "TOSTRAIN": "E", "RFL": "RFL", "MESTRAIN": "ME"}


def read_frd(path: Path, n_nodes: int) -> list[Frame]:
    """Parse an ASCII .frd file into frames of nodal fields (rows = node id - 1)."""
    frames: list[Frame] = []
    cur: Frame | None = None
    with open(path, "r", errors="replace") as fh:
        lines = fh.readlines()
    i, n = 0, len(lines)
    pending_value, pending_step = 0.0, 0
    last_key = None
    while i < n:
        line = lines[i]
        if line.startswith("  100C"):
            try:
                pending_value = float(line[12:24])
            except ValueError:
                pending_value = 0.0
            try:
                pending_step = int(line[58:63])
            except ValueError:
                pending_step += 1
            i += 1
            continue
        if line.startswith(" -4"):
            name = line[5:13].strip()
            ncomp = int(line[13:18])
            i += 1
            comps = 0
            while i < n and lines[i].startswith(" -5"):
                if "ALL" not in lines[i][5:13]:
                    comps += 1
                i += 1
            start = i
            while i < n and not lines[i].startswith(" -3"):
                i += 1
            block = lines[start:i]
            arr = np.zeros((n_nodes, comps))
            for b in block:
                if not b.startswith(" -1"):
                    continue
                nid = int(b[3:13])
                if nid > n_nodes:
                    continue
                body = b[13:].rstrip("\n")
                for c in range(comps):
                    s = body[12 * c:12 * c + 12]
                    try:
                        arr[nid - 1, c] = float(s)
                    except ValueError:
                        arr[nid - 1, c] = _fix_exp(s)
            key = (pending_step, pending_value)
            if cur is None or key != last_key:
                cur = Frame(step=pending_step, value=pending_value, fields={})
                frames.append(cur)
                last_key = key
            cur.fields[FIELD_NAMES.get(name, name)] = arr
            continue
        i += 1
    return frames


def _fix_exp(s: str) -> float:
    """Fortran may drop the 'E' in three-digit exponents: 1.234-101."""
    m = re.match(r"\s*([-+]?\d*\.\d+)([-+]\d+)\s*$", s)
    if m:
        return float(f"{m.group(1)}E{m.group(2)}")
    return 0.0


# --------------------------------------------------------------------------- .dat
def read_dat(path: Path) -> dict:
    """Totals of reaction force / heat flow per set, eigenfrequencies, buckling factors."""
    out: dict = {"rf": {}, "rfl": {}, "frequencies": [], "buckling": []}
    if not Path(path).exists():
        return out
    lines = Path(path).read_text(errors="replace").splitlines()
    i = 0
    while i < len(lines):
        low = lines[i].lower()
        m = re.search(r"total (force|heat generation|flux).*for set\s+(\S+)\s+and time\s+(\S+)", low)
        if m:
            vals: list[float] = []
            j = i + 1
            while j < len(lines) and not vals:
                vals = _floats(lines[j])
                j += 1
            setname = m.group(2).upper()
            setname = setname[2:] if setname.startswith("N_") else setname
            t = float(m.group(3))
            bucket = out["rf"] if m.group(1) == "force" else out["rfl"]
            bucket.setdefault(setname, []).append((t, vals))
            i = j
            continue
        if "e i g e n v a l u e   o u t p u t" in low:
            j = i + 1
            while j < len(lines):
                v = _floats(lines[j])
                if len(v) >= 4 and float(v[0]).is_integer():
                    out["frequencies"].append(v[3])          # cycles / time
                elif out["frequencies"] and lines[j].strip() and not v:
                    break
                elif "p a r t i c i p a t i o n" in lines[j].lower():
                    break
                j += 1
            i = j
            continue
        if "b u c k l i n g   f a c t o r" in low:
            j = i + 1
            while j < len(lines):
                v = _floats(lines[j])
                if len(v) == 2 and float(v[0]).is_integer():
                    out["buckling"].append(v[1])
                elif out["buckling"] and lines[j].strip():
                    break
                j += 1
            i = j
            continue
        i += 1
    return out


def _floats(line: str) -> list[float]:
    vals = []
    for tok in line.split():
        try:
            vals.append(float(tok))
        except ValueError:
            return []
    return vals
