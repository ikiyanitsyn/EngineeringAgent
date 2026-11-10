"""Thermoplastic-composite hand calculations.

Classical laminate theory (CLT), smeared 3-D laminate properties for solid
FEA, process-induced spring-in, and consolidation / cooling estimates.
Internal units (mm, MPa, 1/K, mW/(mm K)).
"""
from __future__ import annotations

import math

import numpy as np

from . import calc
from .. import materials
from .thermal import slab_transient


def _lamina(material) -> dict:
    m = materials.get(material) if not isinstance(material, materials.Material) else material
    if not m.orthotropic:
        raise ValueError(f"{m.key} is not an orthotropic lamina; use a *_ud or *_fabric material")
    return m.props | {"_key": m.key, "_name": m.name, "_tply": m.meta.get("ply_thickness_mm")}


def expand_layup(layup, symmetric=False) -> list[float]:
    """Accept [0, 45, -45, 90] or a string such as '[0/45/-45/90]2s'."""
    if isinstance(layup, str):
        s = layup.strip().lower().replace(" ", "")
        sym = s.endswith("s")
        s = s[:-1] if sym else s
        rep = 1
        if "]" in s:
            body, tail = s.split("]", 1)
            rep = int(tail) if tail else 1
            s = body.lstrip("[")
        angles = []
        for tok in s.replace(",", "/").split("/"):
            if tok.startswith("±") or tok.startswith("+-"):
                a = float(tok.lstrip("±+-"))
                angles += [a, -a]
            elif tok:
                angles.append(float(tok))
        angles = angles * rep
        return angles + angles[::-1] if (sym or symmetric) else angles
    angles = [float(a) for a in layup]
    return angles + angles[::-1] if symmetric else angles


def _Q(p):
    d = 1 - p["nu12"] * p["nu12"] * p["E2"] / p["E1"]
    return np.array([[p["E1"] / d, p["nu12"] * p["E2"] / d, 0],
                     [p["nu12"] * p["E2"] / d, p["E2"] / d, 0],
                     [0, 0, p["G12"]]])


def _T(theta_deg):
    c, s = math.cos(math.radians(theta_deg)), math.sin(math.radians(theta_deg))
    Ts = np.array([[c * c, s * s, 2 * c * s], [s * s, c * c, -2 * c * s], [-c * s, c * s, c * c - s * s]])
    Te = np.array([[c * c, s * s, c * s], [s * s, c * c, -c * s], [-2 * c * s, 2 * c * s, c * c - s * s]])
    return Ts, Te, c, s


