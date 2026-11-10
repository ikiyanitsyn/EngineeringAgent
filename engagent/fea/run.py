"""Run a job end to end: geometry -> mesh -> deck -> solve -> metrics -> checks -> files.

Outputs in the job folder:
    job.inp / job.frd / job.dat / job.log   CalculiX input and raw output
    results.json                            metrics, hand-calc comparison, checks, verdict
    view.json                               surface fields for the viewer and plots
"""
from __future__ import annotations

import json
import math
import time
from pathlib import Path
from typing import Any

import numpy as np

from .. import __version__, handcalc
from .. import units as U
from . import post
from .deck import write_deck
from .job import Job, load_job
from .mesh import Mesh, build_mesh
from .solver import RunLog, read_dat, read_frd, run_ccx

PASS, FAIL, WARN, NOT_DONE, INFO = "PASS", "FAIL", "WARN", "NOT DONE", "INFO"


def _mesh_job(job: Job, size: float | None = None) -> Mesh:
    m = job.mesh
    base = job.L(m["size"]) if "size" in m else None
    return build_mesh([(p.name, str(p.step)) for p in job.parts], job.sets,
                      size=size if size is not None else base, order=int(m.get("order", 2)),
                      refine=m.get("refine"), system=job.system,
                      min_size=job.L(m["min_size"]) if "min_size" in m else None,
                      curvature=int(m.get("curvature", 12)),
                      max_nodes=int(m.get("max_nodes", 600_000)))


def _solve(job: Job, mesh: Mesh, stem: str) -> tuple[RunLog, list, dict, dict]:
    inp = job.folder / f"{stem}.inp"
    info = write_deck(job, mesh, inp)
    log = run_ccx(inp, timeout=float(job.raw.get("timeout", 3600)),
                  serial_solver=job.analysis in ("modal", "buckling"))
    frames = read_frd(inp.with_suffix(".frd"), mesh.n_nodes) if inp.with_suffix(".frd").exists() else []
    dat = read_dat(inp.with_suffix(".dat"))
    for junk in (inp.with_suffix(".12d"), inp.with_suffix(".cvg"), inp.parent / "spooles.out"):
        junk.unlink(missing_ok=True)
    return log, frames, dat, info


def metric_value(metrics: dict, name: str) -> dict:
    if name in metrics:
        return metrics[name]
    import difflib
    hint = difflib.get_close_matches(name, metrics, n=4)
    raise KeyError(f"metric {name!r} is not available for this analysis; "
                   f"available: {', '.join(sorted(metrics))}" + (f" (closest: {', '.join(hint)})" if hint else ""))


def _hand_calcs(job: Job, metrics: dict) -> list[dict]:
    rows = []
    for hc in job.hand_calcs:
        row: dict[str, Any] = {"name": hc.get("name", hc.get("calc", "hand calculation"))}
        try:
            if "calc" in hc:
                res = handcalc.run(hc["calc"], hc.get("inputs", {}), job.system)
                key = hc.get("output") or next(iter(res.outputs))
                expected, kind = res.value(key), res.out_kinds.get(key, "ratio")
                row.update(calc=hc["calc"], output=key, formulas=res.formulas, reference=res.reference,
                           inputs=res.to_dict(job.system)["inputs"], notes=res.notes,
                           all_outputs=res.to_dict(job.system)["outputs"])
            else:
                kind = hc.get("kind", "ratio")
                expected = U.to_internal(hc["expected"], kind, job.system)
                row.update(formulas=[hc["formula"]] if hc.get("formula") else [],
                           reference=hc.get("reference", "user-supplied hand calculation"),
                           inputs=hc.get("inputs", {}), notes=hc.get("notes", []))
            row.update(expected=expected, kind=kind)
            if hc.get("metric"):
                m = metric_value(metrics, hc["metric"])
                fea = m["value"]
                if kind in ("temperature",):
                    ref_span = abs(U.to_internal(hc["span"], "temp_delta", job.system)) \
                        if hc.get("span") else max(abs(expected), 1.0)
                    diff = abs(fea - expected) / ref_span
                elif hc.get("signed"):
                    diff = abs(fea - expected) / max(abs(expected), 1e-30)
                else:
                    diff = abs(abs(fea) - abs(expected)) / max(abs(expected), 1e-30)
                tol = float(hc.get("tol", 0.05))
                row.update(metric=hc["metric"], fea=fea, diff=diff, tol=tol,
                           status=PASS if diff <= tol else FAIL)
            else:
                row.update(status=INFO)
        except Exception as e:  # report, never hide
            row.update(status=FAIL, error=f"{type(e).__name__}: {e}")
        rows.append(row)
    return rows


