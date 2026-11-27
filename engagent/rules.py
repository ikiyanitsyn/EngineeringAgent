"""Read common requests straight from the user's words - no language model.

The free model on a GitHub runner is slow (minutes) and sometimes misreads a request. Most
everyday requests follow a few patterns ("steel bar 200 x 10 x 20 bolted to a wall at one end,
50 kg hanging from the free end"), so this module fills the same form the model would fill,
using plain rules. It returns None whenever it is not sure, and the model takes over.

The form then goes through exactly the same checks as a model's form (structured.build_request,
magnitudes_from_user, guard.check_request), so the rules cannot invent anything either.
"""
from __future__ import annotations

import re

from .guard import analysis_intent, material_from_words

NUM = r"(\d+(?:\.\d+)?)"
LEN_UNIT = r"\s*(mm|cm|millimet(?:er|re)s?|centimet(?:er|re)s?|met(?:er|re)s?|m|in|inch|inches|\"|')?"

TEMPLATE_WORDS = [  # order matters: more specific first
    ("phone_stand", r"phone stand|tablet stand|phone holder"),
    ("wall_hook", r"\bhook\b"),
    ("pipe_clamp", r"pipe clamp|pipe clip|tube clamp|saddle clamp"),
    ("lid", r"\blid\b"),
    ("enclosure", r"\b(enclosure|box|case|housing)\b"),
    ("l_bracket", r"l[- ]?bracket|angle bracket|\bbracket\b"),
    ("flange", r"\bflange\b"),
    ("standoff", r"\b(standoff|stand-off|spacer|washer|ring|bushing|bush|sleeve|tube|cylinder|disc|disk|puck|"
                 r"grommet|collar)\b"),
    ("plate", r"\b(plate|sheet|panel|block|cube|brick|tile|slab)\b"),
    ("beam", r"\b(beam|bar|rod|cantilever|joist|rail|column|strut|post)\b"),
]
PRINT_WORDS = r"3d[- ]?print|printable|\bprint\b|\bstl\b|\b3mf\b|filament|\bfdm\b"
# features the standard templates cannot make: such a request is a custom shape for the model, never a
# plain template that only matches its size (benchmark 018: a "cable comb ... plate" came out with no slots)
CUSTOM_RX = (r"\b(slots?|slotted|notch(?:es|ed)?|grooves?|cut-?outs?|pockets?|ribs?|tabs?|d-?shaped|d-?shaft|"
             r"knobs?|combs?|handles?|hinges?|latch(?:es)?|snap[- ]?fits?|gears?|pulleys?|engrav\w*|emboss\w*|"
             r"logos?|text|letters?|countersunk|counterbor\w*|chamfered|teeth|fingers?|dovetails?|keyways?|"
             r"hex|hexagon(?:al)?)\b")
PRINT_MATERIALS = ["petg", "pla", "abs", "asa", "pc", "nylon", "tpu", "pa12"]
FORCE_RX = NUM + r"\s*(kn|n|newtons?|kg|kgs|kilos?|kilograms?|lbf|lbs?|pounds?)(?![a-z])"
# an alloy number is not a pressure: "aluminium 6061 bar" is a bar of 6061, not 6061 bar
_ALLOY = "".join(f"(?<!{w} )" for w in ("aluminium", "aluminum", "al", "aa", "aisi", "sae", "steel", "alloy",
                                        "grade", "type", "en", "ss", "stainless"))
PRESSURE_RX = r"(?<![\d.])" + _ALLOY + NUM + r"\s*(mpa|kpa|bar|psi)(?![a-z])"
TEMP_RX = NUM + r"\s*(?:°\s*|deg(?:rees?)?\s*)?([cf])(?![a-z])"


def _mm(value: float, unit: str | None) -> float:
    unit = (unit or "mm").lower()
    unit = re.sub(r"^millimet(er|re)s?$", "mm", re.sub(r"^centimet(er|re)s?$", "cm", re.sub(r"^met(er|re)s?$", "m", unit)))
    return value * {"mm": 1, "cm": 10, "m": 1000, "in": 25.4, "inch": 25.4, "inches": 25.4, '"': 25.4,
                    "'": 304.8}.get(unit, 1)


def template_of(t: str) -> str | None:
    """The part the message is about: the template named first in the body (an issue title such as
    "shelf bracket bar" only counts when the body names none)."""
    lines = t.strip().split("\n", 1)
    body = lines[1] if len(lines) > 1 and re.match(r"\s*request\b", lines[0]) else t
    for text in (body, t):
        hits = []
        for rank, (name, rx) in enumerate(TEMPLATE_WORDS):
            m = re.search(rx, text)
            if m:
                hits.append((m.start(), rank, name))
        if hits:
            return min(hits)[2]
    return None


def clearance(m: int) -> float:
    """ISO 273 medium clearance hole for a metric screw Mm."""
    return {2: 2.4, 2.5: 2.9, 3: 3.4, 4: 4.5, 5: 5.5, 6: 6.6, 8: 9.0, 10: 11.0, 12: 13.5}.get(m, m * 1.1)


