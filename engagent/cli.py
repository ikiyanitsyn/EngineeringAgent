"""Command line interface: ``engagent <group> <command>``.

Every command accepts ``--json`` for machine-readable output and
``--units metric|imperial`` to override the saved unit system for one call.
"""
from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path

from . import __version__, config
from . import units as U


def _read_json(path):
    from .fea.job import read_json
    return read_json(path)


def _out(args, data, text_lines=None):
    if getattr(args, "json", False):
        print(json.dumps(data, indent=1, default=str))
    else:
        for line in (text_lines if text_lines is not None else [json.dumps(data, indent=1, default=str)]):
            print(line)


def _kv(rows, pad=2):
    w = max((len(str(a)) for a, _ in rows), default=0)
    return [f"{' ' * pad}{str(a).ljust(w)}  {b}" for a, b in rows]


def _params(items) -> dict:
    out = {}
    for it in items or []:
        if "=" not in it:
            raise SystemExit(f"parameter {it!r} must look like name=value")
        k, v = it.split("=", 1)
        try:
            out[k] = json.loads(v)
        except ValueError:
            out[k] = v
    return out


# ------------------------------------------------------------------ general
def cmd_doctor(a):
    import importlib
    import platform
    import subprocess
    rows, ok = [], True
    rows.append(("engagent", __version__))
    rows.append(("python", f"{platform.python_version()} ({sys.executable})"))
    for mod in ("build123d", "gmsh", "numpy", "scipy", "matplotlib", "reportlab"):
        try:
            m = importlib.import_module(mod)
            rows.append((mod, getattr(m, "__version__", "ok")))
        except Exception as e:
            rows.append((mod, f"MISSING ({type(e).__name__})"))
            ok = False
    try:
        importlib.import_module("mcp")
        rows.append(("mcp (optional)", "ok"))
    except Exception:
        rows.append(("mcp (optional)", "not installed - needed only for the MCP server"))
    ccx = config.find_ccx()
    if ccx:
        try:
            v = subprocess.run([ccx, "-v"], capture_output=True, text=True, timeout=30).stdout.strip().splitlines()
            rows.append(("CalculiX", f"{ccx}  [{(v[0] if v else '').strip()}]"))
        except Exception as e:
            rows.append(("CalculiX", f"{ccx} (could not run: {e})"))
            ok = False
    else:
        rows.append(("CalculiX", "NOT FOUND - run scripts/setup.ps1 or scripts/setup.sh, or set ENGAGENT_CCX"))
        ok = False
    rows.append(("unit system", f"{config.get_units()}  (config: {config.config_path()})"))
    rows.append(("tolerancing standard", config.get_standard()))
    bench = None
    if a.full and ok:
        import tempfile
        from .fea.run import run_job
        with tempfile.TemporaryDirectory() as d:
            r = run_job({"name": "doctor", "analysis": "static", "units": "metric",
                         "geometry": {"template": "beam", "params": {"length": 100, "width": 10, "height": 10}},
                         "material": "steel_generic", "mesh": {"size": 3},
                         "sets": {"fixed": "xmin", "tip": "xmax"},
                         "constraints": [{"type": "fixed", "on": "fixed"}],
                         "loads": [{"type": "force", "on": "tip", "value": [0, 0, -100]}],
                         "probes": {"tip": {"set": "tip"}},
                         "hand_calcs": [{"name": "tip deflection", "calc": "beam.cantilever_end_load",
                                         "inputs": {"P": 100, "L": 100, "E": 210000, "b": 10, "h": 10, "nu": 0.3},
                                         "output": "deflection", "metric": "probe.tip.uz", "tol": 0.02}]}, d)
            h = r["hand_calcs"][0] if r["hand_calcs"] else {}
            bench = {"status": h.get("status", "FAIL"), "diff_percent": round(h.get("diff", 1) * 100, 3)}
            rows.append(("benchmark (cantilever)", f"{bench['status']}: FEA vs beam theory "
                                                   f"{bench['diff_percent']} % (limit 2 %)"))
            ok = ok and bench["status"] == "PASS"
    _out(a, {"ok": ok, "items": dict(rows), "benchmark": bench},
         ["EngineeringAgent environment check"] + _kv(rows) + ["", "READY" if ok else "NOT READY - see items above"])
    return 0 if ok else 1


