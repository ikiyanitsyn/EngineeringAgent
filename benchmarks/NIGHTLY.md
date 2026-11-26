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
| Claude chat round 2 (fresh blind replies to the improved sheet), 19 cases | - | **19** |
| Gemini via the issue bot, original 10 cases | 9 (case 010: quota 429) | **10** |
| Gemini via the issue bot, all 19 cases (first run after midnight) | - | 13 (3 quota errors; 1 units slip, 2 time-budget artifacts - fixed, re-run below) |
| Gemini re-run of cases 001 + 010-019 after the fixes | - | **9 / 11** - every case Gemini answered passed (011, 013, 014, 016, 018 now PASS); 017 and 019 got no answer (daily quota used up) |

The chat solver's replies were written once and re-scored on the improved toolkit, so the gain is the
toolkit absorbing the slips any AI makes, not a different answer.

### Improvements merged
(after midnight) 10. A bare moment must match the user's number in N*m (Gemini wrote 100 N*m as 100000 and got a
    1000x result). 11. An exact hand check that FAILs is fed back to the model once to find the wrong input.
    12. Each benchmark case gets its own time budget, as each issue does.
    13. A used-up DAILY model quota is reported at once (with the paste-into-any-chatbot alternative) instead
    of ~15 minutes of retries that cannot succeed.

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

### Verified live on GitHub
- Issue #24: a public share link (NIST's 14 MB zip of 33 STEP parts) -> "which part?" -> measured faces and
  holes with a picture -> "aluminium 6061, fix F2, 5000 N down on F1" -> FEA (REVIEW: no hand check for an
  arbitrary part), all without an AI model. Two routing bugs found and fixed on the way.

### Waiting for the owner (major change)
- Make "supports leave the part free to move" a hard stop instead of a WARN. Today the run still
  completes with a warning; as a stop, the AI gets the error and fixes its supports before any result is
  shown. Recommended: yes.

### Still open
- Case 017 in round 1 (supports let the bar spin) is solved in round 2 by the sheet's new support rule.
- Gemini after-score (quota).

### Morning report (6 am PT)
- Final Gemini position on the latest code: every case Gemini answered passed; 019 (D-shaft knob) never
  got an answer from a strong model (lite model / daily quota). Original 10 cases: 9 -> 10.
- Claude chat stand-in (Sonnet, sheet only): 14 -> 19 / 19 (+36 %).
- Per domain, chat round 2: structures 10/10, thermal 4/4, 3D-print 5/5.
- Average time per case: Gemini 306 s (median 43 s; waits on a busy free tier dominate), chat replies 22 s.
- Run ended at 6 am PT.

### Follow-up (2026-11-19 afternoon, after the owner's go-ahead)
- Owner approved: supports that leave a rigid-body motion free now STOP the run (the AI fixes them first).
  Chat round 2 still 19 / 19, toolkit check 6 / 6.
- Repository made public by the owner: GitHub Actions minutes are now free; attachments no longer need a login.
- Case 019 (D-shaft knob) with a strong Gemini model: PASS in 76 s. Every one of the 19 cases has now passed
  with Gemini at least once (017 in the first run, 019 here, the rest after the fixes).

## 2026-11-25 -> 26 (owner: "begin overnight training", 6 am report)

### Cases
- 10 new cases (020-029): shelf with a spread load (Roark 2a), square tube cantilever, clamped disc under
  pressure (Roark 11.2 10b), pinned rod buckling (Euler K = 1), simply supported frequency, PETG wall with
  convection (Incropera 3.1), heated plate in air (energy balance), printed box with M3 bosses, M3 hex
  standoff, printed L-bracket. 29 cases in all.
- Toolkit check (answers known): all 7 new analysis cases reach the textbook value (worst 1.0 %).

### Scores
| Solver | Before | After |
|---|---|---|
| Gemini, 19 earlier cases (baseline at midnight) | 14 / 19 (4 daily-quota errors, 1 crash) | crash fixed |
| Claude chat stand-in (Sonnet, sheet only), 10 new cases | - | **10 / 10** |
| Claude chat stand-in, fresh blind round on all 29 cases (final sheet) | - | **29 / 29** |
| Rules only (no AI model), all 29 cases | about 10 (shelf: CAD only; hex: round part; L-bracket: wrong size) | **20 / 29**, no FAIL or wrong answer (the other 9 need a model) |

### Improvements merged
1. Hand check without an output name no longer crashes the run (Gemini case 013); the smooth peak stress
   (Lame bore, Kt hole) is picked by default, and any slip in an optional check is reported, never fatal.
2. Beam frequency and column buckling accept each other's support words; `D=` alone means a solid rod.
3. Print cases match their size in any orientation and bound the volume (a missing feature fails).
4. Instruction sheet: in modal analysis, hold faces / use symmetry, not single points (a point hold gave a
   false mode at half the real frequency in the toolkit check).
5. Rules: a load spread along a cantilever is a pressure on the top face, not a tip load (2.7x error
   avoided); "how far ... drop" is an analysis; a hex part is a custom shape, not the round standoff.
6. Rules (no AI model needed, so they work when the free Gemini quota is gone - it ran out after ~6 calls
   tonight): square / rectangular / round tube cantilevers; pinned-pinned columns held at true pins (the old
   rule modelled fixed-pinned: 2x Euler; the hand check caught it) and solid round rods (new round beam
   section); first natural frequency of cantilever / simply supported / fixed-fixed bars (half models, faces
   held); flat round plates under pressure (Roark 11.2, clamped or simply supported); a wall with one face held
   and air on the other; a heated plate cooled by air; L-bracket sizes read from the words.
7. A deflection hand check under a spread load compares the peak, not the average over the loaded face (a
   simply supported round plate showed a false 55 % FAIL while the FEA was 0.25 % off Roark).
8. thermal.convection also gives the surface temperature from a heat input.
