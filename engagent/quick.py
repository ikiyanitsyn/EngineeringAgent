"""One-line front end: ``make`` a part, ``analyze`` a part, without writing job.json.

    ea make l_bracket thickness=6 --print petg
    ea analyze part.step -m al_6061_t6 --fix zmin --force xmax 0,0,-500

Each call creates the next numbered folder under ``jobs/`` (or uses ``--folder``),
writes a complete ``job.json`` there (so the run is reproducible and editable),
runs it and writes the report.  Everything is in the active unit system.

Face selector shorthand (``--fix``, ``--force``, ...):

    xmin xmax ymin ymax zmin zmax       extreme planes
    plane:z=12.5                         planar face(s) at z = 12.5
    cyl:3.3       cyl:3.3@10,20,0        cylinders of radius 3.3 (nearest the point)
    hole:6.6                             cylinders of diameter 6.6
    near:10,0,5                          the single face closest to a point
    normal:0,0,1                         planar faces facing +Z
    box:x0,y0,z0,x1,y1,z1                faces inside a box
    faces:3,7                            CAD face tags (from ``ea cad faces``)
    point:0,-5,-5                        a single node (supports only)
    a+b                                  union, e.g. xmin+xmax
"""
from __future__ import annotations

import json
import re
import shutil
from pathlib import Path
from typing import Any

from . import config
from . import units as U

ANALYSIS_WORDS = {"static", "nonlinear", "modal", "buckling", "thermal_steady", "thermal",
                  "thermal_transient", "transient", "thermal_stress", "thermomechanical",
                  "frequency", "stress", "plastic", "heat"}


# --------------------------------------------------------------------------- folders
def slug(text: str, n: int = 32) -> str:
    s = re.sub(r"[^a-z0-9]+", "-", str(text).lower()).strip("-")
    return (s[:n].rstrip("-")) or "job"


def jobs_dir() -> Path:
    return config.root() / "jobs"


def next_job_folder(name: str, base: Path | None = None) -> Path:
    """jobs/NN-name with NN one higher than any existing numbered folder."""
    base = Path(base) if base else jobs_dir()
    base.mkdir(parents=True, exist_ok=True)
    nums = [int(m.group(1)) for p in base.iterdir() if p.is_dir() and (m := re.match(r"(\d+)-", p.name))]
    folder = base / f"{(max(nums) + 1 if nums else 1):02d}-{slug(name)}"
    folder.mkdir(parents=True)
    return folder


# --------------------------------------------------------------------------- parsing
def _nums(text: str) -> list[Any]:
    """'10,20,0' -> [10.0, 20.0, 0.0]; '0,0,-30 lbf' -> ['0 lbf', '0 lbf', '-30 lbf']."""
    t = str(text).strip()
    m = re.match(r"^(.*?)([A-Za-z°][A-Za-z0-9*/^°]*)\s*$", t)
    unit = None
    if m and m.group(1).strip() and not re.fullmatch(r"[eE]\d+", m.group(2)) \
            and not m.group(1).strip().endswith(("e", "E")):
        t, unit = m.group(1).strip(), m.group(2)
    parts = [p.strip() for p in re.split(r"[,;\s]+", t.strip("()[] ")) if p.strip()]
    try:
        vals = [float(p) for p in parts]
    except ValueError as e:
        raise ValueError(f"cannot read numbers from {text!r} (expected e.g. 0,0,-500 or 0,0,-30lbf)") from e
    return [f"{v:g} {unit}" for v in vals] if unit else vals


