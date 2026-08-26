#!/usr/bin/env python3
"""Backtest comparatif: trend-following vs contrarien vs fixe 80EUR.
Teste les 3 approches sur les 350 trades fermes."""

import json
import sys

pf = json.load(open("paper_trading.json"))
trades = pf.get("trades_fermes", [])

if not trades:
    print("Aucun trade a analyser")
    sys.exit(1)

CAPITAL = 1000.0
RISK_BASE = 0.08
RISK_MAX = 0.50

def score_mult(score):
    if score <= 3: return 0.5
    elif score <= 6: return 1.0
    elif score <= 8: return 1.5
    else: return 2.0

# Trend-following (actuel): Greed = grosse position
def sentiment_trend(fg):
    if fg < 25: return 0.5, "Extreme Fear"
    elif fg < 45: return 0.8, "Fear"
    elif fg < 55: return 1.0, "Neutral"
    elif fg < 75: return 1.5, "Greed"
    else: return 2.0, "Extreme Greed"

# Contrarien: Fear = grosse position, Greed = petite position
def sentiment_contrarian(fg):
    if fg < 25: return 2.0, "Extreme Fear"
    elif fg < 45: return 1.5, "Fear"
    elif fg < 55: return 1.0, "Neutral"
    elif fg < 75: return 0.8, "Greed"
    else: return 0.5, "Extreme Greed"

def get_fg(t):
    fg = t.get("intel_fg")
    if fg is not None:
        return float(fg)
    return 50

def run_simulation(trades, sentiment_fn, label):
    capital = CAPITAL
    gains = 0
    count = 0
    gagnants = 0
    pertes = 0
    max_drawdown = 0
    peak = CAPITAL
    by_sent = {}
    details = []
    
    for t in trades:
        if t.get("montant_eur", 0) <= 0:
            continue
        pct = t.get("variation_pct", 0) / 100
        score = float(t.get("score", t.get("intel_score", 5)) or 5)
        fg = get_fg(t)
        
        s_mult, s_label = sentiment_fn(fg)
        sc_mult = score_mult(score)
        
        base = capital * RISK_BASE
        montant = base * s_mult * sc_mult
        montant = min(montant, capital * RISK_MAX)
        montant = max(montant, base)
        
        gain = montant * pct
        frais = montant * 0.001
        gain_net = gain - frais * 2
        capital += gain_net
        gains += gain_net
        count += 1
        
        if gain_net > 0:
            gagnants += 1
        else:
            pertes += 1
        
        peak = max(peak, capital)
        dd = (capital - peak) / peak * 100
        max_drawdown = min(max_drawdown, dd)
        
        if s_label not in by_sent:
            by_sent[s_label] = {"trades": 0, "gains": 0, "gagnants": 0, "pertes_max": 0}
        by_sent[s_label]["trades"] += 1
        by_sent[s_label]["gains"] += gain_net
        if gain_net > 0:
            by_sent[s_label]["gagnants"] += 1
        by_sent[s_label]["pertes_max"] = min(by_sent[s_label]["pertes_max"], gain_net)
        
        details.append((t.get("symbole","?"), pct, s_label, gain_net, montant))
    
    wr = gagnants / count * 100 if count else 0
    avg = gains / count if count else 0
    
    return {
        "label": label,
        "capital": capital,
        "gains": gains,
        "rendement": gains / CAPITAL * 100,
        "trades": count,
        "gagnants": gagnants,
        "pertes": pertes,
        "win_rate": wr,
        "gain_moyen": avg,
        "max_drawdown": max_drawdown,
        "by_sent": by_sent,
        "details": details,
    }

# --- Lancer les 3 simulations ---
fixe = run_simulation(trades, lambda fg: (1.0, "N/A"), "Fixe 80EUR")
trend = run_simulation(trades, sentiment_trend, "Trend-following")
contrarian = run_simulation(trades, sentiment_contrarian, "Contrarien")

# --- Affichage ---
print("=" * 75)
print("  BACKTEST COMPARATIF: Fixe vs Trend-following vs Contrarien")
print("=" * 75)
print()
print(f"  Trades analyses: {len(trades)}")
print()

print("--- RESULTATS GLOBAUX ---")
print(f"  {'Metrique':<25} {'Fixe 80EUR':>15} {'Trend':>15} {'Contrarien':>15}")
print(f"  {'-'*70}")
print(f"  {'Capital final':<25} {fixe['capital']:>13.2f}EUR {trend['capital']:>13.2f}EUR {contrarian['capital']:>13.2f}EUR")
print(f"  {'Gain/perte net':<25} {fixe['gains']:>+13.2f}EUR {trend['gains']:>+13.2f}EUR {contrarian['gains']:>+13.2f}EUR")
print(f"  {'Rendement':<25} {fixe['rendement']:>+13.2f}% {trend['rendement']:>+13.2f}% {contrarian['rendement']:>+13.2f}%")
print(f"  {'Win rate':<25} {fixe['win_rate']:>13.1f}% {trend['win_rate']:>13.1f}% {contrarian['win_rate']:>13.1f}%")
print(f"  {'Gain moyen/trade':<25} {fixe['gain_moyen']:>+13.2f}EUR {trend['gain_moyen']:>+13.2f}EUR {contrarian['gain_moyen']:>+13.2f}EUR")
print(f"  {'Max drawdown':<25} {fixe['max_drawdown']:>13.2f}% {trend['max_drawdown']:>13.2f}% {contrarian['max_drawdown']:>13.2f}%")
print()

