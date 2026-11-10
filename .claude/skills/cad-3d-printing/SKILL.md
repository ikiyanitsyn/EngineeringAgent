---
name: cad-3d-printing
description: Design and check parts for 3D printing (FDM/FFF, SLA, SLS, MJF, metal powder bed) - wall thickness, overhangs and supports, orientation, build volume, hole compensation, tolerances, shrinkage, printed mass, STL/3MF export. Use when the user wants a printable part, an STL or 3MF, asks "will this print", or mentions a printer, filament, resin, infill or layer height.
---

# CAD for 3D printing

## Ask first

Process (FDM, SLA, SLS, MJF, DMLS), material, printer build volume and nozzle if unusual,
what the part must do (load, temperature, fit with other parts), which surfaces matter.

## Steps

1. Model the part with the `cad-modeling` skill, applying the design rules below.
2. Export and check:

       ./ea cad build jobs/NN-name/geometry.py --stl --3mf
       ./ea cad printcheck jobs/NN-name/part.step --process fdm -m petg
       ./ea cad printcheck part.step --process fdm -m petg --build 220 220 250 --orientation +X

   The check measures: valid solid, build-volume fit, thinnest wall (ray-cast sample),
   overhang area and support volume, bed contact, hole sizes, the best of six
   orientations, expected accuracy, shrinkage scale, printed mass.
3. Fix every FAIL in the CAD and re-run. Explain each WARN and what you recommend.
4. Tell the user: orientation, supports needed or not, material and infill assumed,
   printed mass, holes to ream or drill, expected accuracy, files written.
5. If the part carries load, run FEA (`fea-mechanical`) with the print material and
   derate for layer direction (see below). For a record, add a `"print"` block to
   `job.json` and build a report (`engineering-report`).

## Design rules by process (defaults the checker uses)

| | FDM | SLA | SLS / MJF | DMLS |
| --- | --- | --- | --- | --- |
| minimum wall | 0.8 mm (2 perimeters) | 0.5 mm | 0.7 / 0.5 mm | 0.4 mm |
| wall for strength | 1.2 mm or more | 1.0 mm | 1.0 mm | 0.8 mm |
| overhang without support | 45 deg from vertical | 30 deg | none needed | 45 deg |
| smallest reliable hole | 2 mm | 0.8 mm | 1.5 / 1.0 mm | 1.0 mm |
| holes print undersize by | about 0.2 mm | 0.1 mm | 0.15 mm | 0.1 mm |
| typical accuracy | +/-0.2 mm or 0.2 % | +/-0.1 mm | +/-0.3 mm or 0.3 % | +/-0.1 mm |

- Clearances for parts that must fit: sliding 0.2-0.3 mm per side (FDM), press 0.0-0.1 mm,
  snap-fit hooks need 0.3-0.5 mm relief. Use `./ea gdt process fdm 50 0.1` to test a
  tolerance against the process.
- Holes for screws: model the ISO 273 clearance hole plus the undersize allowance, or
  drill after printing. Self-tapping into plastic: pilot = 0.8 x screw diameter. Heat-set
  inserts: follow the insert maker's hole size, wall around the insert >= 1.5 mm.
- Orient so that the main load runs along the layers, not across them. FDM strength
  across layers (Z) is typically 40-70 % of in-plane strength.
- Horizontal holes above 8 mm sag: use a teardrop shape or accept supports.
- Fillet the bed-contact edge with a chamfer, not a fillet (a fillet there is an overhang).
- Avoid large flat areas on the bed for ABS/ASA/PC/PA (warping); add ribs instead of mass.
- Powder-bed parts: add escape holes (>= 4 mm) to hollow sections.
- Shrinkage: the checker prints a scale factor per material; apply with
  `./ea cad export part.step --stl --scale <factor>` only if the slicer does not compensate.

## Strength of printed parts in FEA

Library print materials (`pla`, `petg`, `abs`, `asa`, `pa12_sls`, `pa6_cf_fdm`, `pc`,
`resin_tough_sla`) hold in-plane properties of well-printed solid material. For a
quick, conservative check:

- use the library material and require a yield safety factor of at least 2 for FDM
  loaded along the layers, at least 3-4 when load crosses layers, and
- reduce stiffness in proportion to infill if the part is not printed solid
  (`"material": {"base": "petg", "E": 1200}`), and say that you did.

State these as assumptions in the answer. Printed parts vary a lot with machine and
settings; a test print is the real verification.
