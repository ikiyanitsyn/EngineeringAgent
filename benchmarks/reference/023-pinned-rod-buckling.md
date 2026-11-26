```python
from build123d import *
from engagent.cad import save
save(Pos(200, 0, 0) * Rot(0, 90, 0) * Cylinder(5, 400))
```
```bash
ea make geometry.py --name rod
ea analyze last -a buckling -m al_6061_t6 --pin point:0,0,0 --slide point:400,0,0 y --slide point:400,0,0 z --slide point:0,5,0 z --force xmax -1000,0,0 --check "column.euler_buckling L=400 E=68900 D=10 ends=pinned_pinned"
```
