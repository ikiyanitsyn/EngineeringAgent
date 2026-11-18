"""Static result plots (PNG) for reports, drawn from view.json with matplotlib."""
from __future__ import annotations

import json
from pathlib import Path

import numpy as np


def _mpl():
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    return plt


def _fmt(v: float) -> str:
    a = abs(v)
    if a == 0:
        return "0"
    return f"{v:.3e}" if (a >= 1e5 or a < 1e-3) else f"{v:.4g}"


def contour(view: dict, field: str, frame: int = -1, path: str | Path | None = None, *,
            scale: float | None = None, title: str | None = None, ax=None, elev: float = 24,
            azim: float = -58, vrange: tuple[float, float] | None = None):
    """Shaded colour plot of a surface field on the (deformed) model."""
    plt = _mpl()
    from matplotlib import cm, colors
    from mpl_toolkits.mplot3d.art3d import Poly3DCollection
    fr = view["frames"][frame]
    nodes = np.asarray(view["nodes"], float).reshape(-1, 3)
    tris = np.asarray(view["tris"], dtype=np.int64).reshape(-1, 3)
    if len(tris) > 40_000:
        tris = np.asarray(view["coarse"], dtype=np.int64).reshape(-1, 3)
    vals = np.asarray(fr["fields"][field]["values"], float)
    unit = fr["fields"][field]["unit"]
    disp = np.asarray(fr["disp"], float).reshape(-1, 3) if fr.get("disp") else None
    size = float(view["size"])
    if disp is not None:
        peak = np.linalg.norm(disp, axis=1).max()
        if scale is None:
            scale = 0.06 * size / peak if peak > 0 else 0.0
        pts = nodes + scale * disp
    else:
        pts, scale = nodes, 0.0
    own = ax is None
    if own:
        fig = plt.figure(figsize=(7.2, 3.9), dpi=150)
        ax = fig.add_subplot(111, projection="3d")
    else:
        fig = ax.figure
    tv = vals[tris].mean(axis=1)
    vmin, vmax = vrange if vrange else (float(vals.min()), float(vals.max()))
    if vmax - vmin < 1e-12 * max(1.0, abs(vmax)):
        vmax = vmin + max(1e-9, abs(vmin) * 1e-6)
    norm = colors.Normalize(vmin, vmax)
    cmap = cm.get_cmap("turbo") if hasattr(cm, "get_cmap") else plt.get_cmap("turbo")
    p = pts[tris]
    n = np.cross(p[:, 1] - p[:, 0], p[:, 2] - p[:, 0])
    ln = np.linalg.norm(n, axis=1)
    n = n / np.maximum(ln, 1e-30)[:, None]
    light = np.array([0.35, -0.5, 0.8])
    light /= np.linalg.norm(light)
    shade = 0.6 + 0.4 * np.abs(n @ light)
    fc = cmap(norm(tv))
    fc[:, :3] *= shade[:, None]
    coll = Poly3DCollection(p, facecolors=fc, edgecolors="none", linewidths=0, antialiased=False)
    ax.add_collection3d(coll)
    lo, hi = pts.min(axis=0), pts.max(axis=0)
    ext = np.maximum(hi - lo, 1e-9 * max(size, 1e-9))
    ext = np.maximum(ext, 0.04 * ext.max())
    c = (lo + hi) / 2
    ax.set_xlim(c[0] - ext[0] / 2, c[0] + ext[0] / 2)
    ax.set_ylim(c[1] - ext[1] / 2, c[1] + ext[1] / 2)
    ax.set_zlim(c[2] - ext[2] / 2, c[2] + ext[2] / 2)
    try:
        ax.set_box_aspect(tuple(ext), zoom=1.25 if ext.max() > 4 * np.sort(ext)[1] else 0.98)
    except TypeError:
        ax.set_box_aspect(tuple(ext))
    ax.view_init(elev=elev, azim=azim)
    ax.set_axis_off()
    sm = cm.ScalarMappable(norm=norm, cmap=cmap)
    cb = fig.colorbar(sm, ax=ax, shrink=0.7, pad=0.02, fraction=0.03)
    cb.set_label(f"{field} [{unit}]" if unit else field, fontsize=8)
    cb.ax.tick_params(labelsize=7)
    sub = f"max {_fmt(float(vals.max()))}, min {_fmt(float(vals.min()))} {unit}".strip()
    if disp is not None and scale:
        sub += f"  |  deformation x{scale:.3g}"
    ax.set_title((title or f"{field} - {fr['label']}") + "\n" + sub, fontsize=9)
    if own and path:
        fig.savefig(path, bbox_inches="tight", facecolor="white")
        plt.close(fig)
        return Path(path)
    return ax