def cmd_units(a):
    if a.system:
        s = config.set_units(a.system)
        msg = f"Unit system set to {s} for all skills and commands (saved in {config.config_path().name})."
    else:
        s = config.get_units()
        msg = f"Active unit system: {s}"
    rows = [(k, f"{d}" + (f"   (solver: {i})" if i else "")) for k, d, i in U.table(s)]
    _out(a, {"units": s, "defaults": {k: d for k, d, _ in U.table(s)}, "standard": config.get_standard(s)},
         [msg, f"Tolerancing standard: {config.get_standard(s).upper()}", ""] + _kv(rows))


def cmd_standard(a):
    if a.standard:
        config.set_standard(a.standard)
    s = config.get_standard()
    _out(a, {"standard": s, "setting": config.load()["standard"]},
         [f"Tolerancing standard: {s.upper()} (setting: {config.load()['standard']}; "
          f"'auto' = ISO GPS with metric, ASME Y14.5 with imperial)"])


def cmd_convert(a):
    v = U.to_internal(a.value, a.kind)
    res = U.from_internal(v, a.kind, unit=a.to) if a.to else None
    other = "imperial" if config.get_units() == "metric" else "metric"
    data = {"input": a.value, "kind": a.kind, "internal": v,
            "metric": U.fmt(v, a.kind, "metric", sig=6), "imperial": U.fmt(v, a.kind, "imperial", sig=6)}
    lines = [f"{a.value} ({a.kind}) = {data['metric']} = {data['imperial']}"]
    if a.to:
        data["result"] = res
        lines = [f"{a.value} = {U._sig(res, 6)} {a.to}"]
    _out(a, data, lines)
    del other


def cmd_materials(a):
    from . import materials
    if a.name:
        m = materials.get(a.name)
        d = m.to_dict()
        _out(a, d, [f"{m.name}  [{m.key}]  family: {m.family}"] + _kv(list(d["properties"].items()))
             + ([f"  note: {m.meta['note']}"] if m.meta.get("note") else [])
             + ["  Typical values - confirm against the supplier data sheet."])
        return
    ms = materials.list_materials(a.family)
    lines = [f"{'key':18s} {'family':15s} name"]
    lines += [f"{m.key:18s} {m.family:15s} {m.name}" for m in ms]
    _out(a, [m.to_dict() for m in ms], lines)


# ------------------------------------------------------------------ cad
def _cad_summary(info, system=None):
    from .cad.inspect import describe
    return _kv(describe(info, system))


def cmd_cad_templates(a):
    from .cad import templates
    cat = templates.catalog()
    lines = []
    for t in cat:
        lines.append(f"{t['name']}: {t['description']}")
        lines.append("    " + ", ".join(f"{k}={v}" for k, v in t["parameters"].items()))
    _out(a, cat, lines)


def cmd_cad_new(a):
    from .cad import templates
    step = Path(a.out) if a.out else Path(a.folder) / "part.step"
    info = templates.build_to_step(a.template, _params(a.param), step, stl=a.stl, threemf=a.threemf)
    _out(a, info, [f"Built template '{a.template}' -> {step}"] + _cad_summary(info)
         + ["  files: " + ", ".join(Path(f).name for f in info["files"])])


def cmd_cad_build(a):
    from .cad import run_script
    info = run_script(a.script, a.out, _params(a.param), stl=a.stl, threemf=a.threemf)
    _out(a, info, [f"Ran {a.script}"] + _cad_summary(info)
         + ["  files: " + ", ".join(Path(f).name for f in info["files"])])


def cmd_cad_inspect(a):
    from .cad import inspect_shape
    info = inspect_shape(a.file, a.material)
    _out(a, info, [f"{a.file}"] + _cad_summary(info))
    return 0 if info["valid"] else 1


def cmd_cad_faces(a):
    from .fea.mesh import list_faces
    faces = list_faces(a.file)
    f3 = lambda v: "(" + ", ".join(f"{U.from_internal(x, 'length'):.4g}" for x in v) + ")"  # noqa: E731
    lines = [f"{len(faces)} faces in {a.file}  (lengths in {U.default_unit('length')})",
             f"{'tag':>4s} {'type':10s} {'area':>10s}  {'centroid':28s} {'outward normal':22s} extra"]
    for f in faces:
        n = f.get("outward")
        extra = (f"radius {U.from_internal(f['radius'], 'length'):.4g}" if "radius" in f else "")
        b = f["bbox"]
        flat = [ax for i, ax in enumerate("xyz") if abs(b[i] - b[i + 3]) < 1e-6]
        if flat:
            extra += f" plane {flat[0]}={U.from_internal(b['xyz'.index(flat[0])], 'length'):.4g}"
        lines.append(f"{f['tag']:4d} {f['type'][:10]:10s} {U.from_internal(f['area'], 'area'):10.4g}  "
                     f"{f3(f['centroid']):28s} "
                     f"{('(' + ', '.join(f'{x:+.2f}' for x in n) + ')') if n and f['type'] == 'Plane' else '':22s} {extra}")
    lines += ["", "Selectors: \"xmin\"..\"zmax\" | {\"plane\":\"x\",\"at\":0} | {\"cylinder\":{\"radius\":5}} | "
              "{\"faces\":[tag,...]} | {\"near\":[x,y,z]} | {\"normal\":[0,0,1]} | {\"box\":[x0,y0,z0,x1,y1,z1]}"]
    _out(a, faces, lines)


