# Review of the original guide and what changed

The starting point was the guide "Building an FEA + CAD Engineering Agent with Claude
Code" (four `SKILL.md` playbooks, a `CLAUDE.md`, and three test prompts). Its core ideas
are sound and are kept: hand-calculate first, one folder per job, a fixed unit set,
check equilibrium and convergence, be honest about singularities, treat results as
assistance rather than sign-off.

Its weakness is that everything except those rules is left to the model to improvise on
every run: the meshing script, the CalculiX deck, the result parsing and the checks.

| Issue in the guide | Consequence | What this repository does |
| --- | --- | --- |
| The agent writes `mesh.py` and `job.inp` from scratch for every job | Different code each time; keyword and set-name mistakes; slow; nothing to regression-test | A tested Python package (`engagent`) builds mesh, deck and post-processing from a declarative `job.json` |
| Relies on Gmsh `.inp` export and tells the agent to "swap the last two nodes if you write connectivity yourself" | Easy to get wrong silently; a stiff or garbage model | Mesh read through the Gmsh API, node order converted in one place, element volumes checked |
| "Spread *CLOAD over the load-face nodes" | Equal nodal forces on quadratic faces are wrong (corner nodes carry zero for uniform traction) | Consistent nodal loads from face areas; forces, moments and pressures all statically exact |
| `OMP_NUM_THREADS = 4` for every run | In testing, multithreaded CalculiX 2.21 intermittently returned wrong stresses, reactions and buckling factors | Serial solver by default; see `docs/validation.md` |
| Units: one fixed set (mm, tonne, s) the user and agent must convert to by hand; no imperial | The classic factor-1000 errors; unusable for inch drawings | Unit-aware inputs everywhere, a single metric/imperial toggle, conversion done by code and covered by tests |
| Checks are a list the agent is asked to perform and report | Depends on the model remembering and doing arithmetic correctly | Checks are computed: equilibrium, heat balance, hand-calc difference, convergence run, singularity zone, linear validity, criteria, verdict |
| "Quote stress away from the singularity" | No definition of "away" | Design stress excludes a stated distance from supports/contacts; peak reported separately; refinement tells you if it is singular |
| Stress compared at the nearest node | Mesh-dependent comparison | Local least-squares probes at a point |
| Scope: linear static, modal, steady/transient thermal, thermal stress | No buckling, plasticity, contact, fatigue, composites | Adds buckling, nonlinear (large deflection, plasticity), tied and contact assemblies, fatigue screening, orthotropic laminates, spring-in, process heat-up/cool-down |
| Hand calculations left to the model | Unreferenced arithmetic | 42 registered calculations with formulas and textbook references, callable and linkable to a job |
| No tolerancing | "Meets engineering standards" cannot be shown | ISO 286 fits, ISO 2768, clearance holes, position tolerance, feature control frames, stack-ups, scheme review for ISO GPS and ASME Y14.5 |
| CAD only as input to FEA | No support for printing or manufacture | Templates, parametric scripts with overrides, STEP/STL/3MF export, printability check |
| `report.md`, one page | Not a deliverable | HTML and PDF verification report with plots, hand calcs, checklist, GD&T, sign-off block |
| ParaView as optional viewer | Extra install, not shareable | Self-contained `viewer.html` with colour plots and animated deformation |
| Windows only, manual solver download, hard-coded `C:\calculix` | Not portable across machines | Setup scripts for Windows / Linux / macOS, solver auto-discovery, `./ea` launcher, CI |
| Claude Code only | - | CLI with `--json`, `AGENTS.md`, MCP server (24 tools) for other AI clients |
| No automated tests ("rerun the beam after changes") | Regressions go unnoticed | 46 unit tests + 20 solver benchmarks, `./ea doctor --full` |

Details in the guide that were checked and kept: the thermal unit conversions (1 W/m/K
= 1 mW/mm/K; 1 J/kg/K = 1e6 mJ/tonne/K; 1 W/m^2/K = 1e-3 mW/mm^2/K; Stefan-Boltzmann
5.67e-11 mW/mm^2/K^4) are correct and are in the unit tests; the three benchmark
problems are the first three examples and reproduce the guide's expected numbers
(0.190 mm, 60 MPa, 4 W, 126 MPa).

One correction: the guide suggests `*UNCOUPLED TEMPERATURE-DISPLACEMENT` for thermal
stress in general. For a uniform temperature change that step is unnecessary and needs
conductivity data; the toolkit uses a plain static step with a prescribed temperature
there and the uncoupled procedure only when a temperature field has to be solved.
