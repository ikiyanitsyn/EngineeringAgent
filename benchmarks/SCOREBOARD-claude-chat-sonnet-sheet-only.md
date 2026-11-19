# Benchmark scoreboard

2026-11-19 05:40 - **18 / 19 PASS** (solved blind from the plain-English prompt; answers from the cited source).

| Case | Outcome | Answered by | Time | Detail | Source |
|---|---|---|---|---|---|
| 001-cantilever-mass | PASS | Claude chat (Sonnet, sheet only) | 10 s | max_displacement: 0.9391 (0.2 % off, tol 5 %) | Roark's Formulas, Table 8.1 case 1a (cantilever, end load), with shear |
| 002-simply-supported | PASS | Claude chat (Sonnet, sheet only) | 5 s | max_displacement: 0.1182 (1.7 % off, tol 7 %) | Roark, Table 8.1 case 1e (simply supported, centre load) |
| 003-column-buckling | PASS | Claude chat (Sonnet, sheet only) | 13 s | buckling_factor_1: 6.915 (0.1 % off, tol 5 %) | Euler buckling, fixed-free (K = 2) |
| 004-cantilever-frequency | PASS | Claude chat (Sonnet, sheet only) | 93 s | frequency_1: 45.54 (0.4 % off, tol 5 %) | Euler-Bernoulli beam, clamped-free, first mode |
| 005-hot-bar-convection | PASS | Claude chat (Sonnet, sheet only) | 2 s | min_temperature: 96.19 (0.0 % off, tol 1 %) | Incropera 3.1.3, thermal circuit |
| 006-restrained-bar-heating | PASS | Claude chat (Sonnet, sheet only) | 4 s | max_von_mises: 126 (0.0 % off, tol 3 %) | sigma = E alpha dT (bar held axially at both ends) |
| 007-bonded-bars | PASS | Claude chat (Sonnet, sheet only) | 48 s | max_displacement: 0.04806 (0.3 % off, tol 3 %) | series springs: P L1/(A E1) + P L2/(A E2) |
| 008-printable-box | PASS | Claude chat (Sonnet, sheet only) | 1 s | cad.size: 110x75x45 | dimensions as asked |
| 009-m5-spacer | PASS | Claude chat (Sonnet, sheet only) | 0 s | cad.size: 12x12x15 | dimensions as asked; ISO 273 medium clearance 5.5 mm |
| 010-cable-clip | PASS | Claude chat (Sonnet, sheet only) | 2 s | cad.valid: True | custom shape: a valid printable solid; fit judged by eye |
| 011-shaft-torsion | PASS | Claude chat (Sonnet, sheet only) | 6 s | max_displacement: 0.1577 (0.0 % off, tol 5 %) | Shigley 10th ed. Eq. 4-5: phi = T L / (G J); surface displacement r phi |
| 012-fixed-fixed-beam | PASS | Claude chat (Sonnet, sheet only) | 4 s | max_displacement: 0.3709 (0.9 % off, tol 5 %) | Roark, Table 8.1 case 1c (both ends fixed, centre load) plus shear (Timoshenko) |
| 013-thick-tube-pressure | PASS | Claude chat (Sonnet, sheet only) | 14 s | max_von_mises: 276 (0.1 % off, tol 5 %) | Lame thick-walled cylinder, open ends (axial stress 0): von Mises at the bore |
| 014-plate-hole-tension | PASS | Claude chat (Sonnet, sheet only) | 143 s | max_von_mises: 125.7 (0.3 % off, tol 6 %) | Peterson's Stress Concentration Factors, chart 4.1 (Kt = 2.506 at d/w = 0.2, net section) |
| 015-imperial-cantilever | PASS | Claude chat (Sonnet, sheet only) | 29 s | max_displacement: 6.584 (1.2 % off, tol 5 %) | Roark, Table 8.1 case 1a (cantilever, end load), inch units |
| 016-pin-fin | PASS | Claude chat (Sonnet, sheet only) | 5 s | min_temperature: 65.07 (0.0 % off, tol 1.5 %) | Incropera 3.6.2, fin with convective tip: theta_L/theta_b = 1 / (cosh mL + (h/mk) sinh mL) |
| 017-free-expansion | FAIL | Claude chat (Sonnet, sheet only) | 5 s | max_displacement: 0.5611 (16.9 % off, tol 3 %) | Free thermal expansion dL = alpha L dT (alpha 12e-6 /K) |
| 018-cable-comb | PASS | Claude chat (Sonnet, sheet only) | 2 s | cad.size: 60x20x5; cad.valid: True; cad.volume: 4800 (allowed - .. 5900) | dimensions as asked |
| 019-d-shaft-knob | PASS | Claude chat (Sonnet, sheet only) | 3 s | cad.size: 30x30x15; cad.valid: True; cad.volume: 1.035e+04 (allowed - .. 10500) | dimensions as asked; D-shaft 6 mm with 4.5 mm flat |

PASS = every expected value within tolerance. ASKED = the agent asked a question instead (fine when the prompt really lacks an input, otherwise a gap). FAIL / ERROR = a gap to fix.
