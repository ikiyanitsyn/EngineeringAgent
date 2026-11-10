"""Unit handling.

One rule keeps the whole tool consistent:

* Everything the solver and the internal Python code sees is in the
  **internal system**: mm, tonne, s, N, MPa, mJ, mW, degC.
* Everything a person types or reads is in the **active display system**:
  ``metric``   -> mm, kg, N, N*m, MPa, degC, W, ...
  ``imperial`` -> in, lbm, lbf, lbf*in, psi, degF, BTU/hr, ...

A bare number is read in the active system's default unit for that kind of
quantity.  A string such as ``"0.25 in"``, ``"30 lbf"`` or ``"210 GPa"`` is
always read in the unit it names, whatever system is active.
"""
from __future__ import annotations

import re
from typing import Iterable, Sequence, Union

Number = Union[int, float]
Value = Union[int, float, str]

SYSTEMS = ("metric", "imperial")
ALIASES = {"si": "metric", "mm": "metric", "sae": "imperial", "us": "imperial",
           "uscs": "imperial", "inch": "imperial", "english": "imperial",
           "metric": "metric", "imperial": "imperial"}

# unit -> (kind, factor, offset): internal = value * factor + offset
_U: dict[str, tuple[str, float, float]] = {}


def _add(kind: str, units: dict[str, float | tuple[float, float]]) -> None:
    for name, f in units.items():
        fac, off = f if isinstance(f, tuple) else (f, 0.0)
        _U[f"{kind}:{name.lower()}"] = (kind, float(fac), float(off))


IN = 25.4
LBF = 4.4482216152605
LBM_T = 0.45359237e-3           # lbm -> tonne
BTU_MJ = 1055.05585262e3        # BTU -> mJ
BTUH_MW = BTU_MJ / 3600.0       # BTU/hr -> mW
G0 = 9806.65                    # mm/s^2

_add("length", {"mm": 1, "cm": 10, "m": 1000, "um": 1e-3, "in": IN, "inch": IN,
                "ft": 12 * IN, "mil": IN / 1000, "thou": IN / 1000})
_add("area", {"mm2": 1, "mm^2": 1, "cm2": 100, "cm^2": 100, "m2": 1e6, "m^2": 1e6,
              "in2": IN**2, "in^2": IN**2, "ft2": (12 * IN)**2, "ft^2": (12 * IN)**2})
_add("volume", {"mm3": 1, "mm^3": 1, "cm3": 1e3, "cm^3": 1e3, "m3": 1e9, "m^3": 1e9,
                "l": 1e6, "in3": IN**3, "in^3": IN**3, "ft3": (12 * IN)**3})
_add("inertia", {"mm4": 1, "mm^4": 1, "cm4": 1e4, "cm^4": 1e4, "m4": 1e12,
                 "in4": IN**4, "in^4": IN**4})
_add("force", {"n": 1, "kn": 1e3, "mn": 1e-3, "lbf": LBF, "lb": LBF, "kip": 1e3 * LBF,
               "kgf": 9.80665, "ozf": LBF / 16})
_add("moment", {"n*mm": 1, "nmm": 1, "n*m": 1e3, "nm": 1e3, "kn*m": 1e6,
                "lbf*in": LBF * IN, "in*lbf": LBF * IN, "lb*in": LBF * IN,
                "lbf*ft": LBF * IN * 12, "ft*lbf": LBF * IN * 12, "lb*ft": LBF * IN * 12})
_PSI = LBF / IN**2
_add("pressure", {"mpa": 1, "gpa": 1e3, "kpa": 1e-3, "pa": 1e-6, "n/mm2": 1, "n/mm^2": 1,
                  "bar": 0.1, "psi": _PSI, "ksi": 1e3 * _PSI, "msi": 1e6 * _PSI,
                  "atm": 0.101325})
_add("mass", {"kg": 1e-3, "g": 1e-6, "tonne": 1, "t": 1, "lbm": LBM_T, "lb": LBM_T,
              "oz": LBM_T / 16, "slug": 14.5939029e-3})
_add("density", {"kg/m3": 1e-12, "kg/m^3": 1e-12, "g/cm3": 1e-9, "g/cm^3": 1e-9,
                 "g/cc": 1e-9, "tonne/mm3": 1, "t/mm3": 1, "lbm/in3": LBM_T / IN**3,
                 "lbm/in^3": LBM_T / IN**3, "lb/in3": LBM_T / IN**3,
                 "lb/in^3": LBM_T / IN**3, "lbm/ft3": LBM_T / (12 * IN)**3,
                 "lb/ft3": LBM_T / (12 * IN)**3})
_add("temperature", {"degc": 1, "c": 1, "°c": 1, "k": (1, -273.15),
                     "degf": (5 / 9, -32 * 5 / 9), "f": (5 / 9, -32 * 5 / 9),
                     "°f": (5 / 9, -32 * 5 / 9), "r": (5 / 9, -273.15)})
_add("temp_delta", {"k": 1, "degc": 1, "c": 1, "°c": 1, "degf": 5 / 9, "f": 5 / 9,
                    "°f": 5 / 9, "r": 5 / 9})
