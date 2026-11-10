"""Post-processing: derived fields, metrics, probes and viewer data."""
from __future__ import annotations

import json
from pathlib import Path

import numpy as np

from .. import units as U
from .job import Job
from .mesh import Mesh
from .solver import Frame


def von_mises(S: np.ndarray) -> np.ndarray:
    sx, sy, sz, txy, tyz, tzx = S.T
    return np.sqrt(0.5 * ((sx - sy)**2 + (sy - sz)**2 + (sz - sx)**2) + 3 * (txy**2 + tyz**2 + tzx**2))


def principals(S: np.ndarray) -> np.ndarray:
    """(N, 3) principal stresses, descending."""
    m = np.zeros((len(S), 3, 3))
    m[:, 0, 0], m[:, 1, 1], m[:, 2, 2] = S[:, 0], S[:, 1], S[:, 2]
    m[:, 0, 1] = m[:, 1, 0] = S[:, 3]
    m[:, 1, 2] = m[:, 2, 1] = S[:, 4]
    m[:, 0, 2] = m[:, 2, 0] = S[:, 5]
    return np.linalg.eigvalsh(m)[:, ::-1]


def exclusion_mask(job: Job, mesh: Mesh, info: dict) -> tuple[np.ndarray, float, list[str]]:
    """Nodes near supports / interaction surfaces where stress is mesh-dependent."""
    opt = job.opts.get("stress_exclusion", {})
    if opt is False or (isinstance(opt, dict) and opt.get("enabled") is False):
        return np.zeros(mesh.n_nodes, bool), 0.0, []
    opt = opt if isinstance(opt, dict) else {}
    dist = job.opts["_exclusion_mm"] if "_exclusion_mm" in job.opts else \
        (job.L(opt["distance"]) if "distance" in opt else 2.0 * mesh.size)
    names = list(opt.get("sets") or info.get("constraint_sets", []))
    for it in job.interactions:
        names += [it["master"], it["slave"]]
    names = [n for n in dict.fromkeys(names) if n in mesh.node_sets]
    mask = np.zeros(mesh.n_nodes, bool)
    if not names or dist <= 0:
        return mask, dist, names
    from scipy.spatial import cKDTree
    src = np.unique(np.concatenate([mesh.node_sets[n] for n in names]))
    tree = cKDTree(mesh.nodes[src - 1])
    d, _ = tree.query(mesh.nodes, distance_upper_bound=dist)
    mask = np.isfinite(d)
    return mask, dist, names


def _metric(value, kind, label, **extra) -> dict:
    return {"value": float(value), "kind": kind, "label": label, **extra}


def _loc(mesh: Mesh, idx: int) -> list[float]:
    return [float(v) for v in mesh.nodes[idx]]


def probe_weights(job: Job, mesh: Mesh, spec: dict) -> tuple[np.ndarray, np.ndarray]:
    """(node indices, weights) so that the probe value is ``weights @ field[indices]``.

    A set probe is the plain average over the set.  A point probe is a local linear
    least-squares fit through the nearest nodes evaluated at the point, which is far less
    mesh-dependent than reading the nearest node.
    """
    if "set" in spec:
        idx = mesh.node_sets[spec["set"]] - 1
        return idx, np.full(len(idx), 1.0 / len(idx))
    pt = np.array([job.L(v) for v in spec["point"]])
    pool = (mesh.part_nodes(spec["part"]) - 1) if spec.get("part") else np.arange(mesh.n_nodes)
    d = np.linalg.norm(mesh.nodes[pool] - pt, axis=1)
    if "radius" in spec:
        sel = np.nonzero(d <= job.L(spec["radius"]))[0]
        if len(sel) < 8:
            sel = np.argsort(d)[:16]
    else:
        sel = np.argsort(d)[:16]
    idx = pool[sel]
    if d[sel].min() < 1e-9 * max(1.0, mesh.size):          # exactly on a node
        w = np.zeros(len(idx))
        w[int(np.argmin(d[sel]))] = 1.0
        return idx, w
    A = np.column_stack([np.ones(len(idx)), (mesh.nodes[idx] - pt) / max(mesh.size, 1e-12)])
    return idx, np.linalg.pinv(A)[0]