def clt(material, layup, ply_thickness=None, symmetric=False, dT=None) -> dict:
    """Full CLT result: ABD, effective constants, CTEs, smeared 3-D constants, ply stresses."""
    p = _lamina(material)
    angles = expand_layup(layup, symmetric)
    t = float(ply_thickness or p.get("_tply") or 0.14)
    n = len(angles)
    h = n * t
    z = np.linspace(-h / 2, h / 2, n + 1)
    Q = _Q(p)
    a_mat = np.array([p.get("cte1", 0.0), p.get("cte2", 0.0), 0.0])
    A = np.zeros((3, 3)); B = np.zeros((3, 3)); D = np.zeros((3, 3))
    NT = np.zeros(3); MT = np.zeros(3)
    plies = []
    for k, th in enumerate(angles):
        Ts, Te, c, s = _T(th)
        Qb = np.linalg.inv(Ts) @ Q @ Te
        ab = np.linalg.inv(Te) @ a_mat            # global CTE (engineering shear)
        z0, z1 = z[k], z[k + 1]
        A += Qb * (z1 - z0); B += Qb * (z1**2 - z0**2) / 2; D += Qb * (z1**3 - z0**3) / 3
        NT += Qb @ ab * (z1 - z0); MT += Qb @ ab * (z1**2 - z0**2) / 2
        plies.append((th, Qb, ab, Te, (z0 + z1) / 2, c, s))
    ABD = np.block([[A, B], [B, D]])
    abd = np.linalg.inv(ABD)
    a_ = abd[:3, :3]
    out = {"n_plies": n, "thickness": h, "angles": angles, "A": A, "B": B, "D": D,
           "Ex": 1 / (h * a_[0, 0]), "Ey": 1 / (h * a_[1, 1]), "Gxy": 1 / (h * a_[2, 2]),
           "nuxy": -a_[0, 1] / a_[0, 0],
           "Efx": 12 / (h**3 * abd[3, 3]), "Efy": 12 / (h**3 * abd[4, 4]),
           "symmetric": bool(np.abs(B).max() < 1e-6 * np.abs(A).max() * h),
           "balanced": bool(abs(A[0, 2]) + abs(A[1, 2]) < 1e-6 * A[0, 0])}
    eps_k = abd @ np.concatenate([NT, MT])       # per unit dT: mid-plane strain + curvature
    out["alpha_x"], out["alpha_y"], out["alpha_xy"] = eps_k[0], eps_k[1], eps_k[2]
    out["kappa_per_K"] = eps_k[3:].tolist()
    # through-thickness response: alpha_z, nu_xz, nu_yz, transverse shear, conductivity
    def eps_z(e0, kap, thermal: float):
        tot = 0.0
        for th, Qb, ab, Te, zm, c, s in plies:
            e_glob = e0 + zm * kap
            e_mat = Te @ e_glob
            sig = Q @ (e_mat - a_mat * thermal)
            tot += t * (p.get("cte3", 0.0) * thermal - p["nu13"] / p["E1"] * sig[0]
                        - p["nu23"] / p["E2"] * sig[1])
        return tot / h
    out["alpha_z"] = eps_z(eps_k[:3], eps_k[3:], 1.0)
    ex = abd @ np.array([h, 0, 0, 0, 0, 0]); ey = abd @ np.array([0, h, 0, 0, 0, 0])
    out["nuxz"] = -eps_z(ex[:3], ex[3:], 0.0) / ex[0]
    out["nuyz"] = -eps_z(ey[:3], ey[3:], 0.0) / ey[1]
    out["Ez"] = p["E3"]
    out["Gxz"] = sum(t * (p["G13"] * c * c + p["G23"] * s * s) for *_, c, s in plies) / h
    out["Gyz"] = sum(t * (p["G13"] * s * s + p["G23"] * c * c) for *_, c, s in plies) / h
    if p.get("k1") is not None:
        out["kx"] = sum(t * (p["k1"] * c * c + p["k2"] * s * s) for *_, c, s in plies) / h
        out["ky"] = sum(t * (p["k1"] * s * s + p["k2"] * c * c) for *_, c, s in plies) / h
        out["kz"] = p["k3"]
    if dT is not None:
        e0, kap = eps_k[:3] * dT, eps_k[3:] * dT
        worst = {"s1": 0.0, "s2": 0.0, "t12": 0.0}
        for th, Qb, ab, Te, zm, c, s in plies:
            sig = Q @ (Te @ (e0 + zm * kap) - a_mat * dT)
            for key, v in zip(("s1", "s2", "t12"), sig):
                if abs(v) > abs(worst[key]):
                    worst[key] = float(v)
        out["ply_residual"] = worst
    return out


def smeared_material(lamina, layup, ply_thickness=None, symmetric=False) -> materials.Material:
    """Homogenised orthotropic solid: 1 = laminate x (0 deg), 2 = laminate y, 3 = thickness."""
    r = clt(lamina, layup, ply_thickness, symmetric)
    p = _lamina(lamina)
    props = {"E1": r["Ex"], "E2": r["Ey"], "E3": r["Ez"], "nu12": r["nuxy"], "nu13": r["nuxz"],
             "nu23": r["nuyz"], "G12": r["Gxy"], "G13": r["Gxz"], "G23": r["Gyz"],
             "cte1": r["alpha_x"], "cte2": r["alpha_y"], "cte3": r["alpha_z"]}
    for k in ("density", "cp", "Tg", "Tm", "T_process", "T_stress_free"):
        if p.get(k) is not None:
            props[k] = p[k]
    if "kx" in r:
        props.update(k1=r["kx"], k2=r["ky"], k3=r["kz"])
    notes = []
    if not r["symmetric"]:
        notes.append("unsymmetric layup: bending-extension coupling is lost in a smeared solid")
    if abs(r["alpha_xy"]) > 1e-9 or not r["balanced"]:
        notes.append("unbalanced layup: shear-extension coupling is lost in a smeared solid")
    return materials.Material(
        key=f"laminate_{p['_key']}", name=f"Smeared laminate of {p['_name']} "
        f"({r['n_plies']} plies, {r['thickness']:.3g} mm)", props=props, orthotropic=True,
        family="tp_composite", meta={"layup": r["angles"], "lamina": p["_key"],
                                     "thickness_mm": r["thickness"], "notes": notes})


