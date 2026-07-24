#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""evolutia_profit.py — Auto-mesure + revert du méta-évolveur (Feature 1).

Comble le trou de plugin_sante: plugin_sante désactive les plugins trop
bloquants/buggés (comportement), mais NE mesure pas si une évolution améliore
ou dégrade réellement le P&L. Ce module le fait:

  1. enregistrer_application(plugin, desc)
     - Snapshot la baseline (perf des BASELINE_N derniers trades fermés AVANT
       l'application). Écrit un record EN_EVALUATION dans evolutia_ledger.jsonl.
     - Appelé par meta_evolver.py après auto-apply (wrappé try/except, safe).

  2. evaluer()  (cron quotidien)
     - Pour chaque évolution EN_EVALUATION:
       * fenêtre = [apply_time, prochaine_apply OU maintenant]
       * post = trades fermés dans la fenêtre
       * si len(post) >= MIN_POST: compare post.avg_gain_pct vs baseline.avg_gain_pct
         - régression nette (post < baseline - REVERT_MARGIN_PCT) => REVERT
           (déplace plugins/<p> -> plugins_disabled/<p> + notif Telegram)
         - sinon => GARDE
       * si > MAX_EVAL_JOURS sans atteindre MIN_POST => EN_ATTENTE (peu actif,
         pas assez de data, low risk)
     - Ledger complet (avant/après + verdict) dans evolutia_ledger.jsonl.

Mesure le P&L paper (proxy du live: le pont Revolut miroir les trades paper).
Scope: plugins auto-générés par le méta-évolveur (pas les gates codés en dur).

CLI:
  python evolutia_profit.py evaluer        # évalue + revert si régression
  python evolutia_profit.py rapport        # résumé du ledger
  python evolutia_profit.py force_revert <plugin.py>
  python evolutia_profit.py force_garde <plugin.py>
"""
import os
import sys
import json
import shutil
from datetime import datetime, timedelta

DOSSIER = os.path.dirname(os.path.abspath(__file__))
LEDGER_FILE = os.path.join(DOSSIER, "evolutia_ledger.jsonl")
PT_FILE = os.path.join(DOSSIER, "paper_trading.json")
PLUGINS_DIR = os.path.join(DOSSIER, "plugins")
DISABLED_DIR = os.path.join(DOSSIER, "plugins_disabled")
TELEGRAM_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN", "")
TELEGRAM_CHAT = os.getenv("TELEGRAM_CHAT_ID", "")

# --- Paramètres (conservateurs pour éviter le whipsaw) ---
BASELINE_N = 40          # trades fermés pour la baseline
MIN_POST = 15            # trades post minimum pour juger
MAX_EVAL_JOURS = 14      # au-delà sans MIN_POST => EN_ATTENTE
REVERT_MARGIN_PCT = 0.30 # revert si post.avg_gain < baseline.avg_gain - 0.30%
DT_FMT = "%Y-%m-%d %H:%M"


def _log(msg):
    print(f"[evolutia] {datetime.utcnow():%H:%M:%S} {msg}", flush=True)


# ============================================
# CHARGEMENT TRADES
# ============================================
def _parse_dt(s):
    if not s:
        return None
    try:
        return datetime.strptime(str(s)[:16], DT_FMT)
    except Exception:
        return None


def _load_trades():
    """Retourne trades_fermes triés par date_fermeture croissante."""
    try:
        pt = json.load(open(PT_FILE))
        trades = pt.get("trades_fermes", []) or []
    except Exception:
        return []
    trades = [t for t in trades if _parse_dt(t.get("date_fermeture"))]
    trades.sort(key=lambda t: _parse_dt(t.get("date_fermeture")))
    return trades


# ============================================
# METRIQUES
# ============================================
def _metrics(trades):
    """Calcule les métriques de perf d'une liste de trades fermés."""
    n = len(trades)
    if n == 0:
        return {"n": 0, "win_rate": 0.0, "avg_gain_pct": 0.0,
                "pnl_eur": 0.0, "pnl_per_trade": 0.0,
                "trades_per_day": 0.0, "std_gain": 0.0}
    gains = [float(t.get("variation_pct", 0) or 0) for t in trades]
    pnl = [float(t.get("gain_eur", 0) or 0) for t in trades]
    wins = sum(1 for g in gains if g > 0)
    avg_g = sum(gains) / n
    var = sum((g - avg_g) ** 2 for g in gains) / n
    std = var ** 0.5
    # trades/jour sur la plage de dates
    dates = [_parse_dt(t.get("date_fermeture")) for t in trades]
    dates = [d for d in dates if d]
    tpd = 0.0
    if len(dates) >= 2:
        span = (max(dates) - min(dates)).total_seconds() / 86400.0
        tpd = n / span if span > 0 else float(n)
    else:
        tpd = float(n)
    return {"n": n, "win_rate": round(wins / n, 3),
            "avg_gain_pct": round(avg_g, 3), "pnl_eur": round(sum(pnl), 2),
            "pnl_per_trade": round(sum(pnl) / n, 3),
            "trades_per_day": round(tpd, 2), "std_gain": round(std, 3)}


# ============================================
# LEDGER
# ============================================
def _read_ledger():
    recs = []
    if os.path.exists(LEDGER_FILE):
        for line in open(LEDGER_FILE):
            line = line.strip()
            if not line:
                continue
            try:
                recs.append(json.loads(line))
            except Exception:
                pass
    return recs


def _write_ledger(recs):
    tmp = LEDGER_FILE + ".tmp"
    with open(tmp, "w") as f:
        for r in recs:
            f.write(json.dumps(r, ensure_ascii=False) + "\n")
    os.replace(tmp, LEDGER_FILE)


def _append_record(rec):
    recs = _read_ledger()
    recs.append(rec)
    _write_ledger(recs)


# ============================================
# APPLICATION (snapshot baseline)
# ============================================
def enregistrer_application(plugin_fname, desc=""):
    """À appeler par meta_evolver après auto-apply. Snapshot la baseline."""
    try:
        trades = _load_trades()
        baseline = _metrics(trades[-BASELINE_N:])
        rec = {
            "apply_time": datetime.utcnow().isoformat(timespec="seconds"),
            "plugin": plugin_fname,
            "desc": (desc or "")[:200],
            "baseline": baseline,
            "statut": "EN_EVALUATION",
            "eval_time": None,
            "post": None,
            "verdict": "",
        }
        _append_record(rec)
        _log(f"Application enregistrée: {plugin_fname} "
             f"(baseline avg_gain {baseline['avg_gain_pct']:+.2f}% sur {baseline['n']} trades)")
        return True
    except Exception as e:
        _log(f"enregistrer_application KO: {e}")
        return False


# ============================================
# EVALUATION + REVERT
# ============================================
def _window_end(record, all_records):
    """Prochaine apply_time après celle-ci, sinon maintenant."""
    apply_dt = _parse_dt_iso(record.get("apply_time"))
    nxt = None
    for r in all_records:
        if r is record:
            continue
        dt = _parse_dt_iso(r.get("apply_time"))
        if dt and apply_dt and dt > apply_dt:
            if nxt is None or dt < nxt:
                nxt = dt
    return nxt or datetime.utcnow()


def _parse_dt_iso(s):
    try:
        return datetime.fromisoformat(s.replace("Z", ""))
    except Exception:
        return None


def _revert(plugin_fname, raison):
    """Déplace plugins/<plugin> vers plugins_disabled/. Retourne True si déplacé."""
    try:
        os.makedirs(DISABLED_DIR, exist_ok=True)
        src = os.path.join(PLUGINS_DIR, plugin_fname)
        dst = os.path.join(DISABLED_DIR, plugin_fname)
        moved = False
        if os.path.isfile(src):
            shutil.move(src, dst)
            moved = True
        _notifier(plugin_fname, raison, moved)
        _log(f"REVERT {plugin_fname}: {raison} (moved={moved})")
        return moved
    except Exception as e:
        _log(f"revert KO {plugin_fname}: {e}")
        return False


def _notifier(plugin, raison, moved):
    if not TELEGRAM_TOKEN or not TELEGRAM_CHAT:
        return
    try:
        import requests
        action = "déplacé vers plugins_disabled/" if moved else "(déjà absent de plugins/)"
        msg = (f"↩️ Évolution revertée (régression P&L)\n\n"
               f"Plugin: {plugin}\nRaison: {raison}\n{action}\n\n"
               f"Le loader le retirera au prochain trade. "
               f"Pour ré-essayer: mv plugins_disabled/{plugin} plugins/")
        requests.post(f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage",
                      json={"chat_id": TELEGRAM_CHAT, "text": msg}, timeout=10)
    except Exception:
        pass


def _decide(baseline, post):
    """Retourne (statut, verdict). GARDE sauf régression nette."""
    bg = baseline.get("avg_gain_pct", 0.0)
    pg = post.get("avg_gain_pct", 0.0)
    seuil = bg - REVERT_MARGIN_PCT
    if pg < seuil:
        return ("REVERT", f"régression: post {pg:+.2f}% < base {bg:+.2f}% "
                          f"(seuil {seuil:+.2f}%, marge -{REVERT_MARGIN_PCT}%)")
    return ("GARDE", f"ok: post {pg:+.2f}% vs base {bg:+.2f}% (seuil revert {seuil:+.2f}%)")


def evaluer():
    """Évalue toutes les évolutions EN_EVALUATION. Revert si régression nette."""
    recs = _read_ledger()
    if not recs:
        _log("Ledger vide — rien à évaluer")
        return []
    trades = _load_trades()
    if not trades:
        _log("Pas de trades fermés — rien à évaluer")
        return []
    now = datetime.utcnow()
    actions = []
    for rec in recs:
        if rec.get("statut") != "EN_EVALUATION":
            continue
        apply_dt = _parse_dt_iso(rec.get("apply_time"))
        if not apply_dt:
            continue
        wend = _window_end(rec, recs)
        # post = trades fermés après apply_time (et avant fin de fenêtre)
        post = [t for t in trades
                if apply_dt < _parse_dt(t.get("date_fermeture")) <= wend]
        # timeout data
        if len(post) < MIN_POST:
            if (now - apply_dt).days > MAX_EVAL_JOURS:
                rec["statut"] = "EN_ATTENTE"
                rec["post"] = {"n": len(post)}
                rec["eval_time"] = now.isoformat(timespec="seconds")
                rec["verdict"] = (f"peu actif: {len(post)} trades en "
                                  f"{(now-apply_dt).days}j (<{MIN_POST}) — pas assez de data")
                actions.append(("EN_ATTENTE", rec.get("plugin"), rec["verdict"]))
            continue
        baseline = rec.get("baseline", {})
        post_m = _metrics(post)
        statut, verdict = _decide(baseline, post_m)
        rec["statut"] = statut
        rec["post"] = post_m
        rec["eval_time"] = now.isoformat(timespec="seconds")
        rec["verdict"] = verdict
        if statut == "REVERT":
            _revert(rec.get("plugin", ""), verdict)
        actions.append((statut, rec.get("plugin"), verdict))
    _write_ledger(recs)
    for st, pl, vd in actions:
        _log(f"  {st}: {pl} — {vd[:80]}")
    return actions


# ============================================
# RAPPORT
# ============================================
def rapport():
    recs = _read_ledger()
    print("=" * 64)
    print("EVOLUTIA PROFIT — ledger auto-mesure méta-évolveur")
    print("=" * 64)
    if not recs:
        print("(ledger vide — aucune évolution enregistrée)")
        return
    from collections import Counter
    cnt = Counter(r.get("statut") for r in recs)
    print(f"Total: {len(recs)} évolution(s) | " +
          " | ".join(f"{k}={v}" for k, v in cnt.items()))
    print("-" * 64)
    for r in recs:
        b = r.get("baseline", {})
        p = r.get("post") or {}
        print(f"\n• {r.get('plugin')} [{r.get('statut')}]")
        print(f"  desc: {r.get('desc','')[:90]}")
        print(f"  apply: {r.get('apply_time','')[:19]}  eval: {(r.get('eval_time') or '-')[:19]}")
        print(f"  baseline: n={b.get('n','?')} avg_gain={b.get('avg_gain_pct','?')}% "
              f"win={b.get('win_rate','?')} tpd={b.get('trades_per_day','?')}")
        if p:
            print(f"  post:     n={p.get('n','?')} avg_gain={p.get('avg_gain_pct','?')}% "
                  f"win={p.get('win_rate','?')} tpd={p.get('trades_per_day','?')}")
        if r.get("verdict"):
            print(f"  verdict: {r['verdict']}")


def force_revert(plugin):
    recs = _read_ledger()
    for r in recs:
        if r.get("plugin") == plugin and r.get("statut") == "EN_EVALUATION":
            r["statut"] = "REVERT"
            r["eval_time"] = datetime.utcnow().isoformat(timespec="seconds")
            r["verdict"] = "force_revert manuel"
            _revert(plugin, "force_revert manuel")
    _write_ledger(recs)


def force_garde(plugin):
    recs = _read_ledger()
    for r in recs:
        if r.get("plugin") == plugin and r.get("statut") == "EN_EVALUATION":
            r["statut"] = "GARDE"
            r["eval_time"] = datetime.utcnow().isoformat(timespec="seconds")
            r["verdict"] = "force_garde manuel"
    _write_ledger(recs)


if __name__ == "__main__":
    cmd = sys.argv[1] if len(sys.argv) > 1 else "rapport"
    if cmd == "evaluer":
        evaluer()
    elif cmd == "rapport":
        rapport()
    elif cmd == "force_revert" and len(sys.argv) > 2:
        force_revert(sys.argv[2])
    elif cmd == "force_garde" and len(sys.argv) > 2:
        force_garde(sys.argv[2])
    else:
        print("Usage: evolutia_profit.py [evaluer|rapport|force_revert <p>|force_garde <p>]")
