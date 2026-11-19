Plan: half model by symmetry - end held fully, mid-span face cannot move along the beam, half the load on it.
```bash
ea make beam length=200 width=20 height=20 --name "fixed-fixed beam (half)"
ea analyze last -m al_6061_t6 --fix xmin --slide xmax x --force xmax 0,0,-500 --check "beam.fixed_fixed_center_load P=1000 L=400 E=68900 nu=0.33 b=20 h=20"
```
