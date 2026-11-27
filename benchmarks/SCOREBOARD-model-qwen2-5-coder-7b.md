# Benchmark scoreboard

2026-11-27 06:15 - **11 / 29 PASS** (solved blind from the plain-English prompt; answers from the cited source).

| Case | Outcome | Answered by | Time | Detail | Source |
|---|---|---|---|---|---|
| 001-cantilever-mass | PASS | model | 38 s | max_displacement: 0.9388 (0.3 % off, tol 5 %) | Roark's Formulas, Table 8.1 case 1a (cantilever, end load), with shear |
| 002-simply-supported | FAIL | model | 39 s | max_displacement: 0.01552 (86.6 % off, tol 7 %) | Roark, Table 8.1 case 1e (simply supported, centre load) |
| 003-column-buckling | FAIL | model | 36 s | buckling_factor_1: no such result | Euler buckling, fixed-free (K = 2) |
| 004-cantilever-frequency | ASKED | model | 12 s | The request is for a natural frequency, but the current template does not support frequency analysis. Please specify if you want to perform a strength/stiffness analysis or if you need additional info | Euler-Bernoulli beam, clamped-free, first mode |
| 005-hot-bar-convection | PASS | model | 44 s | min_temperature: 96.19 (0.0 % off, tol 1 %) | Incropera 3.1.3, thermal circuit |
| 006-restrained-bar-heating | ASKED | model | 16 s | To run the analysis I still need: where the part is held (bolted, clamped); the starting and final temperature. Please reply with those - I will not guess them. | sigma = E alpha dT (bar held axially at both ends) |
| 007-bonded-bars | FAIL | model | 33 s | max_displacement: 9.542 (19700.1 % off, tol 3 %) | series springs: P L1/(A E1) + P L2/(A E2) |
| 008-printable-box | PASS | model | 15 s | cad.size: 110x75x45 | dimensions as asked |
| 009-m5-spacer | PASS | model | 13 s | cad.size: 12x12x15 | dimensions as asked; ISO 273 medium clearance 5.5 mm |
| 010-cable-clip | PASS | model | 20 s | cad.valid: True | custom shape: a valid printable solid; fit judged by eye |
| 011-shaft-torsion | PASS | model | 27 s | max_displacement: 0.1577 (0.0 % off, tol 5 %) | Shigley 10th ed. Eq. 4-5: phi = T L / (G J); surface displacement r phi |
| 012-fixed-fixed-beam | FAIL | model | 32 s | max_displacement: 0.1844 (50.7 % off, tol 5 %) | Roark, Table 8.1 case 1c (both ends fixed, centre load) plus shear (Timoshenko) |
| 013-thick-tube-pressure | ASKED | model | 30 s | Before I run the analysis I need a few facts from you - I will not guess them, because the answer depends on them: - the starting temperature (25 - not a temperature in your message) - the final tempe | Lame thick-walled cylinder, open ends (axial stress 0): von Mises at the bore |
| 014-plate-hole-tension | FAIL | model | 211 s | max_von_mises: 402.1 (220.9 % off, tol 6 %) | Peterson's Stress Concentration Factors, chart 4.1 (Kt = 2.506 at d/w = 0.2, net section) |
| 015-imperial-cantilever | ASKED | model | 25 s | To run the analysis I still need: where the part is held (bolted, clamped); the load (size, direction and where it acts). Please reply with those - I will not guess them. | Roark, Table 8.1 case 1a (cantilever, end load), inch units |
| 016-pin-fin | FAIL | model | 46 s | min_temperature: 79.12 (21.6 % off, tol 1.5 %) | Incropera 3.6.2, fin with convective tip: theta_L/theta_b = 1 / (cosh mL + (h/mk) sinh mL) |
| 017-free-expansion | ASKED | model | 18 s | To run the analysis I still need: where the part is held (bolted, clamped); the starting and final temperature. Please reply with those - I will not guess them. | Free thermal expansion dL = alpha L dT (alpha 12e-6 /K) |
| 018-cable-comb | PASS | model | 37 s | cad.size: 60x20x5; cad.valid: True; cad.volume: 5749 (allowed - .. 5900) | dimensions as asked |
| 019-d-shaft-knob | PASS | model | 19 s | cad.size: 30x30x15; cad.valid: True; cad.volume: 1.018e+04 (allowed - .. 10500) | dimensions as asked; D-shaft 6 mm with 4.5 mm flat |
| 020-shelf-cantilever-udl | PASS | model | 48 s | max_displacement: 3.822 (1.0 % off, tol 5 %) | Roark, Table 8.1 case 2a (cantilever, uniform load), plus shear |
| 021-square-tube-cantilever | FAIL | model | 35 s | max_displacement: 2.442 (52.9 % off, tol 5 %) | Roark, Table 8.1 case 1a with the hollow-section inertia (Table A.1), plus thin-wall shear |
| 022-clamped-disc-pressure | ASKED | model | 24 s | Is the load of 1 bar a force or a pressure? Please state it with its unit. | Roark, Table 11.2 case 10b (circular plate, fixed edge, uniform pressure) |
| 023-pinned-rod-buckling | FAIL | model | 26 s | buckling_factor_1: no such result / errors: `ea analyze /tmp/bench-fuhpqpq2/jobs/01-beam -m al_6061_t6 --fix xmin --fix xmax --force zmax 0,0,-1000`: ValueError: set 'zmax': selector 'zmax' matched no CAD face (xmin..zmax pick only FLAT faces a | Euler buckling, pinned-pinned (K = 1): P_cr = pi^2 E I / L^2 |
| 024-simply-supported-frequency | ASKED | model | 14 s | The request is for the first natural frequency of a steel bar, but the provided information does not include the material, where the part is held, or the load. Please provide the material, where the p | Euler-Bernoulli beam, simply supported, first mode: f = (pi / 2 L^2) sqrt(EI / rho A) |
| 025-petg-wall-convection | FAIL | model | 183 s | min_temperature: 20.63 (60.6 % off, tol 1.5 %) | Incropera 3.1, plane wall with fixed temperature and convection (series resistances) |
| 026-heated-plate-in-air | ASKED | model | 52 s | Before I run the analysis I need a few facts from you - I will not guess them, because the answer depends on them: - the load (5 kN - your message does not give a force of that size)  Please give the  | Energy balance, Q = h A_total (T - T_inf); nearly uniform plate (Bi << 1) |
| 027-box-with-bosses | PASS | model | 25 s | cad.size: 80x60x30; cad.valid: True; cad.volume: 2.819e+04 (allowed 25200 .. 40000) | dimensions as asked; bosses add material inside a 24832 mm3 shell |
| 028-m3-hex-standoff | FAIL | model | 15 s | cad.size: 5.5x5.5x20; cad.valid: True; cad.volume: 184.7 (allowed 300 .. 420) | dimensions as asked; hexagon (not a cylinder) with an M3 clearance hole |
| 029-printed-l-bracket | PASS | model | 24 s | cad.size: 20x40x40; cad.valid: True; cad.volume: 6030 (allowed 5000 .. 6050) | dimensions as asked; two 4 mm legs with a hole each |

PASS = every expected value within tolerance. ASKED = the agent asked a question instead (fine when the prompt really lacks an input, otherwise a gap). FAIL / ERROR = a gap to fix.