def selector(text: str) -> Any:
    """Shorthand -> job.json selector (see module docstring)."""
    t = str(text).strip()
    parts = [p.strip() for p in t.split("+") if p.strip()]
    if len(parts) > 1 and all(re.match(r"^([xyz](min|max)$|[a-z]+:)", p.lower()) for p in parts):
        return [selector(p) for p in parts]
    low = t.lower()
    if re.fullmatch(r"[xyz](min|max)", low):
        return low
    if ":" not in t:
        raise ValueError(f"unknown face selector {text!r}. Use xmin..zmax, plane:z=0, cyl:R, hole:D, "
                         f"near:x,y,z, normal:0,0,1, box:..., faces:1,2 or point:x,y,z "
                         f"(run `ea cad faces <part.step>` to see the faces)")
    kind, arg = low.split(":", 1)
    if kind == "plane":
        m = re.fullmatch(r"\s*([xyz])\s*=\s*(.+)", arg)
        if not m:
            raise ValueError(f"plane selector must look like plane:z=12.5, got {text!r}")
        at = m.group(2).strip()
        return {"plane": m.group(1), "at": at if at in ("min", "max") else _one(at)}
    if kind in ("cyl", "cylinder", "hole"):
        size, _, near = arg.partition("@")
        c: dict = {}
        if size.strip():
            c["diameter" if kind == "hole" else "radius"] = _one(size)
        if near:
            c["near"] = _nums(near)
        return {"cylinder": c}
    if kind == "near":
        return {"near": _nums(arg)}
    if kind == "normal":
        return {"normal": [float(v) for v in _nums(arg)]}
    if kind == "box":
        b = _nums(arg)
        if len(b) != 6:
            raise ValueError("box selector needs six numbers: x0,y0,z0,x1,y1,z1")
        return {"box": b}
    if kind == "faces":
        return {"faces": [int(float(v)) for v in _nums(arg)]}
    if kind == "point":
        return {"point": _nums(arg)}
    raise ValueError(f"unknown selector type {kind!r} in {text!r}")


def _one(text: str):
    v = _nums(text)
    if len(v) != 1:
        raise ValueError(f"expected one number, got {text!r}")
    return v[0]


def _set_name(text: str, used: dict) -> str:
    base = slug(text.replace(":", "-").replace("@", "-at-"), 24).replace("-", "_") or "s"
    name, k = base, 2
    while name in used and used[name] != text:
        name, k = f"{base}_{k}", k + 1
    used[name] = text
    return name


def kv_params(items: list[str] | None) -> dict:
    out = {}
    for it in items or []:
        if "=" not in it:
            raise ValueError(f"parameter {it!r} must look like name=value")
        k, v = it.split("=", 1)
        try:
            out[k.strip()] = json.loads(v)
        except ValueError:
            out[k.strip()] = v.strip()
    return out


# --------------------------------------------------------------------------- make
def make(shape: str, params: dict | None = None, *, name: str | None = None, folder: str | Path | None = None,
         material: str | None = None, print_process: str | None = None, print_material: str | None = None,
         infill: float | None = None, report: bool = True, system: str | None = None,
         title: str | None = None, description: str | None = None) -> dict:
    """Build a part (template name or path to a build123d script / STEP file) into a job folder.

    Writes part.step, part.stl, part.3mf, job.json and, by default, report.html/pdf.
    With a print material or process it also runs the 3D-print check.
    """
    from .cad import run_script, templates
    from .cad.inspect import inspect_shape
    system = U.normalize_system(system)
    params = dict(params or {})
    src = Path(shape)
    is_file = src.suffix.lower() in (".py", ".step", ".stp") and src.exists()
    if not is_file and shape not in templates.TEMPLATES:
        import difflib
        hint = difflib.get_close_matches(shape, list(templates.TEMPLATES), n=3)
        raise KeyError(f"unknown part {shape!r}" + (f"; did you mean {', '.join(hint)}?" if hint else "")
                       + f". Templates: {', '.join(templates.TEMPLATES)}. Or give a build123d script (.py) "
                       f"or a STEP file.")
    folder = Path(folder) if folder else next_job_folder(name or (src.stem if is_file else shape))
    folder.mkdir(parents=True, exist_ok=True)
    step = folder / "part.step"
    if is_file and src.suffix.lower() == ".py":
        if src.resolve() != (folder / "geometry.py").resolve():
            shutil.copy(src, folder / "geometry.py")
        info = run_script(folder / "geometry.py", step, params, stl=True, threemf=True, system=system)
        geom = {"script": "geometry.py", **({"params": params} if params else {})}
    elif is_file:
        if src.resolve() != step.resolve():
            shutil.copy(src, step)
        from .cad.export import convert
        convert(step, stl=True, threemf=True)
        info = inspect_shape(step)
        geom = {"step": "part.step"}
    else:
        info = templates.build_to_step(shape, params, step, system, stl=True, threemf=True)
        geom = {"template": shape, "params": params}
    pmat = print_material or (material if print_process else None)
    job: dict = {"name": folder.name, "units": system,
                 "title": title or f"{shape if not is_file else src.stem} ({', '.join(f'{k}={v}' for k, v in params.items()) or 'defaults'})",
                 "geometry": geom}
    if description:
        job["description"] = description
    if material or pmat:
        job["material"] = material or pmat
    if print_process or print_material:
        job["print"] = {"process": print_process or "fdm", **({"material": pmat} if pmat else {}),
                        **({"infill": infill} if infill is not None else {})}
    (folder / "job.json").write_text(json.dumps(job, indent=1) + "\n", encoding="utf-8")
    out = {"folder": str(folder), "cad": info, "job": job,
           "files": [str(p) for p in (step, step.with_suffix(".stl"), step.with_suffix(".3mf")) if p.exists()]}
    if job.get("print"):
        from .cad.printcheck import print_check
        pr = print_check(step, job["print"]["process"], pmat, infill=infill, system=system)
        pr.pop("orientations", None)
        out["print"] = pr
    if report:
        from .report import build_report
        out["files"] += [str(p) for p in build_report(folder)]
        out["verdict"] = json.loads((folder / "report.json").read_text())["verdict"]
    return out


