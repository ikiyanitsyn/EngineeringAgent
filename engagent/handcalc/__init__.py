"""Closed-form engineering calculations with traceable formulas and references.

Each calculation is registered with the kind of every input and output, so it
can be called with values in any unit system:

    from engagent import handcalc
    r = handcalc.run("beam.cantilever_end_load",
                     {"P": 100, "L": 100, "E": "210 GPa", "b": 10, "h": 10})
    r.value("deflection")          # internal units (mm)
    r.text("deflection")           # '0.1905 mm' in the active unit system

The Python functions themselves take and return internal units
(mm, tonne, s, N, MPa, mJ, mW, degC).
"""
from __future__ import annotations

import inspect
from dataclasses import dataclass, field
from typing import Any, Callable

from .. import units as U


@dataclass
class CalcResult:
    name: str
    title: str
    inputs: dict[str, float]
    outputs: dict[str, float]
    in_kinds: dict[str, str]
    out_kinds: dict[str, str]
    formulas: list[str]
    reference: str
    notes: list[str] = field(default_factory=list)
    system: str | None = None

    def value(self, key: str) -> float:
        return self.outputs[key]

    def text(self, key: str, system: str | None = None) -> str:
        k = self.out_kinds.get(key, "ratio")
        return U.fmt(self.outputs[key], k, system or self.system)

    def to_dict(self, system: str | None = None) -> dict:
        s = system or self.system
        return {
            "name": self.name, "title": self.title, "reference": self.reference,
            "formulas": self.formulas, "notes": self.notes,
            "inputs": {k: (U.fmt(v, self.in_kinds[k], s) if self.in_kinds.get(k) in U.KINDS
                           and isinstance(v, (int, float)) else str(v))
                       for k, v in self.inputs.items()},
            "outputs": {k: U.fmt(v, self.out_kinds.get(k, "ratio"), s) for k, v in self.outputs.items()},
            "outputs_internal": dict(self.outputs),
            "output_kinds": dict(self.out_kinds),
        }


@dataclass
class _Entry:
    name: str
    fn: Callable
    title: str
    inputs: dict[str, str]
    outputs: dict[str, str]
    formulas: list[str]
    reference: str
    notes: list[str]


REGISTRY: dict[str, _Entry] = {}


def calc(name: str, title: str, inputs: dict[str, str], outputs: dict[str, str],
         formulas: list[str], reference: str, notes: list[str] | None = None):
    """Register a calculation.  ``inputs``/``outputs`` map names to quantity kinds;
    kinds outside ``units.KINDS`` ("int", "text", "list") are passed through unchanged."""
    def deco(fn):
        REGISTRY[name] = _Entry(name, fn, title, inputs, outputs, formulas, reference, notes or [])
        return fn
    return deco


SYNONYMS = {"alpha": "cte", "length": "L", "load": "P", "force": "P", "torque": "T", "thickness": "t",
            "width": "b", "diameter": "D", "pressure": "p", "ends": "support", "support": "ends",
            "boundary": "support", "edge": "edges"}


def _aliases(inputs: dict[str, Any], params: list[str]) -> dict[str, Any]:
    """Forgive the usual spellings of an input (W for w, alpha for cte, ...), as an AI often writes them."""
    out: dict[str, Any] = {}
    lower = {p.lower(): p for p in params}
    for k, v in inputs.items():
        key = k
        if k not in params:
            if SYNONYMS.get(k.lower()) in params:
                key = SYNONYMS[k.lower()]
            elif k.lower() in lower and sum(p.lower() == k.lower() for p in params) == 1:
                key = lower[k.lower()]
        if key == "cte":                   # a coefficient written per kelvin (12e-6) -> um/m/K (12)
            try:
                f = float(v)
                if 0 < abs(f) < 1e-3:
                    v = f * 1e6
            except (TypeError, ValueError):
                pass
        out[key] = v
    return out


def run(name: str, inputs: dict[str, Any], system: str | None = None) -> CalcResult:
    """Run a registered calculation with inputs in the active (or given) unit system."""
    _load_all()
    if name not in REGISTRY:
        import difflib
        hint = difflib.get_close_matches(name, REGISTRY, n=4)
        raise KeyError(f"unknown calculation {name!r}" + (f"; did you mean {', '.join(hint)}?" if hint else ""))
    e = REGISTRY[name]
    sig = inspect.signature(e.fn)
    inputs = _aliases(inputs, list(sig.parameters))
    unknown = [k for k in inputs if k not in sig.parameters]
    if unknown:
        raise ValueError(f"{name}: unknown input(s) {', '.join(unknown)}; "
                         f"accepted: {', '.join(sig.parameters)}")
    args: dict[str, Any] = {}
    for k, v in inputs.items():
        kind = e.inputs.get(k)
        args[k] = U.to_internal(v, kind, system) if kind in U.KINDS and v is not None \
            and not isinstance(v, (list, tuple, dict)) else v
    missing = [p for p, par in sig.parameters.items() if par.default is inspect._empty and p not in args]
    if missing:
        raise ValueError(f"{name}: missing input(s) {', '.join(missing)}")
    out = e.fn(**args)
    notes = list(e.notes)
    if isinstance(out, tuple):
        out, extra = out
        notes += list(extra)
    full_in = {p: args.get(p, par.default) for p, par in sig.parameters.items()
               if args.get(p, par.default) is not None}
    return CalcResult(name=name, title=e.title, inputs=full_in, outputs=out, in_kinds=e.inputs,
                      out_kinds=e.outputs, formulas=e.formulas, reference=e.reference,
                      notes=notes, system=U.normalize_system(system))


def catalog() -> list[dict]:
    _load_all()
    return [{"name": e.name, "title": e.title, "inputs": e.inputs, "outputs": e.outputs,
             "reference": e.reference} for e in sorted(REGISTRY.values(), key=lambda x: x.name)]


_loaded = False


def _load_all() -> None:
    global _loaded
    if not _loaded:
        from . import beams, composites, fasteners, fatigue, mechanics, sections, thermal  # noqa: F401
        _loaded = True
