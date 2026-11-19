# Benchmark scoreboard

2026-11-19 22:21 - **6 / 6 PASS** (solved blind from the plain-English prompt; answers from the cited source).

| Case | Outcome | Answered by | Time | Detail | Source |
|---|---|---|---|---|---|
| 011-shaft-torsion | PASS | toolkit check | 10 s | max_displacement: 0.1577 (0.0 % off, tol 5 %) | Shigley 10th ed. Eq. 4-5: phi = T L / (G J); surface displacement r phi |
| 012-fixed-fixed-beam | PASS | toolkit check | 5 s | max_displacement: 0.3709 (0.9 % off, tol 5 %) | Roark, Table 8.1 case 1c (both ends fixed, centre load) plus shear (Timoshenko) |
| 013-thick-tube-pressure | PASS | toolkit check | 66 s | max_von_mises: 280.1 (1.3 % off, tol 5 %) | Lame thick-walled cylinder, open ends (axial stress 0): von Mises at the bore |
| 014-plate-hole-tension | PASS | toolkit check | 187 s | max_von_mises: 125.7 (0.3 % off, tol 6 %) | Peterson's Stress Concentration Factors, chart 4.1 (Kt = 2.506 at d/w = 0.2, net section) |
| 016-pin-fin | PASS | toolkit check | 5 s | min_temperature: 65.07 (0.0 % off, tol 1.5 %) | Incropera 3.6.2, fin with convective tip: theta_L/theta_b = 1 / (cosh mL + (h/mk) sinh mL) |
| 017-free-expansion | PASS | toolkit check | 7 s | max_displacement: 0.4802 (0.0 % off, tol 3 %) | Free thermal expansion dL = alpha L dT (alpha 12e-6 /K) |

PASS = every expected value within tolerance. ASKED = the agent asked a question instead (fine when the prompt really lacks an input, otherwise a gap). FAIL / ERROR = a gap to fix.
