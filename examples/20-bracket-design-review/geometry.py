"""Aluminium angle bracket: base leg bolted down, upright leg carries the load.

Coordinate system: base leg along +X, upright leg along +Z, width along +Y.
The inside corner fillet is kept because it is the critical stress location.
"""
from build123d import *
from engagent.cad import params, save

P = params(
    leg_x=60.0,            # base leg length
    leg_z=60.0,            # upright leg height
    width=40.0,
    thickness=5.0,
    inside_radius=5.0,     # corner fillet (stress relief)
    hole_dia=6.6,          # M6 clearance, ISO 273 medium
    base_hole_x=40.0,      # base holes: distance from the back face
    load_hole_z=42.0,      # upright holes: height above the underside
    hole_pitch=20.0,       # spacing of each hole pair across the width
)

a = (Align.MIN, Align.MIN, Align.MIN)
bracket = Box(P.leg_x, P.width, P.thickness, align=a) + Box(P.thickness, P.width, P.leg_z, align=a)

corner = [e for e in bracket.edges().filter_by(Axis.Y)
          if abs(e.center().X - P.thickness) < 1e-6 and abs(e.center().Z - P.thickness) < 1e-6]
bracket = fillet(corner, P.inside_radius)

for y in (P.width / 2 - P.hole_pitch / 2, P.width / 2 + P.hole_pitch / 2):
    bracket -= Pos(P.base_hole_x, y, P.thickness / 2) * Cylinder(P.hole_dia / 2, 3 * P.thickness)
    bracket -= Pos(P.thickness / 2, y, P.load_hole_z) * Rot(0, 90, 0) * Cylinder(P.hole_dia / 2, 3 * P.thickness)

# Faces used by the analysis:
#   underside            z = 0                  (seats on the frame)
#   base bolt holes      cylinders r = 3.3, axis Z, at x = 40
#   load holes           cylinders r = 3.3, axis X, at z = 42
save(bracket)
