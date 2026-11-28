Plan: modelled as printed - standing along Z, so its length runs through the layers (E3).
```python
from build123d import *
from engagent.cad import save
save(Box(40, 20, 300, align=(Align.MIN, Align.MIN, Align.MIN)))
```
```bash
ea make geometry.py --name "lfam arm (upright)"
ea analyze last -m petg_gf30_lfam --fix zmin --force zmax 0,50,0 --check "beam.cantilever_end_load P=50 L=300 E=2492 b=40 h=20"
```
