"""Cross-section properties (internal units: mm)."""
from __future__ import annotations

import math

from . import calc

_OUT = {"A": "area", "Ix": "inertia", "Iy": "inertia", "J": "inertia", "cx": "length",
        "cy": "length", "Zx": "volume", "rx": "length", "ry": "length", "kappa": "ratio"}


def _pack(A, Ix, Iy, J, cx, cy, kappa):
    return {"A": A, "Ix": Ix, "Iy": Iy, "J": J, "cx": cx, "cy": cy, "Zx": Ix / cx,
            "rx": math.sqrt(Ix / A), "ry": math.sqrt(Iy / A), "kappa": kappa}


@calc("section.rectangle", "Solid rectangle b x h (bending about the axis parallel to b)",
      {"b": "length", "h": "length"}, _OUT,
      ["A = b h", "Ix = b h^3 / 12", "Iy = h b^3 / 12",
       "J = a b^3 (1/3 - 0.21 (b/a)(1 - b^4/(12 a^4))), a >= b"],
      "Roark's Formulas for Stress and Strain, 8th ed., Table A.1 and Table 10.1")
def rectangle(b: float, h: float):
    a_, b_ = max(b, h), min(b, h)
    J = a_ * b_**3 * (1 / 3 - 0.21 * (b_ / a_) * (1 - b_**4 / (12 * a_**4)))
    return _pack(b * h, b * h**3 / 12, h * b**3 / 12, J, h / 2, b / 2, 5 / 6)


@calc("section.circle", "Solid circle of diameter d", {"d": "length"}, _OUT,
      ["A = pi d^2 / 4", "I = pi d^4 / 64", "J = pi d^4 / 32"],
      "Roark's Formulas for Stress and Strain, 8th ed., Table A.1")
def circle(d: float):
    I = math.pi * d**4 / 64
    return _pack(math.pi * d**2 / 4, I, I, 2 * I, d / 2, d / 2, 0.9)


@calc("section.tube", "Round tube, outer diameter D, wall t", {"D": "length", "t": "length"}, _OUT,
      ["A = pi (D^2 - d^2)/4", "I = pi (D^4 - d^4)/64", "J = 2 I", "d = D - 2 t"],
      "Roark's Formulas for Stress and Strain, 8th ed., Table A.1")
def tube(D: float, t: float):
    d = D - 2 * t
    if d <= 0:
        raise ValueError("wall thickness must be less than half the outer diameter")
    I = math.pi * (D**4 - d**4) / 64
    return _pack(math.pi * (D**2 - d**2) / 4, I, I, 2 * I, D / 2, D / 2, 0.5)


@calc("section.rect_tube", "Rectangular hollow section b x h, wall t",
      {"b": "length", "h": "length", "t": "length"}, _OUT,
      ["A = b h - (b-2t)(h-2t)", "Ix = (b h^3 - (b-2t)(h-2t)^3)/12",
       "J = 2 t (b-t)^2 (h-t)^2 / (b + h - 2t)  (thin wall, Bredt)"],
      "Roark's Formulas for Stress and Strain, 8th ed., Table A.1 and Table 10.1")
def rect_tube(b: float, h: float, t: float):
    bi, hi = b - 2 * t, h - 2 * t
    if bi <= 0 or hi <= 0:
        raise ValueError("wall too thick for the section")
    A = b * h - bi * hi
    J = 2 * t * (b - t)**2 * (h - t)**2 / (b + h - 2 * t)
    return _pack(A, (b * h**3 - bi * hi**3) / 12, (h * b**3 - hi * bi**3) / 12, J, h / 2, b / 2,
                 2 * hi * t / A if A else 0.44)


@calc("section.i_beam", "Symmetric I-section: flange width b, depth h, flange tf, web tw",
      {"b": "length", "h": "length", "tf": "length", "tw": "length"}, _OUT,
      ["A = 2 b tf + (h - 2 tf) tw", "Ix = (b h^3 - (b - tw)(h - 2 tf)^3)/12",
       "Iy = (2 tf b^3 + (h - 2 tf) tw^3)/12", "J ~ (2 b tf^3 + (h - tf) tw^3)/3"],
      "Roark's Formulas for Stress and Strain, 8th ed., Table A.1")
def i_beam(b: float, h: float, tf: float, tw: float):
    hw = h - 2 * tf
    if hw <= 0 or tw >= b:
        raise ValueError("inconsistent I-section dimensions")
    A = 2 * b * tf + hw * tw
    return _pack(A, (b * h**3 - (b - tw) * hw**3) / 12, (2 * tf * b**3 + hw * tw**3) / 12,
                 (2 * b * tf**3 + (h - tf) * tw**3) / 3, h / 2, b / 2, hw * tw / A)


def section_from(spec: dict) -> dict:
    """Section properties from inputs: either I (+c, A) directly or a shape."""
    if "d" in spec and "D" not in spec:
        return circle(spec["d"])
    if "D" in spec and "t" in spec:
        return tube(spec["D"], spec["t"])
    if "tf" in spec:
        return i_beam(spec["b"], spec["h"], spec["tf"], spec["tw"])
    if "b" in spec and "h" in spec and "t" in spec:
        return rect_tube(spec["b"], spec["h"], spec["t"])
    if "b" in spec and "h" in spec:
        return rectangle(spec["b"], spec["h"])
    raise ValueError("give a section: (b, h), (d), (D, t), (b, h, t) or (b, h, tf, tw), or I and c")
