"""Bolted-joint hand calculations (ISO metric coarse and Unified coarse threads)."""
from __future__ import annotations

import math

from . import calc

# ISO 724 / ISO 898-1 coarse series: nominal d -> (pitch mm, tensile stress area mm^2)
METRIC = {"M3": (0.5, 5.03), "M4": (0.7, 8.78), "M5": (0.8, 14.2), "M6": (1.0, 20.1),
          "M8": (1.25, 36.6), "M10": (1.5, 58.0), "M12": (1.75, 84.3), "M14": (2.0, 115.0),
          "M16": (2.0, 157.0), "M20": (2.5, 245.0), "M24": (3.0, 353.0), "M30": (3.5, 561.0)}
# ISO 898-1 property classes: proof, yield (0.2 %), tensile [MPa]
CLASSES = {"4.6": (225, 240, 400), "5.8": (380, 420, 520), "8.8": (600, 660, 830),
           "10.9": (830, 940, 1040), "12.9": (970, 1100, 1220),
           "a2-70": (450, 450, 700), "a4-80": (600, 600, 800)}
# Unified coarse: size -> (nominal d in, threads per inch, tensile stress area in^2)
UNC = {"#6-32": (0.138, 32, 0.00909), "#8-32": (0.164, 32, 0.0140), "#10-24": (0.190, 24, 0.0175),
       "1/4-20": (0.25, 20, 0.0318), "5/16-18": (0.3125, 18, 0.0524), "3/8-16": (0.375, 16, 0.0775),
       "7/16-14": (0.4375, 14, 0.1063), "1/2-13": (0.5, 13, 0.1419), "5/8-11": (0.625, 11, 0.226),
       "3/4-10": (0.75, 10, 0.334), "1-8": (1.0, 8, 0.606)}
# SAE J429 grades: proof, yield, tensile [ksi]
GRADES = {"grade2": (55, 57, 74), "grade5": (85, 92, 120), "grade8": (120, 130, 150)}


def thread(size: str) -> tuple[float, float, float]:
    """(nominal diameter mm, pitch mm, tensile stress area mm^2)."""
    s = str(size).strip()
    if s.upper() in METRIC:
        p, a = METRIC[s.upper()]
        return float(s[1:]), p, a
    if s.lower() in UNC:
        d, tpi, a = UNC[s.lower()]
        return d * 25.4, 25.4 / tpi, a * 25.4**2
    raise ValueError(f"unknown thread {size!r}; known: {', '.join(list(METRIC) + list(UNC))}")


def strength(grade: str) -> tuple[float, float, float]:
    g = str(grade).lower().replace(" ", "")
    if g in CLASSES:
        return tuple(float(v) for v in CLASSES[g])
    if g in GRADES:
        return tuple(v * 6.894757 for v in GRADES[g])
    raise ValueError(f"unknown bolt grade {grade!r}; known: {', '.join(list(CLASSES) + list(GRADES))}")


@calc("bolt.preload_torque", "Bolt preload and tightening torque",
      {"size": "text", "grade": "text", "preload_fraction": "ratio", "K": "ratio",
       "reusable": "text"},
      {"preload": "force", "torque": "moment", "proof_load": "force", "stress_area": "area",
       "preload_stress": "pressure"},
      ["F_i = fraction * S_p * A_t   (0.75 reusable, 0.90 permanent)", "T = K d F_i",
       "K ~ 0.20 dry zinc/steel, 0.15 lubricated, 0.12 anti-seize"],
      "Shigley's Mechanical Engineering Design, 10th ed., Eq. 8-27, 8-31 and 8-32; ISO 898-1",
      ["Torque control scatters preload by roughly +/-25 %."])
def preload_torque(size, grade="8.8", preload_fraction=None, K=0.2, reusable=True):
    d, _, At = thread(size)
    Sp, _, _ = strength(grade)
    frac = preload_fraction if preload_fraction is not None else \
        (0.75 if str(reusable).lower() not in ("false", "0", "no") else 0.90)
    Fi = frac * Sp * At
    return {"preload": Fi, "torque": K * d * Fi, "proof_load": Sp * At, "stress_area": At,
            "preload_stress": Fi / At}


@calc("bolt.joint_tension", "Preloaded bolted joint under external tension",
      {"size": "text", "grade": "text", "P": "force", "preload": "force", "C": "ratio",
       "n_bolts": "int"},
      {"bolt_load": "force", "bolt_stress": "pressure", "n_yield": "ratio", "n_load": "ratio",
       "n_separation": "ratio", "clamp_load": "force"},
      ["F_b = C P + F_i", "F_m = (1 - C) P - F_i", "n_p = S_p A_t / (C P + F_i)",
       "n_L = (S_p A_t - F_i) / (C P)", "n_0 = F_i / (P (1 - C))",
       "C = k_b / (k_b + k_m), typically 0.15 to 0.30 for steel members"],
      "Shigley's Mechanical Engineering Design, 10th ed., Eq. 8-24, 8-25, 8-28 to 8-30",
      ["P is the total external tensile load shared equally by n_bolts."])
def joint_tension(size, P, grade="8.8", preload=None, C=0.25, n_bolts=1):
    _, _, At = thread(size)
    Sp, _, _ = strength(grade)
    Fi = preload if preload is not None else 0.75 * Sp * At
    Pb = P / int(n_bolts)
    Fb = C * Pb + Fi
    return {"bolt_load": Fb, "bolt_stress": Fb / At, "n_yield": Sp * At / Fb,
            "n_load": (Sp * At - Fi) / (C * Pb) if Pb else float("inf"),
            "n_separation": Fi / (Pb * (1 - C)) if Pb else float("inf"),
            "clamp_load": Fi - (1 - C) * Pb}


@calc("bolt.shear_bearing", "Bolt shear, plate bearing and tear-out",
      {"size": "text", "grade": "text", "V": "force", "t": "length", "edge": "length",
       "plate_yield": "pressure", "n_bolts": "int", "threads_in_shear": "text"},
      {"shear_stress": "pressure", "n_shear": "ratio", "bearing_stress": "pressure",
       "n_bearing": "ratio", "tearout_stress": "pressure", "n_tearout": "ratio"},
      ["tau = V / (n A), A = A_t if threads are in the shear plane else pi d^2 / 4",
       "S_sy = 0.577 S_y(bolt)", "sigma_b = V / (n d t)", "tau_tearout = V / (2 n t e)",
       "e = edge distance from the hole centre"],
      "Shigley's Mechanical Engineering Design, 10th ed., Sec. 8-12")
def shear_bearing(size, V, t, plate_yield, grade="8.8", edge=None, n_bolts=1, threads_in_shear=True):
    d, _, At = thread(size)
    _, Sy, _ = strength(grade)
    n = int(n_bolts)
    A = At if str(threads_in_shear).lower() not in ("false", "0", "no") else math.pi * d**2 / 4
    tau = V / (n * A)
    sb = V / (n * d * t)
    out = {"shear_stress": tau, "n_shear": 0.577 * Sy / tau, "bearing_stress": sb,
           "n_bearing": plate_yield / sb}
    if edge:
        tt = V / (2 * n * t * edge)
        out["tearout_stress"] = tt
        out["n_tearout"] = 0.577 * plate_yield / tt
    return out
