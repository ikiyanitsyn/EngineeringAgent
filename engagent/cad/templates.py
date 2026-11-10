"""Parametric part templates (all dimensions in mm, internal units).

Templates cover the shapes engineers ask for most; anything else is written as
a build123d script (see the cad-modeling skill).  Each template returns a
build123d Part positioned so that supports and loads are easy to select:
the part starts at the origin and grows along +X / +Z.
"""
from __future__ import annotations

from pathlib import Path
from typing import Any, Callable

from .. import units as U

TEMPLATES: dict[str, tuple[Callable, dict[str, Any], str]] = {}


def template(name: str, doc: str, **defaults):
    def deco(fn):
        TEMPLATES[name] = (fn, defaults, doc)
        return fn
    return deco


@template("beam", "Prismatic beam along +X. section: rect | tube | rect_tube | i",
          length=100.0, width=10.0, height=10.0, section="rect", wall=2.0, flange=2.0, web=2.0)
def beam(length, width, height, section, wall, flange, web):
    from build123d import Align, Circle, Plane, Rectangle, extrude
    yz = Plane.YZ
    if section == "rect":
        prof = yz * Rectangle(width, height)
    elif section == "tube":
        prof = yz * (Circle(width / 2) - Circle(width / 2 - wall))
    elif section == "rect_tube":
        prof = yz * (Rectangle(width, height) - Rectangle(width - 2 * wall, height - 2 * wall))
    elif section == "i":
        prof = yz * (Rectangle(width, height)
                     - Rectangle((width - web) / 2, height - 2 * flange,
                                 align=(Align.MIN, Align.CENTER)).move(_loc(web / 2, 0))
                     - Rectangle((width - web) / 2, height - 2 * flange,
                                 align=(Align.MAX, Align.CENTER)).move(_loc(-web / 2, 0)))
    else:
        raise ValueError("section must be rect, tube, rect_tube or i")
    return extrude(prof, length)


def _loc(x, y):
    from build123d import Location
    return Location((x, y, 0))


@template("plate", "Flat plate in XY with an optional rectangular hole pattern and corner radius",
          length=100.0, width=60.0, thickness=5.0, hole_diameter=0.0, holes_x=2, holes_y=2,
          edge_distance=10.0, corner_radius=0.0, center_hole=0.0)
def plate(length, width, thickness, hole_diameter, holes_x, holes_y, edge_distance, corner_radius,
          center_hole):
    from build123d import Align, Axis, Box, Cylinder, Pos, fillet
    p = Box(length, width, thickness, align=(Align.MIN, Align.MIN, Align.MIN))
    if corner_radius > 0:
        p = fillet(p.edges().filter_by(Axis.Z), corner_radius)
    if hole_diameter > 0:
        nx, ny = max(1, int(holes_x)), max(1, int(holes_y))
        for i in range(nx):
            for j in range(ny):
                x = length / 2 if nx == 1 else edge_distance + i * (length - 2 * edge_distance) / (nx - 1)
                y = width / 2 if ny == 1 else edge_distance + j * (width - 2 * edge_distance) / (ny - 1)
                p -= Pos(x, y, thickness / 2) * Cylinder(hole_diameter / 2, thickness * 2)
    if center_hole > 0:
        p -= Pos(length / 2, width / 2, thickness / 2) * Cylinder(center_hole / 2, thickness * 2)
    return p


@template("l_bracket", "L-bracket: base leg along +X, upright leg along +Z, inside fillet, bolt holes",
          leg_x=60.0, leg_z=60.0, width=40.0, thickness=5.0, inside_radius=5.0,
          hole_diameter=6.6, holes_per_leg=2, gusset=False)
