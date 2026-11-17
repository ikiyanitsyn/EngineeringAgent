# Status and next steps

Written so that a later session (or another model) can pick the work up without the
original conversation. Last updated 2026-11-17.

## What exists and how it is verified

| Feature | Where | Verified by |
| --- | --- | --- |
| CAD templates (beam, plate, l_bracket, flange, enclosure, lid, standoff, pipe_clamp, wall_hook, phone_stand, curved_laminate) | `engagent/cad/templates.py` | `tests/test_cad.py` builds every template; print check on each |
| One-line commands `ea make`, `ea analyze` (+ `--check` hand-calc linking) | `engagent/quick.py`, `engagent/cli.py` | `tests/test_quick.py`, live GitHub runs, Windows CI |
| Request format (`ea` lines, ```json, ```python, `last`) | `engagent/request.py` | `tests/test_quick.py`, issue #1 live runs |
| Chatbot prompt (generated from the catalogues) | `engagent/prompt.py` -> `docs/CHATBOT-PROMPT.md` | test fails if the doc is stale; every example in it was run |
| Plain English: `ea ask` with any OpenAI-compatible model, error feedback and retry | `engagent/assistant.py` | `tests/test_assistant.py` with a fake model server |
| GitHub issue bot | `.github/workflows/engineer.yml`, `scripts/issue_bot.py`, `.github/ISSUE_TEMPLATE/` | issue #1 (closed, kept as a worked example): `ea` lines and a Python-geometry request ran on GitHub, results committed (`jobs/01`-`04`), replies posted; same numbers as locally |
| Default mesh from wall thickness; singularity diagnosis in the convergence check | `engagent/fea/run.py` | bracket example: stress 43 -> 48 MPa with the finer default; corner singularity reported with its location |
| Windows: `START-HERE.cmd` + `scripts/start.ps1` menu, `scripts/setup.ps1` | | CI job `windows`: parse check, real setup (CalculiX 2.23 download, benchmark 0.795 %), menu actions via `start.ps1 -Do ...` (request, units, prompt, UTF-8 BOM file), one-liners |
| MCP server (28 tools incl. one-call `make`, `analyze`, `run_request`) | `engagent/mcp_server.py` | stdio client test (manual, see commit history) |
| Analysis core, hand calcs, GD&T, reports, viewer | `engagent/` | `pytest -m solver` (22 FEA benchmarks against closed form), `docs/validation.md` |

Run everything: `.venv/bin/python -m pytest -q` then `.venv/bin/python -m pytest -q -m solver`.

## Open items, highest value first

1. ~~Plain English in GitHub issues needs a model key~~ - done without a key: when no hosted
   model answers (GitHub Models returned a plain "OK" from these runners), the bot installs
   Ollama on the runner and uses `qwen2.5-coder:7b` (cached between runs). Live run: "3D
   printable wall hook in PETG ... arm 50 mm" -> `ea make wall_hook arm_length=50 --print petg`
   -> files, 6.7 min including the one-time download. A Gemini key remains an optional upgrade.
