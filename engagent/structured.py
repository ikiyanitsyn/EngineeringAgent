"""Structured extraction for small local models.

Small models (7B on a CPU) write command syntax badly but fill in a form reliably, and
Ollama can force the reply to follow a JSON schema. So for local models the model only
fills fields - template, dimensions, material, held faces, loads with the magnitude and unit
exactly as the user wrote them - and this module builds the `ea` commands itself.
"""
from __future__ import annotations

import json
import re

from . import materials
from .cad import templates
from .guard import material_from_words

FACES = ["xmin", "xmax", "ymin", "ymax", "zmin", "zmax", "sides"]   # sides = the long / curved side surface
DIRS = ["+x", "-x", "+y", "-y", "+z", "-z"]
UNITS = ["N", "kN", "kg", "lbf", "lb", "MPa", "kPa", "bar", "psi", "N*m", "lbf*in", "lbf*ft"]
TO_NM = {"N*m": 1.0, "lbf*in": 0.11298483, "lbf*ft": 1.3558179}
TO_N = {"N": 1.0, "kN": 1000.0, "kg": 9.80665, "lbf": 4.4482216, "lb": 4.4482216}
TO_MPA = {"MPa": 1.0, "kPa": 1e-3, "bar": 0.1, "psi": 0.0068947573}

FACE_HELP = {
    "beam": "bar along +X from x=0 to length; xmin and xmax are its two END faces (a load 'at the end', "
            "'at the tip' or 'on the free end' acts on xmax when xmin is held), zmax the top surface along "
            "the whole length, zmin the bottom",
    "plate": "flat plate on z=0; zmin is the bottom face, zmax the top, xmin/xmax/ymin/ymax the edges",
    "l_bracket": "base leg on z=0 along +X (zmin = underside of the base), upright leg at x=0 going up "
                 "(xmin = back of the upright)",
    "flange": "disc on z=0, axis along Z; zmin bottom face, zmax top face",
    "enclosure": "open box on z=0; zmin is the floor underside",
    "lid": "lid plate; zmax is the top face",
    "standoff": "round spacer on z=0 along Z; zmin and zmax are its ends",
    "pipe_clamp": "saddle clamp on z=0 (zmin = mounting face); the pipe runs along Y",
    "wall_hook": "back plate on z=0 against the wall (zmin = wall side); the hook arm points up +Z",
    "phone_stand": "stand on z=0 (zmin = the bottom resting on the table)",
    "curved_laminate": "curved composite section",
}


def schema() -> dict:
    load = {"type": "object", "properties": {
        "face": {"enum": FACES}, "kind": {"enum": ["force", "pressure", "torque"]},
        "direction": {"enum": DIRS}, "magnitude": {"type": "number"}, "unit": {"enum": UNITS}},
        "required": ["face", "kind", "direction", "magnitude", "unit"]}
    return {"type": "object", "properties": {
        "action": {"enum": ["make", "analyze", "question"]},
        "question": {"type": "string"},
        "template": {"enum": list(templates.TEMPLATES)},
        "params": {"type": "object", "additionalProperties": {"type": "number"}},
        "section": {"enum": ["rect", "round", "tube", "rect_tube", "i"]},
        "name": {"type": "string"},
        "print_material": {"type": "string"},
        "material_words": {"type": "string"},
        "fixed_faces": {"type": "array", "items": {"enum": FACES}},
        "loads": {"type": "array", "items": load},
        "temperatures": {"type": "array", "items": {"type": "object", "properties": {
            "face": {"enum": FACES}, "value": {"type": "number"}, "unit": {"enum": ["C", "F"]}},
            "required": ["face", "value", "unit"]}},
        "convection": {"type": "array", "items": {"type": "object", "properties": {
            "face": {"enum": FACES}, "h": {"type": "number"}, "ambient": {"type": "number"},
            "unit": {"enum": ["C", "F"]}}, "required": ["face", "h", "ambient", "unit"]}},
        "heat": {"type": "array", "items": {"type": "object", "properties": {
            "face": {"enum": FACES}, "watts": {"type": "number"}}, "required": ["face", "watts"]}},
        "temperature_change": {"type": "object", "properties": {
            "start": {"type": "number"}, "end": {"type": "number"}, "unit": {"enum": ["C", "F"]}},
            "required": ["start", "end", "unit"]},
        "analysis": {"enum": ["static", "modal", "buckling", "thermal", "thermal_stress"]}},
        "required": ["action"]}


