"""Job specification: read a user job (dict / JSON) into internal units.

See docs/job-reference.md for the full schema.  Every number in a job is in
the active unit system unless it carries its own unit string ("0.5 in").
"""
from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from .. import config, materials
from .. import units as U

ANALYSES = ("static", "nonlinear", "modal", "buckling", "thermal_steady",
            "thermal_transient", "thermal_stress")
ANALYSIS_ALIASES = {
    "linear_static": "static", "stress": "static", "mechanical": "static",
    "nonlinear_static": "nonlinear", "plastic": "nonlinear", "nlgeom": "nonlinear",
    "frequency": "modal", "modes": "modal", "natural_frequency": "modal",
    "buckle": "buckling", "linear_buckling": "buckling",
    "thermal": "thermal_steady", "steady_thermal": "thermal_steady",
    "heat_transfer": "thermal_steady", "conduction": "thermal_steady",
    "transient_thermal": "thermal_transient", "transient": "thermal_transient",
    "thermomechanical": "thermal_stress", "thermal_structural": "thermal_stress",
    "thermo_mechanical": "thermal_stress", "thermal_mechanical": "thermal_stress",
}
MECH = ("static", "nonlinear", "modal", "buckling", "thermal_stress")
THERMAL = ("thermal_steady", "thermal_transient", "thermal_stress")
THERMAL_LOADS = ("heat_flux", "heat_power", "convection", "radiation", "heat_generation")
MECH_LOADS = ("force", "pressure", "moment", "torque", "gravity", "centrifugal",
              "temperature_change")


@dataclass
class Part:
    name: str
    step: Path
    material: materials.Material
    orientation: dict | None = None


@dataclass
class Job:
    name: str
    folder: Path
    analysis: str
    system: str
    parts: list[Part]
    raw: dict
    sets: dict[str, Any] = field(default_factory=dict)
    mesh: dict = field(default_factory=dict)
    constraints: list[dict] = field(default_factory=list)
    loads: list[dict] = field(default_factory=list)
    interactions: list[dict] = field(default_factory=list)
    probes: dict[str, dict] = field(default_factory=dict)
    hand_calcs: list[dict] = field(default_factory=list)
    criteria: dict = field(default_factory=dict)
    initial_temperature: float = 20.0
    opts: dict = field(default_factory=dict)
    title: str = ""
    description: str = ""
    standard: str = "iso"

    @property
    def mechanical(self) -> bool:
        return self.analysis in MECH

    @property
    def thermal(self) -> bool:
        return self.analysis in THERMAL

    @property
    def coupled(self) -> bool:
        """Thermal-stress job that needs a heat-transfer solution (not just a uniform dT)."""
        if self.analysis != "thermal_stress":
            return False
        return any(c["type"] == "temperature" for c in self.constraints) or \
            any(l["type"] in THERMAL_LOADS for l in self.loads)

    @property
    def transient(self) -> bool:
        return self.analysis == "thermal_transient" or \
            (self.analysis == "thermal_stress" and bool(self.opts.get("transient")))

    def L(self, v) -> float:
        return U.to_internal(v, "length", self.system)

    def q(self, v, kind: str) -> float:
        return U.to_internal(v, kind, self.system)


def _resolve_geometry(spec: Any, folder: Path, name: str, rebuild: bool = False) -> Path:
    """Return a STEP path; run a build123d script first if one is given."""
    if isinstance(spec, (str, Path)):
        spec = {"script": str(spec)} if str(spec).endswith(".py") else {"step": str(spec)}
    if not isinstance(spec, dict):
        raise ValueError("geometry must be a STEP path, a script path, or a dict")
    if "script" in spec:
        script = (folder / spec["script"]).resolve()
        step = (folder / spec.get("step", f"{name}.step")).resolve()
        if rebuild or not step.exists() or step.stat().st_mtime < script.stat().st_mtime:
            from ..cad.build import run_script
            run_script(script, step, params=spec.get("params"))
        return step
    if "template" in spec:
        from ..cad import templates
        step = (folder / spec.get("step", f"{name}.step")).resolve()
        templates.build_to_step(spec["template"], spec.get("params", {}), step)
        return step
    if "step" in spec:
        return (folder / spec["step"]).resolve()
    raise ValueError("geometry needs 'step', 'script' or 'template'")


