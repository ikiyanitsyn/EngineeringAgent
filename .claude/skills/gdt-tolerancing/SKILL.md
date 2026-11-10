---
name: gdt-tolerancing
description: Tolerancing and GD&T to ISO GPS (ISO 1101, ISO 286, ISO 2768) or ASME Y14.5-2018 - limits and fits, general tolerances, clearance holes, position tolerance for fastener patterns, feature control frames, datum schemes, tolerance stack-ups (worst case, RSS, Monte Carlo) and process capability. Use when the user asks about tolerances, fits (H7/g6), datums, a drawing callout, whether parts will assemble, a stack-up, or what a manufacturing process can hold.
---

# Tolerancing and GD&T

Standard in force: `./ea standard` (auto: ISO GPS with metric units, ASME Y14.5-2018
with imperial; force with `./ea standard iso|asme`).

## Commands

    ./ea gdt fit 25 H7/g6                  # limits, clearance/interference, fit type (ISO 286 / ASME B4.2)
    ./ea gdt general 120 m                 # ISO 2768-1 linear tolerance; classes f m c v
    ./ea gdt general 120 K --kind flatness # ISO 2768-2 geometrical; classes H K L
    ./ea gdt hole M6 --joint fixed         # clearance hole + largest safe position tolerance
    ./ea gdt frame position 0.2 A B C --dia --mod M     # feature control frame text
    ./ea gdt process                       # what each process holds (typical / best)
    ./ea gdt process cnc_milling 50 0.02   # is +/-0.02 on 50 realistic for milling?
    ./ea gdt stack stack.json --monte-carlo 20000
    ./ea gdt review jobs/NN-name/job.json  # rule check of a whole scheme

## Building a scheme (in this order)

1. **Function first.** What must fit, seal, align or move? Tolerances come from that.
2. **Datums.** Primary = the face that seats the part (3 points), secondary = the
   feature that stops rotation (2 points), tertiary = the stop (1 point). Choose the
   surfaces the part is actually mounted and measured on, and give each datum feature a
   form control (flatness, cylindricity) or orientation control to the higher datum.
3. **Size** of features of size: fits for bores/shafts (`gdt fit`), clearance holes for
   fasteners (`gdt hole`).
4. **Location and orientation** with feature control frames: position for holes and
   patterns, profile for free-form surfaces, perpendicularity/parallelism for mounting
   faces. Position tolerance for a fastener pattern must not exceed:
   floating fastener `T = H - F`; fixed fastener (threaded hole) `T = (H - F) / 2`.
5. **General tolerance** for everything else: ISO 2768-mK (machined) or the title-block
   default for inch drawings.
6. **Stack-ups** for every functional gap or interference.
7. **Process check**: every tolerance against the process that will make it.
8. Run `gdt review` and fix what it finds.

## Scheme format (file or the "gdt" block of job.json)

    {
      "standard": "iso",                 // optional
      "process": "cnc_milling",
      "general_tolerance": "ISO 2768-mK",
      "datums": [
        {"label": "A", "feature": "mounting face", "reason": "seats on the frame"},
        {"label": "B", "feature": "locating bore", "reason": "centres the part"},
        {"label": "C", "feature": "side face", "reason": "stops rotation"}
      ],
      "features": [
        {"name": "mounting face", "type": "surface",
         "fcf": {"characteristic": "flatness", "tolerance": 0.05}},
        {"name": "locating bore", "type": "hole", "nominal": 20, "fit": "H7/g6",
         "fcf": {"characteristic": "perpendicularity", "tolerance": 0.02, "diameter": true, "datums": ["A"]}},
        {"name": "bolt holes 4x", "type": "hole", "nominal": 6.6, "tol": 0.1,
         "fcf": {"characteristic": "position", "tolerance": 0.2, "diameter": true,
                 "modifier": "M", "datums": ["A", "B", "C"]},
         "fastener": {"size": "M6", "joint": "fixed"}}
      ],
      "stacks": [
        {"name": "bearing end float",
         "contributors": [
           {"name": "housing depth", "nominal": 50, "tol": 0.1, "direction": 1},
           {"name": "bearing width", "nominal": 15, "plus": 0, "minus": 0.12, "direction": -1},
           {"name": "spacer", "nominal": 34.8, "tol": 0.05, "direction": -1}],
         "limits": {"min": 0.05, "max": 0.5}, "monte_carlo": 20000}
      ]
    }

`direction` +1 opens the gap, -1 closes it. Feature `type` words that count as features
of size (and may take the M/L modifier): hole, pin, shaft, slot, tab, boss, bore, width.

Characteristics: straightness, flatness, circularity, cylindricity, profile_line,
profile_surface, perpendicularity, parallelism, angularity, position, concentricity,
symmetry, circular_runout, total_runout.

## What the review checks

- form tolerances carry no datums; orientation, location and runout tolerances do
- every referenced datum is defined; datum features have a form control
- M / L modifiers only on features of size
- position tolerance against the fixed/floating fastener limit (parts will assemble)
- size and geometric tolerances against process capability
- ASME: concentricity and symmetry were removed in Y14.5-2018 (use position / runout / profile)
- every stack against its functional limits (worst case, then statistically)

## ISO versus ASME (state which applies)

| | ISO GPS | ASME Y14.5-2018 |
| --- | --- | --- |
| size vs form | independent (ISO 8015); envelope only with the E modifier | Rule #1: size limits control form |
| material condition | maximum material requirement, ISO 2692 | MMC / LMC; RFS by default |
| general tolerances | ISO 2768-1 / -2 | title block |
| fits | ISO 286 | ASME B4.2 (same system); B4.1 inch classes are not tabulated here |
| decimal style | 0.2 (leading zero) | .2 for inch (no leading zero) |

## Rules

- Never tolerance tighter than the function needs; each IT grade tighter costs money.
- A tolerance the process cannot hold is flagged REVIEW with the secondary operation
  needed (ream, bore, grind). Tell the user the cost implication.
- Worst-case failure but RSS pass is acceptable only for volume production under
  process control; say so.
- Stack-ups here are one-dimensional. Angular and geometric effects (tilt across a
  short datum, position at MMC bonus) need their own lines or a 3D analysis.
- Fit tables cover 0-500 mm, IT5-IT14, holes H G F E D JS, shafts d e f g h js k n p s.
- This is a rule-based check of the scheme given, not a drawing sign-off.
