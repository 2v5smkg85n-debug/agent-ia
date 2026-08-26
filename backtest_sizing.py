#!/usr/bin/env python3
"""Backtest du sizing dynamique sentiment + score.
Compare les rendements avec taille fixe 80EUR vs sizing dynamique."""

import json
import sys

# Charger les trades fermes
pf = json.load(open("paper_trading.json"))
trades = pf.get("trades_fermes", [])

if not trades:
    print("Aucun trade a analyser")
    sys.exit(1)

# --- Parametres du sizing dynamique (identiques au code live) ---
RISK_BASE = 0.08    # 8% plancher
RISK_MAX = 0.50     # 50% plafond
CAPITAL = 1000.0   # capital de reference pour le calcul

# Simuler un capital qui evolue
def sentiment_mult(fg):
    if fg < 25: return 0.5, "Extreme Fear"
    elif fg < 45: return 0.8, "Fear"
    elif fg < 55: return 1.0, "Neutral"
    elif fg < 75: return 1.5, "Greed"
    else: return 2.0, "Extreme Greed"

def score_mult(score):
    if score <= 3: return 0.5
    elif score <= 6: return 1.0
    elif score <= 8: return 1.5
    else: return 2.0

# Recuperer le sentiment a la date du trade (approximation: on utilise la valeur stockee si dispo)
# Sinon on utilise 50 (neutral) par defaut
def get_fg_for_trade(t):
    # Si le trade a un champ intel_fg, l'utiliser
    fg = t.get("intel_fg")
    if fg is not None:
        return float(fg)
    return 50  # neutral par defaut

# --- Simulation 1: Taille fixe 80EUR ---
capital_fixe = CAPITAL
gains_fixe = 0
trades_fixe = 0
gagnants_fixe = 0
for t in trades:
    if t.get("montant_eur", 0) <= 0:
        continue
    # Rendement proportionnel: gain_eur / montant_eur = rendement reel
    # On recalcule avec 80EUR fixe
    pct = t.get("variation_pct", 0) / 100
    gain_80 = 80 * pct
    frais_80 = 80 * 0.001  # 0.1% aller
    gain_net = gain_80 - frais_80 * 2  # aller-retour
    capital_fixe += gain_net
    gains_fixe += gain_net
    trades_fixe += 1
    if gain_net > 0:
        gagnants_fixe += 1

# --- Simulation 2: Sizing dynamique sentiment + score ---
capital_dyn = CAPITAL
gains_dyn = 0
trades_dyn = 0
gagnants_dyn = 0
details_dyn = []

for t in trades:
    if t.get("montant_eur", 0) <= 0:
        continue
    pct = t.get("variation_pct", 0) / 100
    score = t.get("score", t.get("intel_score", 5))
    if score is None:
        score = 5
    score = float(score)
    
    fg = get_fg_for_trade(t)
    s_mult, s_label = sentiment_mult(fg)
    sc_mult = score_mult(score)
    
    # Taille dynamique
    base = capital_dyn * RISK_BASE
    montant = base * s_mult * sc_mult
    montant = min(montant, capital_dyn * RISK_MAX)
    montant = max(montant, base)
    
    # Gain/perte proportionnel
    gain = montant * pct
    frais = montant * 0.001
    gain_net = gain - frais * 2
    capital_dyn += gain_net
    gains_dyn += gain_net
    trades_dyn += 1
    if gain_net > 0:
        gagnants_dyn += 1
    
    details_dyn.append({
        "symbole": t.get("symbole", "?"),
        "date": t.get("date_fermeture", "?"),
        "variation_pct": t.get("variation_pct", 0),
        "gain_eur_reel": t.get("gain_eur", 0),
        "montant_reel": t.get("montant_eur", 0),
        "montant_dyn": montant,
        "fg": fg,
        "sentiment": s_label,
        "s_mult": s_mult,
        "score": score,
        "sc_mult": sc_mult,
        "gain_dyn": gain_net,
        "raison": t.get("raison", "?"),
    })

# --- Affichage ---
print("=" * 70)
print("  BACKTEST SIZING DYNAMIQUE vs TAILLE FIXE 80EUR")
print("=" * 70)
print()
print(f"  Trades analyses: {len(trades)}")
print(f"  Capital initial: {CAPITAL:.0f}EUR")
print()

print("--- RESULTATS GLOBAUX ---")
print(f"  {'Metrique':<25} {'Fixe 80EUR':>15} {'Dynamique':>15}")
print(f"  {'-'*55}")
print(f"  {'Capital final':<25} {capital_fixe:>13.2f}EUR {capital_dyn:>13.2f}EUR")
print(f"  {'Gain/perte net':<25} {gains_fixe:>+13.2f}EUR {gains_dyn:>+13.2f}EUR")
print(f"  {'Rendement':<25} {(gains_fixe/CAPITAL)*100:>+13.2f}% {(gains_dyn/CAPITAL)*100:>+13.2f}%")
print(f"  {'Win rate':<25} {(gagnants_fixe/trades_fixe*100 if trades_fixe else 0):>13.1f}% {(gagnants_dyn/trades_dyn*100 if trades_dyn else 0):>13.1f}%")
print(f"  {'Gain moyen/trade':<25} {(gains_fixe/trades_fixe if trades_fixe else 0):>+13.2f}EUR {(gains_dyn/trades_dyn if trades_dyn else 0):>+13.2f}EUR")
print()

