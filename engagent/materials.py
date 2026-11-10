"""Material library and unit-aware material definitions.

Library values are *typical room-temperature* figures for preliminary design.
Always confirm against the supplier data sheet or the governing material
specification before a design decision; printed and composite parts in
particular vary strongly with process and orientation.

Field kinds (how a bare number is read in the active unit system):
    E, E1..E3, G12.., yield, uts, endurance  -> pressure
    density                                  -> density
    cte, cte1..3                             -> cte
    k, k1..3                                 -> conductivity
    cp                                       -> specific_heat
    Tg, Tm, T_process, T_max_service         -> temperature
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from . import units as U

FIELD_KIND = {
    "E": "pressure", "E1": "pressure", "E2": "pressure", "E3": "pressure",
    "G12": "pressure", "G13": "pressure", "G23": "pressure",
    "yield": "pressure", "uts": "pressure", "endurance": "pressure",
    "yield_c": "pressure", "Xt": "pressure", "Xc": "pressure", "Yt": "pressure",
    "Yc": "pressure", "S12": "pressure",
    "density": "density", "cte": "cte", "cte1": "cte", "cte2": "cte", "cte3": "cte",
    "k": "conductivity", "k1": "conductivity", "k2": "conductivity", "k3": "conductivity",
    "cp": "specific_heat", "Tg": "temperature", "Tm": "temperature",
    "T_process": "temperature", "T_max_service": "temperature", "T_stress_free": "temperature",
}
DIMENSIONLESS = ("nu", "nu12", "nu13", "nu23", "elongation", "emissivity")

# Library in metric display units: MPa, kg/m^3, um/m/K, W/m/K, J/kg/K, degC.
_M = dict
LIBRARY: dict[str, dict[str, Any]] = {
    # ---- steels -----------------------------------------------------------
    "steel_generic": _M(name="Structural steel (generic)", family="steel", E=210000, nu=0.30,
                        density=7850, cte=12.0, k=50, cp=480, **{"yield": 250}, uts=400,
                        elongation=0.20, endurance=200, spec="generic, guide default"),
    "steel_s235": _M(name="S235JR structural steel", family="steel", E=210000, nu=0.30,
                     density=7850, cte=12.0, k=50, cp=480, **{"yield": 235}, uts=360,
                     elongation=0.26, endurance=180, spec="EN 10025-2"),
    "steel_s355": _M(name="S355J2 structural steel", family="steel", E=210000, nu=0.30,
                     density=7850, cte=12.0, k=45, cp=480, **{"yield": 355}, uts=510,
                     elongation=0.22, endurance=255, spec="EN 10025-2"),
    "steel_a36": _M(name="ASTM A36 structural steel", family="steel", E=200000, nu=0.26,
                    density=7850, cte=11.7, k=50, cp=480, **{"yield": 250}, uts=400,
                    elongation=0.20, endurance=200, spec="ASTM A36"),
    "steel_1045": _M(name="AISI 1045 medium-carbon steel (normalized)", family="steel",
                     E=205000, nu=0.29, density=7850, cte=11.5, k=50, cp=486,
                     **{"yield": 410}, uts=630, elongation=0.16, endurance=315, spec="AISI 1045"),
    "steel_4140_qt": _M(name="AISI 4140 Q&T (approx. 28-32 HRC)", family="steel", E=205000,
                        nu=0.29, density=7850, cte=12.2, k=42, cp=473, **{"yield": 655},
                        uts=850, elongation=0.17, endurance=425, spec="AISI 4140"),
    "stainless_304": _M(name="AISI 304 stainless steel (annealed)", family="stainless",
                        E=193000, nu=0.29, density=8000, cte=17.3, k=16.2, cp=500,
                        **{"yield": 215}, uts=505, elongation=0.40, endurance=240,
                        spec="ASTM A240 304"),
    "stainless_316l": _M(name="AISI 316L stainless steel (annealed)", family="stainless",
                         E=193000, nu=0.30, density=8000, cte=16.0, k=16.3, cp=500,
                         **{"yield": 170}, uts=485, elongation=0.40, endurance=230,
                         spec="ASTM A240 316L"),
    "tool_steel_p20": _M(name="P20 mould tool steel (pre-hardened)", family="tooling",
                         E=205000, nu=0.29, density=7850, cte=12.8, k=29, cp=460,
                         **{"yield": 830}, uts=1000, elongation=0.12, spec="AISI P20"),
    "invar_36": _M(name="Invar 36 (composite tooling alloy)", family="tooling", E=141000,
                   nu=0.29, density=8050, cte=1.3, k=10.5, cp=515, **{"yield": 276}, uts=448,
                   elongation=0.35, spec="ASTM F1684"),
    # ---- aluminium / titanium / others -----------------------------------
    "al_6061_t6": _M(name="Aluminium 6061-T6", family="aluminium", E=68900, nu=0.33,
                     density=2700, cte=23.6, k=167, cp=896, **{"yield": 276}, uts=310,
                     elongation=0.12, endurance=96.5, spec="ASTM B209 6061-T6"),
    "al_7075_t6": _M(name="Aluminium 7075-T6", family="aluminium", E=71700, nu=0.33,
                     density=2810, cte=23.6, k=130, cp=960, **{"yield": 503}, uts=572,
                     elongation=0.11, endurance=159, spec="ASTM B209 7075-T6"),
    "al_5052_h32": _M(name="Aluminium 5052-H32 sheet", family="aluminium", E=70300, nu=0.33,
                      density=2680, cte=23.8, k=138, cp=880, **{"yield": 193}, uts=228,
                      elongation=0.12, endurance=117, spec="ASTM B209 5052-H32"),
    "al_mic6": _M(name="Cast aluminium tooling plate (MIC-6 type)", family="tooling", E=71000,
                  nu=0.33, density=2800, cte=23.6, k=142, cp=880, **{"yield": 105}, uts=166,
                  elongation=0.03, spec="cast tooling plate"),
    "ti_6al4v": _M(name="Titanium Ti-6Al-4V (annealed)", family="titanium", E=113800, nu=0.342,
                   density=4430, cte=8.6, k=6.7, cp=526, **{"yield": 880}, uts=950,
                   elongation=0.14, endurance=510, spec="ASTM B265 Gr.5"),
    "brass_c360": _M(name="Free-cutting brass C360", family="copper", E=97000, nu=0.31,
                     density=8500, cte=20.5, k=115, cp=380, **{"yield": 124}, uts=338,
                     elongation=0.53, spec="ASTM B16 C36000"),
    "copper_c110": _M(name="Copper C110 (ETP)", family="copper", E=115000, nu=0.33,
                      density=8910, cte=17.0, k=388, cp=385, **{"yield": 69}, uts=220,
                      elongation=0.50, spec="ASTM B152 C11000"),
    # ---- 3D-printing polymers (typical FDM/SLS, in-plane) ------------------
    "pla": _M(name="PLA (FDM printed, XY)", family="print_polymer", E=3300, nu=0.36,
              density=1240, cte=68, k=0.13, cp=1800, **{"yield": 50}, uts=55, elongation=0.04,
              Tg=60, T_max_service=50, process="FDM",
              note="Z (layer) strength is typically 40-60 % of XY."),
    "petg": _M(name="PETG (FDM printed, XY)", family="print_polymer", E=2050, nu=0.38,
               density=1270, cte=68, k=0.21, cp=1300, **{"yield": 45}, uts=50, elongation=0.10,
               Tg=80, T_max_service=70, process="FDM",
               note="Z (layer) strength is typically 50-70 % of XY."),
    "abs": _M(name="ABS (FDM printed, XY)", family="print_polymer", E=2200, nu=0.35,
              density=1040, cte=90, k=0.17, cp=1400, **{"yield": 38}, uts=40, elongation=0.06,
              Tg=105, T_max_service=85, process="FDM",
              note="Z (layer) strength is typically 50-70 % of XY."),
    "asa": _M(name="ASA (FDM printed, XY)", family="print_polymer", E=2100, nu=0.35,
              density=1070, cte=95, k=0.18, cp=1300, **{"yield": 40}, uts=45, elongation=0.06,
              Tg=100, T_max_service=85, process="FDM"),
    "pa12_sls": _M(name="PA12 nylon (SLS / MJF)", family="print_polymer", E=1700, nu=0.39,
                   density=1010, cte=100, k=0.25, cp=1700, **{"yield": 45}, uts=48,
                   elongation=0.15, Tg=50, Tm=178, T_max_service=95, process="SLS"),
    "pa6_cf_fdm": _M(name="PA6-CF short carbon fibre nylon (FDM, XY)", family="print_polymer",
                     E=7500, nu=0.35, density=1170, cte=25, k=0.5, cp=1500, **{"yield": 90},
                     uts=105, elongation=0.02, Tg=70, T_max_service=120, process="FDM",
                     note="Strongly anisotropic; Z properties far lower."),
    "pc": _M(name="Polycarbonate (FDM printed, XY)", family="print_polymer", E=2300, nu=0.37,
             density=1200, cte=68, k=0.20, cp=1250, **{"yield": 58}, uts=62, elongation=0.06,
             Tg=147, T_max_service=115, process="FDM"),
    "resin_tough_sla": _M(name="Tough engineering resin (SLA, post-cured)",
                          family="print_polymer", E=2700, nu=0.38, density=1180, cte=90, k=0.2,
                          cp=1500, **{"yield": 50}, uts=55, elongation=0.20, Tg=60,
                          T_max_service=45, process="SLA"),
    # ---- neat high-performance thermoplastics -----------------------------
    "peek": _M(name="PEEK, unfilled (semi-crystalline)", family="thermoplastic", E=3900,
               nu=0.40, density=1300, cte=47, k=0.29, cp=1340, **{"yield": 98}, uts=98,
               elongation=0.25, Tg=143, Tm=343, T_process=385, T_max_service=250),
    "pekk": _M(name="PEKK, unfilled (60/40, semi-crystalline)", family="thermoplastic",
               E=3800, nu=0.40, density=1290, cte=40, k=0.25, cp=1300, **{"yield": 102},
               uts=102, elongation=0.12, Tg=160, Tm=305, T_process=375, T_max_service=240),
    "lmpaek": _M(name="LM-PAEK, unfilled", family="thermoplastic", E=3700, nu=0.40,
                 density=1300, cte=45, k=0.26, cp=1320, **{"yield": 95}, uts=95,
                 elongation=0.20, Tg=147, Tm=305, T_process=365, T_max_service=240),
    "pps": _M(name="PPS, unfilled", family="thermoplastic", E=3800, nu=0.38, density=1350,
              cte=50, k=0.30, cp=1000, **{"yield": 85}, uts=85, elongation=0.03, Tg=90,
              Tm=280, T_process=320, T_max_service=200),
    "pei": _M(name="PEI (Ultem 1000 type), amorphous", family="thermoplastic", E=3200,
              nu=0.36, density=1270, cte=55, k=0.22, cp=1250, **{"yield": 105}, uts=105,
              elongation=0.60, Tg=217, T_process=340, T_max_service=170),
    "pp": _M(name="Polypropylene homopolymer", family="thermoplastic", E=1500, nu=0.42,
             density=905, cte=110, k=0.20, cp=1900, **{"yield": 33}, uts=35, elongation=1.0,
             Tg=-10, Tm=165, T_process=220, T_max_service=90),
    # ---- thermoplastic composite laminae (unidirectional tape, ~60 % Vf) ----
    # 1 = fibre, 2 = transverse in-plane, 3 = through thickness.
    "cf_peek_ud": _M(name="CF/PEEK UD tape (AS4/APC-2 type)", family="tp_composite",
                     orthotropic=True, E1=138000, E2=10300, E3=10300, nu12=0.30, nu13=0.30,
                     nu23=0.45, G12=5700, G13=5700, G23=3700, density=1600, cte1=0.3,
                     cte2=28.0, cte3=28.0, k1=5.0, k2=0.55, k3=0.55, cp=1100, Xt=2070,
                     Xc=1360, Yt=86, Yc=176, S12=186, Tg=143, Tm=343, T_process=385,
                     T_stress_free=310, ply_thickness_mm=0.14,
                     note="T_stress_free ~ peak crystallisation temperature."),
    "cf_pekk_ud": _M(name="CF/PEKK UD tape (AS4D/PEKK type)", family="tp_composite",
                     orthotropic=True, E1=135000, E2=10000, E3=10000, nu12=0.31, nu13=0.31,
                     nu23=0.45, G12=5200, G13=5200, G23=3500, density=1590, cte1=0.3,
                     cte2=29.0, cte3=29.0, k1=5.0, k2=0.55, k3=0.55, cp=1100, Xt=2300,
                     Xc=1300, Yt=80, Yc=200, S12=150, Tg=160, Tm=337, T_process=375,
                     T_stress_free=280, ply_thickness_mm=0.14),
    "cf_lmpaek_ud": _M(name="CF/LM-PAEK UD tape (TC1225 type)", family="tp_composite",
                       orthotropic=True, E1=135000, E2=10000, E3=10000, nu12=0.30, nu13=0.30,
                       nu23=0.45, G12=4300, G13=4300, G23=3500, density=1590, cte1=0.3,
                       cte2=29.0, cte3=29.0, k1=5.0, k2=0.55, k3=0.55, cp=1100, Xt=2400,
                       Xc=1300, Yt=85, Yc=200, S12=150, Tg=147, Tm=305, T_process=365,
                       T_stress_free=260, ply_thickness_mm=0.14),
    "cf_pps_fabric": _M(name="CF/PPS 5HS woven fabric ply", family="tp_composite",
                        orthotropic=True, E1=56000, E2=54000, E3=9000, nu12=0.05, nu13=0.35,
                        nu23=0.35, G12=4000, G13=3000, G23=3000, density=1550, cte1=2.5,
                        cte2=2.8, cte3=45.0, k1=2.5, k2=2.5, k3=0.45, cp=1000, Xt=750,
                        Xc=640, Yt=750, Yc=640, S12=120, Tg=90, Tm=280, T_process=320,
                        T_stress_free=230, ply_thickness_mm=0.31),
    "gf_pp_ud": _M(name="GF/PP UD tape (~45 % Vf)", family="tp_composite", orthotropic=True,
                   E1=34000, E2=4000, E3=4000, nu12=0.30, nu13=0.30, nu23=0.45, G12=1500,
                   G13=1500, G23=1300, density=1650, cte1=7.0, cte2=60.0, cte3=60.0, k1=0.6,
                   k2=0.35, k3=0.35, cp=1200, Xt=800, Xc=350, Yt=15, Yc=70, S12=30, Tg=-10,
                   Tm=165, T_process=220, T_stress_free=120, ply_thickness_mm=0.25),
}


@dataclass
class Material:
    """A material in internal units (mm, tonne, s, N, MPa, mJ, mW, degC)."""
    key: str
    name: str
    props: dict[str, float] = field(default_factory=dict)   # internal units
    orthotropic: bool = False
    family: str = "custom"
    meta: dict[str, Any] = field(default_factory=dict)
    plastic: list[tuple[float, float]] | None = None         # (true stress MPa, plastic strain)

    def get(self, name: str, default: float | None = None) -> float | None:
        return self.props.get(name, default)

    def need(self, *names: str) -> None:
        missing = [n for n in names if self.props.get(n) is None]
        if missing:
            raise ValueError(f"material {self.key!r} lacks {', '.join(missing)} "
                             f"needed for this analysis; add them to the material definition")

    def display(self, system: str | None = None) -> dict[str, str]:
        out = {}
        for k, v in self.props.items():
            if k in FIELD_KIND:
                unit = None
                if FIELD_KIND[k] == "pressure" and k.startswith(("E", "G")) and \
                        U.normalize_system(system) == "metric":
                    unit = "GPa"
                out[k] = U.fmt(v, FIELD_KIND[k], system, unit)
            else:
                out[k] = f"{v:g}"
        return out

    def bilinear_plastic(self) -> list[tuple[float, float]]:
        """True stress / plastic strain table from yield, UTS and elongation."""
        if self.plastic:
            return self.plastic
        self.need("E", "yield")
        sy = self.props["yield"]
        su = self.props.get("uts") or sy * 1.1
        el = self.props.get("elongation") or 0.10
        eu = max(el * 0.8, 0.01)                    # uniform strain estimate
        true_u = su * (1 + eu)
        import math
        ep_u = max(math.log(1 + eu) - true_u / self.props["E"], 1e-4)
        return [(sy, 0.0), (max(true_u, sy * 1.0001), ep_u)]

    def to_dict(self, system: str | None = None) -> dict:
        return {"key": self.key, "name": self.name, "family": self.family,
                "orthotropic": self.orthotropic, "properties": self.display(system),
                "meta": self.meta}


def _build(key: str, raw: dict[str, Any], system: str | None) -> Material:
    props: dict[str, float] = {}
    meta: dict[str, Any] = {}
    plastic = None
    for k, v in raw.items():
        if k in ("name", "family", "orthotropic", "key", "base"):
            continue
        if k == "plastic":
            plastic = [(U.to_internal(s, "pressure", system), float(e)) for s, e in v]
        elif k in FIELD_KIND:
            props[k] = U.to_internal(v, FIELD_KIND[k], system)
        elif k in DIMENSIONLESS:
            props[k] = float(v)
        else:
            meta[k] = v
    ortho = bool(raw.get("orthotropic", "E1" in props))
    return Material(key=key, name=raw.get("name", key), props=props, orthotropic=ortho,
                    family=raw.get("family", "custom"), meta=meta, plastic=plastic)


def get(spec: str | dict | Material, system: str | None = None) -> Material:
    """Resolve a material.

    ``spec`` is a library key (``"al_6061_t6"``), or a dict of properties in
    the active unit system.  A dict may carry ``"base": "<library key>"`` to
    start from a library entry and override individual values.
    """
    if isinstance(spec, Material):
        return spec
    if isinstance(spec, str):
        key = spec.strip().lower()
        if key not in LIBRARY:
            import difflib
            hint = difflib.get_close_matches(key, LIBRARY, n=3)
            raise KeyError(f"unknown material {spec!r}" +
                           (f"; did you mean {', '.join(hint)}?" if hint else "") +
                           " (see `engagent materials`)")
        return _build(key, LIBRARY[key], "metric")
    if isinstance(spec, dict) and "laminate" in spec:
        from .handcalc.composites import smeared_material
        lam = spec["laminate"]
        t = lam.get("ply_thickness")
        return smeared_material(lam["lamina"], lam["layup"],
                                U.to_internal(t, "length", system) if t is not None else None,
                                bool(lam.get("symmetric", False)))
    if isinstance(spec, dict):
        key = str(spec.get("key") or spec.get("name") or "custom").lower().replace(" ", "_")
        if spec.get("base"):
            base = get(spec["base"])
            over = _build(key, {k: v for k, v in spec.items() if k != "base"}, system)
            base.props.update(over.props)
            base.meta.update(over.meta)
            base.key = key if (spec.get("key") or spec.get("name")) else base.key
            base.name = spec.get("name", base.name + " (modified)")
            base.plastic = over.plastic or base.plastic
            return base
        return _build(key, spec, system)
    raise TypeError(f"cannot read a material from {type(spec).__name__}")


def list_materials(family: str | None = None) -> list[Material]:
    mats = [get(k) for k in LIBRARY]
    return [m for m in mats if family is None or m.family == family]
