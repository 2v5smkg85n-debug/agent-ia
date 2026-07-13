#!/usr/bin/env python3
"""Rapport de performance (Phase 3) — integre au dashboard sur la route /perf.
Lit: paper_trading, backtests_pro, ml_performances, stats_marches."""
import json
import html


def render_chart(historique):
    """Graphique SVG du capital (copie locale pour eviter import circulaire)."""
    if not historique:
        return "<p class='muted'>Pas d'historique</p>"
    vals = []
    for i, h in enumerate(historique):
        v = None
        if isinstance(h, dict):
            for k in ("capital", "valeur", "solde", "total", "cap", "capital_total"):
                if k in h:
                    try:
                        v = float(h[k])
                    except (ValueError, TypeError):
                        pass
                    break
            if v is None:
                for val in h.values():
                    try:
                        v = float(val)
                        break
                    except (ValueError, TypeError):
                        pass
        elif isinstance(h, (int, float)):
            v = float(h)
        else:
            try:
                v = float(h)
            except (ValueError, TypeError):
                pass
        if v is not None:
            vals.append(v)
    if len(vals) < 2:
        return f"<p class='muted'>{len(vals)} point(s)</p>"
    W, H, P = 640, 220, 50
    vmin, vmax = min(vals), max(vals)
    if vmax == vmin:
        vmax = vmin + 1
    n = len(vals)
    pts = []
    for i, v in enumerate(vals):
        x = P + (W - 2 * P) * (i / (n - 1))
        y = H - P - (H - 2 * P) * ((v - vmin) / (vmax - vmin))
        pts.append(f"{x:.1f},{y:.1f}")
    color = "#4ade80" if vals[-1] >= vals[0] else "#f87171"
    poly = " ".join(pts)
    return f'''<svg viewBox="0 0 {W} {H}" style="width:100%;height:auto;background:#161b22;border:1px solid #30363d;border-radius:8px" preserveAspectRatio="xMidYMid meet">
      <line x1="{P}" y1="{H-P}" x2="{W-P}" y2="{H-P}" stroke="#30363d" />
      <text x="{P-8}" y="{P+4}" text-anchor="end" fill="#8b949e" font-size="10">{vmin:.2f}</text>
      <text x="{P-8}" y="{H-P}" text-anchor="end" fill="#8b949e" font-size="10">{vmax:.2f}</text>
      <polyline points="{poly}" fill="none" stroke="{color}" stroke-width="2.5" />
    </svg>'''


def load(name, default):
    try:
        return json.load(open(name))
    except Exception:
        return default


def esc(s):
    return html.escape(str(s))


def num(v, default=0.0):
    try:
        return float(v)
    except (ValueError, TypeError):
        return default


def fmt(v):
    try:
        return f"{float(v):.2f}"
    except (ValueError, TypeError):
        return str(v)


def color_pct(v):
    cls = "pos" if v >= 0 else "neg"
    return f"<span class='{cls}'>{v:+.2f}%</span>"


# ---------- LIVE PAPER TRADING ----------
def compute_live(pt):
    cap_init = num(pt.get("capital_initial", 1000))
    liq = num(pt.get("liquidites", 0))
    positions = pt.get("positions", [])
    hist = pt.get("historique", [])
    frais = num(pt.get("total_frais", 0))
    pic = num(pt.get("pic_capital", cap_init))
    tf = pt.get("trades_fermes", [])
    cap = num(pt.get("capital_actuel")) if pt.get("capital_actuel") is not None else liq + sum(num(p.get("valeur", 0)) for p in positions if isinstance(p, dict))
    val_pos = cap - liq
    perf = (cap - cap_init) / cap_init * 100 if cap_init else 0
    dd = (cap - pic) / pic * 100 if pic else 0

    # trades fermes
    gains = [num(t.get("gain_eur")) for t in tf]
    wins = [g for g in gains if g > 0]
    losses = [g for g in gains if g < 0]
    gross_win = sum(wins)
    gross_loss = abs(sum(losses))
    pnl = sum(gains)
    winrate = len(wins) / len(gains) * 100 if gains else 0
    pf = gross_win / gross_loss if gross_loss > 0 else (float("inf") if gross_win > 0 else 0)
    best = max(gains) if gains else 0
    worst = min(gains) if gains else 0
    return {
        "cap_init": cap_init, "cap": cap, "liq": liq, "val_pos": val_pos,
        "perf": perf, "frais": frais, "dd": dd, "pic": pic,
        "n_trades": len(tf), "winrate": winrate, "pnl": pnl,
        "pf": pf, "best": best, "worst": worst, "trades": tf, "hist": hist,
    }