@calc("composite.laminate", "Laminate stiffness and thermal expansion (classical laminate theory)",
      {"material": "text", "layup": "list", "ply_thickness": "length", "symmetric": "text",
       "dT": "temp_delta"},
      {"thickness": "length", "Ex": "pressure", "Ey": "pressure", "Gxy": "pressure",
       "nuxy": "ratio", "Efx": "pressure", "Efy": "pressure", "alpha_x": "cte", "alpha_y": "cte",
       "alpha_z": "cte", "Ez": "pressure", "nuxz": "ratio", "nuyz": "ratio",
       "ply_stress_fibre": "pressure", "ply_stress_transverse": "pressure",
       "ply_shear": "pressure", "transverse_strength_ratio": "ratio"},
      ["[N; M] = [A B; B D] [eps0; kappa]", "A_ij = sum Qbar_ij (z_k - z_k-1), etc.",
       "Ex = 1 / (h a11), nu_xy = -a12 / a11 with [a] = inverse ABD",
       "alpha = [abd] [N_T; M_T] per unit dT",
       "alpha_z from ply through-thickness strain under the in-plane constraint",
       "ply residual stress: sigma = Q (eps_ply - alpha_ply dT)"],
      "Jones, Mechanics of Composite Materials, 2nd ed., Ch. 4; Kaw, Mechanics of Composite Materials, Ch. 4",
      ["layup: list of angles in degrees or a string such as '[0/45/-45/90]2s'.",
       "dT = service temperature minus stress-free temperature (negative for cool-down); "
       "gives the worst ply residual stresses in material axes.",
       "Thin-laminate theory: no free-edge or interlaminar stresses."])
def laminate(material, layup, ply_thickness=None, symmetric=False, dT=None):
    sym = str(symmetric).lower() in ("true", "1", "yes")
    r = clt(material, layup, ply_thickness, sym, dT)
    out = {k: float(r[k]) for k in ("thickness", "Ex", "Ey", "Gxy", "nuxy", "Efx", "Efy",
                                    "alpha_x", "alpha_y", "alpha_z", "Ez", "nuxz", "nuyz")}
    notes = [f"{r['n_plies']} plies; symmetric: {r['symmetric']}; balanced: {r['balanced']}"]
    if not r["symmetric"]:
        k = r["kappa_per_K"]
        notes.append(f"Unsymmetric: thermal curvature kx={k[0]:.3e}, ky={k[1]:.3e} 1/mm per K (warpage).")
    if dT is not None:
        w = r["ply_residual"]
        out.update(ply_stress_fibre=w["s1"], ply_stress_transverse=w["s2"], ply_shear=w["t12"])
        p = _lamina(material)
        if p.get("Yt") and w["s2"] > 0:
            out["transverse_strength_ratio"] = p["Yt"] / w["s2"]
            if w["s2"] > p["Yt"]:
                notes.append("Transverse residual stress exceeds Yt: micro-cracking is likely.")
    return out, notes


@calc("composite.spring_in", "Process-induced spring-in of a curved laminate section",
      {"angle": "angle", "alpha_inplane": "cte", "alpha_thickness": "cte", "dT": "temp_delta",
       "shrinkage_inplane": "ratio", "shrinkage_thickness": "ratio", "flange": "length"},
      {"delta_angle": "angle", "thermal_part": "angle", "shrinkage_part": "angle",
       "tip_offset": "length"},
      ["d_theta = theta [ (a_I - a_T) dT / (1 + a_T dT) + (phi_I - phi_T) / (1 + phi_T) ]",
       "a_I, a_T = in-plane (circumferential) and through-thickness CTE",
       "phi_I, phi_T = in-plane and through-thickness crystallisation/cure shrinkage strains",
       "tip_offset ~ flange * d_theta (rad)"],
      "Radford & Rennick, J. Reinforced Plastics & Composites 19 (2000) 621; "
      "Nelson & Cairns, ICCM-7 (1989)",
      ["theta = arc angle swept by the bend, e.g. 90 deg for an L-section.",
       "dT = room temperature minus stress-free temperature (negative for cool-down). "
       "A positive d_theta means the arc angle grows, i.e. the flanges close ('spring-in').",
       "Geometric effect only; tool-part interaction and through-thickness gradients add to it."])