def l_bracket(leg_x, leg_z, width, thickness, inside_radius, hole_diameter, holes_per_leg, gusset):
    from build123d import Align, Axis, Box, Cylinder, Plane, Polygon, Pos, Rot, extrude, fillet
    a = (Align.MIN, Align.MIN, Align.MIN)
    p = Box(leg_x, width, thickness, align=a) + Box(thickness, width, leg_z, align=a)
    if inside_radius > 0:
        e = [e for e in p.edges().filter_by(Axis.Y)
             if abs(e.center().X - thickness) < 1e-6 and abs(e.center().Z - thickness) < 1e-6]
        if e:
            p = fillet(e, inside_radius)
    if gusset:
        g = extrude(Plane.XZ * Polygon((thickness, thickness), (leg_x * 0.8, thickness),
                                       (thickness, leg_z * 0.8), align=None), -thickness)
        p += Pos(0, width / 2 - thickness / 2, 0) * g
    if hole_diameter > 0:
        n = max(1, int(holes_per_leg))
        for k in range(n):
            y = width / 2 if n == 1 else width * (k + 1) / (n + 1)
            xh = thickness + inside_radius + (leg_x - thickness - inside_radius) * 0.6
            zh = thickness + inside_radius + (leg_z - thickness - inside_radius) * 0.6
            p -= Pos(xh, y, thickness / 2) * Cylinder(hole_diameter / 2, thickness * 3)
            p -= Pos(thickness / 2, y, zh) * Rot(0, 90, 0) * Cylinder(hole_diameter / 2, thickness * 3)
    return p


@template("flange", "Circular flange with a centre bore and a bolt circle, axis along Z",
          outer_diameter=120.0, bore=40.0, thickness=12.0, bolt_circle=90.0, bolt_hole=9.0,
          bolt_count=6, hub_diameter=0.0, hub_height=0.0)
def flange(outer_diameter, bore, thickness, bolt_circle, bolt_hole, bolt_count, hub_diameter,
           hub_height):
    import math
    from build123d import Align, Cylinder, Pos
    a = (Align.CENTER, Align.CENTER, Align.MIN)
    p = Cylinder(outer_diameter / 2, thickness, align=a)
    if hub_diameter > 0 and hub_height > 0:
        p += Pos(0, 0, thickness) * Cylinder(hub_diameter / 2, hub_height, align=a)
    total = thickness + max(hub_height, 0.0)
    if bore > 0:
        p -= Pos(0, 0, -1) * Cylinder(bore / 2, total + 2, align=a)
    for k in range(int(bolt_count)):
        ang = 2 * math.pi * k / int(bolt_count)
        p -= Pos(bolt_circle / 2 * math.cos(ang), bolt_circle / 2 * math.sin(ang), -1) * \
            Cylinder(bolt_hole / 2, thickness + 2, align=a)
    return p


@template("enclosure", "Open-top box enclosure with wall thickness, corner radius and screw bosses",
          length=100.0, width=70.0, height=40.0, wall=2.4, floor=2.4, corner_radius=4.0,
          boss_diameter=7.0, boss_hole=2.8)
def enclosure(length, width, height, wall, floor, corner_radius, boss_diameter, boss_hole):
    from build123d import Align, Axis, Box, Cylinder, Pos, fillet
    a = (Align.MIN, Align.MIN, Align.MIN)
    outer = Box(length, width, height, align=a)
    inner = Pos(wall, wall, floor) * Box(length - 2 * wall, width - 2 * wall, height, align=a)
    if corner_radius > 0:
        outer = fillet(outer.edges().filter_by(Axis.Z), corner_radius)
        if corner_radius > wall:
            inner = fillet(inner.edges().filter_by(Axis.Z), corner_radius - wall)
    p = outer - inner
    if boss_diameter > 0:
        off = wall + boss_diameter / 2
        ca = (Align.CENTER, Align.CENTER, Align.MIN)
        for x in (off, length - off):
            for y in (off, width - off):
                p += Pos(x, y, floor) * Cylinder(boss_diameter / 2, height - floor, align=ca)
                if boss_hole > 0:
                    p -= Pos(x, y, floor + 2) * Cylinder(boss_hole / 2, height, align=ca)
    return p


