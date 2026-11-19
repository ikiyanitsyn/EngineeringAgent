from build123d import *
from engagent.cad import params, save

P = params(
    length=120.0,
    width=60.0,
    thickness=8.0,
    hole_d=6.6,
    edge_dist=10.0,
    chamfer_val=0.5
)

part = Box(P.length, P.width, P.thickness, align=(Align.MIN, Align.MIN, Align.MIN))

holes = [
    (P.edge_dist, P.edge_dist),
    (P.length - P.edge_dist, P.edge_dist),
    (P.edge_dist, P.width - P.edge_dist),
    (P.length - P.edge_dist, P.width - P.edge_dist)
]

for x, y in holes:
    part -= Pos(x, y, -P.thickness) * Cylinder(P.hole_d / 2, P.thickness * 3)

part = chamfer(part.edges(), P.chamfer_val)

save(part)