def load_job(spec: dict | str | Path, folder: str | Path | None = None,
             rebuild_geometry: bool = False) -> Job:
    """Read a job dict or job.json file and convert every quantity to internal units."""
    if isinstance(spec, (str, Path)):
        path = Path(spec)
        if path.is_dir():
            path = path / "job.json"
        folder = folder or path.parent
        spec = json.loads(path.read_text(encoding="utf-8"))
    raw = dict(spec)
    folder = Path(folder or ".").resolve()
    system = U.normalize_system(raw.get("units"))
    a = str(raw.get("analysis", "static")).lower().replace("-", "_").replace(" ", "_")
    a = ANALYSIS_ALIASES.get(a, a)
    if a not in ANALYSES:
        raise ValueError(f"unknown analysis {raw.get('analysis')!r}; choose from {', '.join(ANALYSES)}")
    name = str(raw.get("name") or folder.name)

    parts: list[Part] = []
    if "parts" in raw:
        for p in raw["parts"]:
            pname = str(p["name"])
            mat = materials.get(p.get("material", raw.get("material", "steel_generic")), system)
            parts.append(Part(pname, _resolve_geometry(p.get("geometry", p), folder, pname,
                                                       rebuild_geometry),
                              mat, p.get("orientation", raw.get("orientation"))))
    else:
        if "geometry" not in raw:
            raise ValueError("job needs 'geometry' (a STEP file or build123d script) or 'parts'")
        if "material" not in raw:
            raise ValueError("job needs a 'material' (library key or property dict); "
                             "materials are never assumed")
        parts.append(Part("part", _resolve_geometry(raw["geometry"], folder, "part",
                                                    rebuild_geometry),
                          materials.get(raw["material"], system), raw.get("orientation")))

    job = Job(name=name, folder=folder, analysis=a, system=system, parts=parts, raw=raw,
              sets=dict(raw.get("sets", {})), mesh=dict(raw.get("mesh", {})),
              constraints=[dict(c) for c in raw.get("constraints", [])],
              loads=[dict(l) for l in raw.get("loads", [])],
              interactions=[dict(i) for i in raw.get("interactions", [])],
              probes={k: dict(v) for k, v in raw.get("probes", {}).items()},
              hand_calcs=[dict(h) for h in raw.get("hand_calcs", [])],
              criteria=dict(raw.get("criteria", {})),
              title=raw.get("title", name), description=raw.get("description", ""),
              standard=str(raw.get("standard") or config.get_standard(system)).lower())
    job.initial_temperature = U.to_internal(
        raw.get("initial_temperature", raw.get("reference_temperature",
                                               "20 degC")), "temperature", system)
    for key in ("modal", "buckling", "nonlinear", "thermal", "fatigue", "stress_exclusion",
                "transient", "output", "angles"):
        if key in raw:
            job.opts[key] = raw[key]
    _validate(job)
    return job


def _validate(job: Job) -> None:
    names = set(job.sets)
    for c in job.constraints:
        t = c.get("type")
        if t not in ("fixed", "displacement", "symmetry", "minimal", "temperature", "pinned"):
            raise ValueError(f"unknown constraint type {t!r}")
        if t != "minimal" and c.get("on") not in names:
            raise ValueError(f"constraint {t!r} refers to set {c.get('on')!r}, "
                             f"which is not defined in 'sets' ({', '.join(sorted(names)) or 'none'})")
    for l in job.loads:
        t = l.get("type")
        if t not in MECH_LOADS + THERMAL_LOADS:
            raise ValueError(f"unknown load type {t!r}; known: {', '.join(MECH_LOADS + THERMAL_LOADS)}")
        if t in ("force", "pressure", "moment", "torque", "heat_flux", "heat_power",
                 "convection", "radiation") and l.get("on") not in names:
            raise ValueError(f"load {t!r} refers to set {l.get('on')!r}, which is not defined in 'sets'")
        if t in THERMAL_LOADS and not job.thermal:
            raise ValueError(f"load {t!r} needs a thermal analysis, not {job.analysis!r}")
        if t in MECH_LOADS and not job.mechanical:
            raise ValueError(f"load {t!r} needs a mechanical analysis, not {job.analysis!r}")
    for i in job.interactions:
        if i.get("type") not in ("tie", "contact"):
            raise ValueError(f"unknown interaction type {i.get('type')!r} (use 'tie' or 'contact')")
        for k in ("master", "slave"):
            if i.get(k) not in names:
                raise ValueError(f"interaction {k} set {i.get(k)!r} is not defined in 'sets'")
    if len(job.parts) > 1 and not job.interactions:
        raise ValueError("a multi-part job needs 'interactions' (tie or contact) between the parts")
    mech_bc = [c for c in job.constraints if c["type"] != "temperature"]
    if job.analysis in ("static", "nonlinear", "buckling", "thermal_stress") and not mech_bc:
        raise ValueError("a static analysis needs supports; add constraints "
                         "(or {'type': 'minimal'} to remove rigid-body motion only)")
    driven = any(c["type"] == "displacement" and any(
        ax in c and c[ax] is not None and job.L(c[ax]) != 0.0 for ax in "xyz") for c in job.constraints)
    if job.analysis in ("static", "nonlinear", "buckling") and not job.loads and not driven:
        raise ValueError("no loads defined; loads and boundary conditions are never assumed")
    for name, spec in job.raw.get("angles", {}).items():
        for sname in spec.get("between", []):
            if sname not in names:
                raise ValueError(f"angle {name!r} refers to set {sname!r}, which is not defined in 'sets'")
    for p in job.parts:
        m = p.material
        if job.mechanical:
            m.need(*(("E1", "E2", "E3", "nu12", "nu13", "nu23", "G12", "G13", "G23")
                     if m.orthotropic else ("E", "nu")))
        if job.thermal and (job.analysis != "thermal_stress" or job.coupled):
            m.need(*(("k1", "k2", "k3") if m.orthotropic else ("k",)))
        if job.transient:
            m.need("cp", "density")
        if job.analysis == "modal":
            m.need("density")
        if job.analysis == "thermal_stress":
            m.need(*(("cte1", "cte2", "cte3") if m.orthotropic else ("cte",)))
