import requests, json, time

prompt = """Tu es un trader crypto expert avec 20 ans d'experience. Analyse ce marche et decide si il faut ouvrir une position.

PRIX ACTUELS:
BTCUSDT: 62000 EUR
ETHUSDT: 3200 EUR
SOLUSDT: 145 EUR

INDICATEURS:
BTC RSI: 28 (survente)
ETH RSI: 52 (neutre)
SOL RSI: 65 (neutre)
Fear & Greed Index: 74

GUIDE DES INDICATEURS (IMPORTANT):
- RSI < 30 = SURVENTE = signal d'ACHAT (le prix a trop bais, rebond probable)
- RSI > 70 = SURACHAT = signal de VENTE (le prix a trop monte, correction probable)
- RSI 30-70 = NEUTRE
- Fear & Greed 0-25 = PEUR EXTREME = bon moment pour ACHATER (contrarien)
- Fear & Greed 25-45 = PEUR = possible ACHATER
- Fear & Greed 45-55 = NEUTRE
- Fear & Greed 55-75 = GREED = prudent, risque de correction
- Fear & Greed 75-100 = GREED EXTREME = NE PAS ACHATER (risque de chute)

PORTFEUILLE: 0 positions ouvertes, 996EUR de liquidites.
Capital: 1000EUR. Risk par trade: 200EUR. TP: 2%, SL: -1%.

REGLES:
- Reponds en JSON exact: {"action": "ACHAT"|"RIEN", "symbole": "XXXUSDT", "raison": "..."}
- ACHAT si tu vois une opportunite avec CONFLUENCE (2+ signaux): survente (RSI<35), momentum haussier, rebond technique, ou tendance favorable
- Pas d'achat si RSI > 70 (surachat) ou Fear & Greed > 75 (Greed eleve)
- 1 seule crypto max
- Si rien d'interessant, repond RIEN
- Respecte le ratio risque/recompense minimum 2:1"""

print("=== TEST PROMPT CORRIGE avec qwen2.5:7b ===")
try:
    s = time.time()
    r = requests.post("http://localhost:11434/api/chat", json={
        "model": "qwen2.5:7b",
        "messages": [{"role": "user", "content": prompt}],
        "stream": False,
        "options": {"temperature": 0.3, "num_predict": 512}
    }, timeout=60)
    e = time.time() - s
    if r.status_code == 200:
        t = r.json()["message"]["content"]
        print(f"Temps: {e:.1f}s | {len(t.split())} mots | {len(t.split())/e:.1f} tok/s")
        print(f"Reponse:\n{t}")
    else:
        print(f"HTTP {r.status_code}")
except Exception as ex:
    print(f"Erreur: {ex}")
