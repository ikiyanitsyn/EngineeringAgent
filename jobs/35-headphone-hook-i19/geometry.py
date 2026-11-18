from build123d import *
from engagent.cad import params, save
P = params(width=30.0, thickness=3.0, plate=40.0, drop=40.0, reach=35.0, lip=10.0, hole=4.5)
plate = Box(P.plate, P.width, P.thickness, align=(Align.MIN, Align.MIN, Align.MIN))
plate -= Pos(P.plate / 2, P.width / 2, 0) * Cylinder(P.hole / 2, P.thickness * 3)
stem = Box(P.thickness, P.width, P.drop, align=(Align.MIN, Align.MIN, Align.MAX))
arm = Pos(0, 0, -P.drop) * Box(P.reach, P.width, P.thickness, align=(Align.MIN, Align.MIN, Align.MIN))
lip = Pos(P.reach - P.thickness, 0, -P.drop) * Box(P.thickness, P.width, P.lip, align=(Align.MIN, Align.MIN, Align.MIN))
part = plate + stem + arm + lip
part = fillet(part.edges().filter_by(Axis.Y), 1.0)
save(part)
