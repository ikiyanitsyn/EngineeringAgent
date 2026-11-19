"""Mounting features of a CAD part: its main flat faces and the hole patterns on them.

Used when the user brings their own parts (e.g. a robot-arm flange and a camera) and asks for an
adapter: the bot lists numbered faces and hole patterns (with a labelled picture) so the user can say
"join arm F2 to camera F4" instead of pointing in a CAD program. Geometry is measured, never guessed.
"""
from __future__ import annotations

import math
from pathlib import Path

import numpy as np

# ISO metric screws: tap drill (coarse thread), nominal, and ISO 273 clearance (fine / medium / coarse)
SCREWS = {
    "M2": (1.6, 2.0, (2.2, 2.4, 2.6)), "M2.5": (2.05, 2.5, (2.7, 2.9, 3.1)), "M3": (2.5, 3.0, (3.2, 3.4, 3.6)),
    "M4": (3.3, 4.0, (4.3, 4.5, 4.8)), "M5": (4.2, 5.0, (5.3, 5.5, 5.8)), "M6": (5.0, 6.0, (6.4, 6.6, 7.0)),
    "M8": (6.8, 8.0, (8.4, 9.0, 10.0)), "M10": (8.5, 10.0, (10.5, 11.0, 12.0)),
    "M12": (10.2, 12.0, (13.0, 13.5, 14.5)),
}


def screw_for(d: float) -> str:
    """ISO metric screw(s) a hole of diameter d (mm) fits. Ambiguous sizes (a 5.0 mm hole is an M6 tap
    drill AND an M5 at nominal size) list both, so the user confirms instead of the tool guessing."""
    if d > 14:
        return f"bore {d:.4g} mm"
    hits = []
    for name, (tap, nom, clear) in SCREWS.items():
        for kind, v in [("tapped", tap), ("at nominal size", nom)] + \
                       [(f"clearance, {w}", c) for w, c in zip(("fine", "medium", "coarse"), clear)]:
            if abs(d - v) <= 0.15:
                hits.append((abs(d - v), f"{name} {kind}"))
    if not hits:
        return "no standard metric screw matches"
    hits.sort()
    close = [h for e, h in hits if e <= hits[0][0] + 0.05]
    return " or ".join(dict.fromkeys(close[:3]))


def _pattern(pts: np.ndarray) -> str:
    n = len(pts)
    if n == 1:
        return "single hole"
    if n == 2:
        return f"2 holes {np.linalg.norm(pts[0] - pts[1]):.4g} mm apart"
    c = pts.mean(axis=0)
    r = np.linalg.norm(pts - c, axis=1)
    on_circle = n >= 3 and r.max() - r.min() < 0.01 * max(r.mean(), 1e-9) + 0.02
    # rectangle test in the pattern's own axes (works for a square rotated 45 degrees too)
    rect = None
    if n == 4:
        dd = sorted(np.linalg.norm(pts[i] - pts[j]) for i in range(4) for j in range(i + 1, 4))
        a, b = dd[0], dd[2]
        if abs(dd[0] - dd[1]) < 0.02 and abs(dd[2] - dd[3]) < 0.02 and abs(math.hypot(a, b) - dd[4]) < 0.02:
            if abs(a - b) > 0.02:                      # a true rectangle: describe it as one
                return f"4 holes in a {a:.4g} x {b:.4g} mm rectangle"
            rect = f"{a:.4g} x {b:.4g} mm square"
    if on_circle:
        return f"{n} holes on a {2 * r.mean():.4g} mm bolt circle" + (f" ({rect})" if rect else "")
    return f"4 holes in a {rect}" if rect else f"{n} holes"


def _holes(shape) -> list[dict]:
    """Every round hole: {'point', 'dir', 'diameter', 'span'} (half-cylinders merged)."""
    holes = []                                   # one entry per hole (half-cylinders merged)
    for f in shape.faces():
        if "CYLINDER" not in str(f.geom_type):
            continue
        try:
            if not f.is_circular_concave:
                continue
            ax = f.axis_of_rotation
        except Exception:
            continue
        d = np.array(tuple(ax.direction), float)
        d /= np.linalg.norm(d)
        p = np.array(tuple(ax.position), float)
        dia = 2 * float(f.radius)
        vs = np.array([tuple(v) for v in f.vertices()], float) if f.vertices() else np.zeros((1, 3))
        span = (float((vs @ d).min()), float((vs @ d).max()))   # extent along the axis (hole depth)
        for h in holes:
            q = p - h["point"]
            if abs(abs(d @ h["dir"]) - 1) < 1e-6 and np.linalg.norm(q - (q @ h["dir"]) * h["dir"]) < 1e-4 \
                    and abs(h["diameter"] - dia) < 1e-4:
                s0 = sorted((span[0], span[1]) if d @ h["dir"] > 0 else (-span[1], -span[0]))
                h["span"] = (min(h["span"][0], s0[0]), max(h["span"][1], s0[1]))
                break
        else:
            holes.append({"point": p, "dir": d, "diameter": dia, "span": span})
    return holes