def cmd_cad_export(a):
    from .cad.export import convert
    files = convert(a.file, stl=a.stl or not a.threemf, threemf=a.threemf, quality=a.quality, scale=a.scale)
    _out(a, [str(f) for f in files], ["Wrote " + ", ".join(str(f) for f in files)])


def cmd_cad_printcheck(a):
    from .cad.printcheck import print_check
    r = print_check(a.file, a.process, a.material, orientation=a.orientation,
                    build_volume=a.build, infill=a.infill)
    lines = [f"Print check: {a.file}  [{r['process_name']}]  ->  {r['status']}",
             f"  orientation: {r.get('orientation_note', r['orientation'])}"]
    if r.get("mass") is not None:
        lines.append(f"  printed mass: {U.fmt(r['mass'], 'mass', unit='g' if config.get_units() == 'metric' else 'oz')}"
                     f" at {r['infill'] * 100:.0f} % infill")
    lines += [f"  [{c['status']:4s}] {c['name']}: {c['detail']}" for c in r["checks"]]
    r.pop("orientations", None)
    _out(a, r, lines)
    return 0 if r["status"] != "FAIL" else 1


# ------------------------------------------------------------------ fea
def _print_results(r):
    s = r["units"]
    lines = [f"{r['title']}  [{r['analysis']}]   verdict: {r['verdict']}   ({r['runtime_s']} s)",
             f"  mesh: {r['mesh']['nodes']:,} nodes, {r['mesh']['elements']:,} {r['mesh']['element_type']}"]
    if r["solver"]["errors"]:
        lines += ["  SOLVER ERRORS:"] + [f"    {e}" for e in r["solver"]["errors"]]
        if r["solver"].get("tail"):
            lines += ["  --- solver output (tail) ---"] + ["    " + ln for ln in r["solver"]["tail"].splitlines()[-12:]]
    comp = (".ux", ".uy", ".uz", ".sxx", ".syy", ".szz", ".sxy", ".syz", ".szx")
    used = {h.get("metric") for h in r["hand_calcs"]}
    lines.append("  Results:")
    for k, m in r["metrics"].items():
        if k.startswith("probe.") and k.endswith(comp) and k not in used:
            continue
        lines.append(f"    {m['label']}: {U.fmt(m['value'], m['kind'], s)}")
    if r["hand_calcs"]:
        lines.append("  Hand calculations:")
        for h in r["hand_calcs"]:
            if "diff" in h:
                lines.append(f"    [{h['status']}] {h['name']}: hand {U.fmt(h['expected'], h['kind'], s)} vs FEA "
                             f"{U.fmt(h['fea'], h['kind'], s)} ({h['diff'] * 100:.2f} %, tol {h['tol'] * 100:g} %)")
            else:
                lines.append(f"    [{h['status']}] {h['name']}: " + (h.get("error") or U.fmt(h["expected"], h["kind"], s)))
    lines.append("  Checks:")
    lines += [f"    [{c['status']:8s}] {c['name']}: {c['detail']}" for c in r["checks"]]
    return lines


def cmd_fea_run(a):
    from .fea.run import run_job
    say = (lambda m: print("  ..", m, file=sys.stderr)) if not a.json else None
    r = run_job(a.job, converge=a.converge, rebuild_geometry=a.rebuild, progress=say)
    folder = Path(a.job) if Path(a.job).is_dir() else Path(a.job).parent
    extra = []
    if a.report:
        from .report import build_report
        extra += [str(p) for p in build_report(folder)]
    if a.view or a.report:
        from .viewer import build_viewer
        extra.append(str(build_viewer(folder, open_browser=a.open)))
    if a.json:
        slim = {k: r[k] for k in ("name", "analysis", "units", "verdict", "status", "solver", "mesh",
                                  "metrics", "hand_calcs", "checks", "convergence", "fatigue",
                                  "frequencies", "buckling_factors")}
        slim["files"] = extra
        print(json.dumps(slim, indent=1, default=str))
    else:
        for line in _print_results(r) + ([""] + ["  wrote " + e for e in extra] if extra else []):
            print(line)
    return 0 if r["verdict"] != "FAIL" else 1