def dimensions(t: str, tmpl: str) -> dict:
    """Dimensions the user gave, in mm, keyed by the template's parameter names."""
    out: dict = {}
    triple = re.search(NUM + LEN_UNIT + r"\s*[x×*]\s*" + NUM + LEN_UNIT + r"\s*[x×*]\s*" + NUM + LEN_UNIT, t)
    if triple:
        g = triple.groups()
        unit = g[5] or g[3] or g[1]
        a, b, c = (_mm(float(g[i]), g[i + 1] or unit) for i in (0, 2, 4))
        keys = {"beam": ("length", "width", "height"), "plate": ("length", "width", "thickness"),
                "enclosure": ("length", "width", "height"), "lid": ("length", "width", "thickness")}.get(tmpl)
        if keys:
            out.update(zip(keys, (a, b, c)))
    if not triple and tmpl == "beam":                     # "40 x 80 mm (section)" = width x height
        two = re.search(NUM + LEN_UNIT + r"\s*[x×*]\s*" + NUM + LEN_UNIT + r"(?!\s*[x×*])", t)
        if two:
            g = two.groups()
            unit = g[3] or g[1]
            out["width"], out["height"] = _mm(float(g[0]), g[1] or unit), _mm(float(g[2]), g[3] or unit)
    words = {"long": "length", "length": "length", "wide": "width", "width": "width",
             "tall": "height", "high": "height", "height": "height", "deep": "height",
             "thick": "thickness", "thickness": "thickness"}
    for m in re.finditer(NUM + LEN_UNIT + r"\s*(long|wide|tall|high|deep|thick)\b", t):
        key = words[m.group(3)]
        if tmpl == "beam" and key == "thickness":
            key = "height"
        out.setdefault(key, _mm(float(m.group(1)), m.group(2)))
    for m in re.finditer(r"\b(length|width|height|thickness)\s*(?:of|=|:|is)?\s*" + NUM + LEN_UNIT, t):
        out.setdefault(m.group(1), _mm(float(m.group(2)), m.group(3)))
    if tmpl == "standoff":
        od = (re.search(NUM + LEN_UNIT + r"\s*(?:outer|outside|o\.?d\.?|od)\b", t)
              or re.search(r"\b(?:od|o\.d\.|outer diameter|outside diameter)\s*(?:of|=|:)?\s*" + NUM + LEN_UNIT, t)
              or re.search(NUM + LEN_UNIT + r"\s*(?:diameter|dia|wide|across)\b", t)
              or re.search(r"\b(?:diameter|dia)\s*(?:of|=|:)?\s*" + NUM + LEN_UNIT, t))
        if od:
            out["outer_diameter"] = _mm(float(od.group(1)), od.group(2))
        af = re.search(NUM + LEN_UNIT + r"\s*across\s*(?:the\s*)?flats", t)
        if af and re.search(r"\bhex", t):
            out["hex_af"] = _mm(float(af.group(1)), af.group(2))
        metric = re.search(r"\b(?:for )?(?:an? )?m(\d+)\b", t) if re.search(r"\bhex", t) else \
            re.search(r"\bfor (?:an? )?m(\d+)\b", t)
        bore = (re.search(NUM + LEN_UNIT + r"\s*(?:inner|inside|i\.?d\.?|id|hole|bore)\b", t)
                or re.search(r"\b(?:id|i\.d\.|inner diameter|inside diameter|hole|bore)\s*(?:of|=|:)?\s*" + NUM + LEN_UNIT, t))
        if bore:
            out["hole"] = _mm(float(bore.group(1)), bore.group(2))
        elif metric:
            out["hole"] = clearance(int(metric.group(1)))
        elif re.search(r"\b(disc|disk|puck|cylinder)\b", t):
            out["hole"] = 0.0
        if "length" in out or "thickness" in out:            # a tube's length / a washer's thickness
            out.setdefault("height", out.get("length") or out.get("thickness"))
        for k in ("length", "width", "thickness"):
            out.pop(k, None)
    if tmpl == "plate":
        cube = re.search(NUM + LEN_UNIT + r"\s*cube\b", t) or re.search(r"\bcube\s*(?:of)?\s*" + NUM + LEN_UNIT, t)
        if cube and not out:
            a = _mm(float(cube.group(1)), cube.group(2))
            out.update(length=a, width=a, thickness=a)
        out.pop("height", None)
        metric = re.search(r"\bm(\d+)\s*(?:screws?|bolts?|holes?)\b", t)
        plain = re.search(NUM + LEN_UNIT + r"\s*(?:mounting |screw |bolt |through[- ])?holes?\b", t)
        d = clearance(int(metric.group(1))) if metric else (_mm(float(plain.group(1)), plain.group(2)) if plain else None)
        if d:
            if re.search(r"\b(middle|centre|center)\b", t) and not re.search(r"\bcorners?\b", t):
                out["center_hole"] = d
            else:
                out["hole_diameter"] = d
    if tmpl == "l_bracket":                               # "two legs 40 mm long, 20 mm wide and 4 mm thick"
        leg = re.search(r"\blegs?\s*(?:of\s*|are\s*|each\s*)?" + NUM + LEN_UNIT, t) or \
            re.search(NUM + LEN_UNIT + r"\s*legs?\b", t)
        L = _mm(float(leg.group(1)), leg.group(2)) if leg else out.get("length")
        if L:
            out.setdefault("leg_x", L)
            out.setdefault("leg_z", L)
        out.pop("length", None)
        out.pop("height", None)
        hole = re.search(NUM + LEN_UNIT + r"\s*(?:mounting |screw |bolt |through[- ])?holes?\b", t)
        metric = re.search(r"\bm(\d+)\s*(?:screws?|bolts?|holes?)\b", t)
        if hole or metric:
            out["hole_diameter"] = clearance(int(metric.group(1))) if metric else _mm(float(hole.group(1)), hole.group(2))
            if re.search(r"\b(?:a|one)\s+(?:\d+(?:\.\d+)?\s*mm\s+)?holes?\b.*\beach leg\b", t):
                out["holes_per_leg"] = 1
    m = re.search(NUM + LEN_UNIT + r"\s*(?:thick\s+)?walls?\b", t) or re.search(r"\bwalls?\s*(?:of|=)?\s*" + NUM + LEN_UNIT, t)
    if m and tmpl in ("enclosure", "lid"):
        out["wall"] = _mm(float(m.group(1)), m.group(2))
    return out


def _direction(t: str) -> str | None:
    if re.search(r"\b(hang|hangs|hanging|weight|down|downward|downwards|sits?|resting|pushing|pushes|presses|"
                 r"standing|stands|load(?:ed)? on top|on top|on its top|along its top|drops?|droops?|sags?)\b", t):
        return "-z"
    if re.search(r"\b(up|upward|upwards|lifts?)\b", t):
        return "+z"
    return None


def _mechanical(t: str, tmpl: str, form: dict) -> dict | None:
    forces = re.findall(FORCE_RX, t)
    pressures = re.findall(PRESSURE_RX, t)
    if len(forces) + len(pressures) != 1:                # none, or several loads: let the model handle it
        return None
    if tmpl == "beam":
        if re.search(r"\bboth ends\b|\beach end\b|simply supported|\btwo supports\b|\bat each end\b", t):
            if re.search(SPREAD_RX, t):
                return None                              # a spread load on two supports: the model handles it
            return _simply_supported(t, form, forces)
        if not re.search(r"\b(one end|an end|cantilever|to a wall|into a wall|wall at|clamped at|fixed at|"
                         r"bolted at|welded at|built[- ]in)\b", t):
            return None
        if not re.search(r"\b(free end|the end|other end|its end|the tip|at the tip|end of)\b", t) and \
                not re.search(r"\bcantilever\b", t):         # a cantilever "loaded at one end" = at the tip
            return None
        if re.search(SPREAD_RX, t):                     # spread along the bar, not at the tip
            return _cantilever_udl(t, form, forces)
        fixed, face = ["xmin"], "xmax"
    elif tmpl == "plate":
        if re.search(r"\b(all|four|4) (edges|sides)\b|\ball round\b|\baround the edge", t):
            fixed = ["xmin", "xmax", "ymin", "ymax"]
        elif re.search(r"\b(one|a|the) long (edge|side)\b", t):
            fixed = ["ymin"]
        elif re.search(r"\b(one|a|the) (short )?(edge|side|end)\b", t):
            fixed = ["xmin"]
        else:
            return None
        if not re.search(r"\b(top|on the plate|on it|face|surface|pushing|pressure|load(?:ed)? on)\b", t):
            return None
        face = "zmax"
    else:
        return None
    if forces:
        mag, unit = forces[0]
        unit = {"n": "N", "newton": "N", "newtons": "N", "kn": "kN", "lbf": "lbf", "lb": "lb", "lbs": "lb",
                "pound": "lb", "pounds": "lb"}.get(unit, "kg")
        d = _direction(t) or ("-z" if unit in ("kg", "lb") else None)
        missing = []
        if tmpl == "beam" and not {"width", "height"} <= set(form["params"]):
            missing.append("the cross-section of the beam (width x height in mm, e.g. 20 x 40 mm, or a "
                           "standard section)")
        if not d:
            missing.append(f"the direction of the {mag} {unit} load (e.g. straight down, or along the beam)")
        if missing:                                    # never guess an analysis input: ask once, for all of it
            got = ", ".join(f"{k} {v:g} mm" for k, v in form["params"].items())
            return {"action": "question", "question":
                    "To run this analysis I still need: " + "; ".join(missing) + "."
                    + (f" (I have: {got}, {mag} {unit} at the free end, {material_from_words(t) or 'material'}.)"
                       if got else "") + " Reply in a comment and I will run it."}
        load = {"face": face, "kind": "force", "direction": d, "magnitude": float(mag), "unit": unit}
    else:
        mag, unit = pressures[0]
        load = {"face": face, "kind": "pressure", "direction": "-z", "magnitude": float(mag),
                "unit": {"mpa": "MPa", "kpa": "kPa", "bar": "bar", "psi": "psi"}[unit]}
    form.update(fixed_faces=fixed, loads=[load], analysis="static")
    return form


