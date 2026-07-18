#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""apprentissage.py — Affiche tout ce que l'IA a appris."""
import os, json

D = os.path.dirname(os.path.abspath(__file__)) if os.path.isdir(os.path.join(os.getcwd(), "reflection_gemini.py")) else os.getcwd()

def load_jsonl(path):
    out = []
    try:
        with open(path, encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if line:
                    out.append(json.loads(line))
    except Exception:
        pass
    return out

print("=" * 64)
print("🧠 APPRENTISSAGE DE L'IA")
print("=" * 64)

# 1) LEÇONS APPRISES
print("\n## 1. LEÇONS APPRISES (hypothèses rejetées par backtest)\n")
lecons = load_jsonl(os.path.join(D, "lecons_apprises.jsonl"))
if not lecons:
    print("  (aucune leçon encore)")
for i, l in enumerate(lecons, 1):
    print(f"  [{i}] {l.get('hypothese','?')}")
    print(f"      Test    : {l.get('test','?')}")
    print(f"      Résultat: {l.get('resultat','?')}")
    print(f"      Raison  : {l.get('raison','?')}")
    print(f"      Décision: {l.get('decision','?')}  [{l.get('statut','?')}]\n")

# 2) RÉFLEXIONS (synthèses + insights + suggestions)
print("## 2. RÉFLEXIONS QUOTIDIENNES\n")
refls = load_jsonl(os.path.join(D, "reflection_log.jsonl"))
if not refls:
    print("  (aucune réflexion encore)")
for r in refls[-6:]:  # 6 dernières
    ts = r.get("ts") or r.get("date") or "?"
    a = r.get("analyse") or r
    if isinstance(a, str):
        try:
            a = json.loads(a)
        except Exception:
            a = {"synthese": a}
    print(f"  📅 {ts}")
    summ = r.get("ctx_summary", {})
    if summ:
        print(f"     Capital {summ.get('capital','?')}€ | PnL {summ.get('pnl','?')}€ | trades jour {summ.get('trades_jour','?')}")
    print(f"     Synthèse: {a.get('synthese','?')}")
    ins = a.get("insights", [])
    if ins:
        print("     Insights:")
        for x in ins:
            print(f"       - {x}")
    sugg = a.get("suggestions", [])
    if sugg:
        print("     Suggestions:")
        for x in sugg:
            print(f"       → {x}")
    pri = a.get("priorite") or a.get("PRIORITE")
    if pri:
        print(f"     ⭐ Priorité: {pri}")
    print()

# 3) ACTIONS EXÉCUTÉES
print("## 3. ACTIONS EXÉCUTÉES (boucle fermée)\n")
acts = load_jsonl(os.path.join(D, "actions_executor_log.jsonl"))
if not acts:
    print("  (aucune action exécutée)")
for a in acts[-10:]:
    ts = a.get("ts") or a.get("date") or "?"
    print(f"  📅 {ts}")
    for k in ("action", "type", "strategie", "actif"):
        if k in a:
            print(f"     {k}: {a[k]}")
    for k in ("details", "raison", "resultat"):
        if k in a:
            print(f"     {k}: {a[k]}")
    print()

# 4) STRATÉGIES DÉSACTIVÉES (auto-pruning)
print("## 4. STRATÉGIES COUPÉES (auto-pruning)\n")
try:
    pr = json.load(open(os.path.join(D, "strategies_desactivees.json"), encoding="utf-8"))
    desact = pr.get("desactivees", {})
    if not desact:
        print("  (aucune stratégie désactivée)")
    for k, v in desact.items():
        if isinstance(v, dict) and v.get("disabled"):
            print(f"  ✂️ {k}")
            if v.get("raison"):
                print(f"     raison: {v['raison']}")
            if v.get("desactive_le"):
                print(f"     le: {v['desactive_le']}")
except Exception as e:
    print(f"  (indispo: {e})")

print("\n" + "=" * 64)
