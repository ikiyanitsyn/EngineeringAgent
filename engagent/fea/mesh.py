"""Meshing with Gmsh: STEP in, CalculiX-ready tetrahedra and named face sets out.

The mesh is read straight from the Gmsh API (not from Gmsh's .inp export), so
element node order, set names and surface face numbers are under our control.
All coordinates are in mm.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import numpy as np

from .. import units as U

AXES = {"x": 0, "y": 1, "z": 2}
# CalculiX C3D4/C3D10 face -> local corner indices (0-based)
TET_FACES = np.array([[0, 1, 2], [0, 3, 1], [1, 3, 2], [2, 3, 0]])


@dataclass
class FaceSet:
    name: str
    face_tags: list[int]
    nodes: np.ndarray            # node ids on the surface
    tris: np.ndarray             # (n, 3|6) surface triangles (node ids)
    elem_faces: np.ndarray       # (n, 2) element id, CalculiX face number 1..4
    area: float
    centroid: np.ndarray
    weights: dict[int, float] = field(default_factory=dict)   # node id -> tributary area
    part: str | None = None


@dataclass
class Mesh:
    nodes: np.ndarray            # (N, 3) coordinates; node id = row + 1
    elems: np.ndarray            # (E, 4|10) node ids in CalculiX order; elem id = row + 1
    elem_part: np.ndarray        # (E,) index into parts
    parts: list[str]
    order: int
    size: float
    face_sets: dict[str, FaceSet] = field(default_factory=dict)
    node_sets: dict[str, np.ndarray] = field(default_factory=dict)
    surface_tris: np.ndarray | None = None      # all boundary triangles (n, 3|6)
    surface_part: np.ndarray | None = None
    quality: dict[str, float] = field(default_factory=dict)
    faces: list[dict] = field(default_factory=list)

    @property
    def n_nodes(self) -> int:
        return len(self.nodes)

    @property
    def n_elems(self) -> int:
        return len(self.elems)

    @property
    def etype(self) -> str:
        return "C3D10" if self.order == 2 else "C3D4"

    def bbox(self) -> tuple[np.ndarray, np.ndarray]:
        return self.nodes.min(axis=0), self.nodes.max(axis=0)

    def part_elems(self, part: str) -> np.ndarray:
        return np.nonzero(self.elem_part == self.parts.index(part))[0] + 1

    def part_nodes(self, part: str) -> np.ndarray:
        return np.unique(self.elems[self.elem_part == self.parts.index(part)])

    def nearest_node(self, point, part: str | None = None) -> int:
        ids = self.part_nodes(part) if part else np.arange(1, self.n_nodes + 1)
        d = np.linalg.norm(self.nodes[ids - 1] - np.asarray(point, float), axis=1)
        return int(ids[int(np.argmin(d))])

    def volume(self) -> float:
        p = self.nodes[self.elems[:, :4] - 1]
        return float(np.abs(np.einsum("ij,ij->i", p[:, 1] - p[:, 0],
                                      np.cross(p[:, 2] - p[:, 0], p[:, 3] - p[:, 0]))).sum() / 6)

    def summary(self) -> dict:
        lo, hi = self.bbox()
        return {"nodes": self.n_nodes, "elements": self.n_elems, "element_type": self.etype,
                "size_mm": self.size, "parts": self.parts, "bbox_min": lo.tolist(),
                "bbox_max": hi.tolist(), "volume_mm3": self.volume(), **self.quality}


# --------------------------------------------------------------------------- geometry
def _gmsh():
    try:
        import gmsh
    except ImportError as e:  # pragma: no cover
        raise RuntimeError("gmsh is not installed; run the setup script "
                           "(scripts/setup.ps1 or scripts/setup.sh)") from e
    return gmsh


def _init(gmsh) -> None:
    """Start Gmsh; without a Ctrl-C handler when not on the main thread (MCP server, GUIs)."""
    import threading
    if threading.current_thread() is threading.main_thread():
        gmsh.initialize()
    else:
        gmsh.initialize(interruptible=False)


def _face_info(gmsh, tag: int, part: str, vol: int) -> dict:
    x0, y0, z0, x1, y1, z1 = gmsh.model.getBoundingBox(2, tag)
    kind = gmsh.model.getType(2, tag)
    info = {"tag": tag, "part": part, "volume": vol, "type": kind,
            "bbox": [x0, y0, z0, x1, y1, z1],
            "area": gmsh.model.occ.getMass(2, tag),
            "centroid": list(gmsh.model.occ.getCenterOfMass(2, tag))}
    try:
        lo, hi = gmsh.model.getParametrizationBounds(2, tag)
        mid = [(lo[0] + hi[0]) / 2, (lo[1] + hi[1]) / 2]
        n = np.array(gmsh.model.getNormal(tag, mid))
        info["normal"] = n.tolist()
        info["mid"] = list(gmsh.model.getValue(2, tag, mid))
        if kind == "Cylinder":
            kmax, kmin, _, _ = gmsh.model.getPrincipalCurvatures(tag, mid)
            k = max(abs(kmax[0]), abs(kmin[0]))
            if k > 1e-12:
                info["radius"] = 1.0 / k
            # axis = direction of zero curvature; estimate from normals at two params
            n2 = np.array(gmsh.model.getNormal(tag, [lo[0] + 0.25 * (hi[0] - lo[0]), mid[1]]))
            ax = np.cross(n, n2)
            if np.linalg.norm(ax) < 1e-6:
                n2 = np.array(gmsh.model.getNormal(tag, [mid[0], lo[1] + 0.25 * (hi[1] - lo[1])]))
                ax = np.cross(n, n2)
            if np.linalg.norm(ax) > 1e-9:
                info["axis"] = (ax / np.linalg.norm(ax)).tolist()
    except Exception:
        pass
    return info


def _outward(gmsh, f: dict) -> np.ndarray | None:
    """Outward unit normal of a face at its mid-parameter point."""
    if "normal" not in f:
        return None
    if "outward" not in f:
        n = np.array(f["normal"])
        p = np.array(f["mid"])
        x0, y0, z0, x1, y1, z1 = gmsh.model.getBoundingBox(3, f["volume"])
        eps = 1e-3 * max(x1 - x0, y1 - y0, z1 - z0)
        inside = gmsh.model.isInside(3, f["volume"], list(p + eps * n))
        f["outward"] = (-n if inside else n).tolist()
    return np.array(f["outward"])


def select_faces(gmsh, faces: list[dict], sel: Any, system: str | None,
                 model_bbox: np.ndarray, tol: float) -> list[int]:
    """Evaluate a face selector; returns Gmsh face tags."""
    if isinstance(sel, (list, tuple)):
        out: list[int] = []
        for s in sel:
            out += [t for t in select_faces(gmsh, faces, s, system, model_bbox, tol) if t not in out]
        return out
    if isinstance(sel, str):
        s = sel.strip().lower()
        if len(s) == 4 and s[0] in AXES and s[1:] in ("min", "max"):
            return select_faces(gmsh, faces, {"plane": s[0], "at": s[1:]}, system, model_bbox, tol)
        raise ValueError(f"unknown face selector {sel!r}; use 'xmin'..'zmax' or a selector dict")
    if not isinstance(sel, dict):
        raise TypeError(f"face selector must be a string, dict or list, got {type(sel).__name__}")

    L = lambda v: U.to_internal(v, "length", system)  # noqa: E731
    cand = list(faces)
    if "part" in sel:
        cand = [f for f in cand if f["part"] == sel["part"]]
        if not cand:
            raise ValueError(f"selector names unknown part {sel['part']!r}")
    if "faces" in sel:
        want = set(int(t) for t in sel["faces"])
        cand = [f for f in cand if f["tag"] in want]
    if "plane" in sel:
        ax = AXES[str(sel["plane"]).lower()]
        at = sel.get("at", "min")
        if isinstance(at, str) and at.lower() in ("min", "max"):
            pool = np.array([f["bbox"] for f in cand]) if cand else np.zeros((0, 6))
            at_v = pool[:, ax].min() if at.lower() == "min" else pool[:, ax + 3].max()
        else:
            at_v = L(at)
        t = L(sel["tol"]) if "tol" in sel else tol
        cand = [f for f in cand if abs(f["bbox"][ax] - at_v) <= t and abs(f["bbox"][ax + 3] - at_v) <= t]
    if "normal" in sel:
        d = np.asarray(sel["normal"], float)
        d /= np.linalg.norm(d)
        keep = []
        for f in cand:
            n = _outward(gmsh, f)
            if n is not None and f["type"] == "Plane" and float(n @ d) > 0.999:
                keep.append(f)
        cand = keep
    if "cylinder" in sel:
        c = sel["cylinder"] if isinstance(sel["cylinder"], dict) else {"radius": sel["cylinder"]}
        cand = [f for f in cand if f["type"] == "Cylinder"]
        if "radius" in c or "diameter" in c:
            r = L(c["radius"]) if "radius" in c else L(c["diameter"]) / 2
            cand = [f for f in cand if abs(f.get("radius", -1) - r) <= max(tol, 0.01 * r)]
        if "axis" in c:
            ax = AXES[str(c["axis"]).lower()]
            cand = [f for f in cand if abs(abs(f.get("axis", [0, 0, 0])[ax]) - 1) < 1e-3]
        if "near" in c:
            p = np.array([L(v) for v in c["near"]])
            if cand:
                # all cylinder faces sharing the axis closest to the point
                def axis_dist(f):
                    a = np.array(f.get("axis", [0, 0, 1.0]))
                    v = np.array(f["centroid"]) - p
                    return float(np.linalg.norm(v - (v @ a) * a))
                dmin = min(axis_dist(f) for f in cand)
                cand = [f for f in cand if axis_dist(f) <= dmin + max(tol, 1e-3)]
    if "box" in sel:
        b = [L(v) for v in sel["box"]]
        cand = [f for f in cand if all(f["bbox"][i] >= b[i] - tol for i in range(3))
                and all(f["bbox"][i + 3] <= b[i + 3] + tol for i in range(3))]
    if "type" in sel:
        cand = [f for f in cand if f["type"].lower() == str(sel["type"]).lower()]
    if "near" in sel:
        p = [L(v) for v in sel["near"]]
        best, bd = None, 1e99
        for f in cand:
            try:
                q, _ = gmsh.model.getClosestPoint(2, f["tag"], p)
                d = float(np.linalg.norm(np.array(q) - np.array(p)))
            except Exception:
                d = float(np.linalg.norm(np.array(f["centroid"]) - np.array(p)))
            if d < bd:
                best, bd = f, d
        cand = [best] if best else []
    tags = [f["tag"] for f in cand]
    if "exclude" in sel:
        drop = set(select_faces(gmsh, faces, sel["exclude"], system, model_bbox, tol))
        tags = [t for t in tags if t not in drop]
    return tags


def _import_parts(gmsh, parts: list[tuple[str, str]]) -> tuple[list[dict], dict[str, list[int]]]:
    gmsh.option.setString("Geometry.OCCTargetUnit", "MM")
    part_vols: dict[str, list[int]] = {}
    for name, path in parts:
        if not Path(path).exists():
            raise FileNotFoundError(f"geometry file not found: {path}")
        ents = gmsh.model.occ.importShapes(str(path))
        vols = [t for d, t in ents if d == 3]
        if not vols:
            raise ValueError(f"{path} contains no solid; FEA needs a closed solid body")
        part_vols[name] = vols
    gmsh.model.occ.synchronize()
    faces: list[dict] = []
    for name, vols in part_vols.items():
        for v in vols:
            for _, ft in gmsh.model.getBoundary([(3, v)], oriented=False):
                faces.append(_face_info(gmsh, ft, name, v))
    return faces, part_vols


def list_faces(parts: list[tuple[str, str]] | str) -> list[dict]:
    """Table of the CAD faces of a STEP file: tag, type, bbox, area, centroid, normal, radius."""
    gmsh = _gmsh()
    if isinstance(parts, (str, Path)):
        parts = [("part", str(parts))]
    _init(gmsh)
    try:
        gmsh.option.setNumber("General.Terminal", 0)
        faces, _ = _import_parts(gmsh, parts)
        for f in faces:
            _outward(gmsh, f)
        return faces
    finally:
        gmsh.finalize()


# --------------------------------------------------------------------------- meshing
def build_mesh(parts: list[tuple[str, str]], sets: dict[str, Any] | None = None, *,
               size: float | None = None, order: int = 2, refine: list[dict] | None = None,
               system: str | None = None, min_size: float | None = None,
               curvature: int = 12, max_nodes: int = 600_000, optimize: bool = True,
               growth: float | None = None) -> Mesh:
    """Mesh one or more STEP solids into tetrahedra.

    parts   list of (part name, STEP path).  Bodies are meshed independently
            (non-conforming), which is what tie/contact interactions expect.
    sets    name -> face selector; each becomes a node set + element-face surface.
    size    target element size in mm (internal units); default = bbox diagonal / 25.
    refine  list of {"on": selector or set name, "size": s, "distance": d}
            (lengths in the active unit system).
    """
    gmsh = _gmsh()
    sets = sets or {}
    _init(gmsh)
    try:
        gmsh.option.setNumber("General.Terminal", 0)
        gmsh.option.setNumber("General.NumThreads", 1)       # reproducible meshes
        faces, part_vols = _import_parts(gmsh, parts)
        bb = np.array(gmsh.model.getBoundingBox(-1, -1))
        diag = float(np.linalg.norm(bb[3:] - bb[:3]))
        tol = max(1e-6 * diag, 1e-5)
        sel_tol = max(1e-4 * diag, 1e-4)
        if size is None:
            size = diag / 25.0
        # --- resolve selectors (before meshing so refinement can use them)
        set_tags: dict[str, list[int]] = {}
        point_sets: dict[str, list[float]] = {}
        for name, sel in sets.items():
            if isinstance(sel, dict) and "point" in sel:
                point_sets[name] = [U.to_internal(v, "length", system) for v in sel["point"]]
                continue
            tags = select_faces(gmsh, faces, sel, system, bb, sel_tol)
            if not tags:
                raise ValueError(
                    f"set {name!r}: selector {sel!r} matched no CAD face. "
                    f"Run `engagent cad faces <file.step>` to list faces and their coordinates.")
            set_tags[name] = tags

        gmsh.option.setNumber("Mesh.MeshSizeMax", size)
        gmsh.option.setNumber("Mesh.MeshSizeMin", min_size if min_size else size / 20.0)
        gmsh.option.setNumber("Mesh.MeshSizeFromCurvature", curvature)
        gmsh.option.setNumber("Mesh.ElementOrder", order)
        gmsh.option.setNumber("Mesh.SecondOrderLinear", 0)
        gmsh.option.setNumber("Mesh.HighOrderOptimize", 2 if (optimize and order == 2) else 0)
        gmsh.option.setNumber("Mesh.Algorithm", 6)
        gmsh.option.setNumber("Mesh.Algorithm3D", 1)
        gmsh.option.setNumber("Mesh.Optimize", 1 if optimize else 0)
        gmsh.option.setNumber("Mesh.OptimizeNetgen", 0)

        fields = []
        for r in refine or []:
            on = r.get("on")
            tags = set_tags.get(on) if isinstance(on, str) and on in set_tags else \
                select_faces(gmsh, faces, on, system, bb, sel_tol)
            if not tags:
                raise ValueError(f"refinement region {on!r} matched no face")
            s = U.to_internal(r["size"], "length", system)
            dist = U.to_internal(r["distance"], "length", system) if "distance" in r else 3 * s
            fd = gmsh.model.mesh.field.add("Distance")
            gmsh.model.mesh.field.setNumbers(fd, "SurfacesList", tags)
            gmsh.model.mesh.field.setNumber(fd, "Sampling", 40)
            ft = gmsh.model.mesh.field.add("Threshold")
            gmsh.model.mesh.field.setNumber(ft, "InField", fd)
            gmsh.model.mesh.field.setNumber(ft, "SizeMin", s)
            gmsh.model.mesh.field.setNumber(ft, "SizeMax", size)
            gmsh.model.mesh.field.setNumber(ft, "DistMin", dist)
            gmsh.model.mesh.field.setNumber(ft, "DistMax", dist + (growth or 6) * max(size - s, s))
            fields.append(ft)
        if fields:
            fm = gmsh.model.mesh.field.add("Min")
            gmsh.model.mesh.field.setNumbers(fm, "FieldsList", fields)
            gmsh.model.mesh.field.setAsBackgroundMesh(fm)
            gmsh.option.setNumber("Mesh.MeshSizeMin",
                                  min(gmsh.option.getNumber("Mesh.MeshSizeMin"),
                                      min(U.to_internal(r["size"], "length", system)
                                          for r in refine) / 2))

        gmsh.model.mesh.generate(3)

        # --- nodes
        tags, coords, _ = gmsh.model.mesh.getNodes()
        tags = np.asarray(tags, dtype=np.int64)
        coords = np.asarray(coords).reshape(-1, 3)
        ttype = 11 if order == 2 else 4
        npe = 10 if order == 2 else 4
        elems, epart = [], []
        names = list(part_vols)
        for pi, name in enumerate(names):
            for v in part_vols[name]:
                etypes, _, enodes = gmsh.model.mesh.getElements(3, v)
                for et, en in zip(etypes, enodes):
                    if et != ttype:
                        continue
                    arr = np.asarray(en, dtype=np.int64).reshape(-1, npe)
                    elems.append(arr)
                    epart.append(np.full(len(arr), pi))
        if not elems:
            raise RuntimeError("Gmsh produced no tetrahedra; check that the STEP solid is valid")
        elems = np.vstack(elems)
        epart = np.concatenate(epart)
        if order == 2:                      # Gmsh -> CalculiX: swap the last two mid-side nodes
            elems = elems[:, [0, 1, 2, 3, 4, 5, 6, 7, 9, 8]]
        used = np.unique(elems)
        if len(used) > max_nodes:
            raise RuntimeError(
                f"mesh has {len(used):,} nodes (limit {max_nodes:,}); increase the element size "
                f"or raise mesh.max_nodes")
        remap = np.zeros(int(tags.max()) + 1, dtype=np.int64)
        remap[used] = np.arange(1, len(used) + 1)
        pos = np.zeros((int(tags.max()) + 1, 3))
        pos[tags] = coords
        nodes = pos[used]
        elems = remap[elems]
        # fix inverted elements (negative volume) by swapping two corners
        p = nodes[elems[:, :4] - 1]
        vol6 = np.einsum("ij,ij->i", p[:, 1] - p[:, 0], np.cross(p[:, 2] - p[:, 0], p[:, 3] - p[:, 0]))
        neg = vol6 < 0
        if neg.any():
            if order == 2:
                elems[neg] = elems[neg][:, [1, 0, 2, 3, 4, 6, 5, 8, 7, 9]]
            else:
                elems[neg] = elems[neg][:, [1, 0, 2, 3]]

        mesh = Mesh(nodes=nodes, elems=elems, elem_part=epart, parts=names, order=order,
                    size=float(size), faces=faces)

        # --- tet face lookup: key of sorted corner ids -> (elem, face)
        N = np.int64(mesh.n_nodes + 1)
        corners = elems[:, :4]
        fk = np.sort(corners[:, TET_FACES], axis=2)                  # (E, 4, 3)
        keys = (fk[..., 0] * N + fk[..., 1]) * N + fk[..., 2]
        flat = keys.ravel()
        srt = np.argsort(flat, kind="stable")
        flat_sorted = flat[srt]

        def tri_data(face_tags: list[int]):
            tri_list = []
            for ft in face_tags:
                etypes, _, enodes = gmsh.model.mesh.getElements(2, ft)
                for et, en in zip(etypes, enodes):
                    if et == (9 if order == 2 else 2):
                        tri_list.append(remap[np.asarray(en, dtype=np.int64).reshape(-1, 6 if order == 2 else 3)])
            return np.vstack(tri_list) if tri_list else np.zeros((0, 6 if order == 2 else 3), dtype=np.int64)

        def lookup(tris: np.ndarray) -> np.ndarray:
            c = np.sort(tris[:, :3], axis=1)
            k = (c[:, 0] * N + c[:, 1]) * N + c[:, 2]
            i = np.searchsorted(flat_sorted, k)
            i = np.clip(i, 0, len(flat_sorted) - 1)
            ok = flat_sorted[i] == k
            idx = srt[i]
            return np.column_stack([idx // 4 + 1, idx % 4 + 1])[ok]

        def make_set(name: str, face_tags: list[int]) -> FaceSet:
            tris = tri_data(face_tags)
            if len(tris) == 0:
                raise RuntimeError(f"set {name!r}: no surface elements found on faces {face_tags}")
            pc = nodes[tris[:, :3] - 1]
            a = 0.5 * np.linalg.norm(np.cross(pc[:, 1] - pc[:, 0], pc[:, 2] - pc[:, 0]), axis=1)
            w: dict[int, float] = {}
            loaded = tris[:, 3:] if order == 2 else tris
            for col in range(loaded.shape[1]):
                for nid, ai in zip(loaded[:, col], a):
                    w[int(nid)] = w.get(int(nid), 0.0) + ai / 3.0
            cen = (pc.mean(axis=1) * a[:, None]).sum(axis=0) / a.sum()
            fparts = {f["part"] for f in faces if f["tag"] in face_tags}
            return FaceSet(name=name, face_tags=list(face_tags), nodes=np.unique(tris), tris=tris,
                           elem_faces=lookup(tris), area=float(a.sum()), centroid=cen, weights=w,
                           part=next(iter(fparts)) if len(fparts) == 1 else None)

        for name, ftags in set_tags.items():
            mesh.face_sets[name] = make_set(name, ftags)
            mesh.node_sets[name] = mesh.face_sets[name].nodes
        for name, pt in point_sets.items():
            mesh.node_sets[name] = np.array([mesh.nearest_node(pt)])

        # --- full boundary surface for plotting
        all_tris, tri_part = [], []
        for pi, name in enumerate(names):
            ftags = [f["tag"] for f in faces if f["part"] == name]
            t = tri_data(ftags)
            all_tris.append(t)
            tri_part.append(np.full(len(t), pi))
        mesh.surface_tris = np.vstack(all_tris)
        mesh.surface_part = np.concatenate(tri_part)

        # --- quality
        try:
            _, etags, _ = gmsh.model.mesh.getElements(3)
            et = np.concatenate([np.asarray(e) for e in etags])
            q = np.asarray(gmsh.model.mesh.getElementQualities(et.tolist(), "minSICN"))
            mesh.quality = {"quality_min": float(q.min()), "quality_mean": float(q.mean()),
                            "quality_below_0p1": int((q < 0.1).sum())}
        except Exception:
            mesh.quality = {}
        return mesh
    finally:
        gmsh.finalize()
