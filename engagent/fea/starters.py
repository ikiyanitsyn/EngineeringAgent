"""Working starter jobs, one per analysis type, written in the active unit system.

Each starter is a small benchmark with a known hand-calculated answer, so a
new job starts from something that already passes its checks.
"""
from __future__ import annotations

from .. import units as U


def starter(analysis: str, system: str = "metric") -> dict:
    from .job import ANALYSES, ANALYSIS_ALIASES
    key = str(analysis).lower().replace("-", "_")
    key = {"contact": "contact", "assembly": "tie", "tie": "tie", "fatigue": "fatigue",
           "composite": "spring_in", "spring_in": "spring_in", "springin": "spring_in",
           "consolidation": "thermal_transient", "convection": "convection"}.get(key, ANALYSIS_ALIASES.get(key, key))
    system = U.normalize_system(system)

    def q(v: float, kind: str = "length"):
        """A metric default value expressed as a plain number in the active system."""
        if system == "metric":
            return v
        metric_unit = U.default_unit(kind, "metric")
        x = U.from_internal(U.to_internal(f"{v} {metric_unit}", kind), kind, "imperial")
        return float(f"{x:.5g}")

    L, b, h = q(100), q(10), q(10)
    beam = {"template": "beam", "params": {"length": L, "width": b, "height": h}}
    E, P = q(210000, "pressure"), q(100, "force")
    base = {"name": key, "units": system, "material": "steel_generic", "geometry": beam,
            "mesh": {"size": q(2.5)}}
    half = q(5)

    if key == "static":
        return {**base, "title": "Steel cantilever with an end load", "analysis": "static",
                "description": "Fixed at x = 0, transverse force on the free end face.",
                "sets": {"fixed": "xmin", "tip": "xmax"},
                "constraints": [{"type": "fixed", "on": "fixed"}],
                "loads": [{"type": "force", "on": "tip", "value": [0, 0, -P]}],
                "probes": {"tip": {"set": "tip"}, "top_x20": {"point": [q(20), 0, half]}},
                "hand_calcs": [
                    {"name": "Tip deflection", "calc": "beam.cantilever_end_load",
                     "inputs": {"P": P, "L": L, "E": E, "b": b, "h": h, "nu": 0.3},
                     "output": "deflection", "metric": "probe.tip.uz", "tol": 0.02},
                    {"name": "Bending stress at x = 20 mm", "calc": "beam.cantilever_end_load",
                     "inputs": {"P": P, "L": L, "E": E, "b": b, "h": h, "x": q(20)},
                     "output": "stress_at_x", "metric": "probe.top_x20.sxx", "tol": 0.10}],
                "criteria": {"yield_sf": 1.5}}
    if key == "fatigue":
        j = starter("static", system)
        j.update(name="fatigue", title="Cantilever under repeated load (fatigue screening)",
                 fatigue={"R": 0, "surface": "machined", "loading": "bending", "reliability": 0.9,
                          "required_sf": 1.5, "stress": "max_principal"})
        return j
    if key == "modal":
        return {**base, "title": "Cantilever natural frequencies", "analysis": "modal",
                "sets": {"fixed": "xmin"}, "constraints": [{"type": "fixed", "on": "fixed"}],
                "modal": {"modes": 6},
                "hand_calcs": [{"name": "First bending frequency", "calc": "beam.natural_frequency",
                                "inputs": {"L": L, "E": E, "b": b, "h": h, "density": q(7850, "density"),
                                           "support": "cantilever"},
                                "output": "f1", "metric": "frequency_1", "tol": 0.03}],
                "criteria": {"min_frequency": 100}}
    if key == "buckling":
        L2 = q(200)
        return {**base, "title": "Column buckling (fixed-free)", "analysis": "buckling",
                "geometry": {"template": "beam", "params": {"length": L2, "width": b, "height": h}},
                "mesh": {"size": q(3)},
                "sets": {"fixed": "xmin", "tip": "xmax"},
                "constraints": [{"type": "fixed", "on": "fixed"}],
                "loads": [{"type": "force", "on": "tip", "value": [-q(1000, "force"), 0, 0]}],
                "buckling": {"modes": 4},
                "hand_calcs": [{"name": "Euler critical load", "calc": "column.euler_buckling",
                                "inputs": {"L": L2, "E": E, "b": b, "h": h, "ends": "fixed_free",
                                           "yield_strength": q(250, "pressure")},
                                "output": "P_cr"},
                               {"name": "Buckling load factor = P_cr / P", "expected": 10.795, "kind": "ratio",
                                "formula": "pi^2 E I / (2 L)^2 / P", "metric": "buckling_factor_1", "tol": 0.03}],
                "criteria": {"min_buckling_factor": 3}}
    if key == "nonlinear":
        return {**base, "title": "Bar stretched beyond yield (plasticity)", "analysis": "nonlinear",
                "mesh": {"size": q(3)},
                "material": {"base": "steel_generic", "plastic": [[q(250, "pressure"), 0.0], [q(350, "pressure"), 0.05]]},
                "sets": {"x0": "xmin", "x1": "xmax", "p1": {"point": [0, -half, -half]},
                         "p2": {"point": [0, half, -half]}},
                "constraints": [{"type": "displacement", "on": "x0", "x": 0},
                                {"type": "displacement", "on": "x1", "x": q(1.0)},
                                {"type": "displacement", "on": "p1", "y": 0, "z": 0},
                                {"type": "displacement", "on": "p2", "z": 0}],
                "probes": {"mid": {"point": [q(50), 0, 0]}}, "stress_exclusion": False,
                "nonlinear": {"nlgeom": True, "plasticity": True},
                "hand_calcs": [{"name": "Stress on the hardening curve at 1 % stretch",
                                "expected": "267.6 MPa", "kind": "pressure",
                                "formula": "sigma = Sy + H (eps_log - sigma/E), H = (350-250)/0.05 MPa",
                                "metric": "probe.mid.sxx", "tol": 0.02}]}
    if key == "thermal_steady":
        return {**base, "title": "Steady conduction along a bar", "analysis": "thermal_steady",
                "sets": {"hot": "xmin", "cold": "xmax"},
                "constraints": [{"type": "temperature", "on": "hot", "value": q(100, "temperature")},
                                {"type": "temperature", "on": "cold", "value": q(20, "temperature")}],
                "probes": {"mid": {"point": [q(50), 0, 0]}},
                "hand_calcs": [
                    {"name": "Temperature at mid-length", "calc": "thermal.conduction_slab",
                     "inputs": {"k": q(50, "conductivity"), "A": q(100, "area"), "L": L,
                                "T_hot": q(100, "temperature"), "T_cold": q(20, "temperature"), "x": q(50)},
                     "output": "T_at_x", "metric": "probe.mid.temperature", "tol": 0.0125,
                     "span": q(80, "temp_delta")},
                    {"name": "Heat flow", "calc": "thermal.conduction_slab",
                     "inputs": {"k": q(50, "conductivity"), "A": q(100, "area"), "L": L,
                                "T_hot": q(100, "temperature"), "T_cold": q(20, "temperature")},
                     "output": "heat_flow", "metric": "heat_flow.hot", "tol": 0.01}]}
    if key == "convection":
        return {**base, "title": "Bar heated at one end, convection at the other", "analysis": "thermal_steady",
                "sets": {"hot": "xmin", "end": "xmax"},
                "constraints": [{"type": "temperature", "on": "hot", "value": q(100, "temperature")}],
                "loads": [{"type": "convection", "on": "end", "h": q(500, "film"),
                           "ambient": q(20, "temperature")}],
                "probes": {"end": {"set": "end"}},
                "hand_calcs": [{"name": "End-face temperature", "calc": "thermal.wall_conduction_convection",
                                "inputs": {"k": q(50, "conductivity"), "L": L, "h": q(500, "film"),
                                           "T_fixed": q(100, "temperature"), "T_ambient": q(20, "temperature")},
                                "output": "T_surface", "metric": "probe.end.temperature", "tol": 0.02,
                                "span": q(80, "temp_delta")}]}
    if key == "thermal_transient":
        t = q(4)
        return {"name": key, "units": system, "title": "Laminate heat-up between hot platens",
                "analysis": "thermal_transient", "material": "cf_peek_ud",
                "description": "Through-thickness heat-up of a CF/PEEK laminate in a matched-die press.",
                "geometry": {"template": "plate", "params": {"length": q(6), "width": q(6), "thickness": t}},
                "mesh": {"size": q(0.8)}, "initial_temperature": q(20, "temperature"),
                "sets": {"bottom": "zmin", "top": "zmax"},
                "constraints": [{"type": "temperature", "on": "bottom", "value": q(385, "temperature")},
                                {"type": "temperature", "on": "top", "value": q(385, "temperature")}],
                "thermal": {"duration": 30, "increments": 100, "frames": 20},
                "probes": {"centre": {"point": [q(3), q(3), q(2)], "target": q(380, "temperature")}},
                "hand_calcs": [{"name": "Time for the mid-plane to reach the target",
                                "calc": "composite.consolidation_heatup",
                                "inputs": {"material": "cf_peek_ud", "thickness": t,
                                           "T_initial": q(20, "temperature"), "T_tool": q(385, "temperature"),
                                           "T_target": q(380, "temperature")},
                                "output": "time_to_target", "metric": "probe.centre.time_to_target",
                                "tol": 0.06}]}
    if key == "thermal_stress":
        return {**base, "title": "Restrained bar heated uniformly", "analysis": "thermal_stress",
                "initial_temperature": q(20, "temperature"),
                "sets": {"x0": "xmin", "x1": "xmax", "p1": {"point": [0, -half, -half]},
                         "p2": {"point": [0, half, -half]}},
                "constraints": [{"type": "displacement", "on": "x0", "x": 0},
                                {"type": "displacement", "on": "x1", "x": 0},
                                {"type": "displacement", "on": "p1", "y": 0, "z": 0},
                                {"type": "displacement", "on": "p2", "z": 0}],
                "loads": [{"type": "temperature_change", "value": q(70, "temperature")}],
                "probes": {"mid": {"point": [q(50), 0, 0]}}, "stress_exclusion": False,
                "hand_calcs": [{"name": "Restrained thermal stress", "calc": "thermal.restrained_bar",
                                "inputs": {"E": E, "cte": q(12, "cte"), "dT": q(50, "temp_delta")},
                                "output": "stress", "metric": "probe.mid.sxx", "tol": 0.03, "signed": True}]}
    if key == "spring_in":
        return {"name": key, "units": system, "title": "Spring-in of a 90 degree CF/PEEK bend on cool-down",
                "analysis": "thermal_stress",
                "description": "Curved quasi-isotropic laminate cooled from its stress-free temperature "
                               "to room temperature; anisotropic shrinkage closes the angle.",
                "geometry": {"template": "curved_laminate",
                             "params": {"inner_radius": q(10), "thickness": q(2.24), "arc_deg": 90.0, "width": q(6)}},
                "material": {"laminate": {"lamina": "cf_peek_ud", "layup": "[0/45/-45/90]2s"}},
                "orientation": {"system": "cylindrical", "origin": [0, 0, 0], "axis": [0, 1, 0]},
                "mesh": {"size": q(0.7)}, "initial_temperature": q(310, "temperature"),
                "sets": {"start": "zmin", "end": "xmin"},
                "constraints": [{"type": "minimal"}],
                "loads": [{"type": "temperature_change", "value": q(20, "temperature")}],
                "angles": {"spring_in": {"between": ["start", "end"]}},
                "hand_calcs": [
                    {"name": "Laminate properties (CLT)", "calc": "composite.laminate",
                     "inputs": {"material": "cf_peek_ud", "layup": "[0/45/-45/90]2s", "dT": q(-290, "temp_delta")},
                     "output": "alpha_z"},
                    {"name": "Spring-in angle (Radford)", "calc": "composite.spring_in",
                     "inputs": {"angle": 90, "alpha_inplane": "2.701 um/m/K", "alpha_thickness": "38.58 um/m/K",
                                "dT": q(-290, "temp_delta")},
                     "output": "delta_angle", "metric": "angle.spring_in", "tol": 0.05}]}
    if key in ("tie", "contact"):
        Lh = q(50)
        job = {"name": key, "units": system, "analysis": "static",
               "title": "Steel and aluminium bars joined end to end (" + ("bonded" if key == "tie" else "contact") + ")",
               "parts": [
                   {"name": "steel", "material": "steel_generic",
                    "geometry": {"template": "beam", "params": {"length": Lh, "width": b, "height": h}, "step": "steel.step"}},
                   {"name": "alu", "material": "al_6061_t6", "geometry": {"script": "alu.py", "step": "alu.step"}}],
               "mesh": {"size": q(2.5)},
               "sets": {"fixed": {"part": "steel", "plane": "x", "at": 0},
                        "steel_end": {"part": "steel", "plane": "x", "at": Lh},
                        "alu_start": {"part": "alu", "plane": "x", "at": Lh},
                        "tip": {"part": "alu", "plane": "x", "at": q(100)}},
               "interactions": [{"type": "tie", "master": "steel_end", "slave": "alu_start"}],
               "constraints": [{"type": "fixed", "on": "fixed"}],
               "loads": [{"type": "force", "on": "tip", "value": [q(5000, "force"), 0, 0]}],
               "probes": {"tip": {"set": "tip"}},
               "hand_calcs": [{"name": "Series elongation P L1/(A E1) + P L2/(A E2)", "expected": "0.04819 mm",
                               "kind": "length", "formula": "delta = P L1 / (A E1) + P L2 / (A E2)",
                               "metric": "probe.tip.ux", "tol": 0.03}],
               "files_needed": {"alu.py": "from build123d import *\nfrom engagent.cad import save\n"
                                          "save(Pos(50, 0, 0) * Box(50, 10, 10, align=(Align.MIN, Align.CENTER, Align.CENTER)))\n"}}
        if key == "contact":
            job["interactions"] = [{"type": "contact", "master": "steel_end", "slave": "alu_start", "friction": 0.2}]
            job["loads"] = [{"type": "force", "on": "tip", "value": [-q(5000, "force"), 0, 0]}]
            job["sets"].update(p1={"point": [q(100), -half, -half]}, p2={"point": [q(100), half, -half]})
            job["constraints"] += [{"type": "displacement", "on": "p1", "y": 0, "z": 0},
                                   {"type": "displacement", "on": "p2", "z": 0}]
        return job
    raise ValueError(f"no starter for {analysis!r}; choose from {', '.join(ANALYSES)}, "
                     f"fatigue, tie, contact, convection, spring_in")


STARTERS = ("static", "fatigue", "modal", "buckling", "nonlinear", "thermal_steady", "convection",
            "thermal_transient", "thermal_stress", "spring_in", "tie", "contact")
