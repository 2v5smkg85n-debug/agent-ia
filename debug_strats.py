#!/usr/bin/env python3
# -*- coding: utf-8 -*-
import traceback
print("=== debug strategies_gagnantes_par_actif ===")
try:
    from signaux_gagnants import strategies_gagnantes_par_actif
    d = strategies_gagnantes_par_actif()
    print("type:", type(d))
    if not d:
        print("RETOUR VIDE (falsy)")
    else:
        print("nb actifs:", len(d))
        print("keys:", list(d.keys()))
        a0 = list(d.keys())[0]
        v = d[a0]
        print("exemple", a0, "-> type:", type(v))
        print("valeur (200):", str(v)[:200])
except Exception as e:
    print("EXCEPTION:")
    traceback.print_exc()
print("=== fin ===")
