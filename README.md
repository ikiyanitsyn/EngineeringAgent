# EngineeringAgent

A CAD + FEA engineering companion you drive in plain language from Claude Code (or any
AI tool that can run commands or speak MCP).

- **Parametric CAD** with [build123d](https://build123d.readthedocs.io/) (OpenCascade):
  templates and scripts, STEP / STL / 3MF export, numerical verification, 3D-print checks.
- **FEA** with [Gmsh](https://gmsh.info/) and [CalculiX](https://www.calculix.de/): linear
  static, nonlinear (large deflection, plasticity), modal, buckling, steady and transient
  heat transfer, thermal stress, tied and contact assemblies, fatigue screening,
  orthotropic laminates.
- **Thermoplastic-composite manufacturing**: laminate theory, residual stress, spring-in,
  consolidation heat-up and cooling rates, tool-part mismatch.
- **Hand calculations**: 42 formulas with textbook references, linked to FEA jobs so
  every run checks itself.
- **Tolerancing / GD&T**: ISO 286 fits, ISO 2768, clearance holes, position tolerance,
  feature control frames, stack-ups, scheme review to ISO GPS or ASME Y14.5-2018.
- **Verification report** (HTML + PDF) and an **interactive viewer** with colour plots
  and animated deformation.
- **One unit toggle**: metric (mm, kg, N, MPa, degC) or imperial (in, lbm, lbf, psi,
  degF) for every skill, command, job and report.

The numerical work is done by a tested Python package, not improvised by the AI on each
run. Every analysis type is benchmarked against a closed-form answer
([docs/validation.md](docs/validation.md)).

## Start in one minute

| You have | Do this |
| --- | --- |
| **A phone or browser only** | **Issues > New issue > Engineering request**, describe what you need in plain English (or paste a chatbot reply), submit. GitHub runs it for free and replies with the numbers, `report.pdf` and `part.stl`; if something is missing it asks in a comment. |
| **A Windows PC** | **Code > Download ZIP**, extract, double-click **`START-HERE.cmd`**. It installs itself, then shows a menu (plain English with a free AI, Claude Code, results). |
| **Claude Code** | Open it in this repository and say what you need. It installs the tools itself if they are missing. |
| **ChatGPT / Gemini / Copilot / Claude.ai** | Paste [docs/CHATBOT-PROMPT.md](docs/CHATBOT-PROMPT.md) into the chat once, describe your part, paste the reply into an issue or `START-HERE` option 4. |

A request is a few plain lines - any chatbot can write them, or you can:

    ea make l_bracket thickness=6 --print petg
    ea analyze last -m al_6061_t6 --fix hole:6.6@40,20,0 --force hole:6.6@0,20,40 -300,0,0 --sf 2

Or just write plain English. In a GitHub issue this works with no setup (a free open model
runs on GitHub's machine); on your PC `ea ask "printable PETG wall hook for a 5 kg coat"`
uses Ollama if it is running, or a free Gemini key.

**Beginner walkthrough: [docs/USER-GUIDE.md](docs/USER-GUIDE.md)** (Windows, iPhone, free AI models).

## Install (only for running on your own computer)

`START-HERE.cmd` does all of this on Windows. Manually:

Requirements: Git, Python 3.10-3.13 (3.12 recommended), about 2 GB of disk.

**Windows (PowerShell, no administrator rights):**

    git clone https://github.com/<you>/EngineeringAgent.git
    cd EngineeringAgent
    powershell -ExecutionPolicy Bypass -File scripts\setup.ps1

**Linux / macOS:**

    git clone https://github.com/<you>/EngineeringAgent.git
    cd EngineeringAgent
    bash scripts/setup.sh

Setup creates `.venv`, installs the Python packages, installs the CalculiX solver
(Windows: downloaded from dhondt.de into `tools\calculix`; Linux: `apt`/`dnf`; macOS:
Homebrew) and runs a benchmark. It ends with `READY` when FEA matches beam theory.

Then start Claude Code in the folder:

    claude

## Talking to it

Ask in plain language. The skills in `.claude/skills/` load automatically.

> Design an aluminium L-bracket, 60 x 60 x 40 mm, 5 mm thick, two M6 holes per leg.
> It is bolted through the base and carries 300 N on the upright. Is it strong enough
> with a safety factor of 2? Give me a report.

> Switch to imperial units.

> Make me a printable PETG enclosure 100 x 70 x 40 mm with 2.4 mm walls and check it
> for FDM printing.

> What fit should I use for a 25 mm shaft that must slide in a bore? Show the limits.

> We stamp-form a 16-ply quasi-isotropic CF/PEEK L-section. How much spring-in should
> the tool compensate for, and how long until the mid-plane reaches 380 degC in the press?

The agent restates the problem, asks for anything missing (it does not guess loads,
supports or materials), hand-calculates, builds the model, runs it, checks it and
reports the answer with the checks.

## Skills

| Skill | Use it for |
| --- | --- |
| `engineering-units` | metric / imperial toggle, conversions |
| `cad-modeling` | parametric parts and assemblies, STEP export, CAD verification |
| `cad-3d-printing` | printable design, printability check, STL / 3MF |
| `hand-calcs` | sizing and prediction with referenced formulas |
| `fea-mechanical` | static, nonlinear, modal, buckling, fatigue |
| `fea-thermal` | conduction, convection, radiation, transient, thermal stress |
| `fea-assembly` | multi-part models: tie and contact, bolt checks |
| `composites-manufacturing` | laminates, spring-in, consolidation, cooling, tooling |
| `gdt-tolerancing` | fits, datums, feature control frames, stack-ups |
| `results-review` | is the result trustworthy? |
| `engineering-report` | HTML/PDF verification report and viewer |

## Command line

Everything the agent does is also a command (`./ea` in Git Bash / Linux / macOS,
`.\ea.cmd` in PowerShell):

    ./ea doctor --full                       # environment check + benchmark
    ./ea units imperial                      # toggle units for everything
    ./ea materials                           # 36 library materials
    ./ea ask "printable PETG phone stand, 80 mm wide"   # plain English (needs a free model)
    ./ea make enclosure length=100 width=70 height=40 --print petg
    ./ea analyze part.step -m al_6061_t6 --fix zmin --force xmax 0,0,-500 --check "..."
    ./ea calc beam.cantilever_end_load P=100 L=100 E="210 GPa" b=10 h=10
    ./ea cad new jobs/01-bracket --template l_bracket -p thickness=6 --stl
    ./ea cad printcheck jobs/01-bracket/part.step -m petg
    ./ea fea new jobs/02-beam -a static      # starter job.json with a hand calculation
    ./ea fea run jobs/02-beam --converge --report
    ./ea gdt fit 25 H7/g6
    ./ea view jobs/02-beam --open

## A job in one file

    {
      "title": "Bracket under 300 N", "analysis": "static",
      "geometry": {"script": "geometry.py"},
      "material": "al_6061_t6",
      "mesh": {"size": 3, "refine": [{"on": "corner", "size": 1}]},
      "sets": {"holes": {"cylinder": {"radius": 3.3, "axis": "z"}}, "corner": {"cylinder": {"radius": 5}},
               "load": {"cylinder": {"radius": 3.3, "axis": "x"}}},
      "constraints": [{"type": "fixed", "on": "holes"}],
      "loads": [{"type": "force", "on": "load", "value": [-300, 0, 0]}],
      "hand_calcs": [{"name": "Upright bending", "calc": "beam.cantilever_end_load",
                      "inputs": {"P": 300, "L": 37, "E": "68.9 GPa", "b": 40, "h": 5, "x": 17},
                      "output": "stress_at_x", "metric": "probe.upright.szz", "tol": 0.15}],
      "probes": {"upright": {"point": [0, 20, 22]}},
      "criteria": {"yield_sf": 2.0, "max_displacement": 0.5}
    }

`./ea fea run` meshes, solves, compares with the hand calculation and prints a verdict:
**PASS** (all checks done and passed), **REVIEW** (something not verified) or **FAIL**.
Full field list: [docs/job-reference.md](docs/job-reference.md).

## Repository layout

    CLAUDE.md, AGENTS.md        rules for the AI agent
    .claude/skills/             task playbooks
    engagent/                   Python package: units, materials, cad, fea, handcalc, gdt, report, viewer, cli, mcp_server
    examples/                   validated reference jobs (13 benchmarks + bracket design review + printed enclosure)
    jobs/                       your work, one folder per job
    docs/                       job reference, tolerancing tables, MCP setup, validation, review of the original guide
    scripts/                    setup for Windows / Linux / macOS
    tests/                      unit tests and solver benchmarks
    engagent.config.json        unit system, tolerancing standard, solver threads (committed: follows the repo)

## Other AI tools

Any tool that runs shell commands can use `./ea ... --json` and reads `AGENTS.md`.
MCP-capable clients (Claude Desktop, Cursor, LM Studio, Gemini CLI, Continue, Goose and
others, including local free models with tool calling) can use the bundled MCP server:
see [docs/mcp.md](docs/mcp.md).

## Limits you should know

- This is engineering assistance, not sign-off. Anything safety-critical or subject to
  certification needs independent verification by a qualified engineer.
- Library material data are typical values. Use certified or supplier data for decisions.
- Solid tetrahedral elements only (no shells or beams): thin sheet-metal and long slender
  frames need fine meshes or a different tool.
- Laminates are smeared orthotropic solids; ply stresses come from laminate theory.
- Bolt preload is checked by hand calculation, not modelled in the FE mesh.
- The solver runs on one thread by default because multithreaded CalculiX 2.21 gave
  intermittently wrong results in testing ([docs/validation.md](docs/validation.md)).
- Check your employer's policy before processing proprietary or export-controlled
  geometry with AI tools.

## Development

    .venv/bin/python -m pytest -q             # unit tests
    .venv/bin/python -m pytest -q -m solver   # FEA benchmarks against theory

Background: [docs/guide-review.md](docs/guide-review.md) explains how this differs from
the step-by-step guide it started from.
