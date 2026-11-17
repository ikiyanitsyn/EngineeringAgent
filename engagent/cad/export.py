"""Export build123d shapes: STEP for engineering/meshing, STL and 3MF for printing."""
from __future__ import annotations

from pathlib import Path

QUALITY = {  # linear tolerance mm, angular tolerance rad
    "draft": (0.1, 0.5), "standard": (0.02, 0.2), "fine": (0.005, 0.1), "ultra": (0.001, 0.05),
}


def export(shape, step: str | Path, *, stl: bool = False, threemf: bool = False,
           quality: str = "fine") -> list[Path]:
    """Write STEP (always) plus optional STL / 3MF next to it.  Lengths are mm."""
    from build123d import export_step, export_stl
    step = Path(step)
    step.parent.mkdir(parents=True, exist_ok=True)
    files = []
    if not export_step(shape, str(step)):
        raise RuntimeError(f"STEP export failed: {step}")
    files.append(step)
    if quality not in QUALITY:
        raise ValueError(f"quality must be one of {', '.join(QUALITY)}")
    lin, ang = QUALITY[quality]
    if stl:
        p = step.with_suffix(".stl")
        if not export_stl(shape, str(p), tolerance=lin, angular_tolerance=ang):
            raise RuntimeError(f"STL export failed: {p}")
        files.append(p)
    if threemf:
        p = write_3mf(shape, step.with_suffix(".3mf"), lin, ang)
        if p:
            files.append(p)
    return files


def convert(src: str | Path, *, stl: bool = True, threemf: bool = False, quality: str = "fine",
            scale: float = 1.0) -> list[Path]:
    """Convert an existing STEP file to print formats (optionally scaled, e.g. for shrinkage)."""
    from .inspect import load_shape
    shape = load_shape(src)
    src = Path(src)
    if scale != 1.0:
        shape = shape.scale(scale)
        src = src.with_name(src.stem + f"_x{scale:g}".replace(".", "p") + src.suffix)
    from build123d import export_stl
    files: list[Path] = []
    lin, ang = QUALITY[quality]
    if stl:
        p = src.with_suffix(".stl")
        export_stl(shape, str(p), tolerance=lin, angular_tolerance=ang)
        files.append(p)
    if threemf:
        p = write_3mf(shape, src.with_suffix(".3mf"), lin, ang)
        if p:
            files.append(p)
    return files


def write_3mf(shape, path: Path, lin: float, ang: float) -> Path | None:
    """3MF is a convenience format: retry coarser, and skip (STL/STEP remain) if the mesher refuses."""
    from build123d import Mesher
    for f in (1.0, 2.0, 5.0):
        try:
            m = Mesher()
            m.add_shape(shape, linear_deflection=lin * f, angular_deflection=min(ang * f, 0.5))
            m.write(str(path))
            return Path(path)
        except Exception:
            continue
    try:
        return _write_3mf_direct(shape, Path(path), lin, ang)
    except Exception:
        Path(path).unlink(missing_ok=True)
        return None


def _write_3mf_direct(shape, path: Path, lin: float, ang: float) -> Path:
    """Minimal 3MF (core spec): one object, merged vertices, millimetres."""
    import zipfile
    verts, tris = shape.tessellate(lin, ang)
    index: dict[tuple, int] = {}
    pts: list[tuple] = []
    remap = []
    for v in verts:
        key = (round(v.X, 6), round(v.Y, 6), round(v.Z, 6))
        if key not in index:
            index[key] = len(pts)
            pts.append(key)
        remap.append(index[key])
    faces = [(remap[a], remap[b], remap[c]) for a, b, c in tris]
    faces = [f for f in faces if len(set(f)) == 3]
    vx = "".join(f'<vertex x="{x:g}" y="{y:g}" z="{z:g}"/>' for x, y, z in pts)
    tx = "".join(f'<triangle v1="{a}" v2="{b}" v3="{c}"/>' for a, b, c in faces)
    model = ('<?xml version="1.0" encoding="UTF-8"?>'
             '<model unit="millimeter" xml:lang="en-US" '
             'xmlns="http://schemas.microsoft.com/3dmanufacturing/core/2015/02">'
             f'<resources><object id="1" type="model"><mesh><vertices>{vx}</vertices>'
             f'<triangles>{tx}</triangles></mesh></object></resources>'
             '<build><item objectid="1"/></build></model>')
    types = ('<?xml version="1.0" encoding="UTF-8"?>'
             '<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types">'
             '<Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/>'
             '<Default Extension="model" ContentType="application/vnd.ms-package.3dmanufacturing-3dmodel+xml"/>'
             '</Types>')
    rels = ('<?xml version="1.0" encoding="UTF-8"?>'
            '<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">'
            '<Relationship Target="/3D/3dmodel.model" Id="rel0" '
            'Type="http://schemas.microsoft.com/3dmanufacturing/2013/01/3dmodel"/></Relationships>')
    with zipfile.ZipFile(path, "w", zipfile.ZIP_DEFLATED) as z:
        z.writestr("[Content_Types].xml", types)
        z.writestr("_rels/.rels", rels)
        z.writestr("3D/3dmodel.model", model)
    return path
