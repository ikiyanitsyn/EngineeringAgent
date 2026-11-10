"""1-D tolerance stack-up: worst case, root-sum-square and Monte Carlo."""
from __future__ import annotations

import math
import random

from .. import units as U


def stack(contributors: list[dict], system: str | None = None, *, sigma: float = 3.0,
          limits: dict | None = None, monte_carlo: int = 0, seed: int = 1) -> dict:
    """Analyse a linear stack.

    Each contributor: {"name", "nominal", "plus", "minus", "direction": +1 | -1}
    or {"name", "nominal", "tol"} for a symmetric +/- tolerance.  Lengths are in
    the active unit system (or strings with units).  ``direction`` is +1 when
    the dimension increases the gap, -1 when it closes it.

    limits: {"min": x, "max": y} functional requirement on the result (gap).
    Returns values in mm.
    """
    rows, nom, wc_hi, wc_lo, var = [], 0.0, 0.0, 0.0, 0.0
    L = lambda v: U.to_internal(v, "length", system)  # noqa: E731
    for c in contributors:
        d = float(c.get("direction", 1))
        if d not in (1.0, -1.0):
            raise ValueError(f"{c.get('name')}: direction must be +1 or -1")
        n = L(c["nominal"])
        if "tol" in c:
            plus = minus = abs(L(c["tol"]))
        else:
            plus, minus = abs(L(c.get("plus", 0))), abs(L(c.get("minus", 0)))
        mean = n + (plus - minus) / 2            # centre of the tolerance band
        half = (plus + minus) / 2
        nom += d * mean
        wc_hi += half
        wc_lo += half
        k = float(c.get("sigma", sigma))         # band = +/- k sigma
        var += (half / k) ** 2
        rows.append({"name": c.get("name", f"dim {len(rows) + 1}"), "nominal": n, "plus": plus,
                     "minus": minus, "direction": int(d), "mean": mean, "half_band": half,
                     "variance": (half / k) ** 2})
    sd = math.sqrt(var)
    for r in rows:
        r["contribution"] = r["variance"] / var if var else 0.0
    out = {"contributors": rows, "nominal": nom, "worst_case_min": nom - wc_lo,
           "worst_case_max": nom + wc_hi, "rss_min": nom - sigma * sd, "rss_max": nom + sigma * sd,
           "std_dev": sd, "sigma": sigma}
    if monte_carlo:
        rnd = random.Random(seed)
        vals = []
        for _ in range(int(monte_carlo)):
            v = 0.0
            for r, c in zip(rows, contributors):
                k = float(c.get("sigma", sigma))
                if c.get("distribution", "normal") == "uniform":
                    x = rnd.uniform(r["mean"] - r["half_band"], r["mean"] + r["half_band"])
                else:
                    x = rnd.gauss(r["mean"], r["half_band"] / k)
                v += r["direction"] * x
            vals.append(v)
        vals.sort()
        n = len(vals)
        out["monte_carlo"] = {"samples": n, "mean": sum(vals) / n, "min": vals[0], "max": vals[-1],
                              "p0135": vals[int(0.00135 * n)], "p99865": vals[min(n - 1, int(0.99865 * n))]}
    if limits:
        lo = L(limits["min"]) if limits.get("min") is not None else None
        hi = L(limits["max"]) if limits.get("max") is not None else None
        wc_ok = (lo is None or out["worst_case_min"] >= lo) and (hi is None or out["worst_case_max"] <= hi)
        rss_ok = (lo is None or out["rss_min"] >= lo) and (hi is None or out["rss_max"] <= hi)
        out["limits"] = {"min": lo, "max": hi}
        out["worst_case_ok"], out["rss_ok"] = wc_ok, rss_ok
        if sd > 0:
            zs = [(nom - lo) / sd] if lo is not None else []
            zs += [(hi - nom) / sd] if hi is not None else []
            z = min(zs)
            out["cpk"] = z / 3.0
            out["defect_ppm"] = sum(0.5 * math.erfc(v / math.sqrt(2)) for v in zs) * 1e6
        if "monte_carlo" in out:
            bad = sum(1 for v in vals if (lo is not None and v < lo) or (hi is not None and v > hi))
            out["monte_carlo"]["reject_fraction"] = bad / len(vals)
        out["status"] = "PASS" if wc_ok else ("WARN" if rss_ok else "FAIL")
        out["message"] = ("meets the requirement at worst case" if wc_ok else
                          "fails at worst case but passes statistically (RSS): acceptable only for "
                          "volume production with process control" if rss_ok else
                          "fails the requirement even statistically: tighten the largest contributors")
    return out


def describe(s: dict, system: str | None = None) -> list[tuple[str, str]]:
    f = lambda v: U.fmt(v, "length", system, sig=5)  # noqa: E731
    rows = [("Nominal result", f(s["nominal"])),
            ("Worst case", f"{f(s['worst_case_min'])} to {f(s['worst_case_max'])}"),
            (f"RSS (+/-{s['sigma']:g} sigma)", f"{f(s['rss_min'])} to {f(s['rss_max'])}")]
    if "monte_carlo" in s:
        m = s["monte_carlo"]
        rows.append((f"Monte Carlo ({m['samples']:,} samples)", f"{f(m['p0135'])} to {f(m['p99865'])} (99.73 %)"))
    if "limits" in s:
        lim = s["limits"]
        rows.append(("Requirement", " to ".join(f(v) if v is not None else "-" for v in (lim["min"], lim["max"]))))
        if "cpk" in s:
            rows.append(("Cpk (RSS)", f"{s['cpk']:.2f}  (~{s['defect_ppm']:.3g} ppm outside)"))
        rows.append(("Verdict", f"{s['status']}: {s['message']}"))
    top = sorted(s["contributors"], key=lambda r: -r["contribution"])[:3]
    rows.append(("Largest contributors", ", ".join(f"{r['name']} ({r['contribution'] * 100:.0f} %)" for r in top)))
    return rows
