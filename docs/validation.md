# Validation

Every analysis type is checked against a closed-form answer. The cases below are the
starter jobs (`./ea fea new <folder> -a <type>`) and the files in `examples/`; they run
in CI on every push (`pytest -m solver`).

Measured with CalculiX 2.21, Gmsh 4.15, build123d 0.13, 10-node tetrahedra, default
mesh sizes, serial solver. Metric and imperial inputs give the same differences.

| Case | Analysis | Reference | FEA vs reference |
| --- | --- | --- | --- |
| Steel cantilever 100 x 10 x 10 mm, 100 N end load | static | tip deflection, Timoshenko beam (0.1920 mm) | 0.80 % |
| same | static | bending stress at x = 20 mm (48 MPa) | 0.02 % |
| same, uniform pressure on top | static | cantilever UDL deflection | 0.9 % |
| same, end moment 10 N*m | static | M L^2 / (2 E I) | 0.5 % |
| Tube 20 x 2 mm in torsion, 50 N*m | static | shear stress as von Mises | 0.2 % |
| Self-weight (100 g) | static | cantilever UDL deflection | 1.0 % |
| Rotating bar, 6000 rpm | static | rho w^2 (L^2 - x^2) / 2 | 0.8 % |
| Plate with a central hole, 10 kN | static, refined mesh | Peterson Kt x net stress (125.3 MPa) | 2.7 % |
| Cantilever | modal | first bending frequency (835.5 Hz) | 0.26 % |
| Fixed-free column 200 mm | buckling | Euler load factor (10.80) | 0.06 % |
| Bar stretched 1 % with bilinear hardening | nonlinear | stress on the hardening curve (267.6 MPa) | 0.08 % |
| Bar, 100 to 20 degC end to end | thermal steady | mid temperature 60 degC, heat flow 4 W | 0.00 %, 0.00 % |
| Bar with convection at the end | thermal steady | series thermal resistance | 0.00 % |
| Bar with 4 W into one end | thermal steady | end temperature 100 degC | 0.00 % |
| Fully restrained bar heated 50 K | thermal stress | -E alpha dT = -126 MPa | 0.00 % |
| Bar with a steady 100 K gradient, free | thermal stress (coupled) | free growth 0.060 mm | 0.5 % |
| 4 mm CF/PEEK laminate between 385 degC platens | thermal transient | time for the mid-plane to reach 380 degC, exact series (23.5 s) | 2.0 % (100 steps) |
| 90 degree CF/PEEK quasi-isotropic bend cooled 290 K | thermal stress, orthotropic, cylindrical axes | Radford spring-in (0.947 deg) | 0.00 % |
| Steel + aluminium bars, tied | assembly, tie | series elongation | 0.33 % |
| Steel + aluminium bars, pressed together | assembly, contact with friction | series shortening | 0.16 % |
| Aluminium angle bracket (`examples/20-*`) | static + fatigue + GD&T | cantilever bending stress in the upright | 2.2 %; converged to 1.3 % |

Mesh convergence on the cantilever (element size halved): displacement 0.08 %, design
stress 0.5 %, peak stress at the fixed face 17 % (a singularity, reported as such and
excluded from the design stress).

## Things found during validation that the toolkit now guards against

1. **Multithreaded CalculiX 2.21 is not reliable.** With 4 threads, 4 of 30 identical
   static runs returned wrong stresses or reactions (for example 4400 MPa instead of
   64 MPa) and buckling factors varied from run to run; 40 of 40 serial runs were
   correct and identical. The solver therefore runs with one thread by default
   (`"threads": 1` in `engagent.config.json`). The wrong runs did not always trip the
   equilibrium check, which is why the default is serial rather than "check and retry".
2. **Gmsh meshing with several threads is not reproducible**; meshing is single-threaded
   so the same job gives the same numbers every time (tested).
3. **Reactions on overlapping support sets were double-counted**; equilibrium is now
   totalled over the union of supported nodes.
4. **Distributed loads on elements touching a support**: the share of pressure or
   gravity load applied directly to supported nodes does not appear in the reactions
   (about 0.3 % here). The equilibrium check accounts for it and now closes to 1e-6 %.
5. **Reading the nearest node** for a stress comparison moved by several percent between
   meshes; probes use a local least-squares fit instead.
6. **Node ordering**: Gmsh and CalculiX order the last two mid-side nodes of a 10-node
   tetrahedron differently; the mesh is read through the Gmsh API and reordered, with a
   volume-sign check.
7. **Force on quadratic faces**: a uniform traction on 6-node triangles puts all of the
   load on the mid-side nodes (zero on corners); spreading it equally over all nodes is
   wrong.

## What has not been validated

- Windows: `scripts/setup.ps1` runs on a GitHub Windows runner on every push (CI job
  `windows`): it downloads CalculiX 2.23 for Windows, installs the packages and passes the
  cantilever benchmark (0.795 % against beam theory, the same as on Linux with 2.21), then
  runs `ea make` and `ea analyze`. The interactive menu (`START-HERE.cmd`) is checked for
  syntax only; its steps call the same commands.
- Plain-English requests depend on the model you connect; the toolkit validates what the
  model produces (selectors, hand checks, verdict), and retries with the error messages.
  GitHub Models returned no usable reply from this repository's runners when tested, so
  the documented free default for the issue bot is a Gemini key.
- Radiation is exercised (it runs and gives a plausible temperature) but has no
  closed-form comparison.
- Transient thermal stress runs but is compared only qualitatively.
- Contact is validated for a flat, fully closed interface; sliding and partial opening
  are not benchmarked.
- GD&T tables were transcribed from the standards and spot-checked, not exhaustively
  compared.
- Library material properties are typical handbook values.
