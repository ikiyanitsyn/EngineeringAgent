"""ISO 286 limits and fits (hole-basis system), also valid for ASME B4.2 metric fits.

Tables cover nominal sizes up to 500 mm, tolerance grades IT5 to IT14, holes
H, G, F, E, D, JS and shafts d, e, f, g, h, js, k, n, p, s.  Values in
micrometres, transcribed from ISO 286-1/-2.
"""
from __future__ import annotations

import re

from .. import units as U

# upper bound (mm, inclusive) of each nominal size range; first range is "over 0 up to 3"
RANGES = [3, 6, 10, 18, 30, 50, 80, 120, 180, 250, 315, 400, 500]
IT = {
    5: [4, 5, 6, 8, 9, 11, 13, 15, 18, 20, 23, 25, 27],
    6: [6, 8, 9, 11, 13, 16, 19, 22, 25, 29, 32, 36, 40],
    7: [10, 12, 15, 18, 21, 25, 30, 35, 40, 46, 52, 57, 63],
    8: [14, 18, 22, 27, 33, 39, 46, 54, 63, 72, 81, 89, 97],
    9: [25, 30, 36, 43, 52, 62, 74, 87, 100, 115, 130, 140, 155],
    10: [40, 48, 58, 70, 84, 100, 120, 140, 160, 185, 210, 230, 250],
    11: [60, 75, 90, 110, 130, 160, 190, 220, 250, 290, 320, 360, 400],
    12: [100, 120, 150, 180, 210, 250, 300, 350, 400, 460, 520, 570, 630],
    13: [140, 180, 220, 270, 330, 390, 460, 540, 630, 720, 810, 890, 970],
    14: [250, 300, 360, 430, 520, 620, 740, 870, 1000, 1150, 1300, 1400, 1550],
}
# shaft fundamental deviations (micrometres).  Negative letters give the UPPER deviation (es),
# positive letters the LOWER deviation (ei).
SHAFT_UPPER = {
    "d": [-20, -30, -40, -50, -65, -80, -100, -120, -145, -170, -190, -210, -230],
    "e": [-14, -20, -25, -32, -40, -50, -60, -72, -85, -100, -110, -125, -135],
    "f": [-6, -10, -13, -16, -20, -25, -30, -36, -43, -50, -56, -62, -68],
    "g": [-2, -4, -5, -6, -7, -9, -10, -12, -14, -15, -17, -18, -20],
    "h": [0] * 13,
}
SHAFT_LOWER = {
    "k": [0, 1, 1, 1, 2, 2, 2, 3, 3, 4, 4, 4, 5],          # grades IT4 to IT7
    "n": [4, 8, 10, 12, 15, 17, 20, 23, 27, 31, 34, 37, 40],
    "p": [6, 12, 15, 18, 22, 26, 32, 37, 43, 50, 56, 62, 68],
}
# 's' varies inside the main ranges above 50 mm: (upper bound mm, ei um)
SHAFT_S = [(3, 14), (6, 19), (10, 23), (18, 28), (30, 35), (50, 43), (65, 53), (80, 59),
           (100, 71), (120, 79), (140, 92), (160, 100), (180, 108), (200, 122), (225, 130),
           (250, 140), (280, 158), (315, 170), (355, 190), (400, 208), (450, 232), (500, 252)]

PREFERRED = {
    "H11/c11": "loose running", "H9/d9": "free running", "H8/f7": "close running",
    "H7/g6": "sliding", "H7/h6": "locational clearance", "H7/k6": "locational transition",
    "H7/n6": "locational transition (tighter)", "H7/p6": "locational interference",
    "H7/s6": "medium drive (press fit)",
}


def _range(nominal: float) -> int:
    if nominal <= 0 or nominal > 500:
        raise ValueError(f"nominal size {nominal:g} mm is outside the ISO 286 table range (0-500 mm)")
    for i, hi in enumerate(RANGES):
        if nominal <= hi:
            return i
    return len(RANGES) - 1


def _it(grade: int, i: int) -> float:
    if grade not in IT:
        raise ValueError(f"tolerance grade IT{grade} is not tabulated (IT5 to IT14)")
    return IT[grade][i] / 1000.0


def _parse(sym: str) -> tuple[str, int]:
    m = re.fullmatch(r"\s*([A-Za-z]{1,2})\s*(\d{1,2})\s*", sym)
    if not m:
        raise ValueError(f"cannot read tolerance class {sym!r} (expected e.g. H7, g6, js9)")
    return m.group(1), int(m.group(2))


