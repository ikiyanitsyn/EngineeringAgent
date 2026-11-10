---
name: hand-calcs
description: Closed-form engineering hand calculations with formulas and textbook references - beams, columns, plates, torsion, pressure vessels, stress concentration, thermal expansion and heat transfer, fatigue, bolted joints, composite laminates. Use before any FEA run to predict the answer, for quick sizing questions ("how thick", "what deflection", "what torque"), and to check a result.
---

# Hand calculations

A result you cannot roughly predict is a result you cannot trust. Every FEA job gets a
hand calculation first.

## Commands

    ./ea calc list                      # all calculations
    ./ea calc list beam                 # filter by word
    ./ea calc beam.cantilever_end_load --help-calc     # inputs, formulas, reference
    ./ea calc beam.cantilever_end_load P=100 L=100 E="210 GPa" b=10 h=10 nu=0.3

Inputs are `name=value`. Bare numbers use the active unit system; quote values that
carry units. Output shows results, the formulas used and the reference.

## Catalogue

| Area | Calculations |
| --- | --- |
| Sections | `section.rectangle`, `.circle`, `.tube`, `.rect_tube`, `.i_beam` |
| Beams | `beam.cantilever_end_load`, `.cantilever_udl`, `.cantilever_end_moment`, `.simply_supported_center_load`, `.simply_supported_udl`, `.fixed_fixed_center_load`, `.fixed_fixed_udl`, `.natural_frequency` |
| Columns | `column.euler_buckling` (with Johnson short-column check) |
| Axial / torsion | `axial.bar`, `torsion.round_shaft` |
| Pressure | `pressure.thin_cylinder`, `pressure.thick_cylinder` |
| Plates | `plate.rectangular_uniform`, `plate.circular_uniform` |
| Stress concentration | `kt.plate_hole_tension`, `kt.shoulder_fillet_tension` |
| Combined stress | `stress.von_mises` |
| Thermal stress | `thermal.restrained_bar`, `thermal.free_expansion` |
| Heat transfer | `thermal.conduction_slab`, `.convection`, `.wall_conduction_convection`, `.lumped_transient`, `.slab_transient`, `.fin_straight`, `.radiation` |
| Fatigue | `fatigue.endurance_limit`, `.mean_stress`, `.basquin_life` |
| Bolts | `bolt.preload_torque`, `.joint_tension`, `.shear_bearing` |
| Composites | `composite.laminate`, `.spring_in`, `.consolidation_heatup`, `.cooling_rate_check` |

Beam calculations take a section either as `I`, `c`, `A` or as a shape: `b h`
(rectangle), `d` (round), `D t` (tube), `b h t` (box), `b h tf tw` (I-beam). Add `nu`
to include shear deflection. Add `x` to get the bending stress at a section.

## How to use them

1. Idealise the real part as the nearest textbook case and say what you simplified
   (e.g. "bracket arm treated as a cantilever of the minimum section").
2. Run the calculation and write down the expected value with its unit.
3. If no closed form fits, bound the answer with two simple cases (stiffer and softer)
   and state the range.
4. Link the calculation to the FEA job so the run checks itself:

       "hand_calcs": [
         {"name": "Tip deflection", "calc": "beam.cantilever_end_load",
          "inputs": {"P": 100, "L": 100, "E": "210 GPa", "b": 10, "h": 10, "nu": 0.3},
          "output": "deflection", "metric": "probe.tip.uz", "tol": 0.02},
         {"name": "Own estimate", "expected": "0.19 mm", "kind": "length",
          "formula": "P L^3 / (3 E I)", "metric": "max_displacement", "tol": 0.05}
       ]

   `metric` names an FEA result (see `docs/job-reference.md`). Compare like with like:
   a probe at the same location, the same stress component, away from supports.
5. Typical tolerances: deflection 2-5 %, frequency 3 %, buckling factor 3-5 %, stress
   away from discontinuities 10 %, temperature 1-2 % of the temperature range,
   heat flow 1-2 %.

## Rules

- Quote the formula and the reference with the number.
- Check the validity notes the tool prints (thin-wall limit, Biot number, slenderness,
  plate deflection versus thickness). If a note says the formula is outside its range,
  do not use the value as the reference.
- A hand calculation that disagrees with FEA means one of them is wrong. Find out which
  before reporting either: units, load on the wrong face, wrong support, wrong section,
  shear deflection, stress read at a singularity.
- Steel fatigue correlations do not apply to aluminium, polymers or composites; pass a
  tested fatigue strength (`endurance_test=`) for those.
