---
name: fea-assembly
description: Finite element analysis of multi-part assemblies with bonded (tied) interfaces or contact with friction, including different materials per part and bolted-joint hand checks. Use when the model has more than one part - brackets bolted to plates, inserts, bonded or welded joints, a part on a tool or fixture, press-fits, clamped stacks.
---

# Assemblies: tie and contact

## Steps

1. One STEP per part, all in the same assembly coordinate system, mating faces
   coincident (zero gap, no overlap). Build each with `cad-modeling`.
2. Decide each interface:
   - **tie** - parts cannot separate or slide: adhesive, weld, fusion bond, co-consolidated
     joint, or a bolted joint that is known to stay clamped. Linear, fast, robust.
   - **contact** - parts can separate and slide: bearing faces, parts resting on tools,
     joints that may open. Nonlinear, slower. Only compression is carried.
3. Start from an example: `./ea fea new jobs/NN-name -a tie` (or `-a contact`).
4. Hand-check: load path stiffness in series/parallel (`axial.bar`), bolt loads
   (`bolt.joint_tension`, `bolt.shear_bearing`, `bolt.preload_torque`).
5. `./ea fea run jobs/NN-name --converge --report`, then `results-review`.

## Job layout

    "parts": [
      {"name": "bracket", "geometry": {"script": "bracket.py", "step": "bracket.step"}, "material": "al_6061_t6"},
      {"name": "plate",   "geometry": {"step": "plate.step"}, "material": "steel_s355"}
    ],
    "sets": {
      "bracket_foot": {"part": "bracket", "plane": "z", "at": 0},
      "plate_top":    {"part": "plate",   "plane": "z", "at": 0},
      "ground":       {"part": "plate",   "plane": "z", "at": -10},
      "load_face":    {"part": "bracket", "plane": "x", "at": 80}
    },
    "interactions": [
      {"type": "tie", "master": "plate_top", "slave": "bracket_foot"}
    ],
    "constraints": [{"type": "fixed", "on": "ground"}],
    "loads": [{"type": "force", "on": "load_face", "value": [0, 0, -800]}]

Always put `"part"` in a selector for an assembly; coincident faces from two parts would
otherwise both match.

Contact instead of tie:

    {"type": "contact", "master": "plate_top", "slave": "bracket_foot", "friction": 0.2}

Optional: `"stiffness": 2e6` (penalty stiffness per unit area; default 10 x the softer
modulus per mm) and, for tie, `"tolerance": 0.2` (search distance).

## Rules

- **Master / slave**: master = the stiffer part or the larger, coarser-meshed face;
  slave = the softer part or the smaller, finer face.
- **Rigid-body motion**: with contact only, every part must still be held in all
  directions, otherwise the solver reports a singular matrix or diverges. Options:
  fix or tie something on each part, add friction plus a small holding constraint, or
  constrain single nodes (`{"point": [...]}` sets with a `displacement` constraint) in
  the directions contact does not restrain.
- Contact needs load that closes the gap. A pulling load on a contact-only interface
  separates the parts (nothing is carried).
- Friction 0.1-0.2 steel on steel (dry), 0.2-0.4 aluminium, 0.05-0.1 lubricated,
  0.2-0.3 polymer on steel. Say what you assumed.
- Stress right at tie edges and contact edges is mesh-dependent; the toolkit excludes
  those zones from the design stress. Judge joint strength with the bolt / bond hand
  calculations and the interface force, not with the edge peak.
- **Bolts are not modelled with preload** in the FE model. Represent a clamped joint as
  a tie over the washer/clamp area (or the whole face if stiff), take the force through
  the joint from the reactions, and check the bolts by hand:

      ./ea calc bolt.preload_torque size=M8 grade=8.8
      ./ea calc bolt.joint_tension size=M8 grade=8.8 P=6000 n_bolts=4 C=0.25
      ./ea calc bolt.shear_bearing size=M8 grade=8.8 V=4000 t=6 plate_yield=276 edge=12 n_bolts=4

- Different materials expand differently: for temperature changes on an assembly use
  `thermal_stress` with a tie (bonded) or contact (free to slide) and expect high
  stresses at tied bi-material edges (real, but singular at the corner).
- Check that results make sense against one merged part: the tied assembly should be
  slightly softer than, or equal to, a monolithic model.
