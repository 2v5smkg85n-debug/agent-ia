#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
auto_pruning.py — Auto-elagage des strategies perdantes (self-improvement).

Realise concretement "coupe les perdantes automatiquement":
  - Analyse les perf LIVE (trades_fermes) par (strategie, actif)
  - DESACTIVE une strategie qui perd systematiquement en live
  - REACTIVE apres un cooldown (re-test apres revalidation walk-forward)

Integration non-invasive: signaux_gagnants importe est_desactivee() et
skip les strategies desactivees au chargement.

Fichier d'etat: strategies_desactivees.json
  { "MACD Momentum|BTCUSDT": {
        "strategie":"MACD Momentum", "actif":"BTCUSDT",
        "disabled":true, "raison":"...", "since":"...", "stats":{...} } }

Regles (conservatrices — besoin de donnees live suffisantes):
  - MIN_TRADES=3        : il faut >=3 trades live pour juger
  - DISABLE si n>=3 AND win_rate<40% AND pnl_total<0
  - RE-ENABLE apres COOLDOWN_JOURS=7
  - SECURITE: on garde toujours >=1 strategie active par actif

CLI:
  python auto_pruning.py            # cycle d'elagage + rapport
  python auto_pruning.py etat        # voir l'etat des strategies
"""
import os
import re
import json
import logging
from datetime import datetime, timedelta

DOSSIER = os.path.dirname(os.path.abspath(__file__))
PT_FILE = os.path.join(DOSSIER, "paper_trading.json")
FICHIER_PRUNING = os.path.join(DOSSIER, "strategies_desactivees.json")
LOG_FILE = os.path.join(DOSSIER, "pruning_log.jsonl")

# --- Regles ---
MIN_TRADES = 3
WIN_RATE_MIN = 40.0           # < 40% en live = perdante
COOLDOWN_JOURS = 7           # re-test apres 7 jours
GARDER_MIN_PAR_ACTIF = 1     # ne jamais desactiver toutes les strats d'un actif

logging.basicConfig(level=logging.INFO,
                    format="%(asctime)s [%(levelname)s] %(message)s",
                    datefmt="%H:%M:%S")
log = logging.getLogger("auto_pruning")


def _load(path, default):
    try:
        return json.load(open(path, encoding="utf-8"))
    except Exception:
        return default


def _save(path, data):
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)


def _tel(msg):
    try:
        from telegram_alerte import envoyer_telegram
        envoyer_telegram(msg)
    except Exception:
        pass


def _log_jsonl(entry):
    try:
        with open(LOG_FILE, "a", encoding="utf-8") as f:
            f.write(json.dumps(entry, ensure_ascii=False) + "\n")
    except Exception:
        pass


def _cle(strategie, actif):
    return f"{strategie}|{actif}"


# ---------------------------------------------------------------- ETAT
def init_pruning():
    if not os.path.exists(FICHIER_PRUNING):
        _save(FICHIER_PRUNING, {"desactivees": {}, "dernier_cycle": None})
    return _load(FICHIER_PRUNING, {"desactivees": {}})


def est_desactivee(strategie, actif):
    """Importe par signaux_gagnants. True si la strategie est desactivee
    (et le cooldown n'est pas expire)."""
    try:
        data = _load(FICHIER_PRUNING, {})
        entry = data.get("desactivees", {}).get(_cle(strategie, actif))
        if not entry or not entry.get("disabled"):
            return False
        # cooldown expire -> on re-active (donne une 2e chance)
        since = entry.get("since", "")
        try:
            dt = datetime.strptime(since, "%Y-%m-%d %H:%M:%S")
            if datetime.now() - dt > timedelta(days=COOLDOWN_JOURS):
                return False  # cooldown expire, sera re-active au prochain cycle
        except Exception:
            pass
        return True
    except Exception:
        return False


# ---------------------------------------------------------------- STATS LIVE
def _extraire_strategie(t):
    """Extrait le nom de strategie d'un trade ferme.
    1. champ direct 'strategie' (si present)
    2. regex sur signal_raison: '... backtest (NOM [intervalle], ...)'
    3. source 'backtest-gagnant' sans nom -> 'backtest-gagnant'
    Retourne '' si impossible a categoriser (legacy)."""
    strat = (t.get("strategie") or "").strip()
    if strat and strat not in ("legacy", "backtest-gagnant"):
        return strat
    raison = t.get("signal_raison", "") or ""
    m = re.search(r"backtest\s*\(([^\[]+)\s*\[", raison)
    if m:
        return m.group(1).strip()
    src = (t.get("source") or "").strip()
    if src == "backtest-gagnant":
        return "backtest-gagnant"
    return ""


def stats_strategies():
    """Calcule les perf live par (strategie, actif) depuis trades_fermes."""
    pf = _load(PT_FILE, {})
    trades = pf.get("trades_fermes", [])
    stats = {}  # cle -> {strategie, actif, n, wins, pnl_total, win_rate, trades}
    for t in trades:
        strat = _extraire_strategie(t)
        if not strat or strat in ("legacy", ""):
            continue
        actif = t.get("symbole", "")
        if not actif:
            continue
        cle = _cle(strat, actif)
        s = stats.setdefault(cle, {
            "strategie": strat, "actif": actif, "n": 0, "wins": 0,
            "pnl_total": 0.0, "trades": []})
        gain = float(t.get("gain_eur") or t.get("pnl") or t.get("variation_eur") or 0)
        s["n"] += 1
        s["pnl_total"] += gain
        if gain > 0:
            s["wins"] += 1
        s["trades"].append({
            "gain": round(gain, 2),
            "date": t.get("date_fermeture", t.get("date_ouverture", ""))})
    for s in stats.values():
        s["win_rate"] = round(100.0 * s["wins"] / s["n"], 1) if s["n"] else 0.0
        s["pnl_total"] = round(s["pnl_total"], 2)
    return stats


# ---------------------------------------------------------------- LOGIQUE
def _actifs_par_strategie(stats):
    """Pour chaque actif, liste des cles de strategie (pour la securite min)."""
    par_actif = {}
    for cle, s in stats.items():
        par_actif.setdefault(s["actif"], []).append(cle)
    return par_actif


def pruner():
    """Cycle d'elagage. Analyse + desactive/reactive."""
    data = init_pruning()
    desact = data.get("desactivees", {})
    stats = stats_strategies()
    changements = []

    # 1. RE-ACTIVER celles dont le cooldown est expire
    maintenant = datetime.now()
    for cle, entry in list(desact.items()):
        if not entry.get("disabled"):
            continue
        try:
            since = datetime.strptime(entry.get("since", ""), "%Y-%m-%d %H:%M:%S")
            if maintenant - since > timedelta(days=COOLDOWN_JOURS):
                entry["disabled"] = False
                entry["reactivee"] = maintenant.strftime("%Y-%m-%d %H:%M:%S")
                changements.append(("REACTIVE", cle, "cooldown expire"))
        except Exception:
            pass

    # 2. DESACTIVER les perdantes
    par_actif = _actifs_par_strategie(stats)
    for cle, s in stats.items():
        if s["n"] < MIN_TRADES:
            continue  # pas assez de donnees
        entry = desact.get(cle, {"strategie": s["strategie"], "actif": s["actif"]})
        if entry.get("disabled"):
            continue  # deja desactivee
        perdante = (s["win_rate"] < WIN_RATE_MIN) and (s["pnl_total"] < 0)
        if not perdante:
            continue
        # SECURITE: garder >=1 strategie active par actif
        actif = s["actif"]
        cles_actif = par_actif.get(actif, [])
        nb_actives = sum(1 for c in cles_actif
                         if not desact.get(c, {}).get("disabled")
                         and stats.get(c, {}).get("n", 0) >= MIN_TRADES)
        if nb_actives <= GARDER_MIN_PAR_ACTIF:
            log.info("[SECURITE] %s: garder >=1 strategie active — skip desactivation",
                     cle)
            continue
        entry.update({
            "disabled": True,
            "raison": f"win_rate {s['win_rate']}% < {WIN_RATE_MIN}% ET pnl {s['pnl_total']}€ < 0 sur {s['n']} trades",
            "since": maintenant.strftime("%Y-%m-%d %H:%M:%S"),
            "stats": {"n": s["n"], "win_rate": s["win_rate"],
                      "pnl_total": s["pnl_total"]},
        })
        desact[cle] = entry
        changements.append(("DESACTIVE", cle, entry["raison"]))

    data["desactivees"] = desact
    data["dernier_cycle"] = maintenant.strftime("%Y-%m-%d %H:%M:%S")
    _save(FICHIER_PRUNING, data)

    # 3. Alertes
    for action, cle, raison in changements:
        strat, actif = cle.split("|", 1)
        msg = (f"✂️ AUTO-PRUNING {action}: {strat} sur {actif}\n{raison}")
        log.info(msg)
        _tel(msg)
        _log_jsonl({"ts": data["dernier_cycle"], "action": action,
                    "strategie": strat, "actif": actif, "raison": raison})
    return changements, stats, data


# ---------------------------------------------------------------- CLI
def cmd_etat():
    data = init_pruning()
    stats = stats_strategies()
    desact = data.get("desactivees", {})
    print("=" * 55)
    print("AUTO-PRUNING — ETAT DES STRATEGIES (perf live)")
    print(f"Regles: min {MIN_TRADES} trades, win_rate < {WIN_RATE_MIN}% = perdante")
    print(f"Cooldown reactivation: {COOLDOWN_JOURS} jours")
    print("=" * 55)
    if not stats:
        print("(aucune strategie avec trades live categorises)")
    for cle, s in sorted(stats.items(), key=lambda x: x[1]["pnl_total"]):
        d = desact.get(cle, {})
        statut = "🔴 DESACTIVEE" if d.get("disabled") else "🟢 active"
        print(f"  {s['strategie']:<22} {s['actif']:<10} n={s['n']} "
              f"wr={s['win_rate']}% pnl={s['pnl_total']:+.2f}€ {statut}")
    print("=" * 55)
    print(f"Dernier cycle: {data.get('dernier_cycle','jamais')}")


def main():
    import sys
    if len(sys.argv) > 1 and sys.argv[1] == "etat":
        cmd_etat()
        return
    changements, stats, data = pruner()
    print(f"Cycle pruning termine. {len(changements)} changement(s).")
    cmd_etat()


if __name__ == "__main__":
    main()