def _criteria(job: Job, metrics: dict) -> list[dict]:
    out = []
    c = job.criteria
    def add(name, ok, detail):
        out.append({"id": "criteria", "name": name, "status": PASS if ok else FAIL, "detail": detail})
    s = job.system
    if "yield_sf" in c or "min_safety_factor" in c:
        req = float(c.get("yield_sf", c.get("min_safety_factor")))
        if "safety_factor_yield" in metrics:
            v = metrics["safety_factor_yield"]["value"]
            add(f"Safety factor on yield >= {req:g}", v >= req, f"achieved {v:.3g}")
        else:
            out.append({"id": "criteria", "name": f"Safety factor on yield >= {req:g}",
                        "status": NOT_DONE, "detail": "no yield strength / stress result available"})
    if "max_displacement" in c and "max_displacement" in metrics:
        lim = job.L(c["max_displacement"])
        v = metrics["max_displacement"]["value"]
        add(f"Displacement <= {U.fmt(lim, 'length', s)}", v <= lim, f"achieved {U.fmt(v, 'length', s)}")
    if "max_stress" in c and "max_von_mises" in metrics:
        lim = job.q(c["max_stress"], "pressure")
        v = metrics["max_von_mises"]["value"]
        add(f"von Mises <= {U.fmt(lim, 'pressure', s)}", v <= lim, f"achieved {U.fmt(v, 'pressure', s)}")
    if "min_frequency" in c and "frequency_1" in metrics:
        lim = U.to_internal(c["min_frequency"], "frequency", s)
        v = metrics["frequency_1"]["value"]
        add(f"First natural frequency >= {lim:g} Hz", v >= lim, f"achieved {v:.4g} Hz")
    if "min_buckling_factor" in c and "buckling_factor_1" in metrics:
        lim = float(c["min_buckling_factor"])
        v = metrics["buckling_factor_1"]["value"]
        add(f"Buckling load factor >= {lim:g}", v >= lim, f"achieved {v:.4g}")
    if "max_temperature" in c and "max_temperature" in metrics:
        lim = job.q(c["max_temperature"], "temperature")
        v = metrics["max_temperature"]["value"]
        add(f"Temperature <= {U.fmt(lim, 'temperature', s)}", v <= lim,
            f"achieved {U.fmt(v, 'temperature', s)}")
    if "max_plastic_strain" in c and "max_plastic_strain" in metrics:
        lim = float(c["max_plastic_strain"])
        v = metrics["max_plastic_strain"]["value"]
        add(f"Plastic strain <= {lim:g}", v <= lim, f"achieved {v:.4g}")
    return out


