```bash
ea make plate length=100 width=100 thickness=200 --name "lfam block (printed upright)"
ea analyze last -m petg_gf30_lfam --slide zmin z --fix point:0,0,0 --slide point:100,0,0 y --force zmax 0,0,-20000 --check "axial.bar P=20000 L=200 A=10000 E=2492"
```
