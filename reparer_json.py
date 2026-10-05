#!/usr/bin/env python3
"""Repare un fichier JSON corrompu (Extra data) en gardant le JSON valide."""
import json
import sys

fichier = sys.argv[1] if len(sys.argv) > 1 else "paper_trading.json"

try:
    with open(fichier, "r") as f:
        contenu = f.read()
    decoder = json.JSONDecoder()
    obj, fin = decoder.raw_decode(contenu)
    # Sauvegarde l'original
    with open(fichier + ".bak", "w") as f:
        f.write(contenu)
    # Reecrit le JSON propre
    with open(fichier, "w") as f:
        json.dump(obj, f, indent=2, ensure_ascii=False)
    print(f"Repare! {fichier}")
    print(f"  Positions: {len(obj.get('positions', []))}")
    print(f"  Liquides: {obj.get('liquidites', 0):.2f}EUR")
    print(f"  Trades fermes: {len(obj.get('trades_fermes', []))}")
    print(f"  Sauvegarde: {fichier}.bak")
except Exception as e:
    print(f"Erreur: {e}")
    sys.exit(1)
