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
