"""Euler-Bernoulli beam formulas with optional Timoshenko shear deflection."""
from __future__ import annotations

import math

from . import calc
from .sections import section_from

_SEC_IN = {"I": "inertia", "c": "length", "A": "area", "b": "length", "h": "length",
           "d": "length", "D": "length", "t": "length", "tf": "length", "tw": "length"}
_IN = {"L": "length", "E": "pressure", "nu": "ratio", "x": "length", **_SEC_IN}
_OUT = {"deflection": "length", "deflection_bending": "length", "deflection_shear": "length",
        "moment": "moment", "stress": "pressure", "stress_at_x": "pressure",
        "shear_force": "force", "shear_stress_avg": "pressure", "slope": "angle",
        "I": "inertia", "reaction": "force"}
_REF = "Roark's Formulas for Stress and Strain, 8th ed., Table 8.1; Shigley's Mechanical " \
       "Engineering Design, 10th ed., Table A-9"


def _section(I, c, A, kw):
    shape = {k: v for k, v in kw.items() if v is not None}
    if set(shape) == {"D"}:                           # 'D=10' with no wall: a solid rod, as people write it
        shape = {"d": shape["D"]}
    if I is not None:
        return {"Ix": I, "cx": c, "A": A, "kappa": 5 / 6}
    s = section_from(shape)
    return s


def _finish(d_b, M, V, sec, E, nu, L, shear_coeff, slope=None, M_x=None, reaction=None):
    out = {"deflection_bending": d_b, "moment": M, "shear_force": V, "I": sec["Ix"]}
    d_s = 0.0
    if nu is not None and sec.get("A"):
        G = E / (2 * (1 + nu))
        d_s = shear_coeff / (sec.get("kappa", 5 / 6) * sec["A"] * G)
        out["deflection_shear"] = d_s
    out["deflection"] = d_b + d_s
    if sec.get("cx"):
        out["stress"] = M * sec["cx"] / sec["Ix"]
        if M_x is not None:
            out["stress_at_x"] = M_x * sec["cx"] / sec["Ix"]
    if sec.get("A"):
        out["shear_stress_avg"] = V / sec["A"]
    if slope is not None:
        out["slope"] = math.degrees(slope)
    if reaction is not None:
        out["reaction"] = reaction
    return out


def _beam(name, title, load_name, load_kind, formulas, fn):
    inputs = {load_name: load_kind, **_IN}

    @calc(name, title, inputs, _OUT, formulas + ["sigma = M c / I", "delta_shear = (shear term) / (kappa A G)"],
          _REF, ["Small deflection, linear elastic, plane sections remain plane.",
                 "Pass nu to include shear deflection (Timoshenko)."])
    def wrapped(L, E, I=None, c=None, A=None, b=None, h=None, d=None, D=None, t=None, tf=None,
                tw=None, nu=None, x=None, **load):
        sec = _section(I, c, A, dict(b=b, h=h, d=d, D=D, t=t, tf=tf, tw=tw))
        return fn(load[load_name], L, E, sec, nu, x)
    wrapped.__signature__ = _sig(load_name)
    return wrapped


def _sig(load_name):
    import inspect
    P = inspect.Parameter
    params = [P(load_name, P.POSITIONAL_OR_KEYWORD), P("L", P.POSITIONAL_OR_KEYWORD),
              P("E", P.POSITIONAL_OR_KEYWORD)]
    params += [P(k, P.POSITIONAL_OR_KEYWORD, default=None)
               for k in ("I", "c", "A", "b", "h", "d", "D", "t", "tf", "tw", "nu", "x")]
    return inspect.Signature(params)


cantilever_end_load = _beam(
    "beam.cantilever_end_load", "Cantilever, point load P at the free end", "P", "force",
    ["delta = P L^3 / (3 E I)", "M_max = P L (at the support)", "M(x) = P (L - x)", "theta = P L^2 / (2 E I)"],
    lambda P, L, E, s, nu, x: _finish(P * L**3 / (3 * E * s["Ix"]), P * L, P, s, E, nu, L, P * L,
                                      P * L**2 / (2 * E * s["Ix"]),
                                      P * (L - x) if x is not None else None, P))

