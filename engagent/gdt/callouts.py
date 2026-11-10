"""Feature control frames, position-tolerance arithmetic and scheme review.

Supports ISO GPS (ISO 1101:2017, ISO 5459, ISO 8015, ISO 2692) and
ASME Y14.5-2018.  The review encodes rules that are checkable from the data
given; it does not replace a drawing check by a qualified person.
"""
from __future__ import annotations

from .. import units as U
from . import general

# characteristic -> (symbol, category, needs datum: "never" | "always" | "optional")
CHARACTERISTICS = {
    "straightness": ("⏤", "form", "never"),
    "flatness": ("⏥", "form", "never"),
    "circularity": ("○", "form", "never"),
    "cylindricity": ("⌭", "form", "never"),
    "profile_line": ("⌒", "profile", "optional"),
    "profile_surface": ("⌓", "profile", "optional"),
    "perpendicularity": ("⟂", "orientation", "always"),
    "parallelism": ("∥", "orientation", "always"),
    "angularity": ("∠", "orientation", "always"),
    "position": ("⌖", "location", "always"),
    "concentricity": ("◎", "location", "always"),
    "symmetry": ("⌯", "location", "always"),
    "circular_runout": ("↗", "runout", "always"),
    "total_runout": ("⌰", "runout", "always"),
}
ALIASES = {"roundness": "circularity", "profile": "profile_surface", "runout": "circular_runout",
           "true_position": "position", "coaxiality": "concentricity", "squareness": "perpendicularity"}
MODIFIERS = {"M": "Ⓜ", "L": "Ⓛ", "F": "Ⓕ", "P": "Ⓟ", "U": "Ⓤ", "E": "Ⓔ"}
SIZE_FEATURES = ("hole", "pin", "shaft", "slot", "tab", "boss", "bore", "width", "diameter")


def _char(name: str) -> str:
    key = str(name).lower().replace(" ", "_").replace("-", "_")
    key = ALIASES.get(key, key)
    if key not in CHARACTERISTICS:
        raise ValueError(f"unknown geometric characteristic {name!r}; known: {', '.join(CHARACTERISTICS)}")
    return key


def frame(characteristic: str, tolerance, datums: list[str] | None = None, *, diameter: bool = False,
          modifier: str | None = None, datum_modifiers: dict | None = None,
          system: str | None = None, standard: str = "iso") -> dict:
    """Build a feature control frame: text for a drawing note plus a structured record."""
    key = _char(characteristic)
    sym, cat, _ = CHARACTERISTICS[key]
    t = U.to_internal(tolerance, "length", system)
    metric = U.normalize_system(system) == "metric"
    txt = f"{t:.3g}" if metric else f"{t / 25.4:.4f}".rstrip("0").rstrip(".")
    if not metric and txt.startswith("0."):
        txt = txt[1:]                                   # inch practice: no leading zero
    cell = ("⌀" if diameter else "") + txt
    if modifier:
        m = modifier.upper()
        if m not in MODIFIERS:
            raise ValueError(f"unknown modifier {modifier!r}; use M (MMC/MMR), L (LMC/LMR), F, P, U or E")
        cell += MODIFIERS[m]
    dcells = []
    for d in datums or []:
        dm = (datum_modifiers or {}).get(d)
        dcells.append(d + (MODIFIERS[dm.upper()] if dm else ""))
    text = "|" + "|".join([sym, cell] + dcells) + "|"
    plain = f"{key.replace('_', ' ')} {'dia ' if diameter else ''}{txt}" + \
            (f" ({'MMC' if modifier.upper() == 'M' else 'LMC' if modifier.upper() == 'L' else modifier.upper()})"
             if modifier else "") + (" to " + "-".join(datums) if datums else "")
    return {"characteristic": key, "category": cat, "symbol": sym, "tolerance": t,
            "diameter": bool(diameter), "modifier": modifier.upper() if modifier else None,
            "datums": list(datums or []), "text": text, "plain": plain, "standard": standard}


def position_tolerance(fastener, hole, joint: str = "floating", system: str | None = None,
                       projected: float | None = None, thickness: float | None = None) -> dict:
    """Largest position tolerance that guarantees assembly.

    floating fastener (bolt through both parts):  T = H - F   (each part)
    fixed fastener (threaded or pressed in one part): T = (H - F) / 2 (each part, equal split);
        with a projected zone, T1 + T2 (1 + 2P / D) = H - F  (ASME Y14.5-2018 Appendix B)
    H = clearance hole at MMC (smallest hole), F = fastener at MMC (largest fastener).
    """
    F = U.to_internal(fastener, "length", system)
    H = U.to_internal(hole, "length", system)
    if H <= F:
        raise ValueError("the clearance hole must be larger than the fastener")
    j = joint.lower()
    if j.startswith("float"):
        T = H - F
        formula = "T = H - F"
    elif j.startswith("fix"):
        if projected is not None and thickness:
            P = U.to_internal(projected, "length", system)
            D = U.to_internal(thickness, "length", system)
            T = (H - F) / (2 + 2 * P / D)
            formula = "T = (H - F) / (2 + 2P/D)  (no projected tolerance zone specified)"
        else:
            T = (H - F) / 2
            formula = "T = (H - F) / 2"
    else:
        raise ValueError("joint must be 'floating' or 'fixed'")
    return {"joint": "floating" if j.startswith("float") else "fixed", "fastener_mmc": F,
            "hole_mmc": H, "position_tolerance": T, "formula": formula,
            "reference": "ASME Y14.5-2018 Appendix B; ISO 2692 (maximum material requirement)"}


