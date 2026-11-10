---
name: composites-manufacturing
description: Analysis for thermoplastic composite manufacturing and design - laminate stiffness and expansion (classical laminate theory), process-induced residual stress, spring-in and warpage on cool-down, tool-part thermal mismatch, through-thickness heat-up and cooling of laminates in press/stamp forming, consolidation, AFP or overmoulding, cooling rate through crystallisation, and tooling thermal design. Use for CF/PEEK, CF/PEKK, LM-PAEK, CF/PPS, GF/PP, UD tape, organosheet, laminate, layup, ply, spring-in, tool compensation, consolidation or cool-down questions.
---

# Thermoplastic composites: design and manufacturing analysis

## Materials in the library (`./ea materials --family tp_composite`)

Laminae: `cf_peek_ud`, `cf_pekk_ud`, `cf_lmpaek_ud`, `cf_pps_fabric`, `gf_pp_ud`
(axes: 1 fibre, 2 transverse, 3 through-thickness). Neat polymers: `peek`, `pekk`,
`lmpaek`, `pps`, `pei`, `pp`. Tooling: `invar_36`, `tool_steel_p20`, `al_mic6`,
`steel_s355`. Each lamina carries Tg, Tm, process temperature and a stress-free
temperature (about the crystallisation peak). Values are typical; ask the user for the
supplier data sheet values and override:
`{"base": "cf_peek_ud", "E1": "142 GPa", "cte2": 30}`.

## Ask first

Material system and layup, part thickness and geometry, process (stamp forming, press
consolidation, AFP in-situ or oven, overmoulding, welding), tool material and
temperature, process temperatures and times, what matters (angle tolerance, flatness,
cycle time, crystallinity).

## 1. Laminate properties and residual stress (hand calculation)

    ./ea calc composite.laminate material=cf_peek_ud layup="[0/45/-45/90]2s" dT=-290

Gives in-plane and flexural moduli, Poisson ratio, in-plane and through-thickness
expansion, and (with `dT` = service temperature minus stress-free temperature) the
worst ply residual stresses with the ratio to transverse strength. Unsymmetric or
unbalanced layups get a warning with the thermal curvature (warpage).

Layup notation: a list `[0, 45, -45, 90]` with `symmetric=true`, or a string such as
`"[0/±45/90]2s"`.

## 2. Spring-in of bends

    ./ea calc composite.spring_in angle=90 alpha_inplane="2.7 um/m/K" alpha_thickness="38.6 um/m/K" dT=-290 flange=40

Take the two expansion coefficients from `composite.laminate` (alpha_x or alpha_y in
the bend direction, alpha_z). The result is the angle by which the bend closes and the
flange tip offset; compensate the tool by that angle. Add crystallisation shrinkage
strains (`shrinkage_inplane`, `shrinkage_thickness`) when known.

FEA version (captures geometry and stacking effects the formula ignores):

    ./ea fea new jobs/NN-spring-in -a spring_in
    ./ea fea run jobs/NN-spring-in --report

Key points of that job: the laminate is a smeared orthotropic solid built from the layup
(`"material": {"laminate": {"lamina": "cf_peek_ud", "layup": "[0/45/-45/90]2s"}}`), a
cylindrical orientation follows the bend (`"orientation": {"system": "cylindrical",
"origin": [...], "axis": [...]}` - radial = thickness, tangential = laminate 0 deg,
axial = laminate 90 deg), the load is a uniform `temperature_change` from the
stress-free temperature to room temperature, restraint is `minimal`, and
`"angles": {"spring_in": {"between": ["start", "end"]}}` measures the change in angle
between two faces. For an L- or U-section with flanges, model flanges and corner as
separate parts with their own orientation, tied together (`fea-assembly`).

## 3. Heat-up, consolidation and cooling through the thickness

    ./ea calc composite.consolidation_heatup material=cf_peek_ud thickness=4 T_initial=20 T_tool=385 T_target=380
    ./ea calc composite.consolidation_heatup material=cf_peek_ud thickness=4 T_initial=385 T_tool=180 T_target=200 h=1500

Omit `h` for perfect contact with a matched metal tool; give a contact/film coefficient
for diaphragm, vacuum-bag or air cooling; `one_sided=true` when one face is insulated.
Outputs: time for the mid-plane to reach the target and the mean rate.

FEA version for real geometry, tool plus laminate, or temperature schedules:

    ./ea fea new jobs/NN-heatup -a thermal_transient

Use temperature `schedule`s on tool faces for ramps and dwells, `convection` with a
`schedule` for transfer/air cooling, probes at mid-plane and surface with a `target`,
and `"thermal": {"rate_window": [T_high, T_low]}` to get the cooling rate through the
crystallisation range. Model a through-thickness slice, not the whole part.

## 4. Cooling rate and crystallinity

    ./ea calc composite.cooling_rate_check material=cf_peek_ud rate="40 K/min"

Compares the rate through crystallisation with the typical window for the polymer
(PEEK about 5-700 K/min, PEKK slower-crystallising: about 2-60 K/min). Too slow gives
coarse, brittle morphology; too fast leaves an amorphous skin. Thick laminates cool
slowly at the core and fast at the skin - check both probes.

## 5. Tool-part interaction and tooling

- Thermal mismatch: tool growth = alpha_tool x L x dT (`thermal.free_expansion`).
  Aluminium tooling grows about 23 um/m/K against a laminate at 0-3 um/m/K in-plane:
  several mm per metre over a 350 K cycle. Invar matches composites best.
- Part locked on a tool during cool-down: `thermal_stress` assembly with the laminate
  tied (or in contact) to the tool, uniform cool-down, different materials.
- Tool heat-up and temperature uniformity: `thermal_transient` on the tool with heater
  power (`heat_power`) or cartridge bores at a `temperature` schedule; judge uniformity
  from max-min temperature on the moulding face.
- Tool deflection under press load: `fea-mechanical` static with a `pressure` load.

## What the models do not capture (say this)

- Smeared laminate solids give laminate-level deformation and stress. Ply stresses come
  from `composite.laminate`; free-edge and interlaminar stresses are not resolved.
- No melting/crystallisation latent heat, no crystallinity-dependent properties, no
  viscoelastic relaxation above Tg: stress is taken to build from the stress-free
  temperature down, which is the standard first-order approach.
- Fibre movement, wrinkling, ply slip during forming and thickness variation at radii
  are not modelled; spring-in in practice is often larger than the thermoelastic value.
  Treat the result as the starting point for tool compensation and confirm on trial parts.
