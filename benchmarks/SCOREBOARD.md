# Benchmark scoreboard

2026-11-18 16:56 - **8 / 10 PASS** (solved blind from the plain-English prompt; answers from the cited source).

| Case | Outcome | Answered by | Time | Detail | Source |
|---|---|---|---|---|---|
| 001-cantilever-mass | PASS | rules | 10 s | max_displacement: 0.9388 (0.3 % off, tol 5 %) | Roark's Formulas, Table 8.1 case 1a (cantilever, end load), with shear |
| 002-simply-supported | PASS | rules | 4 s | max_displacement: 0.1182 (1.7 % off, tol 7 %) | Roark, Table 8.1 case 1e (simply supported, centre load) |
| 003-column-buckling | FAIL | gemini-3.5-flash-lite | 75 s | buckling_factor_1: 9.217 (33.4 % off, tol 5 %) | Euler buckling, fixed-free (K = 2) |
| 004-cantilever-frequency | PASS | gemini-3.5-flash-lite | 135 s | frequency_1: 45.54 (0.4 % off, tol 5 %) | Euler-Bernoulli beam, clamped-free, first mode |
| 005-hot-bar-convection | PASS | rules | 2 s | min_temperature: 96.19 (0.0 % off, tol 1 %) | Incropera 3.1.3, thermal circuit |
| 006-restrained-bar-heating | ASKED | gemini-3.5-flash-lite | 167 s | Before I run the analysis I need a few facts from you - I will not guess them, because the answer depends on them: - the temperature (the request assumed 50)  Please give the material (e.g. 'steel', ' | sigma = E alpha dT (fully restrained bar; 3-D ends add a little) |
| 007-bonded-bars | PASS | rules | 45 s | max_displacement: 0.04806 (0.3 % off, tol 3 %) | series springs: P L1/(A E1) + P L2/(A E2) |
| 008-printable-box | PASS | rules | 1 s | cad.size: 100x70x40 | dimensions as asked |
| 009-m5-spacer | PASS | rules | 0 s | cad.size: 12x12x15 | dimensions as asked; ISO 273 medium clearance 5.5 mm |
| 010-cable-clip | PASS | gemini-3.5-flash-lite | 56 s | cad.valid: True | custom shape: a valid printable solid; fit judged by eye |

PASS = every expected value within tolerance. ASKED = the agent asked a question instead (fine when the prompt really lacks an input, otherwise a gap). FAIL / ERROR = a gap to fix.