def prompt() -> str:
    rows = []
    for t in templates.catalog():
        ps = ", ".join(f"{k}={v}" for k, v in t["parameters"].items())
        rows.append(f"- {t['name']}: {t['description']}. Faces: {FACE_HELP.get(t['name'], '')}.\n  parameters (mm): {ps}")
    return (
        "You turn an engineering request into a JSON form for a CAD and FEA tool. Reply with JSON only.\n"
        "action: 'make' = build a part (and 3D-print check), 'analyze' = build it and run a strength/stiffness "
        "analysis, 'question' = information is missing.\n"
        "RULES\n"
        "- For 'analyze' the user must have given: the material, where the part is held, and the load. If any is "
        "missing, use action 'question' and ask for exactly what is missing in 'question'.\n"
        "- Never invent numbers. 'magnitude' and 'unit' must be exactly what the user wrote (50 kg -> magnitude 50, "
        "unit 'kg'; 2 kN -> 2, 'kN'). A weight hanging down is kind 'force', direction '-z'.\n"
        "- 'material_words': copy the user's own words for the material (e.g. 'mild steel', 'aluminium 6061').\n"
        "- 'params': only dimensions the user gave, in mm (convert inches x 25.4). Leave others out.\n"
        "- 'fixed_faces': the faces that are bolted/clamped/held. 'loads.face': where the load acts.\n"        "- A beam that is a round rod or shaft: template 'beam', section 'round', params 'diameter' (and length). "
        "A twisting load (torque, N m) is kind 'torque' with unit 'N*m' and direction = its axis (a shaft along "
        "the beam is '+x').\n"
        "- Face 'sides' = the long side surface (all four sides of a bar, or the curved side of a round part); "
        "use it e.g. for air cooling along a pin or rod.\n"
        "- For 3D printing set 'print_material' (pla, petg, abs, asa, pa12_sls, pc); default petg.\n"
        "- Heat questions (how hot, temperature, cooling): analysis 'thermal'; 'temperatures' = faces held at a "
        "temperature, 'convection' = faces cooled by air/fluid (h in W/m2K and ambient temperature), 'heat' = "
        "watts put into a face. No 'loads' or 'fixed_faces' needed.\n"
        "- Thermal stress/expansion from heating or cooling the whole part: analysis 'thermal_stress', "
        "'temperature_change' start/end, plus 'fixed_faces'.\n"
        "TEMPLATES\n" + "\n".join(rows) + "\n"
        "EXAMPLE (values are only an example): 'aluminium plate 100 x 60 x 4, clamped along one short edge, "
        "2 kg pushing down on the top' -> {\"action\": \"analyze\", \"template\": \"plate\", \"params\": "
        "{\"length\": 100, \"width\": 60, \"thickness\": 4}, \"material_words\": \"aluminium\", \"fixed_faces\": "
        "[\"xmin\"], \"loads\": [{\"face\": \"zmax\", \"kind\": \"force\", \"direction\": \"-z\", \"magnitude\": 2, "
        "\"unit\": \"kg\"}]}\n")