def animate(view: dict, field: str, path: str | Path, frame: int = -1, n: int = 10, *, title: str | None = None,
            dpi: int = 100, ms: int = 110) -> Path | None:
    """Animated GIF of the deformation growing and relaxing (exaggerated), coloured by ``field``.

    For issue comments and phones: an image plays everywhere a picture is shown, no viewer needed.
    """
    import io
    import math
    from PIL import Image
    plt = _mpl()
    fr = view["frames"][frame]
    if not fr.get("disp") or field not in fr["fields"]:
        return None
    disp = np.asarray(fr["disp"], float).reshape(-1, 3)
    peak = float(np.linalg.norm(disp, axis=1).max())
    if peak <= 0:
        return None
    full = 0.08 * float(view["size"]) / peak
    vals = np.asarray(fr["fields"][field]["values"], float)
    vr = (float(vals.min()), float(vals.max()))
    nodes = np.asarray(view["nodes"], float).reshape(-1, 3)
    both = np.vstack([nodes, nodes + full * disp])          # frame fits the shape at full deformation
    lo, hi = both.min(axis=0), both.max(axis=0)
    ext = np.maximum(hi - lo, 0.04 * float(np.max(hi - lo)))
    c = (lo + hi) / 2
    lo, hi = c - ext / 2, c + ext / 2
    images = []
    for k in range(n):
        amp = math.sin(0.5 * math.pi * k / (n - 1))        # 0 -> full, eased
        fig = plt.figure(figsize=(6.0, 4.0), dpi=dpi)
        ax = fig.add_subplot(111, projection="3d")
        contour(view, field, frame, None, scale=max(amp * full, 1e-12), ax=ax, vrange=vr,
                title=title or f"{field} - deformation shown x{full:.3g}")
        ax.set_xlim(lo[0], hi[0]); ax.set_ylim(lo[1], hi[1]); ax.set_zlim(lo[2], hi[2])
        try:
            ax.set_box_aspect(tuple(ext), zoom=1.2)
        except TypeError:
            ax.set_box_aspect(tuple(ext))
        buf = io.BytesIO()
        fig.savefig(buf, format="png", facecolor="white", bbox_inches="tight", pad_inches=0.05)
        plt.close(fig)
        buf.seek(0)
        im = Image.open(buf).convert("RGB")
        if images and im.size != images[0].size:
            im = im.resize(images[0].size)
        images.append(im.convert("P", palette=Image.ADAPTIVE, colors=128))
    seq = images + images[-2:0:-1]                       # grow, then relax: a smooth loop
    seq[0].save(path, save_all=True, append_images=seq[1:], duration=ms, loop=0, optimize=True)
    return Path(path)


def history(times, series: dict[str, list[float]], path: str | Path, ylabel: str, title: str,
            xlabel: str = "Time [s]") -> Path:
    plt = _mpl()
    fig, ax = plt.subplots(figsize=(7.2, 3.4), dpi=150)
    for name, ys in series.items():
        ax.plot(times, ys, label=name, linewidth=1.6)
    ax.set_xlabel(xlabel, fontsize=8); ax.set_ylabel(ylabel, fontsize=8)
    ax.set_title(title, fontsize=9)
    ax.grid(True, alpha=0.3); ax.tick_params(labelsize=7)
    if len(series) > 1:
        ax.legend(fontsize=7, frameon=False)
    fig.savefig(path, bbox_inches="tight", facecolor="white")
    plt.close(fig)
    return Path(path)


def job_plots(folder: str | Path, results: dict) -> list[dict]:
    """Create the standard set of plots for a solved job; returns [{path, caption}]."""
    from .. import units as U
    folder = Path(folder)
    vp = folder / "view.json"
    if not vp.exists():
        return []
    view = json.loads(vp.read_text(encoding="utf-8"))
    frames = view["frames"]
    if not frames:
        return []
    out: list[dict] = []
    plots = folder / "plots"
    plots.mkdir(exist_ok=True)
    a = results.get("analysis")
    names = list(frames[-1]["fields"])
    def add(field, frame, fname, caption, **kw):
        if field in frames[frame]["fields"]:
            out.append({"path": contour(view, field, frame, plots / fname, **kw), "caption": caption})
    if a in ("modal", "buckling"):
        for k in range(min(4, len(frames))):
            add("Mode shape (normalised)", k, f"mode_{k + 1}.png", frames[k]["label"])
    else:
        if "von Mises stress" in names:
            add("von Mises stress", -1, "von_mises.png",
                "von Mises stress on the deformed shape (nodal values extrapolated from integration points)")
            add("Displacement", -1, "displacement.png", "Displacement magnitude on the deformed shape")
            try:                                          # animated deformation for chats and phones
                gif = animate(view, "von Mises stress", plots / "deformation.gif")
                if gif:
                    out.append({"path": gif, "caption": "Animated deformation (exaggerated), coloured by "
                                "von Mises stress", "animation": True})
            except Exception:
                pass
        heat_solved = a in ("thermal_steady", "thermal_transient") or (
            a == "thermal_stress" and any(c.get("type") == "temperature"
                                          for c in (results.get("job") or {}).get("constraints", [])))
        if heat_solved:
            add("Temperature", -1, "temperature.png",
                "Temperature field" + (" at the end of the run" if view.get("transient") else ""))
        if "Plastic strain" in names:
            add("Plastic strain", -1, "plastic_strain.png", "Equivalent plastic strain")
        if a == "thermal_steady":
            add("Heat flux", -1, "heat_flux.png", "Heat flux magnitude")
    h = results.get("history")
    if h and len(h.get("time", [])) > 1:
        s = results.get("units")
        series = {k: [U.from_internal(v, "temperature", s) for v in vals]
                  for k, vals in h.items() if k not in ("time",)}
        labels = {"max": "model maximum", "min": "model minimum"}
        series = {labels.get(k, f"probe '{k}'"): v for k, v in series.items()}
        out.append({"path": history(h["time"], series, plots / "history.png",
                                    f"Temperature [{U.default_unit('temperature', s)}]",
                                    "Temperature history"),
                    "caption": "Temperature history at the probes and model extremes"})
    return out
