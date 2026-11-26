"""Heat-transfer hand calculations (internal units: mm, mW, degC, s, tonne, mJ)."""
from __future__ import annotations

import math

from . import calc


@calc("thermal.conduction_slab", "Steady 1-D conduction through a slab or bar",
      {"k": "conductivity", "A": "area", "L": "length", "T_hot": "temperature",
       "T_cold": "temperature", "x": "length"},
      {"heat_flow": "power", "heat_flux": "heat_flux", "resistance_dT": "temp_delta",
       "T_at_x": "temperature"},
      ["q = k A (T_hot - T_cold) / L", "T(x) = T_hot - (T_hot - T_cold) x / L"],
      "Incropera, Fundamentals of Heat and Mass Transfer, 7th ed., Eq. 3.4")
def conduction_slab(k, A, L, T_hot, T_cold, x=None):
    q = k * A * (T_hot - T_cold) / L
    out = {"heat_flow": q, "heat_flux": q / A, "resistance_dT": T_hot - T_cold}
    if x is not None:
        out["T_at_x"] = T_hot - (T_hot - T_cold) * x / L
    return out


@calc("thermal.convection", "Convective heat flow from a surface (or, given the heat, the surface temperature)",
      {"h": "film", "A": "area", "T_surface": "temperature", "T_ambient": "temperature", "heat_flow": "power"},
      {"heat_flow": "power", "T_surface": "temperature"},
      ["q = h A (T_s - T_inf)", "T_s = T_inf + q / (h A)   (a body losing heat q from area A)"],
      "Incropera, Fundamentals of Heat and Mass Transfer, 7th ed., Eq. 1.3a")
def convection(h, A, T_ambient, T_surface=None, heat_flow=None):
    if T_surface is not None:
        return {"heat_flow": h * A * (T_surface - T_ambient), "T_surface": T_surface}
    if heat_flow is None:
        raise ValueError("give T_surface (to get the heat flow) or heat_flow (to get the surface temperature)")
    return {"T_surface": T_ambient + heat_flow / (h * A), "heat_flow": heat_flow}


@calc("thermal.wall_conduction_convection", "Slab with fixed temperature on one face, convection on the other",
      {"k": "conductivity", "L": "length", "h": "film", "T_fixed": "temperature",
       "T_ambient": "temperature", "A": "area"},
      {"T_surface": "temperature", "heat_flux": "heat_flux", "heat_flow": "power", "biot": "ratio"},
      ["q'' = (T_fixed - T_inf) / (L/k + 1/h)", "T_surface = T_inf + q'' / h", "Bi = h L / k"],
      "Incropera, Fundamentals of Heat and Mass Transfer, 7th ed., Sec. 3.1.3 (thermal circuit)")
def wall_cond_conv(k, L, h, T_fixed, T_ambient, A=None):
    q = (T_fixed - T_ambient) / (L / k + 1 / h)
    out = {"T_surface": T_ambient + q / h, "heat_flux": q, "biot": h * L / k}
    if A:
        out["heat_flow"] = q * A
    return out


@calc("thermal.lumped_transient", "Lumped-capacitance transient (uniform body temperature)",
      {"density": "density", "cp": "specific_heat", "V": "volume", "h": "film", "A": "area",
       "k": "conductivity", "T_initial": "temperature", "T_ambient": "temperature",
       "time": "time", "T_target": "temperature"},
      {"tau": "time", "biot": "ratio", "T_at_time": "temperature", "time_to_target": "time"},
      ["tau = rho c V / (h A)", "T(t) = T_inf + (T_i - T_inf) exp(-t / tau)",
       "Bi = h (V/A) / k  (valid for Bi < 0.1)"],
      "Incropera, Fundamentals of Heat and Mass Transfer, 7th ed., Eq. 5.5 to 5.10")
def lumped(density, cp, V, h, A, k=None, T_initial=None, T_ambient=None, time=None, T_target=None):
    tau = density * cp * V / (h * A)
    out = {"tau": tau}
    notes = []
    if k:
        out["biot"] = h * (V / A) / k
        if out["biot"] > 0.1:
            notes.append(f"Bi = {out['biot']:.3g} > 0.1: internal gradients matter; "
                         f"use thermal.slab_transient or FEA instead.")
    if T_initial is not None and T_ambient is not None:
        if time is not None:
            out["T_at_time"] = T_ambient + (T_initial - T_ambient) * math.exp(-time / tau)
        if T_target is not None:
            r = (T_target - T_ambient) / (T_initial - T_ambient)
            if 0 < r < 1:
                out["time_to_target"] = -tau * math.log(r)
    return out, notes


def _zeta1(bi: float) -> float:
    """First root of zeta tan(zeta) = Bi."""
    if bi > 1e8:
        return math.pi / 2
    lo, hi = 1e-9, math.pi / 2 - 1e-12
    for _ in range(200):
        mid = (lo + hi) / 2
        if mid * math.tan(mid) > bi:
            hi = mid
        else:
            lo = mid
    return (lo + hi) / 2


