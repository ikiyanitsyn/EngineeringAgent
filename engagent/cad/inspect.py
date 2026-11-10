"""Numerical verification of a CAD solid: validity, volume, bounding box, mass properties."""
from __future__ import annotations

from pathlib import Path
from typing import Any

from .. import materials
from .. import units as U


def load_shape(path: str | Path):
    """Read a STEP (or BREP / STL) file into a build123d shape."""
    from build123d import import_brep, import_step, import_stl
    p = Path(path)
    if not p.exists():
        raise FileNotFoundError(f"CAD file not found: {p}")
    ext = p.suffix.lower()
    if ext in (".step", ".stp"):
        return import_step(str(p))
    if ext == ".brep":
        return import_brep(str(p))
    if ext == ".stl":
        return import_stl(str(p))
    raise ValueError(f"unsupported CAD format {ext}; use .step, .brep or .stl")


def inspect_shape(shape_or_path: Any, material: str | dict | None = None,
                  system: str | None = None) -> dict:
    """Geometry facts in internal units (mm, mm^2, mm^3, tonne)."""
    from build123d import CenterOf, GeomType
    shape = load_shape(shape_or_path) if isinstance(shape_or_path, (str, Path)) else shape_or_path
    bb = shape.bounding_box()
    solids = shape.solids()
    faces = shape.faces()
    info: dict = {
        "valid": bool(shape.is_valid if not callable(shape.is_valid) else shape.is_valid()),
        "solids": len(solids), "faces": len(faces), "edges": len(shape.edges()),
        "volume": float(sum(s.volume for s in solids)) if solids else float(getattr(shape, "volume", 0.0)),
        "area": float(shape.area),
        "bbox_min": [bb.min.X, bb.min.Y, bb.min.Z], "bbox_max": [bb.max.X, bb.max.Y, bb.max.Z],
        "bbox_size": [bb.size.X, bb.size.Y, bb.size.Z],
    }
    try:
        c = shape.center(CenterOf.MASS)
        info["center_of_mass"] = [c.X, c.Y, c.Z]
    except Exception:
        pass
    try:
        info["inertia_unit_density"] = [[float(v) for v in row] for row in shape.matrix_of_inertia]
    except Exception:
        pass
    kinds: dict[str, int] = {}
    holes: dict[float, int] = {}
    flat = []
    for f in faces:
        name = f.geom_type.name.lower()
        kinds[name] = kinds.get(name, 0) + 1
        if f.geom_type == GeomType.CYLINDER:
            try:
                d = round(2 * float(f.radius), 4)
                holes[d] = holes.get(d, 0) + 1
            except Exception:
                pass
    info["face_types"] = kinds
    info["cylinder_diameters"] = [{"diameter": d, "faces": n} for d, n in sorted(holes.items())]
    if material is not None:
        m = materials.get(material, system)
        rho = m.get("density")
        if rho:
            info["material"] = m.key
            info["mass"] = info["volume"] * rho
            if "inertia_unit_density" in info:
                info["inertia"] = [[v * rho for v in row] for row in info["inertia_unit_density"]]
    return info


def describe(info: dict, system: str | None = None) -> list[tuple[str, str]]:
    """Human-readable rows for reports and the CLI, in the active unit system."""
    rows = [("Valid solid", "yes" if info["valid"] else "NO"),
            ("Solid bodies", str(info["solids"])),
            ("Faces / edges", f"{info['faces']} / {info['edges']}"),
            ("Bounding box", U.fmt_vec(info["bbox_size"], "length", system)),
            ("Bounding box min", U.fmt_vec(info["bbox_min"], "length", system)),
            ("Bounding box max", U.fmt_vec(info["bbox_max"], "length", system)),
            ("Volume", U.fmt(info["volume"], "volume", system)),
            ("Surface area", U.fmt(info["area"], "area", system, "cm^2" if U.normalize_system(system) == "metric" else None))]
    if "center_of_mass" in info:
        rows.append(("Centre of mass", U.fmt_vec(info["center_of_mass"], "length", system)))
    if "mass" in info:
        rows.append((f"Mass ({info['material']})", U.fmt(info["mass"], "mass", system)))
    if info.get("cylinder_diameters"):
        rows.append(("Cylindrical faces", ", ".join(
            f"{c['faces']} x dia {U.fmt(c['diameter'], 'length', system)}" for c in info["cylinder_diameters"][:12])))
    return rows
