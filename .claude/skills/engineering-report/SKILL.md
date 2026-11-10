---
name: engineering-report
description: Produce the final engineering verification report (HTML and PDF) and the interactive results viewer for a job - summary and verdict, problem definition, CAD verification, FEA results with plots, hand calculations versus FEA, verification checklist, GD&T and tolerance review, 3D-print check, standards, assumptions and sign-off block. Use when the user asks for a report, a write-up, documentation for a design review, or to see colour plots and animated deformation.
---

# Verification report and viewer

    ./ea fea run jobs/NN-name --converge --report      # solve + report.html + report.pdf + viewer.html
    ./ea report jobs/NN-name                           # (re)build the report from existing results
    ./ea report jobs/NN-name -f html                   # one format only
    ./ea view jobs/NN-name --open                      # interactive viewer in the browser

## What the report contains

1. Summary - verdict (PASS / REVIEW / FAIL), key results, items needing attention,
   acceptance criteria.
2. Problem definition - analysis type, unit system, materials with properties, supports,
   loads, interactions, named faces.
3. CAD model verification - valid solid, bodies, bounding box, volume, area, centre of
   mass, mass.
4. Finite element model - element type, node/element counts, size, quality, solver.
5. Results - colour plots, result table, where stresses were taken.
6. Hand calculations - formula, inputs, reference, hand value versus FEA, difference.
7. Verification checklist, mesh convergence table.
8. Fatigue screening (if requested).
9. Dimensioning and tolerancing review (if the job has a `"gdt"` block).
10. 3D-printing check (if the job has a `"print"` block).
11. Standards and references, assumptions and limitations, review/approval block.

The report follows the job's unit system and tolerancing standard. PDF page size is A4
for metric and Letter for imperial.

## Getting a complete report

Add what applies to `job.json` before building:

    "description": "What the part is, what it does, where the loads come from.",
    "criteria": {"yield_sf": 2.0, "max_displacement": 0.5},
    "hand_calcs": [ ... ],                      // hand-calcs skill
    "gdt": { ... },                             // gdt-tolerancing skill
    "print": {"process": "fdm", "material": "petg", "infill": 0.4}     // cad-3d-printing skill

Design-only report (no FEA): a `job.json` with `title`, `geometry`, `material` and any
of `gdt` / `print`, then `./ea report jobs/NN-name`.

## Viewer

`viewer.html` is one self-contained file (no internet needed): choose the field (von
Mises, principal stresses, displacement, temperature, heat flux, plastic strain, mode
shape), choose the frame (time step or mode), scale and animate the deformation, show
element edges and the undeformed outline, banded colours, hover for values. It can be
e-mailed or attached to a review as is.

## Rules

- Build the report only after `results-review`. Do not hand over a report whose verdict
  you cannot explain.
- The verdict is computed from the checks; never edit report files to change it. If it
  says REVIEW or FAIL, fix the model or tell the user why it stands.
- In your message give: the verdict, the two or three numbers that answer the question,
  what needs attention, and the paths of `report.pdf`, `report.html` and `viewer.html`.
- The report states that it is engineering assistance, not sign-off. Keep that. The
  "Checked by / Approved by" block is for the user's own process.
- Proprietary or export-controlled geometry: remind the user to follow their
  organisation's rules before sharing report files.