def _checks(job: Job, mesh: Mesh, log: RunLog, metrics: dict, info: dict, hand: list[dict],
            conv: dict | None, frames: list) -> list[dict]:
    s = job.system
    ck: list[dict] = []
    def add(cid, name, status, detail):
        ck.append({"id": cid, "name": name, "status": status, "detail": detail})

    # 1 solver
    if log.errors:
        add("solver", "Solver finished without errors", FAIL, "; ".join(log.errors[:3]))
    else:
        w = f"{len(log.warnings)} warning(s): " + " | ".join(log.warnings[:3]) if log.warnings else "no warnings"
        add("solver", "Solver finished without errors", WARN if len(log.warnings) > 0 else PASS,
            f"CalculiX {log.version}, {log.seconds:.1f} s, {w}")
    # 2 units and material plausibility
    odd = []
    for p in job.parts:
        E = p.material.get("E") or p.material.get("E1")
        if job.mechanical and E is not None and not (50.0 <= E <= 1.2e6):
            odd.append(f"{p.material.key}: E = {E:.4g} MPa looks implausible")
        rho = p.material.get("density")
        if rho is not None and not (1e-11 <= rho <= 3e-8):
            odd.append(f"{p.material.key}: density = {rho:.3g} tonne/mm^3 looks implausible")
    add("units", "Unit set and material values", FAIL if odd else PASS,
        "; ".join(odd) if odd else f"deck written in {U.INTERNAL_BANNER}; inputs read as {s}")
    # 3 mesh
    q = mesh.quality.get("quality_min")
    lin = mesh.order == 1 and job.mechanical
    st = WARN if (lin or (q is not None and q < 0.1)) else PASS
    add("mesh", "Mesh quality", st,
        f"{mesh.n_nodes:,} nodes, {mesh.n_elems:,} {mesh.etype}, size {U.fmt(mesh.size, 'length', s)}"
        + (f", min quality (SICN) {q:.2f}" if q is not None else "")
        + ("; first-order tets are too stiff in bending - use order 2" if lin else ""))
    # 4 equilibrium
    if job.analysis in ("static", "nonlinear", "thermal_stress") and "reaction_total" in metrics:
        app = np.array(info.get("applied_force", [0, 0, 0]))
        rt = np.array(metrics["reaction_total"]["vector"])
        scale = max(np.linalg.norm(app), 1e-9)
        direct = np.array(info.get("applied_on_supports", [0, 0, 0]))
        if np.linalg.norm(app) > 0 and not info.get("partial_reactions") and not info.get("unsummed_load"):
            err = np.linalg.norm(rt + app - direct) / scale
            add("equilibrium", "Reactions balance the applied load",
                PASS if err <= 1e-3 else (WARN if err <= 1e-2 else FAIL),
                f"applied {U.fmt_vec(app, 'force', s)}, reactions {U.fmt_vec(rt, 'force', s)}, "
                f"imbalance {err * 100:.3g} %"
                + (f" ({U.fmt(np.linalg.norm(direct), 'force', s)} of the load acts directly on "
                   f"supported nodes and is not part of the reactions)" if np.linalg.norm(direct) > 1e-6 * scale else ""))
        elif info.get("unsummed_load"):
            add("equilibrium", "Reactions balance the applied load", INFO,
                f"net reaction {U.fmt_vec(rt, 'force', s)}; the {info['unsummed_load']} load is not "
                f"totalled by the tool - compare the reaction with m * r * omega^2 by hand")
        else:
            add("equilibrium", "Reactions balance the applied load", INFO,
                f"net reaction {U.fmt_vec(rt, 'force', s)} (self-equilibrated or displacement-driven load)")
    elif job.analysis in ("static", "nonlinear"):
        add("equilibrium", "Reactions balance the applied load", NOT_DONE,
            "no support set with reaction output (minimal restraint only)")
    if job.thermal and (job.analysis != "thermal_stress" or job.coupled):
        flows = [m["value"] for k, m in metrics.items() if k.startswith("heat_flow.")]
        has_surface_exchange = any(l["type"] in ("convection", "radiation") for l in job.loads)
        if flows and not has_surface_exchange and not job.transient:
            net = sum(flows) + info.get("applied_heat", 0.0)
            scale = max(max(abs(f) for f in flows), abs(info.get("applied_heat", 0.0)), 1e-12)
            err = abs(net) / scale
            add("heat_balance", "Heat flows balance", PASS if err <= 1e-2 else FAIL,
                f"net {U.fmt(net, 'power', s)} of {U.fmt(scale, 'power', s)} ({err * 100:.3g} %)")
        else:
            add("heat_balance", "Heat flows balance", NOT_DONE if not job.transient else INFO,
                "transient run (energy is stored)" if job.transient else
                "convection/radiation exchange is not totalled by the solver; compare the heat "
                "flow with a hand calculation")
    # 5 hand calculations
    compared = [h for h in hand if "diff" in h or h["status"] == FAIL]
    if not hand:
        add("hand_calc", "Agreement with hand calculation", NOT_DONE,
            "no hand calculation supplied - a result that cannot be predicted cannot be trusted")
    elif not compared:
        add("hand_calc", "Agreement with hand calculation", NOT_DONE,
            "hand calculations are listed but none is linked to an FEA metric")
    else:
        bad = [h for h in compared if h["status"] == FAIL]
        det = "; ".join(f"{h['name']}: " + (h["error"] if "error" in h else
                        f"{h['diff'] * 100:.2f} % (tol {h['tol'] * 100:g} %)") for h in compared)
        add("hand_calc", "Agreement with hand calculation", FAIL if bad else PASS, det)
    # 6 convergence
    if conv is None:
        add("convergence", "Mesh convergence", NOT_DONE, "run with converge=true (CLI: --converge)")
    elif conv.get("error"):
        add("convergence", "Mesh convergence", NOT_DONE, conv["error"])
    else:
        worst = max((r["change"] for r in conv["rows"] if r["required"]), default=0.0)
        tol = conv["tol"]
        det = "; ".join(f"{r['metric']}: {r['change'] * 100:.2f} %" for r in conv["rows"])
        add("convergence", f"Mesh convergence (size x{conv['ratio']:g}, change < {tol * 100:g} %)",
            PASS if worst <= tol else FAIL, det)
    # 7 singularities
    if "peak_von_mises" in metrics and "max_von_mises" in metrics:
        pk, ds = metrics["peak_von_mises"]["value"], metrics["max_von_mises"]["value"]
        d = info.get("exclusion_distance", 0.0)
        peak_change = next((r["change"] for r in (conv or {}).get("rows", [])
                            if r["metric"] == "peak_von_mises"), None)
        grow = f"; peak changed {peak_change * 100:.1f} % on refinement" if peak_change is not None else ""
        if metrics["peak_von_mises"].get("in_exclusion") and pk > 1.02 * ds:
            add("singularity", "Stress singularities identified and excluded", PASS,
                f"peak {U.fmt(pk, 'pressure', s)} lies within {U.fmt(d, 'length', s)} of a support/"
                f"contact (sets: {', '.join(info.get('exclusion_sets', []))}) and is mesh-dependent, "
                f"so it is not a design value; design stress {U.fmt(ds, 'pressure', s)} is taken "
                f"outside that zone{grow}")
        elif peak_change is not None and peak_change > 0.10:
            add("singularity", "Stress singularities identified and excluded", WARN,
                f"peak stress {U.fmt(pk, 'pressure', s)} is in the design zone but changed "
                f"{peak_change * 100:.1f} % on refinement: likely a sharp corner or point load - "
                f"add a fillet/refinement there or exclude it explicitly")
        else:
            add("singularity", "Stress singularities identified and excluded", PASS,
                f"peak stress {U.fmt(pk, 'pressure', s)} is in the design zone{grow}")
    # 8 linear validity
    if job.analysis in ("static", "thermal_stress") and "max_displacement" in metrics:
        lo, hi = mesh.bbox()
        small = float((hi - lo).min())
        d = metrics["max_displacement"]["value"]
        notes, st = [], PASS
        if d > 0.05 * small:
            st = WARN
            notes.append(f"displacement {U.fmt(d, 'length', s)} exceeds 5 % of the smallest overall "
                         f"dimension ({U.fmt(small, 'length', s)}): check with analysis 'nonlinear'")
        sf = metrics.get("safety_factor_yield")
        if sf and sf["value"] < 1.0:
            st = WARN
            notes.append(f"design stress exceeds yield (SF {sf['value']:.2f}): linear result is "
                         f"not valid beyond yield; run 'nonlinear' with plasticity")
        add("linearity", "Linear analysis is valid", st, "; ".join(notes) or
            "small displacement and stress below yield")
    # 9 sanity
    if job.analysis == "thermal_steady" and "max_temperature" in metrics:
        temps = [job.q(c["value"], "temperature") for c in job.constraints
                 if c["type"] == "temperature" and "value" in c]
        temps += [job.q(l["ambient"], "temperature") for l in job.loads
                  if l["type"] in ("convection", "radiation") and "ambient" in l]
        sources = any(l["type"] in ("heat_flux", "heat_power", "heat_generation") for l in job.loads)
        if temps and not sources:
            lo_t, hi_t = min(temps), max(temps)
            tmax, tmin = metrics["max_temperature"]["value"], metrics["min_temperature"]["value"]
            span = max(hi_t - lo_t, 1e-9)
            ok = tmax <= hi_t + 0.01 * span and tmin >= lo_t - 0.01 * span
            add("sanity", "Temperatures within boundary values", PASS if ok else FAIL,
                f"{U.fmt(tmin, 'temperature', s)} to {U.fmt(tmax, 'temperature', s)} "
                f"(boundaries {U.fmt(lo_t, 'temperature', s)} to {U.fmt(hi_t, 'temperature', s)})")
    if job.analysis == "static" and "max_displacement" in metrics and "applied_force" in metrics:
        u = np.array(metrics["max_displacement"]["vector"])
        f = np.array(metrics["applied_force"]["vector"])
        if np.linalg.norm(u) > 0 and np.linalg.norm(f) > 0:
            cosang = float(u @ f / (np.linalg.norm(u) * np.linalg.norm(f)))
            add("sanity", "Displacement follows the load direction", PASS if cosang > 0 else WARN,
                f"cosine between peak displacement and net load = {cosang:.2f}")
    if job.analysis == "buckling" and "buckling_factor_1" in metrics:
        bf = metrics["buckling_factor_1"]["value"]
        add("sanity", "Buckling factor is positive", PASS if bf > 0 else WARN,
            f"first factor {bf:.4g} (negative means buckling under the reversed load)")
    ck += _criteria(job, metrics)
    return ck


