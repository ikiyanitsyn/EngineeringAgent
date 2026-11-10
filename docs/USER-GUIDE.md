# EngineeringAgent user guide (start here)

This guide assumes no coding experience. You type what you want in plain English; the
agent builds the 3D model, runs the analysis, checks its own work and hands you files.

## 1. What this is, in plain words

EngineeringAgent is a folder (a GitHub repository) containing:

- **tools** that do the engineering maths: a CAD engine, a stress/heat solver, a
  library of hand formulas, tolerance tables and a report writer;
- **instructions** that teach an AI assistant (Claude Code, or another AI) how to use
  those tools properly and honestly.

You talk to the AI. The AI runs the tools. You get files.

A few words you will see:

| Word | Meaning |
| --- | --- |
| CAD | the 3D computer model of a part |
| STEP file (`.step`) | exact 3D geometry; what machine shops and analysis use |
| STL / 3MF file | a triangle mesh of the surface; what 3D-printer slicers use |
| FEA | finite element analysis: the computer splits the part into thousands of small pieces ("mesh") to calculate stress, deflection or temperature |
| Load | what pushes, pulls or heats the part (force, pressure, temperature) |
| Support / constraint | where the part is held |
| Safety factor | strength divided by stress; 2.0 means the part could take twice the load before yielding |
| Hand calculation | a textbook formula used to predict the answer and check the computer |
| Job | one piece of work, kept in its own folder under `jobs/` |

## 2. One-time step: put the tool on your main branch

The tool currently lives on the branch `claude/wonderful-cerf-u9mbnt`. To have it on
every machine automatically, merge it into `main` once:

1. Open the repository on github.com.
2. Click **Compare & pull request** for that branch (or **Pull requests > New**).
3. Click **Create pull request**, then **Merge pull request**.

Until you do, add `git checkout claude/wonderful-cerf-u9mbnt` after cloning (shown below).

## 3. Getting started on a Windows PC

You need Windows 10 or 11, about 2 GB of free disk space, and a Claude plan that
includes Claude Code (or see section 8 for free alternatives). No administrator
rights are needed.

**Step 1 - open PowerShell.** Start menu, type `PowerShell`, press Enter.

**Step 2 - install Git and Python** (skip any you already have):

    winget install --id Git.Git -e
    winget install --id Python.Python.3.12 -e

Close PowerShell and open it again so Windows finds the new programs.

**Step 3 - install Claude Code and sign in:**

    irm https://claude.ai/install.ps1 | iex

Close and reopen PowerShell again.

**Step 4 - download the agent.** Keep it out of OneDrive folders (Documents, Desktop):

    mkdir ~\projects
    cd ~\projects
    git clone https://github.com/ikiyanitsyn/EngineeringAgent.git
    cd EngineeringAgent
    git checkout claude/wonderful-cerf-u9mbnt

(Skip the last line once you have merged into `main`.)

**Step 5 - run setup** (5 to 10 minutes the first time):

    powershell -ExecutionPolicy Bypass -File scripts\setup.ps1

It installs the CAD and meshing packages, downloads the solver, then runs a test
problem with a known answer. Success looks like this at the end:

    benchmark (cantilever)  PASS: FEA vs beam theory 0.795 % (limit 2 %)
    READY

> Honest note: this script was written carefully but has only been run on Linux so
> far. If it stops with an error, copy the whole message into Claude Code (step 6) and
> ask it to fix the setup. If Windows or antivirus blocks the solver download, allow it
> or ask IT; it comes from the solver author's site, dhondt.de.

**Step 6 - start the agent:**

    cd ~\projects\EngineeringAgent
    claude

Type a first message to check everything is alive:

> Run the doctor check and tell me if you are ready.

**Next time**, you only need step 6. To pick up improvements: `git pull`.

### What working with it feels like

- It **asks questions** before it starts. That is deliberate: it is not allowed to
  guess a load, a material or a dimension.
- It **asks permission** before running commands. Read the prompt and approve. Commands
  starting with `./ea` are the agent's own tools.
- It **predicts the answer by hand first**, then runs the computer model, then compares.
- It ends with a **verdict**:
  - **PASS** - every check was done and passed.
  - **REVIEW** - nothing failed, but something was not verified. It will say what.
  - **FAIL** - a check failed. Do not use the numbers until it is fixed.

## 4. The three things you will ask for most

### A. A model for 3D printing

**Tell it:** what the part is and its dimensions; printing process (FDM filament, SLA
resin, SLS powder); material (PLA, PETG, ABS, ...); your printer's build size if
unusual; what the part must fit or hold.

**Example request:**

