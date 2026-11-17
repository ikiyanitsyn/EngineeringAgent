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

FACES = ["xmin", "xmax", "ymin", "ymax", "zmin", "zmax"]
DIRS = ["+x", "-x", "+y", "-y", "+z", "-z"]
UNITS = ["N", "kN", "kg", "lbf", "lb", "MPa", "kPa", "bar", "psi"]
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
        "face": {"enum": FACES}, "kind": {"enum": ["force", "pressure"]},
        "direction": {"enum": DIRS}, "magnitude": {"type": "number"}, "unit": {"enum": UNITS}},
        "required": ["face", "kind", "direction", "magnitude", "unit"]}
    return {"type": "object", "properties": {
        "action": {"enum": ["make", "analyze", "question"]},
        "question": {"type": "string"},
        "template": {"enum": list(templates.TEMPLATES)},
        "params": {"type": "object", "additionalProperties": {"type": "number"}},
        "name": {"type": "string"},
        "print_material": {"type": "string"},
        "material_words": {"type": "string"},
        "fixed_faces": {"type": "array", "items": {"enum": FACES}},
        "loads": {"type": "array", "items": load},
        "analysis": {"enum": ["static", "modal", "buckling"]}},
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
        "- 'fixed_faces': the faces that are bolted/clamped/held. 'loads.face': where the load acts.\n"
        "- For 3D printing set 'print_material' (pla, petg, abs, asa, pa12_sls, pc); default petg.\n"
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
    params = {k: v for k, v in (form.get("params") or {}).items() if k in defaults and isinstance(v, (int, float))}
    pstr = " ".join(f"{k}={v:g}" for k, v in params.items())
    name = re.sub(r'["\\]', "", str(form.get("name") or tmpl))[:40]
    if action == "make":
        pm = str(form.get("print_material") or "petg").lower()
        if pm not in materials.LIBRARY:
            pm = "petg"
        return f'ea make {tmpl} {pstr} --print {pm} --name "{name}"'.replace("  ", " "), None
    # analyze: material from the user's words (never from the model), loads converted here
    mat = material_from_words(user_text) or material_from_words(" " + str(form.get("material_words") or ""))
    missing = []
    if not mat:
        missing.append("the material")
    fixed = [f for f in form.get("fixed_faces") or [] if f in FACES]
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
             f"ea analyze last -m {mat} " + " ".join(f"--fix {f}" for f in dict.fromkeys(fixed))]
    for l in loads:
        unit, mag = l.get("unit"), float(l.get("magnitude") or 0)
        axis, sign = "xyz".index(l["direction"][1]), (-1 if l["direction"][0] == "-" else 1)
        if l.get("kind") == "pressure" and unit in TO_MPA:
            parts[-1] += f" --pressure {l['face']} {mag * TO_MPA[unit]:g}"
        elif unit in TO_N:
            vec = [0.0, 0.0, 0.0]
            vec[axis] = sign * mag * TO_N[unit]
            parts[-1] += f" --force {l['face']} " + ",".join(f"{v:g}" for v in vec)
        else:
            return None, f"Is the load of {mag:g} {unit} a force or a pressure? Please state it with its unit."
    analysis = form.get("analysis")
    if analysis in ("modal", "buckling"):
        parts[-1] += f" -a {analysis}"
    return "\n".join(parts), None


def magnitudes_from_user(form: dict, user_text: str) -> list[str]:
    """Loads whose magnitude the user never wrote (checked before converting units)."""
    from .guard import _numbers
    nums = _numbers(user_text)
    bad = []
    for l in form.get("loads") or []:
        try:
            m = abs(float(l.get("magnitude")))
        except (TypeError, ValueError):
            bad.append("a load without a number")
            continue
        if m and not any(abs(m - u) <= 0.01 * m for u in nums):
            bad.append(f"the load ({m:g} {l.get('unit')} was not in your message)")
    return bad


def parse_form(text: str) -> dict:
    text = text.strip()
    m = re.search(r"\{.*\}", text, re.S)
    try:
        return json.loads(m.group(0) if m else text)
    except ValueError:
        return {"action": "question", "question": "Sorry - could you describe the part and what you need again?"}