# --------------------------------------------------------------------------- analyze
def build_analysis_job(source: str, *, material: str | None, analysis: str = "static",
                       fix: list[str] | None = None, pin: list[str] | None = None,
                       slide: list[list[str]] | None = None, forces: list[list[str]] | None = None,
                       pressures: list[list[str]] | None = None, moments: list[list[str]] | None = None,
                       gravity: str | None = None, temps: list[list[str]] | None = None,
                       convects: list[list[str]] | None = None, heats: list[list[str]] | None = None,
                       dtemp: str | None = None, initial_temperature: str | None = None,
                       params: dict | None = None, mesh_size: str | None = None, modes: int | None = None,
                       duration: str | None = None, criteria: dict | None = None, fatigue: bool = False,
                       checks: list[str] | None = None, title: str | None = None,
                       system: str | None = None) -> dict:
    """Assemble a job.json dict from one-line options (values in the active unit system)."""
    from .cad import templates
    from .fea.job import ANALYSIS_ALIASES
    system = U.normalize_system(system)
    a = ANALYSIS_ALIASES.get(analysis.lower().replace("-", "_"), analysis.lower().replace("-", "_"))
    if not material:
        from . import materials
        common = ", ".join(k for k in ("steel_generic", "steel_s355", "stainless_304", "al_6061_t6",
                                       "ti_6al4v", "petg", "pla", "abs", "pa12_sls", "peek") if k in materials.LIBRARY)
        raise ValueError("an analysis needs a material (-m). Common choices: " + common
                         + ". All: `ea materials`. Or give properties, e.g. -m '{\"E\": \"70 GPa\", \"nu\": 0.33}'.")
    mat: Any = material
    if isinstance(material, str) and material.strip().startswith("{"):
        mat = json.loads(material)
    src = Path(source)
    if src.suffix.lower() in (".step", ".stp"):
        geom: dict = {"step": src.name}
    elif src.suffix.lower() == ".py":
        geom = {"script": "geometry.py", **({"params": params} if params else {})}
    elif source in templates.TEMPLATES:
        geom = {"template": source, "params": params or {}}
    else:
        raise ValueError(f"cannot analyse {source!r}: give a STEP file, a build123d script (.py) or a "
                         f"template name ({', '.join(templates.TEMPLATES)})")
    sets: dict = {}
    used: dict = {}
    cons: list = []
    loads: list = []
    probes: dict = {}

    def S(text):
        n = _set_name(text, used)
        sets[n] = selector(text)
        return n
    for t in fix or []:
        cons.append({"type": "fixed", "on": S(t)})
    for t in pin or []:
        cons.append({"type": "pinned", "on": S(t)})
    for t, axis in slide or []:
        cons.append({"type": "symmetry", "on": S(t), "normal": axis.lower()})
    for t, v in forces or []:
        n = S(t)
        loads.append({"type": "force", "on": n, "value": _nums(v)})
        probes[n] = {"set": n}
    for t, v in pressures or []:
        n = S(t)
        loads.append({"type": "pressure", "on": n, "value": _one(v)})
        probes[n] = {"set": n}
    for t, v in moments or []:
        n = S(t)
        loads.append({"type": "moment", "on": n, "value": _nums(v)})
        probes[n] = {"set": n}
    if gravity:
        g = [float(x) for x in _nums(gravity)] if "," in gravity else [0.0, 0.0, -abs(float(_one(gravity)))]
        loads.append({"type": "gravity", "g": g})
    for t, v in temps or []:
        cons.append({"type": "temperature", "on": S(t), "value": _one(v)})
    for t, h, amb in convects or []:
        loads.append({"type": "convection", "on": S(t), "h": _one(h), "ambient": _one(amb)})
    for t, v in heats or []:
        n = S(t)
        loads.append({"type": "heat_power", "on": n, "value": _one(v)})
        probes[n] = {"set": n}
    if dtemp is not None:
        loads.append({"type": "temperature_change", "value": _one(dtemp)})
        if a == "static":
            a = "thermal_stress"
    thermal_driven = any(c["type"] == "temperature" for c in cons) or any(
        l["type"] in ("convection", "heat_power") for l in loads)
    mech_bc = [c for c in cons if c["type"] != "temperature"]
    if a == "static" and thermal_driven and not any(l["type"] in ("force", "pressure", "moment", "gravity") for l in loads):
        a = "thermal_steady"
    if a == "thermal_stress" and not mech_bc:
        cons.append({"type": "minimal"})
    job: dict = {"name": "", "units": system, "analysis": a,
                 "title": title or f"{a.replace('_', ' ')} analysis of {src.stem if src.suffix else source}",
                 "geometry": geom, "material": mat, "sets": sets, "constraints": cons, "loads": loads,
                 "probes": probes}
    if initial_temperature is not None:
        job["initial_temperature"] = _one(initial_temperature)
    if mesh_size:
        job["mesh"] = {"size": _one(mesh_size)}
    if modes:
        job[a if a in ("modal", "buckling") else "modal"] = {"modes": int(modes)}
    if a in ("thermal_transient",) or duration:
        job["thermal"] = {"duration": float(_one(duration)) if duration else 600.0, "increments": 60}
    if criteria:
        job["criteria"] = criteria
    elif a in ("static", "nonlinear", "thermal_stress"):
        job["criteria"] = {"yield_sf": 1.5}
    if fatigue:
        job["fatigue"] = {"R": 0, "surface": "machined", "required_sf": 1.5}
    if not checks:
        auto = _auto_beam_check(source, params or {}, mat, cons, loads, a, system)
        checks = [auto] if auto else None
    if checks:
        job["hand_calcs"] = [link_check(c, job, system) for c in checks]
    return job