_add("cte", {"1/k": 1, "/k": 1, "1/degc": 1, "/degc": 1, "1/c": 1, "um/m/k": 1e-6,
             "ppm/k": 1e-6, "ppm/c": 1e-6, "1/degf": 9 / 5, "/degf": 9 / 5, "1/f": 9 / 5,
             "ppm/f": 9 / 5 * 1e-6, "uin/in/f": 9 / 5 * 1e-6})
_add("conductivity", {"w/m/k": 1, "w/(m*k)": 1, "w/mk": 1, "mw/mm/k": 1,
                      "btu/hr/ft/f": BTUH_MW / (12 * IN) / (5 / 9),
                      "btu/(hr*ft*f)": BTUH_MW / (12 * IN) / (5 / 9),
                      "btu*in/hr/ft2/f": BTUH_MW * IN / (12 * IN)**2 / (5 / 9)})
_add("specific_heat", {"j/kg/k": 1e6, "j/(kg*k)": 1e6, "kj/kg/k": 1e9, "j/g/k": 1e9,
                       "btu/lbm/f": BTU_MJ / LBM_T / (5 / 9),
                       "btu/lb/f": BTU_MJ / LBM_T / (5 / 9),
                       "btu/(lbm*f)": BTU_MJ / LBM_T / (5 / 9)})
_add("film", {"w/m2/k": 1e-3, "w/m^2/k": 1e-3, "w/(m2*k)": 1e-3, "mw/mm2/k": 1,
              "btu/hr/ft2/f": BTUH_MW / (12 * IN)**2 / (5 / 9),
              "btu/(hr*ft2*f)": BTUH_MW / (12 * IN)**2 / (5 / 9)})
_add("heat_flux", {"w/m2": 1e-3, "w/m^2": 1e-3, "kw/m2": 1, "w/mm2": 1e3, "w/cm2": 10,
                   "mw/mm2": 1, "btu/hr/ft2": BTUH_MW / (12 * IN)**2,
                   "w/in2": 1e3 / IN**2})
_add("heat_gen", {"w/m3": 1e-6, "w/m^3": 1e-6, "w/mm3": 1e3, "mw/mm3": 1,
                  "btu/hr/ft3": BTUH_MW / (12 * IN)**3, "w/in3": 1e3 / IN**3})
_add("power", {"w": 1e3, "kw": 1e6, "mw": 1, "btu/hr": BTUH_MW, "btu/h": BTUH_MW,
               "hp": 745.699872e3})
_add("energy", {"j": 1e3, "kj": 1e6, "mj": 1, "btu": BTU_MJ, "ft*lbf": LBF * IN * 12,
                "in*lbf": LBF * IN})
_add("time", {"s": 1, "ms": 1e-3, "min": 60, "h": 3600, "hr": 3600})
_add("frequency", {"hz": 1, "khz": 1e3, "rpm": 1 / 60, "cpm": 1 / 60})
_add("acceleration", {"mm/s2": 1, "mm/s^2": 1, "m/s2": 1e3, "m/s^2": 1e3, "g": G0,
                      "in/s2": IN, "in/s^2": IN, "ft/s2": 12 * IN, "ft/s^2": 12 * IN})
_add("angular_velocity", {"rad/s": 1, "rpm": 2 * 3.141592653589793 / 60,
                          "deg/s": 3.141592653589793 / 180})
_add("angle", {"deg": 1, "rad": 180 / 3.141592653589793})
_add("stiffness", {"n/mm": 1, "n/m": 1e-3, "kn/mm": 1e3, "lbf/in": LBF / IN})
_add("contact_stiffness", {"mpa/mm": 1, "n/mm3": 1, "psi/in": _PSI / IN})
_add("temp_rate", {"k/s": 1, "c/s": 1, "k/min": 1 / 60, "c/min": 1 / 60,
                   "f/s": 5 / 9, "f/min": 5 / 9 / 60})
_add("ratio", {"": 1, "-": 1, "%": 0.01})

#: default display unit per kind and system
DEFAULTS: dict[str, tuple[str, str]] = {
    "length": ("mm", "in"), "area": ("mm^2", "in^2"), "volume": ("cm^3", "in^3"),
    "inertia": ("mm^4", "in^4"), "force": ("N", "lbf"), "moment": ("N*m", "lbf*in"),
    "pressure": ("MPa", "psi"), "mass": ("kg", "lbm"), "density": ("kg/m^3", "lbm/in^3"),
    "temperature": ("degC", "degF"), "temp_delta": ("K", "degF"),
    "cte": ("um/m/K", "uin/in/F"), "conductivity": ("W/m/K", "BTU/hr/ft/F"),
    "specific_heat": ("J/kg/K", "BTU/lbm/F"), "film": ("W/m^2/K", "BTU/hr/ft2/F"),
    "heat_flux": ("W/m^2", "BTU/hr/ft2"), "heat_gen": ("W/m^3", "BTU/hr/ft3"),
    "power": ("W", "BTU/hr"), "energy": ("J", "ft*lbf"), "time": ("s", "s"),
    "frequency": ("Hz", "Hz"), "acceleration": ("g", "g"),
    "angular_velocity": ("rpm", "rpm"), "angle": ("deg", "deg"),
    "stiffness": ("N/mm", "lbf/in"), "contact_stiffness": ("MPa/mm", "psi/in"),
    "temp_rate": ("K/min", "F/min"), "ratio": ("", ""),
}
KINDS = tuple(DEFAULTS)