# Performance par sentiment pour chaque approche
for sim, name in [(trend, "TREND-FOLLOWING"), (contrarian, "CONTRARIEN")]:
    print(f"--- PERFORMANCE PAR SENTIMENT ({name}) ---")
    print(f"  {'Sentiment':<15} {'Trades':>7} {'Gains':>10} {'Win%':>7} {'Pire trade':>11}")
    print(f"  {'-'*55}")
    for s in ["Extreme Fear", "Fear", "Neutral", "Greed", "Extreme Greed"]:
        if s in sim["by_sent"]:
            d = sim["by_sent"][s]
            wr = d["gagnants"] / d["trades"] * 100 if d["trades"] else 0
            print(f"  {s:<15} {d['trades']:>7} {d['gains']:>+9.2f}EUR {wr:>6.1f}% {d['pertes_max']:>+9.2f}EUR")
    print()

# Simuler avec un Fear & Greed realiste (pas tous a 50)
# Le F&G varie entre 25 et 85 en general. On simule avec des valeurs distribuees.
print("=" * 75)
print("  SIMULATION AVEC F&G REALISTE (25-85)")
print("=" * 75)
print()
print("  La plupart des trades n'ont pas de F&G stocke (default=50).")
print("  On simule avec des valeurs distribuees pour tester les extremes.")
print()

# Simuler avec F&G aleatoire mais realiste
import random
random.seed(42)

fg_values = []
for _ in range(len(trades)):
    # Distribution realiste: 10% Extreme Fear, 20% Fear, 30% Neutral, 30% Greed, 10% Extreme Greed
    r = random.random()
    if r < 0.10: fg_values.append(random.randint(10, 24))
    elif r < 0.30: fg_values.append(random.randint(25, 44))
    elif r < 0.60: fg_values.append(random.randint(45, 55))
    elif r < 0.90: fg_values.append(random.randint(56, 74))
    else: fg_values.append(random.randint(75, 95))

# Creer des trades modifies avec F&G distribue
trades_modifies = []
for i, t in enumerate(trades):
    t2 = dict(t)
    t2["intel_fg"] = fg_values[i]
    trades_modifies.append(t2)

fixe2 = run_simulation(trades_modifies, lambda fg: (1.0, "N/A"), "Fixe 80EUR")
trend2 = run_simulation(trades_modifies, sentiment_trend, "Trend-following")
contrarian2 = run_simulation(trades_modifies, sentiment_contrarian, "Contrarien")

print("--- RESULTATS AVEC F&G DISTRIBUE ---")
print(f"  {'Metrique':<25} {'Fixe 80EUR':>15} {'Trend':>15} {'Contrarien':>15}")
print(f"  {'-'*70}")
print(f"  {'Capital final':<25} {fixe2['capital']:>13.2f}EUR {trend2['capital']:>13.2f}EUR {contrarian2['capital']:>13.2f}EUR")
print(f"  {'Gain/perte net':<25} {fixe2['gains']:>+13.2f}EUR {trend2['gains']:>+13.2f}EUR {contrarian2['gains']:>+13.2f}EUR")
print(f"  {'Rendement':<25} {fixe2['rendement']:>+13.2f}% {trend2['rendement']:>+13.2f}% {contrarian2['rendement']:>+13.2f}%")
print(f"  {'Max drawdown':<25} {fixe2['max_drawdown']:>13.2f}% {trend2['max_drawdown']:>13.2f}% {contrarian2['max_drawdown']:>13.2f}%")
print()

for sim, name in [(trend2, "TREND-FOLLOWING"), (contrarian2, "CONTRARIEN")]:
    print(f"--- F&G DISTRIBUE: {name} ---")
    print(f"  {'Sentiment':<15} {'Trades':>7} {'Gains':>10} {'Win%':>7} {'Montant moy':>12}")
    print(f"  {'-'*55}")
    for s in ["Extreme Fear", "Fear", "Neutral", "Greed", "Extreme Greed"]:
        if s in sim["by_sent"]:
            d = sim["by_sent"][s]
            wr = d["gagnants"] / d["trades"] * 100 if d["trades"] else 0
            print(f"  {s:<15} {d['trades']:>7} {d['gains']:>+9.2f}EUR {wr:>6.1f}%")
    print()

print("=" * 75)
print("  CONCLUSION")
print("=" * 75)
print()
if contrarian["gains"] > trend["gains"] and contrarian["gains"] > fixe["gains"]:
    print(f"  CONTRARIEN est le meilleur avec les donnees reelles")
    print(f"  +{contrarian['gains'] - fixe['gains']:.2f}EUR vs fixe")
elif trend["gains"] > contrarian["gains"] and trend["gains"] > fixe["gains"]:
    print(f"  TREND-FOLLOWING est le meilleur avec les donnees reelles")
    print(f"  +{trend['gains'] - fixe['gains']:.2f}EUR vs fixe")
else:
    print(f"  FIXE 80EUR est le meilleur (le sizing dynamique n'aide pas)")

if contrarian2["gains"] > trend2["gains"]:
    print(f"  Avec F&G distribue: CONTRARIEN > Trend (+{contrarian2['gains'] - trend2['gains']:.2f}EUR)")
else:
    print(f"  Avec F&G distribue: Trend > CONTRARIEN (+{trend2['gains'] - contrarian2['gains']:.2f}EUR)")
print("=" * 75)
