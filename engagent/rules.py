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
LEN_UNIT = r"\s*(mm|cm|m|in|inch|inches|\"|')?"

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
    ("beam", r"\b(beam|bar|rod|cantilever|joist|rail)\b"),
]
PRINT_WORDS = r"3d[- ]?print|printable|\bprint\b|\bstl\b|\b3mf\b|filament|\bfdm\b"
PRINT_MATERIALS = ["petg", "pla", "abs", "asa", "pc", "nylon", "tpu", "pa12"]
FORCE_RX = NUM + r"\s*(kn|n|newtons?|kg|kgs|kilos?|kilograms?|lbf|lbs?|pounds?)(?![a-z])"
PRESSURE_RX = NUM + r"\s*(mpa|kpa|bar|psi)(?![a-z])"
TEMP_RX = NUM + r"\s*(?:°\s*|deg(?:rees?)?\s*)?([cf])(?![a-z])"


def _mm(value: float, unit: str | None) -> float:
    unit = (unit or "mm").lower()
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
                 r"standing|stands|load(?:ed)? on top|on top)\b", t):
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
        if re.search(r"\bboth ends\b|\beach end\b", t):
            return None                                  # mid-span loads need a point selector: model/Claude
        if not re.search(r"\b(one end|an end|cantilever|to a wall|into a wall|wall at|clamped at|fixed at|"
                         r"bolted at|welded at|built[- ]in)\b", t):
            return None
        if not re.search(r"\b(free end|the end|other end|its end|the tip|at the tip|end of)\b", t):
            return None
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
        if not d:
            return None
        load = {"face": face, "kind": "force", "direction": d, "magnitude": float(mag), "unit": unit}
    else:
        mag, unit = pressures[0]
        load = {"face": face, "kind": "pressure", "direction": "-z", "magnitude": float(mag),
                "unit": {"mpa": "MPa", "kpa": "kPa", "bar": "bar", "psi": "psi"}[unit]}
    form.update(fixed_faces=fixed, loads=[load], analysis="static")
    return form


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


def form_from_words(user_text: str) -> dict | None:
    """A complete form for a common request, or None when the rules are not sure."""
    t = " " + user_text.lower().replace("×", "x") + " "
    tmpl = template_of(t)
    if not tmpl:
        return None
    word = re.search(dict(TEMPLATE_WORDS)[tmpl], t)
    name = word.group(0).strip() if word and tmpl in ("standoff", "plate", "enclosure", "beam") else tmpl.replace("_", " ")
    form: dict = {"template": tmpl, "params": dimensions(t, tmpl), "name": name}
    if not analysis_intent(user_text):
        form["action"] = "make"
        pm = next((m for m in PRINT_MATERIALS if re.search(rf"\b{m}\b", t)), None)
        if pm or re.search(PRINT_WORDS, t):
            form["print_material"] = {"nylon": "pa12_sls", "pa12": "pa12_sls"}.get(pm, pm or "petg")
        return form
    if not material_from_words(user_text):
        return None                                    # the model (or the code) will ask
    form.update(action="analyze", material_words="")
    thermal = re.search(r"\b(how hot|temperature|heat|cool|cooled|thermal|warm)\b", t)
    return _thermal(t, tmpl, form) if thermal else _mechanical(t, tmpl, form)