def _auto_beam_check(source, params, mat, cons, loads, analysis, system) -> str | None:
    """The textbook cantilever: beam template, fixed at xmin, one transverse force on xmax."""
    if source != "beam" or analysis != "static" or str(params.get("section", "rect")) != "rect":
        return None
    if [c["type"] for c in cons] != ["fixed"] or len(loads) != 1 or loads[0]["type"] != "force":
        return None
    from . import materials
    try:
        m = materials.get(mat, system)
    except Exception:
        return None
    E = m.get("E")
    if m.orthotropic or not E:
        return None
    fx, fy, fz = (U.to_internal(v, "force", system) for v in loads[0]["value"])
    if abs(fx) > 1e-9 * max(abs(fy), abs(fz), 1.0) or (fy and fz):
        return None
    dims = {k: (U.to_internal(params[k], "length", system) if k in params else d)
            for k, d in (("length", 100.0), ("width", 10.0), ("height", 10.0))}
    b, h = (dims["width"], dims["height"]) if fz else (dims["height"], dims["width"])
    nu = m.get("nu") or 0.3
    return (f'beam.cantilever_end_load P="{abs(fz or fy):g} N" L="{dims["length"]:g} mm" E="{E:g} MPa" '
            f'b="{b:g} mm" h="{h:g} mm" nu={nu:g}')


