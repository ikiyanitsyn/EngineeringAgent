"""Design-for-3D-printing checks on a CAD solid.

Tessellates the solid and measures what decides whether a print succeeds:
build-volume fit, overhang/support area, bed contact, wall thickness (by ray
casting), hole sizes and orientation.  Lengths in mm internally.
"""
from __future__ import annotations

from pathlib import Path
from typing import Any

import numpy as np

from .. import materials
from .. import units as U
from .inspect import inspect_shape, load_shape

# Typical process rules (desktop/industrial averages; tune per machine with `overrides`)
PROCESSES: dict[str, dict[str, Any]] = {
    "fdm": dict(name="FDM / FFF (material extrusion)", min_wall=0.8, good_wall=1.2,
                overhang_deg=45.0, supports=True, min_hole=2.0, hole_comp=0.2, layer=0.2,
                build=(250.0, 210.0, 210.0), tolerance="fdm", shell=0.8, default_infill=0.2,
                min_feature=0.8, min_gap=0.3),
    "sla": dict(name="SLA / DLP (vat photopolymerisation)", min_wall=0.5, good_wall=1.0,
                overhang_deg=30.0, supports=True, min_hole=0.8, hole_comp=0.1, layer=0.05,
                build=(145.0, 145.0, 185.0), tolerance="sla", shell=None, default_infill=1.0,
                min_feature=0.3, min_gap=0.3),
    "sls": dict(name="SLS (polymer powder bed fusion)", min_wall=0.7, good_wall=1.0,
                overhang_deg=0.0, supports=False, min_hole=1.5, hole_comp=0.15, layer=0.1,
                build=(300.0, 300.0, 300.0), tolerance="sls", shell=None, default_infill=1.0,
                min_feature=0.6, min_gap=0.5),
    "mjf": dict(name="MJF (multi jet fusion)", min_wall=0.5, good_wall=1.0, overhang_deg=0.0,
                supports=False, min_hole=1.0, hole_comp=0.15, layer=0.08,
                build=(380.0, 284.0, 380.0), tolerance="mjf", shell=None, default_infill=1.0,
                min_feature=0.5, min_gap=0.5),
    "dmls": dict(name="DMLS / SLM (metal powder bed fusion)", min_wall=0.4, good_wall=0.8,
                 overhang_deg=45.0, supports=True, min_hole=1.0, hole_comp=0.1, layer=0.04,
                 build=(250.0, 250.0, 300.0), tolerance="dmls", shell=None, default_infill=1.0,
                 min_feature=0.3, min_gap=0.3),
}
# linear shrinkage guidance (fraction) for scale compensation
SHRINK = {"pla": 0.003, "petg": 0.004, "abs": 0.007, "asa": 0.006, "pc": 0.007, "pa12_sls": 0.0,
          "pa6_cf_fdm": 0.004, "peek": 0.012, "pekk": 0.008, "pei": 0.007, "pp": 0.015}

ORIENTATIONS = {"+Z": np.eye(3),
                "-Z": np.diag([1.0, -1.0, -1.0]),
                "+X": np.array([[0, 0, -1.0], [0, 1, 0], [1, 0, 0]]),
                "-X": np.array([[0, 0, 1.0], [0, 1, 0], [-1, 0, 0]]),
                "+Y": np.array([[1.0, 0, 0], [0, 0, -1], [0, 1, 0]]),
                "-Y": np.array([[1.0, 0, 0], [0, 0, 1], [0, -1, 0]])}


def _tessellate(shape, tol: float) -> tuple[np.ndarray, np.ndarray]:
    verts, tris = shape.tessellate(tol, 0.3)
    v = np.array([[p.X, p.Y, p.Z] for p in verts], dtype=float)
    t = np.array(tris, dtype=np.int64)
    return v, t