2. **Open model behaviour seen live (issues #2, #3).** It copied example values (steel S355,
   500 N) when the user gave none, and wrote 500 N for "50 kg". Now guarded in code
   (`engagent/guard.py`): untraceable materials/loads are rejected, the model gets one retry with
   the user's own quantities converted (50 kg = 490.3 N), and only then is the user asked; analysis
   questions answered with CAD only get a follow-up question. On top, `guard.autocorrect` maps the
   user's material words to a library key (mild steel -> steel_generic, also replacing grades the user
   never named, e.g. S355) and replaces an invented load magnitude with the single load the user
   stated, listing each change in the reply; a question the user's messages already answer is pushed
   back to the model once. Small models still sometimes ask odd questions - the user can always paste
   `ea` lines, or add a Gemini key. Each CPU model call takes
   roughly 3-6 minutes; a Gemini key (or a faster runner) makes replies ~1 minute.
   **Final design for local models (`engagent/structured.py`):** the small model fills a JSON form
   constrained by Ollama's schema support (template, dimensions, material words, held faces, loads
   with the user's own magnitude and unit); the code maps the material, converts units, places end
   loads on the end face, builds the `ea` commands and checks every magnitude. Live result (issue #4):
   "mild steel bar 200 x 10 x 20, bolted to a wall at one end, 50 kg hanging from the free end" ->
   SF 1.79, 0.94 mm, hand check 0.5 %, PASS, ~5 minutes, no key. Covers templates with supports and
   forces/pressures, steady heat flow (--temp/--convect/--heat, deg F converted) and thermal stress
   (--t0/--dT); every temperature, h and wattage is checked against the user's words. Custom shapes
   and assemblies need a hosted model or a pasted request.
   **Live thermal test (issue #5, "how hot does the end of a steel bar get"):** found and fixed
   three problems. (a) Ollama's installer fell back to a `.tgz` that releases no longer ship:
   `assistant._install_ollama` now takes the `.tar.zst` from the GitHub release, then `.tgz`,
   then the script. (b) The model asked for the very temperature the user wanted: a needless
   question is retried once with the form forced to `analyze` (`assistant._inputs_given`).
   (c) Forced, it read "100 C" as a 100 kg force: `structured.magnitudes_from_user` now requires
   every value to appear in the user's words with a unit of the same kind. The 1-D hot-end /
   cooled-end bar gets automatic hand checks (end temperature + heat flow, which also closes the
   heat balance): locally 96.19 degC, both 0.0 %, PASS.
   **Confirmed live:** issue #5 then answered 96.19 degC, both hand checks 0.0 %, PASS (~6 min,
   no key; jobs/13-beam). **Next for a follow-up session:** if the 7B model misfills thermal forms, add a deterministic pre-fill from the user's words (temperatures
   with units, "h = N", "held at" / "cooled by" -> faces) and let the model only pick the template.
   **Rules first (`engagent/rules.py`):** common requests (cantilever bar with an end load, plate
   clamped on an edge with a force or pressure on top, hot-end / air-cooled bar, print requests for
   any template with sizes) are read from the user's words with no model, in 1-3 minutes, and go
   through the same checks. Anything the rules are unsure of (no load direction, mid-span loads,
   brackets, several loads) goes to the model. `ENGAGENT_NO_RULES=1` turns it off.
3. **Watch the open model on harder requests.** Custom shapes (Python blocks) and multi-step
   analyses are where a 7B model is most likely to stumble; the error-feedback loop helps.
   If quality is poor, try `vars.ENGAGENT_LOCAL_MODEL = qwen2.5-coder:14b` (slower) or a key.
3. ~~3MF export fails on some shapes~~ - done: a direct 3MF writer takes over when the mesher
   refuses (mesh volume checked against CAD).
4. **More templates** for common print requests: hinge, snap-fit box with lid, knob, gear
   (bd_warehouse), spacer/washer set, cable clip, hose adapter. Each needs a `@template` entry
   and is covered automatically by `tests/test_cad.py`.
5. **Viewer on the phone.** `viewer.html` is in the run's artifact zip, not committed (size).
   Option: enable GitHub Pages and publish job viewers there; link it from the issue reply.
6. **Auto hand checks for templates** - done for the `beam` cantilever; other templates
   (plate under pressure, flange, l_bracket) could get the same treatment in `quick._auto_beam_check`.
7. **Assemblies in one line** (`ea analyze` with two parts and a tie) - today they need a
   `job.json` (see the `fea-assembly` skill and `examples/12-tied-assembly`).
8. **Solver threads.** Serial by default because multithreaded CalculiX 2.21 was
   unreliable on Linux. The Windows build is 2.23; its multithreading has not been tested.
9. **Claude in GitHub issues** (`@claude`): the user can run `/install-github-app` in Claude
   Code to add Anthropic's action; `CLAUDE.md` already tells Claude to install the toolchain
   itself. Not set up here because it needs the user's account.

## Conventions to keep

- Numbers only from tools; FAIL and REVIEW are reported as such (see `CLAUDE.md`).
- Every new feature gets a test; solver tests carry `@pytest.mark.solver`.
- `docs/CHATBOT-PROMPT.md` is generated; never edit it by hand.
- Commit messages end with the attribution lines the session provides.
