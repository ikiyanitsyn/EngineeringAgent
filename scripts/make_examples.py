"""Regenerate the benchmark examples from the built-in starter jobs.

    .venv/bin/python scripts/make_examples.py

Hand-written examples (20-*, 21-*) are left untouched.
"""
import json
from pathlib import Path

from engagent.fea.starters import starter

ROOT = Path(__file__).resolve().parent.parent / "examples"
BENCH = [("01-cantilever-static", "static", "metric"), ("02-cantilever-imperial", "static", "imperial"),
         ("03-modal-cantilever", "modal", "metric"), ("04-column-buckling", "buckling", "metric"),
         ("05-plastic-bar-nonlinear", "nonlinear", "metric"), ("06-fatigue-screening", "fatigue", "metric"),
         ("07-bar-conduction", "thermal_steady", "metric"), ("08-bar-convection", "convection", "metric"),
         ("09-bar-thermal-stress", "thermal_stress", "metric"),
         ("10-laminate-heatup-transient", "thermal_transient", "metric"),
         ("11-laminate-spring-in", "spring_in", "metric"), ("12-tied-assembly", "tie", "metric"),
         ("13-contact-assembly", "contact", "metric")]

for folder, kind, system in BENCH:
    d = ROOT / folder
    d.mkdir(parents=True, exist_ok=True)
    job = starter(kind, system)
    job["name"] = folder
    for fname, text in job.pop("files_needed", {}).items():
        (d / fname).write_text(text, encoding="utf-8")
    (d / "job.json").write_text(json.dumps(job, indent=1) + "\n", encoding="utf-8")
    print("wrote", d / "job.json")