def bonus(stated, mmc_size, actual_size, feature: str = "hole", system: str | None = None) -> dict:
    """Total position tolerance available with the MMC / MMR modifier."""
    t = U.to_internal(stated, "length", system)
    mmc = U.to_internal(mmc_size, "length", system)
    act = U.to_internal(actual_size, "length", system)
    b = (act - mmc) if feature.lower() in ("hole", "slot", "bore") else (mmc - act)
    if b < 0:
        raise ValueError("actual size violates the maximum material limit")
    return {"stated": t, "bonus": b, "total": t + b}


def review(spec: dict, system: str | None = None) -> dict:
    """Review a GD&T scheme.

    spec = {
      "standard": "iso" | "asme",            (default: follows the unit system)
      "process": "cnc_milling",              (optional, for capability checks)
      "general_tolerance": "ISO 2768-mK",    (optional)
      "datums": [{"label": "A", "feature": "mounting face", "reason": "..."}],
      "features": [{"name": "bolt holes", "type": "hole", "nominal": 6.6, "tol": 0.1,
                    "fit": "H7/g6",
                    "fcf": {"characteristic": "position", "tolerance": 0.2, "diameter": true,
                            "modifier": "M", "datums": ["A", "B", "C"]},
                    "fastener": {"size": "M6", "joint": "fixed"}}],
      "stacks": [{"name": "...", "contributors": [...], "limits": {...}}]
    }
    """
    from ..config import get_standard
    from . import fits, stackup
    std = str(spec.get("standard") or get_standard(system)).lower()
    findings: list[dict] = []
    def note(status, item, msg):
        findings.append({"status": status, "item": item, "message": msg})
    datums = {d["label"]: d for d in spec.get("datums", [])}
    labels = list(datums)
    if not labels:
        note("WARN", "datums", "No datum reference frame defined; location and orientation "
             "tolerances cannot be specified without one.")
    elif len(labels) < 3:
        note("INFO", "datums", f"{len(labels)} datum(s) defined: fewer than three leaves degrees of "
             f"freedom unconstrained; confirm that is intended.")
    features_out = []
    form_controlled = set()
    for f in spec.get("features", []):
        row = {"name": f.get("name", "feature"), "type": f.get("type", ""), "notes": []}
        ftype = str(f.get("type", "")).lower()
        nominal = U.to_internal(f["nominal"], "length", system) if "nominal" in f else None
        row["nominal"] = nominal
        if "fit" in f and nominal is not None:
            fr = fits.fit(nominal, f["fit"], "metric")
            row["fit"] = fr
            lo, hi = (fr["hole"]["min"], fr["hole"]["max"]) if ftype in ("hole", "bore", "slot") \
                else (fr["shaft"]["min"], fr["shaft"]["max"])
            row["size_limits"] = [lo, hi]
        elif "tol" in f and nominal is not None:
            t = abs(U.to_internal(f["tol"], "length", system))
            row["size_limits"] = [nominal - t, nominal + t]
        elif "plus" in f or "minus" in f:
            row["size_limits"] = [nominal - abs(U.to_internal(f.get("minus", 0), "length", system)),
                                  nominal + abs(U.to_internal(f.get("plus", 0), "length", system))]
        if spec.get("process") and row.get("size_limits") and nominal:
            half = (row["size_limits"][1] - row["size_limits"][0]) / 2
            cap = general.check_tolerance(spec["process"], nominal, half, "metric")
            row["process"] = cap
            if cap["status"] != "PASS":
                note(cap["status"], row["name"], f"size tolerance +/-{half:.3g} mm on {nominal:g} mm: "
                     f"{cap['message']} ({cap['process']}: typical +/-{cap['typical']:.3g} mm).")
        fc = f.get("fcf")
        if fc:
            fr = frame(fc["characteristic"], fc["tolerance"], fc.get("datums"),
                       diameter=fc.get("diameter", False), modifier=fc.get("modifier"),
                       system=system, standard=std)
            row["fcf"] = fr
            _, cat, need = CHARACTERISTICS[fr["characteristic"]]
            if need == "never" and fr["datums"]:
                note("FAIL", row["name"], f"{fr['characteristic']} is a form tolerance and must not "
                     f"reference datums.")
            if need == "always" and not fr["datums"]:
                note("FAIL", row["name"], f"{fr['characteristic']} needs at least one datum reference.")
            for d in fr["datums"]:
                if d not in datums:
                    note("FAIL", row["name"], f"references datum {d}, which is not defined.")
            if fr["modifier"] in ("M", "L") and ftype and not any(k in ftype for k in SIZE_FEATURES):
                note("FAIL", row["name"], "MMC/LMC modifiers apply only to features of size "
                     "(holes, pins, slots, tabs), not to surfaces.")
            if fr["diameter"] and fr["characteristic"] in ("flatness", "profile_surface", "parallelism") \
                    and "hole" not in ftype and "pin" not in ftype and "axis" not in ftype:
                note("WARN", row["name"], "a diameter symbol implies a cylindrical tolerance zone; "
                     "check that the toleranced feature is an axis.")
            if std == "asme" and fr["characteristic"] in ("concentricity", "symmetry"):
                note("FAIL", row["name"], f"{fr['characteristic']} was removed from ASME Y14.5-2018; "
                     f"use position, runout or profile instead.")
            if std == "iso" and fr["characteristic"] == "position" and fr["modifier"] == "M":
                row["notes"].append("ISO: maximum material requirement per ISO 2692.")
            if cat == "form":
                form_controlled.add(row["name"])
            if spec.get("process") and nominal:
                cap = general.process_capability(spec["process"], nominal, "metric")
                if fr["tolerance"] < cap["best"]:
                    note("WARN", row["name"], f"geometric tolerance {fr['tolerance']:.3g} mm is below the "
                         f"practical limit of {cap['process']} (~{cap['best']:.3g} mm).")
        fa = f.get("fastener")
        if fa:
            ch = general.clearance_hole(fa["size"], fa.get("fit", "medium"))
            Hmin = row["size_limits"][0] if row.get("size_limits") else ch["hole"]
            pt = position_tolerance(ch["fastener"], Hmin, fa.get("joint", "floating"), "metric")
            row["fastener"] = {**ch, **pt}
            if fc and _char(fc["characteristic"]) == "position":
                if row["fcf"]["tolerance"] > pt["position_tolerance"] + 1e-9:
                    note("FAIL", row["name"], f"position tolerance {row['fcf']['tolerance']:.3g} mm exceeds "
                         f"the {pt['joint']}-fastener limit {pt['position_tolerance']:.3g} mm "
                         f"({pt['formula']}, H = {Hmin:.3g}, F = {ch['fastener']:.3g}): parts may not assemble.")
                else:
                    row["notes"].append(f"assembly guaranteed: {pt['formula']} = "
                                        f"{pt['position_tolerance']:.3g} mm")
            elif not fc:
                note("WARN", row["name"], f"fastener pattern without a position tolerance; the "
                     f"{pt['joint']}-fastener limit is {pt['position_tolerance']:.3g} mm.")
        features_out.append(row)
    for lab, d in datums.items():
        feat = d.get("feature", "")
        if not d.get("form_controlled") and feat not in form_controlled:
            note("INFO", f"datum {lab}", f"datum feature '{feat}' has no form tolerance (flatness / "
                 f"cylindricity); add one so the datum is repeatable.")
    stacks = []
    for st in spec.get("stacks", []):
        r = stackup.stack(st["contributors"], system, limits=st.get("limits"),
                          monte_carlo=int(st.get("monte_carlo", 0)))
        r["name"] = st.get("name", "stack")
        stacks.append(r)
        if r.get("status") and r["status"] != "PASS":
            note(r["status"], r["name"], r["message"])
    gen = spec.get("general_tolerance") or ("ISO 2768-mK" if std == "iso" else
                                            "per title block (X.XX +/-.01, X.XXX +/-.005, angles +/-0.5 deg)")
    principles = (["ISO 8015 independency principle: size and geometry are independent unless "
                   "the envelope requirement (E) is stated.",
                   "ISO 1101:2017 geometrical tolerancing; ISO 5459 datums; ISO 14405-1 size.",
                   f"General tolerances: {gen}."] if std == "iso" else
                  ["ASME Y14.5-2018 Rule #1 (envelope principle): size limits control form "
                   "unless stated otherwise.",
                   "Tolerances apply RFS unless MMC/LMC is specified (Rule #2).",
                   f"General tolerances: {gen}."])
    worst = "FAIL" if any(f["status"] == "FAIL" for f in findings) else \
        ("WARN" if any(f["status"] == "WARN" for f in findings) else "PASS")
    return {"standard": std, "standard_name": "ISO GPS (ISO 1101 / ISO 5459 / ISO 8015)" if std == "iso"
            else "ASME Y14.5-2018", "datums": list(datums.values()), "features": features_out,
            "stacks": stacks, "findings": findings, "principles": principles,
            "general_tolerance": gen, "process": spec.get("process"), "status": worst}