def _orient_metrics(v: np.ndarray, t: np.ndarray, R: np.ndarray, rule: dict) -> dict:
    p = v @ R.T
    a, b, c = p[t[:, 0]], p[t[:, 1]], p[t[:, 2]]
    n = np.cross(b - a, c - a)
    area = 0.5 * np.linalg.norm(n, axis=1)
    ok = area > 1e-12
    nz = np.where(ok, n[:, 2] / np.maximum(2 * area, 1e-300), 0.0)
    zc = (a[:, 2] + b[:, 2] + c[:, 2]) / 3
    zmin, zmax = p[:, 2].min(), p[:, 2].max()
    eps = max(1e-3, 1e-4 * (zmax - zmin))
    on_bed = (zc - zmin < eps) & (nz < -0.99)
    lim = np.cos(np.radians(rule["overhang_deg"]))             # angle measured from straight down
    over = (nz < -lim) & ~on_bed if rule["supports"] else np.zeros_like(on_bed)
    size = p.max(axis=0) - p.min(axis=0)
    # support volume estimate: overhang triangles projected down to the bed
    sup_vol = float((area[over] * -nz[over] * (zc[over] - zmin)).sum()) if rule["supports"] else 0.0
    return {"size": size, "bed_area": float(area[on_bed].sum()), "overhang_area": float(area[over].sum()),
            "support_volume": sup_vol, "height": float(zmax - zmin),
            "footprint": float(size[0] * size[1])}


def _wall_thickness(v: np.ndarray, t: np.ndarray, samples: int = 500, seed: int = 0) -> dict:
    """Thickness at sampled surface points: distance along the inward normal to the opposite wall."""
    a, b, c = v[t[:, 0]], v[t[:, 1]], v[t[:, 2]]
    n = np.cross(b - a, c - a)
    area2 = np.linalg.norm(n, axis=1)
    good = area2 > 1e-12
    nu = np.zeros_like(n)
    nu[good] = n[good] / area2[good][:, None]
    rng = np.random.default_rng(seed)
    prob = np.where(good, area2, 0.0)
    prob = prob / prob.sum()
    k = min(samples, int(good.sum()) * 4)
    pick = rng.choice(len(t), size=k, p=prob)
    r1, r2 = np.sqrt(rng.random(k)), rng.random(k)
    pts = (1 - r1)[:, None] * a[pick] + (r1 * (1 - r2))[:, None] * b[pick] + (r1 * r2)[:, None] * c[pick]
    dirs = -nu[pick]
    e1, e2 = b - a, c - a
    thick = np.full(k, np.inf)
    for i in range(k):
        o, d = pts[i] + 1e-6 * dirs[i], dirs[i]
        h = np.cross(d, e2)
        det = np.einsum("ij,ij->i", e1, h)
        m = np.abs(det) > 1e-12
        inv = np.zeros_like(det)
        inv[m] = 1.0 / det[m]
        s = o - a
        u = np.einsum("ij,ij->i", s, h) * inv
        q = np.cross(s, e1)
        w = (q @ d) * inv
        dist = np.einsum("ij,ij->i", e2, q) * inv
        hit = m & (u >= -1e-9) & (w >= -1e-9) & (u + w <= 1 + 1e-9) & (dist > 1e-5)
        hit[pick[i]] = False
        if hit.any():
            thick[i] = dist[hit].min()
    fin = np.isfinite(thick)
    if not fin.any():
        return {"min": None}
    j = int(np.argmin(np.where(fin, thick, np.inf)))
    return {"min": float(thick[j]), "p05": float(np.percentile(thick[fin], 5)),
            "median": float(np.median(thick[fin])), "location": pts[j].tolist(),
            "samples": int(fin.sum()), "values": thick[fin], "areas": None}


