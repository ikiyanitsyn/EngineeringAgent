```bash
ea make beam length=1000 section=i width=50 height=100 flange=6 web=4 --name "I-beam"
ea analyze last -m steel_generic --fix xmin --force xmax 0,0,-2000 --check "beam.cantilever_end_load P=2000 L=1000 E=210000 nu=0.3 b=50 h=100 tf=6 tw=4"
```
