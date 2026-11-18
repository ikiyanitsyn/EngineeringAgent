"""Stage 2 of 'join my two parts': design a flat adapter plate between two hole patterns.

Part A (e.g. a robot tool flange) sits under the plate, part B (e.g. a camera) on top. Screws into A
come from the top of the plate, screws into B from the bottom, each in a counterbore. The design is
deterministic (no AI): it searches the rotation (and, only if needed, a sideways offset) of B that

* keeps every hole and counterbore clear of the others, and
* leaves one set of screws reachable after the first part is mounted (assembly order),

then builds the plate, the assembly, a bill of screws and the checks. When no flat plate works it says
so and why, instead of producing a part that cannot be assembled.
"""
from __future__ import annotations

import math
from pathlib import Path

import numpy as np

# ISO 4762 socket head cap screw: (clearance medium, head diameter, head height) and counterbore size
SHCS = {"M3": (3.4, 5.5, 3.0), "M4": (4.5, 7.0, 4.0), "M5": (5.5, 8.5, 5.0), "M6": (6.6, 10.0, 6.0),
        "M8": (9.0, 13.0, 8.0), "M10": (11.0, 16.0, 10.0)}
LENGTHS = (6, 8, 10, 12, 16, 20, 25, 30, 35, 40, 45, 50, 60)


def _face(feat: dict, fid: str) -> dict:
    for f in feat["faces"]:
        if f["id"].upper() == fid.upper():
            return f
    raise ValueError(f"there is no face {fid} (faces: {', '.join(f['id'] for f in feat['faces'])})")


def _pattern(face: dict) -> dict:
    pats = [h for h in face["holes"] if h["count"] >= 2 and not h["screw"].startswith("bore")]
    if not pats:
        raise ValueError(f"face {face['id']} has no screw hole pattern to bolt to")
    return max(pats, key=lambda h: h["count"])


def _pts2d(face: dict, pat: dict) -> tuple[np.ndarray, np.ndarray]:
    """Hole centres in the face's own (u, v) axes, centred on the pattern; and the pattern centre (3D)."""
    c3 = np.array(pat["centres"], float)
    ctr = c3.mean(axis=0)
    u, v = np.array(face["u"]), np.array(face["v"])
    return np.array([[(p - ctr) @ u, (p - ctr) @ v] for p in c3]), ctr


def _covers(face_obj, point3) -> bool:
    """True when this face has material at the point (so a screw head there would be buried)."""
    from build123d import Vector
    try:
        return bool(face_obj.is_inside(Vector(*point3), tolerance=0.05))
    except Exception:
        return False


