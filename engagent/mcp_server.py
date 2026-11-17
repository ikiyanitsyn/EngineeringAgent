"""MCP server: exposes the toolkit to any MCP-capable AI client.

Run with ``engagent-mcp`` (stdio transport).  Register it in a client with a
command such as ``<repo>/.venv/Scripts/engagent-mcp.exe`` (Windows) or
``<repo>/.venv/bin/engagent-mcp`` (Linux/macOS).  See docs/mcp.md.

Every tool returns plain JSON.  Quantities follow the active unit system
(``units_set``) unless a value carries its own unit string, e.g. "0.25 in".
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from . import config
from . import units as U

INSTRUCTIONS = """EngineeringAgent: parametric CAD (build123d), FEA (Gmsh + CalculiX), hand calculations,
GD&T / tolerancing and verification reports.

Fastest path: call chatbot_prompt once, then make / analyze (one call each) or run_request.

Rules for the calling model:
1. Never invent loads, supports, materials or dimensions. Ask the user for anything missing.
2. Call units_get first. Bare numbers are read in the active unit system; strings may carry units.
3. Hand-calculate first (calc_list / calc_run) and link the calculation to the FEA job with
   "hand_calcs" so the run checks itself.
4. Use cad_faces to find the faces for supports and loads before writing a job.
5. Use fea_job_help for the job schema and a working starter. Run with converge=true before
   anyone acts on a result, then report_build.