def _verdict(checks: list[dict], solver_ok: bool) -> str:
    if not solver_ok or any(c["status"] == FAIL for c in checks):
        return "FAIL"
    if any(c["status"] in (WARN, NOT_DONE) for c in checks):
        return "REVIEW"
    return "PASS"


CONV_METRICS = {"static": ["max_displacement", "max_von_mises", "peak_von_mises"],
                "nonlinear": ["max_displacement", "max_von_mises"],
                "thermal_stress": ["max_displacement", "max_von_mises", "peak_von_mises"],
                "modal": ["frequency_1", "frequency_2", "frequency_3"],
                "buckling": ["buckling_factor_1"],
                "thermal_steady": ["max_temperature", "min_temperature", "max_heat_flux"],
                "thermal_transient": ["max_temperature", "min_temperature"]}


def _fatigue(job: Job, metrics: dict) -> dict | None:
    fo = job.opts.get("fatigue")
    if not fo or "max_von_mises" not in metrics:
        return None
    s = job.system
    mat = job.parts[0].material
    stress_metric = fo.get("stress", "max_principal")
    smax = abs(metric_value(metrics, stress_metric)["value"]) * float(fo.get("load_factor", 1.0))
    R = float(fo.get("R", 0.0))
    sa, sm = smax * (1 - R) / 2, smax * (1 + R) / 2
    uts, sy = mat.get("uts"), mat.get("yield")
    if not uts:
        return {"error": f"material {mat.key} has no ultimate strength; cannot screen fatigue"}
    etest = job.q(fo["endurance"], "pressure") if "endurance" in fo else \
        (mat.get("endurance") if mat.family not in ("steel", "stainless") else None)
    en = handcalc.run("fatigue.endurance_limit", {
        "uts": f"{uts} MPa", "surface": fo.get("surface", "machined"),
        **({"size": fo["size"]} if "size" in fo else {}),
        "loading": fo.get("loading", "bending"), "reliability": fo.get("reliability", 0.9),
        **({"endurance_test": f"{etest} MPa"} if etest else {})}, s)
    Se = en.value("Se")
    ms = handcalc.run("fatigue.mean_stress", {
        "stress_alt": f"{sa} MPa", "stress_mean": f"{sm} MPa", "Se": f"{Se} MPa", "uts": f"{uts} MPa",
        **({"yield_strength": f"{sy} MPa"} if sy else {}), "Kf": fo.get("Kf", 1.0)}, s)
    life = handcalc.run("fatigue.basquin_life", {
        "stress_alt_equiv": f"{ms.value('stress_alt_equiv')} MPa", "uts": f"{uts} MPa", "Se": f"{Se} MPa"}, s)
    req = float(fo.get("required_sf", 1.5))
    target = fo.get("target_cycles")
    n = ms.value("n_goodman")
    cyc = life.value("cycles")
    status = PASS if n >= req else (PASS if target and cyc >= float(target) else FAIL)
    metrics["fatigue_sf_goodman"] = {"value": n, "kind": "ratio", "label": "Fatigue safety factor (Goodman)"}
    if math.isfinite(cyc):
        metrics["fatigue_life_cycles"] = {"value": cyc, "kind": "ratio", "label": "Estimated life (cycles)"}
    return {"stress_metric": stress_metric, "stress_max": smax, "R": R, "stress_alt": sa,
            "stress_mean": sm, "Se": Se, "n_goodman": n, "n_gerber": ms.value("n_gerber"),
            "n_soderberg": ms.outputs.get("n_soderberg"), "n_yield": ms.outputs.get("n_yield"),
            "cycles": cyc if math.isfinite(cyc) else None, "infinite_life": not math.isfinite(cyc),
            "required_sf": req, "target_cycles": target, "status": status,
            "calcs": [en.to_dict(s), ms.to_dict(s), life.to_dict(s)],
            "notes": en.notes + ms.notes + life.notes +
            (["Endurance limit taken from the material's tested fatigue strength (non-ferrous: "
              "valid at the stated life only, no true endurance limit)."] if etest else [])}


