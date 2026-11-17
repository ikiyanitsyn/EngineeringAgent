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

1. **Plain English in GitHub issues needs a model key (user action, 3 minutes).** GitHub
   Models returned a plain-text "OK" instead of a completion from this repository's runners,
   and the old Azure endpoint does not resolve there. The bot explains this in the issue.
   Fix: add secret `ENGAGENT_LLM_KEY` (free Gemini key) and variables `ENGAGENT_LLM_URL`,
   `ENGAGENT_LLM_MODEL` (values in docs/USER-GUIDE.md section 2A). Then re-test by opening an
   issue in plain English. If GitHub Models becomes available, nothing needs to change.
2. **Live test of the plain-English loop with a real model.** Only the fake-server test
   exists. After item 1, open an issue such as "Printable PETG wall hook for a 5 kg coat" and
   check the model's request, the auto-fix loop and the question path ("analyse my bracket").
   Tune `engagent/prompt.py` from what goes wrong (regenerate the doc with `ea prompt -o docs/CHATBOT-PROMPT.md`).
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
