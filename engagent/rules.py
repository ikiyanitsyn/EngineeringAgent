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
        metric = re.search(r"\bfor (?:an? )?m(\d+)\b", t)
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
    tmpl = template_of(" " + first.lower().replace("×", "x") + " ") if first else template_of(t)
    if not tmpl:
        return None
    if re.search(CUSTOM_RX, (" " + (first or user_text).lower() + " ")):
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
        special = _restrained_heating(t, form) or _column(t, form)
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