cantilever_udl = _beam(
    "beam.cantilever_udl", "Cantilever, uniform load w per unit length", "w", "stiffness",
    ["delta = w L^4 / (8 E I)", "M_max = w L^2 / 2", "M(x) = w (L - x)^2 / 2", "theta = w L^3 / (6 E I)"],
    lambda w, L, E, s, nu, x: _finish(w * L**4 / (8 * E * s["Ix"]), w * L**2 / 2, w * L, s, E, nu, L,
                                      w * L**2 / 2, w * L**3 / (6 * E * s["Ix"]),
                                      w * (L - x)**2 / 2 if x is not None else None, w * L))

cantilever_end_moment = _beam(
    "beam.cantilever_end_moment", "Cantilever, moment M0 at the free end", "M0", "moment",
    ["delta = M0 L^2 / (2 E I)", "M = M0 (constant)", "theta = M0 L / (E I)"],
    lambda M0, L, E, s, nu, x: _finish(M0 * L**2 / (2 * E * s["Ix"]), M0, 0.0, s, E, None, L, 0.0,
                                       M0 * L / (E * s["Ix"]), M0 if x is not None else None))

simply_supported_center_load = _beam(
    "beam.simply_supported_center_load", "Simply supported, point load P at mid-span", "P", "force",
    ["delta = P L^3 / (48 E I)", "M_max = P L / 4", "theta = P L^2 / (16 E I)"],
    lambda P, L, E, s, nu, x: _finish(P * L**3 / (48 * E * s["Ix"]), P * L / 4, P / 2, s, E, nu, L,
                                      P * L / 4, P * L**2 / (16 * E * s["Ix"]),
                                      (P / 2 * min(x, L - x)) if x is not None else None, P / 2))

simply_supported_udl = _beam(
    "beam.simply_supported_udl", "Simply supported, uniform load w per unit length", "w", "stiffness",
    ["delta = 5 w L^4 / (384 E I)", "M_max = w L^2 / 8", "theta = w L^3 / (24 E I)"],
    lambda w, L, E, s, nu, x: _finish(5 * w * L**4 / (384 * E * s["Ix"]), w * L**2 / 8, w * L / 2, s,
                                      E, nu, L, w * L**2 / 8, w * L**3 / (24 * E * s["Ix"]),
                                      (w * x * (L - x) / 2) if x is not None else None, w * L / 2))

fixed_fixed_center_load = _beam(
    "beam.fixed_fixed_center_load", "Both ends fixed, point load P at mid-span", "P", "force",
    ["delta = P L^3 / (192 E I)", "M_max = P L / 8 (ends and centre)"],
    lambda P, L, E, s, nu, x: _finish(P * L**3 / (192 * E * s["Ix"]), P * L / 8, P / 2, s, E, nu, L,
                                      P * L / 4, None, None, P / 2))

fixed_fixed_udl = _beam(
    "beam.fixed_fixed_udl", "Both ends fixed, uniform load w per unit length", "w", "stiffness",
    ["delta = w L^4 / (384 E I)", "M_max = w L^2 / 12 (at the ends)", "M_centre = w L^2 / 24"],
    lambda w, L, E, s, nu, x: _finish(w * L**4 / (384 * E * s["Ix"]), w * L**2 / 12, w * L / 2, s, E,
                                      nu, L, w * L**2 / 8, None, None, w * L / 2))

_LAMBDA = {"cantilever": [1.875104, 4.694091, 7.854757],
           "simply_supported": [math.pi, 2 * math.pi, 3 * math.pi],
           "fixed_fixed": [4.730041, 7.853205, 10.995608],
           "free_free": [4.730041, 7.853205, 10.995608],
           "fixed_pinned": [3.926602, 7.068583, 10.210176]}


_SUPPORT_ALIASES = {"pinned_pinned": "simply_supported", "pinned": "simply_supported", "fixed_free": "cantilever",
                    "clamped_free": "cantilever", "clamped_clamped": "fixed_fixed", "clamped": "fixed_fixed"}

