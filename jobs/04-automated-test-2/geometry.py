from build123d import *
from engagent.cad import params, save
P = params(arm=80.0, height=80.0, width=20.0, t=5.0, hole=4.5)
a = (Align.MIN, Align.MIN, Align.MIN)
part = Box(P.arm, P.width, P.t, align=a) + Box(P.t, P.width, P.height, align=a)
gusset = extrude(Plane.XZ * Polygon((P.t, P.t), (P.arm * 0.7, P.t), (P.t, P.height * 0.7), align=None), -P.t)
part += Pos(0, P.width / 2 - P.t / 2, 0) * gusset
for z in (P.height * 0.4, P.height * 0.8):
    part -= Pos(0, P.width / 2, z) * Rot(0, 90, 0) * Cylinder(P.hole / 2, P.t * 3)
save(part)