def run_job(spec: dict | str | Path, folder: str | Path | None = None, *, converge: bool = False,
            rebuild_geometry: bool = False, progress=None) -> dict:
    """Run a job and return the results dictionary (also written to results.json)."""
    say = progress or (lambda msg: None)
    t0 = time.time()
    job = load_job(spec, folder, rebuild_geometry)
    job.folder.mkdir(parents=True, exist_ok=True)
    say(f"Meshing {len(job.parts)} part(s) ...")
    mesh = _mesh_job(job)
    say(f"Mesh: {mesh.n_nodes:,} nodes, {mesh.n_elems:,} {mesh.etype}. Solving ({job.analysis}) ...")
    log, frames, dat, info = _solve(job, mesh, "job")
    if job.constraints and any(c["type"] == "minimal" for c in job.constraints):
        info["partial_reactions"] = True
    metrics = post.compute_metrics(job, mesh, frames, dat, info) if frames else {}
    history = post.transient_history(job, mesh, frames, metrics) if job.transient and frames else None

    conv = None
    if converge and log.ok:
        conv = _converge(job, mesh, metrics, say)
    fatigue = _fatigue(job, metrics) if log.ok else None
    hand = _hand_calcs(job, metrics) if log.ok else []
    checks = _checks(job, mesh, log, metrics, info, hand, conv, frames)
    if fatigue and not fatigue.get("error"):
        checks.append({"id": "fatigue", "name": f"Fatigue (Goodman) safety factor >= {fatigue['required_sf']:g}",
                       "status": fatigue["status"],
                       "detail": f"n = {fatigue['n_goodman']:.3g}; life "
                       + ("infinite" if fatigue["infinite_life"] else f"{fatigue['cycles']:.3g} cycles")})
    elif fatigue:
        checks.append({"id": "fatigue", "name": "Fatigue screening", "status": NOT_DONE,
                       "detail": fatigue["error"]})

    results = {
        "engagent_version": __version__, "name": job.name, "title": job.title,
        "description": job.description, "analysis": job.analysis, "units": job.system,
        "standard": job.standard, "status": "ok" if log.ok else "failed",
        "verdict": _verdict(checks, log.ok),
        "solver": {"version": log.version, "seconds": round(log.seconds, 2), "errors": log.errors,
                   "warnings": log.warnings, "command": log.command,
                   "tail": log.tail if not log.ok else ""},
        "mesh": mesh.summary(),
        "parts": [{"name": p.name, "geometry": _rel(p.step, job.folder), "material": p.material.to_dict(job.system),
                   "orientation": p.orientation} for p in job.parts],
        "sets": {n: {"area": fs.area, "faces": fs.face_tags, "nodes": int(len(fs.nodes)),
                     "centroid": fs.centroid.tolist()} for n, fs in mesh.face_sets.items()},
        "constraints": _describe_constraints(job), "loads": info.get("load_summary", []),
        "interactions": job.interactions, "notes": info.get("notes", []),
        "initial_temperature": job.initial_temperature if job.thermal else None,
        "metrics": metrics, "hand_calcs": hand, "checks": checks, "convergence": conv,
        "fatigue": fatigue, "history": history,
        "frequencies": dat.get("frequencies", []), "buckling_factors": dat.get("buckling", []),
        "exclusion": {"distance": info.get("exclusion_distance", 0.0), "sets": info.get("exclusion_sets", [])},
        "criteria": job.criteria, "gdt": job.raw.get("gdt"), "runtime_s": round(time.time() - t0, 1),
        "job": job.raw,
    }
    (job.folder / "results.json").write_text(json.dumps(results, indent=1, default=_json), encoding="utf-8")
    if frames:
        post.write_view(job.folder / "view.json", post.view_data(job, mesh, frames, dat))
    say(f"Done: verdict {results['verdict']} in {results['runtime_s']} s")
    return results