HOLLOW_RX = (r"\b(?:(square|rectangular|rect|box)[- ]?(?:tube|tubing|section|hollow section)|(round|circular)?[- ]?"
             r"(?:tube|tubing|pipe))\b")
WALL_RX = r"(\d+(?:\.\d+)?)\s*mm\s*(?:thick\s*)?wall|wall(?:\s*thickness)?(?:\s*of)?\s*(\d+(?:\.\d+)?)\s*mm"


def _hollow_cantilever(t: str, forces) -> dict | None:
    """A square / rectangular / round tube clamped at one end with a load at the free end, as a hollow beam
    with the tube's own section in the hand check (the round standoff template is not a tube beam)."""
    h = re.search(HOLLOW_RX, t)
    w = re.search(WALL_RX, t)
    L = re.search(NUM + r"\s*mm\s*long", t)
    if not (h and w and L and len(forces) == 1):
        return None
    if not re.search(r"\b(one end|clamped at|fixed at|to a wall|cantilever|bolted at|welded at)\b", t) or \
            not re.search(r"\b(free end|the end|other end|its end|the tip|end of)\b", t) or \
            re.search(r"\bboth ends\b|\beach end\b", t) or re.search(SPREAD_RX, t):
        return None
    wall, L = float(w.group(1) or w.group(2)), float(L.group(1))
    mag, unit = forces[0]
    from .structured import TO_N
    unit = {"n": "N", "newton": "N", "newtons": "N", "kn": "kN", "lbf": "lbf", "lb": "lb", "lbs": "lb",
            "pound": "lb", "pounds": "lb"}.get(unit, "kg")
    if (_direction(t) or ("-z" if unit in ("kg", "lb") else None)) != "-z":
        return None
    P = float(mag) * TO_N[unit]
    mat = material_from_words(t)
    if not mat:
        return None
    from . import materials
    nu = materials.get(mat).props.get("nu", 0.3)
    if h.group(1):                                    # square / rectangular: "40 x 40 mm" (or "40 mm square")
        two = re.search(NUM + r"\s*(?:mm)?\s*[x×*]\s*" + NUM + r"\s*mm", t)
        if not two:
            return None
        b, hh = float(two.group(1)), float(two.group(2))
        make = f"section=rect_tube width={b:g} height={hh:g} wall={wall:g}"
        sec = f"b={b:g} h={hh:g} t={wall:g}"
    else:
        d = re.search(NUM + r"\s*mm\s*(?:outside|outer|o\.?d\.?|diameter|dia)", t) or \
            re.search(r"(?:diameter|o\.?d\.?)\s*(?:of\s*)?" + NUM + r"\s*mm", t)
        if not d:
            return None
        D = float(d.group(1))
        make = f"section=tube width={D:g} height={D:g} wall={wall:g}"
        sec = f"D={D:g} t={wall:g}"
    req = (f'ea make beam length={L:g} {make} --name "tube cantilever"\n'
           f'ea analyze last -m {mat} --fix xmin --force xmax 0,0,{-P:g} '
           f'--check "beam.cantilever_end_load P={P:g} L={L:g} E={_E(mat)} nu={nu:g} {sec}"')
    return {"action": "raw", "request": req,
            "plan": "_A tube clamped at one end with the load at the free end, checked against the cantilever "
                    "formula with the tube's own section (Roark Table 8.1 case 1a, Table A.1)._"}


def _wall_convection(t: str) -> dict | None:
    """A flat wall / panel / plate: one face held at a temperature, the other cooled (or heated) by air with a
    film coefficient h. Steady 1-D conduction in series with convection (Incropera 3.1): a small patch of the
    wall is enough, since nothing varies along it."""
    if not re.search(r"\b(wall|panel|plate|sheet|slab|skin|lid)\b", t) or not re.search(r"\bfaces?\b|\bsides?\b", t):
        return None
    th = re.search(NUM + r"\s*mm\s*thick", t)
    temps = re.findall(TEMP_RX, t)
    h = re.search(r"\bh\s*(?:=|of|is)?\s*" + NUM, t)
    mat = material_from_words(t)
    if not (th and h and mat) or len(temps) != 2 or not re.search(r"\b(air|fluid|water|ambient|convect\w*|cooled|cooling)\b", t):
        return None
    if not re.search(r"\b(surface|face|outside|outer|cool|hot|temperature)\b", t):
        return None
    c = lambda v, u: (float(v) - 32) * 5 / 9 if u == "f" else float(v)          # noqa: E731
    # the face temperature comes first ("inside face at 60 C"), the air second ("air at 20 C")
    order = [(m.start(), m) for m in re.finditer(TEMP_RX, t)]
    air_at = re.search(r"\b(air|fluid|water|ambient)\b", t).start()
    face = min((m for _, m in order if m.start() < air_at), key=lambda m: air_at - m.start(), default=None)
    amb = next((m for _, m in order if m.start() > air_at), None)
    if not face or not amb:
        return None
    Tf, Ta = c(face.group(1), face.group(2)), c(amb.group(1), amb.group(2))
    T = float(th.group(1))
    hv = float(h.group(1))
    from . import materials
    k = materials.get(mat).props.get("k")
    if not k:
        return None
    side = max(10 * T, 20.0)                             # a patch; the answer does not depend on it
    req = (f'ea make plate length={side:g} width={side:g} thickness={T:g} --name "wall (patch)"\n'
           f'ea analyze last -a thermal -m {mat} --temp zmin {Tf:g} --convect zmax {hv:g} {Ta:g} '
           f'--check "thermal.wall_conduction_convection k={k:g} L={T:g} h={hv:g} T_fixed={Tf:g} T_ambient={Ta:g}"')
    return {"action": "raw", "request": req,
            "plan": f"_A {T:g} mm wall: one face at {Tf:g} C, the other cooled by air at {Ta:g} C (h = {hv:g}). "
                    "Heat flows straight through, so a small patch of the wall gives the answer; checked against "
                    "a plane wall with convection (Incropera 3.1)._"}


