"""Stress-life fatigue screening (Marin factors, mean-stress criteria, Basquin life)."""
from __future__ import annotations

import math

from . import calc

# Marin surface factor ka = a * Sut^b  (Sut in MPa), Shigley Table 6-2
_SURFACE = {"ground": (1.58, -0.085), "machined": (4.51, -0.265), "cold_drawn": (4.51, -0.265),
            "hot_rolled": (57.7, -0.718), "as_forged": (272.0, -0.995), "polished": (1.0, 0.0)}
_RELIABILITY = {0.5: 1.0, 0.9: 0.897, 0.95: 0.868, 0.99: 0.814, 0.999: 0.753, 0.9999: 0.702}


@calc("fatigue.endurance_limit", "Corrected endurance limit (Marin factors) for steel",
      {"uts": "pressure", "surface": "text", "size": "length", "loading": "text",
       "reliability": "ratio", "endurance_test": "pressure", "k_misc": "ratio"},
      {"Se": "pressure", "Se_prime": "pressure", "ka": "ratio", "kb": "ratio", "kc": "ratio",
       "ke": "ratio"},
      ["Se = ka kb kc kd ke kf Se'", "Se' = 0.5 Sut (steel, Sut <= 1400 MPa), else 700 MPa",
       "ka = a Sut^b (surface)", "kb = 1.24 d^-0.107 (2.79 <= d <= 51 mm), 1.51 d^-0.157 (51 < d <= 254 mm)",
       "kc = 1 bending, 0.85 axial, 0.59 torsion"],
      "Shigley's Mechanical Engineering Design, 10th ed., Sec. 6-7 to 6-9",
      ["Steel correlations. For aluminium, titanium, polymers and composites supply a tested "
       "fatigue strength with 'endurance_test' (taken as Se' at the stated life)."])
def endurance_limit(uts, surface="machined", size=None, loading="bending", reliability=0.5,
                    endurance_test=None, k_misc=1.0):
    se_p = endurance_test if endurance_test else (0.5 * uts if uts <= 1400 else 700.0)
    key = str(surface).lower().replace("-", "_").replace(" ", "_")
    if key not in _SURFACE:
        raise ValueError(f"surface must be one of {', '.join(_SURFACE)}")
    a, b = _SURFACE[key]
    ka = min(1.0, a * uts**b)
    load = str(loading).lower()
    kc = {"bending": 1.0, "axial": 0.85, "torsion": 0.59}.get(load)
    if kc is None:
        raise ValueError("loading must be bending, axial or torsion")
    if size is None or load == "axial":
        kb = 1.0
    elif size <= 51:
        kb = 1.24 * max(size, 2.79) ** -0.107
    else:
        kb = 1.51 * size ** -0.157
    ke = _RELIABILITY.get(round(float(reliability), 4))
    if ke is None:
        raise ValueError(f"reliability must be one of {', '.join(str(k) for k in _RELIABILITY)}")
    return {"Se": ka * kb * kc * ke * k_misc * se_p, "Se_prime": se_p, "ka": ka, "kb": kb,
            "kc": kc, "ke": ke}


@calc("fatigue.mean_stress", "Fatigue safety factor with mean stress (Goodman, Gerber, Soderberg, Langer)",
      {"stress_alt": "pressure", "stress_mean": "pressure", "Se": "pressure", "uts": "pressure",
       "yield_strength": "pressure", "Kf": "ratio"},
      {"n_goodman": "ratio", "n_gerber": "ratio", "n_soderberg": "ratio", "n_yield": "ratio",
       "stress_alt_equiv": "pressure"},
      ["Goodman: 1/n = sa/Se + sm/Sut", "Soderberg: 1/n = sa/Se + sm/Sy",
       "Gerber: n sa/Se + (n sm/Sut)^2 = 1", "Langer first-cycle yield: n = Sy / (sa + sm)",
       "sigma_ar = sa / (1 - sm/Sut)  (equivalent fully reversed, Goodman)"],
      "Shigley's Mechanical Engineering Design, 10th ed., Sec. 6-12, Eq. 6-45 to 6-49",
      ["Kf (fatigue notch factor) multiplies the alternating stress; use Kf = 1 when the FEA "
       "stress already includes the notch.",
       "Compressive mean stress is treated as zero mean (conservative for Goodman)."])
def mean_stress(stress_alt, stress_mean, Se, uts, yield_strength=None, Kf=1.0):
    sa, sm = abs(stress_alt) * Kf, max(stress_mean, 0.0)
    out = {}
    out["n_goodman"] = 1 / (sa / Se + sm / uts) if (sa or sm) else float("inf")
    if sm > 0:
        r = (uts / sm)**2 * sa / Se
        out["n_gerber"] = 0.5 * r * (-1 + math.sqrt(1 + (2 * sm * Se / (uts * sa))**2)) if sa else uts / sm
    else:
        out["n_gerber"] = Se / sa if sa else float("inf")
    if yield_strength:
        out["n_soderberg"] = 1 / (sa / Se + sm / yield_strength) if (sa or sm) else float("inf")
        out["n_yield"] = yield_strength / (sa + abs(stress_mean)) if (sa or stress_mean) else float("inf")
    out["stress_alt_equiv"] = sa / (1 - sm / uts) if sm < uts else float("inf")
    return out


@calc("fatigue.basquin_life", "Finite life from the S-N (Basquin) line",
      {"stress_alt_equiv": "pressure", "uts": "pressure", "Se": "pressure", "f": "ratio",
       "N_endurance": "ratio"},
      {"cycles": "ratio", "a": "pressure", "b": "ratio"},
      ["S_f = a N^b", "a = (f Sut)^2 / Se", "b = -(1/3) log10(f Sut / Se)", "N = (sigma_ar / a)^(1/b)",
       "f = fatigue strength fraction at 10^3 cycles (about 0.9 at Sut = 490 MPa, 0.77 at 1380 MPa)"],
      "Shigley's Mechanical Engineering Design, 10th ed., Eq. 6-13 to 6-16",
      ["Valid for 10^3 to N_endurance cycles; below Se the life is reported as infinite "
       "(steel) and above f*Sut the result is low-cycle fatigue (not valid here)."])
def basquin_life(stress_alt_equiv, uts, Se, f=None, N_endurance=1e6):
    if f is None:
        f = min(0.9, max(0.77, 0.9 - (uts - 490.0) * (0.9 - 0.77) / (1380.0 - 490.0)))
    s3 = f * uts
    n_dec = math.log10(N_endurance) - 3
    b = -math.log10(s3 / Se) / n_dec
    a = s3 / (1e3 ** b)
    notes = []
    if stress_alt_equiv <= Se:
        N = float("inf")
        notes.append("Equivalent alternating stress is below the endurance limit: infinite life predicted.")
    else:
        N = (stress_alt_equiv / a) ** (1 / b)
        if stress_alt_equiv > s3:
            notes.append("Stress exceeds the 10^3-cycle strength: low-cycle fatigue; use strain-life.")
    return {"cycles": N, "a": a, "b": b}, notes