def cmd_fea_new(a):
    from .fea.starters import starter
    folder = Path(a.folder)
    folder.mkdir(parents=True, exist_ok=True)
    target = folder / "job.json"
    if target.exists() and not a.force:
        raise SystemExit(f"{target} exists; use --force to overwrite")
    job = starter(a.analysis, config.get_units())
    job["name"] = folder.name
    for fname, text in job.pop("files_needed", {}).items():
        (folder / fname).write_text(text, encoding="utf-8")
    target.write_text(json.dumps(job, indent=1), encoding="utf-8")
    _out(a, job, [f"Wrote {target} (a working {a.analysis} example in {config.get_units()} units).",
                  "Edit geometry, material, sets, constraints and loads, then run:",
                  f"  engagent fea run {folder} --converge --report"])


# ------------------------------------------------------------------ calc
def cmd_calc(a):
    from . import handcalc
    if a.name in (None, "list"):
        cat = handcalc.catalog()
        if a.args:
            cat = [c for c in cat if any(q.lower() in (c["name"] + c["title"]).lower() for q in a.args)]
        _out(a, cat, [f"{c['name']:36s} {c['title']}" for c in cat]
             + ["", "Details: engagent calc <name> --help-calc     Run: engagent calc <name> key=value ..."])
        return
    if a.help_calc:
        handcalc._load_all()
        e = handcalc.REGISTRY.get(a.name)
        if not e:
            raise SystemExit(f"unknown calculation {a.name!r}; see `engagent calc list`")
        _out(a, {"name": e.name, "inputs": e.inputs, "outputs": e.outputs, "formulas": e.formulas,
                 "reference": e.reference, "notes": e.notes},
             [f"{e.name}: {e.title}", "  inputs (quantity kind; bare numbers use the active unit system):"]
             + [f"    {k}: {v} [{U.default_unit(v) if v in U.KINDS else v}]" for k, v in e.inputs.items()]
             + ["  outputs: " + ", ".join(e.outputs), "  formulas:"] + [f"    {f}" for f in e.formulas]
             + [f"  reference: {e.reference}"] + [f"  note: {n}" for n in e.notes])
        return
    r = handcalc.run(a.name, _params(a.args))
    d = r.to_dict()
    _out(a, d, [f"{d['title']}", "  inputs:"] + _kv(list(d["inputs"].items()), 4) + ["  results:"]
         + _kv(list(d["outputs"].items()), 4) + ["  formulas:"] + [f"    {f}" for f in d["formulas"]]
         + [f"  reference: {d['reference']}"] + [f"  note: {n}" for n in d["notes"]])


# ------------------------------------------------------------------ gdt
def cmd_gdt_fit(a):
    from .gdt import fits
    f = fits.fit(a.nominal, a.designation)
    _out(a, f, _kv(fits.describe(f)))


def cmd_gdt_general(a):
    from .gdt import general_tolerance
    v = general_tolerance(a.nominal, a.cls, kind=a.kind)
    unit = "deg" if a.kind == "angular" else None
    txt = f"+/-{v:.4g} deg" if unit else ("+/-" if a.kind in ("linear", "radius") else "zone ") + U.fmt(v, "length")
    _out(a, {"nominal": a.nominal, "class": a.cls, "kind": a.kind, "tolerance_mm_or_deg": v},
         [f"ISO 2768-{a.cls} {a.kind} tolerance for {a.nominal}: {txt}"])


def cmd_gdt_hole(a):
    from .gdt import clearance_hole, position_tolerance
    ch = clearance_hole(a.size, a.fit)
    pt = position_tolerance(ch["fastener"], ch["hole"], a.joint, "metric")
    _out(a, {**ch, **pt}, _kv([
        ("Fastener", f"{a.size} (major diameter {U.fmt(ch['fastener'], 'length')})"),
        (f"Clearance hole ({a.fit})", f"{U.fmt(ch['hole'], 'length')}  [{ch['standard']}]"),
        (f"Position tolerance ({pt['joint']} fastener)", f"dia {U.fmt(pt['position_tolerance'], 'length')} at MMC  ({pt['formula']})"),
        ("Reference", pt["reference"])]))