# ---------- BACKTESTS ----------
def compute_backtests(bp):
    if not bp:
        return None
    n = len(bp)
    retours = [num(b.get("retour_pct")) for b in bp]
    wrs = [num(b.get("win_rate")) for b in bp if b.get("win_rate") is not None]
    pfs = [num(b.get("profit_factor")) for b in bp if b.get("profit_factor") is not None]
    dds = [num(b.get("drawdown_max")) for b in bp if b.get("drawdown_max") is not None]
    sharpes = [num(b.get("sharpe")) for b in bp if b.get("sharpe") is not None]
    gagnantes = sum(1 for b in bp if b.get("verdict") == "GAGNANTE")

    def avg(lst):
        return sum(lst) / len(lst) if lst else 0

    # par marche
    marches = {}
    for b in bp:
        m = b.get("marche", "?")
        marches.setdefault(m, []).append(b)
    per_marche = []
    for m, lst in marches.items():
        rets = [num(x.get("retour_pct")) for x in lst]
        pfm = [num(x.get("profit_factor")) for x in lst if x.get("profit_factor") is not None]
        wrm = [num(x.get("win_rate")) for x in lst if x.get("win_rate") is not None]
        g = sum(1 for x in lst if x.get("verdict") == "GAGNANTE")
        per_marche.append({
            "marche": m, "n": len(lst),
            "retour": avg(rets), "pf": avg(pfm), "wr": avg(wrm),
            "gagnantes_pct": g / len(lst) * 100 if lst else 0,
        })
    per_marche.sort(key=lambda x: x["retour"], reverse=True)

    # par strategie (audit)
    strat = {}
    for b in bp:
        s = b.get("strategie", "?")
        strat.setdefault(s, []).append(b)
    per_strat = []
    for s, lst in strat.items():
        rets = [num(x.get("retour_pct")) for x in lst]
        pfs2 = [num(x.get("profit_factor")) for x in lst if x.get("profit_factor") is not None]
        wrs2 = [num(x.get("win_rate")) for x in lst if x.get("win_rate") is not None]
        g = sum(1 for x in lst if x.get("verdict") == "GAGNANTE")
        avg_ret = avg(rets)
        avg_pf = avg(pfs2)
        avg_wr = avg(wrs2)
        pct_g = g / len(lst) * 100 if lst else 0
        # recommandation
        if avg_ret > 0 and avg_pf >= 1.0 and pct_g >= 50:
            reco = "Garder"
        elif avg_ret < 0 or avg_pf < 1:
            reco = "Couper"
        else:
            reco = "Surveiller"
        per_strat.append({
            "strategie": s, "n": len(lst), "retour": avg_ret,
            "pf": avg_pf, "wr": avg_wr, "gagnantes_pct": pct_g, "reco": reco,
        })
    per_strat.sort(key=lambda x: x["retour"], reverse=True)

    return {
        "n": n, "avg_retour": avg(retours), "avg_wr": avg(wrs),
        "avg_pf": avg(pfs), "avg_dd": avg(dds), "avg_sharpe": avg(sharpes),
        "pct_gagnantes": gagnantes / n * 100 if n else 0,
        "per_marche": per_marche, "per_strat": per_strat,
    }


# ---------- ML WALK-FORWARD ----------
def compute_ml(ml):
    rows = []
    for actif, d in ml.items():
        prec = num(d.get("precision_walk_forward"))
        marche = d.get("marche", "?")
        if prec >= 55:
            edge = "Edge"
        elif prec >= 50:
            edge = "Faible"
        else:
            edge = "Negatif"
        rows.append({"actif": actif, "marche": marche, "prec": prec, "edge": edge})
    rows.sort(key=lambda x: x["prec"], reverse=True)
    return rows


