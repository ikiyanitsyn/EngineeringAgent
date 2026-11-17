---
name: fea-thermal
description: Run heat-transfer and thermal-stress finite element analysis with CalculiX - steady conduction, convection and radiation boundaries, heat sources, transient heating and cooling, conduction-dominated problems, and thermo-mechanical (thermal-structural) stress and distortion. Use for temperature distribution, heat flow, heat sink, cool-down or heat-up time, thermal expansion, thermal stress, warpage or tool heating questions.
---

# Thermal and thermo-mechanical FEA

**Fast path:** most jobs are one line, e.g.
`./ea analyze <part.step|template|jobs/NN-name> -m MATERIAL --fix FACES --force FACES FX,FY,FZ --check "<hand calc>"`
(thermal: `--temp FACES T`, `--convect FACES H T_AMB`, `--heat FACES W`, `-a transient`).
Face shorthand: `xmin..zmax`, `plane:z=0`, `hole:D@x,y,z`, `cyl:R`, `near:x,y,z`. See `./ea analyze --help`.
Write a full `job.json` (below) only for what the one-liner cannot express.

## Ask first

Material (conductivity k, specific heat cp, density; plus E, nu, expansion for stress),
initial temperature, heat sources (power or flux and where), fixed temperatures,
convection (film coefficient h and ambient), radiation (emissivity and surroundings),
steady or transient and for how long, and what result is wanted.

## Hand-calculate first

| Situation | Calculation |
| --- | --- |
| conduction through a wall or bar | `thermal.conduction_slab` |
| wall with convection on one side | `thermal.wall_conduction_convection` |
| uniform body cooling in a fluid (Bi < 0.1) | `thermal.lumped_transient` |
| slab heated or cooled through its thickness | `thermal.slab_transient` |
| fin / pin | `thermal.fin_straight` |
| radiating surface | `thermal.radiation` |
| restrained expansion | `thermal.restrained_bar`, `thermal.free_expansion` |

## Run

    ./ea fea new jobs/NN-name -a thermal_steady      # also: convection, thermal_transient, thermal_stress
    ./ea fea run jobs/NN-name --converge --report

## Job blocks

Temperature boundary (a constraint):

    {"type": "temperature", "on": "hot", "value": 100}
    {"type": "temperature", "on": "platen", "schedule": [[0, 20], [600, 385], [1200, 385]]}   // time s, temperature

Thermal loads:

    {"type": "heat_power", "on": "chip", "value": 15}                 // total power on a face
    {"type": "heat_flux", "on": "face", "value": 5000}                // per unit area
    {"type": "heat_generation", "value": 2e5, "part": "coil"}         // per unit volume
    {"type": "convection", "on": "fins", "h": 25, "ambient": 20}
    {"type": "convection", "on": "skin", "h": 150, "schedule": [[0, 385], [300, 60]]}   // ambient vs time
    {"type": "radiation", "on": "outer", "emissivity": 0.85, "ambient": 20}

Faces with no thermal boundary are insulated (adiabatic).

**thermal_steady** - final temperature field and heat flows. Results:
`max_temperature`, `min_temperature`, `max_heat_flux`, `heat_flow.<set>` (heat entering
the model at each fixed-temperature set), `probe.<name>.temperature`.

**thermal_transient** - needs cp and density, plus:

    "initial_temperature": 20,
    "thermal": {"duration": 600, "increments": 100, "frames": 25, "rate_window": [340, 200]},
    "probes": {"core": {"point": [x, y, z], "target": 380}}

Fixed time step = duration / increments. Results per probe:
`probe.<name>.time_to_target` and, with `rate_window`, `probe.<name>.rate` (mean
heating or cooling rate between the two temperatures). A history plot goes into the
report. Check time-step convergence by doubling `increments`: results should move by
less than a few percent. Cost: every increment is a solve, so keep the mesh modest
(a few thousand nodes) for long transients; model a slice or use symmetry.

**thermal_stress** - three ways:

1. Uniform temperature change: no thermal boundaries, one load
   `{"type": "temperature_change", "value": 150}`; `initial_temperature` is the
   stress-free temperature.
2. Steady temperature field then stress: add temperature constraints and/or thermal
   loads to a `thermal_stress` job; the heat-transfer solution drives the expansion.
3. Transient: add `"thermal": {"transient": true, "duration": ..., "increments": ...}`.

Needs the expansion coefficient (`cte`). Mechanical supports are required: use
`{"type": "minimal"}` when the part is free to grow (distortion and internal stress
only), or the real fixings when restraint is the question.

## Rules

- Restraint decides thermal stress. A freely expanding uniform part has zero stress;
  a fully clamped one has E*alpha*dT. Never fix more than is really fixed.
- Steady temperatures must lie between the lowest and highest boundary temperatures
  unless there is a heat source. The checklist tests this.
- Heat balance: with only fixed-temperature and flux boundaries, heat in = heat out
  (checked automatically). With convection or radiation, check the heat flow against
  h*A*dT by hand.
- h values are the biggest uncertainty in most thermal models. Say where the value
  came from (natural convection in air 5-25, forced air 25-250, water 500-10 000 W/m^2/K)
  and run a low and a high case when it matters.
- Radiation makes the problem nonlinear and needs absolute temperatures; the toolkit
  sets absolute zero and the Stefan-Boltzmann constant in solver units for you.
- Properties are constant with temperature. Across a large range, use values at the
  mean temperature and say so.
- Latent heat (melting, crystallisation) is not modelled.
