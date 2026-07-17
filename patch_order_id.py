#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Patch pont_revolut.py: extraction robuste de l'order_id (réponse imbriquée 'data').
+ backfill de l'ordre ETH existant dans revolut_mirror.json avec son vrai ID."""
import os, json

DOSSIER = os.getcwd()
PONT = os.path.join(DOSSIER, "pont_revolut.py")
MIRROR = os.path.join(DOSSIER, "revolut_mirror.json")

# ---------- 1. Patch pont_revolut.py ----------
src = open(PONT, encoding="utf-8").read()

OLD = '''            resp = client.place_market_order(paire, "buy", quote_size=montant)
            record["order_id"] = resp.get("id") or resp.get("order_id")
            log.info("[LIVE] ordre achat place: %s", resp)'''

NEW = '''            resp = client.place_market_order(paire, "buy", quote_size=montant)
            _d = resp.get("data", resp) if isinstance(resp, dict) else resp
            _oid = None
            if isinstance(_d, dict):
                _oid = _d.get("id") or _d.get("order_id")
            elif isinstance(_d, list) and _d:
                _oid = _d[0].get("id") or _d[0].get("order_id")
            record["order_id"] = _oid
            log.info("[LIVE] ordre achat place (order_id=%s): %s", _oid, resp)'''

if OLD in src:
    src = src.replace(OLD, NEW)
    open(PONT, "w", encoding="utf-8").write(src)
    print("✅ pont_revolut.py patché (extraction order_id robuste)")
else:
    # peut-être déjà patché
    if "_oid = _d.get" in src:
        print("ℹ️ pont_revolut.py déjà patché (order_id robuste présent)")
    else:
        print("⚠️ bloc cible introuvable dans pont_revolut.py — patch NON appliqué")
        print("   (vérifie que le code correspond à la version attendue)")

# ---------- 2. Backfill revolut_mirror.json ----------
REAL_ETH_ORDER_ID = "eac95376-3575-4d8a-9420-80de7b80bd2f"
if os.path.exists(MIRROR):
    mir = json.load(open(MIRROR, encoding="utf-8"))
    achats = mir.get("achats", {})
    patched = 0
    for k, v in achats.items():
        if isinstance(v, dict) and v.get("order_id") in (None, "", "null") and "ETH" in str(v.get("symbole", "")):
            v["order_id"] = REAL_ETH_ORDER_ID
            patched += 1
            print(f"✅ backfill order_id pour {k} -> {REAL_ETH_ORDER_ID}")
    if patched:
        json.dump(mir, open(MIRROR, "w", encoding="utf-8"), indent=2, ensure_ascii=False)
        print(f"✅ revolut_mirror.json mis à jour ({patched} ordre(s) backfillé(s))")
    else:
        print("ℹ️ aucun achat ETH à backfiller (déjà renseigné ou introuvable)")
else:
    print("⚠️ revolut_mirror.json introuvable")

# ---------- 3. Vérification syntaxe ----------
print("\n=== Vérification syntaxe pont_revolut.py ===")
import py_compile
try:
    py_compile.compile(PONT, doraise=True)
    print("✅ pont_revolut.py compile sans erreur")
except py_compile.PyCompileError as e:
    print(f"❌ erreur de syntaxe: {e}")
