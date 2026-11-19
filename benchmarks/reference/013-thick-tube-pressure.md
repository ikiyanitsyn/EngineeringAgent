Plan: quarter-free model: full tube along Z, ends free to slide axially (open ends), held against rigid motion by symmetry planes.
```python
from build123d import *
from engagent.cad import save
save(Cylinder(50, 200, align=(Align.CENTER, Align.CENTER, Align.MIN)) - Cylinder(30, 200, align=(Align.CENTER, Align.CENTER, Align.MIN)))
```
```bash
ea make geometry.py --name tube
ea analyze last -m steel_generic --slide zmin z --fix point:50,0,0 --slide point:0,50,0 x --pressure cyl:30 100 --check "pressure.thick_cylinder p=100 ri=30 ro=50 -> hoop_stress_inner"
```
