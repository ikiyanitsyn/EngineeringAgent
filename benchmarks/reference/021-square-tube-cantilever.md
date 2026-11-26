```python
from build123d import *
from engagent.cad import save
s = Box(600, 40, 40, align=(Align.MIN, Align.CENTER, Align.CENTER)) - Box(600, 34, 34, align=(Align.MIN, Align.CENTER, Align.CENTER))
save(s)
```
```bash
ea make geometry.py --name tube
ea analyze last -m al_6061_t6 --fix xmin --force xmax 0,0,-500 --check "beam.cantilever_end_load P=500 L=600 E=68900 nu=0.33 I=101972 A=444 c=20"
```
