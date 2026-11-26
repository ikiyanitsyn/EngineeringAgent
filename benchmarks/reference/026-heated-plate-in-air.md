```bash
ea make plate length=100 width=100 thickness=3 --name plate
ea analyze last -a thermal -m al_6061_t6 --heat zmin 5 --convect xmin+xmax+ymin+ymax+zmin+zmax 10 20
```