def _heated_plate(t: str) -> dict | None:
    """A plate carrying a heat load (an electronics module, a heater) cooled by air on every surface:
    steady energy balance T = T_air + Q / (h A_total), good when the plate conducts well (Bi << 1)."""
    q = re.search(NUM + r"\s*(?:w|watts?)\b", t)
    h = re.search(r"\bh\s*(?:=|of|is)?\s*" + NUM, t)
    tri = re.search(NUM + r"\s*(?:mm)?\s*[x×*]\s*" + NUM + r"\s*(?:mm)?\s*[x×*]\s*" + NUM + r"\s*mm", t)
    amb = re.search(r"\b(?:air|ambient)\b[^.]*?" + TEMP_RX, t) or re.search(TEMP_RX + r"[^.]*?\b(?:air|ambient)\b", t)
    mat = material_from_words(t)
    if not (q and h and tri and amb and mat) or not re.search(r"\b(plate|panel|sheet|block|heat ?spreader)\b", t):
        return None
    if not re.search(r"\b(every|all|each)\s+(surface|face|side)s?\b|\ball (?:round|over)\b", t):
        return None                                      # only some faces cooled: the model sets it up
    from . import materials
    k = materials.get(mat).props.get("k") or 0
    a, b, c = (float(tri.group(i)) for i in (1, 2, 3))
    T = min(a, b, c)
    if k < 10:                                           # a poor conductor is not uniform: not this simple case
        return None
    Q, hv = float(q.group(1)), float(h.group(1))
    Ta = float(amb.group(1)) if amb.group(2) != "f" else (float(amb.group(1)) - 32) * 5 / 9
    area = 2 * (a * b + b * c + a * c)
    req = (f'ea make plate length={a:g} width={b:g} thickness={c:g} --name "heated plate"\n'
           f'ea analyze last -a thermal -m {mat} --heat zmin {Q:g} --convect xmin+xmax+ymin+ymax+zmin+zmax {hv:g} {Ta:g} '
           f'--check "thermal.convection h={hv:g} A={area:g} T_ambient={Ta:g} heat_flow={Q:g} -> T_surface"')
    return {"action": "raw", "request": req, "derived": [area],
            "plan": f"_{Q:g} W into the plate, lost to air at {Ta:g} C (h = {hv:g}) from all {area:g} mm2 of its "
                    "surface; checked against the steady energy balance T = T_air + Q / (h A) (Incropera Eq. 1.3a), "
                    "which holds when the plate conducts well._"}


def _tri(t: str):
    m = re.search(NUM + r"\s*(?:mm)?\s*[x×*]\s*" + NUM + r"\s*(?:mm)?\s*[x×*]\s*" + NUM + r"\s*mm", t)
    return tuple(float(m.group(i)) for i in (1, 2, 3)) if m else None


def _plate_hole_tension(t: str) -> dict | None:
    """A plate with one central hole pulled lengthwise: Peterson's Kt for a hole in a finite-width plate. The
    peak at the hole edge is smooth (not a singularity), so the FEA reproduces it."""
    if not re.search(r"\bplate|strip|bar\b", t) or not re.search(r"\b(pulled|tension|tensile|stretched)\b", t):
        return None
    tri = _tri(t)
    hole = re.search(NUM + r"\s*mm\s*(?:diameter\s*)?(?:hole|bore)", t)
    forces = re.findall(FORCE_RX, t)
    mat = material_from_words(t)
    if not (tri and hole and len(forces) == 1 and mat) or not re.search(r"\b(centre|center|middle)\b", t):
        return None
    L, W, T = tri
    d = float(hole.group(1))
    from .structured import TO_N
    mag, unit = forces[0]
    unit = {"n": "N", "newton": "N", "newtons": "N", "kn": "kN", "lbf": "lbf", "lb": "lb", "lbs": "lb",
            "pound": "lb", "pounds": "lb"}.get(unit, "kg")
    P = float(mag) * TO_N[unit]
    req = (f'ea make plate length={L:g} width={W:g} thickness={T:g} center_hole={d:g} --name "plate with hole"\n'
           f'ea analyze last -m {mat} --slide xmin x --fix point:0,0,0 --slide point:0,{W:g},0 z '
           f'--force xmax {P:g},0,0 --check "kt.plate_hole_tension P={P:g} w={W:g} d={d:g} t={T:g}"')
    return {"action": "raw", "request": req,
            "plan": f"_The plate is pulled along its length with {P:g} N; the far end slides (held only along "
                    "the pull, plus two points against rigid motion), and the peak at the hole is checked against "
                    "Peterson's stress concentration factor._"}


def _pin_fin(t: str) -> dict | None:
    """A pin / rod sticking out of a hot (or cold) wall into air: a round fin, its base at the wall temperature,
    its sides and tip cooled by air (Incropera 3.6; the check uses the insulated-tip formula as a close bound)."""
    if not re.search(r"\b(pin|rod|fin|stud)\b", t) or not re.search(r"\b(sticking out|sticks out|protrud\w*|out of a wall|from a wall)\b", t):
        return None
    d = re.search(NUM + r"\s*mm\s*(?:in\s*)?(?:diameter|dia\b)", t)
    L = re.search(NUM + r"\s*mm\s*long", t)
    h = re.search(r"\bh\s*(?:=|of|is)?\s*" + NUM, t)
    temps = list(re.finditer(TEMP_RX, t))
    mat = material_from_words(t)
    if not (d and L and h and mat) or len(temps) != 2:
        return None
    air_at = re.search(r"\b(air|fluid|water|ambient|surround\w*)\b", t)
    if not air_at:
        return None
    wall = [m for m in temps if m.start() < air_at.start()]
    air = [m for m in temps if m.start() > air_at.start()]
    if len(wall) != 1 or len(air) != 1:
        return None
    c = lambda m: (float(m.group(1)) - 32) * 5 / 9 if m.group(2) == "f" else float(m.group(1))   # noqa: E731
    Tb, Ta = c(wall[0]), c(air[0])
    D, Lv, hv = float(d.group(1)), float(L.group(1)), float(h.group(1))
    from . import materials
    k = materials.get(mat).props.get("k")
    import math
    req = (f'ea make beam length={Lv:g} section=round width={D:g} height={D:g} --name "pin fin"\n'
           f'ea analyze last -a thermal -m {mat} --temp xmin {Tb:g} --convect cyl:{D / 2:g}+xmax {hv:g} {Ta:g} '
           f'--check "thermal.fin_straight k={k:g} h={hv:g} P={math.pi * D:.6g} A={math.pi * D * D / 4:.6g} L={Lv:g} '
           f'T_base={Tb:g} T_ambient={Ta:g} -> T_tip@min_temperature tol=0.03"')
    return {"action": "raw", "request": req, "derived": [math.pi * D, math.pi * D * D / 4],
            "plan": "_A round fin: its base at the wall temperature, its sides and tip cooled by the air. Checked "
                    "against the straight-fin formula (Incropera 3.6, insulated tip - a close estimate, the small "
                    "tip area is also cooled in the model)._"}


