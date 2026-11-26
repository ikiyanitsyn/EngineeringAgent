```bash
ea make beam length=300 width=30 height=10 --name shelf
ea analyze last -m steel_generic --fix xmin --pressure zmax 0.0666667 --check "beam.cantilever_udl w=2 L=300 E=210000 nu=0.3 b=30 h=10"
```
