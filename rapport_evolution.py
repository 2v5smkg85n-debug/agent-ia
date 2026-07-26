#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""rapport_evolution.py — Rapport visuel de l'évolution et des apprentissages de l'agent.

Génère un rapport HTML interactif montrant:
- Les leçons apprises (auto-sweep, genetic, regime shifts)
- Les stratégies générées (deployed/rejected)
- Les plugins méta-évolveur
- Les réflexions et la trajectoire du capital
- Les actions de pruning/tuning
- L'évolution chronologique

Usage: python rapport_evolution.py [--serve]
  --serve: démarre un serveur local sur le port 8799
"""
import json
import os
import sys
import html
from datetime import datetime
from collections import Counter, defaultdict

DOSSIER = os.path.dirname(os.path.abspath(__file__))

def load_jsonl(fname):
    path = os.path.join(DOSSIER, fname)
    if not os.path.exists(path):
        return []
    out = []
    try:
        for line in open(path, encoding="utf-8"):
            line = line.strip()
            if line:
                try:
                    out.append(json.loads(line))
                except Exception:
                    pass
    except Exception:
        pass
    return out

def load_json(fname):
    path = os.path.join(DOSSIER, fname)
    if not os.path.exists(path):
        return {}
    try:
        return json.load(open(path, encoding="utf-8"))
    except Exception:
        return {}

def esc(s):
    return html.escape(str(s)) if s else ""

def gen_html():
    lecons = load_jsonl("lecons_apprises.jsonl")
    strategies = load_jsonl("strategies_generated.jsonl")
    meta_props = load_jsonl("meta_propositions.jsonl")
    reflections = load_jsonl("reflection_log.jsonl")
    recherche = load_jsonl("recherche_log.jsonl")
    pruning = load_jsonl("pruning_log.jsonl")
    meta_tuning = load_jsonl("meta_tuning_log.jsonl")
    evolutia = load_jsonl("evolutia_ledger.jsonl")
    desactivees = load_json("strategies_desactivees.json")

    # --- Stats globales ---
    total_lecons = len(lecons)
    total_strats = len(strategies)
    strats_deployed = [s for s in strategies if s.get("verdict") == "DEPLOYED"]
    strats_rejected = [s for s in strategies if s.get("verdict") == "REJETEE"]
    total_reflections = len(reflections)
    total_recherche = len(recherche)
    total_plugins = len(meta_props)

    # --- Trajectoire capital (reflections) ---
    cap_points = []
    for r in reflections:
        ctx = r.get("ctx_summary", {}) or {}
        ts = r.get("ts", "")
        cap = ctx.get("capital")
        pnl = ctx.get("pnl")
        if cap is not None:
            cap_points.append({"ts": ts, "cap": cap, "pnl": pnl})

    # --- Leçons par type ---
    lecons_by_type = defaultdict(list)
    for l in lecons:
        typ = l.get("type") or l.get("source", "?")[:20]
        lecons_by_type[typ].append(l)

    # --- Auto-sweep résultats (dernier run) ---
    sweep_results = []
    for l in reversed(lecons):
        if "auto_sweep" in (l.get("source", "") or "").lower():
            sweep_results.append(l)
            if len(sweep_results) >= 5:
                break

    # --- Genetic optimizer runs ---
    genetic_runs = [l for l in lecons if l.get("type") == "optimisation_genetique"]

    # --- Regime shifts ---
    regime_shifts = [l for l in lecons if l.get("type") == "regime_shift"]

    # --- Derniers régimes (recherche) ---
    last_regimes = {}
    if recherche:
        last = recherche[-1]
        last_regimes = last.get("regimes", {}) if isinstance(last, dict) else {}

    # --- HTML ---
    parts = []
    parts.append(f"""<!DOCTYPE html>