# hand-calc output -> how to find the matching FEA result
def link_check(spec: str, job: dict, system: str | None = None) -> dict:
    """``"beam.cantilever_end_load P=500 L=200 E=210GPa b=10 h=20"`` -> a linked hand_calcs entry.

    The output compared is chosen from the analysis: deflection -> displacement of the first
    loaded face; f1 -> first frequency; P_cr -> first buckling factor (P_cr / applied load);
    heat_flow -> heat flow at the first fixed-temperature face; T_at_x / T_surface /
    T_tip -> temperature of the first heated/cooled face. Add ``-> output@metric`` to choose.
    """
    import shlex
    from . import handcalc
    head, _, target = spec.partition("->")
    toks = shlex.split(head)
    if not toks:
        raise ValueError("--check needs a calculation name, e.g. beam.cantilever_end_load P=100 L=100 ...")
    name, inputs = toks[0], kv_params(toks[1:])
    res = handcalc.run(name, inputs, system)
    out_name, metric = None, None
    if target.strip():
        out_name, _, metric = target.strip().partition("@")
        out_name, metric = out_name.strip() or None, metric.strip() or None
    load_sets = [l["on"] for l in job["loads"] if l.get("on")]
    temp_sets = [c["on"] for c in job["constraints"] if c["type"] == "temperature"]
    a = job["analysis"]
    entry: dict = {"name": f"Hand check: {res.title}", "calc": name, "inputs": inputs}
    outs = res.outputs
    if out_name is None:
        for cand in ("deflection", "f1", "P_cr", "heat_flow", "T_surface", "T_at_x", "T_tip", "elongation",
                     "growth", "stress"):
            if cand in outs:
                out_name = cand
                break
    if out_name not in outs:
        raise ValueError(f"{name} has no output {out_name!r}; outputs: {', '.join(outs)}")
    tol = 0.05
    if metric is None:
        if out_name in ("deflection", "elongation", "growth") and load_sets:
            metric = f"probe.{load_sets[0]}.displacement"
        elif out_name == "f1":
            metric = "frequency_1"
        elif out_name == "P_cr" and a == "buckling":
            F = next((l for l in job["loads"] if l["type"] == "force"), None)
            if F is None:
                raise ValueError("a P_cr check needs a --force load to compare the buckling factor with")
            import math
            mag = math.sqrt(sum(U.to_internal(v, "force", system) ** 2 for v in F["value"]))
            return {"name": "Hand check: Euler buckling factor P_cr / applied load",
                    "inputs": {k: str(v) for k, v in inputs.items()},
                    "expected": res.value("P_cr") / mag, "kind": "ratio",
                    "formula": "factor = P_cr / P; " + "; ".join(res.formulas[:1]),
                    "reference": res.reference, "metric": "buckling_factor_1", "tol": 0.05}
        elif out_name == "heat_flow" and temp_sets:
            metric = f"heat_flow.{temp_sets[0]}"
            tol = 0.02
        elif out_name.startswith("T_"):
            heated = [l["on"] for l in job["loads"] if l["type"] in ("convection", "heat_power") and l.get("on")]
            if heated:
                metric = f"probe.{heated[0]}.temperature"
                job["probes"].setdefault(heated[0], {"set": heated[0]})
                tol = 0.02
                fixed = [c for c in job["constraints"] if c["type"] == "temperature"]
                conv = [l for l in job["loads"] if l["type"] == "convection"]
                if fixed and conv:            # compare relative to the driving temperature difference
                    dT = abs(U.to_internal(fixed[0]["value"], "temperature", system)
                             - U.to_internal(conv[0]["ambient"], "temperature", system))
                    entry["span"] = f"{U.from_internal(dT, 'temp_delta', system):g}"
        elif out_name == "stress":
            metric = "max_von_mises"
            tol = 0.15
    entry.update(output=out_name, tol=tol)
    if metric:
        entry["metric"] = metric
    return entry


