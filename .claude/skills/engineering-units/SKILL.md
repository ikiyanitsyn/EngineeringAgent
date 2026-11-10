---
name: engineering-units
description: Show or switch the unit system used by every engineering skill, command, job and report - metric (mm, kg, N, MPa, degC) or imperial / SAE / US customary (in, lbm, lbf, psi, degF). Use when the user says "switch to imperial", "use inches", "SAE units", "back to metric", asks what units are active, or asks to convert a value.
---

# Unit system toggle

One setting controls all skills. It is saved in `engagent.config.json` at the repository
root, so it follows the repository to every machine.

## Commands

    ./ea units                 # show the active system and the default unit of each quantity
    ./ea units imperial        # switch everything to in, lbm, lbf, psi, degF  (aliases: sae, us, inch)
    ./ea units metric          # switch everything to mm, kg, N, MPa, degC      (alias: si)
    ./ea convert "30 psi" pressure          # show a value in both systems
    ./ea convert "2.5 in" length mm         # convert to a named unit
    ./ea standard                           # tolerancing standard: auto | iso | asme

Add `--units imperial` (or `metric`) to any single command to override the saved system
for that call only.

## Rules

1. After switching, confirm to the user in one line what changed and that it applies to
   all later work until toggled back.
2. A bare number means "in the active system's default unit for that quantity".
   A string with a unit ("0.25 in", "210 GPa", "150 degF") is read in that unit whatever
   system is active. When the user gives mixed units, keep their unit strings as given.
3. Existing job files: a job with `"units"` inside keeps that system. A job without it is
   read in the active system, so do not toggle between writing a job and running it. When
   in doubt, write `"units"` into the job.
4. Geometry scripts stay in mm. Convert the user's inch dimensions through `params()`
   overrides or write the mm value with the inch value in a comment.
5. The tolerancing standard follows the unit system unless forced: metric -> ISO GPS,
   imperial -> ASME Y14.5-2018.
6. Never convert solver-internal values by hand. Reports and CLI output are already in the
   active system.

## Default units

| Quantity | metric | imperial |
| --- | --- | --- |
| length | mm | in |
| force / moment | N / N*m | lbf / lbf*in |
| stress, pressure, modulus | MPa (GPa accepted) | psi (ksi, Msi accepted) |
| mass / density | kg / kg/m^3 | lbm / lbm/in^3 |
| temperature / difference | degC / K | degF / degF |
| thermal expansion | um/m/K | uin/in/F |
| conductivity | W/m/K | BTU/hr/ft/F |
| specific heat | J/kg/K | BTU/lbm/F |
| film coefficient | W/m^2/K | BTU/hr/ft2/F |
| heat flux / power | W/m^2 / W | BTU/hr/ft2 / BTU/hr |
| acceleration | g | g |

Longer forms also work: cm, m, ft, kN, kip, kPa, bar, g, tonne, slug, K, rpm, etc.
`./ea convert` reports an error listing valid units if one is not recognised.