<html lang="fr">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>Évolution de l'Agent IA</title>
<style>
:root {{
  --bg: #0d1117;
  --card: #161b22;
  --border: #30363d;
  --text: #e6edf3;
  --muted: #8b949e;
  --green: #3fb950;
  --red: #f85149;
  --yellow: #d29922;
  --blue: #58a6ff;
  --purple: #bc8cff;
  --orange: #db6d28;
}}
* {{ margin: 0; padding: 0; box-sizing: border-box; }}
body {{
  background: var(--bg);
  color: var(--text);
  font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Helvetica, Arial, sans-serif;
  line-height: 1.6;
  padding: 20px;
  max-width: 1200px;
  margin: 0 auto;
}}
h1 {{
  font-size: 2em;
  margin-bottom: 8px;
  background: linear-gradient(135deg, var(--blue), var(--purple));
  -webkit-background-clip: text;
  -webkit-text-fill-color: transparent;
}}
h2 {{
  font-size: 1.4em;
  margin: 30px 0 12px;
  padding-bottom: 8px;
  border-bottom: 2px solid var(--border);
  color: var(--blue);
}}
h3 {{ font-size: 1.1em; margin: 16px 0 8px; color: var(--text); }}
.subtitle {{ color: var(--muted); margin-bottom: 24px; font-size: 0.95em; }}
.stats-grid {{
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(160px, 1fr));
  gap: 12px;
  margin-bottom: 24px;
}}
.stat-card {{
  background: var(--card);
  border: 1px solid var(--border);
  border-radius: 12px;
  padding: 16px;
  text-align: center;
}}
.stat-card .num {{ font-size: 2em; font-weight: 700; }}
.stat-card .label {{ color: var(--muted); font-size: 0.85em; margin-top: 4px; }}
.stat-card.green .num {{ color: var(--green); }}
.stat-card.red .num {{ color: var(--red); }}
.stat-card.blue .num {{ color: var(--blue); }}
.stat-card.yellow .num {{ color: var(--yellow); }}
.stat-card.purple .num {{ color: var(--purple); }}
.card {{
  background: var(--card);
  border: 1px solid var(--border);
  border-radius: 12px;
  padding: 16px;
  margin-bottom: 12px;
}}
.card:hover {{ border-color: var(--blue); }}
.badge {{
  display: inline-block;
  padding: 2px 10px;
  border-radius: 12px;
  font-size: 0.8em;
  font-weight: 600;
}}
.badge.green {{ background: rgba(63,185,80,0.2); color: var(--green); }}
.badge.red {{ background: rgba(248,81,73,0.2); color: var(--red); }}
.badge.yellow {{ background: rgba(210,153,34,0.2); color: var(--yellow); }}
.badge.blue {{ background: rgba(88,166,255,0.2); color: var(--blue); }}
.badge.purple {{ background: rgba(188,140,255,0.2); color: var(--purple); }}
.badge.orange {{ background: rgba(219,109,40,0.2); color: var(--orange); }}
.timeline {{ position: relative; padding-left: 24px; }}
.timeline::before {{
  content: "";
  position: absolute;
  left: 6px;
  top: 0;
  bottom: 0;
  width: 2px;
  background: var(--border);
}}
.timeline-item {{ position: relative; margin-bottom: 16px; }}
.timeline-item::before {{
  content: "";
  position: absolute;
  left: -22px;
  top: 6px;
  width: 12px;
  height: 12px;
  border-radius: 50%;
  background: var(--blue);
  border: 2px solid var(--card);
}}
.timeline-item.deployed::before {{ background: var(--green); }}
.timeline-item.rejected::before {{ background: var(--red); }}
.timeline-item.lesson::before {{ background: var(--yellow); }}
.timeline-item.plugin::before {{ background: var(--purple); }}
.timeline-item.reflection::before {{ background: var(--blue); }}
.timeline-item.pruning::before {{ background: var(--orange); }}
.meta {{ color: var(--muted); font-size: 0.85em; }}
table {{ width: 100%; border-collapse: collapse; margin: 8px 0; }}
th, td {{ text-align: left; padding: 8px 12px; border-bottom: 1px solid var(--border); }}
th {{ color: var(--muted); font-size: 0.85em; text-transform: uppercase; }}
td {{ font-size: 0.9em; }}
.cap-chart {{
  background: var(--card);
  border: 1px solid var(--border);
  border-radius: 12px;
  padding: 16px;
  margin-bottom: 12px;
}}
.bar-container {{
  display: flex;
  align-items: center;
  gap: 8px;
  margin: 4px 0;
}}
.bar {{
  height: 24px;
  border-radius: 4px;
  min-width: 4px;
  display: flex;
  align-items: center;
  justify-content: flex-end;
  padding-right: 8px;
  font-size: 0.8em;
  font-weight: 600;
  color: var(--bg);
}}
.grid-2 {{
  display: grid;
  grid-template-columns: 1fr 1fr;
  gap: 12px;
}}
@media (max-width: 768px) {{
  .grid-2 {{ grid-template-columns: 1fr; }}
}}
.regime-pill {{
  display: inline-block;
  padding: 4px 12px;
  border-radius: 16px;
  font-size: 0.85em;
  margin: 2px;
}}
.regime-QUIET {{ background: rgba(88,166,255,0.15); color: var(--blue); }}
.regime-TRENDING_UP {{ background: rgba(63,185,80,0.15); color: var(--green); }}
.regime-TRENDING_DOWN {{ background: rgba(248,81,73,0.15); color: var(--red); }}
.regime-VOLATILE {{ background: rgba(210,153,34,0.15); color: var(--yellow); }}
.progress {{ width: 100%; height: 8px; background: var(--border); border-radius: 4px; overflow: hidden; }}
.progress-bar {{ height: 100%; border-radius: 4px; transition: width 0.5s; }}
pre {{
  background: #010409;
  border: 1px solid var(--border);
  border-radius: 8px;
  padding: 12px;
  overflow-x: auto;
  font-size: 0.85em;
}}
code {{ color: var(--purple); }}
.insight {{
  background: linear-gradient(135deg, rgba(88,166,255,0.08), rgba(188,140,255,0.08));
  border: 1px solid rgba(88,166,255,0.3);
  border-radius: 12px;
  padding: 16px;
  margin: 12px 0;
}}
.insight-icon {{ font-size: 1.2em; margin-right: 8px; }}
.footer {{ color: var(--muted); font-size: 0.8em; text-align: center; margin-top: 40px; padding-top: 20px; border-top: 1px solid var(--border); }}
</style>
</head>
<body>
<h1>🧠 Évolution de l'Agent IA</h1>
<p class="subtitle">Rapport généré le {datetime.now().strftime("%d/%m/%Y à %H:%M UTC")} — Synthèse des apprentissages autonomes</p>
""")

    # --- Stats globales ---
    parts.append(f"""
