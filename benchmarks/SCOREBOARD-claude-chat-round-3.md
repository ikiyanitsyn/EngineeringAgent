# Benchmark scoreboard

2026-11-26 08:36 - **10 / 10 PASS** (solved blind from the plain-English prompt; answers from the cited source).

| Case | Outcome | Answered by | Time | Detail | Source |
|---|---|---|---|---|---|
| 020-shelf-cantilever-udl | PASS | Claude chat round 3 | 34 s | max_displacement: 3.822 (1.0 % off, tol 5 %) | Roark, Table 8.1 case 2a (cantilever, uniform load), plus shear |
| 021-square-tube-cantilever | PASS | Claude chat round 3 | 129 s | max_displacement: 5.187 (0.1 % off, tol 5 %) | Roark, Table 8.1 case 1a with the hollow-section inertia (Table A.1), plus thin-wall shear |
| 022-clamped-disc-pressure | PASS | Claude chat round 3 | 630 s | max_displacement: 0.06544 (0.7 % off, tol 7 %) | Roark, Table 11.2 case 10b (circular plate, fixed edge, uniform pressure) |
| 023-pinned-rod-buckling | PASS | Claude chat round 3 | 21 s | buckling_factor_1: 2.083 (0.2 % off, tol 6 %) | Euler buckling, pinned-pinned (K = 1): P_cr = pi^2 E I / L^2 |
| 024-simply-supported-frequency | PASS | Claude chat round 3 | 42 s | frequency_1: 93.76 (0.1 % off, tol 5 %) | Euler-Bernoulli beam, simply supported, first mode: f = (pi / 2 L^2) sqrt(EI / rho A) |
| 025-petg-wall-convection | PASS | Claude chat round 3 | 15 s | min_temperature: 52.31 (0.0 % off, tol 1.5 %) | Incropera 3.1, plane wall with fixed temperature and convection (series resistances) |
| 026-heated-plate-in-air | PASS | Claude chat round 3 | 193 s | max_temperature: 43.61 (0.1 % off, tol 2 %) | Energy balance, Q = h A_total (T - T_inf); nearly uniform plate (Bi << 1) |
| 027-box-with-bosses | PASS | Claude chat round 3 | 1 s | cad.size: 80x60x30; cad.valid: True; cad.volume: 2.819e+04 (allowed 25200 .. 40000) | dimensions as asked; bosses add material inside a 24832 mm3 shell |
| 028-m3-hex-standoff | PASS | Claude chat round 3 | 3 s | cad.size: 5.5x6.351x20; cad.valid: True; cad.volume: 342.4 (allowed 300 .. 420) | dimensions as asked; hexagon (not a cylinder) with an M3 clearance hole |
| 029-printed-l-bracket | PASS | Claude chat round 3 | 0 s | cad.size: 20x40x40; cad.valid: True; cad.volume: 5940 (allowed 5000 .. 6050) | dimensions as asked; two 4 mm legs with a hole each |

PASS = every expected value within tolerance. ASKED = the agent asked a question instead (fine when the prompt really lacks an input, otherwise a gap). FAIL / ERROR = a gap to fix.
