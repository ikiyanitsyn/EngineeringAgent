```python
from build123d import *
from engagent.cad import save
save(Pos(25, 0, 0) * Rot(0, 90, 0) * Cylinder(2.5, 50))
```
```bash
ea make geometry.py --name pin
ea analyze last -a thermal -m al_6061_t6 --temp xmin 80 --convect xmax+cyl:2.5 50 20
```
