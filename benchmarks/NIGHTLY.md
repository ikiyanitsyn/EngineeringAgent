# Nightly improvement runs

## 2026-11-18 -> 19 (owner said yes at 8 pm PT)

Domains tonight: structures & brackets, thermal, 3D-print parts (as agreed). Sources: Roark, Shigley,
Peterson, Lame, Incropera; one public CAD dataset (NIST MBE PMI STEP files) for the parts route.

### Cases
- 9 new cases (011-019): torsion, fixed-fixed beam, thick tube under pressure (Lame), plate with a hole
  (Peterson Kt), inch-unit cantilever, pin fin with convective tip, free thermal expansion, a slotted cable
  comb and a D-shaft knob (print cases also bound the volume, so a missing feature fails). 19 cases in all.
- Toolkit check (answers known, `benchmarks/reference`): all six new analysis cases reach the textbook
  value, worst 1.3 % off.

### Scores
| Solver | Before | After |
|---|---|---|
| Rules only (no AI model), 19 cases | 10, one of them false (comb built without slots) | 10, all real (adds the fixed-fixed beam) |
| Claude chat (Sonnet given only docs/CHATBOT-PROMPT.md, no tools), 19 cases | 14 | 18 |
| Gemini via the issue bot (10 original cases) | 9 (case 010: quota 429) | after-score runs once the free quota resets |

The chat solver's replies were written once and re-scored on the improved toolkit, so the gain is the
toolkit absorbing the slips any AI makes, not a different answer.

### Improvements merged
1. Requests naming a feature no template has (slots, notches, D-shafts, knobs, combs ...) go to the model
   instead of a plain template that only matched the size (found: comb built with no slots).
2. "aluminium 6061 bar" is no longer read as a pressure of 6061 bar.
3. Beam fixed at both ends with a centre load: half model by symmetry (rules), 0.9 % off Roark.
4. The input guard accepts half / quarter of a user's load for symmetry models (it passed the simply
   supported case only by coincidence before).
5. Hand checks: a check that cannot be built no longer stops the analysis (NOT DONE -> REVIEW, reason
   shown); outputs and inputs are matched forgivingly (`stress` -> `von_mises_inner`, `alpha` -> `cte`,
   a CTE written per kelvin is converted, `-> max_displacement` names a result).
6. Vectors accept a unit on one component (`100N*m,0,0`); job `analysis` may be `{"type": ...}`.
7. Supports that leave a rigid-body motion free (e.g. a bar free to spin about its axis) are reported as a
   WARN with the fix. The restrained-bar rule and the instruction-sheet example now hold all six motions.
8. Parts route: STEP from cloud share links, a many-part zip asks which part (real NIST link, issue #24),
   part measurement no longer crashes on radius-less cylinder patches.
9. Hole recognition knows inch (UNC) screws when no metric one fits (the NIST part is an inch design:
   its 9.78 mm holes are 3/8-16 close-fit clearance holes).

### Waiting for the owner (major change)
- Make "supports leave the part free to move" a hard stop instead of a WARN. Today the run still
  completes with a warning; as a stop, the AI gets the error and fixes its supports before any result is
  shown. Recommended: yes.

### Still open
- Case 017 for the chat solver: its supports let the bar spin (now flagged by the WARN above).
- Gemini after-score (quota).
