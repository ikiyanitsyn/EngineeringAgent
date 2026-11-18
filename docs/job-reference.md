# Job reference (`job.json`)

A job is one JSON file in its own folder. `./ea fea new <folder> -a <type>` writes a
working example to edit. `//` comments and trailing commas are allowed.

Numbers are in the active unit system (`./ea units`) unless the job has `"units"` or
the value is a string with a unit (`"0.25 in"`, `"210 GPa"`, `"150 degF"`).

## Top level

| Key | Meaning |
| --- | --- |
| `name`, `title`, `description` | identification; the description goes into the report |
| `units` | `"metric"` or `"imperial"`; pins the system for this job |
| `analysis` | `static`, `nonlinear`, `modal`, `buckling`, `thermal_steady`, `thermal_transient`, `thermal_stress` |
| `geometry` | single part (see Geometry) |
| `material` | single part (see Materials) |
| `orientation` | material axes for orthotropic materials |
| `parts` | list of parts for an assembly: `{"name", "geometry", "material", "orientation"}` |
| `mesh` | meshing options |
| `sets` | named faces / points used by everything else |
| `constraints`, `loads`, `interactions` | boundary conditions |
| `initial_temperature` | start and stress-free temperature (default 20 degC) |
| `probes` | points or sets where results are read |
| `angles` | change of angle between two faces |
| `hand_calcs` | expected values compared with FEA results |
| `criteria` | acceptance limits |
| `modal`, `buckling`, `nonlinear`, `thermal`, `fatigue`, `stress_exclusion`, `convergence` | analysis options |
| `gdt`, `print` | tolerancing scheme and 3D-print settings for the report |
| `timeout` | solver time limit in seconds (default 3600) |

## Geometry

    "geometry": "part.step"
    "geometry": {"step": "part.step"}
    "geometry": {"script": "geometry.py", "params": {"length": 120}}     // build123d script, re-run when changed
    "geometry": {"template": "l_bracket", "params": {"thickness": 6}}     // ./ea cad templates
    "geometry": {"template": "beam", "params": {"length": 50}, "position": [50, 0, 0], "rotation": [0, 0, 90]}
                                       // assemblies: place a template part (rotation in degrees, applied first)

Scripts must end with `engagent.cad.save(part)`. STEP files are in mm.

## Materials

    "material": "al_6061_t6"                                   // library key: ./ea materials
    "material": {"E": "70 GPa", "nu": 0.33, "density": 2700, "yield": 276, "uts": 310}
    "material": {"base": "steel_s355", "yield": 420}           // library entry with overrides
    "material": {"base": "steel_s355", "plastic": [[355, 0], [470, 0.05]]}   // true stress, plastic strain
    "material": {"laminate": {"lamina": "cf_peek_ud", "layup": "[0/45/-45/90]2s", "ply_thickness": 0.14}}

Isotropic fields: `E`, `nu`, `density`, `yield`, `uts`, `elongation`, `endurance`,
`cte`, `k` (conductivity), `cp` (specific heat). Orthotropic: `E1 E2 E3 nu12 nu13 nu23
G12 G13 G23 cte1..3 k1..3`. Needed per analysis: mechanical -> `E`, `nu`; modal and
gravity -> `density`; thermal -> `k`; transient -> `cp`, `density`; thermal stress -> `cte`.
A missing property is an error, never a default.

Orientation (orthotropic only; default = global axes):

    "orientation": {"system": "rectangular", "a": [1, 0, 0], "b": [0, 1, 0]}      // a = material 1, b in the 1-2 plane
    "orientation": {"system": "cylindrical", "origin": [0, 0, 0], "axis": [0, 1, 0]}

Cylindrical: radial = material 3 (thickness), tangential = material 1, axial = material 2
(change with `"map": [3, 1, 2]`, the material axis used for radial, tangential, axial).

## Mesh

    "mesh": {"size": 3, "order": 2, "refine": [{"on": "hole", "size": 0.8, "distance": 4}],
             "min_size": 0.2, "curvature": 12, "max_nodes": 600000}

