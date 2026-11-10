"""Engineering verification report (HTML + PDF) for a job folder.

Works for a solved FEA job (results.json present) and for a design-only job
(job.json with geometry plus optional "print" and "gdt" blocks).
"""
from __future__ import annotations

import datetime as _dt
import json
from pathlib import Path
from typing import Any

from .. import __version__
from .. import units as U

Block = tuple


def _load(folder: Path) -> tuple[dict, dict]:
    rp, jp = folder / "results.json", folder / "job.json"
    if rp.exists():
        res = json.loads(rp.read_text(encoding="utf-8"))
        return res, res.get("job") or {}
    if jp.exists():
        from ..fea.job import read_json
        job = read_json(jp)
        return {}, job
    raise FileNotFoundError(f"{folder} has neither results.json nor job.json")


def _m(res: dict, name: str) -> str | None:
    m = res.get("metrics", {}).get(name)
    return U.fmt(m["value"], m["kind"], res.get("units")) if m else None


def _status_word(s: str) -> str:
    return {"PASS": "PASS", "FAIL": "FAIL", "WARN": "REVIEW", "NOT DONE": "NOT DONE", "INFO": "INFO"}.get(s, s)


def assemble(folder: str | Path) -> dict:
    """Collect everything the report shows into a renderer-independent document."""
    from ..cad.inspect import describe, inspect_shape
    folder = Path(folder)
    res, job = _load(folder)
    system = U.normalize_system(res.get("units") or job.get("units"))
    blocks: list[Block] = []
    statuses: list[str] = []
    title = res.get("title") or job.get("title") or job.get("name") or folder.name
    fea = bool(res)
    analysis = res.get("analysis")

    # ---------------- design-side evaluations (always fresh)
    parts = res.get("parts") or []
    geoms: list[tuple[str, Path, Any]] = []
    if parts:
        for p in parts:
            geoms.append((p["name"], folder / p["geometry"], p["material"]["key"]))
    elif job.get("geometry"):
        from ..fea.job import _resolve_geometry
        geoms.append(("part", _resolve_geometry(job["geometry"], folder, "part", False, system), job.get("material")))
    cad_rows = []
    for name, step, mat in geoms:
        try:
            mspec = mat if (isinstance(mat, str) and not mat.startswith("laminate_")) else None
            info = inspect_shape(step, mspec, system)
            cad_rows.append((name, step.name, info))
            statuses.append("PASS" if info["valid"] and info["solids"] >= 1 else "FAIL")
        except Exception as e:
            cad_rows.append((name, step.name, {"error": str(e)}))
            statuses.append("NOT DONE")
    gdt_rev = None
    if job.get("gdt"):
        from ..gdt import review
        gdt_rev = review(job["gdt"], system)
        statuses.append(gdt_rev["status"])
    pr = None
    if job.get("print") and geoms:
        from ..cad.printcheck import print_check
        po = dict(job["print"])
        pr = print_check(geoms[0][1], po.get("process", "fdm"), po.get("material") or
                         (geoms[0][2] if isinstance(geoms[0][2], str) else None),
                         orientation=po.get("orientation", "auto"), build_volume=po.get("build_volume"),
                         infill=po.get("infill"), system=system, overrides=po.get("overrides"))
        statuses.append(pr["status"])
    if fea:
        statuses.append({"PASS": "PASS", "FAIL": "FAIL", "REVIEW": "WARN"}[res["verdict"]])
    verdict = "FAIL" if "FAIL" in statuses else ("REVIEW" if any(s in ("WARN", "NOT DONE") for s in statuses) else "PASS")

    # ---------------- 1 summary
    blocks.append(("h2", "1. Summary"))
    vtext = {"PASS": "All checks performed passed.",
             "REVIEW": "No check failed, but one or more checks need engineering review or were not done.",
             "FAIL": "One or more checks failed. Do not use these results for a design decision until resolved."}[verdict]
    blocks.append(("verdict", verdict, vtext))
    if res.get("description") or job.get("description"):
        blocks.append(("p", res.get("description") or job.get("description")))
    key_rows = []
    if fea:
        order = ["max_displacement", "max_von_mises", "peak_von_mises", "safety_factor_yield",
                 "max_plastic_strain", "frequency_1", "frequency_2", "frequency_3",
                 "buckling_factor_1", "buckling_factor_2", "max_temperature", "min_temperature",
                 "reaction_total", "fatigue_sf_goodman"]
        mets = res.get("metrics", {})
        for k in order + [k for k in mets if k.startswith(("angle.", "heat_flow."))] + \
                [k for k in mets if k.endswith((".time_to_target", ".rate"))]:
            if k in mets and not any(r[0] == mets[k]["label"] for r in key_rows):
                loc = mets[k].get("location")
                key_rows.append((mets[k]["label"], U.fmt(mets[k]["value"], mets[k]["kind"], system),
                                 U.fmt_vec(loc, "length", system) if loc else ""))
        if key_rows:
            blocks.append(("table", ["Result", "Value", "Location"], key_rows, {"widths": [0.5, 0.2, 0.3]}))
    attention = [f"{_status_word(c['status'])} - {c['name']}: {c['detail']}" for c in res.get("checks", [])
                 if c["status"] in ("FAIL", "WARN", "NOT DONE")]
    if gdt_rev:
        attention += [f"{_status_word(f['status'])} - tolerancing, {f['item']}: {f['message']}"
                      for f in gdt_rev["findings"] if f["status"] in ("FAIL", "WARN")]
    if pr:
        attention += [f"{_status_word(c['status'])} - 3D printing, {c['name']}: {c['detail']}"
                      for c in pr["checks"] if c["status"] in ("FAIL", "WARN")]
    for name, fname, info in cad_rows:
        if "error" in info or not info.get("valid", True):
            attention.append(f"FAIL - CAD model {fname} is not a valid solid or could not be read")
    if attention:
        blocks.append(("list", "Items needing attention", attention))
    crit = [c for c in res.get("checks", []) if c["id"] in ("criteria", "fatigue")]
    if crit:
        blocks.append(("checks", [(c["name"], c["status"], c["detail"]) for c in crit], "Acceptance criteria"))

    # ---------------- 2 problem definition
    blocks.append(("h2", "2. Problem definition"))
    kv = [("Job", res.get("name") or job.get("name") or folder.name)]
    if fea:
        kv.append(("Analysis type", analysis.replace("_", " ")))
    kv += [("Unit system (inputs and report)", f"{system} - " + ", ".join(
        U.default_unit(k, system) for k in ("length", "force", "pressure", "mass", "temperature"))),
        ("Solver unit set", U.INTERNAL_BANNER)]
    if fea and res.get("initial_temperature") is not None:
        kv.append(("Initial / stress-free temperature", U.fmt(res["initial_temperature"], "temperature", system)))
    blocks.append(("kv", kv))
    for p in parts:
        mat = p["material"]
        props = ", ".join(f"{k} = {v}" for k, v in mat["properties"].items())
        blocks.append(("p", f"<b>Material - {p['name']}:</b> {mat['name']} ({mat['key']}). {props}."
                       + (f" Orientation: {json.dumps(p['orientation'])}." if p.get("orientation") else "")))
        for note in (mat.get("meta") or {}).get("notes", []) or []:
            blocks.append(("note", f"Laminate model: {note}."))
    if fea:
        if res.get("constraints"):
            blocks.append(("list", "Supports and boundary conditions", res["constraints"]))
        if res.get("loads"):
            blocks.append(("list", "Loads", res["loads"]))
        if res.get("interactions"):
            blocks.append(("list", "Interactions", [
                f"{i['type'].title()} between '{i['master']}' (master) and '{i['slave']}' (slave)"
                + (f", friction {i['friction']}" if i.get("friction") else "") for i in res["interactions"]]))
        if res.get("sets"):
            blocks.append(("table", ["Named face set", "Area", "CAD faces", "Nodes"],
                           [(n, U.fmt(s["area"], "area", system), ", ".join(str(t) for t in s["faces"][:8]),
                             str(s["nodes"])) for n, s in res["sets"].items()], {"widths": [0.3, 0.25, 0.25, 0.2]}))
        for n in res.get("notes", []):
            blocks.append(("note", n))

    # ---------------- 3 CAD verification
    blocks.append(("h2", "3. CAD model verification"))
    for name, fname, info in cad_rows:
        if "error" in info:
            blocks.append(("note", f"{fname}: could not be inspected ({info['error']})"))
            continue
        blocks.append(("kv", [("Part / file", f"{name} / {fname}")] + describe(info, system)))
    if not cad_rows:
        blocks.append(("note", "No geometry file was available for inspection."))

    # ---------------- 4 FEA
    sec = 4
    if fea:
        ms = res["mesh"]
        blocks.append(("h2", f"{sec}. Finite element model")); sec += 1
        blocks.append(("kv", [("Mesher / solver", f"Gmsh / CalculiX {res['solver'].get('version', '')}"),
                              ("Element type", f"{ms['element_type']} ("
                               + ("10-node quadratic tetrahedron" if ms["element_type"] == "C3D10" else "4-node linear tetrahedron") + ")"),
                              ("Nodes / elements", f"{ms['nodes']:,} / {ms['elements']:,}"),
                              ("Target element size", U.fmt(ms["size_mm"], "length", system)),
                              ("Minimum element quality (SICN)", f"{ms.get('quality_min', float('nan')):.2f}"),
                              ("Mesh volume", U.fmt(ms["volume_mm3"], "volume", system)),
                              ("Solve time", f"{res['solver']['seconds']} s")]))
        if res["solver"]["errors"]:
            blocks.append(("note", "SOLVER ERRORS: " + " | ".join(res["solver"]["errors"])))
        blocks.append(("h2", f"{sec}. Results")); sec += 1
        try:
            from .plots import job_plots
            for pl in job_plots(folder, res):
                blocks.append(("img", str(pl["path"]), pl["caption"]))
        except Exception as e:  # plots are optional; never block the report
            blocks.append(("note", f"Plots could not be generated: {type(e).__name__}: {e}"))
        mets = res.get("metrics", {})
        used = {h.get("metric") for h in res.get("hand_calcs", [])}
        comp = (".ux", ".uy", ".uz", ".sxx", ".syy", ".szz", ".sxy", ".syz", ".szx")
        rows = [(m["label"], U.fmt(m["value"], m["kind"], system),
                 U.fmt_vec(m["vector"], m["kind"], system) if m.get("vector") else
                 (U.fmt_vec(m["location"], "length", system) if m.get("location") else ""))
                for k, m in mets.items()
                if not (k.startswith("probe.") and k.endswith(comp) and k not in used)]
        if rows:
            blocks.append(("table", ["Quantity", "Value", "Vector / location"], rows, {"widths": [0.48, 0.2, 0.32]}))
        if res.get("exclusion", {}).get("sets"):
            ex = res["exclusion"]
            blocks.append(("note", f"Design stresses exclude nodes within {U.fmt(ex['distance'], 'length', system)} "
                           f"of: {', '.join(ex['sets'])} (support / contact singularity zones). "
                           f"Stresses are nodal values extrapolated from integration points."))
        blocks.append(("p", "Open <b>viewer.html</b> in this folder for interactive colour plots and "
                       "animated deformation."))

        # hand calculations
        blocks.append(("h2", f"{sec}. Hand calculations")); sec += 1
        hc = res.get("hand_calcs", [])
        if not hc:
            blocks.append(("note", "No hand calculation was supplied for this job."))
        for h in hc:
            lines = []
            if h.get("error"):
                lines.append(f"Could not be evaluated: {h['error']}")
            if h.get("formulas"):
                lines.append("Formula: " + "; ".join(h["formulas"][:4]))
            if h.get("inputs"):
                lines.append("Inputs: " + ", ".join(f"{k} = {v}" for k, v in h["inputs"].items()))
            if h.get("reference"):
                lines.append("Reference: " + h["reference"])
            for n in (h.get("notes") or [])[:3]:
                lines.append("Note: " + n)
            blocks.append(("calc", h["name"], h.get("status", "INFO"), lines,
                           U.fmt(h["expected"], h["kind"], system) if "expected" in h else "",
                           U.fmt(h["fea"], h["kind"], system) if "fea" in h else "",
                           f"{h['diff'] * 100:.2f} % (tolerance {h['tol'] * 100:g} %)" if "diff" in h else ""))

        # checklist
        blocks.append(("h2", f"{sec}. Verification checklist")); sec += 1
        blocks.append(("checks", [(c["name"], c["status"], c["detail"]) for c in res.get("checks", [])
                                  if c["id"] not in ("criteria", "fatigue")], None))
        conv = res.get("convergence")
        if conv and not conv.get("error"):
            blocks.append(("h3", "Mesh convergence study"))
            blocks.append(("p", f"Coarse mesh: size {U.fmt(conv['coarse']['size'], 'length', system)}, "
                           f"{conv['coarse']['nodes']:,} nodes. Fine mesh: size "
                           f"{U.fmt(conv['fine']['size'], 'length', system)}, {conv['fine']['nodes']:,} nodes."))
            blocks.append(("table", ["Metric", "Coarse", "Fine", "Change"],
                           [(r["metric"], U.fmt(r["coarse"], r["kind"], system), U.fmt(r["fine"], r["kind"], system),
                             f"{r['change'] * 100:.2f} %" + ("" if r["required"] else " (singular, informative)"))
                            for r in conv["rows"]], {"widths": [0.4, 0.2, 0.2, 0.2]}))
        fat = res.get("fatigue")
        if fat and not fat.get("error"):
            blocks.append(("h2", f"{sec}. Fatigue screening (stress-life)")); sec += 1
            blocks.append(("kv", [
                ("Stress used", f"{fat['stress_metric']} = {U.fmt(fat['stress_max'], 'pressure', system)}"),
                ("Load ratio R", f"{fat['R']:g}"),
                ("Alternating / mean stress", f"{U.fmt(fat['stress_alt'], 'pressure', system)} / "
                 f"{U.fmt(fat['stress_mean'], 'pressure', system)}"),
                ("Corrected endurance limit Se", U.fmt(fat["Se"], "pressure", system)),
                ("Safety factor - Goodman / Gerber", f"{fat['n_goodman']:.3g} / {fat['n_gerber']:.3g}"),
                ("Safety factor - Soderberg / first-cycle yield",
                 f"{fat['n_soderberg']:.3g} / {fat['n_yield']:.3g}" if fat.get("n_soderberg") else "n/a"),
                ("Estimated life", "infinite (below endurance limit)" if fat["infinite_life"]
                 else f"{fat['cycles']:.3g} cycles"),
                ("Required safety factor", f"{fat['required_sf']:g}  ->  {fat['status']}")]))
            blocks.append(("p", "Formulas: " + "; ".join(f for c in fat["calcs"] for f in c["formulas"][:2])
                           + ". Reference: " + fat["calcs"][0]["reference"] + "."))
            for n in fat.get("notes", []):
                blocks.append(("note", n))

    # ---------------- GD&T
    if gdt_rev:
        blocks.append(("h2", f"{sec}. Dimensioning and tolerancing - "
                       + ("ISO GPS" if gdt_rev["standard"] == "iso" else "ASME Y14.5-2018"))); sec += 1
        blocks.append(("list", "Governing principles", gdt_rev["principles"]))
        if gdt_rev["datums"]:
            blocks.append(("table", ["Datum", "Feature", "Reason"],
                           [(d["label"], d.get("feature", ""), d.get("reason", "")) for d in gdt_rev["datums"]],
                           {"widths": [0.12, 0.38, 0.5]}))
        rows = []
        for f in gdt_rev["features"]:
            size = ""
            if f.get("size_limits"):
                size = f"{U.fmt(f['size_limits'][0], 'length', system, sig=6)} to {U.fmt(f['size_limits'][1], 'length', system, sig=6)}"
                if f.get("fit"):
                    size += f" ({f['fit']['designation']}, {f['fit']['type']})"
            fcf = f["fcf"]["text"] if f.get("fcf") else ""
            plain = f["fcf"]["plain"] if f.get("fcf") else ""
            rows.append((f["name"], size, fcf, plain, "; ".join(f["notes"])))
        if rows:
            blocks.append(("table", ["Feature", "Size limits", "Control frame", "Reads as", "Notes"], rows,
                           {"widths": [0.2, 0.26, 0.3, 0.24], "symbols": 2}))
        if gdt_rev["process"]:
            blocks.append(("p", f"Tolerances were checked against typical capability of process "
                           f"<b>{gdt_rev['process']}</b>."))
        from ..gdt import stackup
        for st in gdt_rev["stacks"]:
            blocks.append(("h3", f"Tolerance stack: {st['name']}"))
            blocks.append(("table", ["Contributor", "Nominal", "Tolerance", "Sense", "Variance share"],
                           [(c["name"], U.fmt(c["nominal"], "length", system, sig=6),
                             f"+{U.fmt(c['plus'], 'length', system)} / -{U.fmt(c['minus'], 'length', system)}",
                             "+" if c["direction"] > 0 else "-", f"{c['contribution'] * 100:.0f} %")
                            for c in st["contributors"]], {"widths": [0.28, 0.17, 0.25, 0.13, 0.17]}))
            blocks.append(("kv", stackup.describe(st, system)))
        blocks.append(("checks", [(f["item"], f["status"], f["message"]) for f in gdt_rev["findings"]] or
                       [("GD&T scheme", "PASS", "no rule violations found in the scheme supplied")],
                       "Tolerancing review findings"))

    # ---------------- print
    if pr:
        blocks.append(("h2", f"{sec}. 3D-printing check ({pr['process_name']})")); sec += 1
        kv = [("Recommended orientation", pr.get("orientation_note", pr["orientation"])),
              ("Part size in print orientation", U.fmt_vec(pr["size"], "length", system)),
              ("Support material (estimate)", U.fmt(pr["support_volume"], "volume", system))]
        if pr.get("mass") is not None:
            kv.append((f"Printed mass ({pr['material']}, {pr['infill'] * 100:.0f} % infill)", U.fmt(pr["mass"], "mass", system, "g" if system == "metric" else "oz")))
        blocks.append(("kv", kv))
        blocks.append(("checks", [(c["name"], c["status"], c["detail"]) for c in pr["checks"]], None))

    # ---------------- standards, limitations, sign-off
    blocks.append(("h2", f"{sec}. Standards and references")); sec += 1
    refs = ["NAFEMS, 'How to Undertake Finite Element Based Analysis' and ASME V&V 10 - verification by "
            "equilibrium, hand calculation and mesh convergence (checklist in this report).",
            "Units: ISO 80000-1 (SI) for metric reports; inch-pound per ASME Y14.5 practice for imperial reports."]
    for h in res.get("hand_calcs", []):
        if h.get("reference") and h["reference"] not in refs:
            refs.append(h["reference"])
    if gdt_rev:
        refs.append("ISO 1101:2017, ISO 5459:2011, ISO 8015:2011, ISO 286-1:2010, ISO 2768-1/-2:1989, ISO 2692:2021"
                    if gdt_rev["standard"] == "iso" else
                    "ASME Y14.5-2018 Dimensioning and Tolerancing; ASME B4.2 (ISO 286) limits and fits; ASME B18.2.8 clearance holes")
    if res.get("fatigue"):
        refs.append("Shigley's Mechanical Engineering Design, 10th ed., Ch. 6 (stress-life fatigue).")
    blocks.append(("list", None, refs))
    blocks.append(("h2", f"{sec}. Assumptions and limitations")); sec += 1
    lim = []
    if fea:
        lim.append("Linear elastic, small-displacement analysis." if analysis in ("static", "modal", "buckling", "thermal_stress")
                   else ("Nonlinear static analysis (large displacement and/or metal plasticity, isotropic hardening)."
                         if analysis == "nonlinear" else "Heat-transfer analysis with temperature-independent properties."))
        lim.append("Material properties are typical room-temperature library or user values; confirm against the "
                   "material certificate or supplier data sheet.")
        if analysis == "buckling":
            lim.append("Eigenvalue buckling assumes a perfect structure and elastic material; real capacity is lower. "
                       "Apply a knock-down factor or run a nonlinear analysis with imperfections.")
        if any(p["material"].get("orthotropic") for p in parts):
            lim.append("Laminates are modelled as a homogenised (smeared) orthotropic solid: ply-level stresses, "
                       "free-edge effects and interlaminar failure are not resolved; ply stresses come from the "
                       "laminate-theory hand calculation.")
        if res.get("interactions"):
            lim.append("Contact uses a linear penalty formulation; tied interfaces are perfectly bonded. "
                       "Bolt preload is not modelled in the FE model (see bolt hand calculations).")
        lim.append("Welds, residual stresses, manufacturing defects and dynamic/impact effects are not included unless stated.")
    if pr:
        lim.append("3D-print checks use typical process rules and a sampled wall-thickness measurement; "
                   "confirm against the machine and material profile actually used.")
    if gdt_rev:
        lim.append("The tolerancing review checks the scheme supplied against rule-based requirements; it does not "
                   "replace a formal drawing check.")
    lim.append("This report is engineering assistance, not a sign-off. Anything safety-critical or subject to "
               "certification needs independent verification and review by a qualified engineer.")
    blocks.append(("list", None, lim))
    blocks.append(("signoff",))
    return {"title": title, "verdict": verdict, "blocks": blocks, "system": system,
            "date": _dt.date.today().isoformat(), "job": res.get("name") or job.get("name") or folder.name,
            "kind": (analysis.replace("_", " ") + " analysis") if fea else "design review",
            "standard": (gdt_rev or {}).get("standard_name") or
            ("ISO GPS" if (res.get("standard") or "iso") == "iso" else "ASME Y14.5"),
            "version": __version__}


def build_report(folder: str | Path, formats: tuple[str, ...] = ("html", "pdf")) -> list[Path]:
    """Write report.html and/or report.pdf into the job folder; returns the files written."""
    from . import render
    folder = Path(folder)
    doc = assemble(folder)
    out = []
    if "html" in formats:
        p = folder / "report.html"
        p.write_text(render.to_html(doc), encoding="utf-8")
        out.append(p)
    if "pdf" in formats:
        p = folder / "report.pdf"
        render.to_pdf(doc, p)
        out.append(p)
    (folder / "report.json").write_text(json.dumps(
        {"title": doc["title"], "verdict": doc["verdict"], "date": doc["date"]}, indent=1), encoding="utf-8")
    return out
