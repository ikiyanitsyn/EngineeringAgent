"""Guard against invented analysis inputs.

A language model (especially a small one) may fill in a material or a load the user never
gave - for example by copying an example from its instructions. Analysis results built on
invented inputs look authoritative and are dangerous, so before any analysis runs, every
material and load value in the request must be traceable to something the user wrote.
Anything that is not becomes a question back to the user instead of a result.

CAD dimensions are deliberately not checked: choosing sensible defaults for a part's shape
is wanted behaviour.
"""
from __future__ import annotations

import json
import re
import shlex

from . import materials

G = 9.80665
# words a user may write for each material family / key fragment
WORDS = {
    "steel": ("steel", "s235", "s355", "a36", "1045", "4140", "mild", "carbon steel"),
    "stainless": ("stainless", "304", "316", "inox"),
    "al_": ("alumin", "6061", "7075", "5052", "alu", "mic-6", "mic6"),
    "aluminium": ("alumin", "6061", "7075", "5052", "alu"),
    "ti_": ("titan", "ti-6", "ti6", "grade 5"),
    "titanium": ("titan",),
    "brass": ("brass",),
    "copper": ("copper",),
    "pla": ("pla",), "petg": ("petg", "pet-g"), "abs": ("abs",), "asa": ("asa",),
    "pa12": ("pa12", "nylon", "sls", "mjf"), "pa6": ("pa6", "nylon", "carbon fibre nylon", "cf nylon"),
    "pc": ("polycarbonate", " pc"), "resin": ("resin", "sla"),
    "peek": ("peek",), "pekk": ("pekk",), "lmpaek": ("paek",), "pps": ("pps",), "pei": ("pei", "ultem"),
    "pp": ("polypropylene", " pp"), "cf_": ("carbon", "cf/", "cfrp", "composite", "laminate"),
    "gf_": ("glass", "gf/", "gfrp"), "invar": ("invar",), "tool_steel": ("tool steel", "p20"),
}
LOAD_FLAGS = {"--force": "force", "--pressure": "pressure", "--moment": "moment", "--heat": "heat",
              "--temp": "temperature", "--convect": "convection", "--dT": "temperature", "--gravity": "gravity"}


def _numbers(text: str) -> list[float]:
    return [abs(float(x)) for x in re.findall(r"(?<![\w.])-?\d+(?:\.\d+)?(?:[eE][-+]?\d+)?", text.replace(",", " "))
            if x not in ("",)]


FACTORS = {   # user number x factor = value written in the request (per kind of quantity)
    "force": (1, G, 1000, 4.4482216, 0.45359237 * G, 1000 * G, 4448.2216),       # N, kg, kN, lbf, lb, t, kip
    "pressure": (1, 1e-3, 0.1, 1000, 0.0068947573, 6.8947573, 0.101325),       # MPa, kPa, bar, GPa, psi, ksi, atm
    "moment": (1, 1000, 1e-3, 0.11298483, 1.3558179, 112.98483, 1355.8179),     # N*m <-> N*mm, lbf*in, lbf*ft
    "heat": (1, 1e-3, 1000, 0.29307107),                                        # W, mW, kW, BTU/hr
    "temperature": (1,),
    "convection": (1, 1e-3, 5.6782633),                                          # W/m2K, BTU/hr/ft2/F
}


def _supported_number(v: float, user_nums: list[float], kind: str = "force") -> bool:
    """v (as written in the request) matches a user number directly or via a unit conversion
    that makes sense for this kind of quantity."""
    if v == 0:
        return True
    for u in user_nums:
        for f in FACTORS.get(kind, (1,)):
            if abs(v - u * f) <= 0.01 * abs(v):
                return True
        if kind in ("temperature", "convection") and abs(v - (u - 32) * 5 / 9) <= 0.01 * max(abs(v), 1):
            return True                                                       # degF -> degC
    return False


def _material_supported(spec: str, user_text: str) -> bool:
    t = " " + user_text.lower() + " "
    spec = spec.strip()
    if spec.startswith("{"):                      # explicit properties: numbers must come from the user
        try:
            props = json.loads(spec)
        except ValueError:
            return False
        nums = _numbers(user_text)
        vals = [abs(float(re.match(r"-?[\d.eE+-]+", str(v)).group())) for v in props.values()
                if re.match(r"-?[\d.eE+-]+", str(v))]
        return all(_supported_number(v, nums, "pressure") or _supported_number(v, nums, "force") for v in vals)
    key = spec.lower()
    if key in t:
        return True
    words = [w for frag, ws in WORDS.items() if frag in key for w in ws]
    try:
        m = materials.get(key)
        words += [m.family.replace("_", " ")]
    except Exception:
        pass
    return any(w in t for w in words)