# Analyser par sentiment
print("--- PERFORMANCE PAR SENTIMENT (dynamique) ---")
by_sent = {}
for d in details_dyn:
    s = d["sentiment"]
    if s not in by_sent:
        by_sent[s] = {"trades": 0, "gains": 0, "gagnants": 0, "montant_moy": 0}
    by_sent[s]["trades"] += 1
    by_sent[s]["gains"] += d["gain_dyn"]
    by_sent[s]["montant_moy"] += d["montant_dyn"]
    if d["gain_dyn"] > 0:
        by_sent[s]["gagnants"] += 1

print(f"  {'Sentiment':<15} {'Trades':>7} {'Gains':>10} {'Win%':>7} {'Montant moy':>12}")
print(f"  {'-'*55}")
for s in ["Extreme Fear", "Fear", "Neutral", "Greed", "Extreme Greed"]:
    if s in by_sent:
        d = by_sent[s]
        wr = d["gagnants"] / d["trades"] * 100 if d["trades"] else 0
        moy = d["montant_moy"] / d["trades"] if d["trades"] else 0
        print(f"  {s:<15} {d['trades']:>7} {d['gains']:>+9.2f}EUR {wr:>6.1f}% {moy:>10.0f}EUR")

# Analyser par score
print()
print("--- PERFORMANCE PAR SCORE (dynamique) ---")
by_score = {}
for d in details_dyn:
    sc = d["score"]
    bucket = f"{int(sc)}" if sc <= 10 else "10+"
    if bucket not in by_score:
        by_score[bucket] = {"trades": 0, "gains": 0, "gagnants": 0, "montant_moy": 0}
    by_score[bucket]["trades"] += 1
    by_score[bucket]["gains"] += d["gain_dyn"]
    by_score[bucket]["montant_moy"] += d["montant_dyn"]
    if d["gain_dyn"] > 0:
        by_score[bucket]["gagnants"] += 1

print(f"  {'Score':>6} {'Trades':>7} {'Gains':>10} {'Win%':>7} {'Montant moy':>12}")
print(f"  {'-'*55}")
for sc in sorted(by_score.keys(), key=float):
    d = by_score[sc]
    wr = d["gagnants"] / d["trades"] * 100 if d["trades"] else 0
    moy = d["montant_moy"] / d["trades"] if d["trades"] else 0
    print(f"  {sc:>6} {d['trades']:>7} {d['gains']:>+9.2f}EUR {wr:>6.1f}% {moy:>10.0f}EUR")

# Top 10 trades dynamiques
print()
print("--- TOP 10 TRADES (gain dynamique) ---")
top = sorted(details_dyn, key=lambda x: x["gain_dyn"], reverse=True)[:10]
print(f"  {'Symbole':<12} {'Var%':>7} {'Sentiment':<15} {'Score':>6} {'Montant':>9} {'Gain dyn':>10}")
print(f"  {'-'*65}")
for d in top:
    print(f"  {d['symbole']:<12} {d['variation_pct']:>+6.2f}% {d['sentiment']:<15} {d['score']:>6.0f} {d['montant_dyn']:>8.0f}EUR {d['gain_dyn']:>+9.2f}EUR")

# Bottom 10
print()
print("--- BOTTOM 10 TRADES (perte dynamique) ---")
bottom = sorted(details_dyn, key=lambda x: x["gain_dyn"])[:10]
print(f"  {'Symbole':<12} {'Var%':>7} {'Sentiment':<15} {'Score':>6} {'Montant':>9} {'Gain dyn':>10}")
print(f"  {'-'*65}")
for d in bottom:
    print(f"  {d['symbole']:<12} {d['variation_pct']:>+6.2f}% {d['sentiment']:<15} {d['score']:>6.0f} {d['montant_dyn']:>8.0f}EUR {d['gain_dyn']:>+9.2f}EUR")

print()
print("=" * 70)
if gains_dyn > gains_fixe:
    print(f"  CONCLUSION: Le sizing dynamique est GAGNANT")
    print(f"  +{gains_dyn - gains_fixe:.2f}EUR vs fixe ({(gains_dyn/CAPITAL)*100:.2f}% vs {(gains_fixe/CAPITAL)*100:.2f}%)")
else:
    print(f"  CONCLUSION: Le sizing dynamique est PERDANT")
    print(f"  {gains_dyn - gains_fixe:.2f}EUR vs fixe ({(gains_dyn/CAPITAL)*100:.2f}% vs {(gains_fixe/CAPITAL)*100:.2f}%)")
    print(f"  Le sizing dynamique agrandit les pertes sur les mauvais trades.")
print("=" * 70)
