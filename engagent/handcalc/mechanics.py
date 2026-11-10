"""Axial, torsion, pressure, plates, stress concentration, combined stress."""
from __future__ import annotations

import math

from . import calc


@calc("axial.bar", "Axially loaded prismatic bar",
      {"P": "force", "L": "length", "A": "area", "E": "pressure"},
      {"stress": "pressure", "elongation": "length", "strain": "ratio", "stiffness": "stiffness"},
      ["sigma = P / A", "delta = P L / (A E)", "k = A E / L"],
      "Shigley's Mechanical Engineering Design, 10th ed., Eq. 4-3")
def axial_bar(P, L, A, E):
    return {"stress": P / A, "elongation": P * L / (A * E), "strain": P / (A * E),
            "stiffness": A * E / L}


@calc("torsion.round_shaft", "Torsion of a solid or hollow round shaft",
      {"T": "moment", "L": "length", "D": "length", "d_inner": "length", "G": "pressure",
       "E": "pressure", "nu": "ratio"},
      {"shear_stress": "pressure", "twist": "angle", "J": "inertia", "von_mises": "pressure"},
      ["tau = T r / J", "phi = T L / (G J)", "J = pi (D^4 - d^4) / 32", "sigma_vm = sqrt(3) tau"],
      "Shigley's Mechanical Engineering Design, 10th ed., Eq. 3-37 and 4-5")
def torsion_round(T, L, D, d_inner=0.0, G=None, E=None, nu=None):
    if G is None:
        if E is None or nu is None:
            raise ValueError("give G, or E and nu")
        G = E / (2 * (1 + nu))
    J = math.pi * (D**4 - d_inner**4) / 32
    tau = T * D / 2 / J
    return {"shear_stress": tau, "twist": math.degrees(T * L / (G * J)), "J": J,
            "von_mises": math.sqrt(3) * tau}


@calc("pressure.thin_cylinder", "Thin-walled cylinder under internal pressure",
      {"p": "pressure", "D": "length", "t": "length", "closed_ends": "text"},
      {"hoop_stress": "pressure", "axial_stress": "pressure", "von_mises": "pressure"},
      ["sigma_hoop = p r / t (r = mean radius)", "sigma_axial = p r / (2 t) (closed ends)",
       "valid for r / t > 10"],
      "Roark's Formulas for Stress and Strain, 8th ed., Table 13.1 case 1")
def thin_cylinder(p, D, t, closed_ends=True):
    r = (D - t) / 2
    closed = str(closed_ends).lower() not in ("false", "0", "no", "open")
    sh, sa = p * r / t, (p * r / (2 * t) if closed else 0.0)
    notes = [] if r / t > 10 else [f"r/t = {r / t:.1f} < 10: use the thick-wall (Lame) solution."]
    return {"hoop_stress": sh, "axial_stress": sa,
            "von_mises": math.sqrt(sh**2 - sh * sa + sa**2)}, notes


@calc("pressure.thick_cylinder", "Thick-walled cylinder under internal pressure (Lame)",
      {"p": "pressure", "ri": "length", "ro": "length"},
      {"hoop_stress_inner": "pressure", "hoop_stress_outer": "pressure",
       "radial_stress_inner": "pressure", "axial_stress": "pressure", "von_mises_inner": "pressure"},
      ["sigma_hoop(r) = p ri^2 (1 + ro^2 / r^2) / (ro^2 - ri^2)",
       "sigma_r(r) = p ri^2 (1 - ro^2 / r^2) / (ro^2 - ri^2)",
       "sigma_axial = p ri^2 / (ro^2 - ri^2) (closed ends)"],
      "Shigley's Mechanical Engineering Design, 10th ed., Eq. 3-49 to 3-51")
def thick_cylinder(p, ri, ro):
    k = p * ri**2 / (ro**2 - ri**2)
    sh, sr, sa = k * (1 + ro**2 / ri**2), -p, k
    vm = math.sqrt(((sh - sr)**2 + (sr - sa)**2 + (sa - sh)**2) / 2)
    return {"hoop_stress_inner": sh, "hoop_stress_outer": 2 * k, "radial_stress_inner": sr,
            "axial_stress": sa, "von_mises_inner": vm}


# Roark Table 11.4: rectangular plate, uniform pressure. a = long side, b = short side.
_AB = [1.0, 1.2, 1.4, 1.6, 1.8, 2.0, 3.0, 4.0, 5.0, 1e9]
_SS_BETA = [0.2874, 0.3762, 0.4530, 0.5172, 0.5688, 0.6102, 0.7134, 0.7410, 0.7476, 0.7500]
_SS_ALPHA = [0.0444, 0.0616, 0.0770, 0.0906, 0.1017, 0.1110, 0.1335, 0.1400, 0.1417, 0.1421]
_CL_AB = [1.0, 1.2, 1.4, 1.6, 1.8, 2.0, 1e9]
_CL_BETA = [0.3078, 0.3834, 0.4356, 0.4680, 0.4872, 0.4974, 0.5000]
_CL_ALPHA = [0.0138, 0.0188, 0.0226, 0.0251, 0.0267, 0.0277, 0.0284]