def hole_summary(shape) -> list[dict]:
    """[{'diameter', 'count', 'depth', 'through'}] grouped by size and depth - shows blind vs through holes."""
    bb = shape.bounding_box()
    lo, hi = np.array(tuple(bb.min), float), np.array(tuple(bb.max), float)
    corners = np.array([[x, y, z] for x in (lo[0], hi[0]) for y in (lo[1], hi[1]) for z in (lo[2], hi[2])])
    groups: dict[tuple, int] = {}
    for h in _holes(shape):
        depth = h["span"][1] - h["span"][0]
        extent = float((corners @ h["dir"]).max() - (corners @ h["dir"]).min())
        through = depth >= extent - 1e-3 or _open_both_ends(shape, h)
        k = (round(h["diameter"], 2), round(depth, 2), through)
        groups[k] = groups.get(k, 0) + 1
    return [{"diameter": d, "count": n, "depth": dep, "through": t} for (d, dep, t), n in sorted(groups.items())]


def _open_both_ends(shape, h) -> bool:
    """A hole through a flange of a larger part: the solid is absent just beyond both ends of the bore."""
    from build123d import Vector
    out = []
    for z, sgn in ((h["span"][0], -1), (h["span"][1], 1)):
        q = h["point"] + h["dir"] * (z - h["point"] @ h["dir"] + sgn * 0.05)   # span is absolute
        try:
            out.append(not shape.is_inside(Vector(*q)))
        except Exception:
            return False
    return all(out)


def mount_features(step: str | Path, max_faces: int = 8) -> dict:
    """{'faces': [{id, area, centre, normal, size, holes, pattern, screws}], 'bbox', 'holes'}."""
    from .inspect import load_shape
    shape = load_shape(step)
    holes = _holes(shape)
    planes = []
    for f in shape.faces():
        if "PLANE" not in str(f.geom_type):
            continue
        c = np.array(tuple(f.center()), float)
        n = np.array(tuple(f.normal_at(f.center())), float)
        bb = f.bounding_box()
        planes.append({"face": f, "area": float(f.area), "centre": c, "normal": n / np.linalg.norm(n),
                       "bbox": (np.array(tuple(bb.min)), np.array(tuple(bb.max)))})
    planes.sort(key=lambda q: -q["area"])
    if planes:                                   # drop slivers and blind-hole floors
        planes = [q for q in planes if q["area"] >= 0.03 * planes[0]["area"]]
    out = []
    for i, pl in enumerate(planes[:max_faces], 1):
        n, c = pl["normal"], pl["centre"]
        lo, hi = pl["bbox"]
        u = np.cross(n, [0, 0, 1] if abs(n[2]) < 0.9 else [1, 0, 0])
        u /= np.linalg.norm(u)
        v = np.cross(n, u)
        on = []
        for h in holes:
            if abs(abs(h["dir"] @ n) - 1) > 1e-3:
                continue
            t = (c - h["point"]) @ n / (h["dir"] @ n)
            hit = h["point"] + t * h["dir"]               # where the hole axis meets this face's plane
            if np.all(hit >= lo - 1e-3) and np.all(hit <= hi + 1e-3) and _hole_opens_on(pl["face"], hit, h):
                on.append((hit, h["diameter"], h["span"][1] - h["span"][0]))
        groups: dict[float, list] = {}
        depth: dict[float, float] = {}
        for hit, dia, dep in on:
            groups.setdefault(round(dia, 3), []).append(hit)
            depth[round(dia, 3)] = min(depth.get(round(dia, 3), 1e9), dep)
        pats = []
        for dia, hits in sorted(groups.items()):
            pts2 = np.array([[(x - c) @ u, (x - c) @ v] for x in hits])
            pats.append({"diameter": dia, "count": len(hits), "screw": screw_for(dia), "depth": round(depth[dia], 3),
                         "pattern": _pattern(pts2), "centres": [list(map(float, x)) for x in hits]})
        ext = hi - lo
        size = sorted((float(e) for e in ext), reverse=True)[:2]
        try:                                      # a point ON the face (the centre of a ring is in its hole)
            fv, ft = pl["face"].tessellate(max(float(np.linalg.norm(hi - lo)) / 50, 0.05))
            fv = np.array([tuple(x) for x in fv], float)
            cents = fv[np.array(ft, int)].mean(axis=1)
            label = cents[np.argmin(np.linalg.norm(cents - c, axis=1))]
        except Exception:
            label = c
        out.append({"id": f"F{i}", "area": pl["area"], "centre": [float(x) for x in c],
                    "u": [float(x) for x in u], "v": [float(x) for x in v],
                    "label_at": [float(x) for x in label],
                    "normal": [round(float(x), 4) for x in n], "size": size, "holes": pats,
                    "selector": "near:" + ",".join(f"{x:.4g}" for x in c)})
    bb = shape.bounding_box()
    return {"file": str(step), "faces": out, "hole_count": len(holes),
            "bbox": [list(map(float, tuple(bb.min))), list(map(float, tuple(bb.max)))]}


