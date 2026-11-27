# Benchmark scoreboard

2026-11-27 05:40 - **4 / 6 PASS** (solved blind from the plain-English prompt; answers from the cited source).

| Case | Outcome | Answered by | Time | Detail | Source |
|---|---|---|---|---|---|
| 001-cantilever-mass | PASS | model | 96 s | max_displacement: 0.9388 (0.3 % off, tol 5 %) | Roark's Formulas, Table 8.1 case 1a (cantilever, end load), with shear |
| 005-hot-bar-convection | PASS | model | 36 s | min_temperature: 96.19 (0.0 % off, tol 1 %) | Incropera 3.1.3, thermal circuit |
| 009-m5-spacer | PASS | model | 14 s | cad.size: 12x12x15 | dimensions as asked; ISO 273 medium clearance 5.5 mm |
| 011-shaft-torsion | FAIL | model | 27 s | max_displacement: no such result / errors: `ea make beam length=200 width=20 height=20 section=20 --name "beam"`: ValueError: section must be rect, round, tube, rect_tube or i; `ea analyze last -m steel_generic --fix xmin --force xmax 0,0,-100 | Shigley 10th ed. Eq. 4-5: phi = T L / (G J); surface displacement r phi |
| 016-pin-fin | FAIL | model | 48 s | min_temperature: no such result / errors: `ea make standoff outer_diameter=5 hole=5 height=50 base_diameter=0 base_height=0 --name "standoff"`: ValueError: template 'standoff' with these parameters does not give one valid solid (valid=True, s | Incropera 3.6.2, fin with convective tip: theta_L/theta_b = 1 / (cosh mL + (h/mk) sinh mL) |
| 018-cable-comb | PASS | model | 37 s | cad.size: 60x20x5; cad.valid: True; cad.volume: 5749 (allowed - .. 5900) | dimensions as asked |

PASS = every expected value within tolerance. ASKED = the agent asked a question instead (fine when the prompt really lacks an input, otherwise a gap). FAIL / ERROR = a gap to fix.
