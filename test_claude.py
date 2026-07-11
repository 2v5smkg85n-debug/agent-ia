#!/usr/bin/env python3
"""Test de la clé API Claude. Decouvre les modeles disponibles puis fait un mini-appel."""
import json
import urllib.request
import urllib.error

# 1. Charger la cle depuis .env
key = None
try:
    for line in open(".env"):
        line = line.strip()
        if line.startswith("ANTHROPIC_API_KEY="):
            key = line.split("=", 1)[1].strip().strip('"').strip("'")
            break
except FileNotFoundError:
    print("ERREUR: fichier .env introuvable.")
    raise SystemExit(1)

if not key:
    print("ERREUR: ANTHROPIC_API_KEY non trouve dans .env")
    raise SystemExit(1)

print(f"Cle detectee: {key[:14]}...{key[-4:]}")

headers = {
    "x-api-key": key,
    "anthropic-version": "2023-06-01",
    "content-type": "application/json",
}

# 2. Lister les modeles disponibles
print("\nModeles disponibles :")
try:
    req = urllib.request.Request("https://api.anthropic.com/v1/models?limit=50", headers=headers)
    with urllib.request.urlopen(req, timeout=20) as r:
        models = json.load(r).get("data", [])
    for m in models:
        print(f"  - {m.get('id')}")
except urllib.error.HTTPError as e:
    print(f"ECHEC listing modeles HTTP {e.code}: {e.read().decode()[:200]}")
    raise SystemExit(1)
except Exception as e:
    print(f"ECHEC listing modeles: {e}")
    raise SystemExit(1)

# 3. Choisir un modele economique (haiku si possible, sinon le dernier)
choix = None
for m in models:
    mid = m.get("id", "")
    if "haiku" in mid.lower():
        choix = mid
        break
if not choix and models:
    choix = models[-1].get("id")

if not choix:
    print("Aucun modele trouve.")
    raise SystemExit(1)

print(f"\nTest avec le modele: {choix}")

# 4. Mini-appel
body = json.dumps({
    "model": choix,
    "max_tokens": 20,
    "messages": [{"role": "user", "content": "Dis juste: OK"}],
}).encode()
req = urllib.request.Request("https://api.anthropic.com/v1/messages", data=body, headers=headers)

try:
    with urllib.request.urlopen(req, timeout=30) as r:
        data = json.load(r)
    text = data["content"][0]["text"]
    usage = data.get("usage", {})
    print("=" * 50)
    print("SUCCES — Claude repond: " + text)
    print(f"Modele: {data.get('model', choix)}")
    print(f"Tokens: input={usage.get('input_tokens')} output={usage.get('output_tokens')}")
    print("Ta cle Claude fonctionne.")
    print("=" * 50)
except urllib.error.HTTPError as e:
    err = e.read().decode()
    print("=" * 50)
    print(f"ECHEC HTTP {e.code}: {err[:300]}")
    print("=" * 50)
except Exception as e:
    print(f"ECHEC: {e}")
