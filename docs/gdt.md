# Tolerancing reference

Commands, scheme format and the review rules are in the `gdt-tolerancing` skill
(`.claude/skills/gdt-tolerancing/SKILL.md`). This page lists what is tabulated.

| Topic | Coverage | Source |
| --- | --- | --- |
| Limits and fits | nominal 0-500 mm; grades IT5-IT14; holes H, G, F, E, D, JS; shafts d, e, f, g, h, js, k, n, p, s | ISO 286-1/-2 (ASME B4.2 uses the same system) |
| General tolerances, linear / radius / angular | classes f, m, c, v | ISO 2768-1 |
| General tolerances, geometrical | flatness, straightness, perpendicularity, symmetry, run-out; classes H, K, L | ISO 2768-2 |
| Clearance holes, metric | M2-M30; fine / medium / coarse | ISO 273 |
| Clearance holes, inch | #4 to 1 in; close / normal / loose | ASME B18.2.8 |
| Position tolerance for fasteners | floating `T = H - F`; fixed `T = (H - F)/2`; projected zone | ASME Y14.5-2018 Appendix B; ISO 2692 |
| Geometric characteristics | all 14 symbols; M, L, F, P, U, E modifiers | ISO 1101:2017; ASME Y14.5-2018 |
| Process capability | CNC milling/turning, grinding, reaming, drilling, laser, bending, FDM, SLA, SLS, MJF, DMLS, injection moulding, die and sand casting, thermoplastic-composite stamp forming, AFP consolidation, overmoulding, composite trimming | typical shop values; confirm with the supplier |
| Stack-up | 1-D worst case, RSS (Cpk, ppm), Monte Carlo (normal or uniform) | - |

Not covered: ANSI B4.1 inch fit classes (RC, LC, LT, LN, FN), hole deviations K to ZC,
sizes above 500 mm, 3-D stack-ups, drawing generation. Inch title-block defaults
(`.X +/-.030`, `.XX +/-.010`, `.XXX +/-.005`, angles +/-0.5 deg) are common practice,
not a standard; use the company's own.

The tables were transcribed from the standards and spot-checked (for example 25 H7 =
0/+21 um, g6 = -20/-7 um, p6 = +22/+35 um, s6 = +35/+48 um). Check critical fits
against your own copy of the standard.

Python API:

    from engagent import gdt
    gdt.fit(25, "H7/g6")                     # limits in mm
    gdt.general_tolerance(120, "m")          # +/- mm
    gdt.clearance_hole("M6", "medium")
    gdt.position_tolerance(6, 6.6, "fixed")
    gdt.frame("position", 0.2, ["A", "B", "C"], diameter=True, modifier="M")
    gdt.stack(contributors, limits={"min": 0.05, "max": 0.5}, monte_carlo=20000)
    gdt.review(scheme)