def build_request(form: dict, user_text: str) -> tuple[str | None, str | None]:
    """(request text, question).  Exactly one is set."""
    action = form.get("action")
    if action == "question" or action not in ("make", "analyze"):
        return None, form.get("question") or "What exactly should I make or analyse?"
    tmpl = form.get("template")
    if tmpl not in templates.TEMPLATES:
        return None, ("Which kind of part is it? I can build: " + ", ".join(templates.TEMPLATES)
                      + ". (For other shapes, add a Gemini key or use Claude.)")
    defaults = templates.TEMPLATES[tmpl][1]
    raw = form.get("params") or {}
    params = {k: v for k, v in raw.items() if k in defaults and isinstance(v, (int, float))}
    if tmpl == "beam":
        d = raw.get("diameter") if isinstance(raw.get("diameter"), (int, float)) else None
        section = form.get("section") if form.get("section") in ("rect", "round", "tube", "rect_tube", "i") else None
        if d and not section:
            section = "round"
        if section in ("round", "tube") and d:
            params["width"] = params["height"] = float(d)
        if section and section != "rect":
            params["section"] = section
    if tmpl == "standoff" and params.get("hole", 0) >= params.get("outer_diameter", defaults["outer_diameter"]):
        params["hole"] = 0                       # a hole as wide as the part leaves nothing: a solid rod was meant
    form["_sides"] = _sides_selector(tmpl, {**{k: v for k, v in defaults.items()}, **params})
    pstr = " ".join(f"{k}={v:g}" if isinstance(v, (int, float)) else f"{k}={v}" for k, v in params.items())
    name = re.sub(r'["\\]', "", str(form.get("name") or tmpl))[:40]
    if action == "make":                     # the 3D-print check only when printing was asked for
        pm = str(form.get("print_material") or "").lower()
        if pm and pm not in materials.LIBRARY:
            pm = "petg"
        pr = f" --print {pm}" if pm else ""
        return f'ea make {tmpl} {pstr}{pr} --name "{name}"'.replace("  ", " "), None
    # analyze: material from the user's words (never from the model), loads converted here
    mat = material_from_words(user_text) or material_from_words(" " + str(form.get("material_words") or ""))
    missing = []
    if not mat:
        missing.append("the material")
    fixed = [f for f in form.get("fixed_faces") or [] if f in FACES]
    analysis = form.get("analysis")
    if analysis == "thermal":
        return _thermal_request(form, tmpl, pstr, name, mat, missing)
    if analysis == "thermal_stress":
        return _thermal_stress_request(form, tmpl, pstr, name, mat, missing, fixed)
    if not fixed:
        missing.append("where the part is held (bolted, clamped)")
    loads = [l for l in form.get("loads") or [] if isinstance(l, dict)]
    if not loads:
        missing.append("the load (size, direction and where it acts)")
    if missing:
        return None, ("To run the analysis I still need: " + "; ".join(missing)
                      + ". Please reply with those - I will not guess them.")
    notes = []
    t = user_text.lower()
    if tmpl == "beam" and re.search(r"\b(free end|at the end|on the end|end of|the tip|at the tip|tip load)\b", t):
        ends = [f for f in fixed if f in ("xmin", "xmax")]
        if ends:
            free = "xmax" if ends[0] == "xmin" else "xmin"
            for l in loads:
                if l.get("face") not in ("xmin", "xmax"):
                    notes.append(f"load placed on the free end ({free}) because you said it acts at the end "
                                 f"(the AI had put it on {l.get('face')})")
                    l["face"] = free
    form["_notes"] = notes
    parts = [f"ea make {tmpl} {pstr} --name \"{name}\"".replace("  ", " "),
             f"ea analyze last -m {mat} " + " ".join(f"--fix {_face(form, f)}" for f in dict.fromkeys(fixed))]
    for l in loads:
        unit, mag = l.get("unit"), float(l.get("magnitude") or 0)
        axis, sign = "xyz".index(l["direction"][1]), (-1 if l["direction"][0] == "-" else 1)
        if l.get("kind") == "torque" or unit in TO_NM:
            if unit not in TO_NM:
                return None, f"Is the {mag:g} {unit} a torque? Please give it in N m or lbf ft."
            vec = [0.0, 0.0, 0.0]
            vec[axis] = sign * mag * TO_NM[unit]
            parts[-1] += f" --moment {_face(form, l['face'])} " + ",".join(f"{v:g}" for v in vec)
        elif l.get("kind") == "pressure" and unit in TO_MPA:
            parts[-1] += f" --pressure {_face(form, l['face'])} {mag * TO_MPA[unit]:g}"
        elif unit in TO_N:
            vec = [0.0, 0.0, 0.0]
            vec[axis] = sign * mag * TO_N[unit]
            parts[-1] += f" --force {_face(form, l['face'])} " + ",".join(f"{v:g}" for v in vec)
        else:
            return None, f"Is the load of {mag:g} {unit} a force or a pressure? Please state it with its unit."
    if analysis in ("modal", "buckling"):
        parts[-1] += f" -a {analysis}"
    return "\n".join(parts), None


