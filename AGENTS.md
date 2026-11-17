# EngineeringAgent - instructions for AI agents

This repository is a CAD + FEA engineering toolkit (build123d, Gmsh, CalculiX) with hand
calculations, GD&T and verification reports. `CLAUDE.md` holds the full working rules;
they apply to every AI agent, not only Claude. Read it first. Summary:

## Commands

Run everything through the launcher: `./ea ...` (bash) or `.\ea.cmd ...` (PowerShell).
Add `--json` for machine-readable output.

    ./ea make <template|geometry.py> k=v --print [material]      ONE LINE: part + STL/3MF + print check + report
    ./ea analyze <part.step|template|last|jobs/NN> -m MAT --fix FACES --force FACES FX,FY,FZ --check "<calc>"
                                              ONE LINE: FEA with hand check, report and viewer
    ./ea request reply.txt                    run `ea` lines / ```json / ```python blocks (e.g. a chatbot reply)
    ./ea ask "plain English"                  needs a model (ENGAGENT_LLM_URL/MODEL/KEY); writes and runs the request
    ./ea prompt                               the request-writing instructions (docs/CHATBOT-PROMPT.md)
    ./ea doctor --full                        check the installation, run the benchmark
    ./ea units [metric|imperial]              show / switch the unit system for everything
    ./ea materials [key]                      material library
    ./ea calc list | ./ea calc <name> k=v     hand calculations with formulas and references
    ./ea cad templates | new | build | inspect | faces | export | printcheck
    ./ea fea new <folder> -a <type>           starter job.json (static, nonlinear, modal, buckling,
                                              thermal_steady, convection, thermal_transient,
                                              thermal_stress, spring_in, tie, contact, fatigue)
    ./ea fea run <folder> --converge --report solve, verify, write report + viewer
    ./ea gdt fit | general | hole | frame | stack | review | process
    ./ea report <folder>      ./ea view <folder> --open

## Rules

0. Read docs/CHATBOT-PROMPT.md for the one-line syntax and face selectors; prefer `make` / `analyze`.
1. Never invent loads, supports or materials. Ask once for what is missing. For pure CAD, pick
   sensible defaults instead of asking and say what you chose.
2. Check the unit system first (`./ea units`). Bare numbers follow it; strings may carry
   units ("0.25 in"). Never convert to solver units by hand.
3. Hand-calculate before running FEA and link it in the job's `hand_calcs`.
4. One folder per job under `jobs/`. Do not edit `examples/` or another job's files.
5. Change `job.json`, not `job.inp`. Do not call `ccx` directly.
6. Report only numbers the tools produced. A FAIL verdict or solver error is reported as
   such. REVIEW means something is unverified: say what.
7. Peak stress at supports, contacts and sharp corners is mesh-dependent: quote the
   design stress the tool reports and say so.
8. Results are engineering assistance, not sign-off.

## Where things are

| Path | Content |
| --- | --- |
| `CLAUDE.md` | full working rules |
| `.claude/skills/*/SKILL.md` | step-by-step playbooks per task (plain Markdown, readable by any agent) |
| `docs/job-reference.md` | every field of `job.json` |
| `docs/gdt.md`, `docs/mcp.md`, `docs/validation.md` | tolerancing tables, MCP setup, accuracy benchmarks |
| `examples/` | validated reference jobs |
| `engagent/` | the Python package (units, materials, cad, fea, handcalc, gdt, report, viewer, cli, mcp_server) |
| `tests/` | `pytest` (fast) and `pytest -m solver` (runs CalculiX) |

## Development

    .venv/bin/python -m pytest -q              # unit tests, a few seconds
    .venv/bin/python -m pytest -q -m solver    # benchmark FEA jobs against theory