> Design an open-top electronics enclosure, 100 x 70 x 40 mm outside, 2.4 mm walls,
> rounded corners, four screw bosses for 3 mm self-tapping screws. I will print it in
> PETG on an FDM printer with a 220 x 220 x 250 mm bed. Check it for printing and give
> me the STL.

**What it does:** builds the model, verifies the size and volume, then runs a print
check: does it fit the printer, thinnest wall, overhangs that need support, best
orientation on the bed, holes that will print undersize, expected accuracy, shrinkage
and printed weight.

**What you get** (in `jobs/NN-name/`): `part.stl` and `part.3mf` for your slicer,
`part.step` (the exact master model), `geometry.py` (the recipe, so changes are easy),
and optionally a report.

**Useful follow-ups:**

> Make the walls 3 mm and add a 20 mm cable hole in one short side.
> Which way up should I print it, and will it need supports?
> It has to carry 5 kg hanging from the bosses. Is PETG strong enough?

### B. Analysis (FEA) of a part you already have

**You need a STEP file.** From your CAD program use *File > Export > STEP*
(Fusion 360, SolidWorks, Onshape, FreeCAD and Inventor all do this). An STL is not
suitable for analysis: it has lost the exact surfaces.

**Put the file in a job folder**, for example
`C:\Users\You\projects\EngineeringAgent\jobs\01-my-bracket\part.step`
(drag it there in File Explorer; `explorer .` opens the current folder).

**Tell it:** the material; where the part is held; the load (how big, which direction,
where it acts); what you want to know; your pass/fail limit if you have one.

**Example request:**

> Analyse jobs/01-my-bracket/part.step. Material is aluminium 6061-T6. It is bolted
> down through the two holes in the base. A 300 N force pulls the two holes in the
> upright sideways, away from the base. I need a safety factor of at least 2 on yield
> and less than 0.5 mm deflection. Check mesh convergence and give me a report.

**What it does:** lists the faces of your model and confirms with you which ones are
the supports and the load; hand-calculates an estimate; meshes and solves; checks force
balance, agreement with the hand calculation and whether a finer mesh changes the
answer; writes the report.

**What you get:**

| File | What it is |
| --- | --- |
| `report.pdf` / `report.html` | the full write-up: answer, pictures, hand calculations, checklist, assumptions |
| `viewer.html` | double-click it: colour plot you can rotate, with animated deformation |
| `results.json` | every number, for the record |
| `job.json` | the exact inputs that were used |

**Other analyses, same pattern** - just ask:

> What are the first natural frequencies of this bracket when bolted down?
> At what load would this strut buckle?
> One end is held at 100 degC and the fins see 25 degC air with h = 20 W/m2K. How hot does the tip get?
> The part cools from 180 degC to 20 degC while clamped at both ends. What stress builds up?
> The load cycles from zero to 300 N. Will it survive fatigue?

### C. Design plus analysis in one go

Describe the part *and* the duty. The agent designs it, analyses it, and changes the
design if it fails.

**Example request:**

> Design an aluminium 6061-T6 angle bracket: base leg 60 mm, upright 60 mm, 40 mm wide,
> 5 mm thick, 5 mm inside corner radius, two M6 clearance holes in each leg. It is
> bolted through the base and carries 300 N pulling the upright. I need a yield safety
> factor of 2 and under 0.5 mm deflection. If it does not pass, tell me what to change.
> Finish with a report including tolerances for CNC machining.

A finished version of exactly this job is in
`examples/20-bracket-design-review/` - open its `report.pdf` to see what to expect.

**Useful follow-ups:**

> What thickness gives a safety factor of exactly 3? Try 4, 6 and 8 mm.
> Add a tolerance scheme: the underside is datum A. Will the bolt pattern always assemble?
> Now check it in steel S355 instead.

## 5. Reading the result

1. **Look at the verdict first** (section 3).
2. **Read the answer line**: the number, its unit, and the margin against your limit.
3. **Open `viewer.html`** and press *Animate*. Ask yourself: is it bending the way a
   real part would? Is the highest stress where you would expect it to break?
4. **Know which stress is quoted.** Right at a bolted or clamped face the computer
   reports stress spikes that are not real (they keep growing as the mesh gets finer).
   The agent quotes the *design stress* away from those spots and tells you so.
5. **Read "Items needing attention" and "Assumptions and limitations"** in the report.

If the hand calculation and the computer disagree, one of them is wrong. Ask:

> Run the results review and tell me which check fails and why.

## 6. Units: metric or inches

Say it in words at any time:

> Switch to imperial units.
> Back to metric.
> What units are active?