def compute_metrics(job: Job, mesh: Mesh, frames: list[Frame], dat: dict, info: dict) -> dict:
    """Headline numbers in internal units, keyed by metric name."""
    M: dict[str, dict] = {}
    if not frames:
        return M
    a = job.analysis
    last = frames[-1]
    excl, dist, excl_sets = exclusion_mask(job, mesh, info)
    info["exclusion_distance"], info["exclusion_sets"] = dist, excl_sets

    if a in ("static", "nonlinear", "thermal_stress") and "U" in last.fields:
        Uv = last.fields["U"]
        mag = np.linalg.norm(Uv, axis=1)
        i = int(np.argmax(mag))
        M["max_displacement"] = _metric(mag[i], "length", "Maximum displacement", location=_loc(mesh, i),
                                        vector=Uv[i].tolist())
        for c, ax in enumerate("xyz"):
            j = int(np.argmax(np.abs(Uv[:, c])))
            M[f"max_u{ax}"] = _metric(Uv[j, c], "length", f"Largest u{ax}", location=_loc(mesh, j))
    if a in ("static", "nonlinear", "thermal_stress") and "S" in last.fields:
        S = last.fields["S"]
        vm = von_mises(S)
        i = int(np.argmax(vm))
        M["peak_von_mises"] = _metric(vm[i], "pressure", "Peak von Mises stress (anywhere)",
                                      location=_loc(mesh, i), in_exclusion=bool(excl[i]))
        ok = ~excl if (~excl).any() else np.ones_like(excl)
        vm_d = np.where(ok, vm, -1.0)
        j = int(np.argmax(vm_d))
        M["max_von_mises"] = _metric(vm[j], "pressure",
                                     "Design von Mises stress (away from supports/contacts)",
                                     location=_loc(mesh, j))
        pr = principals(S)
        p1 = np.where(ok, pr[:, 0], -1e30)
        p3 = np.where(ok, pr[:, 2], 1e30)
        k1, k3 = int(np.argmax(p1)), int(np.argmin(p3))
        M["max_principal"] = _metric(pr[k1, 0], "pressure", "Maximum principal stress (design zone)",
                                     location=_loc(mesh, k1))
        M["min_principal"] = _metric(pr[k3, 2], "pressure", "Minimum principal stress (design zone)",
                                     location=_loc(mesh, k3))
        # safety factor per part against yield
        sfs = []
        for pi, part in enumerate(job.parts):
            y = part.material.get("yield")
            if y is None or part.material.orthotropic:
                continue
            nodes = mesh.part_nodes(part.name) - 1
            sel = nodes[ok[nodes]]
            if len(sel):
                sfs.append((y / max(vm[sel].max(), 1e-12), part.name, y))
        if sfs:
            sf, pname, y = min(sfs)
            M["safety_factor_yield"] = _metric(sf, "ratio", "Safety factor on yield (design stress)",
                                               part=pname, yield_strength=y)
        if "PEEQ" in last.fields:
            pe = last.fields["PEEQ"][:, 0]
            k = int(np.argmax(pe))
            M["max_plastic_strain"] = _metric(pe[k], "ratio", "Maximum equivalent plastic strain",
                                              location=_loc(mesh, k))
    # reactions
    if dat.get("rf"):
        tot = np.zeros(3)
        for name, rows in dat["rf"].items():
            v = np.array(rows[-1][1][:3])
            key = _orig_name(name, mesh)
            M[f"reaction.{key}"] = _metric(np.linalg.norm(v), "force", f"Reaction force on '{key}'",
                                           vector=v.tolist())
            tot += v
        M["reaction_total"] = _metric(np.linalg.norm(tot), "force", "Total reaction force",
                                      vector=tot.tolist())
    app = np.array(info.get("applied_force", [0, 0, 0]))
    if a in ("static", "nonlinear", "thermal_stress") and np.linalg.norm(app) > 0:
        M["applied_force"] = _metric(np.linalg.norm(app), "force", "Total applied force",
                                     vector=app.tolist())
    if a == "modal":
        for k, fq in enumerate(dat.get("frequencies", [])[:20], 1):
            M[f"frequency_{k}"] = _metric(fq, "frequency", f"Natural frequency, mode {k}")
    if a == "buckling":
        for k, bf in enumerate(dat.get("buckling", [])[:20], 1):
            M[f"buckling_factor_{k}"] = _metric(bf, "ratio", f"Buckling load factor, mode {k}")
    if "T" in last.fields and job.thermal and (a != "thermal_stress" or job.coupled):
        T = last.fields["T"][:, 0]
        i, j = int(np.argmax(T)), int(np.argmin(T))
        M["max_temperature"] = _metric(T[i], "temperature", "Maximum temperature", location=_loc(mesh, i))
        M["min_temperature"] = _metric(T[j], "temperature", "Minimum temperature", location=_loc(mesh, j))
        if "HFL" in last.fields:
            q = np.linalg.norm(last.fields["HFL"], axis=1)
            k = int(np.argmax(q))
            M["max_heat_flux"] = _metric(q[k], "heat_flux", "Maximum heat flux", location=_loc(mesh, k))
        for name, rows in dat.get("rfl", {}).items():
            key = _orig_name(name, mesh)
            M[f"heat_flow.{key}"] = _metric(rows[-1][1][0], "power",
                                            f"Heat flow into the model at '{key}'")

    # probes
    for pname, spec in job.probes.items():
        idx, w = probe_weights(job, mesh, spec)
        loc = ([job.L(v) for v in spec["point"]] if "point" in spec
               else mesh.nodes[idx].mean(axis=0).tolist())
        if "U" in last.fields and a not in ("modal", "buckling"):
            u = w @ last.fields["U"][idx]
            for c, ax in enumerate("xyz"):
                M[f"probe.{pname}.u{ax}"] = _metric(u[c], "length", f"u{ax} at probe '{pname}'", location=loc)
            M[f"probe.{pname}.displacement"] = _metric(np.linalg.norm(u), "length",
                                                       f"Displacement at probe '{pname}'", location=loc)
        if "S" in last.fields and a not in ("modal", "buckling"):
            sv = w @ last.fields["S"][idx]
            for c, nm in enumerate(("sxx", "syy", "szz", "sxy", "syz", "szx")):
                M[f"probe.{pname}.{nm}"] = _metric(sv[c], "pressure", f"{nm} at probe '{pname}'", location=loc)
            M[f"probe.{pname}.von_mises"] = _metric(von_mises(sv[None, :])[0], "pressure",
                                                    f"von Mises at probe '{pname}'", location=loc)
        if "T" in last.fields:
            M[f"probe.{pname}.temperature"] = _metric(w @ last.fields["T"][idx, 0], "temperature",
                                                      f"Temperature at probe '{pname}'", location=loc)
    return M