def _hole_opens_on(face, hit: np.ndarray, hole: dict) -> bool:
    """True when the hole really breaks through this face (its rim lies on the face's edge set)."""
    from build123d import Vector
    try:
        r = hole["diameter"] / 2
        for e in face.edges():
            if "CIRCLE" in str(e.geom_type) and abs(e.radius - r) < 1e-4 and \
                    (Vector(*hit) - e.arc_center).length < 1e-3:
                return True
    except Exception:
        return True
    return False


def describe(feat: dict, part: str = "") -> list[str]:
    head = f"**{part}**" if part else Path(feat["file"]).name
    lo, hi = feat["bbox"]
    lines = [f"{head}: {hi[0] - lo[0]:.4g} x {hi[1] - lo[1]:.4g} x {hi[2] - lo[2]:.4g} mm, "
             f"{feat['hole_count']} holes"]
    for f in feat["faces"]:
        n = f["normal"]
        facing = max(range(3), key=lambda k: abs(n[k]))
        dirn = ("+" if n[facing] > 0 else "-") + "XYZ"[facing]
        holes = "; ".join((f"{h['screw']}" if h["screw"].startswith("bore") else
                           f"{h['pattern']}, {h['diameter']:.4g} mm ({h['screw']})") for h in f["holes"])
        lines.append(f"- **{f['id']}** flat face {f['size'][0]:.4g} x {f['size'][1]:.4g} mm facing {dirn}"
                     + (f" - {holes}" if holes else ""))
    return lines


def picture(step: str | Path, feat: dict, path: str | Path, title: str = "") -> Path:
    """Shaded picture of the part with the face numbers (F1, F2, ...) written on the faces."""
    from ..report.plots import _mpl
    from .inspect import load_shape
    from mpl_toolkits.mplot3d.art3d import Poly3DCollection
    plt = _mpl()
    shape = load_shape(step)
    lo, hi = np.array(feat["bbox"][0]), np.array(feat["bbox"][1])
    tol = max(float(np.linalg.norm(hi - lo)) / 400, 0.01)
    verts, tris = shape.tessellate(tol, math.radians(15))
    pts = np.array([tuple(v) for v in verts], float)
    tri = np.array(tris, int)
    p = pts[tri]
    nrm = np.cross(p[:, 1] - p[:, 0], p[:, 2] - p[:, 0])
    nrm /= np.maximum(np.linalg.norm(nrm, axis=1), 1e-30)[:, None]
    light = np.array([0.35, -0.5, 0.8]) / np.linalg.norm([0.35, -0.5, 0.8])
    shade = 0.45 + 0.5 * np.abs(nrm @ light)
    fc = np.column_stack([0.62 * shade, 0.70 * shade, 0.80 * shade, np.ones_like(shade)])
    fig = plt.figure(figsize=(8.4, 4.2), dpi=110)
    ext = np.maximum(hi - lo, 0.04 * float((hi - lo).max()))
    c = (lo + hi) / 2
    off = 0.04 * float((hi - lo).max())
    views = ((28, -55, "front, from above"), (-28, 125, "back, from below"))   # together: all six sides
    for k, (elev, azim, name) in enumerate(views):
        ax = fig.add_subplot(1, 2, k + 1, projection="3d")
        ax.add_collection3d(Poly3DCollection(p, facecolors=fc, edgecolors="none"))
        ax.set_xlim(c[0] - ext[0] / 2, c[0] + ext[0] / 2)
        ax.set_ylim(c[1] - ext[1] / 2, c[1] + ext[1] / 2)
        ax.set_zlim(c[2] - ext[2] / 2, c[2] + ext[2] / 2)
        try:
            ax.set_box_aspect(tuple(ext), zoom=1.05)
        except TypeError:
            ax.set_box_aspect(tuple(ext))
        ax.view_init(elev=elev, azim=azim)
        ax.set_axis_off()
        e, a_ = math.radians(elev), math.radians(azim)
        eye = np.array([math.cos(e) * math.cos(a_), math.cos(e) * math.sin(a_), math.sin(e)])
        for f in feat["faces"]:
            if np.dot(f["normal"], eye) <= 0.05:          # only faces this view can see
                continue
            q = np.array(f.get("label_at", f["centre"])) + off * np.array(f["normal"])
            ax.text(*q, f["id"], fontsize=10, weight="bold", color="white", ha="center", va="center", zorder=10,
                    bbox={"boxstyle": "round,pad=0.25", "fc": "#c0392b" if f["holes"] else "#34495e", "ec": "none"})
        ax.set_title(name, fontsize=9)
    fig.suptitle(title or Path(step).name, fontsize=11)
    fig.text(0.5, 0.02, "red = face with holes (see the list for the hole pattern and screw size)",
             ha="center", fontsize=7, color="#555")
    fig.savefig(path, bbox_inches="tight", facecolor="white")
    plt.close(fig)
    return Path(path)