def cmd_gdt_frame(a):
    from .gdt import frame
    f = frame(a.characteristic, a.tolerance, a.datums, diameter=a.dia, modifier=a.mod,
              standard=config.get_standard())
    _out(a, f, [f["text"], f"reads: {f['plain']}  [{f['standard'].upper()}]"])


def cmd_gdt_stack(a):
    from .gdt import stackup
    spec = _read_json(a.file)
    s = stackup.stack(spec["contributors"], limits=spec.get("limits"),
                      monte_carlo=int(spec.get("monte_carlo", a.monte_carlo)))
    _out(a, s, [spec.get("name", "Tolerance stack")] + _kv(stackup.describe(s)))
    return 0 if s.get("status", "PASS") != "FAIL" else 1


def cmd_gdt_review(a):
    from .gdt import review
    spec = _read_json(a.file)
    spec = spec.get("gdt", spec)
    r = review(spec)
    lines = [f"Tolerancing review [{r['standard_name']}]  ->  {r['status']}"]
    lines += [f"  - {p}" for p in r["principles"]]
    for f in r["features"]:
        lines.append(f"  {f['name']}: " + (f["fcf"]["text"] + "  (" + f["fcf"]["plain"] + ")" if f.get("fcf") else "")
                     + ("  " + "; ".join(f["notes"]) if f["notes"] else ""))
    lines += [f"  [{f['status']}] {f['item']}: {f['message']}" for f in r["findings"]] or ["  no findings"]
    _out(a, r, lines)
    return 0 if r["status"] != "FAIL" else 1


def cmd_gdt_process(a):
    from .gdt import general
    if not a.process:
        _out(a, general.PROCESSES, [f"{k:22s} typical +/-{v[0]:g} mm  best +/-{v[2]:g} mm  {v[3]}  {v[4]}"
                                    for k, v in general.PROCESSES.items()])
        return
    c = general.check_tolerance(a.process, a.nominal, a.tolerance) if a.tolerance else \
        general.process_capability(a.process, a.nominal)
    rows = [("Process", c["process"]), ("Typical", "+/-" + U.fmt(c["typical"], "length")),
            ("Best practical", "+/-" + U.fmt(c["best"], "length")), ("Grade", c["grade"]), ("Note", c["note"])]
    if a.tolerance:
        rows.append(("Requested", f"+/-{U.fmt(c['tolerance'], 'length')} -> {c['status']}: {c['message']}"))
    _out(a, c, _kv(rows))


# ------------------------------------------------------------------ report / view
def cmd_report(a):
    from .report import build_report
    files = build_report(a.folder, tuple(a.format))
    info = json.loads((Path(a.folder) / "report.json").read_text())
    _out(a, {"files": [str(f) for f in files], **info},
         [f"Report verdict: {info['verdict']}"] + [f"  wrote {f}" for f in files])
    return 0 if info["verdict"] != "FAIL" else 1


def cmd_view(a):
    from .viewer import build_viewer
    p = build_viewer(a.folder, open_browser=a.open)
    _out(a, {"viewer": str(p)}, [f"Viewer written: {p}", "Open it in any browser (double-click, or add --open)."])


# ------------------------------------------------------------------ quick (one-line) commands
def cmd_make(a):
    from . import quick
    from .cad.inspect import describe
    params = quick.kv_params(a.params)
    pmat = a.print if isinstance(a.print, str) and a.print != "__default__" else None
    process = a.process or ("fdm" if a.print else None)
    if a.print == "__default__":
        pmat = a.material or "petg"
    r = quick.make(a.shape, params, name=a.name, folder=a.folder, material=a.material,
                   print_process=process, print_material=pmat, infill=a.infill,
                   report=not a.no_report, title=a.title)
    lines = [f"Built {a.shape} -> {r['folder']}"] + _kv(describe(r["cad"]))
    if r.get("print"):
        p = r["print"]
        lines += [f"3D-print check ({p['process_name']}): {p['status']}",
                  f"  {p.get('orientation_note', 'orientation ' + p['orientation'])}"]
        if p.get("mass") is not None:
            lines.append(f"  printed mass about {U.fmt(p['mass'], 'mass', unit='g' if config.get_units() == 'metric' else 'oz')}"
                         f" at {p['infill'] * 100:.0f} % infill")
        lines += [f"  [{c['status']}] {c['name']}: {c['detail']}" for c in p["checks"] if c["status"] != "PASS"]
    lines += ["Files:"] + [f"  {f}" for f in r["files"]]
    _out(a, {k: v for k, v in r.items() if k != "job"}, lines)
    return 0 if r.get("verdict") != "FAIL" else 1