@calc("beam.natural_frequency", "Bending natural frequencies of a uniform beam",
      {"L": "length", "E": "pressure", "density": "density", "support": "text", **_SEC_IN},
      {"f1": "frequency", "f2": "frequency", "f3": "frequency"},
      ["f_n = (lambda_n^2 / (2 pi)) sqrt(E I / (rho A L^4))",
       "lambda: cantilever 1.8751, 4.6941, 7.8548; simply supported n pi; fixed-fixed 4.7300, 7.8532, 10.9956"],
      "Blevins, Formulas for Natural Frequency and Mode Shape, Table 8-1",
      ["Euler-Bernoulli beam; overestimates frequency for short, deep beams (L/h < 10)."])
def natural_frequency(L, E, density, support="cantilever", I=None, c=None, A=None, b=None, h=None,
                      d=None, D=None, t=None, tf=None, tw=None):
    s = _section(I, c, A, dict(b=b, h=h, d=d, D=D, t=t, tf=tf, tw=tw))
    key = str(support).lower().replace("-", "_").replace(" ", "_")
    key = _SUPPORT_ALIASES.get(key, key)            # the same words as a column's 'ends'
    if key not in _LAMBDA:
        raise ValueError(f"support must be one of {', '.join(_LAMBDA)}")
    base = math.sqrt(E * s["Ix"] / (density * s["A"] * L**4)) / (2 * math.pi)
    return {f"f{i + 1}": lam**2 * base for i, lam in enumerate(_LAMBDA[key])}


_K = {"fixed_free": 2.0, "pinned_pinned": 1.0, "fixed_pinned": 0.699, "fixed_fixed": 0.5}
_ENDS_ALIASES = {"simply_supported": "pinned_pinned", "pinned": "pinned_pinned", "cantilever": "fixed_free",
                 "clamped_free": "fixed_free", "clamped_clamped": "fixed_fixed", "clamped_pinned": "fixed_pinned"}


@calc("column.euler_buckling", "Elastic column buckling (Euler) with Johnson short-column check",
      {"L": "length", "E": "pressure", "ends": "text", "yield_strength": "pressure", **_SEC_IN},
      {"P_cr": "force", "stress_cr": "pressure", "slenderness": "ratio",
       "transition_slenderness": "ratio", "P_cr_johnson": "force"},
      ["P_cr = pi^2 E I / (K L)^2", "K: fixed-free 2, pinned-pinned 1, fixed-pinned 0.699, fixed-fixed 0.5",
       "Johnson (KL/r below transition): sigma_cr = Sy [1 - Sy (KL/r)^2 / (4 pi^2 E)]",
       "transition (KL/r)_1 = sqrt(2 pi^2 E / Sy)"],
      "Shigley's Mechanical Engineering Design, 10th ed., Sec. 4-12 and 4-13",
      ["Uses the smaller second moment when a section shape is given.",
       "Ideal straight column; real columns need an imperfection allowance."])
def euler_buckling(L, E, ends="pinned_pinned", yield_strength=None, I=None, c=None, A=None, b=None,
                   h=None, d=None, D=None, t=None, tf=None, tw=None):
    s = _section(I, c, A, dict(b=b, h=h, d=d, D=D, t=t, tf=tf, tw=tw))
    Imin = min(s["Ix"], s.get("Iy", s["Ix"]))
    key = str(ends).lower().replace("-", "_").replace(" ", "_")
    key = _ENDS_ALIASES.get(key, key)
    if key not in _K:
        raise ValueError(f"ends must be one of {', '.join(_K)}")
    K = _K[key]
    Pcr = math.pi**2 * E * Imin / (K * L)**2
    out = {"P_cr": Pcr}
    notes = []
    if s.get("A"):
        r = math.sqrt(Imin / s["A"])
        out["stress_cr"] = Pcr / s["A"]
        out["slenderness"] = K * L / r
        if yield_strength:
            tr = math.sqrt(2 * math.pi**2 * E / yield_strength)
            out["transition_slenderness"] = tr
            if out["slenderness"] < tr:
                sj = yield_strength * (1 - yield_strength * out["slenderness"]**2 / (4 * math.pi**2 * E))
                out["P_cr_johnson"] = sj * s["A"]
                notes.append("Slenderness is below the Euler/Johnson transition: the Johnson value "
                             "governs and elastic (eigenvalue) buckling over-predicts capacity.")
    return out, notes
