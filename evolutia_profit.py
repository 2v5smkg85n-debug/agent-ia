#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""evolutia_profit.py — Auto-mesure + revert (plugins méta-évolveur + stratégies evolved).

Comble le trou de plugin_sante: plugin_sante désactive les plugins trop
bloquants/buggés (comportement), mais NE mesure pas si une évolution améliore
ou dégrade réellement le P&L. Ce module le fait:

  1a. enregistrer_application(plugin, desc)
      - Snapshot la baseline (perf des BASELINE_N derniers trades fermés AVANT
        l'application). Écrit un record EN_EVALUATION dans evolutia_ledger.jsonl.
      - Appelé par meta_evolver.py après auto-apply (wrappé try/except, safe).

  1b. enregistrer_strategie(name, oos_avg, win_rate, trades)
      - Snapshot la baseline du portefeuille + métriques OOS de la stratégie.
      - Appelé par strategy_evolver.deploy() après déploiement.

  2. evaluer()  (cron quotidien)
     - Pour chaque évolution EN_EVALUATION:
       * Plugins: fenêtre = [apply_time, prochaine_apply OU maintenant]
         post = TOUS les trades fermés dans la fenêtre
         revert si post.avg_gain < baseline.avg_gain - REVERT_MARGIN_PCT
       * Stratégies: post = trades de CETTE stratégie (filtré par nom)
         revert si pnl_eur < 0 OU avg_gain < baseline - margin OU win << OOS
       * si > MAX_EVAL_JOURS sans atteindre MIN_POST => EN_ATTENTE
     - Ledger complet (avant/après + verdict) dans evolutia_ledger.jsonl.

Mesure le P&L paper (proxy du live: le pont Revolut miroir les trades paper).
Scope: plugins méta-évolveur + stratégies strategy_evolver (pas les gates codés en dur).

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

# --- Stratégies evolved (strategy_evolver.py) ---
EVOLVED_JSON = os.path.join(DOSSIER, "strategies_evolved.json")
EVOLVED_PY = os.path.join(DOSSIER, "strategies_evolved.py")
MIN_POST_STRATEGIE = 10  # seuil plus bas: une stratégie génère moins de trades que le portefeuille


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
# STRATÉGIES EVOLVED (strategy_evolver.py)
# ============================================
def enregistrer_strategie(name, oos_avg=0.0, win_rate=0.0, trades_count=0):
    """À appeler par strategy_evolver.deploy() après déploiement d'une stratégie.
    Snapshot la baseline du portefeuille + métriques OOS de la stratégie."""
    try:
        trades = _load_trades()
        baseline = _metrics(trades[-BASELINE_N:])
        rec = {
            "type": "strategie",
            "apply_time": datetime.utcnow().isoformat(timespec="seconds"),
            "strategie": name,
            "plugin": name,  # alias pour compatibilité rapport
            "oos_avg": round(float(oos_avg), 2),
            "oos_win": round(float(win_rate), 3),
            "oos_trades": int(trades_count),
            "baseline": baseline,
            "statut": "EN_EVALUATION",
            "eval_time": None,
            "post": None,
            "verdict": "",
        }
        _append_record(rec)
        _log(f"Stratégie enregistrée: {name} "
             f"(OOS {oos_avg:+.2f}% win {win_rate:.0%} | "
             f"baseline portefeuille avg_gain {baseline['avg_gain_pct']:+.2f}%)")
        return True
    except Exception as e:
        _log(f"enregistrer_strategie KO: {e}")
        return False


def _regen_evolved_module(strats):
    """Régénère strategies_evolved.py depuis la liste JSON.
    Évite d'importer strategy_evolver (imports lourds: backtest_moteur, indicateurs)."""
    lines = ['#!/usr/bin/env python3',
             '# -*- coding: utf-8 -*-',
             '"""strategies_evolved.py — Stratégies générées par strategy_evolver.py.',
             'NE PAS ÉDITER MANUELLEMENT — géré par strategy_evolver.py."""',
             '']
    names = []
    for s in strats:
        lines.append(s.get("code", "").rstrip())
        lines.append("")
        names.append((s.get("name", ""), s.get("func_name", "")))
    lines.append("EVOLVED_STRATEGIES = {")
    for name, fn in names:
        lines.append(f'    "{name}": {fn},')
    lines.append("}")
    open(EVOLVED_PY, "w", encoding="utf-8").write("\n".join(lines))


def _revert_strategie(name, raison):
    """Retire une stratégie evolved de strategies_evolved.json + régénère le .py."""
    try:
        strats = []
        if os.path.exists(EVOLVED_JSON):
            strats = json.load(open(EVOLVED_JSON, encoding="utf-8"))
        before = len(strats)
        strats = [s for s in strats if s.get("name") != name]
        json.dump(strats, open(EVOLVED_JSON, "w"), indent=2, ensure_ascii=False)
        _regen_evolved_module(strats)
        removed = before - len(strats)
        _notifier_strategie(name, raison, removed > 0)
        _log(f"REVERT STRATEGIE {name}: {raison} (removed={removed})")
        return removed > 0
    except Exception as e:
        _log(f"revert strategie KO {name}: {e}")
        return False


def _notifier_strategie(name, raison, removed):
    if not TELEGRAM_TOKEN or not TELEGRAM_CHAT:
        return
    try:
        import requests
        action = ("retirée de strategies_evolved.json + .py régénéré"
                  if removed else "(déjà absente)")
        msg = (f"↩️ Stratégie evolved revertée (régression P&L)\n\n"
               f"Stratégie: {name}\nRaison: {raison}\n{action}\n\n"
               f"Le loader la retirera au prochain trade.")
        requests.post(f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage",
                      json={"chat_id": TELEGRAM_CHAT, "text": msg}, timeout=10)
    except Exception:
        pass


def _decide_strategie(baseline, post, oos_win=0.0):
    """Décision pour une stratégie evolved. Revert si perte nette ou sous-perf.
    Plus strict que _decide (plugins): une stratégie qui perd de l'argent doit partir."""
    if post.get("pnl_eur", 0) < 0:
        return ("REVERT", f"perte nette: {post['pnl_eur']:+.2f}€ sur {post['n']} trades")
    bg = baseline.get("avg_gain_pct", 0.0)
    pg = post.get("avg_gain_pct", 0.0)
    seuil = bg - REVERT_MARGIN_PCT
    if pg < seuil:
        return ("REVERT", f"sous-perf: post {pg:+.2f}% < base {bg:+.2f}% "
                          f"(seuil {seuil:+.2f}%)")
    if oos_win > 0 and post.get("win_rate", 0) < oos_win - 0.15:
        return ("REVERT", f"win rate dégradé: live {post['win_rate']:.0%} "
                          f"vs OOS {oos_win:.0%}")
    return ("GARDE", f"ok: post {pg:+.2f}% pnl {post['pnl_eur']:+.2f}€ "
                     f"win {post['win_rate']:.0%} sur {post['n']} trades")


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
    """Évalue toutes les évolutions EN_EVALUATION (plugins + stratégies).
    Revert si régression nette. Gère type='plugin' (tous trades) et
    type='strategie' (trades de la stratégie spécifique)."""
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
        rtype = rec.get("type", "plugin")  # backward compat: default plugin
        min_post = MIN_POST_STRATEGIE if rtype == "strategie" else MIN_POST
        wend = _window_end(rec, recs)
        label = rec.get("strategie", rec.get("plugin", ""))
        if rtype == "strategie":
            # Post = trades de CETTE stratégie après apply_time
            post = [t for t in trades
                    if apply_dt < _parse_dt(t.get("date_fermeture")) <= wend
                    and t.get("strategie", "") == label]
        else:
            # Post = tous les trades après apply_time (plugins affectent tout)
            post = [t for t in trades
                    if apply_dt < _parse_dt(t.get("date_fermeture")) <= wend]
        # timeout data
        if len(post) < min_post:
            if (now - apply_dt).days > MAX_EVAL_JOURS:
                rec["statut"] = "EN_ATTENTE"
                rec["post"] = {"n": len(post)}
                rec["eval_time"] = now.isoformat(timespec="seconds")
                rec["verdict"] = (f"peu actif: {len(post)} trades en "
                                  f"{(now-apply_dt).days}j (<{min_post}) — pas assez de data")
                actions.append(("EN_ATTENTE", label, rec["verdict"]))
            continue
        baseline = rec.get("baseline", {})
        post_m = _metrics(post)
        if rtype == "strategie":
            statut, verdict = _decide_strategie(baseline, post_m,
                                                rec.get("oos_win", 0.0))
        else:
            statut, verdict = _decide(baseline, post_m)
        rec["statut"] = statut
        rec["post"] = post_m
        rec["eval_time"] = now.isoformat(timespec="seconds")
        rec["verdict"] = verdict
        if statut == "REVERT":
            if rtype == "strategie":
                _revert_strategie(label, verdict)
            else:
                _revert(rec.get("plugin", ""), verdict)
        actions.append((statut, label, verdict))
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
    print("EVOLUTIA PROFIT — ledger auto-mesure (plugins + stratégies)")
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
        rtype = r.get("type", "plugin")
        label = r.get("strategie", r.get("plugin", "?"))
        tag = "[stratégie]" if rtype == "strategie" else "[plugin]"
        print(f"\n• {label} {tag} [{r.get('statut')}]")
        if rtype == "strategie":
            print(f"  OOS: avg={r.get('oos_avg','?')}% win={r.get('oos_win','?')} "
                  f"trades={r.get('oos_trades','?')}")
        else:
            print(f"  desc: {r.get('desc','')[:90]}")
        print(f"  apply: {r.get('apply_time','')[:19]}  eval: {(r.get('eval_time') or '-')[:19]}")
        print(f"  baseline: n={b.get('n','?')} avg_gain={b.get('avg_gain_pct','?')}% "
              f"win={b.get('win_rate','?')} tpd={b.get('trades_per_day','?')}")
        if p:
            print(f"  post:     n={p.get('n','?')} avg_gain={p.get('avg_gain_pct','?')}% "
                  f"win={p.get('win_rate','?')} pnl={p.get('pnl_eur','?')}€")
        if r.get("verdict"):
            print(f"  verdict: {r['verdict']}")


def force_revert(name):
    """Force le revert d'un plugin OU d'une stratégie (type-aware)."""
    recs = _read_ledger()
    for r in recs:
        label = r.get("strategie", r.get("plugin", ""))
        if label == name and r.get("statut") == "EN_EVALUATION":
            r["statut"] = "REVERT"
            r["eval_time"] = datetime.utcnow().isoformat(timespec="seconds")
            r["verdict"] = "force_revert manuel"
            if r.get("type") == "strategie":
                _revert_strategie(name, "force_revert manuel")
            else:
                _revert(name, "force_revert manuel")
    _write_ledger(recs)


def force_garde(name):
    """Force le garde d'un plugin OU d'une stratégie (type-aware)."""
    recs = _read_ledger()
    for r in recs:
        label = r.get("strategie", r.get("plugin", ""))
        if label == name and r.get("statut") == "EN_EVALUATION":
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
        print("Usage: evolutia_profit.py [evaluer|rapport|force_revert <nom>|force_garde <nom>]")
        print("  <nom> = nom de plugin (meta_xxx.py) OU nom de stratégie (Evolved XXXXX)")