def _pressurised_tube(t: str) -> dict | None:
    """A thick-walled tube (pipe, cylinder) with internal pressure: Lame. Open ends unless the user says the
    ends are closed / capped (then the end-cap force is added as an axial pressure on the ends)."""
    if not re.search(r"\b(tube|pipe|cylinder|barrel)\b", t) or not re.search(r"\b(internal|inside|bore)\b", t):
        return None
    pr = re.findall(PRESSURE_RX, t)
    od = re.search(NUM + r"\s*mm\s*(?:outside|outer|o\.?d\.?)(?:\s*diameter)?", t)
    bore = re.search(NUM + r"\s*mm\s*(?:bore|inside diameter|inner diameter|i\.?d\.?)", t)
    L = re.search(NUM + r"\s*mm\s*long", t)
    mat = material_from_words(t)
    if len(pr) != 1 or not (od and bore and L and mat):
        return None
    from .structured import TO_MPA
    mag, unit = pr[0]
    p = float(mag) * TO_MPA[{"mpa": "MPa", "kpa": "kPa", "bar": "bar", "psi": "psi"}[unit]]
    ro, ri, Lv = float(od.group(1)) / 2, float(bore.group(1)) / 2, float(L.group(1))
    if ri >= ro:
        return None
    closed = bool(re.search(r"\b(closed|capped|sealed) ends?\b|\bends? (?:are )?(?:closed|capped|sealed)\b", t))
    ends = f" --pressure zmin+zmax {-p * ri * ri / (ro * ro - ri * ri):.6g}" if closed else ""
    req = ("```python\nfrom build123d import *\nfrom engagent.cad import save\na = (Align.CENTER, Align.CENTER, Align.MIN)\n"
           f"save(Cylinder({ro:g}, {Lv:g}, align=a) - Cylinder({ri:g}, {Lv:g}, align=a))\n```\n"
           f"```bash\nea make geometry.py --name \"pressurised tube\"\n"
           f"ea analyze last -m {mat} --slide zmin z --slide point:{ro:g},0,0 y --slide point:{-ro:g},0,0 y "
           f"--slide point:0,{ro:g},0 x "
           f"--pressure cyl:{ri:g} {p:.6g}{ends} "
           f"--check \"pressure.thick_cylinder p={p:.6g} ri={ri:g} ro={ro:g} -> von_mises_inner@max_von_mises\"\n```")
    return {"action": "raw", "request": req, "derived": [p] + ([p * ri * ri / (ro * ro - ri * ri)] if closed else []),
            "plan": f"_A tube {2 * ro:g} mm outside, {2 * ri:g} mm bore, {p:g} MPa inside, "
                    f"{'closed' if closed else 'open'} ends; one end slides on its plane and three points are held only around "
                    "the tube (so it can still grow), stopping rigid motion. "
                    "Checked against Lame's thick-cylinder solution (von Mises at the bore)._"}


def _free_expansion(t: str) -> dict | None:
    """A bar against a wall, otherwise free, heated evenly: it grows alpha L dT and stays stress free."""
    if not re.search(r"\b(against a wall|free to (?:grow|expand)|free end|freely)\b", t) or \
            not re.search(r"\b(heated|cooled|warmed)\b", t):
        return None
    tri = _tri(t)
    temps = re.findall(TEMP_RX, t)
    mat = material_from_words(t)
    if not (tri and mat) or len(temps) != 2 or re.search(r"\bboth ends\b|\beach end\b", t):
        return None
    c = lambda v, u: (float(v) - 32) * 5 / 9 if u == "f" else float(v)          # noqa: E731
    T0, T1 = c(*temps[0]), c(*temps[1])
    L, W, H = tri
    from . import materials
    cte = materials.get(mat).props.get("cte") * 1e6
    req = (f'ea make beam length={L:g} width={W:g} height={H:g} --name "bar"\n'
           f'ea analyze last -a thermal_stress -m {mat} --slide xmin x --fix point:0,0,0 --slide point:0,{W / 2:g},0 z '
           f'--t0 {T0:g} --dT {T1:g} --check "thermal.free_expansion L={L:g} cte={cte:g} dT={T1 - T0:g} '
           f'-> growth@max_displacement tol=0.03"')
    return {"action": "raw", "request": req,
            "plan": "_The bar rests against the wall at one end (held only along its length there, plus two points "
                    "against rigid motion) and is otherwise free, so it grows alpha L dT without stress._"}


def _round_plate(t: str) -> dict | None:
    """A flat round plate (disc, cover, diaphragm) under uniform pressure, its edge clamped or simply supported:
    Roark Table 11.2 cases 10a / 10b. None (-> the model) when anything is unclear."""
    pr = re.findall(PRESSURE_RX, t)
    d = re.search(NUM + r"\s*mm\s*(?:in\s*)?(?:diameter|dia\b|across)|(?:diameter|dia)\s*(?:of\s*)?" + NUM + r"\s*mm", t)
    th = re.search(NUM + r"\s*mm\s*thick|thickness\s*(?:of\s*)?" + NUM + r"\s*mm", t)
    mat = material_from_words(t)
    if len(pr) != 1 or not (d and th and mat):
        return None
    if re.search(r"\b(clamped|fixed|welded|bolted|built[- ]in)\b", t):
        edges = "clamped"
    elif re.search(r"simply supported|rests? on|resting on|sits? on|free to rotate|on a ledge", t):
        edges = "simply_supported"
    else:
        return None
    from .structured import TO_MPA
    mag, unit = pr[0]
    q = float(mag) * TO_MPA[{"mpa": "MPa", "kpa": "kPa", "bar": "bar", "psi": "psi"}[unit]]
    D, tk = float(d.group(1) or d.group(2)), float(th.group(1) or th.group(2))
    R = D / 2
    from . import materials
    nu = materials.get(mat).props.get("nu", 0.3)
    hold = (f"--fix cyl:{R:g}" if edges == "clamped" else
            f"--slide cyl:{R:g} z --slide point:0,0,0 x --slide point:0,0,0 y --slide point:{R:g},0,0 y")
    req = ("```python\nfrom build123d import *\nfrom engagent.cad import save\n"
           f"save(Cylinder({R:g}, {tk:g}, align=(Align.CENTER, Align.CENTER, Align.MIN)))\n```\n"
           f"```bash\nea make geometry.py --name \"round plate\"\n"
           f"ea analyze last -m {mat} {hold} --pressure zmax {q:.6g} "
           f"--check \"plate.circular_uniform q={q:.6g} r={R:g} t={tk:g} E={_E(mat)} nu={nu:g} edges={edges} -> deflection@max_displacement\"\n```")
    return {"action": "raw", "request": req, "derived": [q],
            "plan": f"_A {D:g} mm round plate, {tk:g} mm thick, {edges.replace('_', ' ')} at its edge, with "
                    f"{q:g} MPa on one face; checked against Roark Table 11.2 (case 10{'b' if edges == 'clamped' else 'a'})._"}


SPREAD_RX = r"\b(spread|evenly|uniform(?:ly)?|distributed|along (?:its|the) (?:whole |full )?(?:top|length))\b"


