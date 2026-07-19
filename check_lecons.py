#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""check_lecons.py — Verifie l'etat des lecons + flag les artefacts regime_shift."""
import json

ls = [json.loads(l) for l in open("lecons_apprises.jsonl", encoding="utf-8") if l.strip()]
print("total lecons:", len(ls))

artefacts = 0
print("\n--- regime_shift ---")
for e in ls:
    if e.get("type") == "regime_shift":
        h = e.get("hypothese", "")
        is_art = "{" in h
        if is_art:
            artefacts += 1
        print(f"  artefact={is_art} | {e.get('ts')} | {h[:90]}")

print(f"\n--- resume ({len(ls)} lecons) ---")
for e in ls:
    t = e.get("type", e.get("source", "?"))
    h = e.get("hypothese", e.get("decision", ""))
    print(f"  - {e.get('ts')} | {t} | {h[:75]}")

print(f"\nArtefacts regime_shift a nettoyer: {artefacts}")