def plan(step_a, fid_a, step_b, fid_b, screw_a="M6", screw_b="M6", max_offset=60.0) -> dict:
    """Search a feasible layout. Returns {'ok', 'theta', 'offset', 'why', ...}."""
    from .features import mount_features
    from .inspect import load_shape
    fa_all, fb_all = mount_features(step_a), mount_features(step_b)
    fa, fb = _face(fa_all, fid_a), _face(fb_all, fid_b)
    pa, ca = _pts2d(fa, _pattern(fa))
    pb, cb = _pts2d(fb, _pattern(fb))
    pb[:, 1] *= -1                                    # B faces down onto the plate: its picture is mirrored
    shape_a, shape_b = load_shape(step_a), load_shape(step_b)
    face_a = _nearest_face(shape_a, fa)
    face_b = _nearest_face(shape_b, fb)
    ua, va, na = map(np.array, (fa["u"], fa["v"], fa["normal"]))
    ub, vb = np.array(fb["u"]), -np.array(fb["v"])
    da, Da = SHCS[screw_a][0], SHCS[screw_a][1] + 1.0
    db, Db = SHCS[screw_b][0], SHCS[screw_b][1] + 1.0
    need = max(Da / 2 + db / 2, Db / 2 + da / 2) + 1.5   # counterbore of one set vs through hole of the other

    def layout(theta, off):
        c, s = math.cos(theta), math.sin(theta)
        R = np.array([[c, -s], [s, c]])
        qb = pb @ R.T + off
        gap = min(np.linalg.norm(x - y) for x in pa for y in qb)
        # A screws (from the top) are buried if B's face covers them; B screws (from below) if A's does
        # a screw is reachable only if its whole head (and the tool) passes: test the head circle, not its centre
        ring = [np.zeros(2)] + [np.array([math.cos(k * math.pi / 6), math.sin(k * math.pi / 6)]) for k in range(12)]
        a_free = not any(_covers(face_b, cb + _to_b(x + 0.5 * Da * r, theta, off, ub, vb)) for x in pa for r in ring)
        b_free = not any(_covers(face_a, ca + (q[0] + 0.5 * Db * r[0]) * ua + (q[1] + 0.5 * Db * r[1]) * va)
                         for q in qb for r in ring)
        return qb, gap, a_free, b_free

    best = None
    offsets = [np.zeros(2)] + [r * np.array([math.cos(a), math.sin(a)])
                               for r in np.arange(4.0, max_offset + 0.1, 4.0)
                               for a in np.radians(np.arange(0, 360, 45))]
    for off in offsets:
        for deg in range(0, 360, 15):
            qb, gap, a_free, b_free = layout(math.radians(deg), off)
            if gap >= need and (a_free or b_free):
                best = (deg, off, qb, gap, a_free, b_free)
                break
        if best:
            break
    centred = layout(0.0, np.zeros(2))
    out = {"screw_a": screw_a, "screw_b": screw_b, "need_gap": need, "pa": pa.tolist(),
           "centred": {"gap": centred[1], "a_free": centred[2], "b_free": centred[3]},
           "fa": fa, "fb": fb, "ca": ca.tolist(), "cb": cb.tolist()}
    if not best:
        out.update(ok=False, why=("no rotation or sideways offset up to "
                                  f"{max_offset:g} mm lets the screws be reached and the holes clear each other"))
        return out
    deg, off, qb, gap, a_free, b_free = best
    out.update(ok=True, theta=deg, offset=[float(off[0]), float(off[1])], pb=qb.tolist(), gap=gap,
               order=("first bolt the plate to part A from the top, then part B from below" if b_free else
                      "first bolt part B to the plate from below, then the plate to part A from the top"))
    return out


def _to_b(x2, theta, off, ub, vb):
    """Plate 2D point -> offset from B's pattern centre in 3D (B's frame)."""
    c, s = math.cos(-theta), math.sin(-theta)
    q = np.array(x2) - off
    q = np.array([c * q[0] - s * q[1], s * q[0] + c * q[1]])
    return q[0] * ub + q[1] * vb


def _nearest_face(shape, f):
    c = np.array(f["centre"])
    best, bd = None, 1e30
    for face in shape.faces():
        if "PLANE" not in str(face.geom_type):
            continue
        d = np.linalg.norm(np.array(tuple(face.center())) - c) + abs(face.area - f["area"])
        if d < bd:
            best, bd = face, d
    return best


