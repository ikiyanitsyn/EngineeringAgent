```python
from build123d import *
from engagent.cad import save
save(Box(200, 50, 5, align=(Align.MIN, Align.MIN, Align.MIN)) - Pos(100, 25, 0) * Cylinder(5, 20))
```
```bash
ea make geometry.py --name plate
ea analyze last -m steel_generic --slide xmin x --fix point:0,0,0 --slide point:0,50,0 z --force xmax 10000,0,0 --check "kt.plate_hole_tension P=10000 w=50 d=10 t=5 -> peak_stress@max_von_mises tol=0.06"
```
