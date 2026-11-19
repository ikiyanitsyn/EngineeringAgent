# Benchmark scoreboard

2026-11-19 05:24 - **9 / 10 PASS** (solved blind from the plain-English prompt; answers from the cited source).

| Case | Outcome | Answered by | Time | Detail | Source |
|---|---|---|---|---|---|
| 001-cantilever-mass | PASS | rules | 16 s | max_displacement: 0.9388 (0.3 % off, tol 5 %) | Roark's Formulas, Table 8.1 case 1a (cantilever, end load), with shear |
| 002-simply-supported | PASS | rules | 7 s | max_displacement: 0.1182 (1.7 % off, tol 7 %) | Roark, Table 8.1 case 1e (simply supported, centre load) |
| 003-column-buckling | PASS | rules | 15 s | buckling_factor_1: 6.915 (0.1 % off, tol 5 %) | Euler buckling, fixed-free (K = 2) |
| 004-cantilever-frequency | PASS | gemini-3.8-flash | 256 s | frequency_1: 45.54 (0.4 % off, tol 5 %) | Euler-Bernoulli beam, clamped-free, first mode |
| 005-hot-bar-convection | PASS | rules | 3 s | min_temperature: 96.19 (0.0 % off, tol 1 %) | Incropera 3.1.3, thermal circuit |
| 006-restrained-bar-heating | PASS | rules | 6 s | max_von_mises: 126 (0.0 % off, tol 3 %) | sigma = E alpha dT (bar held axially at both ends) |
| 007-bonded-bars | PASS | rules | 58 s | max_displacement: 0.04806 (0.3 % off, tol 3 %) | series springs: P L1/(A E1) + P L2/(A E2) |
| 008-printable-box | PASS | rules | 1 s | cad.size: 110x75x45 | dimensions as asked |
| 009-m5-spacer | PASS | rules | 0 s | cad.size: 12x12x15 | dimensions as asked; ISO 273 medium clearance 5.5 mm |
| 010-cable-clip | ERROR | - | 1098 s | LLMError: the language model could not be used. gemini-3.8-flash at https://generativelanguage.googleapis.com/v1beta/openai/chat/completions: HTTP 429 [{
  "error": {
    "code": 429,
    "message": "You exceed | custom shape: a valid printable solid; fit judged by eye |

PASS = every expected value within tolerance. ASKED = the agent asked a question instead (fine when the prompt really lacks an input, otherwise a gap). FAIL / ERROR = a gap to fix.
