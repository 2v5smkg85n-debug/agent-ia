#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""rapport_matin.py — Bilan de ce que l'IA a fait pendant la nuit.

Agrège: services, cycles de recherche, regimes, classement (avec sagesse),
trades/ACHAT+dip, EXTEND_TP, reflection du matin, auto-pruning, lecons.
"""
import os, json, subprocess, sys
from datetime import datetime, timedelta

D = os.path.dirname(os.path.abspath("paper_trading.py")) or os.getcwd()


def sh(cmd):
    try:
        return subprocess.run(cmd, shell=True, capture_output=True, text=True, timeout=15).stdout.strip()
    except Exception as e:
        return f"err: {e}"


def load_jsonl(name):
    p = os.path.join(D, name)
    if not os.path.exists(p):
        return []
    return [json.loads(l) for l in open(p, encoding="utf-8") if l.strip()]


def load_json(name):
    p = os.path.join(D, name)
    if not os.path.exists(p):
        return None
    try:
        return json.load(open(p, encoding="utf-8"))
    except Exception:
        return None


print("#" * 76)
print("#  RAPPORT MATINAL — activité de l'IA pendant la nuit")
print("#" * 76)

# 1) Services
print("\n=== 1. SERVICES ===")
for svc in ["paper_trading", "protection", "dashboard", "telegram_monitor",
            "pont_revolut", "research_loop"]:
    st = sh(f"systemctl is-active {svc}.service")
    print(f"  {svc:<20} {st}")

# 2) Cycles de recherche
cycles = load_jsonl("recherche_log.jsonl")
print(f"\n=== 2. RESEARCH LOOP ({len(cycles)} cycles) ===")
regimes_seen = set()
shifts = 0
for c in cycles:
    rg = c.get("regimes", {})
    if isinstance(rg, dict):
        for s, v in rg.items():
            r = v if isinstance(v, str) else v.get("REGIME", "?")
            regimes_seen.add(r)
    if c.get("divergence", {}).get("n_extend", 0) > 0:
        shifts += 1
if cycles:
    print(f"  premier cycle: {cycles[0].get('ts','?')[:19]}")
    print(f"  dernier cycle: {cycles[-1].get('ts','?')[:19]}")
    print(f"  regimes observes: {regimes_seen or '?'}")
    sw = cycles[-1].get("sweep", {})
    if isinstance(sw, dict):
        best = sw.get("best", [])
        print(f"  dernier sweep: FIXE={sw.get('fixe','?')}% | best EXTEND tp_ext={best[0] if best else '?'} -> {best[1] if len(best)>1 else '?'}%")
    top = cycles[-1].get("top_strat", "")
    if top:
        print(f"  derniere top strat: {top[:80]}")
    div = cycles[-1].get("divergence", {})
    print(f"  divergence EXTEND: {div.get('msg', div)}")

# 3) Regime history (shifts)
rh = load_json("regime_history.json")
print(f"\n=== 3. REGIMES / SHIFTS ===")
if rh:
    if isinstance(rh, dict):
        for k, v in list(rh.items())[:8]:
            print(f"  {k}: {v}")
    elif isinstance(rh, list):
        print(f"  {len(rh)} entrees historique")
else:
    print("  (historique regimes vide)")

# 4) Classement actuel (avec sagesse)
cl = load_json("classement_strategies.json")
print(f"\n=== 4. CLASSEMENT ACTUEL (avec sagesse) ===")
if cl:
    rows = []
    for actif, v in cl.items():
        if isinstance(v, dict):
            for s in v.get("strategies", []):
                rows.append(s)
    rows.sort(key=lambda x: x.get("score", 0), reverse=True)
    print(f"  {'#':<3}{'Actif':<10}{'Strategie':<20}{'Score':>6}{'Fit':>5}{'Sag':>5}  {'Verdict':<8}")
    for s in rows[:8]:
        print(f"  {str(s.get('rang','?')):<3}{str(s.get('actif','?')):<10}"
              f"{str(s.get('strategie','?')):<20}{s.get('score',0):>6.2f}"
              f"{s.get('regime_fit',0):>5.2f}x{s.get('sagesse_mult',1.0):>4.2f}"
              f"  {str(s.get('sagesse_verdict','?')):<8}")
    has_sag = any("sagesse_mult" in r for r in rows)
    print(f"  sagesse cablee: {'OUI' if has_sag else 'NON (ancien format)'}")

# 5) Trades / ACHAT+dip dans paper_trading.log
print(f"\n=== 5. TRADES & ACHAT (paper_trading.log) ===")
log_p = os.path.join(D, "paper_trading.log")
if os.path.exists(log_p):
    lines = open(log_p, encoding="utf-8", errors="ignore").read().splitlines()
    achat_dip = [l for l in lines if "ACHAT" in l and "dip" in l]
    achat_all = [l for l in lines if "ACHAT" in l]
    trades_ouvert = [l for l in lines if "TRADE OUVERT" in l or "position ouverte" in l.lower()]
    trades_ferme = [l for l in lines if "TRADE FERM" in l or "ferme" in l.lower() and ("gain" in l.lower() or "perte" in l.lower())]
    print(f"  lignes log: {len(lines)}")
    print(f"  ACHAT (total): {len(achat_all)}")
    print(f"  ACHAT avec dip: {len(achat_dip)}")
    if achat_dip:
        print("  --- derniers ACHAT+dip ---")
        for l in achat_dip[-5:]:
            print(f"    {l[-90:]}")
    # dernier portefeuille
    pf_lines = [i for i, l in enumerate(lines) if "Valeur totale" in l or "Gain/perte" in l]
    if pf_lines:
        i = pf_lines[-1]
        print("  --- dernier portefeuille ---")
        for l in lines[max(0, i-6):i+3]:
            print(f"    {l.strip()[:80]}")
    # dernier tick
    tick = [l for l in lines if "Dernier tick" in l]
    if tick:
        print(f"  {tick[-1].strip()}")
else:
    print("  (log introuvable)")

# 6) Watcher Telegram
print(f"\n=== 6. WATCHER ACHAT+DIP (Telegram) ===")
wp = "/tmp/watch_achat_dip.log"
if os.path.exists(wp):
    wl = open(wp, encoding="utf-8", errors="ignore").read().splitlines()
    alertes = [l for l in wl if "ALERTE" in l]
    print(f"  watcher log: {len(wl)} lignes | alertes: {len(alertes)}")
    if alertes:
        for l in alertes[-5:]:
            print(f"    {l[:90]}")
    else:
        print("  Aucune alerte ACHAT+dip (marche calme / pas de creux confirme)")
    # watcher encore vivant?
    pid = sh("pgrep -f watch_achat_dip.py")
    print(f"  watcher processus: {'actif ('+pid+')' if pid else 'ARRETE'}")
else:
    print("  (watcher arrete ou log absent)")

# 7) EXTEND_TP trades fermes
print(f"\n=== 7. EXTEND_TP (crypto) ===")
ext = [l for l in (open(log_p, encoding="utf-8", errors="ignore").read().splitlines() if os.path.exists(log_p) else []) if "EXTEND" in l]
print(f"  lignes EXTEND: {len(ext)}")
for l in ext[-4:]:
    print(f"    {l.strip()[:85]}")

# 8) Reflection du matin (08:00 UTC = 10:00 CEST)
print(f"\n=== 8. REFLECTION DU MATIN (10:00 CEST) ===")
for cand in ["reflection_log.jsonl", "reflection.jsonl", "insights.jsonl",
             "propositions.jsonl", "actions_proposees.jsonl"]:
    p = os.path.join(D, cand)
    if os.path.exists(p):
        data = load_jsonl(cand)
        print(f"  {cand}: {len(data)} entrees")
        for e in data[-3:]:
            ts = e.get("ts", e.get("date", "?"))
            print(f"    [{ts}] {str(e.get('insight', e.get('proposition', e.get('action', e))))[:80]}")
        break
else:
    print("  (aucun fichier de reflection trouve - reflection peut loguer ailleurs)")

# 9) Auto-pruning
print(f"\n=== 9. AUTO-PRUNING ===")
ap = load_json("auto_pruning_stats.json") or load_json("strategies_desactivees.json")
if ap:
    print(f"  {ap}")
else:
    # verifier via auto_pruning module
    try:
        import auto_pruning
        stats = auto_pruning.stats_strategies()
        disabled = [k for k, v in stats.items() if v.get("disabled") or v.get("n", 0) > 0]
        print(f"  strategies avec trades live: {len(stats)} | desactivees: {sum(1 for v in stats.values() if v.get('disabled'))}")
        for k, v in list(stats.items())[:5]:
            if v.get("n", 0) > 0:
                print(f"    {k}: n={v.get('n')} win={v.get('win_rate',0):.0f}% pnl={v.get('pnl_total',0):.2f}")
    except Exception as e:
        print(f"  (auto_pruning non lisible: {e})")

# 10) Lecons
lecons = load_jsonl("lecons_apprises.jsonl")
print(f"\n=== 10. LECONS ({len(lecons)}) ===")
for e in lecons:
    st = e.get("statut", "?")
    m = "OK" if "DEPLOY" in st.upper() else ("~" if "NUANCE" in st.upper() else "X")
    print(f"  [{m}] {e.get('ts','?')[:16]} | {e.get('hypothese','?')[:55]}")

print("\n" + "#" * 76)
print("Fin du rapport matinal")
print("#" * 76)