def check_request(request_text: str, user_text: str) -> list[str]:
    """Return the analysis inputs in ``request_text`` that the user never gave (empty = fine)."""
    from .request import parse
    req = parse(request_text)
    missing: list[str] = []
    nums = _numbers(user_text)
    for cmd in req["commands"]:
        try:
            argv = shlex.split(cmd)
        except ValueError:
            continue
        if not argv or argv[0] not in ("analyze", "analyse"):
            continue
        for i, a in enumerate(argv):
            if a in ("-m", "--material") and i + 1 < len(argv):
                if not _material_supported(argv[i + 1], user_text):
                    missing.append(f"the material (the request assumed '{argv[i + 1]}')")
            if a in LOAD_FLAGS:
                vals = argv[i + 1:i + 4]
                if a == "--gravity":
                    continue                       # self weight follows from the material
                if a in ("--force", "--pressure", "--moment", "--heat", "--temp"):
                    vals = argv[i + 2:i + 3]
                elif a == "--convect":
                    vals = argv[i + 2:i + 4]
                elif a == "--dT":
                    vals = argv[i + 1:i + 2]
                for v in vals:
                    for n in _numbers(re.sub(r"[A-Za-z]+", " ", v)):
                        if not _supported_number(n, nums, LOAD_FLAGS[a]):
                            what = LOAD_FLAGS[a]
                            missing.append(f"the {what} (the request assumed {v})")
                            break
    for block in req["json"]:
        try:
            job = json.loads(block)
        except ValueError:
            continue
        if not (job.get("analysis") or job.get("loads")):
            continue
        if job.get("material") and not _material_supported(json.dumps(job["material"]) if isinstance(job["material"], dict)
                                                           else str(job["material"]), user_text):
            missing.append(f"the material (the request assumed {job['material']})")
        for part in job.get("parts") or []:
            m = part.get("material") if isinstance(part, dict) else None
            if m and not _material_supported(json.dumps(m) if isinstance(m, dict) else str(m), user_text):
                missing.append(f"the material of '{part.get('name', 'a part')}' (the request assumed {m})")
        for load in job.get("loads", []):
            for v in (load.get("value") if isinstance(load.get("value"), list) else [load.get("value")]):
                for n in _numbers(str(v or "")):
                    kind = {"force": "force", "pressure": "pressure", "moment": "moment", "heat_power": "heat",
                            "convection": "convection", "temperature_change": "temperature"}.get(load.get("type"), "force")
                    if not _supported_number(n, nums, kind):
                        missing.append(f"the {load.get('type', 'load')} (the request assumed {load.get('value')})")
                        break
    return list(dict.fromkeys(missing))


def question(missing: list[str]) -> str:
    items = "\n".join(f"- {m}" for m in missing)
    return ("Before I run the analysis I need a few facts from you - I will not guess them, because the "
            f"answer depends on them:\n{items}\n\nPlease give the material (e.g. 'steel', 'aluminium 6061', "
            "'PETG'), the load with its size and direction (e.g. '500 N downwards at the free end', "
            "'5 kg hanging from the hook'), and where the part is held, if not already stated.")


INTENT = ("bend", "deflect", "sag", "stress", "strength", "strong", "will it hold", "can it hold", "hold up",
          "hold the weight", "hold the load", "break", "fail", "safety factor",
          "safe", "carry", "support the", "vibrat", "frequency", "resonan", "buckl", "temperature", "how hot",
          "heat", "cool", "thermal", "fatigue", "analy", "fea", "stiff", "deform", "crack", "stretch", "elongat",
          "compress", "twist", "torsion", "displace", "move under", "yield", "load capacity")
LOAD_UNITS = r"(n|kn|kg|g|lb|lbs|lbf|kip|psi|ksi|mpa|kpa|bar|pa|w|kw|nm|n\.?m|n\*m|°c|°f|degc|degf|c|f|k|newtons?|kilos?|pounds?)\b"
SUPPORT_WORDS = ("fix", "bolt", "clamp", "held", "hold", "mount", "support", "wall", "weld", "screw", "rest",
                 "sits", "attached", "cantilever", "pinned", "both ends", "one end")


def analysis_intent(user_text: str) -> bool:
    t = user_text.lower()
    return any(w in t for w in INTENT)


def missing_for_analysis(user_text: str) -> list[str]:
    """What an analysis question still lacks, judged only from the user's own words."""
    t = " " + user_text.lower() + " "
    missing = []
    mat_words = {w for ws in WORDS.values() for w in ws} | {"wood", "plastic", "metal", "iron", "nylon"}
    if not any(w in t for w in mat_words):
        missing.append("the material (for example steel, aluminium 6061, PETG)")
    if not re.search(r"\d[\d.,]*\s*" + LOAD_UNITS, t):
        missing.append("the load: how big, which direction and where it acts (for example 500 N downwards at "
                       "the free end, or a 5 kg weight hanging from the hook)")
    if not any(w in t for w in SUPPORT_WORDS):
        missing.append("how the part is held (for example bolted to a wall at one end)")
    return missing


