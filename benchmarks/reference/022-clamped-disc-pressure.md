```python
from build123d import *
from engagent.cad import save
save(Cylinder(100, 5, align=(Align.CENTER, Align.CENTER, Align.MIN)))
```
```bash
ea make geometry.py --name disc
ea analyze last -m steel_generic --fix cyl:100 --pressure zmax 0.1 --check "plate.circular_uniform q=0.1 r=100 t=5 E=210000 nu=0.3 edges=clamped -> deflection"
```