One switch changes everything: inputs, results, reports (and the tolerancing standard:
ISO with metric, ASME Y14.5 with imperial). You can always mix by writing the unit:
"a 0.25 in hole in a 100 mm plate" is understood.

## 7. Doing it yourself (optional commands)

Everything the agent does is also a command you can type in PowerShell from the
repository folder. Useful ones:

| Command | What it does |
| --- | --- |
| `.\ea.cmd doctor --full` | health check plus the test problem |
| `.\ea.cmd units imperial` | switch units (or `metric`) |
| `.\ea.cmd materials` | list the material library |
| `.\ea.cmd calc list` | list the hand formulas |
| `.\ea.cmd cad templates` | list ready-made part shapes |
| `.\ea.cmd cad printcheck jobs\01-x\part.step -m petg` | print check |
| `.\ea.cmd fea new jobs\02-x -a static` | create a working example job to edit |
| `.\ea.cmd fea run jobs\02-x --converge --report` | solve, check, write the report |
| `.\ea.cmd view jobs\02-x --open` | open the colour-plot viewer |
| `.\ea.cmd gdt fit 25 H7/g6` | shaft/hole fit limits |

## 8. Using free AI models instead of a Claude subscription

The tools themselves are free and run on your PC. Only the "assistant that drives
them" changes. Three routes, easiest first. Do sections 3 steps 1, 2, 4 and 5 first
(you can skip installing Claude Code).

Free models are weaker than Claude at following a long engineering procedure. Keep the
safety net on: always ask for the hand calculation and the convergence check, and
treat a REVIEW or FAIL verdict seriously.

### Route 1 - any free chatbot, you run the commands (no installation)

Works with any free chat AI in a browser. The chatbot writes the job file; you run it.

1. In PowerShell: `.\ea.cmd fea new jobs\01-test -a static` - this creates a working
   example, `jobs\01-test\job.json`.
2. Open `docs\job-reference.md` and that `job.json` in Notepad. Paste both into the
   chatbot with a message like:
   > This is the input format of an FEA tool and a working example. Rewrite the
   > example for my problem: [describe part, material, supports, loads]. Reply with
   > the complete job.json only.
3. Save the reply over `job.json`, then run
   `.\ea.cmd fea run jobs\01-test --converge --report`.
4. If there is an error, paste the error text back to the chatbot. The tool's messages
   are written to say what is wrong (for example a face selector that matched nothing).

### Route 2 - a free coding agent that can run commands

Agents that work in a terminal can use the tool exactly as Claude Code does. One
example is Google's Gemini CLI, which has offered free use with a personal Google
account (check the current terms). Install it per its own instructions, start it in
the `EngineeringAgent` folder, and make this your first message:

> Read AGENTS.md and CLAUDE.md in this folder and follow them for everything we do.
> Use the commands starting with .\ea.cmd. The step-by-step playbooks are in
> .claude/skills. Start by running: .\ea.cmd doctor --full

`AGENTS.md` is written for this purpose: it lists the commands and the rules for any
AI, not just Claude.

### Route 3 - a local model on your own PC, connected as "tools" (MCP)

Fully offline and free; needs a reasonably strong PC (16 GB RAM or more, a graphics
card helps).

1. Install a free app that runs local models and supports MCP tools, such as
   LM Studio. Download a model marked as supporting **tool use / function calling**.
2. In the app's MCP settings (in LM Studio: the `mcp.json` file), add:

       {
         "mcpServers": {
           "engineering-agent": {
             "command": "C:\\Users\\YOU\\projects\\EngineeringAgent\\.venv\\Scripts\\engagent-mcp.exe",
             "args": [],
             "env": {"ENGAGENT_ROOT": "C:\\Users\\YOU\\projects\\EngineeringAgent"}
           }
         }
       }

   Replace `YOU` with your Windows user name. Keep the double backslashes.
3. Start a chat, enable the `engineering-agent` tools, and begin with:
   > Call the doctor tool, then units_get. For any analysis, call fea_job_help first
   > and start from the starter job it returns. Never invent loads or materials.

The model then has 24 tools (build CAD, check for printing, hand calculations, run
FEA, write the report, tolerances). Give file locations as full paths, for example
`C:\Users\YOU\projects\EngineeringAgent\jobs\01-test`. More detail: `docs/mcp.md`.

## 9. Using it from an iPhone

An iPhone cannot run the CAD engine or the solver itself. It works as a remote
control for a computer that can. Two ways:

### Way 1 - cloud session (nothing needs to be switched on at home)

Claude Code can run on a cloud computer linked to your GitHub repository. You need a
Claude plan that includes Claude Code.