def _interp(x, xs, ys):
    if x <= xs[0]:
        return ys[0]
    for i in range(1, len(xs)):
        if x <= xs[i]:
            if xs[i] > 1e8:
                return ys[i] if x > 2 * xs[i - 1] else ys[i - 1] + (ys[i] - ys[i - 1]) * min(1.0, (x - xs[i - 1]) / xs[i - 1])
            f = (x - xs[i - 1]) / (xs[i] - xs[i - 1])
            return ys[i - 1] + f * (ys[i] - ys[i - 1])
    return ys[-1]


@calc("plate.rectangular_uniform", "Flat rectangular plate under uniform pressure",
      {"q": "pressure", "a": "length", "b": "length", "t": "length", "E": "pressure",
       "edges": "text"},
      {"stress": "pressure", "deflection": "length", "beta": "ratio", "alpha": "ratio"},
      ["sigma_max = beta q b^2 / t^2", "y_max = alpha q b^4 / (E t^3)",
       "b = short side; beta, alpha from Roark Table 11.4 (nu = 0.3)"],
      "Roark's Formulas for Stress and Strain, 8th ed., Table 11.4 cases 1a and 8a",
      ["Small-deflection plate theory: valid while deflection < about t/2.",
       "Simply supported: maximum stress at the centre. Clamped: at the middle of the long edge."])
def plate_rect(q, a, b, t, E, edges="simply_supported"):
    a, b = max(a, b), min(a, b)
    clamped = str(edges).lower().startswith(("clamp", "fixed", "built"))
    if clamped:
        beta, alpha = _interp(a / b, _CL_AB, _CL_BETA), _interp(a / b, _CL_AB, _CL_ALPHA)
    else:
        beta, alpha = _interp(a / b, _AB, _SS_BETA), _interp(a / b, _AB, _SS_ALPHA)
    y = alpha * q * b**4 / (E * t**3)
    notes = [f"Deflection {y:.3g} mm exceeds t/2: membrane action matters; run nonlinear FEA."] \
        if y > t / 2 else []
    return {"stress": beta * q * b**2 / t**2, "deflection": y, "beta": beta, "alpha": alpha}, notes


@calc("plate.circular_uniform", "Flat circular plate under uniform pressure",
      {"q": "pressure", "r": "length", "t": "length", "E": "pressure", "nu": "ratio",
       "edges": "text"},
      {"stress": "pressure", "deflection": "length"},
      ["clamped: sigma_max = 3 q r^2 / (4 t^2) at the edge; y = q r^4 / (64 D)",
       "simply supported: sigma_max = 3 (3 + nu) q r^2 / (8 t^2) at the centre; "
       "y = (5 + nu) q r^4 / (64 (1 + nu) D)", "D = E t^3 / (12 (1 - nu^2))"],
      "Roark's Formulas for Stress and Strain, 8th ed., Table 11.2 cases 10a and 10b")
def plate_circ(q, r, t, E, nu=0.3, edges="clamped"):
    Dp = E * t**3 / (12 * (1 - nu**2))
    if str(edges).lower().startswith(("clamp", "fixed", "built")):
        return {"stress": 3 * q * r**2 / (4 * t**2), "deflection": q * r**4 / (64 * Dp)}
    return {"stress": 3 * (3 + nu) * q * r**2 / (8 * t**2),
            "deflection": (5 + nu) * q * r**4 / (64 * (1 + nu) * Dp)}


@calc("kt.plate_hole_tension", "Stress concentration: central hole in a finite-width plate, tension",
      {"P": "force", "w": "length", "d": "length", "t": "length"},
      {"Kt": "ratio", "nominal_stress": "pressure", "peak_stress": "pressure",
       "gross_stress": "pressure"},
      ["sigma_nom = P / ((w - d) t)   (net section)",
       "Kt = 3.000 - 3.140 (d/w) + 3.667 (d/w)^2 - 1.527 (d/w)^3", "sigma_peak = Kt sigma_nom"],
      "Pilkey, Peterson's Stress Concentration Factors, 3rd ed., Chart 4.1 (Heywood fit)")
