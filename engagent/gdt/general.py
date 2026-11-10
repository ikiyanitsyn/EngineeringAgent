"""General tolerances, process capability and clearance holes."""
from __future__ import annotations

from .. import units as U

# ISO 2768-1 linear dimensions: (over, up to) mm -> +/- tolerance mm per class
_LIN_RANGES = [(0.5, 3), (3, 6), (6, 30), (30, 120), (120, 400), (400, 1000), (1000, 2000), (2000, 4000)]
ISO2768_LINEAR = {
    "f": [0.05, 0.05, 0.1, 0.15, 0.2, 0.3, 0.5, None],
    "m": [0.1, 0.1, 0.2, 0.3, 0.5, 0.8, 1.2, 2.0],
    "c": [0.2, 0.3, 0.5, 0.8, 1.2, 2.0, 3.0, 4.0],
    "v": [None, 0.5, 1.0, 1.5, 2.5, 4.0, 6.0, 8.0],
}
# ISO 2768-1 external radii and chamfer heights
_RAD_RANGES = [(0.5, 3), (3, 6), (6, 1e9)]
ISO2768_RADIUS = {"f": [0.2, 0.5, 1.0], "m": [0.2, 0.5, 1.0], "c": [0.4, 1.0, 2.0], "v": [0.4, 1.0, 2.0]}
# ISO 2768-1 angular: length of the shorter leg (mm) -> +/- degrees
_ANG_RANGES = [(0, 10), (10, 50), (50, 120), (120, 400), (400, 1e9)]
ISO2768_ANGULAR = {"f": [1.0, 0.5, 1 / 3, 1 / 6, 1 / 12], "m": [1.0, 0.5, 1 / 3, 1 / 6, 1 / 12],
                   "c": [1.5, 1.0, 0.5, 0.25, 1 / 6], "v": [3.0, 2.0, 1.0, 0.5, 1 / 3]}
# ISO 2768-2 geometrical: straightness / flatness
_GEO_RANGES = [(0, 10), (10, 30), (30, 100), (100, 300), (300, 1000), (1000, 3000)]
ISO2768_FLATNESS = {"H": [0.02, 0.05, 0.1, 0.2, 0.3, 0.4], "K": [0.05, 0.1, 0.2, 0.4, 0.6, 0.8],
                    "L": [0.1, 0.2, 0.4, 0.8, 1.2, 1.6]}
_PERP_RANGES = [(0, 100), (100, 300), (300, 1000), (1000, 3000)]
ISO2768_PERPENDICULARITY = {"H": [0.2, 0.3, 0.4, 0.5], "K": [0.4, 0.6, 0.8, 1.0], "L": [0.6, 1.0, 1.5, 2.0]}
ISO2768_SYMMETRY = {"H": [0.5, 0.5, 0.5, 0.5], "K": [0.6, 0.6, 0.8, 1.0], "L": [0.6, 1.0, 1.5, 2.0]}
ISO2768_RUNOUT = {"H": 0.1, "K": 0.2, "L": 0.5}

# Typical inch title-block defaults (company practice, not a standard): decimal places -> +/- in
ASME_TITLE_BLOCK = {1: 0.030, 2: 0.010, 3: 0.005, 4: 0.0005}
ASME_ANGLE_DEFAULT = 0.5      # degrees


def _pick(ranges, values, x):
    for (lo, hi), v in zip(ranges, values):
        if lo < x <= hi or (lo == 0 and x <= hi):
            return v
    return None


