#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""evolution_check.py — Ce que l'agent a fait depuis hier (auto-apprentissage)."""
import os, sys, json
from datetime import datetime
os.chdir(os.path.dirname(os.path.abspath("paper_trading.py")) or ".")
sys.path.insert(0, ".")

print("=" * 70)
print(f"EVOLUTION DE L'AGENT — point {datetime.utcnow():%Y-%m-%d %H:%M} UTC")
print("=" * 70)

# 1. Lecons apprises (auto + manuelles)
print("\n--- 1. LECONS APPRISES ---")
try:
    lecons = [json.loads(l) for l in open("lecons_apprises.jsonl", encoding="utf-8") if l.strip()]
    print(f"Total: {len(lecons)} lecons")
    print("Dernieres 3:")
    for l in lecons[-3:]:
        src = l.get("source", "?")[:30]
        statut = l.get("statut", "?")
        dec = l.get("decision", l.get("hypothese", "?"))[:55]
        print(f"  [{statut[:8]:<8}] {src:<30} {dec}")
    # Lecons auto_sweep specifiquement
    auto = [l for l in lecons if "auto_sweep" in l.get("source", "")]
    print(f"\nLecons auto-apprises (auto_sweep): {len(auto)}")
    for l in auto[-3:]:
        print(f"  [{l.get('statut','?')[:8]}] {l.get('decision','?')[:70]}")
except Exception as e:
    print(f"  erreur: {e}")

# 2. strat_params.json (auto_sweep a-t-il change le seuil?)
print("\n--- 2. AUTO-SWEEP (seuil RSI auto-optimise) ---")
try:
    p = json.load(open("strat_params.json", encoding="utf-8"))
    print(f"  seuil RSI actuel: {p.get('rsi_achat', '?')}")
    print(f"  dernier sweep: {p.get('dernier_sweep', 'jamais')}")
    print(f"  dernier PnL total: {p.get('dernier_pnl_total', '?')}%")
except Exception as e:
    print(f"  erreur: {e}")

# 3. Reflection recente
print("\n--- 3. REFLECTION (insights Gemini/Perplexity) ---")
try:
    import subprocess
    r = subprocess.run(["tail", "-30", "reflection_log.jsonl"], capture_output=True, text=True)
    lines = [l for l in r.stdout.splitlines() if l.strip()]
    if lines:
        for l in lines[-2:]:
            try:
                d = json.loads(l)
                ts = d.get("ts", d.get("date", "?"))[:16]
                sugg = d.get("suggestions", d.get("insights", []))
                n = len(sugg) if isinstance(sugg, list) else "?"
                print(f"  {ts} - {n} suggestions/insights")
                if isinstance(sugg, list):
                    for s in sugg[-2:]:
                        txt = s.get("action", s.get("texte", str(s)))[:60] if isinstance(s, dict) else str(s)[:60]
                        print(f"    -> {txt}")
            except Exception:
                pass
    else:
        print("  log reflection vide")
except Exception as e:
    print(f"  erreur: {e}")

# 4. Portefeuille paper actuel
print("\n--- 4. PORTEFEUILLE PAPER ---")
try:
    import paper_trading as pt
    pf = pt.charger_portefeuille()
    solde = pf.get("solde", pf.get("capital", 0))
    pos = pf.get("positions", {})
    n_pos = sum(1 for v in pos.values() if isinstance(v, dict) and v.get("quantite", v.get("qty", 0)) > 0) if isinstance(pos, dict) else 0
    print(f"  Solde: {solde:.2f}€")
    print(f"  Positions ouvertes: {n_pos}")
    if isinstance(pos, dict):
        for sym, v in list(pos.items())[:5]:
            if isinstance(v, dict) and v.get("quantite", v.get("qty", 0)) > 0:
                print(f"    {sym}: {v.get('quantite', v.get('qty',0))} @ {v.get('prix_entree', v.get('prix', '?'))}€")
    pnl = solde - 1000
    print(f"  PnL: {pnl:+.2f}€ ({pnl/10:+.2f}%)")
except Exception as e:
    print(f"  erreur: {e}")

# 5. Trades recents (paper_trading.log)
print("\n--- 5. SIGNAUX/TRADES RECENTS ---")
try:
    import subprocess
    r = subprocess.run(["tail", "-100", "paper_trading.log"], capture_output=True, text=True)
    achat = [l for l in r.stdout.splitlines() if "ACHAT" in l]
    ventes = [l for l in r.stdout.splitlines() if "VENTE" in l or "ferm" in l.lower()]
    print(f"  ACHAT recents: {len(achat)} | VENTES/fermetures: {len(ventes)}")
    for l in achat[-3:]:
        print(f"    {l.strip()[-80:]}")
except Exception as e:
    print(f"  erreur: {e}")

# 6. Logs auto_sweep cron
print("\n--- 6. LOGS AUTO-SWEEP CRON ---")
try:
    import subprocess
    r = subprocess.run(["tail", "-20", "/tmp/auto_sweep_cron.log"], capture_output=True, text=True)
    if r.stdout.strip():
        print(r.stdout.strip()[-500:])
    else:
        print("  (log vide - premier cron a 00:10 UTC)")
except Exception as e:
    print(f"  erreur: {e}")

print("\n" + "=" * 70)
