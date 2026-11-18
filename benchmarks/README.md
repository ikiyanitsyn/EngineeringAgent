# Benchmarks: real engineering cases, solved blind

Each folder is one case:
- `prompt.md`: what an engineer would type, in plain English. It is all the solver sees.
- `expected.json`: the source (textbook / standard), the expected results and tolerances. Never shown to
  the solver.

Run them with `./ea bench` (all cases; writes `SCOREBOARD.md`) or `./ea bench --only cantilever`. On GitHub,
go to **Actions > bench > Run workflow**: the cases are solved exactly as the issue bot would solve them
(rules first, then your Gemini key), and the scoreboard is committed.

This is phases 0 and 1 of the improvement loop (`docs/ROADMAP.md`): a fixed set of cases with known
answers and a scoreboard. Next: an Opus judge that also scores the method, then an improver that proposes
repo changes. A change is accepted only if no case gets worse, and you approve it.

## Decisions (agreed with the owner)

| Topic | Decision |
|---|---|
| Domains | First: structures & brackets, thermal, 3D-print parts. Composites (thermosets and thermoplastics) is a separate improvement stage afterwards; ask the owner for current composites work before starting it. |
| Approval | Changes merge automatically when every benchmark case still passes. A MAJOR change (new solver behaviour, new template families, changed verification logic) waits for the owner, with a short summary and an easy approve / don't-approve choice. |
| Sources | Textbooks / standards and open-access papers; only our own summary and numbers are stored. The owner's own work is a later stage, used first to verify the agent. |
| Schedule | Nightly. The owner is asked at about 8 pm PST before each run, and the run starts only after they confirm. It runs overnight and ends at 6 am PST, or when usage limits are reached, with a report: improvements made, issues solved and still open, score before -> after and improvement %, pass rate per domain, the sources tested, and anything waiting for approval. |
