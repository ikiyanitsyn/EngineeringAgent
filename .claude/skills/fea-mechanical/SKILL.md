---
name: fea-mechanical
description: Run mechanical finite element analysis with Gmsh and CalculiX on a STEP model - linear static stress and deflection, nonlinear static (large deflection, plasticity), modal natural frequencies, linear buckling, and fatigue screening. Use for stress, deflection, reaction force, safety factor, stiffness, natural frequency, buckling load, yield or fatigue life questions, or "will this part hold the load".
---

# Mechanical FEA

Jobs are a `job.json` in the job folder. The toolkit meshes (10-node tetrahedra),
writes the CalculiX deck, solves, reads the results, compares with the hand
calculation and runs the verification checklist.

## Steps

1. Confirm with the user: material (E, nu, yield - or a library key from
   `./ea materials`), supports, loads (size, direction, which face), the answer wanted,
   the acceptance criterion (safety factor, deflection limit, minimum frequency).
   Ask if anything is missing. Do not assume.
2. Hand-calculate the expected result (`hand-calcs` skill).
3. Geometry: `cad-modeling` skill. Then `./ea cad faces <part.step>` and choose faces.
4. Start from a working example of the right type and edit it:

       ./ea fea new jobs/NN-name -a static      # static | nonlinear | modal | buckling | fatigue

5. Run with a convergence check and a report:

       ./ea fea run jobs/NN-name --converge --report

6. Read the output top to bottom: verdict, results, hand-calc comparison, checklist.
   Then apply the `results-review` skill before telling the user anything.

## Job essentials (full reference: docs/job-reference.md)

    {
      "name": "bracket", "title": "Bracket under 500 N", "analysis": "static",
      "geometry": {"script": "geometry.py"},            // or {"step": "part.step"} or {"template": ..., "params": {...}}
      "material": "al_6061_t6",                         // or {"E": "70 GPa", "nu": 0.33, "yield": 276, "density": 2700}
      "mesh": {"size": 3, "refine": [{"on": "hole", "size": 0.8}]},
      "sets": {"base": "zmin", "hole": {"cylinder": {"radius": 4}}, "tip": "xmax"},
      "constraints": [{"type": "fixed", "on": "base"}],
      "loads": [{"type": "force", "on": "tip", "value": [0, 0, -500]}],
      "probes": {"tip": {"set": "tip"}, "root": {"point": [10, 0, 5]}},
      "hand_calcs": [ ... ],
      "criteria": {"yield_sf": 2.0, "max_displacement": 0.5}
    }

Constraints: `fixed`, `displacement` (`x`, `y`, `z` values; non-zero = prescribed
motion), `symmetry` (`normal`), `minimal` (3-2-1, removes rigid-body motion only).
A set can also be a single node: `{"point": [x, y, z]}`.

Loads: `force` (total vector on a face), `pressure` (positive pushes into the face),
`moment` (vector about the face centroid), `gravity` (`"g": [0, 0, -1]`), `centrifugal`
(`rpm`, `point`, `axis`), `temperature_change` (thermal_stress only).

Results you can name in `hand_calcs` and `criteria`: `max_displacement`,
`max_von_mises` (design value, away from supports), `peak_von_mises`,
`max_principal`, `min_principal`, `safety_factor_yield`, `reaction_total`,
`reaction.<set>`, `frequency_1...`, `buckling_factor_1...`, `max_plastic_strain`,
`angle.<name>`, and per probe `probe.<name>.ux|uy|uz|displacement|sxx|...|von_mises`.

## Mesh

- Default element size is the bounding-box diagonal / 25. Set `mesh.size` so that the
  thinnest loaded section has at least 2 elements through it (3-4 for bending).
- Refine where stress matters (holes, fillets, notches): `"refine": [{"on": "<set or
  selector>", "size": s, "distance": d}]`. Aim for 6-8 elements around a quarter fillet.
- Keep quadratic elements (`"order": 2`, the default). Linear tets are too stiff in bending.
- `--converge` re-runs at half the element size and compares key results (5 % limit).
  Always do it before anyone acts on the numbers.

## Analysis types

**static** - linear elastic, small displacement. Check `safety_factor_yield` against the
criterion. If the checklist says displacement is large or stress exceeds yield, switch to
nonlinear.

**nonlinear** - `"analysis": "nonlinear"`, options
`"nonlinear": {"nlgeom": true, "plasticity": true}`. Plasticity uses the material's
yield/UTS/elongation as a bilinear curve, or an explicit table
`"material": {"base": "steel_s355", "plastic": [[355, 0], [470, 0.05], [510, 0.15]]}`
(true stress, plastic strain). Reports `max_plastic_strain`. If it does not converge,
reduce `"initial_increment"`, check supports, or apply the load as a prescribed
displacement.

**modal** - `"analysis": "modal", "modal": {"modes": 6}`. Needs density. No loads.
Supports as in service; with no supports the first six modes are rigid-body (near 0 Hz).
Mode shapes are normalised - amplitudes are not physical. Criterion: `"min_frequency"`.

**buckling** - `"analysis": "buckling", "buckling": {"modes": 4}`. Apply the service
load; the factor multiplies it to give the critical load. Eigenvalue buckling assumes a
perfect elastic structure and over-predicts: require a factor of 3 or more, compare
with `column.euler_buckling` (check the Johnson limit for short columns), and for
thin shells or anything near the limit run nonlinear with an imperfection.

**fatigue** - add to a static job:
`"fatigue": {"R": 0, "surface": "machined", "loading": "bending", "reliability": 0.9,
"required_sf": 1.5, "size": 20, "Kf": 1.0}`. Uses the design-zone maximum principal
stress as the cyclic maximum, Marin factors, Goodman/Gerber/Soderberg and a Basquin
life. Stress-life screening only: it does not replace a fatigue analysis for welded,
notched-to-yield, variable-amplitude or safety-critical parts. Non-steels need a tested
fatigue strength (`"endurance": "95 MPa"`).

## Rules

- Never put a force on a single node unless the user wants that singularity.
- Supports: fix only what is really held. Over-constraining hides flexibility and
  thermal growth; under-constraining gives a singular matrix (solver error).
- Use symmetry (`"type": "symmetry"`) to cut model size, never to guess a boundary.
- Stress at fixed faces, contact edges and sharp inside corners is mesh-dependent. The
  toolkit reports `max_von_mises` outside those zones (default: 2 element sizes from
  supports). If the real peak of interest is at a fillet near a support, shrink the
  zone with `"stress_exclusion": {"distance": 1.0}` and refine the mesh there.
- Do not edit `job.inp` by hand and re-run `ccx` yourself; change `job.json`.
- If the solver fails, read the quoted `*ERROR`, fix the job, re-run. Common causes:
  unsupported part (singular matrix), a set that matched no face, missing material value.