def _sides_selector(tmpl: str, p: dict) -> str:
    """The 'sides' face of a template as a selector: the curved side of a round part, the 4 long faces of a bar."""
    if tmpl == "standoff":
        return f"cyl:{float(p.get('outer_diameter', 10)) / 2:g}"
    if tmpl == "beam" and p.get("section") in ("round", "tube"):
        return f"cyl:{float(p.get('width', 10)) / 2:g}"
    if tmpl == "beam":
        return "ymin+ymax+zmin+zmax"
    if tmpl == "flange":
        return f"cyl:{float(p.get('outer_diameter', p.get('diameter', 100))) / 2:g}"
    return "xmin+xmax+ymin+ymax"


def _face(form: dict, face: str) -> str:
    return form.get("_sides", "xmin+xmax+ymin+ymax") if face == "sides" else face


def _degc(v, unit) -> float:
    return (float(v) - 32) * 5 / 9 if unit == "F" else float(v)


def _ask_missing(missing):
    return None, ("To run the analysis I still need: " + "; ".join(missing)
                  + ". Please reply with those - I will not guess them.")


def _thermal_request(form, tmpl, pstr, name, mat, missing):
    temps = [t for t in form.get("temperatures") or [] if isinstance(t, dict) and t.get("face") in FACES]
    conv = [c for c in form.get("convection") or [] if isinstance(c, dict) and c.get("face") in FACES]
    heat = [h for h in form.get("heat") or [] if isinstance(h, dict) and h.get("face") in FACES]
    if not temps and not heat:
        missing.append("what heats the part (a face held at a temperature, or the watts put in)")
    if not temps and not conv:
        missing.append("how the heat leaves (a face held at a temperature, or air cooling with h and the air temperature)")
    if missing:
        return _ask_missing(missing)
    line = f"ea analyze last -m {mat} -a thermal"
    line += "".join(f" --temp {_face(form, t['face'])} {_degc(t['value'], t.get('unit')):g}" for t in temps)
    line += "".join(f" --convect {_face(form, c['face'])} {float(c['h']):g} {_degc(c['ambient'], c.get('unit')):g}"
                    for c in conv)
    line += "".join(f" --heat {_face(form, h['face'])} {float(h['watts']):g}" for h in heat)
    return f'ea make {tmpl} {pstr} --name "{name}"'.replace("  ", " ") + "\n" + line, None


def _thermal_stress_request(form, tmpl, pstr, name, mat, missing, fixed):
    tc = form.get("temperature_change") if isinstance(form.get("temperature_change"), dict) else {}
    if not fixed:
        missing.append("where the part is held (bolted, clamped)")
    if "start" not in tc or "end" not in tc:
        missing.append("the starting and final temperature")
    if missing:
        return _ask_missing(missing)
    line = (f"ea analyze last -m {mat} -a thermal_stress " + " ".join(f"--fix {f}" for f in dict.fromkeys(fixed))
            + f" --t0 {_degc(tc['start'], tc.get('unit')):g} --dT {_degc(tc['end'], tc.get('unit')):g}")
    return f'ea make {tmpl} {pstr} --name "{name}"'.replace("  ", " ") + "\n" + line, None


