```bash
ea make beam length=500 width=20 height=10 --name bar
ea analyze last -a modal -m steel_generic --slide plane:x=0 z --slide plane:x=500 z --pin point:0,0,0 --slide point:0,20,0 x --check "beam.natural_frequency L=500 E=210000 b=20 h=10 density=7850 ends=pinned_pinned"
```
