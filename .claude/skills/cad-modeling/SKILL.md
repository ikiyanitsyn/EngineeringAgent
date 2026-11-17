---
name: cad-modeling
description: Build parametric 3D CAD models in Python with build123d (OpenCascade) and export STEP, STL or 3MF. Use when the user asks to design, model, draw, change or parametrise a part or assembly (bracket, plate, beam, housing, flange, enclosure, tube, fixture, tool), needs geometry for FEA, or wants a CAD file checked (volume, mass, bounding box).
---

# Parametric CAD with build123d

**Fast path:** `./ea make <template> name=value ... --print [material]` builds STEP, STL, 3MF,
the print check and a report in a new `jobs/NN-name` folder. For custom shapes write
`jobs/NN-name/geometry.py` (pattern below) and run `./ea make jobs/NN-name/geometry.py --print petg`.
Templates: `./ea cad templates`. Do not interview the user about CAD details: choose and state defaults.

## Steps

1. Restate the part: every dimension, features (holes, fillets, ribs, pockets), where
   the origin is and which way the axes point. Ask about anything missing. Never silently
   change a dimension the user gave.
2. Check whether a template fits: `./ea cad templates`
   (beam, plate, l_bracket, flange, enclosure, standoff, curved_laminate).
   `./ea cad new jobs/NN-name --template l_bracket -p leg_x=80 -p thickness=6 --stl`
3. Otherwise write `jobs/NN-name/geometry.py` (pattern below) and run it:
   `./ea cad build jobs/NN-name/geometry.py --stl`
   Override parameters without editing the file: `-p length=120 -p hole_count=6`.
4. Verify numerically before saying it worked: `./ea cad inspect jobs/NN-name/part.step -m al_6061_t6`
   - valid solid, exactly the number of bodies intended
   - bounding box equals the overall dimensions the user gave
   - volume matches a hand estimate (gross block minus holes/pockets) within a few percent
   - mass = volume x density when a material is known
5. Report: overall size, volume, mass, origin and axes, what was left out and why.

## Script pattern

    from build123d import *
    from engagent.cad import params, save

    # Lengths are floats in mm. Counts are ints. Angles end in _deg.
    P = params(length=100.0, width=40.0, thickness=5.0, hole_dia=6.6, hole_count=2, edge=10.0)

    plate = Box(P.length, P.width, P.thickness, align=(Align.MIN, Align.MIN, Align.MIN))
    for i in range(P.hole_count):
        x = P.edge + i * (P.length - 2 * P.edge) / max(P.hole_count - 1, 1)
        plate -= Pos(x, P.width / 2, P.thickness / 2) * Cylinder(P.hole_dia / 2, P.thickness * 2)

    # Faces for analysis: x = 0 (support), x = length (load), z = thickness (pressure)
    save(plate)          # validates, writes part.step and part.cad.json, prints a summary

`save(part, stl=True, threemf=True)` also writes print files. `save` refuses an invalid
or empty shape, so a script that finishes has produced a usable solid.

## Rules

- Every dimension is a named parameter in `params(...)`; no magic numbers in the body.
- Put the part where analysis is easy: a support face on a coordinate plane (x = 0),
  the long axis along +X, symmetric parts centred on the symmetry plane.
- Algebra mode (`Box`, `Cylinder`, `Pos`, `Rot`, `+`, `-`) for simple solids. Builder
  mode (`BuildPart`, `BuildSketch`, `extrude`, `revolve`, `sweep`, `loft`) for
  sketch-driven shapes. Build 2D profiles first, add fillets and chamfers last.
- Select edges for fillets by geometry, not by index:
  `part.edges().filter_by(Axis.Z)`, `.group_by(Axis.Z)[-1]`, `.sort_by(Axis.X)[0]`.
- Model for the purpose. For FEA leave out cosmetic detail (logos, threads, tiny fillets)
  unless it matters for stress or heat flow, but keep fillets at stress concentrations.
  For manufacturing or printing keep everything. Say what you left out.
- In a comment, list the faces that will carry supports and loads with their coordinates.
- Assemblies: one script and one STEP per part, positioned in the common assembly
  coordinate system. Mating faces must coincide (zero gap) for tie/contact in FEA.
- If a build123d function is missing or behaves unexpectedly in the installed version,
  check https://build123d.readthedocs.io/ instead of guessing. Print
  `build123d.__version__` if needed.
- Imperial drawings: keep the script in mm. Either pass inch values as overrides
  (`-p length="4 in"`) or write `length=101.6  # 4.000 in`.

## Finding faces

`./ea cad faces part.step` lists every face with tag, type, area, centroid, outward
normal and radius. Use it to write selectors for FEA sets:

    "xmin" ... "zmax"                          face(s) on the extreme plane
    {"plane": "x", "at": 25}                   planar face(s) at x = 25
    {"cylinder": {"radius": 3.3}}              all cylindrical faces of that radius
    {"cylinder": {"radius": 3.3, "near": [10, 20, 0]}}   the hole nearest a point
    {"normal": [0, 0, 1]}                      planar faces facing +Z
    {"near": [x, y, z]}                        the single face closest to a point
    {"box": [x0, y0, z0, x1, y1, z1]}          faces wholly inside a box
    {"faces": [3, 7]}                          by tag
    {"part": "bracket", "plane": "z", "at": 0} restrict to one part of an assembly
    [selector, selector]                       union;  {"...": ..., "exclude": selector}

## Exports

    ./ea cad export part.step --stl --3mf --quality fine     # draft | standard | fine | ultra
    ./ea cad export part.step --stl --scale 1.004            # shrinkage-compensated copy

STEP is the engineering master (exact geometry, used for meshing and for sending to a
machine shop). STL/3MF are for printing and viewing only.
