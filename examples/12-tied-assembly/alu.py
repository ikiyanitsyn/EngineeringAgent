from build123d import *
from engagent.cad import save
save(Pos(50, 0, 0) * Box(50, 10, 10, align=(Align.MIN, Align.CENTER, Align.CENTER)))
