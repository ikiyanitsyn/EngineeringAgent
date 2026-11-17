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
    Path(path).unlink(missing_ok=True)
    return None