def kt_hole(P, w, d, t):
    r = d / w
    if not 0 < r < 1:
        raise ValueError("hole diameter must be smaller than the plate width")
    Kt = 3.0 - 3.14 * r + 3.667 * r**2 - 1.527 * r**3
    nom = P / ((w - d) * t)
    return {"Kt": Kt, "nominal_stress": nom, "peak_stress": Kt * nom, "gross_stress": P / (w * t)}


@calc("kt.shoulder_fillet_tension", "Stress concentration: stepped flat bar with fillets, tension",
      {"P": "force", "D": "length", "d": "length", "r": "length", "t": "length"},
      {"Kt": "ratio", "nominal_stress": "pressure", "peak_stress": "pressure"},
      ["sigma_nom = P / (d t)", "Kt = C1 + C2 (2h/D) + C3 (2h/D)^2 + C4 (2h/D)^3, h = (D - d)/2",
       "C1..C4 polynomial in sqrt(h/r)"],
      "Pilkey, Peterson's Stress Concentration Factors, 3rd ed., Chart 3.1")
def kt_fillet(P, D, d, r, t):
    h = (D - d) / 2
    if h <= 0 or r <= 0:
        raise ValueError("need D > d and r > 0")
    s = math.sqrt(h / r)
    hr = h / r
    if 0.1 <= hr <= 2.0:
        C = (1.006 + 1.008 * s - 0.044 * hr, -0.115 - 0.584 * s + 0.315 * hr,
             0.245 - 1.006 * s - 0.257 * hr, -0.135 + 0.582 * s - 0.017 * hr)
    else:
        C = (1.020 + 1.009 * s - 0.048 * hr, -0.065 - 0.165 * s - 0.007 * hr,
             -3.459 + 1.266 * s - 0.016 * hr, 3.505 - 2.109 * s + 0.069 * hr)
    x = 2 * h / D
    Kt = C[0] + C[1] * x + C[2] * x**2 + C[3] * x**3
    nom = P / (d * t)
    notes = [] if 0.1 <= hr <= 20 else ["h/r outside the chart range 0.1-20; Kt is an extrapolation."]
    return {"Kt": Kt, "nominal_stress": nom, "peak_stress": Kt * nom}, notes


@calc("stress.von_mises", "Von Mises equivalent and principal stresses from components",
      {"sx": "pressure", "sy": "pressure", "sz": "pressure", "txy": "pressure",
       "tyz": "pressure", "tzx": "pressure", "yield_strength": "pressure"},
      {"von_mises": "pressure", "s1": "pressure", "s2": "pressure", "s3": "pressure",
       "max_shear": "pressure", "safety_factor": "ratio"},
      ["sigma_vm = sqrt(((sx-sy)^2 + (sy-sz)^2 + (sz-sx)^2)/2 + 3 (txy^2 + tyz^2 + tzx^2))",
       "n = Sy / sigma_vm (distortion-energy theory)"],
      "Shigley's Mechanical Engineering Design, 10th ed., Eq. 5-14 and 5-19")
def von_mises(sx=0.0, sy=0.0, sz=0.0, txy=0.0, tyz=0.0, tzx=0.0, yield_strength=None):
    import numpy as np
    vm = math.sqrt(((sx - sy)**2 + (sy - sz)**2 + (sz - sx)**2) / 2 + 3 * (txy**2 + tyz**2 + tzx**2))
    p = np.linalg.eigvalsh(np.array([[sx, txy, tzx], [txy, sy, tyz], [tzx, tyz, sz]]))[::-1]
    out = {"von_mises": vm, "s1": float(p[0]), "s2": float(p[1]), "s3": float(p[2]),
           "max_shear": float(p[0] - p[2]) / 2}
    if yield_strength and vm > 0:
        out["safety_factor"] = yield_strength / vm
    return out


@calc("thermal.restrained_bar", "Fully restrained bar under a uniform temperature change",
      {"E": "pressure", "cte": "cte", "dT": "temp_delta", "A": "area"},
      {"stress": "pressure", "force": "force", "free_strain": "ratio"},
      ["sigma = -E alpha dT (compressive for heating)", "F = sigma A"],
      "Shigley's Mechanical Engineering Design, 10th ed., Eq. 3-61")
def restrained_bar(E, cte, dT, A=None):
    s = -E * cte * dT
    out = {"stress": s, "free_strain": cte * dT}
    if A:
        out["force"] = s * A
    return out


@calc("thermal.free_expansion", "Free thermal expansion of a length",
      {"L": "length", "cte": "cte", "dT": "temp_delta"}, {"growth": "length", "strain": "ratio"},
      ["delta = alpha L dT"], "Shigley's Mechanical Engineering Design, 10th ed., Eq. 3-60")
def free_expansion(L, cte, dT):
    return {"growth": cte * L * dT, "strain": cte * dT}