6. Only report numbers returned by these tools. If a tool returns an error or verdict FAIL, say so.
7. Results are engineering assistance, not sign-off."""


def _mcp():
    try:
        from mcp.server.fastmcp import FastMCP          # mcp 1.x
        return FastMCP("engineering-agent", instructions=INSTRUCTIONS)
    except Exception:
        from mcp.server.mcpserver import MCPServer      # mcp 2.x
        return MCPServer("engineering-agent", instructions=INSTRUCTIONS)


def _safe(fn):
    """Return {'error': ...} instead of raising, so the client model can read and recover."""
    import functools

    @functools.wraps(fn)
    def wrapper(*a, **k):
        try:
            return fn(*a, **k)
        except Exception as e:
            msg = e.args[0] if isinstance(e, KeyError) and e.args else str(e)
            return {"error": f"{type(e).__name__}: {msg}"}
    return wrapper


def _clean(o: Any) -> Any:
    return json.loads(json.dumps(o, default=str))


def build_server():
    mcp = _mcp()
    tool = lambda f: mcp.tool()(_safe(f))  # noqa: E731

    @tool
    def doctor() -> dict:
        """Check the toolchain: Python packages, Gmsh, CalculiX solver, active units and standard."""
        import importlib
        out: dict = {"units": config.get_units(), "standard": config.get_standard(),
                     "calculix": config.find_ccx() or "NOT FOUND", "root": str(config.root())}
        for m in ("build123d", "gmsh", "scipy", "matplotlib", "reportlab"):
            try:
                out[m] = getattr(importlib.import_module(m), "__version__", "ok")
            except Exception:
                out[m] = "MISSING"
        out["ok"] = out["calculix"] != "NOT FOUND" and "MISSING" not in out.values()
        return out

    @tool
    def units_get() -> dict:
        """Active unit system (metric or imperial) and the default unit of every quantity kind."""
        s = config.get_units()
        return {"units": s, "standard": config.get_standard(s),
                "defaults": {k: d for k, d, _ in U.table(s)},
                "solver_units": U.INTERNAL_BANNER}

    @tool
    def units_set(system: str) -> dict:
        """Switch every tool to 'metric' (mm, kg, N, MPa, degC) or 'imperial' (in, lbm, lbf, psi, degF).
        The choice is saved in the repository and applies to all later calls."""
        s = config.set_units(system)
        return {"units": s, "standard": config.get_standard(s), "defaults": {k: d for k, d, _ in U.table(s)}}

    @tool
    def standard_set(standard: str) -> dict:
        """Set the tolerancing standard: 'auto' (ISO with metric, ASME with imperial), 'iso' or 'asme'."""
        config.set_standard(standard)
        return {"standard": config.get_standard(), "setting": standard}

    @tool
    def convert(value: str, kind: str, to_unit: str = "") -> dict:
        """Convert a quantity. value e.g. '30 psi'; kind e.g. pressure, length, force, temperature."""
        v = U.to_internal(value, kind)
        out = {"metric": U.fmt(v, kind, "metric", sig=6), "imperial": U.fmt(v, kind, "imperial", sig=6)}
        if to_unit:
            out["result"] = f"{U._sig(U.from_internal(v, kind, unit=to_unit), 6)} {to_unit}"
        return out

    @tool
    def materials_list(family: str = "") -> list:
        """Library materials (key, name, family). Families: steel, stainless, aluminium, titanium,
        copper, tooling, print_polymer, thermoplastic, tp_composite."""
        from . import materials
        return [{"key": m.key, "name": m.name, "family": m.family}
                for m in materials.list_materials(family or None)]

    @tool
    def material_get(key: str) -> dict:
        """Properties of one library material in the active unit system (typical values)."""
        from . import materials
        return materials.get(key).to_dict()

    @tool
    def make(shape: str, params: dict | None = None, print_material: str = "", process: str = "",
             name: str = "") -> dict:
        """ONE CALL: build a part and get STEP + STL (+3MF) + report, with a 3D-print check when
        print_material or process is given. shape = template name (cad_templates) or a path to a
        build123d script / STEP file. params in the active unit system, e.g. {"thickness": 6}."""
        from . import quick
        r = quick.make(shape, params or {}, name=name or None, print_process=process or ("fdm" if print_material else None),
                       print_material=print_material or None)
        if r.get("print"):
            r["print"] = {k: r["print"][k] for k in ("status", "orientation_note", "mass", "checks") if k in r["print"]}
        r.pop("job", None)
        return _clean(r)

    @tool
    def analyze(source: str, material: str, fix: list[str] | None = None, forces: list[list[str]] | None = None,
                pressures: list[list[str]] | None = None, temps: list[list[str]] | None = None,
                convects: list[list[str]] | None = None, analysis: str = "static", check: str = "",
                params: dict | None = None, required_sf: float | None = None, quick_run: bool = False) -> dict:
        """ONE CALL FEA. source = STEP path, template name or a job folder from `make`.
        Faces: xmin..zmax, plane:z=0, hole:D@x,y,z, cyl:R, near:x,y,z. forces=[["xmax","0,0,-500"]],
        pressures=[["zmax","0.1"]], temps=[["xmin","100"]], convects=[["xmax","25","20"]].
        check = hand calculation, e.g. "beam.cantilever_end_load P=500 L=200 E=210GPa b=10 h=20"."""
        from . import quick
        r = quick.analyze(source, material=material, analysis=analysis, fix=fix, forces=forces,
                          pressures=pressures, temps=temps, convects=convects, params=params,
                          checks=[check] if check else None, converge=not quick_run,
                          criteria={"yield_sf": required_sf} if required_sf else None)
        res = r["results"]
        return _clean({"folder": r["folder"], "verdict": res["verdict"], "summary": quick.summary_lines(res),
                       "attention": quick.attention_lines(res), "files": r["files"]})

    @tool
    def run_request(text: str) -> dict:
        """Run a request written in the `ea` command format (see `chatbot_prompt`): `ea make ...`,
        `ea analyze last ...`, plus optional ```json job and ```python geometry blocks."""
        from .request import run_request as rr
        r = rr(text)
        return _clean({"ok": r["ok"], "jobs": r["jobs"], "errors": r["errors"], "outputs": r["outputs"]})

    @tool
    def chatbot_prompt() -> str:
        """The full instructions for writing requests: commands, face selectors, templates, materials,
        build123d cheat sheet and examples. Read this once before using make / analyze / run_request."""
        from .prompt import chatbot_prompt as cp
        return cp()

    @tool
    def cad_templates() -> list:
        """Parametric part templates and their parameters (defaults in mm)."""
        from .cad import templates
        return templates.catalog()

    @tool
    def cad_build_template(template: str, folder: str, params: dict | None = None,
                           stl: bool = False, threemf: bool = False) -> dict:
        """Build a template into <folder>/part.step (plus STL / 3MF) and return its verified geometry."""
        from .cad import templates
        return _clean(templates.build_to_step(template, params or {}, Path(folder) / "part.step",
                                              stl=stl, threemf=threemf))

    @tool
    def cad_run_script(script: str, params: dict | None = None, stl: bool = False,
                       threemf: bool = False) -> dict:
        """Run a build123d geometry script (it must end with engagent.cad.save(part)); returns the
        verified geometry: validity, volume, bounding box, centre of mass, files written."""
        from .cad import run_script
        return _clean(run_script(script, None, params or {}, stl=stl, threemf=threemf))

    @tool
    def cad_inspect(file: str, material: str = "") -> dict:
        """Verify a STEP file: valid solid, volume, bounding box, area, mass (if a material is given)."""
        from .cad import inspect_shape
        from .cad.inspect import describe
        info = inspect_shape(file, material or None)
        return {"summary": dict(describe(info)), "internal_mm": _clean(info)}

    @tool
    def cad_faces(file: str) -> list:
        """List the CAD faces of a STEP file (tag, type, area, centroid, bounding box, outward normal,
        radius) in mm, to choose face selectors for supports and loads."""
        from .fea.mesh import list_faces
        keep = ("tag", "part", "type", "area", "centroid", "bbox", "outward", "radius", "axis")
        return _clean([{k: f[k] for k in keep if k in f} for f in list_faces(file)])

    @tool
    def cad_print_check(file: str, process: str = "fdm", material: str = "",
                        orientation: str = "auto") -> dict:
        """3D-printing design check: build volume, wall thickness, overhangs/support, bed contact,
        holes, best orientation, printed mass. process: fdm | sla | sls | mjf | dmls."""
        from .cad.printcheck import print_check
        r = print_check(file, process, material or None, orientation=orientation)
        r.pop("orientations", None)
        return _clean(r)

    @tool
    def calc_list(search: str = "") -> list:
        """Available hand calculations (beams, columns, plates, pressure, Kt, thermal, fatigue,
        bolts, composites). Filter with a search word."""
        from . import handcalc
        return [c for c in handcalc.catalog()
                if not search or search.lower() in (c["name"] + " " + c["title"]).lower()]

    @tool
    def calc_run(name: str, inputs: dict) -> dict:
        """Run a hand calculation, e.g. name='beam.cantilever_end_load',
        inputs={'P': 100, 'L': 100, 'E': '210 GPa', 'b': 10, 'h': 10}. Returns results, formulas, reference."""
        from . import handcalc
        return handcalc.run(name, inputs).to_dict()

    @tool
    def fea_job_help(analysis: str = "static") -> dict:
        """Job schema summary plus a working starter job for an analysis type: static, nonlinear, modal,
        buckling, thermal_steady, convection, thermal_transient, thermal_stress, spring_in, tie, contact, fatigue."""
        from .fea.starters import STARTERS, starter
        doc = config.root() / "docs" / "job-reference.md"
        return {"starter": starter(analysis, config.get_units()), "starters": list(STARTERS),
                "reference": doc.read_text(encoding="utf-8") if doc.exists() else "see docs/job-reference.md"}

    @tool
    def fea_run(job: str, converge: bool = False, report: bool = False) -> dict:
        """Run an FEA job (path to a job folder or job.json). Returns verdict, metrics, hand-calc
        comparison and the verification checklist. converge=true adds a mesh-refinement run;
        report=true also writes report.html, report.pdf and viewer.html."""
        from .fea.run import run_job
        r = run_job(job, converge=converge)
        s = r["units"]
        folder = Path(job) if Path(job).is_dir() else Path(job).parent
        out = {"verdict": r["verdict"], "analysis": r["analysis"], "units": s, "mesh": r["mesh"],
               "solver": r["solver"],
               "metrics": {k: U.fmt(m["value"], m["kind"], s) for k, m in r["metrics"].items()},
               "hand_calcs": [{"name": h["name"], "status": h["status"],
                               "hand": U.fmt(h["expected"], h["kind"], s) if "expected" in h else None,
                               "fea": U.fmt(h["fea"], h["kind"], s) if "fea" in h else None,
                               "difference_percent": round(h["diff"] * 100, 3) if "diff" in h else None,
                               "error": h.get("error")} for h in r["hand_calcs"]],
               "checks": r["checks"], "fatigue": r.get("fatigue"), "files": [str(folder / "results.json")]}
        if report:
            from .report import build_report
            from .viewer import build_viewer
            out["files"] += [str(p) for p in build_report(folder)] + [str(build_viewer(folder))]
        return _clean(out)

    @tool
    def report_build(folder: str, formats: list[str] | None = None) -> dict:
        """Write the verification report (HTML and PDF) for a job folder. Works for solved FEA jobs and
        for design-only jobs (job.json with geometry plus optional 'print' and 'gdt' blocks)."""
        from .report import build_report
        files = build_report(folder, tuple(formats or ("html", "pdf")))
        return {"files": [str(f) for f in files],
                **json.loads((Path(folder) / "report.json").read_text(encoding="utf-8"))}

    @tool
    def viewer_build(folder: str) -> dict:
        """Write viewer.html (interactive colour plots with animated deformation) for a solved job."""
        from .viewer import build_viewer
        return {"viewer": str(build_viewer(folder))}

    @tool
    def gdt_fit(nominal: str, designation: str) -> dict:
        """ISO 286 / ASME B4.2 fit, e.g. nominal='25', designation='H7/g6': limits, clearance, fit type."""
        from .gdt import fits
        f = fits.fit(nominal, designation)
        return {"summary": dict(fits.describe(f)), "internal_mm": f}

    @tool
    def gdt_fastener_hole(size: str, joint: str = "floating", fit: str = "medium") -> dict:
        """Clearance hole (ISO 273 / ASME B18.2.8) and the largest position tolerance that still
        guarantees assembly. joint: floating | fixed."""
        from .gdt import clearance_hole, position_tolerance
        ch = clearance_hole(size, fit)
        return {**ch, **position_tolerance(ch["fastener"], ch["hole"], joint, "metric"), "lengths": "mm"}

    @tool
    def gdt_stack(contributors: list, limits: dict | None = None, monte_carlo: int = 0) -> dict:
        """Tolerance stack-up (worst case, RSS, optional Monte Carlo). contributors:
        [{'name','nominal','tol' or 'plus'/'minus','direction': +1|-1}]; limits: {'min','max'}."""
        from .gdt import stackup
        s = stackup.stack(contributors, limits=limits, monte_carlo=monte_carlo)
        return {"summary": dict(stackup.describe(s)), "status": s.get("status"), "internal_mm": _clean(s)}

    @tool
    def gdt_review(spec: dict) -> dict:
        """Review a GD&T scheme (datums, features with size limits, feature control frames, fasteners,
        stacks, process) against ISO GPS or ASME Y14.5 rules. See docs/gdt.md for the spec format."""
        from .gdt import review
        return _clean(review(spec))

    @tool
    def gdt_process_check(process: str, nominal: str, tolerance: str) -> dict:
        """Is +/- tolerance on a nominal size realistic for a process (cnc_milling, fdm, sls,
        injection_molding, tp_stamp_forming, ...)?"""
        from .gdt import check_tolerance
        return check_tolerance(process, nominal, tolerance)

    return mcp


def main() -> None:
    build_server().run()


if __name__ == "__main__":
    main()
