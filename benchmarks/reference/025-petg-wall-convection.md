```bash
ea make plate length=50 width=50 thickness=5 --name wall
ea analyze last -a thermal -m petg --temp zmin 60 --convect zmax 10 20 --check "thermal.wall_conduction_convection k=0.21 L=5 h=10 T_fixed=60 T_ambient=20"
```