def general_tolerance(nominal, cls: str = "m", system: str | None = None, kind: str = "linear"):
    """ISO 2768 general tolerance (+/- mm, or mm zone for geometrical) for a nominal size.

    kind: linear | radius | angular (returns degrees) | flatness | perpendicularity | symmetry | runout
    """
    d = abs(U.to_internal(nominal, "length", system))
    k = kind.lower()
    if k in ("flatness", "straightness", "perpendicularity", "symmetry", "runout"):
        c = cls.upper()
        if c not in ("H", "K", "L"):
            raise ValueError("ISO 2768-2 class must be H, K or L")
        if k == "runout":
            return ISO2768_RUNOUT[c]
        if k in ("flatness", "straightness"):
            v = _pick(_GEO_RANGES, ISO2768_FLATNESS[c], d)
        else:
            v = _pick(_PERP_RANGES, (ISO2768_PERPENDICULARITY if k == "perpendicularity"
                                     else ISO2768_SYMMETRY)[c], d)
    else:
        c = cls.lower()
        if c not in ISO2768_LINEAR:
            raise ValueError("ISO 2768-1 class must be f, m, c or v")
        if k == "linear":
            v = _pick(_LIN_RANGES, ISO2768_LINEAR[c], d)
        elif k == "radius":
            v = _pick(_RAD_RANGES, ISO2768_RADIUS[c], d)
        elif k == "angular":
            v = _pick(_ANG_RANGES, ISO2768_ANGULAR[c], d)
        else:
            raise ValueError(f"unknown general tolerance kind {kind!r}")
    if v is None:
        raise ValueError(f"ISO 2768 class {cls} gives no {kind} tolerance for {d:g} mm "
                         f"(outside the table); state the tolerance explicitly")
    return v


def title_block_tolerance(value_text: str) -> float:
    """Inch title-block default (+/- in) from the number of decimal places written."""
    places = len(value_text.split(".")[1]) if "." in value_text else 0
    if places not in ASME_TITLE_BLOCK:
        raise ValueError("title-block defaults are defined for 1 to 4 decimal places")
    return ASME_TITLE_BLOCK[places]


# Typical achievable tolerances per process: (fixed +/- mm, proportional +/- fraction of size,
# best practical +/- mm, typical IT grade, note)
PROCESSES = {
    "cnc_milling": (0.05, 0.0, 0.01, "IT8-IT10", "ISO 2768-m is the usual default; +/-0.01 mm needs care"),
    "cnc_turning": (0.025, 0.0, 0.005, "IT7-IT9", "diameters; lengths are closer to milling"),
    "grinding": (0.005, 0.0, 0.002, "IT5-IT7", ""),
    "reaming": (0.013, 0.0, 0.005, "IT7", "holes only"),
    "drilling": (0.1, 0.0, 0.05, "IT11-IT12", "holes only; position +/-0.1 mm without a jig"),
    "laser_cutting": (0.1, 0.0, 0.05, "IT11-IT12", "sheet profile; kerf taper on thick plate"),
    "sheet_bending": (0.25, 0.0, 0.1, "IT13", "bend angle +/-1 deg; ISO 2768-c typical"),
    "fdm": (0.2, 0.002, 0.1, "IT13-IT14", "holes print 0.1-0.4 mm undersize; Z is quantised by layer height"),
    "sla": (0.1, 0.002, 0.05, "IT11-IT12", "post-cure shrinkage; supports mark the surface"),
    "sls": (0.3, 0.003, 0.2, "IT13", "PA12; warpage on large flat areas"),
    "mjf": (0.3, 0.003, 0.2, "IT13", "PA12; similar to SLS with better small features"),
    "dmls": (0.1, 0.002, 0.05, "IT11-IT12", "metal powder bed; machine critical interfaces"),
    "injection_molding": (0.1, 0.002, 0.05, "IT10-IT12", "ISO 20457 / DIN 16742 govern; material shrinkage dependent"),
    "die_casting": (0.1, 0.0015, 0.05, "IT11-IT12", "plus draft; machine datum features"),
    "sand_casting": (1.0, 0.005, 0.5, "IT14+", "ISO 8062 CT grades govern"),
    "tp_stamp_forming": (0.25, 0.001, 0.15, "IT12-IT13",
                         "thermoplastic composite press/stamp forming: thickness +/-5 %, bend angle "
                         "+/-1 deg from spring-in unless tool-compensated"),
    "tp_afp_consolidation": (0.4, 0.001, 0.25, "IT13",
                             "in-situ / oven consolidated tape laminates: thickness +/-8 %"),
    "tp_overmolding": (0.15, 0.002, 0.1, "IT11-IT12", "hybrid overmoulding on a composite insert"),
    "composite_trim_cnc": (0.15, 0.0, 0.1, "IT11", "routed edges and drilled holes in laminates"),
}