def print_check(shape_or_path, process: str = "fdm", material: str | None = None, *,
                orientation: str = "auto", build_volume=None, infill: float | None = None,
                system: str | None = None, overrides: dict | None = None,
                samples: int = 500) -> dict:
    """Check a solid for printability.  Returns facts (mm) and a list of PASS/WARN/FAIL checks."""
    key = process.lower()
    if key not in PROCESSES:
        raise KeyError(f"unknown print process {process!r}; known: {', '.join(PROCESSES)}")
    rule = dict(PROCESSES[key])
    for k, val in (overrides or {}).items():
        if k not in rule:
            raise KeyError(f"unknown override {k!r}; valid: {', '.join(rule)}")
        rule[k] = U.to_internal(val, "length", system) if isinstance(rule[k], float) and \
            k not in ("overhang_deg", "default_infill") else val
    if build_volume is not None:
        rule["build"] = tuple(U.to_internal(x, "length", system) for x in build_volume)
    shape = load_shape(shape_or_path) if isinstance(shape_or_path, (str, Path)) else shape_or_path
    info = inspect_shape(shape)
    diag = float(np.linalg.norm(info["bbox_size"]))
    v, t = _tessellate(shape, max(0.01, diag / 2000))

    cands = {name: _orient_metrics(v, t, R, rule) for name, R in ORIENTATIONS.items()}
    def fits(m):
        return all(s <= b + 1e-6 for s, b in zip(sorted(m["size"][:2]), sorted(rule["build"][:2]))) \
            and m["size"][2] <= rule["build"][2] + 1e-6
    def score(m):
        return (0 if fits(m) else 1, m["support_volume"] / max(info["volume"], 1e-9)
                - 0.3 * m["bed_area"] / max(m["footprint"], 1e-9) + 0.02 * m["height"] / max(diag, 1e-9))
    best = min(cands, key=lambda k_: score(cands[k_]))
    chosen = best if orientation == "auto" else orientation
    if chosen not in cands:
        raise ValueError(f"orientation must be 'auto' or one of {', '.join(ORIENTATIONS)}")
    m = cands[chosen]
    wt = _wall_thickness(v, t, samples)

    checks: list[dict] = []
    def add(name, status, detail):
        checks.append({"name": name, "status": status, "detail": detail})
    f = lambda x, kind="length": U.fmt(x, kind, system)  # noqa: E731
    add("Geometry is a valid closed solid", "PASS" if info["valid"] and info["solids"] >= 1 else "FAIL",
        f"{info['solids']} solid(s), valid = {info['valid']}")
    if info["solids"] > 1:
        add("Single body", "WARN", f"{info['solids']} separate solids: print as an assembly or fuse them")
    add("Fits the build volume", "PASS" if fits(m) else "FAIL",
        f"part {U.fmt_vec(m['size'], 'length', system)} vs build {U.fmt_vec(rule['build'], 'length', system)}"
        + ("" if fits(m) else "; split the part or use a larger machine"))
    if wt["min"] is not None:
        st = "FAIL" if wt["min"] < rule["min_wall"] * 0.98 else ("WARN" if wt["min"] < rule["good_wall"] * 0.98 else "PASS")
        frac = float((wt["values"] < rule["min_wall"] * 0.98).mean())
        add(f"Wall thickness >= {f(rule['min_wall'])}", st,
            f"thinnest sampled wall {f(wt['min'])} at {U.fmt_vec(wt['location'], 'length', system)}; "
            f"5th percentile {f(wt['p05'])}, median {f(wt['median'])}"
            + (f"; {frac * 100:.0f} % of the surface is below the minimum" if st == "FAIL" else "")
            + (f"; recommended >= {f(rule['good_wall'])} for strength" if st == "WARN" else ""))
    if rule["supports"]:
        ratio = m["overhang_area"] / max(info["area"], 1e-9)
        st = "PASS" if ratio < 0.02 else ("WARN" if ratio < 0.25 else "WARN")
        add(f"Overhangs beyond {rule['overhang_deg']:g} deg from vertical", st,
            f"{f(m['overhang_area'], 'area')} needs support ({ratio * 100:.1f} % of the surface), "
            f"about {f(m['support_volume'], 'volume')} of support material in orientation {chosen}")
    else:
        add("Supports", "PASS", "powder-bed process: no support structures needed; leave powder escape holes "
            "in hollow sections")
    bed_ratio = m["bed_area"] / max(m["footprint"], 1e-9)
    if key in ("fdm", "sla", "dmls"):
        st = "PASS" if m["bed_area"] > 0 and (m["height"] / max(np.sqrt(max(m["bed_area"], 1e-9)), 1e-9)) < 6 else "WARN"
        add("Bed contact and stability", st,
            f"flat contact area {f(m['bed_area'], 'area')} ({bed_ratio * 100:.0f} % of the footprint), "
            f"height {f(m['height'])}" + ("" if st == "PASS" else
                                           "; tall or small-footprint part: add a brim/raft or re-orient"))
    R = ORIENTATIONS[chosen]
    holes = []
    try:
        from build123d import GeomType
        for face in shape.faces():
            if face.geom_type != GeomType.CYLINDER:
                continue
            d = 2 * float(face.radius)
            ax = np.array(tuple(face.axis_of_rotation.direction)) @ R.T
            holes.append((round(d, 3), "vertical" if abs(ax[2]) > 0.9 else ("horizontal" if abs(ax[2]) < 0.1 else "inclined")))
    except Exception:
        pass
    hole_rows = sorted(set(holes))
    small = [h for h in hole_rows if h[0] < rule["min_hole"]]
    if hole_rows:
        add(f"Hole / cylinder diameters >= {f(rule['min_hole'])}", "WARN" if small else "PASS",
            ", ".join(f"dia {f(d)} ({o})" for d, o in hole_rows[:10])
            + (f"; {len(small)} below the minimum will close up - drill after printing" if small else "")
            + (f"; expect holes about {f(rule['hole_comp'])} undersize: model them oversize or ream"
               if rule["hole_comp"] else ""))
        big_h = [h for h in hole_rows if h[1] == "horizontal" and h[0] > 8 and rule["supports"]]
        if big_h:
            add("Horizontal holes", "WARN", f"{len(big_h)} horizontal hole(s) over 8 mm sag at the top: "
                f"use a teardrop profile or accept supports")
    cap = None
    try:
        from ..gdt.general import process_capability
        cap = process_capability(rule["tolerance"], max(m["size"]), "metric")
        add("Expected dimensional accuracy", "INFO",
            f"about +/-{f(cap['typical'])} on the largest dimension ({cap['grade']}); {cap['note']}")
    except Exception:
        pass
    out = {"process": key, "process_name": rule["name"], "orientation": chosen, "best_orientation": best,
           "orientations": {k_: {"support_volume": c["support_volume"], "overhang_area": c["overhang_area"],
                                 "bed_area": c["bed_area"], "height": c["height"], "fits": bool(fits(c))}
                            for k_, c in cands.items()},
           "size": m["size"].tolist(), "volume": info["volume"], "area": info["area"],
           "min_wall": wt["min"], "wall_p05": wt.get("p05"), "wall_location": wt.get("location"),
           "overhang_area": m["overhang_area"], "support_volume": m["support_volume"],
           "bed_area": m["bed_area"], "holes": hole_rows, "rules": {k_: rule[k_] for k_ in
                                                                   ("min_wall", "good_wall", "overhang_deg", "min_hole", "hole_comp", "layer")},
           "build_volume": list(rule["build"]), "checks": checks}
    if material:
        mat = materials.get(material)
        rho = mat.get("density")
        if rho:
            inf = rule["default_infill"] if infill is None else float(infill)
            if rule["shell"]:
                shell_v = min(info["volume"], info["area"] * rule["shell"])
                solid_frac = (shell_v + inf * (info["volume"] - shell_v)) / info["volume"]
            else:
                solid_frac = 1.0
            mass = info["volume"] * solid_frac * rho
            out.update(material=mat.key, infill=inf, mass=mass, mass_solid=info["volume"] * rho)
            if key == "fdm":
                out["filament_length_1p75"] = info["volume"] * solid_frac / (np.pi * 0.875**2)
        sh = SHRINK.get(mat.key)
        if sh:
            out["shrink_scale"] = 1 + sh
            add("Shrinkage compensation", "INFO",
                f"{mat.name}: typical linear shrinkage {sh * 100:.1f} % - scale the export by "
                f"{1 + sh:.4f} if the slicer does not compensate")
        tmax = mat.get("T_max_service")
        if tmax is not None:
            add("Service temperature", "INFO", f"{mat.name} is usable to about "
                f"{U.fmt(tmax, 'temperature', system)}")
        if mat.meta.get("note"):
            add("Material anisotropy", "INFO", str(mat.meta["note"]))
    worst = "FAIL" if any(c["status"] == "FAIL" for c in checks) else \
        ("WARN" if any(c["status"] == "WARN" for c in checks) else "PASS")
    out["status"] = worst
    if orientation == "auto" or chosen != best:
        out["orientation_note"] = (f"Print with the model's {chosen} axis pointing up."
                                   + ("" if chosen == best else f" Orientation {best} would need less support."))
    return out