def _orig_name(upper: str, mesh: Mesh) -> str:
    for n in mesh.node_sets:
        if n.upper() == upper:
            return n
    return upper.lower()


def transient_history(job: Job, mesh: Mesh, frames: list[Frame], metrics: dict) -> dict:
    """Temperature histories at probes plus time-to-target and cooling/heating rates."""
    hist: dict = {"time": [f.value for f in frames]}
    if not frames or "T" not in frames[0].fields:
        return hist
    t = np.array(hist["time"])
    T0 = job.initial_temperature
    hist["max"] = [float(f.fields["T"].max()) for f in frames]
    hist["min"] = [float(f.fields["T"].min()) for f in frames]
    th = job.opts.get("thermal", {})
    window = th.get("rate_window")
    for pname, spec in job.probes.items():
        idx, w = probe_weights(job, mesh, spec)
        series = np.array([w @ f.fields["T"][idx, 0] for f in frames])
        hist[pname] = series.tolist()
        tt = np.concatenate([[0.0], t])
        ss = np.concatenate([[T0], series])
        if "target" in spec:
            tgt = job.q(spec["target"], "temperature")
            cross = np.nonzero((ss[:-1] - tgt) * (ss[1:] - tgt) <= 0)[0]
            if len(cross):
                k = int(cross[0])
                f = 0.0 if ss[k + 1] == ss[k] else (tgt - ss[k]) / (ss[k + 1] - ss[k])
                metrics[f"probe.{pname}.time_to_target"] = _metric(
                    tt[k] + f * (tt[k + 1] - tt[k]), "time",
                    f"Time for probe '{pname}' to reach {U.fmt(tgt, 'temperature', job.system)}")
        if window:
            hi, lo = sorted((job.q(window[0], "temperature"), job.q(window[1], "temperature")), reverse=True)
            def cross_time(level):
                c = np.nonzero((ss[:-1] - level) * (ss[1:] - level) <= 0)[0]
                if not len(c):
                    return None
                k = int(c[0])
                f = 0.0 if ss[k + 1] == ss[k] else (level - ss[k]) / (ss[k + 1] - ss[k])
                return tt[k] + f * (tt[k + 1] - tt[k])
            t1, t2 = cross_time(hi), cross_time(lo)
            if t1 is not None and t2 is not None and t1 != t2:
                metrics[f"probe.{pname}.rate"] = _metric(
                    (hi - lo) / abs(t2 - t1), "temp_rate",
                    f"Mean rate at probe '{pname}' between {U.fmt(hi, 'temperature', job.system)} "
                    f"and {U.fmt(lo, 'temperature', job.system)}")
    return hist


# --------------------------------------------------------------------------- viewer data
def _r(a: np.ndarray, sig: int = 5) -> list:
    a = np.asarray(a, dtype=float)
    with np.errstate(divide="ignore", invalid="ignore"):
        mag = np.where(a == 0, 1.0, 10.0 ** (sig - 1 - np.floor(np.log10(np.abs(np.where(a == 0, 1.0, a))))))
    return (np.round(a * mag) / mag).tolist()