def _cantilever_udl(t: str, form: dict, forces) -> dict | None:
    """A cantilever with its load spread evenly along the top (a shelf of books): pressure on the top face,
    checked against Roark's uniformly loaded cantilever. A tip load here would overstate the drop 2.7x."""
    if len(forces) != 1:
        return None
    p = form["params"]
    if not {"length", "width", "height"} <= set(p):
        return {"action": "question", "question": "To run this analysis I still need: the bar's length and "
                "cross-section (width x thickness in mm). Reply in a comment and I will run it."}
    mag, unit = forces[0]
    from .structured import TO_N
    unit = {"n": "N", "newton": "N", "newtons": "N", "kn": "kN", "lbf": "lbf", "lb": "lb", "lbs": "lb",
            "pound": "lb", "pounds": "lb"}.get(unit, "kg")
    if (_direction(t) or ("-z" if unit in ("kg", "lb") else None)) != "-z":
        return None
    P = float(mag) * TO_N[unit]
    L, b, h = p["length"], p["width"], p["height"]
    mat = material_from_words(t)
    from . import materials
    nu = materials.get(mat).props.get("nu", 0.3)
    req = (f'ea make beam length={L:g} width={b:g} height={h:g} --name "cantilever, spread load"\n'
           f'ea analyze last -m {mat} --fix xmin --pressure zmax {P / (L * b):.6g} '
           f'--check "beam.cantilever_udl w={P / L:.6g} L={L:g} E={_E(mat)} nu={nu:g} b={b:g} h={h:g}"')
    return {"action": "raw", "request": req, "derived": [P / (L * b), P / L],
            "plan": f"_The {P:g} N is spread evenly along the top, so it is applied as a pressure "
                    f"({P / (L * b):.4g} MPa) on the top face, not at the tip; checked against the uniformly "
                    "loaded cantilever (Roark)._"}


def _simply_supported(t: str, form: dict, forces) -> dict | None:
    """A beam resting on supports at both ends with a load at the middle, modelled as HALF the beam:
    the mid-span face is a symmetry plane (cannot move along the beam) carrying half the load, and the
    far end is a simple support (held vertically only, free to rotate). Same mid-span deflection as the
    whole beam, with no point-load singularity, and a textbook hand check."""
    fixed = bool(re.search(r"\b(clamped|fixed|welded|built[- ]in|bolted|rigidly)\b", t))
    if not re.search(r"\b(middle|centre|center|mid-?span|halfway)\b", t) or len(forces) != 1:
        return None
    p = form["params"]
    mag, unit = forces[0]
    from .structured import TO_N
    unit = {"n": "N", "newton": "N", "newtons": "N", "kn": "kN", "lbf": "lbf", "lb": "lb", "lbs": "lb",
            "pound": "lb", "pounds": "lb"}.get(unit, "kg")
    d = _direction(t) or ("-z" if unit in ("kg", "lb") else None)
    missing = []
    if "length" not in p:
        missing.append("the beam's length (span between the supports)")
    if not {"width", "height"} <= set(p):
        missing.append("the beam's cross-section (width x height, e.g. 40 x 80 mm)")
    if d not in ("-z", "+z"):
        missing.append(f"the direction of the {mag} {unit} load (e.g. straight down)")
    if missing:
        return {"action": "question", "question": "To run this analysis I still need: " + "; ".join(missing)
                + ". Reply in a comment and I will run it."}
    P = float(mag) * TO_N[unit]
    sgn = -1 if d == "-z" else 1
    L, b, h = p["length"], p["width"], p["height"]
    from .guard import material_from_words
    mat = material_from_words(t)
    if fixed:                                            # both ends built in: the end face is held fully
        from . import materials
        nu = materials.get(mat).props.get("nu", 0.3)
        req = (f'ea make beam length={L / 2:g} width={b:g} height={h:g} --name "fixed-fixed beam (half, symmetry)"\n'
               f'ea analyze last -m {mat} --fix xmin --slide xmax x --force xmax 0,0,{sgn * P / 2:g} '
               f'--check "beam.fixed_fixed_center_load P={P:g} L={L:g} E={_E(mat)} nu={nu:g} b={b:g} h={h:g}"')
        return {"action": "raw", "request": req,
                "plan": "_Modelled as half the beam using symmetry: the mid-span face carries half the load and "
                        "cannot move along the beam (so it stays square, as at the middle of a fixed beam); the "
                        "end is held fully._"}
    req = (f'ea make beam length={L / 2:g} width={b:g} height={h:g} --name "simply supported beam (half, symmetry)"\n'
           f'ea analyze last -m {mat} --slide xmin z --slide xmax x --slide xmax y '
           f'--force xmax 0,0,{sgn * P / 2:g} '
           f'--check "beam.simply_supported_center_load P={P:g} L={L:g} E={_E(mat)} b={b:g} h={h:g}"')
    return {"action": "raw", "request": req,
            "plan": "_Modelled as half the beam using symmetry: the mid-span face carries half the load and "
                    "cannot move along the beam; the end support holds the beam up but lets it rotate._"}


def _E(mat: str) -> str:
    from . import materials
    try:
        return f'{materials.get(mat, "metric").get("E"):g}MPa'
    except Exception:
        return "210GPa"


def _thermal(t: str, tmpl: str, form: dict) -> dict | None:
    if tmpl != "beam":
        return None
    temps = [(float(v), u.upper()) for v, u in re.findall(TEMP_RX, t)]
    h = re.search(r"\bh\s*(?:=|of|is|:)?\s*" + NUM, t) or re.search(NUM + r"\s*w\s*/\s*\(?m", t)
    if len(temps) != 2 or not h:
        return None
    if not re.search(r"\b(end|ends)\b", t) or not re.search(r"\b(air|fluid|water|convect|cooled|ambient)\b", t):
        return None
    # the first temperature is the held end, the second the air (as people say it)
    held = re.search(r"(held|kept|fixed|maintained|is|at)\s+(?:at\s+)?" + TEMP_RX, t)
    air = re.search(r"(air|ambient|fluid|water)[^.;]*?" + TEMP_RX, t)
    if not held or not air:
        return None
    (tv, tu), (av, au) = (float(held.group(2)), held.group(3).upper()), (float(air.group(2)), air.group(3).upper())
    if (tv, tu) == (av, au):
        return None
    form.update(analysis="thermal", temperatures=[{"face": "xmin", "value": tv, "unit": tu}],
                convection=[{"face": "xmax", "h": float(h.group(1)), "ambient": av, "unit": au}])
    return form


def materials_in_order(user_text: str) -> list[str]:
    """Library materials named in the text, in the order they are mentioned."""
    from .guard import MATERIAL_MAP
    t = " " + user_text.lower() + " "
    hits = []
    for words, key in MATERIAL_MAP:
        pos = [t.find(w) for w in words if w in t]
        if pos:
            hits.append((min(pos), key))
    out = []
    for _, key in sorted(hits):
        if key not in out:
            out.append(key)
    return out


