#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""ia_render.py — rendu de la page dashboard /ia (Phase 6).
Affiche: strategies actives/desactivees (perf live) + derniere reflexion LLM."""
import os
import json
import html

DOSSIER = os.path.dirname(os.path.abspath(__file__))
PT_FILE = os.path.join(DOSSIER, "paper_trading.json")
PRUNING_FILE = os.path.join(DOSSIER, "strategies_desactivees.json")
REFLECTION_FILE = os.path.join(DOSSIER, "reflection_log.jsonl")


def _esc(s):
    return html.escape(str(s)) if s else ""


def _load(path, default):
    try:
        return json.load(open(path, encoding="utf-8"))
    except Exception:
        return default


def _stats_strategies():
    """Reuse auto_pruning pour les perf live par strategie."""
    try:
        from auto_pruning import stats_strategies
        return stats_strategies()
    except Exception:
        return {}


def _derniere_reflexion():
    try:
        with open(REFLECTION_FILE, encoding="utf-8") as f:
            lignes = f.readlines()
        if not lignes:
            return None
        return json.loads(lignes[-1])
    except Exception:
        return None


def render_ia(token):
    stats = _stats_strategies()
    pruning = _load(PRUNING_FILE, {})
    desact = pruning.get("desactivees", {})
    refl = _derniere_reflexion()

    # table strategies
    lignes_tbl = []
    for cle, s in sorted(stats.items(), key=lambda x: x[1].get("pnl_total", 0)):
        d = desact.get(cle, {})
        disa = d.get("disabled")
        statut = ('<span class="bad">DESACTIVEE</span>' if disa
                  else '<span class="good">active</span>')
        raison = _esc(d.get("raison", "")) if disa else ""
        lignes_tbl.append(
            f"<tr><td>{_esc(s.get('strategie',''))}</td>"
            f"<td>{_esc(s.get('actif',''))}</td>"
            f"<td class='num'>{s.get('n',0)}</td>"
            f"<td class='num'>{s.get('win_rate',0)}%</td>"
            f"<td class='num'>{s.get('pnl_total',0):+.2f}€</td>"
            f"<td>{statut}</td><td class='sm'>{raison}</td></tr>")

    # reflexion
    refl_html = "<p class='sm muted'>(aucune reflexion enregistree — "
    refl_html += "lancee a 08:00 UTC ou via python reflection_gemini.py)</p>"
    if refl:
        a = refl.get("analyse", {}) or {}
        source = refl.get("source", "?")
        ts = refl.get("ts", "?")
        items = lambda lst: "".join(f"<li>{_esc(x)}</li>" for x in (lst or []))
        refl_html = f"""
        <div class="card">
          <div class="meta">Reflexion du {_esc(ts)} · source: {_esc(source)}</div>
          <h3>Synthese</h3><p>{_esc(a.get('synthese',''))}</p>
          <div class="grid2">
            <div><h4>Points forts</h4><ul>{items(a.get('points_forts'))}</ul></div>
            <div><h4>Points faibles</h4><ul>{items(a.get('points_faibles'))}</ul></div>
          </div>
          <h4>Insights</h4><ul>{items(a.get('insights'))}</ul>
          <h4>Suggestions</h4><ul>{items(a.get('suggestions'))}</ul>
          <div class="priority">PRIORITE: {_esc(a.get('priorite',''))}</div>
        </div>"""

    n_desact = sum(1 for v in desact.values() if v.get("disabled"))
    n_strat = len(stats)

    return f"""<!DOCTYPE html><html lang="fr"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>IA — Agent Trading</title><meta http-equiv="refresh" content="120">
<style>
body{{background:#0d1117;color:#e6edf3;font-family:system-ui,sans-serif;margin:0;padding:16px}}
h2{{color:#58a6ff;margin:0 0 12px}}
h3{{color:#c9d1d9;margin:14px 0 6px}}h4{{color:#8b949e;margin:10px 0 4px;font-size:.95em}}
.meta{{color:#8b949e;font-size:.8em;margin-bottom:8px}}
a{{color:#58a6ff}}
table{{border-collapse:collapse;width:100%;margin:8px 0;font-size:.88em}}
th,td{{border:1px solid #30363d;padding:6px 8px;text-align:left}}
th{{background:#161b22;color:#8b949e}}.num{{text-align:right;font-variant-numeric:tabular-nums}}
.sm{{font-size:.78em;color:#8b949e}}.muted{{color:#6e7681}}
.good{{color:#3fb950;font-weight:600}}.bad{{color:#f85149;font-weight:600}}
.card{{background:#161b22;border:1px solid #30363d;border-radius:8px;padding:12px;margin:10px 0}}
.grid2{{display:grid;grid-template-columns:1fr 1fr;gap:12px}}
.priority{{background:#1f6feb22;border-left:3px solid #1f6feb;padding:8px 12px;margin-top:8px;font-weight:600;color:#79c0ff}}
ul{{margin:4px 0;padding-left:20px}}li{{margin:3px 0}}
</style></head><body>
<h2>🧠 IA Avancée — Self-improvement</h2>
<div class="meta">{n_strat} stratégies suivies · {n_desact} désactivée(s) ·
pruning: {str(len(desact))} entrée(s) · dernier cycle: {_esc(pruning.get('dernier_cycle','jamais'))} ·
<a class="lnk" href="/?token={_esc(token)}">Dashboard</a> ·
<a class="lnk" href="/perf?token={_esc(token)}">Performance</a></div>

<h3>Stratégies — performance live</h3>
<table><tr><th>Stratégie</th><th>Actif</th><th>Trades</th><th>Win rate</th><th>PnL</th><th>Statut</th><th>Raison</th></tr>
{''.join(lignes_tbl) if lignes_tbl else '<tr><td colspan=7 class=muted>(aucune stratégie avec trades catégorisés)</td></tr>'}
</table>

<h3>Dernière réflexion IA</h3>
{refl_html}
<div class="meta" style="margin-top:14px">Auto-pruning: min 3 trades, win_rate&lt;40% = désactivation ·
cooldown réactivation 7 jours · reflexion quotidienne 08:00 UTC</div>
</body></html>"""