def analyze(source: str, *, name: str | None = None, folder: str | Path | None = None,
            converge: bool = True, report: bool = True, progress=None, **kw) -> dict:
    """Create a job folder from one-line options, run it, write the report and viewer."""
    from .fea.job import read_json
    from .fea.run import run_job
    system = U.normalize_system(kw.get("system"))
    keep: dict = {}
    if Path(source).is_dir():                       # analyse a part made earlier with `make`
        folder = Path(source)
        old = read_json(folder / "job.json") if (folder / "job.json").exists() else {}
        keep = {k: old[k] for k in ("geometry", "print", "gdt", "description", "units") if k in old}
        if not kw.get("material") and old.get("material"):
            kw["material"] = old["material"]
        source = str(folder / "part.step")
        if not Path(source).exists():
            raise FileNotFoundError(f"{folder} has no part.step; build the part first (ea make ...)")
        system = U.normalize_system(keep.get("units", system))
    job = build_analysis_job(source, system=system, **{k: v for k, v in kw.items() if k != "system"})
    job.update(keep)
    geo = job.get("geometry") or {}
    if not job.get("hand_calcs") and geo.get("template") == "beam":     # part made earlier with `make beam`
        auto = _auto_beam_check("beam", geo.get("params") or {}, job["material"], job["constraints"],
                                job["loads"], job["analysis"], system)
        if auto:
            job["hand_calcs"] = [link_check(auto, job, system)]
    src = Path(source)
    if src.suffix and not src.exists():
        raise FileNotFoundError(f"{source} not found")
    folder = Path(folder) if folder else next_job_folder(name or (src.stem if src.suffix else source))
    folder.mkdir(parents=True, exist_ok=True)
    if src.suffix.lower() in (".step", ".stp") and src.resolve() != (folder / src.name).resolve():
        shutil.copy(src, folder / src.name)
    if src.suffix.lower() == ".py" and src.resolve() != (folder / "geometry.py").resolve():
        shutil.copy(src, folder / "geometry.py")
    job["name"] = folder.name
    (folder / "job.json").write_text(json.dumps(job, indent=1) + "\n", encoding="utf-8")
    r = run_job(folder, converge=converge, progress=progress)
    files = [str(folder / "job.json"), str(folder / "results.json")]
    if report:
        from .report import build_report
        from .viewer import build_viewer
        files += [str(p) for p in build_report(folder)] + [str(build_viewer(folder))]
    return {"folder": str(folder), "results": r, "files": files}


# --------------------------------------------------------------------------- text summaries
def summary_lines(r: dict, top: int = 8) -> list[str]:
    """Short human summary of a results dict (for chat replies and issue comments)."""
    s = r["units"]
    m = r["metrics"]
    order = ["safety_factor_yield", "max_von_mises", "max_displacement", "frequency_1", "frequency_2",
             "buckling_factor_1", "max_temperature", "min_temperature", "max_plastic_strain",
             "fatigue_sf_goodman", "reaction_total"]
    keys = [k for k in order if k in m] + [k for k in m if k.startswith(("angle.", "heat_flow."))]
    lines = [f"{m[k]['label']}: {U.fmt(m[k]['value'], m[k]['kind'], s)}" for k in keys[:top]]
    for h in r.get("hand_calcs", []):
        if "diff" in h:
            lines.append(f"Hand calc '{h['name']}': {h['status']} ({h['diff'] * 100:.1f} % difference)")
    return lines


def attention_lines(r: dict) -> list[str]:
    return [f"{c['status']}: {c['name']} - {c['detail']}" for c in r.get("checks", [])
            if c["status"] in ("FAIL", "WARN", "NOT DONE")]