def _joined_bars(user_text: str, t: str) -> dict | None:
    """Two bars of different materials joined end to end, held at one end, pulled or pushed at the
    other: a tied two-part assembly with the series-stiffness hand check."""
    if not re.search(r"\b(joined|bonded|glued|welded|brazed|soldered|fused|attached)\b", t) or \
            not re.search(r"\bend[- ]to[- ]end\b", t):
        return None
    mats = materials_in_order(user_text)
    if len(mats) != 2:
        return None
    sec = re.search(NUM + LEN_UNIT + r"\s*[x×*]\s*" + NUM + LEN_UNIT + r"(?!\s*[x×*])", t)
    each = re.search(NUM + LEN_UNIT + r"\s*long each\b|\beach\s*" + NUM + LEN_UNIT + r"\s*long\b", t)
    if not sec or not each:
        return None
    b = _mm(float(sec.group(1)), sec.group(2) or sec.group(4))
    h = _mm(float(sec.group(3)), sec.group(4) or sec.group(2))
    g = [x for x in each.groups() if x is not None]
    L = _mm(float(g[0]), g[1] if len(g) > 1 else None)
    if not re.search(r"\b(one end|an end|fixed at|held at|clamped at|bolted at)\b", t):
        return None
    forces = re.findall(FORCE_RX, t)
    if len(forces) != 1:
        return None
    if re.search(r"\b(pull|pulled|pulling|tension|stretch)", t):
        sign = 1
    elif re.search(r"\b(push|pushed|pushing|compress)", t):
        sign = -1
    else:
        return None
    mag, unit = forces[0]
    from .structured import TO_N
    unit = {"n": "N", "newton": "N", "newtons": "N", "kn": "kN", "lbf": "lbf", "lb": "lb", "lbs": "lb",
            "pound": "lb", "pounds": "lb"}.get(unit, "kg")
    P = float(mag) * TO_N[unit]
    from . import materials
    E1, E2 = (materials.get(m, "metric").get("E") for m in mats)
    A = b * h
    delta = P * L / (A * E1) + P * L / (A * E2)
    names = [m.split("_")[0] for m in mats]
    if names[0] == names[1]:
        names = ["part1", "part2"]
    job = {
        "name": "joined-bars", "units": "metric", "analysis": "static",
        "title": f"{mats[0]} and {mats[1]} bars joined end to end",
        "parts": [
            {"name": names[0], "material": mats[0], "geometry": {
                "template": "beam", "params": {"length": L, "width": b, "height": h}, "step": f"{names[0]}.step"}},
            {"name": names[1], "material": mats[1], "geometry": {
                "template": "beam", "params": {"length": L, "width": b, "height": h}, "position": [L, 0, 0],
                "step": f"{names[1]}.step"}}],
        "sets": {"fixed": {"part": names[0], "plane": "x", "at": 0},
                 "joint_a": {"part": names[0], "plane": "x", "at": L},
                 "joint_b": {"part": names[1], "plane": "x", "at": L},
                 "tip": {"part": names[1], "plane": "x", "at": 2 * L}},
        "interactions": [{"type": "tie", "master": "joint_a", "slave": "joint_b"}],
        "constraints": [{"type": "fixed", "on": "fixed"}],
        "loads": [{"type": "force", "on": "tip", "value": [sign * P, 0, 0]}],
        "probes": {"tip": {"set": "tip"}},
        "hand_calcs": [{"name": "Series elongation P L1/(A E1) + P L2/(A E2)", "expected": f"{sign * delta:.6g} mm",
                        "kind": "length", "formula": "delta = P L1 / (A E1) + P L2 / (A E2)",
                        "metric": "probe.tip.ux", "tol": 0.03}]}
    return {"action": "job", "job": job, "name": "joined bars"}


def form_from_words(user_text: str, first: str | None = None) -> dict | None:
    """A complete form for a common request, or None when the rules are not sure.

    ``first`` is the original request of a conversation: the KIND of part comes from it only, so a
    follow-up comment ("the standoff you made was wrong") can add details but never change the part.
    """
    if first is not None and first.strip() != user_text.strip():
        f = " " + first.lower() + " "
        if not template_of(f) and not (analysis_intent(first) and _joined_bars(first, f)):
            return None                                  # the original request is not a rules case
    t = " " + user_text.lower().replace("×", "x") + " "
    if analysis_intent(user_text):
        joined = _joined_bars(user_text, t)
        if joined:
            return joined
    if analysis_intent(user_text):
        wall = _wall_convection(t) or _heated_plate(t) or _plate_hole_tension(t) or _pin_fin(t) or _free_expansion(t) or _pressurised_tube(t)
        if wall:
            return wall
    if analysis_intent(user_text) and re.findall(PRESSURE_RX, t) and re.search(
            r"\b(disc|disk|round plate|circular plate|round cover|circular cover|round lid|diaphragm)\b", t):
        return _round_plate(t)                           # a flat round plate under pressure (Roark 11.2)
    tmpl = template_of(" " + first.lower().replace("×", "x") + " ") if first else template_of(t)
    if not tmpl:
        return None
    whole = " " + (first or user_text).lower() + " "
    customs = {m.group(0) for m in re.finditer(CUSTOM_RX, whole)}
    hex_spacer = tmpl == "standoff" and customs and all(c.startswith("hex") for c in customs) and \
        re.search(r"across\s*(?:the\s*)?flats|\bA/?F\b", whole, re.I)
    if customs and not hex_spacer:
        return None                                      # a feature no template has: the model designs it
    word = re.search(dict(TEMPLATE_WORDS)[tmpl], t)
    name = word.group(0).strip() if word and tmpl in ("standoff", "plate", "enclosure", "beam") else tmpl.replace("_", " ")
    form: dict = {"template": tmpl, "params": dimensions(t, tmpl), "name": name}
    loaded = re.search(FORCE_RX, t) or re.search(PRESSURE_RX, t)
    wants_fea = analysis_intent(user_text) or bool(loaded and material_from_words(user_text) and re.search(
        r"\b(run|loaded|load|simulat\w*|check|calculate|what happens)\b", t))
    if wants_fea and tmpl in ("standoff", "beam") and re.search(HOLLOW_RX, t) and re.search(WALL_RX, t):
        tube = _hollow_cantilever(t, re.findall(FORCE_RX, t))
        if tube:
            return tube
        return None                                      # a tube we cannot set up surely: the model does it
    if not wants_fea:
        form["action"] = "make"
        pm = next((m for m in PRINT_MATERIALS if re.search(rf"\b{m}\b", t)), None)
        if pm or re.search(PRINT_WORDS, t):
            form["print_material"] = {"nylon": "pa12_sls", "pa12": "pa12_sls"}.get(pm, pm or "petg")
        return form
    if not material_from_words(user_text):
        return None                                    # the model (or the code) will ask
    form.update(action="analyze", material_words="")
    if tmpl == "beam":
        special = _restrained_heating(t, form) or _column(t, form) or _frequency(t, form)
        if special:
            return special
    thermal = re.search(r"\b(how hot|temperature|heat|cool|cooled|thermal|warm)\b", t)
    return _thermal(t, tmpl, form) if thermal else _mechanical(t, tmpl, form)


def _section(form) -> tuple[float, float, float] | None:
    p = form["params"]
    if {"length", "width", "height"} <= set(p):
        return p["length"], p["width"], p["height"]
    return None