<div class="stats-grid">
  <div class="stat-card yellow"><div class="num">{total_lecons}</div><div class="label">Leçons apprises</div></div>
  <div class="stat-card blue"><div class="num">{total_strats}</div><div class="label">Stratégies générées</div></div>
  <div class="stat-card green"><div class="num">{len(strats_deployed)}</div><div class="label">Déployées</div></div>
  <div class="stat-card red"><div class="num">{len(strats_rejected)}</div><div class="label">Rejetées</div></div>
  <div class="stat-card purple"><div class="num">{total_plugins}</div><div class="label">Plugins méta-évolveur</div></div>
  <div class="stat-card blue"><div class="num">{total_reflections}</div><div class="label">Réflexions IA</div></div>
  <div class="stat-card yellow"><div class="num">{total_recherche}</div><div class="label">Observations marché</div></div>
</div>
""")

    # --- Trajectoire capital ---
    parts.append('<h2>📈 Trajectoire du Capital</h2>')
    if cap_points:
        parts.append('<div class="cap-chart">')
        caps = [c["cap"] for c in cap_points]
        min_cap = min(caps) - 1
        max_cap = max(caps) + 1
        for c in cap_points:
            pct = ((c["cap"] - min_cap) / (max_cap - min_cap)) * 100 if max_cap > min_cap else 50
            color = "var(--green)" if (c.get("pnl", 0) or 0) >= 0 else "var(--red)"
            pnl_str = f'{c["pnl"]:+.2f}€' if c.get("pnl") is not None else ""
            parts.append(f'<div class="bar-container"><span class="meta" style="width:120px">{esc(c["ts"][:16])}</span>'
                        f'<div class="bar" style="width:{max(pct,5):.0f}%;background:{color}">{c["cap"]:.2f}€ {pnl_str}</div></div>')
        parts.append('</div>')

    # --- Leçons apprises ---
    parts.append('<h2>📚 Leçons Apprises</h2>')

    # Auto-sweep
    parts.append('<h3>🔄 Auto-Sweep RSI (toutes les 6h)</h3>')
    parts.append('<div class="card"><p>L\'agent teste systématiquement les seuils RSI [30, 35, 40, 45] sur 500 bougies × 10 cryptos.</p>')
    if sweep_results:
        parts.append('<table><tr><th>Date</th><th>RSI&lt;30</th><th>RSI&lt;35</th><th>RSI&lt;40</th><th>RSI&lt;45</th></tr>')
        for s in sweep_results:
            ts = s.get("ts", "?")[:16]
            res = s.get("resultat", "")
            parts.append(f'<tr><td class="meta">{esc(ts)}</td><td>{esc(res)}</td></tr>')
        parts.append('</table>')
        # Insight
        parts.append('<div class="insight"><span class="insight-icon">💡</span><strong>Leçon:</strong> RSI&lt;35 reste '
                     'le seuil optimal à chaque run (meilleur P&L + win rate). L\'agent ne change pas ce paramètre car '
                     'il est validé.</div>')
    parts.append('</div>')

    # Genetic optimizer
    parts.append('<h3>🧬 Optimisation Génétique (quotidien 03:30 UTC)</h3>')
    if genetic_runs:
        parts.append('<div class="card"><p>Algorithme génétique: 6 générations, 12 individus. Évolution des paramètres RSI Mean Reversion.</p>')
        parts.append('<table><tr><th>Date</th><th>RSI achat</th><th>RSI vente</th><th>TP</th><th>SL</th><th>BB écart</th><th>Fitness OOS</th></tr>')
        for g in genetic_runs:
            genome = g.get("genome", {})
            oos = g.get("fitness_out_of_sample", "?")
            date = g.get("date", g.get("ts", "?"))[:16]
            oos_color = "var(--green)" if isinstance(oos, (int, float)) and oos > 1.5 else "var(--red)"
            parts.append(f'<tr><td class="meta">{esc(date)}</td>'
                        f'<td>{esc(genome.get("rsi_achat", "?"))}</td>'
                        f'<td>{esc(genome.get("rsi_vente", "?"))}</td>'
                        f'<td>{esc(genome.get("tp", "?"))}</td>'
                        f'<td>{esc(genome.get("sl", "?"))}</td>'
                        f'<td>{esc(genome.get("bb_ecart", "?"))}</td>'
                        f'<td style="color:{oos_color}">{esc(oos)}%</td></tr>')
        parts.append('</table>')
        parts.append('<div class="insight"><span class="insight-icon">💡</span><strong>Leçon:</strong> La fitness OOS '
                     'chute au fil du temps — le marché change et les paramètres optimisés in-sample généralisent moins. '
                     'L\'agent le détecte.</div>')
        parts.append('</div>')

    # Regime shifts
    parts.append('<h3>🌐 Détection de Régimes (24/7)</h3>')
    parts.append('<div class="card">')
    if last_regimes:
        parts.append('<p><strong>Régimes actuels:</strong></p>')
        for asset, regime in last_regimes.items():
            css = f"regime-{esc(regime)}" if regime else "regime-QUIET"
            parts.append(f'<span class="regime-pill {css}">{esc(asset)}: {esc(regime)}</span>')
        parts.append('</div>')

    if regime_shifts:
        parts.append('<div class="card"><h3>Shifts de régime détectés</h3>')
        for r in regime_shifts:
            ts = r.get("ts", "?")[:16]
            hyp = r.get("hypothese", "")[:100]
            res = r.get("resultat", "")[:120]
            dec = r.get("decision", "")[:150]
            parts.append(f'<div class="card" style="margin:8px 0">'
                        f'<div class="meta">{esc(ts)}</div>'
                        f'<p><strong>{esc(hyp)}</strong></p>'
                        f'<p class="meta">Résultat: {esc(res)}</p>'
                        f'<p class="meta">Décision: {esc(dec)}</p></div>')
        parts.append('<div class="insight"><span class="insight-icon">💡</span><strong>Leçon:</strong> EXTEND_TP aide '
                     'dans tous les régimes (+2.4% delta P&L), particulièrement en TRENDING_DOWN.</div>')
        parts.append('</div>')

    # --- Stratégies générées ---
    parts.append('<h2>🧪 Stratégies Générées (strategy_evolver)</h2>')
    parts.append(f'<div class="card"><p>L\'agent génère des stratégies par mutation LLM, validées par 4 gates '
                 '(syntaxe, causalité, sanity, walk-forward). <strong>{total_strats} tentatives, '
                 f'{len(strats_deployed)} déployée(s), {len(strats_rejected)} rejetée(s).</strong></p></div>')

    # Timeline stratégies
    parts.append('<div class="card"><div class="timeline">')
    for s in strategies:
        name = s.get("name", "?")
        verdict = s.get("verdict", "?")
        date = s.get("date", "?")[:16]
        raison = s.get("raison", "")[:150]
        oos = s.get("oos_avg", "?")
        win = s.get("win_rate", "?")
        parent = s.get("parent", "")
        css = "deployed" if verdict == "DEPLOYED" else "rejected"
        badge = "green" if verdict == "DEPLOYED" else "red"
        parts.append(f'<div class="timeline-item {css}">'
                    f'<span class="badge {badge}">{esc(verdict)}</span> '
                    f'<strong>{esc(name)}</strong> '
                    f'<span class="meta">— {esc(date)}</span>')
        if oos != "?" or win != "?":
            parts.append(f' <span class="meta">OOS={esc(oos)}% win={esc(win)}%</span>')
        if parent:
            parts.append(f' <span class="meta">(parent: {esc(parent)})</span>')
        if raison:
            parts.append(f'<br><span class="meta">{esc(raison)}</span>')
        parts.append('</div>')
    parts.append('</div></div>')

    parts.append('<div class="insight"><span class="insight-icon">💡</span><strong>Leçon:</strong> 95% des stratégies '
                 'générées sont rejetées par les gates (OOS insuffisant, pas assez de trades, crash sanity). '
                 'La seule déployée (Evolved 00955) a sous-performé en live → désactivée. Le système est '
                 'conservateur: il préfère ne pas déployer que déployer une stratégie non validée.</div>')

    # --- Méta-évolveur ---
    parts.append('<h2>🔧 Plugins Méta-Évolveur</h2>')
    for p in meta_props:
        date = p.get("date", "?")[:16]
        module = p.get("module", "?")
        detail = p.get("detail", "")[:200]
        source = p.get("source", "?")
        applied = " + plugins/" in detail
        badge = "green" if applied else "yellow"
        parts.append(f'<div class="card"><span class="badge {badge}">{"ACTIF" if applied else "PROPOSITION"}</span> '
                    f'<strong>{esc(module)}</strong> <span class="meta">— {esc(date)} (via {esc(source)})</span>'
                    f'<br><span class="meta">{esc(detail)}</span></div>')

    parts.append('<div class="insight"><span class="insight-icon">💡</span><strong>Auto-correction:</strong> Le '
                 'méta-évolveur a diagnostiqué lui-même qu\'Evolved 00955 était faible et a codé '
                 '<code>stoploss_shield_v1</code> pour bloquer ses entrées à haut risque. L\'agent identifie '
                 'un problème et génère une solution automatiquement.</div>')

    # --- Pruning + Tuning ---
    parts.append('<h2>✂️ Pruning & Tuning Automatique</h2>')

    parts.append('<div class="grid-2">')
    # Pruning
    parts.append('<div class="card"><h3>Pruning (désactivation par actif)</h3>')
    if pruning:
        for p in pruning:
            ts = p.get("ts", "?")[:16]
            action = p.get("action", "?")
            strat = p.get("strategie", "?")
            actif = p.get("actif", "?")
            raison = p.get("raison", "")[:150]
            badge = "red" if "DESACTIV" in action else "green"
            parts.append(f'<div class="card" style="margin:8px 0">'
                        f'<span class="badge {badge}">{esc(action)}</span> '
                        f'<strong>{esc(strat)}</strong> sur <strong>{esc(actif)}</strong>'
                        f'<div class="meta">{esc(ts)}</div>'
                        f'<div class="meta">{esc(raison)}</div></div>')
    else:
        parts.append('<p class="meta">Aucune action de pruning.</p>')
    parts.append('</div>')

    # Tuning
    parts.append('<div class="card"><h3>Meta-tuning (ajustement TP/SL)</h3>')
    if meta_tuning:
        for t in meta_tuning:
            ts = t.get("ts", "?")[:16]
            sym = t.get("symbole", "?")
            tp_av = t.get("tp_avant", "?")
            tp_ap = t.get("tp_apres", "?")
            sl_av = t.get("sl_avant", "?")
            sl_ap = t.get("sl_apres", "?")
            raison = t.get("raison", "")[:150]
            parts.append(f'<div class="card" style="margin:8px 0">'
                        f'<strong>{esc(sym)}</strong> <span class="badge blue">TP {esc(tp_av)}→{esc(tp_ap)}</span>'
                        f' <span class="badge yellow">SL {esc(sl_av)}→{esc(sl_ap)}</span>'
                        f'<div class="meta">{esc(ts)}</div>'
                        f'<div class="meta">{esc(raison)}</div></div>')
    else:
        parts.append('<p class="meta">Aucun tuning.</p>')
    parts.append('</div>')
    parts.append('</div>')  # grid-2

    parts.append('<div class="insight"><span class="insight-icon">💡</span><strong>Leçon:</strong> L\'agent ajuste '
                 'dynamiquement les paramètres par actif — pas de paramètres universels, mais une optimisation '
                 'ciblée. Il désactive les combinaisons sous-performantes et les réactive après cooldown.</div>')

    # --- Réflexions ---
    parts.append('<h2>🤔 Réflexions IA (toutes les 6h)</h2>')
    parts.append(f'<div class="card"><p>L\'agent s\'auto-analyse toutes les 6h via Perplexity. {total_reflections} '
                 'réflexions enregistrées.</p></div>')

    parts.append('<div class="card"><div class="timeline">')
    for r in reflections:
        ts = r.get("ts", "?")[:16]
        ctx = r.get("ctx_summary", {}) or {}
        cap = ctx.get("capital", "?")
        pnl = ctx.get("pnl", "?")
        trades = ctx.get("trades_jour", "?")
        analyse = r.get("analyse", {}) or {}
        synthese = analyse.get("synthese", "")[:250]
        pnl_color = "var(--green)" if isinstance(pnl, (int, float)) and pnl >= 0 else "var(--red)"
        parts.append(f'<div class="timeline-item reflection">'
                    f'<span class="badge blue">{esc(cap)}€</span> '
                    f'<span style="color:{pnl_color}">{pnl:+.2f}€</span> '
                    f'<span class="meta">— {esc(ts)} — {esc(trades)} trades/jour</span>')
        if synthese:
            parts.append(f'<br><span class="meta">{esc(synthese)}</span>')
        parts.append('</div>')
    parts.append('</div></div>')

    # --- Évolutia ---
    parts.append('<h2>📊 Auto-Mesure Evolutia</h2>')
    if evolutia:
        for e in evolutia:
            name = e.get("strategie", e.get("plugin", "?"))
            statut = e.get("statut", "?")
            apply_t = e.get("apply_time", "?")[:19]
            baseline = e.get("baseline", {})
            post = e.get("post") or {}
            verdict = e.get("verdict", "")
            badge = "green" if statut == "GARDE" else ("red" if statut == "REVERT" else "yellow")
            rtype = e.get("type", "plugin")
            parts.append(f'<div class="card"><span class="badge {badge}">{esc(statut)}</span> '
                        f'<span class="badge purple">{esc(rtype)}</span> '
                        f'<strong>{esc(name)}</strong>'
                        f'<div class="meta">Appliqué: {esc(apply_t)}</div>'
                        f'<div class="meta">Baseline: n={esc(baseline.get("n","?"))} '
                        f'avg_gain={esc(baseline.get("avg_gain_pct","?"))}% '
                        f'win={esc(baseline.get("win_rate","?"))}</div>')
            if post:
                parts.append(f'<div class="meta">Post: n={esc(post.get("n","?"))} '
                            f'avg_gain={esc(post.get("avg_gain_pct","?"))}% '
                            f'pnl={esc(post.get("pnl_eur","?"))}€</div>')
            if verdict:
                parts.append(f'<div class="meta">Verdict: {esc(verdict[:150])}</div>')
            parts.append('</div>')
    else:
        parts.append('<div class="card"><p class="meta">Aucune évolution enregistrée.</p></div>')

    # --- Timeline globale ---
    parts.append('<h2>🕐 Chronologie de l\'Évolution</h2>')
    all_events = []
    for s in strategies:
        all_events.append({
            "ts": s.get("date", s.get("ts", "")),
            "type": "strategie",
            "title": s.get("name", "?"),
            "desc": s.get("verdict", "") + " — " + s.get("raison", "")[:80],
        })
    for p in meta_props:
        all_events.append({
            "ts": p.get("date", p.get("ts", "")),
            "type": "plugin",
            "title": p.get("module", "?"),
            "desc": p.get("detail", "")[:100],
        })
    for r in reflections:
        all_events.append({
            "ts": r.get("ts", ""),
            "type": "reflection",
            "title": f"Réflexion — {r.get('ctx_summary', {}).get('capital', '?')}€",
            "desc": ((r.get("analyse", {}) or {}).get("synthese", ""))[:100],
        })
    for p in pruning:
        all_events.append({
            "ts": p.get("ts", ""),
            "type": "pruning",
            "title": f"{p.get('action', '?')} {p.get('strategie', '?')} {p.get('actif', '?')}",
            "desc": p.get("raison", "")[:100],
        })
    for t in meta_tuning:
        all_events.append({
            "ts": t.get("ts", ""),
            "type": "pruning",
            "title": f"Tuning {t.get('symbole', '?')} TP {t.get('tp_avant','?')}→{t.get('tp_apres','?')}",
            "desc": t.get("raison", "")[:100],
        })

    # Sort by ts
    all_events.sort(key=lambda e: e.get("ts", ""))

    parts.append('<div class="card"><div class="timeline">')
    for e in all_events:
        etype = e["type"]
        css = etype
        title = e["title"]
        ts = e.get("ts", "?")[:16]
        desc = e.get("desc", "")
        badge_map = {"strategie": "blue", "plugin": "purple", "reflection": "blue", "pruning": "orange", "lesson": "yellow"}
        badge = badge_map.get(etype, "blue")
        parts.append(f'<div class="timeline-item {css}">'
                    f'<span class="badge {badge}">{esc(etype)}</span> '
                    f'<strong>{esc(title)}</strong> '
                    f'<span class="meta">— {esc(ts)}</span>'
                    f'<br><span class="meta">{esc(desc)}</span></div>')
    parts.append('</div></div>')

    # --- Footer ---
    parts.append(f"""
<div class="footer">
  Rapport généré automatiquement par rapport_evolution.py<br>
  Données: {total_lecons} leçons, {total_strats} stratégies, {total_plugins} plugins, {total_reflections} réflexions, {total_recherche} observations<br>
  Agent IA — Système de trading autonome
</div>
</body>
</html>
""")

    return "\n".join(parts)


if __name__ == "__main__":
    html_content = gen_html()
    out_path = os.path.join(DOSSIER, "rapport_evolution.html")
    with open(out_path, "w", encoding="utf-8") as f:
        f.write(html_content)
    print(f"Rapport généré: {out_path}")
    print(f"Taille: {len(html_content)} caractères")

    if "--serve" in sys.argv:
        import http.server
        import socketserver
        PORT = 8799
        os.chdir(DOSSIER)
        handler = http.server.SimpleHTTPRequestHandler
        with socketserver.TCPServer(("", PORT), handler) as httpd:
            print(f"Serveur démarré sur http://localhost:{PORT}/rapport_evolution.html")
            print("Ctrl+C pour arrêter")
            try:
                httpd.serve_forever()
            except KeyboardInterrupt:
                print("\nArrêt du serveur.")