def _converge(job: Job, mesh: Mesh, metrics: dict, say) -> dict:
    opt = job.raw.get("convergence", {})
    ratio = float(opt.get("ratio", 0.5))
    tol = float(opt.get("tol", 0.05))
    limit = int(job.mesh.get("max_nodes", 600_000))
    est = mesh.n_nodes / ratio**3
    while est > limit and ratio < 0.85:
        ratio = min(0.85, ratio + 0.1)
        est = mesh.n_nodes / ratio**3
    try:
        say(f"Convergence run at element size x{ratio:g} ...")
        fine = _mesh_job(job, size=mesh.size * ratio)
        log, frames, dat, info = _solve(job, fine, "job_fine")
        if not log.ok:
            return {"error": "refined run failed: " + "; ".join(log.errors[:2])}
        job.opts["_exclusion_mm"] = post.exclusion_mask(job, mesh, info)[1]   # same zone as coarse
        try:
            m2 = post.compute_metrics(job, fine, frames, dat, info)
        finally:
            job.opts.pop("_exclusion_mm", None)
            for f in job.folder.glob("job_fine.*"):
                f.unlink(missing_ok=True)
    except Exception as e:
        return {"error": f"refined run failed: {type(e).__name__}: {e}"}
    names = list(opt.get("metrics") or CONV_METRICS.get(job.analysis, []))
    names += [k for k in metrics if k.startswith("probe.") and k not in names
              and not k.endswith(("sxy", "syz", "szx", "ux", "uy", "uz", "sxx", "syy", "szz"))]
    rows = []
    for n in names:
        if n in metrics and n in m2:
            a, b = metrics[n]["value"], m2[n]["value"]
            if metrics[n]["kind"] == "temperature":
                span = abs(metrics.get("max_temperature", {}).get("value", a) -
                           metrics.get("min_temperature", {}).get("value", 0.0)) or max(abs(b), 1.0)
                ch = abs(b - a) / span
            else:
                ch = abs(b - a) / max(abs(b), 1e-30)
            rows.append({"metric": n, "coarse": a, "fine": b, "kind": metrics[n]["kind"], "change": ch,
                         "required": n != "peak_von_mises"})
    return {"ratio": ratio, "tol": tol, "rows": rows,
            "coarse": {"size": mesh.size, "nodes": mesh.n_nodes, "elements": mesh.n_elems},
            "fine": {"size": fine.size, "nodes": fine.n_nodes, "elements": fine.n_elems}}