def cmd_analyze(a):
    from . import quick
    say = (lambda m: print("  ..", m, file=sys.stderr)) if not a.json else None
    crit = {}
    if a.sf is not None:
        crit["yield_sf"] = a.sf
    if a.max_disp is not None:
        crit["max_displacement"] = a.max_disp
    if a.min_freq is not None:
        crit["min_frequency"] = a.min_freq
    r = quick.analyze(a.source, name=a.name, folder=a.folder, converge=not a.quick, progress=say,
                      material=a.material, analysis=a.type, fix=a.fix, pin=a.pin, slide=a.slide,
                      forces=a.force, pressures=a.pressure, moments=a.moment, gravity=a.gravity,
                      temps=a.temp, convects=a.convect, heats=a.heat, dtemp=a.dT,
                      initial_temperature=a.t0, params=quick.kv_params(a.params), mesh_size=a.size,
                      modes=a.modes, duration=a.duration, criteria=crit or None, fatigue=a.fatigue,
                      checks=a.check, title=a.title)
    res = r["results"]
    if a.json:
        print(json.dumps({"folder": r["folder"], "verdict": res["verdict"], "files": r["files"],
                          "summary": quick.summary_lines(res), "attention": quick.attention_lines(res),
                          "metrics": res["metrics"]}, indent=1, default=str))
    else:
        for line in _print_results(res) + ["", "Files:"] + [f"  {f}" for f in r["files"]]:
            print(line)
    return 0 if res["verdict"] != "FAIL" else 1


def cmd_prompt(a):
    from .prompt import chatbot_prompt
    text = chatbot_prompt()
    if a.out:
        Path(a.out).write_text(text, encoding="utf-8")
        print(f"Wrote {a.out}. Paste its contents into any chatbot (or its custom instructions).")
    else:
        print(text)


def cmd_request(a):
    from .request import run_request
    text = sys.stdin.read() if a.file == "-" else Path(a.file).read_text(encoding="utf-8")
    out = run_request(text, markdown=a.markdown)
    print(out["markdown"] if a.markdown else out["text"])
    return 0 if out["ok"] else 1


