Plan: half the bar by symmetry (the first bending mode is symmetric): the mid-span face cannot move along the bar, the end face is held vertically only (free to rotate), and one end edge point stops sideways drift. No single-point holds in the bending direction (they create false local modes).
```bash
ea make beam length=250 width=20 height=10 --name "bar (half)"
ea analyze last -a modal -m steel_generic --slide xmax x --slide xmin z --slide point:0,0,0 y --check "beam.natural_frequency L=500 E=210000 b=20 h=10 density=7850 support=simply_supported"
```
