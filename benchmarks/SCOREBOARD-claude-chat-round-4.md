# Benchmark scoreboard

2026-11-26 12:30 - **29 / 29 PASS** (solved blind from the plain-English prompt; answers from the cited source).

| Case | Outcome | Answered by | Time | Detail | Source |
|---|---|---|---|---|---|
| 001-cantilever-mass | PASS | Claude chat round 4 | 14 s | max_displacement: 0.9391 (0.2 % off, tol 5 %) | Roark's Formulas, Table 8.1 case 1a (cantilever, end load), with shear |
| 002-simply-supported | PASS | Claude chat round 4 | 7 s | max_displacement: 0.1182 (1.7 % off, tol 7 %) | Roark, Table 8.1 case 1e (simply supported, centre load) |
| 003-column-buckling | PASS | Claude chat round 4 | 17 s | buckling_factor_1: 6.915 (0.1 % off, tol 5 %) | Euler buckling, fixed-free (K = 2) |
| 004-cantilever-frequency | PASS | Claude chat round 4 | 125 s | frequency_1: 45.54 (0.4 % off, tol 5 %) | Euler-Bernoulli beam, clamped-free, first mode |
| 005-hot-bar-convection | PASS | Claude chat round 4 | 3 s | min_temperature: 96.19 (0.0 % off, tol 1 %) | Incropera 3.1.3, thermal circuit |
| 006-restrained-bar-heating | PASS | Claude chat round 4 | 6 s | max_von_mises: 126 (0.0 % off, tol 3 %) | sigma = E alpha dT (bar held axially at both ends) |
| 007-bonded-bars | PASS | Claude chat round 4 | 64 s | max_displacement: 0.04806 (0.3 % off, tol 3 %) | series springs: P L1/(A E1) + P L2/(A E2) |
| 008-printable-box | PASS | Claude chat round 4 | 1 s | cad.size: 110x75x45 | dimensions as asked |
| 009-m5-spacer | PASS | Claude chat round 4 | 0 s | cad.size: 12x12x15 | dimensions as asked; ISO 273 medium clearance 5.5 mm |
| 010-cable-clip | PASS | Claude chat round 4 | 3 s | cad.valid: True | custom shape: a valid printable solid; fit judged by eye |
| 011-shaft-torsion | PASS | Claude chat round 4 | 5 s | max_displacement: 0.1577 (0.0 % off, tol 5 %) | Shigley 10th ed. Eq. 4-5: phi = T L / (G J); surface displacement r phi |
| 012-fixed-fixed-beam | PASS | Claude chat round 4 | 5 s | max_displacement: 0.3709 (0.9 % off, tol 5 %) | Roark, Table 8.1 case 1c (both ends fixed, centre load) plus shear (Timoshenko) |
| 013-thick-tube-pressure | PASS | Claude chat round 4 | 66 s | max_von_mises: 280.4 (1.4 % off, tol 5 %) | Lame thick-walled cylinder, open ends (axial stress 0): von Mises at the bore |
| 014-plate-hole-tension | PASS | Claude chat round 4 | 205 s | max_von_mises: 125.7 (0.3 % off, tol 6 %) | Peterson's Stress Concentration Factors, chart 4.1 (Kt = 2.506 at d/w = 0.2, net section) |
| 015-imperial-cantilever | PASS | Claude chat round 4 | 39 s | max_displacement: 6.584 (1.2 % off, tol 5 %) | Roark, Table 8.1 case 1a (cantilever, end load), inch units |
| 016-pin-fin | PASS | Claude chat round 4 | 3 s | min_temperature: 65.07 (0.0 % off, tol 1.5 %) | Incropera 3.6.2, fin with convective tip: theta_L/theta_b = 1 / (cosh mL + (h/mk) sinh mL) |
| 017-free-expansion | PASS | Claude chat round 4 | 7 s | max_displacement: 0.4802 (0.0 % off, tol 3 %) | Free thermal expansion dL = alpha L dT (alpha 12e-6 /K) |
| 018-cable-comb | PASS | Claude chat round 4 | 4 s | cad.size: 60x20x5; cad.valid: True; cad.volume: 4800 (allowed - .. 5900) | dimensions as asked |
| 019-d-shaft-knob | PASS | Claude chat round 4 | 4 s | cad.size: 30x30x15; cad.valid: True; cad.volume: 1.031e+04 (allowed - .. 10500) | dimensions as asked; D-shaft 6 mm with 4.5 mm flat |
| 020-shelf-cantilever-udl | PASS | Claude chat round 4 | 26 s | max_displacement: 3.822 (1.0 % off, tol 5 %) | Roark, Table 8.1 case 2a (cantilever, uniform load), plus shear |
| 021-square-tube-cantilever | PASS | Claude chat round 4 | 149 s | max_displacement: 5.187 (0.1 % off, tol 5 %) | Roark, Table 8.1 case 1a with the hollow-section inertia (Table A.1), plus thin-wall shear |
| 022-clamped-disc-pressure | PASS | Claude chat round 4 | 625 s | max_displacement: 0.06544 (0.7 % off, tol 7 %) | Roark, Table 11.2 case 10b (circular plate, fixed edge, uniform pressure) |
| 023-pinned-rod-buckling | PASS | Claude chat round 4 | 17 s | buckling_factor_1: 2.08 (0.3 % off, tol 6 %) | Euler buckling, pinned-pinned (K = 1): P_cr = pi^2 E I / L^2 |
| 024-simply-supported-frequency | PASS | Claude chat round 4 | 17 s | frequency_1: 93.88 (0.1 % off, tol 5 %) | Euler-Bernoulli beam, simply supported, first mode: f = (pi / 2 L^2) sqrt(EI / rho A) |
| 025-petg-wall-convection | PASS | Claude chat round 4 | 104 s | min_temperature: 52.31 (0.0 % off, tol 1.5 %) | Incropera 3.1, plane wall with fixed temperature and convection (series resistances) |
| 026-heated-plate-in-air | PASS | Claude chat round 4 | 174 s | max_temperature: 43.61 (0.1 % off, tol 2 %) | Energy balance, Q = h A_total (T - T_inf); nearly uniform plate (Bi << 1) |
| 027-box-with-bosses | PASS | Claude chat round 4 | 1 s | cad.size: 80x60x30; cad.valid: True; cad.volume: 2.819e+04 (allowed 25200 .. 40000) | dimensions as asked; bosses add material inside a 24832 mm3 shell |
| 028-m3-hex-standoff | PASS | Claude chat round 4 | 7 s | cad.size: 5.5x6.351x20; cad.valid: True; cad.volume: 342.4 (allowed 300 .. 420) | dimensions as asked; hexagon (not a cylinder) with an M3 clearance hole |
| 029-printed-l-bracket | PASS | Claude chat round 4 | 0 s | cad.size: 20x40x40; cad.valid: True; cad.volume: 6030 (allowed 5000 .. 6050) | dimensions as asked; two 4 mm legs with a hole each |

PASS = every expected value within tolerance. ASKED = the agent asked a question instead (fine when the prompt really lacks an input, otherwise a gap). FAIL / ERROR = a gap to fix.