`size` target element size (default: half the thinner wall thicknesses measured on the part,
so walls get at least two elements, bounded to bounding-box diagonal / 150 ... / 25); `order` 2 = 10-node
tetrahedra (default), 1 = linear; `refine.on` a set name or selector; `distance` how far
the fine size extends; `curvature` elements per full circle on curved faces.

## Sets (face selectors)

    "sets": {
      "base": "zmin",                                      // "xmin" "xmax" "ymin" "ymax" "zmin" "zmax"
      "seat": {"plane": "z", "at": 12.5},
      "bore": {"cylinder": {"radius": 10}},                // or "diameter"; add "axis": "z", "near": [x, y, z]
      "top":  {"normal": [0, 0, 1]},
      "pad":  {"near": [40, 10, 5]},                       // the one face closest to the point
      "zone": {"box": [0, 0, 0, 20, 20, 5]},
      "f7":   {"faces": [7, 9]},                           // tags from ./ea cad faces
      "foot": {"part": "bracket", "plane": "z", "at": 0},  // assemblies: always name the part
      "all_holes": [{"cylinder": {"radius": 3.3}}, {"cylinder": {"radius": 4.5}}],     // union
      "side": {"plane": "x", "at": 0, "exclude": {"box": [0, 0, 0, 0, 5, 5]}},
      "pin":  {"point": [0, -5, -5]}                       // a single node (constraints and probes only)
    }

Keys inside one selector combine (intersection). A selector that matches nothing is an
error that tells you to run `./ea cad faces`.

## Constraints

    {"type": "fixed", "on": "base"}                        // all translations zero
    {"type": "displacement", "on": "end", "x": 0.5, "y": 0}        // listed components only; non-zero = prescribed
    {"type": "symmetry", "on": "cut", "normal": "x"}       // no motion normal to an axis-aligned plane
    {"type": "minimal"}                                    // 3-2-1: removes rigid-body motion only
    {"type": "temperature", "on": "hot", "value": 100}     // thermal analyses
    {"type": "temperature", "on": "platen", "schedule": [[0, 20], [600, 385]]}     // time s, temperature

## Loads

    {"type": "force", "on": "tip", "value": [0, 0, -500]}          // total force vector, spread over the face
    {"type": "pressure", "on": "top", "value": 0.2}                // positive pushes into the surface
    {"type": "moment", "on": "end", "value": [0, 12, 0]}           // moment vector about the face centroid
    {"type": "gravity", "g": [0, 0, -1]}                           // in g; needs density
    {"type": "centrifugal", "rpm": 3000, "point": [0, 0, 0], "axis": [0, 0, 1]}
    {"type": "temperature_change", "value": 150}                   // thermal_stress: uniform final temperature
    {"type": "heat_power", "on": "chip", "value": 15}
    {"type": "heat_flux", "on": "face", "value": 5000}
    {"type": "heat_generation", "value": 200000, "part": "coil"}
    {"type": "convection", "on": "fins", "h": 25, "ambient": 20}   // or "schedule": [[t, T_ambient], ...]
    {"type": "radiation", "on": "skin", "emissivity": 0.85, "ambient": 20}

## Interactions (assemblies)

    {"type": "tie", "master": "plate_top", "slave": "foot", "tolerance": 0.2}
    {"type": "contact", "master": "plate_top", "slave": "foot", "friction": 0.2, "stiffness": 2e6}

## Probes, angles

    "probes": {
      "tip":  {"set": "tip"},                              // average over a set
      "root": {"point": [10, 0, 5]},                       // local linear fit at a point
      "core": {"point": [3, 3, 2], "target": 380}          // transient: time to reach the target temperature
    },
    "angles": {"spring_in": {"between": ["start", "end"]}} // change of angle between two faces, degrees

## Result names (for `hand_calcs.metric`, `convergence.metrics`)