_UNIT_WORDS = {   # what the user may write after a number, per form unit / quantity
    "force": r"n|newtons?|kn|kilonewtons?|lbf|lbs?|pounds?|kg|kgs|kilos?|kilograms?",
    "pressure": r"mpa|kpa|pa|bar|psi|ksi|atm",
    "temperature": r"°\s*[cf]|deg(?:rees?)?\s*[cf]?|[cf]|celsius|fahrenheit",
    "power": r"w|watts?|kw|mw",
}
_FORM_KIND = {"N": "force", "kN": "force", "kg": "force", "lbf": "force", "lb": "force",
              "MPa": "pressure", "kPa": "pressure", "bar": "pressure", "psi": "pressure"}


def _written_with_unit(value: float, user_text: str, kind: str) -> bool:
    """The user wrote this number followed by a unit of this kind (e.g. '50 kg', '100 C')."""
    rx = r"(-?\d+(?:[.,]\d+)?)\s*(?:" + _UNIT_WORDS[kind] + r")(?![a-z])"
    for m in re.finditer(rx, user_text.lower()):
        u = float(m.group(1).replace(",", "."))
        if abs(abs(u) - abs(value)) <= 0.01 * max(abs(value), 1e-9):
            return True
    return False


def magnitudes_from_user(form: dict, user_text: str) -> list[str]:
    """Values the user never wrote, or wrote as a different kind of quantity (e.g. a temperature
    read as a mass). Checked before converting units."""
    from .guard import _numbers
    nums = _numbers(user_text)
    bad = []
    for l in form.get("loads") or []:
        try:
            m = abs(float(l.get("magnitude")))
        except (TypeError, ValueError):
            bad.append("a load without a number")
            continue
        kind = "pressure" if l.get("kind") == "pressure" else _FORM_KIND.get(l.get("unit"), "force")
        if m and not _written_with_unit(m, user_text, kind):
            bad.append(f"the load ({m:g} {l.get('unit')} - your message does not give a {kind} of that size)")
    temps = [("temperature", t.get("value")) for t in form.get("temperatures") or [] if isinstance(t, dict)]
    for c in form.get("convection") or []:
        if isinstance(c, dict):
            temps.append(("air temperature", c.get("ambient")))
            try:
                h = abs(float(c.get("h")))
                if h and not any(abs(h - abs(u)) <= 0.01 * h for u in nums):
                    bad.append(f"the convection coefficient h ({h:g} was not in your message)")
            except (TypeError, ValueError):
                bad.append("the convection coefficient h")
    tc = form.get("temperature_change")
    if isinstance(tc, dict):
        temps += [("starting temperature", tc.get("start")), ("final temperature", tc.get("end"))]
    for label, v in temps:
        try:
            m = float(v)
        except (TypeError, ValueError):
            bad.append(f"the {label}")
            continue
        if not _written_with_unit(m, user_text, "temperature"):
            bad.append(f"the {label} ({m:g} - not a temperature in your message)")
    for h in form.get("heat") or []:
        if isinstance(h, dict):
            try:
                w = abs(float(h.get("watts")))
            except (TypeError, ValueError):
                bad.append("the heat input")
                continue
            if w and not _written_with_unit(w, user_text, "power"):
                bad.append(f"the heat input ({w:g} W was not in your message)")
    return bad


def parse_form(text: str) -> dict:
    text = text.strip()
    m = re.search(r"\{.*\}", text, re.S)
    try:
        return json.loads(m.group(0) if m else text)
    except ValueError:
        return {"action": "question", "question": "Sorry - could you describe the part and what you need again?"}
