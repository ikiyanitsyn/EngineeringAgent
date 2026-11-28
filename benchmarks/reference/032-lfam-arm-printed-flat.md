```bash
ea make beam length=300 width=40 height=20 --name "lfam arm (flat)"
ea analyze last -m petg_gf30_lfam --fix xmin --force xmax 0,0,-200 --check "beam.cantilever_end_load P=200 L=300 E=7414 b=40 h=20"
```
