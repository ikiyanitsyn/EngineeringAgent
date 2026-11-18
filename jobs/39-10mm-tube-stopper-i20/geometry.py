from build123d import *
from engagent.cad import params, save

# Parameters for a 10mm push connect stopper with pulling knob
P = params(
    tube_d=10.0,
    plug_len=18.0,
    flange_d=18.0,
    flange_len=4.0,
    knob_d=22.0,
    knob_len=12.0
)

# Build the stopper stepped cylinder along +X
plug = Cylinder(P.tube_d / 2.0, P.plug_len, align=(Align.MIN, Align.CENTER, Align.CENTER))
flange = Pos(P.plug_len, 0, 0) * Cylinder(P.flange_d / 2.0, P.flange_len, align=(Align.MIN, Align.CENTER, Align.CENTER))
knob = Pos(P.plug_len + P.flange_len, 0, 0) * Cylinder(P.knob_d / 2.0, P.knob_len, align=(Align.MIN, Align.CENTER, Align.CENTER))

part = plug + flange + knob
save(part)
