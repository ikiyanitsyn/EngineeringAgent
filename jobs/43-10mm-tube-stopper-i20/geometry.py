from build123d import *
from engagent.cad import params, save

P = params(length=35.0, tube_d=10.0, knob_d=18.0, knob_l=10.0)

with BuildPart() as p:
    Cylinder(radius=P.knob_d/2, height=P.knob_l, align=(Align.MIN, Align.CENTER, Align.CENTER))
    with Locations((P.knob_l, 0, 0)):
        Cylinder(radius=P.tube_d/2, height=P.length - P.knob_l, align=(Align.MIN, Align.CENTER, Align.CENTER))
    with Locations((P.knob_l + 8.0, 0, 0)):
        Cylinder(radius=(P.tube_d/2) - 0.8, height=3.0, align=(Align.MIN, Align.CENTER, Align.CENTER))

part = p.part
save(part)
