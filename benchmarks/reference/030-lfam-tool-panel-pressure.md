Plan: half the panel by symmetry, printed flat (beads along X), ends held vertically, mid-span face cannot move along X.
```bash
ea make plate length=200 width=100 thickness=20 --name "lfam panel (half)"
ea analyze last -m petg_gf30_lfam --slide xmin z --slide xmax x --slide point:0,0,0 y --pressure zmax 0.1 --check "beam.simply_supported_udl w=10 L=400 E=7414 b=100 h=20"
```