def _restrained_heating(t: str, form: dict) -> dict | None:
    """A bar held rigidly at both ends and heated (or cooled) evenly from T1 to T2: sigma = E alpha dT."""
    if not re.search(r"\b(rigidly|both ends|each end|restrained|fixed at both|clamped at both|cannot expand)\b", t):
        return None
    m = re.search(r"from\s+" + NUM + r"\s*(?:°\s*|deg(?:rees?)?\s*)?([cf])\b\s*to\s+" + NUM
                  + r"\s*(?:°\s*|deg(?:rees?)?\s*)?([cf])\b", t)
    sec = _section(form)
    from .guard import material_from_words
    mat = material_from_words(t)
    if not m or not sec or not mat:
        return None
    c = lambda v, u: (float(v) - 32) * 5 / 9 if u == "f" else float(v)          # noqa: E731
    t0, t1 = c(m.group(1), m.group(2)), c(m.group(3), m.group(4))
    L, b, h = sec
    from . import materials
    mm = materials.get(mat, "metric")
    req = (f'ea make beam length={L:g} width={b:g} height={h:g} --name "restrained bar"\n'
           f'ea analyze last -m {mat} -a thermal_stress --slide xmin x --slide xmax x '
           f'--fix point:0,0,0 --fix point:{L:g},0,0 --slide point:0,{b:g},0 z --t0 {t0:g} --dT {t1:g} '
           f'--check "thermal.restrained_bar E={mm.get("E"):g}MPa cte={mm.get("cte") * 1e6:g} dT={t1 - t0:g} '
           f'-> stress@max_von_mises tol=0.03"')
    return {"action": "raw", "request": req,
            "plan": f"_Held at both ends and heated from {t0:g} to {t1:g} degC: the bar cannot grow, so it is "
                    f"squeezed; checked against sigma = E alpha dT._"}


def _frequency(t: str, form: dict) -> dict | None:
    """First bending frequency of a bar: clamped at one end (cantilever), on simple supports at both ends,
    or fixed at both ends. Two-support cases are HALF models with a symmetry plane at mid-span (the first mode
    is symmetric); faces are held, never single points in the bending direction (a point hold adds a false,
    mesh-dependent low mode - found in the 2026-11-26 toolkit check)."""
    if not re.search(r"\b(natural frequenc\w*|frequenc\w*|vibrat\w*|resonan\w*)\b", t):
        return None
    if re.findall(FORCE_RX, t) or re.findall(PRESSURE_RX, t):
        return None                                      # a load as well: not a plain frequency question
    sec = _section(form)
    from .guard import material_from_words
    mat = material_from_words(t)
    if not sec or not mat:
        return None
    L, b, h = sec
    both = re.search(r"\bboth ends\b|\beach end\b|\btwo supports\b|simply supported", t)
    fixed_words = re.search(r"\b(clamped|fixed|welded|built[- ]in|bolted|rigidly)\b", t)
    if both:
        kind = "fixed_fixed" if fixed_words and not re.search(r"simpl[ey]|rests?|resting|pinned", t) else \
            "simply_supported"
    elif re.search(r"\b(one end|cantilever|to a wall|clamped at|fixed at)\b", t):
        kind = "cantilever"
    else:
        return None
    from . import materials
    props = materials.get(mat).props
    rho = props["density"] * 1e12                         # t/mm^3 -> kg/m^3
    nu = props.get("nu", 0.3)
    weak_b, weak_h = max(b, h), min(b, h)                 # the first mode bends the thin way
    check = (f'--check "beam.natural_frequency L={L:g} E={_E(mat)} b={weak_b:g} h={weak_h:g} '
             f'density={rho:.6g} support={kind}"')
    if kind == "cantilever":
        req = (f'ea make beam length={L:g} width={b:g} height={h:g} --name "cantilever"\n'
               f'ea analyze last -a modal -m {mat} --fix xmin {check}')
        plan = "_Clamped at one end, first bending mode checked against Euler-Bernoulli beam theory._"
    else:
        end = "--fix xmin" if kind == "fixed_fixed" else "--slide xmin z --slide point:0,0,0 y"
        req = (f'ea make beam length={L / 2:g} width={b:g} height={h:g} --name "{kind.replace("_", " ")} bar (half)"\n'
               f'ea analyze last -a modal -m {mat} {end} --slide xmax x {check}')
        plan = ("_Half the bar by symmetry: the mid-span face cannot move along the bar; "
                + ("the end is held fully" if kind == "fixed_fixed" else "the end face is held vertically only, "
                   "free to rotate") + ". First bending mode checked against Euler-Bernoulli beam theory._")
    return {"action": "raw", "request": req, "plan": plan}


def _column(t: str, form: dict) -> dict | None:
    """A column pushed along its axis: Euler buckling with the end conditions the user named."""
    if not re.search(r"\b(column|strut|post|buckl\w*)\b", t):
        return None
    ends = None
    if re.search(r"fixed at the bottom and free at the top|fixed at one end and free|free at the top|cantilever(ed)? column", t):
        ends, sup = "fixed_free", "--fix xmin"
    elif re.search(r"pinned at both ends|pin-?ended|hinged at both ends", t):
        ends, sup = "pinned_pinned", None      # set below: true pins at the end centres (see there)
    forces = re.findall(FORCE_RX, t)
    sec = _section(form) or (None if "length" not in form["params"] else None)
    p = form["params"]
    if ends is None or len(forces) != 1:
        return None
    sq = re.search(NUM + LEN_UNIT + r"\s*[x×*]\s*" + NUM + LEN_UNIT + r"\s*(?:square|section|cross)", t)
    if "width" not in p and sq:
        p["width"], p["height"] = _mm(float(sq.group(1)), sq.group(2) or sq.group(4)), _mm(float(sq.group(3)), sq.group(4) or sq.group(2))
    sec = _section(form)
    from .guard import material_from_words
    mat = material_from_words(t)
    dia = re.search(NUM + r"\s*mm\s*(?:in\s*)?(?:diameter|dia\b)|(?:diameter|dia)\s*(?:of\s*)?" + NUM + r"\s*mm", t)
    Lm = re.search(NUM + r"\s*mm\s*long", t)
    if not sec and dia and Lm and re.search(r"\b(rod|bar|pin|shaft|round)\b", t) and not re.search(HOLLOW_RX, t):
        D = float(dia.group(1) or dia.group(2))       # a solid round rod
        sec = (float(Lm.group(1)), D, D)
        form["params"]["section_round"] = D
    if not sec or not mat:
        return None
    mag, unit = forces[0]
    from .structured import TO_N
    unit = {"n": "N", "newton": "N", "newtons": "N", "kn": "kN", "lbf": "lbf", "lb": "lb", "lbs": "lb",
            "pound": "lb", "pounds": "lb"}.get(unit, "kg")
    P = float(mag) * TO_N[unit]
    L, b, h = sec
    if sup is None:
        # holding a whole end face clamps it (a solid model has no rotation dofs): fixed-pinned, not pinned-pinned.
        # True pins: the end-face centres, plus one off-axis point so the column cannot spin about its axis.
        sup = (f"--pin point:0,0,0 --slide point:{L:g},0,0 y --slide point:{L:g},0,0 z "
               f"--slide point:0,{b / 2:g},0 z")
    from . import materials
    E = materials.get(mat, "metric").get("E")
    round_d = form["params"].get("section_round")
    shape = f"section=round width={b:g} height={b:g}" if round_d else f"width={b:g} height={h:g}"
    secin = f"D={b:g}" if round_d else f"b={b:g} h={h:g}"
    req = (f'ea make beam length={L:g} {shape} --name "column"\n'
           f'ea analyze last -m {mat} -a buckling {sup} --force xmax {-P:g},0,0 '
           f'--check "column.euler_buckling L={L:g} E={E:g}MPa {secin} ends={ends}"')
    return {"action": "raw", "request": req,
            "plan": f"_Column modelled along X ({ends.replace('_', '-')} ends), {P:g} N along its axis; the buckling "
                    f"factor is checked against Euler's formula._"}