def slab_series(theta_fn_x: float, Fo: float, bi: float, terms: int = 60) -> float:
    """Dimensionless temperature theta*(x*, Fo) of a plane wall, half-thickness L, both faces
    convecting (Bi) or held at ambient (Bi -> inf).  x* = 0 is the mid-plane."""
    total = 0.0
    if bi > 1e8:
        for n in range(terms):
            z = (2 * n + 1) * math.pi / 2
            total += (4 * math.sin(z) / (2 * z + math.sin(2 * z))) * math.exp(-z * z * Fo) * math.cos(z * theta_fn_x)
        return total
    # roots of z tan z = Bi in each interval (n pi, n pi + pi/2)
    for n in range(terms):
        lo, hi = n * math.pi + 1e-12, n * math.pi + math.pi / 2 - 1e-12
        for _ in range(100):
            mid = (lo + hi) / 2
            if mid * math.tan(mid) > bi:
                hi = mid
            else:
                lo = mid
        z = (lo + hi) / 2
        total += (4 * math.sin(z) / (2 * z + math.sin(2 * z))) * math.exp(-z * z * Fo) * math.cos(z * theta_fn_x)
    return total


@calc("thermal.slab_transient", "Transient conduction in a plane wall heated or cooled from both faces",
      {"k": "conductivity", "density": "density", "cp": "specific_heat", "thickness": "length",
       "T_initial": "temperature", "T_ambient": "temperature", "time": "time", "h": "film",
       "T_target": "temperature", "one_sided": "text"},
      {"T_center": "temperature", "T_surface": "temperature", "fourier": "ratio", "biot": "ratio",
       "diffusivity": "area", "time_to_target": "time"},
      ["alpha = k / (rho c)", "Fo = alpha t / L^2, L = half thickness (full thickness if one-sided)",
       "theta* = sum C_n exp(-zeta_n^2 Fo) cos(zeta_n x*), zeta_n tan(zeta_n) = Bi",
       "T = T_inf + theta* (T_i - T_inf)"],
      "Incropera, Fundamentals of Heat and Mass Transfer, 7th ed., Eq. 5.42 (exact series solution)",
      ["Omit h for a prescribed surface temperature (Bi -> infinity), e.g. a laminate in a hot press.",
       "one_sided=true: heated from one face, the other face insulated.",
       "'diffusivity' is reported in area units per second."])
def slab_transient(k, density, cp, thickness, T_initial, T_ambient, time=None, h=None,
                   T_target=None, one_sided=False):
    one = str(one_sided).lower() in ("true", "1", "yes")
    L = thickness if one else thickness / 2
    alpha = k / (density * cp)
    bi = h * L / k if h else 1e12
    out = {"diffusivity": alpha}
    if h:
        out["biot"] = bi
    def centre(t):
        return T_ambient + slab_series(0.0, alpha * t / L**2, bi) * (T_initial - T_ambient)
    if time is not None:
        Fo = alpha * time / L**2
        out["fourier"] = Fo
        out["T_center"] = centre(time)
        out["T_surface"] = T_ambient + slab_series(1.0, Fo, bi) * (T_initial - T_ambient)
    if T_target is not None:
        r = (T_target - T_ambient) / (T_initial - T_ambient)
        if 0 < r < 1:
            lo, hi = 0.0, L**2 / alpha * 50
            for _ in range(200):
                mid = (lo + hi) / 2
                if slab_series(0.0, alpha * mid / L**2, bi) > r:
                    lo = mid
                else:
                    hi = mid
            out["time_to_target"] = (lo + hi) / 2
    return out


@calc("thermal.fin_straight", "Straight fin of uniform cross-section (adiabatic tip)",
      {"k": "conductivity", "h": "film", "P": "length", "A": "area", "L": "length",
       "T_base": "temperature", "T_ambient": "temperature"},
      {"heat_flow": "power", "efficiency": "ratio", "T_tip": "temperature", "mL": "ratio"},
      ["m = sqrt(h P / (k A))", "q = sqrt(h P k A) (T_b - T_inf) tanh(m L)",
       "eta = tanh(m L) / (m L)", "T_tip = T_inf + (T_b - T_inf) / cosh(m L)"],
      "Incropera, Fundamentals of Heat and Mass Transfer, 7th ed., Table 3.4 case B",
      ["P = fin perimeter, A = fin cross-section area."])
def fin(k, h, P, A, L, T_base, T_ambient):
    m = math.sqrt(h * P / (k * A))
    th = T_base - T_ambient
    return {"heat_flow": math.sqrt(h * P * k * A) * th * math.tanh(m * L),
            "efficiency": math.tanh(m * L) / (m * L), "T_tip": T_ambient + th / math.cosh(m * L),
            "mL": m * L}


@calc("thermal.radiation", "Grey-body radiation from a surface to large surroundings",
      {"emissivity": "ratio", "A": "area", "T_surface": "temperature", "T_ambient": "temperature"},
      {"heat_flow": "power", "h_equivalent": "film"},
      ["q = eps sigma A (Ts^4 - Tsur^4), absolute temperatures", "sigma = 5.670e-8 W/(m^2 K^4)"],
      "Incropera, Fundamentals of Heat and Mass Transfer, 7th ed., Eq. 1.7")
def radiation(emissivity, A, T_surface, T_ambient):
    sig = 5.670374419e-11
    ts, ta = T_surface + 273.15, T_ambient + 273.15
    q = emissivity * sig * A * (ts**4 - ta**4)
    return {"heat_flow": q, "h_equivalent": q / (A * (ts - ta)) if ts != ta else 0.0}
