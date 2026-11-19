Plan: solid steel shaft along X, clamped at x=0, torque 100 N m about X on the far end.
```python
from build123d import *
from engagent.cad import save
save(Pos(100, 0, 0) * Rot(0, 90, 0) * Cylinder(10, 200))
```
```bash
ea make geometry.py --name shaft
ea analyze last -m steel_generic --fix xmin --moment xmax 100,0,0 --check "torsion.round_shaft T=100 L=200 D=20 E=210000 nu=0.3 -> twist"
```