def limits(nominal: float, tol_class: str) -> tuple[float, float]:
    """(lower deviation, upper deviation) in mm for a tolerance class such as 'H7' or 'g6'."""
    letter, grade = _parse(tol_class)
    i = _range(nominal)
    it = _it(grade, i)
    is_hole = letter[0].isupper()
    L = letter.lower()
    if L == "js":
        return -it / 2, it / 2
    if is_hole:
        if L == "h":
            return 0.0, it
        if L in SHAFT_UPPER:                       # holes D..G mirror shafts d..g: EI = -es
            ei = -SHAFT_UPPER[L][i] / 1000.0
            return ei, ei + it
        raise ValueError(f"hole class {letter}{grade} is not tabulated; supported holes: "
                         f"H, G, F, E, D, JS (hole-basis system)")
    if L in SHAFT_UPPER:
        es = SHAFT_UPPER[L][i] / 1000.0
        return es - it, es
    if L in SHAFT_LOWER:
        if L == "k" and not 4 <= grade <= 7:
            ei = 0.0
        else:
            ei = SHAFT_LOWER[L][i] / 1000.0
        return ei, ei + it
    if L == "s":
        ei = next(v for hi, v in SHAFT_S if nominal <= hi) / 1000.0
        return ei, ei + it
    raise ValueError(f"shaft class {letter}{grade} is not tabulated; supported shafts: "
                     f"d, e, f, g, h, js, k, n, p, s")


def fit(nominal, designation: str, system: str | None = None) -> dict:
    """Evaluate a fit such as ``fit(25, "H7/g6")``.

    ``nominal`` is in the active unit system (or a string with a unit).  All
    returned values are in mm (internal); use :func:`describe` for display text.
    """
    d = U.to_internal(nominal, "length", system)
    if "/" not in designation:
        raise ValueError("fit designation must look like 'H7/g6'")
    hole_c, shaft_c = (s.strip() for s in designation.split("/", 1))
    if not hole_c[0].isupper() or not shaft_c[0].islower():
        raise ValueError("write the hole class first in capitals and the shaft class in lower case, e.g. H7/g6")
    EI, ES = limits(d, hole_c)
    ei, es = limits(d, shaft_c)
    cmin, cmax = EI - es, ES - ei
    kind = "clearance" if cmin >= 0 else ("interference" if cmax <= 0 else "transition")
    key = f"{hole_c}/{shaft_c}"
    return {"nominal": d, "designation": key, "type": kind,
            "character": PREFERRED.get(key, ""),
            "hole": {"class": hole_c, "lower_dev": EI, "upper_dev": ES, "min": d + EI, "max": d + ES,
                     "tolerance": ES - EI},
            "shaft": {"class": shaft_c, "lower_dev": ei, "upper_dev": es, "min": d + ei, "max": d + es,
                      "tolerance": es - ei},
            "min_clearance": cmin, "max_clearance": cmax,
            "standard": "ISO 286-1:2010 / ASME B4.2"}


def describe(f: dict, system: str | None = None) -> list[tuple[str, str]]:
    metric = U.normalize_system(system) == "metric"
    def L(v, sig=6):
        return U.fmt(v, "length", system, sig=sig)
    def dev(v):
        return f"{v * 1000:+.0f} um" if metric else f"{v / 25.4:+.5f} in"
    rows = [("Fit", f"{L(f['nominal'])} {f['designation']} - {f['type']}"
             + (f" ({f['character']})" if f["character"] else "")),
            ("Hole " + f["hole"]["class"], f"{L(f['hole']['min'])} to {L(f['hole']['max'])} "
             f"({dev(f['hole']['lower_dev'])} / {dev(f['hole']['upper_dev'])})"),
            ("Shaft " + f["shaft"]["class"], f"{L(f['shaft']['min'])} to {L(f['shaft']['max'])} "
             f"({dev(f['shaft']['lower_dev'])} / {dev(f['shaft']['upper_dev'])})")]
    if f["type"] == "interference":
        rows.append(("Interference", f"{dev(-f['max_clearance'])} to {dev(-f['min_clearance'])}"))
    elif f["type"] == "clearance":
        rows.append(("Clearance", f"{dev(f['min_clearance'])} to {dev(f['max_clearance'])}"))
    else:
        rows.append(("Clearance / interference", f"{dev(f['min_clearance'])} (interference) to "
                     f"{dev(f['max_clearance'])} (clearance)"))
    rows.append(("Standard", f["standard"]))
    return rows


def interference_pressure(f: dict, E_hub: float, nu_hub: float, E_shaft: float, nu_shaft: float,
                          hub_od: float, shaft_id: float = 0.0, length: float | None = None,
                          friction: float = 0.12) -> dict:
    """Contact pressure and holding capacity of a press fit (Lame), at min and max interference.

    Moduli in MPa, lengths in mm (internal units).
    """
    d = f["nominal"]
    out = {}
    for tag, delta in (("min", max(-f["max_clearance"], 0.0)), ("max", max(-f["min_clearance"], 0.0))):
        ko = (hub_od**2 + d**2) / (hub_od**2 - d**2) + nu_hub
        ki = (d**2 + shaft_id**2) / (d**2 - shaft_id**2) - nu_shaft
        p = delta / (d * (ko / E_hub + ki / E_shaft))
        out[f"pressure_{tag}"] = p
        out[f"hub_hoop_stress_{tag}"] = p * (hub_od**2 + d**2) / (hub_od**2 - d**2)
        if length:
            import math
            out[f"axial_force_{tag}"] = math.pi * d * length * p * friction
            out[f"torque_{tag}"] = out[f"axial_force_{tag}"] * d / 2
    return out