_Q = [  # (regex unit, kind, factor to the request's metric unit, label)
    (r"kg|kilos?|kilograms?", "force", G, "N (weight of the mass)"),
    (r"lbs?|pounds?", "force", 0.45359237 * G, "N (weight)"),
    (r"kn", "force", 1000, "N"), (r"lbf", "force", 4.4482216, "N"), (r"n|newtons?", "force", 1, "N"),
    (r"mpa", "pressure", 1, "MPa"), (r"kpa", "pressure", 1e-3, "MPa"), (r"bar", "pressure", 0.1, "MPa"),
    (r"psi", "pressure", 0.0068947573, "MPa"),
    (r"n\.?m|n\*m|nm", "moment", 1, "N*m"),
    (r"kw", "heat", 1000, "W"), (r"w|watts?", "heat", 1, "W"),
]


def stated_quantities(user_text: str) -> list[str]:
    """Loads the user stated, converted to the request's metric units (for the model's retry)."""
    out = []
    t = user_text.lower()
    for m in re.finditer(r"(\d+(?:\.\d+)?)\s*(°?c|°?f|deg\s?[cf]|[a-z*.]+)", t):
        num, unit = float(m.group(1)), m.group(2).strip(".")
        if re.fullmatch(r"°?c|deg\s?c", unit):
            out.append(f"{num:g} degC")
            continue
        if re.fullmatch(r"°?f|deg\s?f", unit):
            out.append(f"{num:g} degF = {(num - 32) * 5 / 9:.4g} degC")
            continue
        for rx, kind, f, label in _Q:
            if re.fullmatch(rx, unit):
                out.append(f"{num:g} {unit} = {num * f:.4g} {label}" if f != 1 else f"{num:g} {label}")
                break
    return list(dict.fromkeys(out))


def materials_mentioned(user_text: str) -> list[str]:
    t = " " + user_text.lower() + " "
    return sorted({w.strip() for ws in WORDS.values() for w in ws if w in t})


def retry_hint(missing: list[str], user_text: str) -> str:
    q = stated_quantities(user_text)
    mats = materials_mentioned(user_text)
    return ("The tool rejected this request because these values were not given by the user:\n"
            + "\n".join(f"- {m}" for m in missing)
            + "\nUse ONLY what the user actually said. The user stated these quantities: "
            + (", ".join(q) if q else "none")
            + ". Material words the user used: " + (", ".join(mats) if mats else "none")
            + ". Map the material words to the closest library key (e.g. 'mild steel' -> steel_generic, "
              "'aluminium 6061' -> al_6061_t6). A weight hanging down is a force in -Z of that many N. "
              "Reply with the complete corrected REQUEST. If the user truly did not give a material or "
              "a load, reply with a short question instead and no commands.")


# user words -> library key, most specific first
MATERIAL_MAP = [
    (("stainless", "304", "inox"), "stainless_304"), (("316",), "stainless_316l"),
    (("s355",), "steel_s355"), (("s235",), "steel_s235"), (("a36",), "steel_a36"), (("4140",), "steel_4140_qt"),
    (("1045",), "steel_1045"), (("tool steel", "p20"), "tool_steel_p20"), (("invar",), "invar_36"),
    (("mild steel", "carbon steel", "structural steel", "steel"), "steel_generic"),
    (("7075",), "al_7075_t6"), (("5052",), "al_5052_h32"),
    (("6061", "aluminium", "aluminum", "alu "), "al_6061_t6"),
    (("titanium", "ti-6", "ti6"), "ti_6al4v"), (("brass",), "brass_c360"), (("copper",), "copper_c110"),
    (("petg", "pet-g"), "petg"), ((" pla",), "pla"), ((" abs",), "abs"), ((" asa",), "asa"),
    (("pa12", "nylon"), "pa12_sls"), (("polycarbonate",), "pc"), (("peek",), "peek"), (("pekk",), "pekk"),
    (("ultem", " pei"), "pei"), (("polypropylene",), "pp"),
]


def material_from_words(user_text: str) -> str | None:
    t = " " + user_text.lower() + " "
    for words, key in MATERIAL_MAP:
        if any(w in t for w in words):
            return key
    return None