def process_capability(process: str, nominal, system: str | None = None) -> dict:
    key = process.lower().replace(" ", "_").replace("-", "_")
    if key not in PROCESSES:
        raise KeyError(f"unknown process {process!r}; known: {', '.join(PROCESSES)}")
    fixed, prop, best, grade, note = PROCESSES[key]
    d = abs(U.to_internal(nominal, "length", system))
    return {"process": key, "nominal": d, "typical": max(fixed, prop * d),
            "best": max(best, prop * d * 0.5), "grade": grade, "note": note}


def check_tolerance(process: str, nominal, tolerance, system: str | None = None) -> dict:
    """Is +/- ``tolerance`` on ``nominal`` realistic for the process?"""
    cap = process_capability(process, nominal, system)
    t = abs(U.to_internal(tolerance, "length", system))
    if t >= cap["typical"]:
        status, msg = "PASS", "within normal process capability"
    elif t >= cap["best"]:
        status, msg = "WARN", "achievable but tighter than normal capability: expect extra cost/inspection"
    else:
        status, msg = "WARN", ("tighter than the process holds on its own: plan a secondary operation "
                               "(ream, bore, grind) or relax it")
    return {**cap, "tolerance": t, "status": status, "message": msg}


# ISO 273 clearance holes for metric fasteners: thread -> (fine, medium, coarse) mm
CLEARANCE_METRIC = {"M2": (2.2, 2.4, 2.6), "M2.5": (2.7, 2.9, 3.1), "M3": (3.2, 3.4, 3.6),
                    "M4": (4.3, 4.5, 4.8), "M5": (5.3, 5.5, 5.8), "M6": (6.4, 6.6, 7.0),
                    "M8": (8.4, 9.0, 10.0), "M10": (10.5, 11.0, 12.0), "M12": (13.0, 13.5, 14.5),
                    "M14": (15.0, 15.5, 16.5), "M16": (17.0, 17.5, 18.5), "M20": (21.0, 22.0, 24.0),
                    "M24": (25.0, 26.0, 28.0), "M30": (31.0, 33.0, 35.0)}
# ASME B18.2.8 clearance holes for inch fasteners: size -> (nominal dia, close, normal, loose) in
CLEARANCE_INCH = {"#4": (0.112, 0.120, 0.129, 0.144), "#6": (0.138, 0.144, 0.156, 0.170),
                  "#8": (0.164, 0.170, 0.177, 0.196), "#10": (0.190, 0.196, 0.206, 0.228),
                  "1/4": (0.250, 0.257, 0.281, 0.297), "5/16": (0.3125, 0.323, 0.344, 0.359),
                  "3/8": (0.375, 0.386, 0.406, 0.422), "7/16": (0.4375, 0.453, 0.469, 0.484),
                  "1/2": (0.500, 0.531, 0.562, 0.609), "5/8": (0.625, 0.656, 0.688, 0.734),
                  "3/4": (0.750, 0.781, 0.812, 0.906), "1": (1.000, 1.031, 1.094, 1.156)}


def clearance_hole(size: str, fit_class: str = "medium") -> dict:
    """Fastener major diameter and clearance-hole diameter (mm)."""
    s = str(size).strip()
    idx = {"fine": 0, "close": 0, "medium": 1, "normal": 1, "coarse": 2, "loose": 2}.get(fit_class.lower())
    if idx is None:
        raise ValueError("fit class must be fine/close, medium/normal or coarse/loose")
    if s.upper() in CLEARANCE_METRIC:
        return {"size": s.upper(), "fastener": float(s[1:]), "hole": CLEARANCE_METRIC[s.upper()][idx],
                "standard": "ISO 273"}
    key = s.split("-")[0].strip().lower()
    if key in CLEARANCE_INCH:
        row = CLEARANCE_INCH[key]
        return {"size": s, "fastener": row[0] * 25.4, "hole": row[idx + 1] * 25.4,
                "standard": "ASME B18.2.8"}
    raise KeyError(f"no clearance-hole data for {size!r}; known: "
                   f"{', '.join(list(CLEARANCE_METRIC) + list(CLEARANCE_INCH))}")