| Analysis | Names |
| --- | --- |
| static, nonlinear, thermal_stress | `max_displacement`, `max_ux|uy|uz`, `max_von_mises` (design zone), `peak_von_mises` (anywhere), `max_principal`, `min_principal`, `safety_factor_yield`, `reaction_total`, `reaction.<set>`, `applied_force`, `max_plastic_strain`, `angle.<name>` |
| modal | `frequency_1`, `frequency_2`, ... |
| buckling | `buckling_factor_1`, ... |
| thermal | `max_temperature`, `min_temperature`, `max_heat_flux`, `heat_flow.<set>` |
| probes | `probe.<name>.ux|uy|uz|displacement|sxx|syy|szz|sxy|syz|szx|von_mises|temperature|time_to_target|rate` |
| fatigue | `fatigue_sf_goodman`, `fatigue_life_cycles` |

## Hand calculations

    "hand_calcs": [
      {"name": "Tip deflection", "calc": "beam.cantilever_end_load",
       "inputs": {"P": 100, "L": 100, "E": "210 GPa", "b": 10, "h": 10, "nu": 0.3},
       "output": "deflection", "metric": "probe.tip.uz", "tol": 0.02},
      {"name": "Own estimate", "expected": "60 MPa", "kind": "pressure",
       "formula": "M c / I", "reference": "beam theory", "metric": "probe.root.sxx", "tol": 0.1}
    ]

`tol` is a fraction (default 0.05). Magnitudes are compared unless `"signed": true`.
Temperatures are compared relative to `"span"` (a temperature difference); give it.
An entry without `metric` is listed in the report for information only.
`kind` is the quantity kind: length, pressure, force, temperature, frequency, time,
angle, ratio, power, ...

## Criteria

    "criteria": {"yield_sf": 2.0, "max_displacement": 0.5, "max_stress": 150,
                 "min_frequency": 80, "min_buckling_factor": 3, "max_temperature": 120,
                 "max_plastic_strain": 0.02}

## Analysis options

    "modal": {"modes": 6}
    "buckling": {"modes": 4}
    "nonlinear": {"nlgeom": true, "plasticity": true, "initial_increment": 0.1,
                  "max_increment": 0.25, "min_increment": 1e-6, "max_increments": 2000}
    "thermal": {"duration": 600, "increments": 100, "frames": 25,
                "rate_window": [340, 200], "transient": true}
    "fatigue": {"R": 0, "surface": "machined", "loading": "bending", "reliability": 0.9,
                "size": 20, "Kf": 1.0, "required_sf": 1.5, "target_cycles": 1e6,
                "stress": "max_principal", "endurance": "95 MPa", "load_factor": 1.0}
    "stress_exclusion": {"distance": 5, "sets": ["base"]}      // or false to switch it off
    "convergence": {"ratio": 0.5, "tol": 0.05, "metrics": ["max_displacement", "probe.root.sxx"]}

`surface`: ground, machined, cold_drawn, hot_rolled, as_forged, polished.
`reliability`: 0.5, 0.9, 0.95, 0.99, 0.999, 0.9999. `thermal.transient` applies to
`thermal_stress` jobs. `stress_exclusion` defaults to 2 element sizes around supports
and interaction faces.

## Report blocks

    "print": {"process": "fdm", "material": "petg", "infill": 0.4, "orientation": "auto",
              "build_volume": [250, 210, 210]}
    "gdt": { ... }        // see docs/gdt.md

## Outputs in the job folder

| File | Content |
| --- | --- |
| `job.inp` | CalculiX input deck (solver units: mm, tonne, s, N, MPa, mJ, mW, degC) |
| `job.frd`, `job.dat`, `job.log` | raw solver output (not committed) |
| `results.json` | metrics, hand-calc comparison, checklist, verdict |
| `view.json` | surface fields for the viewer and plots |
| `report.html`, `report.pdf`, `plots/` | verification report |
| `viewer.html` | interactive colour plots and animation |