def view_data(job: Job, mesh: Mesh, frames: list[Frame], dat: dict, max_frames: int = 30) -> dict:
    """Surface mesh + per-frame fields in display units for the HTML viewer and PNG plots."""
    tris = mesh.surface_tris
    if mesh.order == 2:        # split each 6-node triangle into four
        t = tris
        sub = np.vstack([t[:, [0, 3, 5]], t[:, [3, 1, 4]], t[:, [5, 4, 2]], t[:, [3, 4, 5]]])
    else:
        sub = tris
    used = np.unique(sub)
    remap = np.zeros(mesh.n_nodes + 1, dtype=np.int64)
    remap[used] = np.arange(len(used))
    idx = used - 1
    sysname = job.system
    lu = U.default_unit("length", sysname)
    lf = U.from_internal(1.0, "length", sysname)
    a = job.analysis
    sel = frames
    if a not in ("modal", "buckling") and len(frames) > max_frames:
        pick = np.unique(np.linspace(0, len(frames) - 1, max_frames).round().astype(int))
        sel = [frames[i] for i in pick]
    if a == "buckling":
        sel = [f for f in frames if f.value != 0.0] or frames
    out_frames = []
    for k, fr in enumerate(sel):
        fields: dict = {}
        disp = None
        if "U" in fr.fields:
            u = fr.fields["U"][idx]
            if a in ("modal", "buckling"):
                peak = np.abs(u).max() or 1.0
                u = u / peak
                fields["Mode shape (normalised)"] = {"unit": "", "values": _r(np.linalg.norm(u, axis=1))}
                disp = u
            else:
                disp = u * lf
                fields[f"Displacement"] = {"unit": lu, "values": _r(np.linalg.norm(disp, axis=1))}
                for c, ax in enumerate("XYZ"):
                    fields[f"Displacement {ax}"] = {"unit": lu, "values": _r(disp[:, c])}
        if "S" in fr.fields and a not in ("modal", "buckling"):
            pu = U.default_unit("pressure", sysname)
            pf = U.from_internal(1.0, "pressure", sysname)
            S = fr.fields["S"][idx]
            fields["von Mises stress"] = {"unit": pu, "values": _r(von_mises(S) * pf)}
            pr = principals(S)
            fields["Max principal stress"] = {"unit": pu, "values": _r(pr[:, 0] * pf)}
            fields["Min principal stress"] = {"unit": pu, "values": _r(pr[:, 2] * pf)}
            for c, nm in enumerate(("XX", "YY", "ZZ")):
                fields[f"Stress {nm}"] = {"unit": pu, "values": _r(S[:, c] * pf)}
        if "T" in fr.fields and job.thermal:
            fields["Temperature"] = {"unit": U.default_unit("temperature", sysname),
                                     "values": _r([U.from_internal(v, "temperature", sysname)
                                                   for v in fr.fields["T"][idx, 0]])}
        if "HFL" in fr.fields:
            fields["Heat flux"] = {"unit": U.default_unit("heat_flux", sysname),
                                   "values": _r(np.linalg.norm(fr.fields["HFL"][idx], axis=1)
                                                * U.from_internal(1.0, "heat_flux", sysname))}
        if "PEEQ" in fr.fields:
            fields["Plastic strain"] = {"unit": "", "values": _r(fr.fields["PEEQ"][idx, 0])}
        if a == "modal":
            fq = dat.get("frequencies", [])
            label = f"Mode {k + 1}: {fq[k]:.5g} Hz" if k < len(fq) else f"Mode {k + 1}"
        elif a == "buckling":
            label = f"Buckling mode {k + 1}: load factor {fr.value:.5g}"
        elif job.transient:
            label = f"t = {fr.value:.5g} s"
        else:
            label = "Final state" if len(sel) == 1 else f"Increment {k + 1} (t = {fr.value:.4g})"
        out_frames.append({"label": label, "value": fr.value,
                           "disp": _r(disp.ravel()) if disp is not None else None, "fields": fields})
    lo, hi = mesh.bbox()
    return {"name": job.name, "title": job.title, "analysis": a, "units": sysname, "length_unit": lu,
            "nodes": _r(mesh.nodes[idx].ravel() * lf, 6), "tris": remap[sub].ravel().tolist(),
            "coarse": remap[tris[:, :3]].ravel().tolist(), "size": float(np.linalg.norm(hi - lo) * lf),
            "mode_like": a in ("modal", "buckling"), "transient": job.transient,
            "frames": out_frames}


def write_view(path: Path, data: dict) -> None:
    Path(path).write_text(json.dumps(data, separators=(",", ":")), encoding="utf-8")