def build(p: dict, folder: str | Path, step_a, step_b, thickness: float | None = None) -> dict:
    """Plate STEP + assembly STEP + screw list for a feasible plan."""
    from build123d import Align, Box, Compound, Cylinder, Location, Plane, Pos, Vector, export_step, fillet, Axis
    from .inspect import load_shape
    folder = Path(folder)
    sa, sb = p["screw_a"], p["screw_b"]
    da, Da, ha = SHCS[sa][0], SHCS[sa][1] + 1.0, SHCS[sa][2] + 0.5
    db, Db, hb = SHCS[sb][0], SHCS[sb][1] + 1.0, SHCS[sb][2] + 0.5
    t = thickness or math.ceil(max(ha, hb) + 4.0)
    pa, pb = np.array(p["pa"]), np.array(p["pb"])
    allp = np.vstack([pa, pb])
    m = max(Da, Db) / 2 + 4.0
    lo, hi = allp.min(axis=0) - m, allp.max(axis=0) + m
    w, l = hi - lo
    plate = Pos((lo[0] + hi[0]) / 2, (lo[1] + hi[1]) / 2, 0) * Box(w, l, t, align=(Align.CENTER, Align.CENTER, Align.MIN))
    plate = fillet(plate.edges().filter_by(Axis.Z), min(m - 0.5, 6.0))
    for x, y in pa:                                   # into A: through hole, counterbore from the top
        plate -= Pos(x, y, -1) * Cylinder(da / 2, t + 2, align=(Align.CENTER, Align.CENTER, Align.MIN))
        plate -= Pos(x, y, t - ha) * Cylinder(Da / 2, ha + 1, align=(Align.CENTER, Align.CENTER, Align.MIN))
    for x, y in pb:                                   # into B: through hole, counterbore from below
        plate -= Pos(x, y, -1) * Cylinder(db / 2, t + 2, align=(Align.CENTER, Align.CENTER, Align.MIN))
        plate -= Pos(x, y, -1) * Cylinder(Db / 2, hb + 1, align=(Align.CENTER, Align.CENTER, Align.MIN))
    export_step(plate, folder / "adapter.step")
    # place the two parts: A's mounting face on the plate's underside, B's on its top
    fa, fb = p["fa"], p["fb"]
    # local frames: A's pattern centre at the origin, its face on z=0 with A below; B's on z=t with B above
    la = Plane(origin=Vector(*p["ca"]), x_dir=Vector(*fa["u"]), z_dir=Vector(*fa["normal"])).location
    part_a = la.inverse() * load_shape(step_a)
    lb = Plane(origin=Vector(*p["cb"]), x_dir=Vector(*fb["u"]), z_dir=Vector(*[-x for x in fb["normal"]])).location
    part_b = Pos(p["offset"][0], p["offset"][1], t) * (Location((0, 0, 0), (0, 0, p["theta"]))
                                                       * (lb.inverse() * load_shape(step_b)))
    export_step(Compound([part_a, plate, part_b]), folder / "assembly.step")
    def length(screw, grip, hole_depth):
        """Longest standard length that still stops 1 mm short of the bottom of the threaded hole, and the
        thread engagement it gives (aim: 1.5 x d in aluminium, at least 1 x d)."""
        d = float(screw[1:])
        fits = [L for L in LENGTHS if L - grip <= hole_depth - 1.0]
        L = max(fits) if fits else LENGTHS[0]
        e = L - grip
        note = "" if e >= 1.5 * d else (f" - only {e:.3g} mm of thread engaged ({e / d:.2g} x d)"
                                        + (": add a washer or a deeper hole" if e < d else ""))
        return L, note
    ga, gb = t - ha, t - hb                           # material under each counterbore = screw grip
    la_len, na = length(sa, ga, _pattern(p["fa"]).get("depth", 99))
    lb_len, nb = length(sb, gb, _pattern(p["fb"]).get("depth", 99))
    screws = [f"{len(pa)} x ISO 4762 {sa} x {la_len} (plate to part A, counterbored from the top){na}",
              f"{len(pb)} x ISO 4762 {sb} x {lb_len} (part B to plate, counterbored from below){nb}"]
    info = {"plate": str(folder / "adapter.step"), "assembly": str(folder / "assembly.step"),
            "thickness": t, "size": [float(w), float(l)], "screws": screws,
            "holes_a": pa.tolist(), "holes_b": pb.tolist(), "clear_a": da, "clear_b": db,
            "screw_a": sa, "screw_b": sb}
    import json
    (folder / "adapter.json").write_text(json.dumps(info, indent=1), encoding="utf-8")
    return info


def fea_request(folder, material: str, mass_kg: float, g_factor: float) -> str:
    """`ea analyze` lines checking the plate: held at the screws into part A, part B's weight times the
    acceleration pulling on its screws (along the plate normal - the worst case for bending), with an
    order-of-magnitude hand check: the plate as a cantilever between the two hole-group centres. The
    screws are spread out, so the true lever is shorter or longer - the estimate is not one-sided.)"""
    import json
    info = json.loads((Path(folder) / "adapter.json").read_text())
    t = info["thickness"]
    sel = lambda pts, d: "+".join(f"hole:{d:g}@{x:.4g},{y:.4g},{t / 2:.4g}" for x, y in pts)   # noqa: E731
    F = mass_kg * 9.80665 * g_factor
    ca, cb = np.mean(info["holes_a"], axis=0), np.mean(info["holes_b"], axis=0)
    L = max(float(np.linalg.norm(cb - ca)), t)
    b = min(info["size"])
    rel = str(Path(folder) / "adapter.step")
    from .. import materials
    E = materials.get(material, "metric").get("E")
    return (f'ea analyze {rel} -m {material} --fix {sel(info["holes_a"], info["clear_a"])} '
            f'--force {sel(info["holes_b"], info["clear_b"])} 0,0,{-F:.4g} --sf 2 --name "adapter check" '
            f'--bound "beam.cantilever_end_load P={F:.4g} L={L:.4g} E={E:g}MPa b={b:.4g} h={t:g} order"')