1. Open the **Claude** app on the iPhone and go to the **Code** section (or open
   claude.ai/code in Safari).
2. Connect your GitHub account when asked, and choose the `EngineeringAgent`
   repository.
3. The cloud computer starts empty every time, so make this your first message:
   > Run `bash scripts/setup.sh`, then confirm the doctor check says READY.
   This takes a few minutes. After that, ask for work exactly as in section 4.
4. **Getting your files.** Ask:
   > Send me report.pdf and viewer.html for this job.
   The files appear in the chat; the PDF opens directly and `viewer.html` opens in
   Safari, where you can rotate the colour plot with your finger.
5. **Saving your work.** The cloud computer is wiped after the session. Before you
   leave, say:
   > Commit and push this job.
   Your job folder and reports are then on GitHub (viewable in the GitHub app) and
   arrive on your PC with `git pull`.

To skip step 3 in future: on a computer, open the session's cloud environment
settings, and put this in the **Setup script** box of an environment you use for this
repository:

    if [ -f EngineeringAgent/scripts/setup.sh ]; then (cd EngineeringAgent && bash scripts/setup.sh) || true; fi

To analyse an existing part from the phone, the STEP file must be in the repository:
upload it on github.com (*Add file > Upload files* into `jobs/NN-name/`) or attach it
in the chat and ask the agent to save it into a new job folder.

### Way 2 - drive your own Windows PC from the phone

Your PC does the work (and keeps all files); the phone is the screen.

1. On the PC, in PowerShell:

       cd ~\projects\EngineeringAgent
       claude remote-control

   Leave that window open and the PC awake.
2. On the iPhone, open the Claude app's Code section. The session from your PC
   appears there; open it and type as usual.
3. Files are written on the PC. Ask the agent to send you the report, or open them
   when you are back at the PC.

Which to choose: Way 1 if the PC is off or you are travelling; Way 2 if you want the
files to stay on your PC, or the PC is much faster than the cloud machine.

Free AI models from an iPhone: Route 1 in section 8 works on a phone for *writing*
the job file, but something still has to run it, so it is only practical together
with a computer.

## 10. Good habits

- **Give numbers with units.** "About 30 kg hanging from the end" beats "a heavy load".
- **Say how the part is held.** It matters as much as the load.
- **Start simple.** Analyse the bare part first; add detail when the simple answer makes sense.
- **Always ask for the convergence check** before acting on a result.
- **One job, one folder.** Ask for a new job rather than reusing an old folder.
- **Save your work**: "Commit this job with a clear message."
- **Keep confidential designs confidential.** Check your employer's rules before
  giving proprietary geometry to any AI service. Route 3 in section 8 keeps
  everything on your PC.

## 11. When something goes wrong

| What you see | What to do |
| --- | --- |
| `ea.cmd` says the agent is not installed | run the setup script (section 3, step 5) |
| `claude` is not recognised | close and reopen PowerShell; reinstall Claude Code if needed |
| Setup fails while installing packages | make sure Python is 3.10 to 3.13 (`python --version`); paste the error into the AI |
| "CalculiX NOT FOUND" in the doctor check | re-run setup; or download the Windows zip from dhondt.de and unzip it into `tools\calculix` |
| "selector matched no CAD face" | ask: "List the faces of the part and let me pick the support and load faces" |
| Solver error about a singular matrix | the part is not fully held; add or correct a support |
| Verdict FAIL on "hand calculation" | load, support, material or units differ between the two; ask the agent to find which |
| Verdict FAIL on "mesh convergence" | ask it to refine the mesh and re-run |
| Results off by 1000 or a million | a unit mistake in an input; ask "show me the inputs you used, with units" |
| Analysis is slow | normal for fine meshes (the solver runs on one processor core on purpose, for reliability); ask for a coarser first pass |

## 12. What it cannot do (so you are not surprised)

- It is engineering assistance, **not a sign-off**. Anything safety-critical or
  certified needs review by a qualified engineer.
- Material data are typical handbook values, not your supplier's certificate.
- Very thin sheet-metal parts and long slender frames analyse slowly (solid elements only).
- Bolt preload is checked with formulas, not inside the 3D model.
- Composite laminates are modelled as one blended material; ply-by-ply stress comes
  from laminate formulas.
- It does not produce 2D manufacturing drawings; it gives the 3D model plus a
  tolerance scheme and its checks.

More detail when you want it: `README.md` (overview), `docs/job-reference.md` (every
input), `docs/validation.md` (how accurate it is and how that was tested),
`docs/mcp.md` (connecting other AI apps).
