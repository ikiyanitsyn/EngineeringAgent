```bash
ea make beam length=500 width=20 height=20 --name bar
ea analyze last -m steel_generic --slide xmin x --fix point:0,0,0 --slide point:0,20,0 z --t0 20 --dT 100 --check "thermal.free_expansion L=500 alpha=12e-6 dT=80 -> max_displacement"
```