def _user_loads(user_text: str, kind: str) -> list[float]:
    vals = []
    for q in stated_quantities(user_text):
        m = re.search(r"=?\s*([\d.]+(?:e[-+]?\d+)?) (N|MPa)\b", q.split("=")[-1])
        if m and ((kind == "force" and m.group(2) == "N") or (kind == "pressure" and m.group(2) == "MPa")):
            vals.append(float(m.group(1)))
    return list(dict.fromkeys(vals))


def _wrong_grade(key: str, mapped: str | None, user_text: str) -> bool:
    """True when the request's material is not what the user's words point to."""
    if key.strip().startswith("{"):
        return not _material_supported(key, user_text)
    if not _material_supported(key, user_text):
        return True
    if not mapped or key == mapped:
        return False
    t = user_text.lower()
    grade_tokens = [p for p in key.lower().split("_") if any(ch.isdigit() for ch in p)]
    return not any(tok in t for tok in grade_tokens)        # e.g. s355 chosen but never mentioned


def _fix_check(spec: str, material: str | None, force: float | None) -> str:
    """Put the job's material stiffness (E, nu) and load (P) into a hand-calc spec."""
    if material:
        try:
            from . import materials
            m = materials.get(material, "metric")
            if m.get("E"):
                spec = re.sub(r"(?<![\w.])E=(\"[^\"]*\"|'[^']*'|\S+)", f'E="{m.get("E"):g} MPa"', spec)
            if m.get("nu"):
                spec = re.sub(r"(?<![\w.])nu=\S+", f"nu={m.get('nu'):g}", spec)
        except Exception:
            pass
    if force:
        spec = re.sub(r"(?<![\w.])P=(\"[^\"]*\"|'[^']*'|\S+)", f'P="{force:g} N"', spec)
    return spec


def autocorrect(request_text: str, user_text: str) -> tuple[str, list[str]]:
    """Replace invented materials / load magnitudes with the user's own, when unambiguous.

    Returns (corrected request, notes describing each change). Only `ea analyze` lines change.
    """
    notes: list[str] = []
    lines = request_text.split("\n")
    mat = material_from_words(user_text)
    forces, pressures = _user_loads(user_text, "force"), _user_loads(user_text, "pressure")
    nums = _numbers(user_text)
    for i, line in enumerate(lines):
        if not re.match(r"^\s*(\./)?ea\s+analy[sz]e\b", line):
            continue
        try:
            argv = shlex.split(line.strip())
        except ValueError:
            continue
        changed = False
        for j, a in enumerate(argv):
            if a in ("-m", "--material") and j + 1 < len(argv) and _wrong_grade(argv[j + 1], mat, user_text):
                if mat:
                    notes.append(f"material: used `{mat}` for what you wrote (the AI had assumed `{argv[j + 1]}`)")
                    argv[j + 1], changed = mat, True
            if a == "--force" and j + 2 < len(argv):
                comps = argv[j + 2].split(",")
                try:
                    vals = [float(c) for c in comps]
                except ValueError:
                    continue
                nz = [k for k, v in enumerate(vals) if v]
                if len(nz) == 1 and not _supported_number(abs(vals[nz[0]]), nums, "force") and len(forces) == 1:
                    k = nz[0]
                    vals[k] = forces[0] if vals[k] > 0 else -forces[0]
                    argv[j + 2] = ",".join(f"{v:g}" for v in vals)
                    notes.append(f"load: used {forces[0]:g} N from what you wrote, direction "
                                 f"{'+-'[vals[k] < 0]}{'XYZ'[k]} as the AI set it")
                    changed = True
            if a == "--pressure" and j + 2 < len(argv) and len(pressures) == 1:
                try:
                    p = float(argv[j + 2])
                except ValueError:
                    continue
                if not _supported_number(abs(p), nums, "pressure"):
                    argv[j + 2] = f"{pressures[0]:g}"
                    notes.append(f"pressure: used {pressures[0]:g} MPa from what you wrote")
                    changed = True
        if changed:
            # hand calcs carry the same material / load: update them to the corrected values (never drop them)
            new_mat = argv[argv.index("-m") + 1] if "-m" in argv and argv.index("-m") + 1 < len(argv) else None
            fv = None
            if "--force" in argv and argv.index("--force") + 2 < len(argv):
                try:
                    fv = max(abs(float(c)) for c in argv[argv.index("--force") + 2].split(","))
                except ValueError:
                    fv = None
            for j, a in enumerate(argv):
                if a in ("--check", "--bound") and j + 1 < len(argv):
                    fixed = _fix_check(argv[j + 1], new_mat, fv)
                    if fixed != argv[j + 1]:
                        argv[j + 1] = fixed
                        notes.append("hand check: updated to your material and load")
            lines[i] = "ea " + " ".join(shlex.quote(x) for x in argv[1:])
    return "\n".join(lines), list(dict.fromkeys(notes))