def render_perf(token=""):
    pt = load("paper_trading.json", {})
    # Preferer les backtests reels (moteur Yahoo Finance) si disponibles
    bp = load("backtests_reels_pro.json", []) or load("backtests_pro.json", [])
    bt_source = "backtests_reels_pro.json" if load("backtests_reels_pro.json", []) else "backtests_pro.json (anciens IA)"
    ml = load("ml_performances.json", {})
    sm = load("stats_marches.json", {})

    live = compute_live(pt)
    bt = compute_backtests(bp)
    mlrows = compute_ml(ml)

    style = """<style>
:root{--bg:#0d1117;--card:#161b22;--txt:#e6edf3;--muted:#8b949e;--pos:#4ade80;--neg:#f87171;--warn:#fbbf24;--border:#30363d}
*{box-sizing:border-box}
body{background:var(--bg);color:var(--txt);font-family:-apple-system,BlinkMacSystemFont,"Segoe UI",Roboto,sans-serif;margin:0 auto;padding:14px;max-width:760px}
h1{font-size:19px;margin:6px 0 2px}
h3{font-size:14px;margin:18px 0 8px;border-bottom:1px solid var(--border);padding-bottom:4px}
a.lnk{color:#58a6ff;font-size:13px}
.muted{color:var(--muted);font-size:13px}
.cards{display:grid;grid-template-columns:repeat(3,1fr);gap:8px;margin:12px 0}
.card{background:var(--card);border:1px solid var(--border);border-radius:8px;padding:9px}
.card .lbl{font-size:10px;color:var(--muted);text-transform:uppercase;letter-spacing:.5px}
.card .val{font-size:17px;font-weight:600;margin-top:2px}
.card.pos .val{color:var(--pos)} .card.neg .val{color:var(--neg)} .card.warn .val{color:var(--warn)}
.pos{color:var(--pos)} .neg{color:var(--neg)} .warn{color:var(--warn)}
table{width:100%;border-collapse:collapse;font-size:12px;margin-bottom:8px}
th,td{text-align:right;padding:6px 8px;border-bottom:1px solid var(--border);white-space:nowrap}
th:first-child,td:first-child{text-align:left}
th{color:var(--muted);font-weight:600;font-size:11px}
.badge{font-size:10px;padding:2px 6px;border-radius:4px}
.b-ok{background:#16331f;color:var(--pos)} .b-cut{background:#3a1717;color:var(--neg)} .b-watch{background:#3a2f0a;color:var(--warn)}
</style>"""

    # LIVE
    live_cards = f"""
    <div class="cards">
      <div class="card {'pos' if live['perf']>=0 else 'neg'}"><div class="lbl">Performance</div><div class="val">{live['perf']:+.2f}%</div></div>
      <div class="card"><div class="lbl">Capital</div><div class="val">{fmt(live['cap'])} €</div></div>
      <div class="card"><div class="lbl">Trades fermés</div><div class="val">{live['n_trades']}</div></div>
      <div class="card {'pos' if live['winrate']>=50 else 'neg'}"><div class="lbl">Win rate live</div><div class="val">{live['winrate']:.0f}%</div></div>
      <div class="card {'pos' if live['pnl']>=0 else 'neg'}"><div class="lbl">P&L net</div><div class="val">{live['pnl']:+.2f} €</div></div>
      <div class="card {'neg' if live['pf']<1 else 'pos'}"><div class="lbl">Profit factor</div><div class="val">{live['pf']:.2f}</div></div>
      <div class="card"><div class="lbl">Frais</div><div class="val">{fmt(live['frais'])} €</div></div>
      <div class="card neg"><div class="lbl">Drawdown</div><div class="val">{live['dd']:+.2f}%</div></div>
      <div class="card"><div class="lbl">Pic</div><div class="val">{fmt(live['pic'])} €</div></div>
    </div>"""

    # trades table
    tt = "<h3>Trades fermés (live)</h3>"
    if live["trades"]:
        tt += '<table><thead><tr><th>Actif</th><th>Marché</th><th>Var%</th><th>Gain €</th><th>Frais €</th><th>Raison</th></tr></thead><tbody>'
        for t in reversed(live["trades"]):
            g = num(t.get("gain_eur"))
            gc = "pos" if g >= 0 else "neg"
            tt += f"<tr><td>{esc(t.get('symbole',''))}</td><td>{esc(t.get('marche',''))}</td><td class='{gc}'>{num(t.get('variation_pct')):+.2f}%</td><td class='{gc}'>{g:+.2f}</td><td>{fmt(t.get('frais_total'))}</td><td>{esc(t.get('raison','')[:24])}</td></tr>"
        tt += "</tbody></table>"
    else:
        tt += "<p class='muted'>Aucun trade fermé</p>"

    # chart
    chart = ""
    if live["hist"]:
        chart = f"<h3>Évolution du capital (live)</h3>{render_chart(live['hist'])}"

    # BACKTESTS
    bt_html = ""
    if bt:
        bt_cards = f"""
      <h3>Synthèse backtests ({bt['n']} tests) — {bt_source}</h3>
      <div class="cards">
        <div class="card {'pos' if bt['avg_retour']>=0 else 'neg'}"><div class="lbl">Retour moyen</div><div class="val">{bt['avg_retour']:+.2f}%</div></div>
        <div class="card"><div class="lbl">Profit factor moy</div><div class="val">{bt['avg_pf']:.2f}</div></div>
        <div class="card"><div class="lbl">Win rate moy</div><div class="val">{bt['avg_wr']:.0f}%</div></div>
        <div class="card {'pos' if bt['pct_gagnantes']>=50 else 'neg'}"><div class="lbl">% gagnantes</div><div class="val">{bt['pct_gagnantes']:.0f}%</div></div>
        <div class="card warn"><div class="lbl">Drawdown moy</div><div class="val">{bt['avg_dd']:.1f}%</div></div>
        <div class="card"><div class="lbl">Sharpe moy</div><div class="val">{bt['avg_sharpe']:.2f}</div></div>
      </div>"""
        # par marche
        mm = "<h3>Par marché</h3><table><thead><tr><th>Marché</th><th>Tests</th><th>Retour moy</th><th>PF moy</th><th>Win rate</th><th>% gagnantes</th></tr></thead><tbody>"
        for m in bt["per_marche"]:
            mc = "pos" if m["retour"] >= 0 else "neg"
            mg = "pos" if m["gagnantes_pct"] >= 50 else "neg"
            mm += f"<tr><td>{esc(m['marche'])}</td><td>{m['n']}</td><td class='{mc}'>{m['retour']:+.2f}%</td><td>{m['pf']:.2f}</td><td>{m['wr']:.0f}%</td><td class='{mg}'>{m['gagnantes_pct']:.0f}%</td></tr>"
        mm += "</tbody></table>"
        # audit strategies
        keep = [s for s in bt["per_strat"] if s["reco"] == "Garder"]
        cut = [s for s in bt["per_strat"] if s["reco"] == "Couper"]
        audit = f"<h3>Audit stratégies ({len(bt['per_strat'])}) — {len(keep)} à garder, {len(cut)} à couper</h3>"
        audit += "<table><thead><tr><th>Stratégie</th><th>Tests</th><th>Retour moy</th><th>PF</th><th>Win rate</th><th>Verdict</th></tr></thead><tbody>"
        for s in bt["per_strat"]:
            bc = {"Garder": "b-ok", "Couper": "b-cut", "Surveiller": "b-watch"}[s["reco"]]
            sc = "pos" if s["retour"] >= 0 else "neg"
            audit += f"<tr><td>{esc(s['strategie'])}</td><td>{s['n']}</td><td class='{sc}'>{s['retour']:+.2f}%</td><td>{s['pf']:.2f}</td><td>{s['wr']:.0f}%</td><td><span class='badge {bc}'>{s['reco']}</span></td></tr>"
        audit += "</tbody></table>"
        bt_html = bt_cards + mm + audit

    # ML
    ml_html = ""
    if mlrows:
        ml_html = "<h3>Walk-forward ML (précision par actif)</h3>"
        ml_html += '<table><thead><tr><th>Actif</th><th>Marché</th><th>Précision WF</th><th>Edge</th></tr></thead><tbody>'
        for r in mlrows:
            ec = {"Edge": "pos", "Faible": "warn", "Negatif": "neg"}[r["edge"]]
            ml_html += f"<tr><td>{esc(r['actif'])}</td><td>{esc(r['marche'])}</td><td>{r['prec']:.1f}%</td><td class='{ec}'>{r['edge']}</td></tr>"
        ml_html += "</tbody></table>"

    # MARKET STATS
    ms_html = ""
    if sm:
        ms_html = "<h3>Stats marché (signaux live)</h3>"
        ms_html += '<table><thead><tr><th>Marché</th><th>Total</th><th>Gagnés</th><th>Perdus</th><th>Win rate</th></tr></thead><tbody>'
        for m, d in sm.items():
            wr = num(d.get("win_rate")) * 100 if num(d.get("win_rate")) <= 1 else num(d.get("win_rate"))
            wrc = "pos" if wr >= 50 else "neg"
            ms_html += f"<tr><td>{esc(m)}</td><td>{d.get('total','?')}</td><td>{d.get('gagnes','?')}</td><td>{d.get('perdus','?')}</td><td class='{wrc}'>{wr:.0f}%</td></tr>"
        ms_html += "</tbody></table>"

    return f"""<!DOCTYPE html><html lang="fr"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Agent IA — Performance</title>
<meta http-equiv="refresh" content="120">
{style}</head><body>
<h1>📈 Performance — Phase 3</h1>
<div class="muted"><a class="lnk" href="/?token={esc(token)}">← Dashboard</a> · <a class="lnk" href="/perf?token={esc(token)}">Rafraîchir</a> · actualisation 120s</div>
<h3>Track record live (paper trading)</h3>
{live_cards}
{chart}
{tt}
{bt_html}
{ml_html}
{ms_html}
<div class="muted" style="margin-top:16px">Règle d'or: ne pas trader en réel avant 8-12 sem. de rentabilité positive nette de frais.</div>
</body></html>"""


if __name__ == "__main__":
    print(render_perf())
