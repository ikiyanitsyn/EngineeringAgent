from build123d import *
from engagent.cad import params, save
P = params(stem_d=10.0, stem_len=20.0, collar_d=14.0, collar_h=3.0, knob_d=18.0, knob_h=10.0, chamfer=0.8)
a = (Align.CENTER, Align.CENTER, Align.MIN)
knob = Cylinder(P.knob_d / 2, P.knob_h, align=a)
knob = chamfer(knob.edges().group_by(Axis.Z)[-1], 1.5)   # easy to grip, prints without support
collar = Pos(0, 0, P.knob_h) * Cylinder(P.collar_d / 2, P.collar_h, align=a)
stem = Pos(0, 0, P.knob_h + P.collar_h) * Cylinder(P.stem_d / 2, P.stem_len, align=a)
stem = chamfer(stem.edges().group_by(Axis.Z)[-1], P.chamfer)
save(knob + collar + stem)
