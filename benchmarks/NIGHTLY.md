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

### Morning report (6 am PT, 2026-11-26)
- Chat stand-in: 29 / 29 (fresh blind round on all cases). Rules only: about 10 -> 20 / 29 (structures 12/15,
  thermal 4/6, print 4/8), no wrong answers. Gemini baseline at midnight: 14 / 19, its quota ran out after ~6 calls.
- Average time per case: chat route 59 s, Gemini 113 s.
- Merged without asking first, flagged for the owner: a deflection hand check under a spread load now compares
  the FEA maximum, not the loaded-face average (verification logic). Revert offered.

## 2026-11-26 -> 27 (owner: "Start it. Test my local qwen model ... or set up a way for it to talk to the repo")

### Local AI (Qwen in Ollama)
- The owner's PC was not reachable from the cloud session (no Remote Control folder), so the same route was
  tested here: Ollama installed by the toolkit's own installer, qwen2.5-coder:7b, NO settings - the agent found
  the installed model itself. 4 CPUs, ~40 s per case.
- New: `ea bench --model-only --quick` (START-HERE.cmd option T) tests YOUR model on six mixed cases with the
  built-in rules off; `--model-only` alone runs all cases. Several case filters separated by commas.
- Qwen quick set, rules off: 4 / 6 -> **6 / 6** after fixing the JSON form a small local model fills:
  torque loads (N*m, lbf*in, lbf*ft), round / tube sections with a 'diameter', a 'sides' face (curved side of a
  pin, long faces of a bar), a hole as wide as the part becomes a solid rod, a numeric 'section' is ignored,
  an air-cooled face is not also held at a temperature, and no face is held at the air temperature.
- MCP route (LM Studio etc.): server checked, 28 tools listed (guide corrected from 24).
- Rules + local Qwen (no internet AI at all), all 29 cases: **24 / 29**. Three of the misses became rules
  (plate with a hole in tension, pin fin from a hot wall, free expansion) and a fourth (thick tube under
  internal pressure, Lame 3.5 %) - the approved support hard stop caught my own first tube set-up (two
  tangential holds still let it spin about their crossing point).
- Waiting for approval (verification logic): the load-balance check gives a false FAIL for a self-balanced
  load (internal pressure) touching a supported face - nodal loads on supported nodes are counted per node
  in one place and per held direction in another. Proposed fix: compare the imbalance with the gross load
  when the net load is ~0, and count the loads on supported nodes per held direction consistently.
- Hex standoffs: the standoff template gained `hex_af` (size across flats; 0 = round), and the rules use it for
  "hex standoff ... across flats" (case 028: 6.35 x 5.5 x 20, 342 mm3). Rules + local Qwen before this: 28 / 29,
  the only miss being 028.

### Gemini after midnight (2026-11-27)
- Only 4 of the 29 cases still need a model at all (010 clip, 011 torsion, 018 comb, 019 knob) - the rules answer
  the other 25. Gemini on those 4: **4 / 4** (75-119 s each).
- One bot-style run of all 29 (rules first, Gemini for the rest - exactly what an issue gets): **28 / 29**, 25
  answered by rules and 4 by Gemini, average 46 s per case. The miss: Gemini's knob came out 29.9 mm across
  instead of 30 (its grip detail), though it passed 15 minutes earlier - model variation, not an agent gap.
- Before tonight Gemini's last full run was 14 / 19 (quota); with the rules carrying most cases, the free daily
  quota now covers a full benchmark run.
- Owner approved (2026-11-27): (1) deflection checks under a spread load compare the FEA maximum - kept;
  (2) the load-balance check now judges the imbalance against the gross load (the total of all loads however
  directed), not the net: the pressurised tube's false FAIL ('imbalance 4.9e13 %') is gone; one-way loads
  (tip loads, gravity) are judged exactly as before (gross = net).
