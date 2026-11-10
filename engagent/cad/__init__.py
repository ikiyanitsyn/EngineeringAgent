"""CAD helpers on top of build123d (OpenCascade).

In a geometry script:

    from build123d import *
    from engagent.cad import params, save

    P = params(length=100, width=10, height=10)      # mm; overridable from a job or the CLI
    part = Box(P.length, P.width, P.height, align=(Align.MIN, Align.CENTER, Align.CENTER))
    save(part)                                       # part.step (+ part.stl, summary)

Geometry scripts are always written in millimetres; unit conversion happens at
the edges (``params`` accepts "4 in", reports follow the active unit system).
"""
from .build import params, run_script, save  # noqa: F401
from .inspect import inspect_shape, load_shape  # noqa: F401
