#!/usr/bin/env python3
"""Test si Ollama repond depuis le chat."""
import requests, time

print("1. Test connexion Ollama...")
try:
    r = requests.get("http://localhost:11434/api/tags", timeout=5)
    print(f"   Connexion OK, status {r.status_code}")
    models = [m["name"] for m in r.json().get("models", [])]
    print(f"   Modeles dispo: {models}")
except Exception as e:
    print(f"   ECHEC: {e}")
    exit(1)

print("\n2. Test chat qwen2.5:14b...")
try:
    t0 = time.time()
    r = requests.post("http://localhost:11434/api/chat", json={
        "model": "qwen2.5:14b",
        "messages": [{"role": "user", "content": "Dis bonjour en 1 phrase"}],
        "stream": False,
        "options": {"temperature": 0.5, "num_predict": 64}
    }, timeout=180)
    t1 = time.time()
    print(f"   Status: {r.status_code}")
    print(f"   Temps: {t1-t0:.1f}s")
    if r.status_code == 200:
        texte = r.json()["message"]["content"].strip()
        print(f"   Reponse: {texte[:200]}")
    else:
        print(f"   Erreur: {r.text[:300]}")
except Exception as e:
    print(f"   ECHEC: {e}")

print("\n3. Test chat mistral:7b (comparaison)...")
try:
    t0 = time.time()
    r = requests.post("http://localhost:11434/api/chat", json={
        "model": "mistral:7b",
        "messages": [{"role": "user", "content": "Dis bonjour en 1 phrase"}],
        "stream": False,
        "options": {"temperature": 0.5, "num_predict": 64}
    }, timeout=60)
    t1 = time.time()
    print(f"   Status: {r.status_code}")
    print(f"   Temps: {t1-t0:.1f}s")
    if r.status_code == 200:
        texte = r.json()["message"]["content"].strip()
        print(f"   Reponse: {texte[:200]}")
except Exception as e:
    print(f"   ECHEC: {e}")
