from build123d import *
from engagent.cad import params, save

P = params(length=25.0, diameter=10.0, knob_dia=18.0, knob_thick=6.0)

shaft = Cylinder(P.diameter / 2, P.length, align=(Align.MIN, Align.CENTER, Align.CENTER))
ridge1 = Pos(P.length - 8, 0, 0) * Cylinder((P.diameter / 2) + 0.6, 2.0, align=(Align.MIN, Align.CENTER, Align.CENTER))
ridge2 = Pos(P.length - 14, 0, 0) * Cylinder((P.diameter / 2) + 0.6, 2.0, align=(Align.MIN, Align.CENTER, Align.CENTER))
knob = Cylinder(P.knob_dia / 2, P.knob_thick, align=(Align.MIN, Align.CENTER, Align.CENTER))

part = shaft + ridge1 + ridge2 + knob

save(part)