INTERNAL = {"length": "mm", "force": "N", "pressure": "MPa", "mass": "tonne",
            "density": "tonne/mm^3", "temperature": "degC", "power": "mW",
            "energy": "mJ", "conductivity": "mW/(mm*K)", "specific_heat": "mJ/(tonne*K)",
            "film": "mW/(mm^2*K)", "heat_flux": "mW/mm^2", "time": "s"}
INTERNAL_BANNER = "mm, tonne, s, N, MPa, mJ, mW, degC"

_NUM = re.compile(r"^\s*([-+]?(?:\d+\.?\d*|\.\d+)(?:[eE][-+]?\d+)?)\s*(.*?)\s*$")


def normalize_system(system: str | None) -> str:
    """Return ``'metric'`` or ``'imperial'``; ``None`` means the active system."""
    if system is None:
        from .config import get_units
        return get_units()
    key = str(system).strip().lower()
    if key not in ALIASES:
        raise ValueError(f"unknown unit system {system!r}; use 'metric' or 'imperial'")
    return ALIASES[key]


def default_unit(kind: str, system: str | None = None) -> str:
    if kind not in DEFAULTS:
        raise ValueError(f"unknown quantity kind {kind!r}; known: {', '.join(KINDS)}")
    return DEFAULTS[kind][SYSTEMS.index(normalize_system(system))]


def _lookup(kind: str, unit: str) -> tuple[float, float]:
    key = f"{kind}:{unit.strip().lower().replace(' ', '').replace('·', '*').replace('²', '2').replace('³', '3')}"
    if key not in _U:
        known = sorted(k.split(":", 1)[1] for k in _U if k.startswith(kind + ":"))
        raise ValueError(f"unit {unit!r} is not a {kind} unit; known: {', '.join(known)}")
    _, fac, off = _U[key]
    return fac, off


def convert(value: Number, kind: str, from_unit: str, to_unit: str) -> float:
    """Convert ``value`` between two named units of the same kind."""
    f1, o1 = _lookup(kind, from_unit)
    f2, o2 = _lookup(kind, to_unit)
    return (float(value) * f1 + o1 - o2) / f2


def parse(value: Value) -> tuple[float, str | None]:
    """Split ``"12.5 mm"`` into ``(12.5, "mm")``; a bare number gives unit ``None``."""
    if isinstance(value, bool):
        raise TypeError("a boolean is not a quantity")
    if isinstance(value, (int, float)):
        return float(value), None
    m = _NUM.match(str(value))
    if not m:
        raise ValueError(f"cannot read quantity {value!r}")
    return float(m.group(1)), (m.group(2) or None)


def to_internal(value: Value, kind: str, system: str | None = None) -> float:
    """Read a user value into the internal (mm, tonne, s, N, MPa, mJ, mW, degC) system."""
    num, unit = parse(value)
    fac, off = _lookup(kind, unit or default_unit(kind, system))
    return num * fac + off


def vec_to_internal(values: Iterable[Value], kind: str, system: str | None = None) -> list[float]:
    return [to_internal(v, kind, system) for v in values]


def from_internal(value: Number, kind: str, system: str | None = None,
                  unit: str | None = None) -> float:
    """Convert an internal value to the active display unit (or to ``unit``)."""
    fac, off = _lookup(kind, unit or default_unit(kind, system))
    return (float(value) - off) / fac


def fmt(value: Number | None, kind: str, system: str | None = None,
        unit: str | None = None, sig: int = 4) -> str:
    """Format an internal value for display, e.g. ``'0.1905 mm'``."""
    if value is None:
        return "n/a"
    u = unit or default_unit(kind, system)
    v = from_internal(value, kind, system, u)
    return f"{_sig(v, sig)} {u}".strip()


def fmt_vec(values: Sequence[Number], kind: str, system: str | None = None, sig: int = 4) -> str:
    u = default_unit(kind, system)
    fac, off = _lookup(kind, u)
    return "(" + ", ".join(_sig((float(v) - off) / fac, sig) for v in values) + f") {u}"


def _sig(v: float, sig: int = 4) -> str:
    if v == 0 or v != v:
        return "0" if v == 0 else "nan"
    a = abs(v)
    if a >= 10 ** (sig + 2) or a < 1e-4:
        return f"{v:.{sig - 1}e}"
    s = f"{v:.{sig}g}"
    if "e" in s:
        s = f"{v:.0f}"
    return s


def table(system: str | None = None) -> list[tuple[str, str, str]]:
    """Rows of (kind, display unit, internal unit) for the active system."""
    return [(k, default_unit(k, system), INTERNAL.get(k, "")) for k in KINDS]
