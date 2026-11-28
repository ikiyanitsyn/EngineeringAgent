# Benchmark scoreboard

2026-11-28 06:18 - **4 / 5 PASS** (solved blind from the plain-English prompt; answers from the cited source).

| Case | Outcome | Answered by | Time | Detail | Source |
|---|---|---|---|---|---|
| 030-lfam-tool-panel-pressure | PASS | Claude chat round 5 | 24 s | max_displacement: 6.805 (0.9 % off, tol 7 %) | Euler-Bernoulli beam, simply supported, uniform load: 5 w L^4 / (384 E1 I) + shear w L^2 / (8 k G A); E1 (bead direction) 7414 MPa, PolyCore PETG-1013 TDS |
| 031-lfam-block-z-compression | FAIL | Claude chat round 5 | 347 s | max_displacement: 0.1705 (6.2 % off, tol 5 %) | Axial bar through the layers: P L / (A E3), E3 (Z) 2492 MPa, PolyCore PETG-1013 TDS |
| 032-lfam-arm-printed-flat | PASS | Claude chat round 5 | 7 s | max_displacement: 9.146 (0.5 % off, tol 5 %) | Cantilever, end load, E1 (bead direction) 7414 MPa: P L^3 / (3 E I) + P L / (k G A) |
| 033-lfam-arm-printed-upright | PASS | Claude chat round 5 | 9 s | max_displacement: 6.759 (0.5 % off, tol 6 %) | Cantilever, end load, E3 (through the layers) 2492 MPa: P L^3 / (3 E I) + P L / (k G A) |
| 034-steel-i-beam-cantilever | PASS | Claude chat round 5 | 143 s | max_displacement: 2.117 (0.6 % off, tol 6 %) | Roark Table 8.1 case 1a with the I-section inertia (Table A.1); web shear P L / (G h tw) |

PASS = every expected value within tolerance. ASKED = the agent asked a question instead (fine when the prompt really lacks an input, otherwise a gap). FAIL / ERROR = a gap to fix.
