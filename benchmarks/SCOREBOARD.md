# Benchmark scoreboard

2026-11-18 16:26 - **8 / 10 PASS** (solved blind from the plain-English prompt; answers from the cited source).

| Case | Outcome | Answered by | Time | Detail | Source |
|---|---|---|---|---|---|
| 001-cantilever-mass | PASS | rules | 16 s | max_displacement: 0.9388 (0.3 % off, tol 5 %) | Roark's Formulas, Table 8.1 case 1a (cantilever, end load), with shear |
| 002-simply-supported | FAIL | gemini-3.5-flash | 62 s | max_displacement: 0.2358 (102.8 % off, tol 7 %) | Roark, Table 8.1 case 1e (simply supported, centre load) |
| 003-column-buckling | PASS | gemini-3.5-flash | 232 s | buckling_factor_1: 6.915 (0.1 % off, tol 5 %) | Euler buckling, fixed-free (K = 2) |
| 004-cantilever-frequency | PASS | gemini-3.5-flash | 142 s | frequency_1: 45.54 (0.4 % off, tol 5 %) | Euler-Bernoulli beam, clamped-free, first mode |
| 005-hot-bar-convection | PASS | rules | 3 s | min_temperature: 96.19 (0.0 % off, tol 1 %) | Incropera 3.1.3, thermal circuit |
| 006-restrained-bar-heating | ASKED | gemini-3.5-flash-lite | 386 s | What is the material key for the steel (e.g. steel_generic, steel_s235, steel_a36)? | sigma = E alpha dT (fully restrained bar; 3-D ends add a little) |
| 007-bonded-bars | PASS | rules | 57 s | max_displacement: 0.04806 (0.3 % off, tol 3 %) | series springs: P L1/(A E1) + P L2/(A E2) |
| 008-printable-box | PASS | rules | 1 s | cad.size: 100x70x40 | dimensions as asked |
| 009-m5-spacer | PASS | rules | 0 s | cad.size: 12x12x15 | dimensions as asked; ISO 273 medium clearance 5.5 mm |
| 010-cable-clip | PASS | gemini-3.5-flash-lite | 425 s | cad.valid: True | custom shape: a valid printable solid; fit judged by eye |

PASS = every expected value within tolerance. ASKED = the agent asked a question instead (fine when the prompt really lacks an input, otherwise a gap). FAIL / ERROR = a gap to fix.