def spring_in(angle, alpha_inplane, alpha_thickness, dT, shrinkage_inplane=0.0,
              shrinkage_thickness=0.0, flange=None):
    th = (alpha_inplane - alpha_thickness) * dT / (1 + alpha_thickness * dT)
    sh = (shrinkage_inplane - shrinkage_thickness) / (1 + shrinkage_thickness)
    out = {"delta_angle": angle * (th + sh), "thermal_part": angle * th, "shrinkage_part": angle * sh}
    if flange:
        out["tip_offset"] = flange * math.radians(abs(out["delta_angle"]))
    return out


@calc("composite.consolidation_heatup", "Through-thickness heat-up or cool-down time of a laminate in a press or tool",
      {"material": "text", "thickness": "length", "T_initial": "temperature", "T_tool": "temperature",
       "T_target": "temperature", "h": "film", "one_sided": "text", "k": "conductivity",
       "density": "density", "cp": "specific_heat"},
      {"time_to_target": "time", "diffusivity": "area", "biot": "ratio",
       "mean_rate": "temp_rate"},
      ["Fo = alpha t / L^2, alpha = k3 / (rho c), L = half thickness (two-sided)",
       "centre temperature from the exact plane-wall series (see thermal.slab_transient)",
       "mean rate = |T_target - T_initial| / time"],
      "Incropera, Fundamentals of Heat and Mass Transfer, 7th ed., Sec. 5.5; "
      "Cogswell, Thermoplastic Aromatic Polymer Composites (1992), Ch. 5",
      ["Uses the through-thickness conductivity k3 of the lamina.",
       "Omit h for perfect tool contact (matched-die press). Add a contact/film coefficient "
       "for diaphragm or vacuum-bag processes.",
       "Latent heat of melting/crystallisation is not included."])
def consolidation_heatup(material, thickness, T_initial, T_tool, T_target, h=None, one_sided=False,
                         k=None, density=None, cp=None):
    m = materials.get(material)
    k = k or m.get("k3") or m.get("k")
    density = density or m.get("density")
    cp = cp or m.get("cp")
    r = slab_transient(k, density, cp, thickness, T_initial, T_tool, None, h, T_target, one_sided)
    out = {"diffusivity": r["diffusivity"]}
    if "biot" in r:
        out["biot"] = r["biot"]
    notes = []
    if "time_to_target" in r:
        out["time_to_target"] = r["time_to_target"]
        out["mean_rate"] = abs(T_target - T_initial) / r["time_to_target"]
    else:
        notes.append("T_target is not between the initial and tool temperatures.")
    return out, notes


# Recommended cooling-rate windows through crystallisation, K/min (typical supplier guidance).
COOLING_WINDOWS = {"peek": (5, 700), "pekk": (2, 60), "lmpaek": (5, 500), "pps": (10, 600),
                   "pp": (1, 600)}


@calc("composite.cooling_rate_check", "Cooling rate through the crystallisation range vs. the material window",
      {"material": "text", "rate": "temp_rate"},
      {"rate": "temp_rate", "rate_min": "temp_rate", "rate_max": "temp_rate", "ok": "ratio"},
      ["rate_min <= cooling rate <= rate_max for a stable, optimum degree of crystallinity"],
      "Cogswell, Thermoplastic Aromatic Polymer Composites (1992); supplier processing guides "
      "(typical values, confirm for the specific grade)",
      ["Too slow: coarse spherulites / high crystallinity and lower toughness. "
       "Too fast: amorphous skin, low crystallinity, lower stiffness and solvent resistance."])
def cooling_rate_check(material, rate):
    m = materials.get(material)
    fam = next((k for k in COOLING_WINDOWS if k in m.key), None)
    if fam is None:
        raise ValueError(f"no cooling-rate window stored for {m.key}; "
                         f"known polymers: {', '.join(COOLING_WINDOWS)}")
    lo, hi = (v / 60.0 for v in COOLING_WINDOWS[fam])
    ok = lo <= abs(rate) <= hi
    notes = [] if ok else [f"Cooling rate is {'below' if abs(rate) < lo else 'above'} the typical "
                           f"window for {fam.upper()}."]
    return {"rate": abs(rate), "rate_min": lo, "rate_max": hi, "ok": 1.0 if ok else 0.0}, notes
