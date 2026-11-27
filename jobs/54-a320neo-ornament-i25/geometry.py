from build123d import *
from engagent.cad import params, save

# A320neo Ornament Parametric Model
P = params(
    fuselage_length=80.0,
    fuselage_radius=6.0,
    wingspan=88.0,
    loop_outer_r=4.5,
    loop_inner_r=2.25,
)

# 1. Main Fuselage, Nose, and Tail
fuselage = Rot(0, 90, 0) * Cylinder(P.fuselage_radius, P.fuselage_length, align=(Align.CENTER, Align.CENTER, Align.MIN))
nose = Pos(-10, 0, 0) * Rot(0, -90, 0) * Cone(P.fuselage_radius, 0.5, 10.0, align=(Align.CENTER, Align.CENTER, Align.MIN))
tail = Pos(P.fuselage_length, 0, 0) * Rot(0, 90, 0) * Cone(P.fuselage_radius, 1.0, 15.0, align=(Align.CENTER, Align.CENTER, Align.MIN))
body = fuselage + nose + tail

# 2. Main Wings (Symmetric across Y=0, overlapping fuselage center)
wing_p1 = Polygon([(25, 0), (35, -P.wingspan / 2), (42, -P.wingspan / 2), (37, 0)])
wing_p2 = Polygon([(25, 0), (35, P.wingspan / 2), (42, P.wingspan / 2), (37, 0)])
wings_sketch = Sketch() + wing_p1 + wing_p2
wings = Pos(0, 0, -2.0) * extrude(wings_sketch, amount=3.0)

# 3. Twin Engines & Pylons
eng_left = Pos(30, -18, -4.5) * Rot(0, 90, 0) * Cylinder(3.5, 14.0)
eng_right = Pos(30, 18, -4.5) * Rot(0, 90, 0) * Cylinder(3.5, 14.0)
pylon_left = Pos(30, -18, -2.5) * Box(10.0, 2.0, 4.0)
pylon_right = Pos(30, 18, -2.5) * Box(10.0, 2.0, 4.0)
engines = eng_left + eng_right + pylon_left + pylon_right

# 4. Tail Assembly (Vertical & Horizontal Stabilizers)
fin_sketch = Sketch() + Polygon([(55, 0), (75, 0), (70, 22), (62, 22)])
fin = Pos(0, -0.9, 0) * Rot(90, 0, 0) * extrude(fin_sketch, amount=1.8)

h_stab_left = Polygon([(65, 0), (75, -18), (81, -18), (74, 0)])
h_stab_right = Polygon([(65, 0), (75, 18), (81, 18), (74, 0)])
h_stab_sketch = Sketch() + h_stab_left + h_stab_right
h_stab = Pos(0, 0, 1.0) * extrude(h_stab_sketch, amount=2.0)

# 5. Hanging Eyelet Ring (Fused to upper fuselage)
loop_cylinder = Pos(35, 0, P.fuselage_radius + 2.5) * Rot(90, 0, 0) * Cylinder(P.loop_outer_r, 3.0)
loop_hole = Pos(35, 0, P.fuselage_radius + 2.5) * Rot(90, 0, 0) * Cylinder(P.loop_inner_r, 4.0)
loop = loop_cylinder - loop_hole

# Fuse all features into ONE solid
ornament = body + wings + engines + fin + h_stab + loop
save(ornament)
