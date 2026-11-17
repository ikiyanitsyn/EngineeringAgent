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


INTENT = ("bend", "deflect", "sag", "stress", "strength", "strong", "hold", "break", "fail", "safety factor",
          "safe", "carry", "support the", "vibrat", "frequency", "resonan", "buckl", "temperature", "how hot",
          "heat", "cool", "thermal", "fatigue", "analy", "fea", "stiff", "deform", "crack")
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