def _describe_constraints(job: Job) -> list[str]:
    out = []
    s = job.system
    for c in job.constraints:
        t = c["type"]
        if t == "fixed":
            out.append(f"Fixed (all translations) on '{c['on']}'")
        elif t == "pinned":
            out.append(f"Pinned (all translations) on '{c['on']}'")
        elif t == "symmetry":
            out.append(f"Symmetry / sliding (u{c.get('normal', 'x')} = 0) on '{c['on']}'")
        elif t == "displacement":
            comps = ", ".join(f"u{ax} = {U.fmt(job.L(c[ax]), 'length', s)}" for ax in "xyz" if ax in c)
            out.append(f"Prescribed displacement on '{c['on']}': {comps}")
        elif t == "minimal":
            out.append("Minimal 3-2-1 restraint (rigid-body motion only)")
        elif t == "temperature":
            out.append(f"Temperature on '{c['on']}': " + ("per schedule" if c.get("schedule") else
                       U.fmt(job.q(c['value'], 'temperature'), 'temperature', s)))
    return out


def _rel(p: Path, base: Path) -> str:
    try:
        return str(Path(p).relative_to(base))
    except ValueError:
        return str(p)


def _json(o):
    if isinstance(o, np.ndarray):
        return o.tolist()
    if isinstance(o, (np.floating, np.integer)):
        return o.item()
    if isinstance(o, Path):
        return str(o)
    return str(o)