def report_lines(p: dict, b: dict | None) -> list[str]:
    if not p["ok"]:
        c = p["centred"]
        why = []
        if not c["a_free"]:
            why.append(f"the {p['screw_a']} screws into part A would sit under part B")
        if not c["b_free"]:
            why.append(f"the {p['screw_b']} screws into part B would sit on part A's face")
        return [f"**A flat adapter plate cannot be assembled here:** {p['why']}."
                + (" Centred, " + " and ".join(why) + "." if why else ""),
                "Options: a spacer or 'cup' adapter with side windows to reach the screws, a plate with an "
                "offset (allow a larger offset), or screws into part B from its top if it allows. Tell me which."]
    lines = [f"**Adapter plate:** {b['size'][0]:.4g} x {b['size'][1]:.4g} x {b['thickness']:g} mm, part B turned "
             f"{p['theta']}°" + (f" and shifted {math.hypot(*p['offset']):.3g} mm sideways (so the screws can be "
                                    f"reached - this moves the camera's centre of mass)" if any(p["offset"]) else "")
             + ".",
             f"**Assembly order:** {p['order']}.",
             f"**Screws:** " + "; ".join(b["screws"]) + ".",
             f"**Clearances:** closest hole-to-hole {p['gap']:.3g} mm (needs {p['need_gap']:.3g} mm so a counterbore "
             f"never cuts into a neighbouring hole); ISO 273 medium clearance holes; counterbores for ISO 4762 heads."]
    return lines


def picture(assembly_step, path, title: str = "Adapter assembly") -> Path:
    """Two views of the assembly: part A grey, adapter orange, part B blue."""
    from build123d import import_step
    from mpl_toolkits.mplot3d.art3d import Poly3DCollection
    from ..report.plots import _mpl
    plt = _mpl()
    solids = sorted(import_step(str(assembly_step)).solids(), key=lambda s: s.bounding_box().min.Z)
    cols = [(0.62, 0.64, 0.68), (0.95, 0.55, 0.20), (0.35, 0.55, 0.85)]
    polys = []
    allp = []
    for s, col in zip(solids, cols):
        bb = s.bounding_box()
        v, t = s.tessellate(max(bb.diagonal / 300, 0.05), math.radians(15))
        pts = np.array([tuple(x) for x in v], float)
        tri = pts[np.array(t, int)]
        n = np.cross(tri[:, 1] - tri[:, 0], tri[:, 2] - tri[:, 0])
        n /= np.maximum(np.linalg.norm(n, axis=1), 1e-30)[:, None]
        shade = 0.5 + 0.5 * np.abs(n @ (np.array([0.35, -0.5, 0.8]) / np.linalg.norm([0.35, -0.5, 0.8])))
        fc = np.column_stack([np.outer(shade, col), np.ones_like(shade)])
        polys.append((tri, fc))
        allp.append(pts)
    allp = np.vstack(allp)
    lo, hi = allp.min(axis=0), allp.max(axis=0)
    ext = np.maximum(hi - lo, 1e-3)
    c = (lo + hi) / 2
    fig = plt.figure(figsize=(8.4, 4.2), dpi=110)
    for k, (elev, azim, name) in enumerate(((22, -55, "from above"), (-22, 125, "from below"))):
        ax = fig.add_subplot(1, 2, k + 1, projection="3d")
        for tri, fc in polys:
            ax.add_collection3d(Poly3DCollection(tri, facecolors=fc, edgecolors="none"))
        ax.set_xlim(c[0] - ext[0] / 2, c[0] + ext[0] / 2)
        ax.set_ylim(c[1] - ext[1] / 2, c[1] + ext[1] / 2)
        ax.set_zlim(c[2] - ext[2] / 2, c[2] + ext[2] / 2)
        try:
            ax.set_box_aspect(tuple(ext), zoom=1.05)
        except TypeError:
            ax.set_box_aspect(tuple(ext))
        ax.view_init(elev=elev, azim=azim)
        ax.set_axis_off()
        ax.set_title(name, fontsize=9)
    fig.suptitle(title, fontsize=11)
    fig.text(0.5, 0.02, "grey = part A, orange = adapter plate, blue = part B", ha="center", fontsize=8, color="#555")
    fig.savefig(path, bbox_inches="tight", facecolor="white")
    plt.close(fig)
    return Path(path)
