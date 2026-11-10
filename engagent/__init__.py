"""EngineeringAgent: parametric CAD (build123d), FEA (Gmsh + CalculiX), hand
calculations, GD&T and verification reporting, with one unit toggle for all."""

__version__ = "0.1.0"

from . import config, units  # noqa: F401
from .config import get_units, set_units  # noqa: F401
