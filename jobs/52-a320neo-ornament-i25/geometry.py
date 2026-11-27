from build123d import *
from engagent.cad import params, save

P = params(
    fuselage_length=92.0,
    fuselage_dia=11.0,
    wingspan=88.0,
    loop_od=9.0,
    loop_id=4.5,
    loop_thick=3.2,
)

r_fuse = P.fuselage_dia / 2.0

# 1. Fuselage
cabin = Pos(42, 0, 0) * Rot(0, 90, 0) * Cylinder(r_fuse, 52)
nose = Pos(8, 0, 0) * Rot(0, -90, 0) * Cone(r_fuse, 1.5, 16) + Pos(0, 0, 0) * Sphere(1.5)
tail = Pos(80, 0, 0) * Rot(0, 90, 0) * Cone(r_fuse, 1.2, 24) + Pos(92, 0, 0) * Sphere(1.2)
fuselage = cabin + nose + tail

# 2. Main Wings & Sharklets
wing_pts = [(28, 0), (48, 44), (57, 44), (52, 0), (57, -44), (48, -44)]
wing = Pos(0, 0, -1.2) * extrude(Polygon(wing_pts), 2.4)
sharklet_r = Pos(52.5, 43.4, 2.0) * Box(7.0, 1.2, 6.5)
sharklet_l = Pos(52.5, -43.4, 2.0) * Box(7.0, 1.2, 6.5)

# 3. Empennage (Horizontal & Vertical Stabilizers)
h_stab_pts = [(74, 0), (82, 16), (88, 16), (86, 0), (88, -16), (82, -16)]
h_stab = Pos(0, 0, -0.9) * extrude(Polygon(h_stab_pts), 1.8)

v_fin_pts = [(66, 4), (80, 27), (89, 27), (90, 4)]
v_fin_raw = Pos(0, 0, -1.0) * extrude(Polygon(v_fin_pts), 2.0)
v_fin = Rot(90, 0, 0) * v_fin_raw

# 4. Turbofan Engines (Nacelles + Pylons)
pylon_r = Pos(40, 19, -1.5) * Box(8.0, 1.5, 4.0)
nacelle_r = Pos(39, 19, -3.5) * Rot(0, 90, 0) * Cylinder(3.25, 14.0)
intake_r = Pos(32, 19, -3.5) * Rot(0, 90, 0) * Cylinder(2.2, 4.0)
engine_r = (nacelle_r + pylon_r) - intake_r

pylon_l = Pos(40, -19, -1.5) * Box(8.0, 1.5, 4.0)
nacelle_l = Pos(39, -19, -3.5) * Rot(0, 90, 0) * Cylinder(3.25, 14.0)
intake_l = Pos(32, -19, -3.5) * Rot(0, 90, 0) * Cylinder(2.2, 4.0)
engine_l = (nacelle_l + pylon_l) - intake_l

# 5. Hanging Loop at CG
loop_sk = (
    Pos(42, 9.5) * (Circle(P.loop_od / 2.0) - Circle(P.loop_id / 2.0))
    + Pos(42, 6.0) * Rectangle(6.0, 4.0)
)
loop_raw = Pos(0, 0, -P.loop_thick / 2.0) * extrude(loop_sk, P.loop_thick)
loop = Rot(90, 0, 0) * loop_raw

# Combine all components
airplane = fuselage + wing + sharklet_r + sharklet_l + h_stab + v_fin + engine_r + engine_l + loop

# Shift strictly into +X, +Y, +Z region starting at the origin
bbox = airplane.bounding_box()
airplane = Pos(-bbox.min.X, -bbox.min.Y, -bbox.min.Z) * airplane

save(airplane)
