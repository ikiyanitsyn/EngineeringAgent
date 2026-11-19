from build123d import *
from engagent.cad import params, save

P = params(
    length=120.0,
    width=60.0,
    thickness=8.0,
    hole_dia=6.6,
    edge_x=10.0,
    edge_y=10.0,
    chamfer_size=0.5,
)

part = Box(P.length, P.width, P.thickness, align=(Align.MIN, Align.MIN, Align.MIN))

# 4x Ø6.6 through holes centered at mid-thickness and oversized to cut completely through
for x in (P.edge_x, P.length - P.edge_x):
    for y in (P.edge_y, P.width - P.edge_y):
        cutter = Pos(x, y, P.thickness / 2) * Cylinder(P.hole_dia / 2, P.thickness * 3)
        part -= cutter

if P.chamfer_size > 0:
    part = chamfer(part.edges(), P.chamfer_size)

save(part)
