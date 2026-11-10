---
name: results-review
description: Check finite element results for correctness before reporting them - solver errors, units, equilibrium, agreement with hand calculation, mesh convergence, singularities, linear validity and plausibility. Use after every FEA run, when the user asks whether a result can be trusted, when FEA and hand calculation disagree, and before writing a report.
---

# Results review

FEA returns a confident-looking answer even when the model is wrong. `./ea fea run`
prints a checklist; your job is to read it critically, close the gaps, and only then
report. Each item is PASS, FAIL, REVIEW (shown as WARN in JSON) or NOT DONE.

    ./ea fea run jobs/NN-name --converge --report
    ./ea fea run jobs/NN-name --json            # machine-readable; also saved in results.json

## The checks and what to do

1. **Solver finished** - any `*ERROR` is a FAIL: quote it, fix the job, re-run. List
   warnings and say whether each matters.
2. **Units and material** - values are converted by the toolkit; this flags implausible
   properties (E outside 50 MPa-1200 GPa, density outside 10-30 000 kg/m^3). If it
   fires, the user's number or unit is wrong: ask.
3. **Mesh** - quadratic elements, minimum quality above 0.1. Low quality: refine or
   remove sliver faces in the CAD.
4. **Equilibrium** - reactions equal applied load within 0.1 %. A mismatch means a load
   on the wrong set or an unintended support. Thermal: heat in = heat out.
5. **Hand calculation** - within the stated tolerance. NOT DONE is not acceptable for a
   result someone will act on: add a `hand_calcs` entry (`hand-calcs` skill).
   If it fails, find the cause before reporting anything:
   - factor 1000 or 1e6: unit error in an input
   - load reaction correct but deflection off: wrong section, modulus, or support stiffness
   - stress off but deflection fine: comparing at a singularity or the wrong component/location
   - 5-10 % stiff: mesh too coarse or linear elements
   - FEA softer than beam theory by about 1 %: shear deflection (add `nu` to the beam calc)
6. **Mesh convergence** - run with `--converge`. Displacement, frequency, buckling
   factor and design stress should change by less than 5 % at half the element size.
   If not: refine (`mesh.size`, `mesh.refine`) and repeat until they do.
7. **Singularities** - peak stress at fixed faces, contact edges, point loads and sharp
   inside corners grows without limit as the mesh is refined. The toolkit reports the
   peak and a design stress outside the support/contact zone and tells you when the
   peak is inside it. Never quote a singular peak as a design value. If the checklist
   says the peak is in the design zone and not converging, there is a sharp corner:
   add the real fillet radius and refine, or exclude it explicitly and say why.
8. **Linear validity** - displacement above about 5 % of the smallest overall dimension,
   or stress above yield, means the linear result is not valid: re-run as `nonlinear`.
9. **Plausibility** - displacement in the direction of the load; steady temperatures
   between the boundary values; a positive buckling factor; mode shapes that look like
   the part vibrating, not a loose piece.
10. **Acceptance criteria** - safety factor, deflection, frequency, buckling factor,
    temperature against the user's limits.

Open `viewer.html` (or the plots in the report) and look: is the part deforming the
way a physical part would under that load? Is the hot spot where the heat goes in?

## Verdict

- **PASS** - every check done and passed.
- **REVIEW** - nothing failed but something was not verified. Tell the user exactly
  what is open and what it would take to close it.
- **FAIL** - at least one check failed. Do not present the numbers as an answer.

## Reporting to the user

Lead with the answer and its unit, then the safety factor or margin against the
criterion, then the checks (one line each), then assumptions and limitations, then the
files. Say which stress you quoted (design or peak) and where it is. Say plainly when
something is outside what was verified.