# ------------------------------------------------------------------ parser
def build_parser() -> argparse.ArgumentParser:
    common = argparse.ArgumentParser(add_help=False)
    common.add_argument("--json", action="store_true", help="machine-readable JSON output")
    common.add_argument("--units", choices=["metric", "imperial"], help="override the unit system for this call")
    p = argparse.ArgumentParser(prog="engagent", description="CAD + FEA engineering agent toolkit")
    p.add_argument("--version", action="version", version=__version__)
    sub = p.add_subparsers(dest="group", required=True)
    def add(sp, name, fn, help_):
        q = sp.add_parser(name, help=help_, parents=[common])
        q.set_defaults(fn=fn)
        return q

    q = add(sub, "doctor", cmd_doctor, "check the toolchain (Python packages, Gmsh, CalculiX)")
    q.add_argument("--full", action="store_true", help="also run the cantilever benchmark")
    q = add(sub, "units", cmd_units, "show or set the unit system for all skills (metric | imperial)")
    q.add_argument("system", nargs="?", help="metric | imperial (aliases: si, sae, us, inch)")
    q = add(sub, "standard", cmd_standard, "show or set the tolerancing standard (auto | iso | asme)")
    q.add_argument("standard", nargs="?", choices=["auto", "iso", "asme"])
    q = add(sub, "convert", cmd_convert, "convert a quantity, e.g. convert '30 psi' pressure")
    q.add_argument("value"); q.add_argument("kind", choices=U.KINDS); q.add_argument("to", nargs="?")
    q = add(sub, "materials", cmd_materials, "list library materials or show one")
    q.add_argument("name", nargs="?"); q.add_argument("--family")

    cad = sub.add_parser("cad", help="parametric CAD (build123d)").add_subparsers(dest="cmd", required=True)
    add(cad, "templates", cmd_cad_templates, "list parametric part templates")
    q = add(cad, "new", cmd_cad_new, "build a template into a folder")
    q.add_argument("folder"); q.add_argument("--template", "-t", required=True)
    q.add_argument("--param", "-p", action="append", help="name=value (repeatable)")
    q.add_argument("--out", "-o"); q.add_argument("--stl", action="store_true"); q.add_argument("--3mf", dest="threemf", action="store_true")
    q = add(cad, "build", cmd_cad_build, "run a build123d geometry script")
    q.add_argument("script"); q.add_argument("--param", "-p", action="append")
    q.add_argument("--out", "-o"); q.add_argument("--stl", action="store_true"); q.add_argument("--3mf", dest="threemf", action="store_true")
    q = add(cad, "inspect", cmd_cad_inspect, "verify a STEP file: validity, volume, bbox, mass")
    q.add_argument("file"); q.add_argument("--material", "-m")
    q = add(cad, "faces", cmd_cad_faces, "list CAD faces with coordinates (for supports and loads)")
    q.add_argument("file")
    q = add(cad, "export", cmd_cad_export, "convert STEP to STL / 3MF")
    q.add_argument("file"); q.add_argument("--stl", action="store_true"); q.add_argument("--3mf", dest="threemf", action="store_true")
    q.add_argument("--quality", default="fine", choices=["draft", "standard", "fine", "ultra"]); q.add_argument("--scale", type=float, default=1.0)
    q = add(cad, "printcheck", cmd_cad_printcheck, "3D-printing design check")
    q.add_argument("file"); q.add_argument("--process", default="fdm", choices=["fdm", "sla", "sls", "mjf", "dmls"])
    q.add_argument("--material", "-m"); q.add_argument("--orientation", default="auto")
    q.add_argument("--build", nargs=3, metavar=("X", "Y", "Z")); q.add_argument("--infill", type=float)

    fea = sub.add_parser("fea", help="finite element analysis (Gmsh + CalculiX)").add_subparsers(dest="cmd", required=True)
    q = add(fea, "run", cmd_fea_run, "run a job folder or job.json")
    q.add_argument("job"); q.add_argument("--converge", "-c", action="store_true", help="add a mesh-refinement run")
    q.add_argument("--report", "-r", action="store_true", help="also write report.html, report.pdf and viewer.html")
    q.add_argument("--view", action="store_true", help="also write viewer.html"); q.add_argument("--open", action="store_true")
    q.add_argument("--rebuild", action="store_true", help="re-run the geometry script/template first")
    q = add(fea, "new", cmd_fea_new, "write a starter job.json for an analysis type")
    q.add_argument("folder"); q.add_argument("--analysis", "-a", default="static")
    q.add_argument("--force", action="store_true")

    q = add(sub, "calc", cmd_calc, "hand calculations: `calc list`, `calc <name> key=value ...`")
    q.add_argument("name", nargs="?"); q.add_argument("args", nargs="*")
    q.add_argument("--help-calc", action="store_true", help="show inputs, formulas and reference")

    gdt = sub.add_parser("gdt", help="tolerancing and GD&T").add_subparsers(dest="cmd", required=True)
    q = add(gdt, "fit", cmd_gdt_fit, "ISO 286 fit, e.g. gdt fit 25 H7/g6"); q.add_argument("nominal"); q.add_argument("designation")
    q = add(gdt, "general", cmd_gdt_general, "ISO 2768 general tolerance"); q.add_argument("nominal"); q.add_argument("cls", nargs="?", default="m")
    q.add_argument("--kind", default="linear", choices=["linear", "radius", "angular", "flatness", "straightness", "perpendicularity", "symmetry", "runout"])
    q = add(gdt, "hole", cmd_gdt_hole, "clearance hole and position tolerance for a fastener"); q.add_argument("size")
    q.add_argument("--fit", default="medium"); q.add_argument("--joint", default="floating", choices=["floating", "fixed"])
    q = add(gdt, "frame", cmd_gdt_frame, "build a feature control frame"); q.add_argument("characteristic"); q.add_argument("tolerance")
    q.add_argument("datums", nargs="*"); q.add_argument("--dia", action="store_true"); q.add_argument("--mod", choices=["M", "L", "F", "P", "U", "E"])
    q = add(gdt, "stack", cmd_gdt_stack, "tolerance stack-up from a JSON file"); q.add_argument("file"); q.add_argument("--monte-carlo", type=int, default=0)
    q = add(gdt, "review", cmd_gdt_review, "review a GD&T scheme (JSON file or job.json with a 'gdt' block)"); q.add_argument("file")
    q = add(gdt, "process", cmd_gdt_process, "process capability; check a tolerance against a process")
    q.add_argument("process", nargs="?"); q.add_argument("nominal", nargs="?", default="50"); q.add_argument("tolerance", nargs="?")

    q = add(sub, "make", cmd_make, "ONE LINE: build a part (+ STL/3MF, print check, report)")
    q.add_argument("shape", help="template name (ea cad templates), build123d script .py, or STEP file")
    q.add_argument("params", nargs="*", help="name=value overrides, e.g. thickness=6")
    q.add_argument("--print", nargs="?", const="__default__", metavar="MATERIAL",
                   help="run the 3D-print check (default material petg)")
    q.add_argument("--process", choices=["fdm", "sla", "sls", "mjf", "dmls"])
    q.add_argument("--material", "-m"); q.add_argument("--infill", type=float)
    q.add_argument("--name"); q.add_argument("--folder"); q.add_argument("--title")
    q.add_argument("--no-report", action="store_true")

    q = add(sub, "analyze", cmd_analyze, "ONE LINE: FEA of a STEP file, script, template or job folder")
    q.add_argument("source", help="part.step, geometry.py, a template name, or a job folder from `ea make`")
    q.add_argument("params", nargs="*", help="template/script parameters name=value")
    q.add_argument("--material", "-m")
    q.add_argument("--type", "-a", default="static",
                   help="static | nonlinear | modal | buckling | thermal | transient | thermal_stress")
    q.add_argument("--fix", action="append", metavar="FACES", help="fully held faces (repeatable)")
    q.add_argument("--pin", action="append", metavar="FACES")
    q.add_argument("--slide", nargs=2, action="append", metavar=("FACES", "AXIS"),
                   help="symmetry / sliding support: no motion along AXIS")
    q.add_argument("--force", nargs=2, action="append", metavar=("FACES", "FX,FY,FZ"))
    q.add_argument("--pressure", nargs=2, action="append", metavar=("FACES", "P"))
    q.add_argument("--moment", nargs=2, action="append", metavar=("FACES", "MX,MY,MZ"))
    q.add_argument("--gravity", nargs="?", const="1", metavar="G", help="self weight in g (default 1, -Z)")
    q.add_argument("--temp", nargs=2, action="append", metavar=("FACES", "T"))
    q.add_argument("--convect", nargs=3, action="append", metavar=("FACES", "H", "T_AMBIENT"))
    q.add_argument("--heat", nargs=2, action="append", metavar=("FACES", "WATTS"))
    q.add_argument("--dT", metavar="T_FINAL", help="uniform final temperature (thermal stress)")
    q.add_argument("--t0", metavar="T", help="initial / stress-free temperature")
    q.add_argument("--size", help="element size"); q.add_argument("--modes", type=int)
    q.add_argument("--duration", help="transient duration in seconds")
    q.add_argument("--sf", type=float, help="required yield safety factor (default 1.5)")
    q.add_argument("--max-disp", dest="max_disp", help="allowed displacement")
    q.add_argument("--min-freq", dest="min_freq", help="required first frequency, Hz")
    q.add_argument("--fatigue", action="store_true", help="add fatigue screening (load 0 -> max)")
    q.add_argument("--check", action="append", metavar='"CALC k=v ..."',
                   help="hand calculation to compare with, e.g. \"beam.cantilever_end_load P=500 L=200 E=210GPa b=10 h=20\"")
    q.add_argument("--quick", action="store_true", help="skip the mesh-convergence run")
    q.add_argument("--name"); q.add_argument("--folder"); q.add_argument("--title")

    q = add(sub, "prompt", cmd_prompt, "print the instructions that turn any chatbot into a request writer")
    q.add_argument("--out", "-o", help="write to a file instead of printing")

    q = add(sub, "request", cmd_request, "run a request file (commands and/or JSON/Python blocks)")
    q.add_argument("file", help="request text file, or - for stdin")
    q.add_argument("--markdown", action="store_true", help="print a Markdown summary")

    q = add(sub, "report", cmd_report, "write the verification report for a job folder")
    q.add_argument("folder"); q.add_argument("--format", "-f", nargs="+", default=["html", "pdf"], choices=["html", "pdf"])
    q = add(sub, "view", cmd_view, "write the interactive viewer for a solved job")
    q.add_argument("folder"); q.add_argument("--open", action="store_true")
    return p


def main(argv=None) -> int:
    import re
    argv = list(sys.argv[1:] if argv is None else argv)
    # negative values such as -300,0,0 must not be taken for options (a leading space stops that)
    argv = [(" " + x) if re.match(r"^-[\d.]", x) else x for x in argv]
    args = build_parser().parse_args(argv)
    if getattr(args, "units", None):
        os.environ["ENGAGENT_UNITS"] = args.units
    try:
        return int(args.fn(args) or 0)
    except (ValueError, KeyError, FileNotFoundError, RuntimeError) as e:
        msg = e.args[0] if isinstance(e, KeyError) and e.args else str(e)
        if getattr(args, "json", False):
            print(json.dumps({"error": f"{type(e).__name__}: {msg}"}))
        else:
            print(f"error: {msg}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    sys.exit(main())