@template("standoff", "Round standoff / spacer with a through hole, axis along Z",
          outer_diameter=10.0, hole=4.3, height=20.0, base_diameter=0.0, base_height=0.0)
def standoff(outer_diameter, hole, height, base_diameter, base_height):
    from build123d import Align, Cylinder, Pos
    a = (Align.CENTER, Align.CENTER, Align.MIN)
    p = Cylinder(outer_diameter / 2, height, align=a)
    if base_diameter > 0 and base_height > 0:
        p += Cylinder(base_diameter / 2, base_height, align=a)
    if hole > 0:
        p -= Pos(0, 0, -1) * Cylinder(hole / 2, height + 2, align=a)
    return p


@template("curved_laminate", "Curved laminate section (bend of a formed part): arc about the Y axis "
          "from the +X direction through arc_deg, with optional straight flanges",
          inner_radius=6.0, thickness=2.24, arc_deg=90.0, width=20.0, flange=0.0)
def curved_laminate(inner_radius, thickness, arc_deg, width, flange):
    import math
    from build123d import Align, Axis, Box, Cylinder, Plane, Pos, Rot, extrude
    # annular sector in the XZ plane, extruded along Y; bend axis = global Y through the origin
    full = Cylinder(inner_radius + thickness, width) - Cylinder(inner_radius, width * 2)
    full = Rot(90, 0, 0) * full                      # cylinder axis -> Y
    big = 4 * (inner_radius + thickness) + 2 * max(flange, 0.0)
    # keep the wedge between angle 0 (the +X axis) and arc_deg, measured towards +Z
    cut1 = Pos(0, 0, -big / 2) * Box(big, big, big)                  # below the XZ start plane
    wedge = full - cut1
    a = math.radians(arc_deg)
    cut2 = Rot(0, -arc_deg, 0) * (Pos(0, 0, big / 2) * Box(big, big, big))
    wedge = wedge - cut2
    p = wedge
    if flange > 0:
        f1 = Pos(inner_radius + thickness / 2, 0, -flange / 2) * Box(thickness, width, flange)
        f2 = Rot(0, -arc_deg, 0) * (Pos(inner_radius + thickness / 2, 0, flange / 2) * Box(thickness, width, flange))
        p = p + f1 + f2
    return p


def build(name: str, params: dict | None = None, system: str | None = None):
    """Build a template with overrides given in the active unit system."""
    if name not in TEMPLATES:
        raise KeyError(f"unknown template {name!r}; available: {', '.join(TEMPLATES)}")
    fn, defaults, _ = TEMPLATES[name]
    args = dict(defaults)
    for k, v in (params or {}).items():
        if k not in defaults:
            raise KeyError(f"template {name!r} has no parameter {k!r}; accepts: {', '.join(defaults)}")
        d = defaults[k]
        if isinstance(d, bool):
            args[k] = bool(v)
        elif isinstance(d, int):
            args[k] = int(v)
        elif isinstance(d, float) and not k.endswith(("_deg", "_ratio")):
            args[k] = U.to_internal(v, "length", system)
        elif isinstance(d, float):
            args[k] = float(v)
        else:
            args[k] = v
    return fn(**args)


def build_to_step(name: str, params: dict | None, step: str | Path, system: str | None = None,
                  stl: bool = False, threemf: bool = False) -> dict:
    import json
    from .export import export
    from .inspect import inspect_shape
    part = build(name, params, system)
    info = inspect_shape(part)
    if not info["valid"] or info["solids"] != 1:
        raise ValueError(f"template {name!r} with these parameters does not give one valid solid "
                         f"(valid={info['valid']}, solids={info['solids']}); check the dimensions")
    files = export(part, step, stl=stl, threemf=threemf)
    info["files"] = [str(f) for f in files]
    info["template"] = name
    Path(step).with_suffix(".cad.json").write_text(json.dumps(info, indent=1), encoding="utf-8")
    return info


def catalog() -> list[dict]:
    return [{"name": n, "description": doc, "parameters": d} for n, (_, d, doc) in TEMPLATES.items()]
