#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Observabilite (Phase 5) — courbe d'equity + metriques de risque + breakdown live.

Corrige le bug: pf['historique'] contient les trades fermes, pas une courbe de capital.
Ce module maintient equity_history.jsonl (vrais snapshots de capital) et expose:
  - snapshot_equity(pf): ajoute un point de capital (dedup ~5min), met a jour pic_capital
  - charger_equity(): lit la courbe
  - calculer_metriques(trades, equity): Sharpe, Sortino, expectancy, streaks, max DD
  - breakdown_strategies(trades): PnL/win_rate par strategie et marche (live)
  - render_equity_chart(): SVG de la courbe de capital
  - render_risk_metrics(trades): cartes metriques
  - render_breakdown(trades): table par strategie

Utilise par performance.py (route /perf) et paper_trading.py (snapshot par tick).
"""
import json
import os
import re
import math
import html
from datetime import datetime

DOSSIER = os.path.dirname(os.path.abspath(__file__))
EQUITY_FILE = os.path.join(DOSSIER, "equity_history.jsonl")
PT_FILE = os.path.join(DOSSIER, "paper_trading.json")
DEDUP_SECONDES = 300  # 5 min entre snapshots


def _num(v, d=0.0):
    try:
        return float(v)
    except (ValueError, TypeError):
        return d


# ---------------------------------------------------------------- EQUITY
def _capital_total(pf):
    liq = _num(pf.get("liquidites", 0))
    pos = pf.get("positions", [])
    val = sum(_num(p.get("montant_eur", 0)) for p in pos if isinstance(p, dict))
    return liq + val, liq, val


def snapshot_equity(pf=None):
    """Ajoute un snapshot de capital a equity_history.jsonl (dedup 5 min).
    Met a jour pic_capital (high-water mark du capital TOTAL) dans pf.
    A appeler en fin de tick() avant sauver_portefeuille. Sans risque (try/except)."""
    try:
        if pf is None:
            try:
                pf = json.load(open(PT_FILE, encoding="utf-8"))
            except Exception:
                return
        capital, liq, val = _capital_total(pf)
        now = datetime.utcnow().timestamp()
        # dedup
        try:
            with open(EQUITY_FILE, "r", encoding="utf-8") as f:
                lignes = f.readlines()
            if lignes:
                dernier = json.loads(lignes[-1].strip())
                if now - float(dernier.get("ts", 0)) < DEDUP_SECONDES:
                    # ne pas skipper la maj du pic quand meme
                    pic = float(pf.get("pic_capital", 0))
                    if capital > pic:
                        pf["pic_capital"] = round(capital, 2)
                    return
        except FileNotFoundError:
            pass
        except Exception:
            pass
        entree = {
            "ts": now,
            "date": datetime.utcnow().strftime("%Y-%m-%d %H:%M"),
            "capital": round(capital, 2),
            "liquidites": round(liq, 2),
            "positions_value": round(val, 2),
            "n_positions": len(pf.get("positions", [])),
        }
        with open(EQUITY_FILE, "a", encoding="utf-8") as f:
            f.write(json.dumps(entree) + "\n")
        # high-water mark du capital total (pas juste liquidites)
        pic = float(pf.get("pic_capital", 0))
        if capital > pic:
            pf["pic_capital"] = round(capital, 2)
    except Exception as e:
        # Ne jamais casser le tick
        try:
            print(f"[obs] snapshot_equity err: {e}")
        except Exception:
            pass


def charger_equity(limite=2000):
    """Lit equity_history.jsonl -> liste de dicts."""
    out = []
    try:
        with open(EQUITY_FILE, "r", encoding="utf-8") as f:
            lignes = f.readlines()
    except FileNotFoundError:
        return out
    for l in lignes[-limite:]:
        l = l.strip()
        if not l:
            continue
        try:
            out.append(json.loads(l))
        except Exception:
            continue
    return out


# ---------------------------------------------------------------- METRIQUES
def calculer_metriques(trades, equity=None):
    """Metriques de risque depuis trades fermes (+ equity pour DD)."""
    gains = [_num(t.get("gain_eur")) for t in trades]
    n = len(gains)
    if n == 0:
        return None
    wins = [g for g in gains if g > 0]
    losses = [g for g in gains if g < 0]
    gross_win = sum(wins)
    gross_loss = abs(sum(losses))
    pnl = sum(gains)
    win_rate = len(wins) / n * 100
    loss_rate = len(losses) / n * 100
    avg_win = (sum(wins) / len(wins)) if wins else 0
    avg_loss = (sum(losses) / len(losses)) if losses else 0
    pf = gross_win / gross_loss if gross_loss > 0 else (float("inf") if gross_win > 0 else 0)
    # expectancy (€/trade)
    expectancy = (win_rate / 100 * avg_win) - (loss_rate / 100 * avg_loss)
    # streaks max
    max_win_streak = max_loss_streak = cur_w = cur_l = 0
    for g in gains:
        if g > 0:
            cur_w += 1; cur_l = 0
            max_win_streak = max(max_win_streak, cur_w)
        elif g < 0:
            cur_l += 1; cur_w = 0
            max_loss_streak = max(max_loss_streak, cur_l)
        else:
            cur_w = cur_l = 0
    # Sharpe / Sortino (base trades: rendement = gain / capital_initial)
    cap_init = 1000.0
    rets = [g / cap_init for g in gains]
    if len(rets) > 1:
        mean_r = sum(rets) / len(rets)
        var = sum((r - mean_r) ** 2 for r in rets) / len(rets)
        std = math.sqrt(var)
        downside = [r for r in rets if r < 0]
        dstd = math.sqrt(sum(r ** 2 for r in downside) / len(downside)) if downside else 0.0001
        # annualise: ~ trades/jour * 365. Estimation grossiere.
        sharpe = (mean_r / std * math.sqrt(n)) if std > 0 else 0
        sortino = (mean_r / dstd * math.sqrt(n)) if dstd > 0 else 0
    else:
        sharpe = sortino = 0
    # max drawdown depuis equity curve
    max_dd = 0.0
    if equity:
        cap_vals = [_num(e.get("capital")) for e in equity if _num(e.get("capital")) > 0]
        if len(cap_vals) >= 2:
            pic = cap_vals[0]
            for v in cap_vals:
                if v > pic:
                    pic = v
                dd = (pic - v) / pic * 100 if pic > 0 else 0
                if dd > max_dd:
                    max_dd = dd
    return {
        "n": n, "win_rate": win_rate, "pnl": pnl, "pf": pf,
        "avg_win": avg_win, "avg_loss": avg_loss, "expectancy": expectancy,
        "max_win_streak": max_win_streak, "max_loss_streak": max_loss_streak,
        "sharpe": sharpe, "sortino": sortino, "max_dd": max_dd,
        "best": max(gains) if gains else 0, "worst": min(gains) if gains else 0,
    }


# ---------------------------------------------------------------- BREAKDOWN
_STRAT_RE = re.compile(r"\(([^()\[\],]+?)\s*[\[\),]", re.IGNORECASE)


def _extraire_strategie(trade):
    """Extrait le nom de strategie depuis signal_raison (trades backtest-gagnant).
    Les trades legacy (sans signal_raison) sont regroupes sous 'legacy'."""
    r = trade.get("signal_raison", "") or ""
    m = _STRAT_RE.search(r)
    if m:
        s = m.group(1).strip()
        # eviter les faux positifs (pourcentages, nombres, signes)
        if s and s[0] not in "+-" and not s.replace(".", "").replace(",", "").isdigit():
            return s
    return "legacy"


def breakdown_strategies(trades):
    """PnL / win rate par strategie et par marche (live)."""
    par_strat = {}
    par_marche = {}
    for t in trades:
        s = _extraire_strategie(t)
        m = t.get("marche", "?") or "?"
        g = _num(t.get("gain_eur"))
        for bucket, key in ((par_strat, s), (par_marche, m)):
            d = bucket.setdefault(key, {"n": 0, "wins": 0, "pnl": 0.0})
            d["n"] += 1
            if g > 0:
                d["wins"] += 1
            d["pnl"] += g
    rows_strat = []
    for s, d in par_strat.items():
        rows_strat.append({
            "cle": s, "n": d["n"], "wins": d["wins"],
            "win_rate": d["wins"] / d["n"] * 100 if d["n"] else 0,
            "pnl": d["pnl"],
            "expectancy": d["pnl"] / d["n"] if d["n"] else 0,
        })
    rows_strat.sort(key=lambda x: x["pnl"], reverse=True)
    rows_marche = []
    for m, d in par_marche.items():
        rows_marche.append({
            "cle": m, "n": d["n"], "wins": d["wins"],
            "win_rate": d["wins"] / d["n"] * 100 if d["n"] else 0,
            "pnl": d["pnl"],
            "expectancy": d["pnl"] / d["n"] if d["n"] else 0,
        })
    rows_marche.sort(key=lambda x: x["pnl"], reverse=True)
    return rows_strat, rows_marche


# ---------------------------------------------------------------- RENDER
def _esc(s):
    return html.escape(str(s))


def _fmt(v):
    try:
        return f"{float(v):.2f}"
    except (ValueError, TypeError):
        return str(v)


def render_equity_chart(equity=None):
    """SVG courbe de capital depuis equity_history."""
    if equity is None:
        equity = charger_equity()
    pts = [(_num(e.get("ts")), _num(e.get("capital"))) for e in equity
           if _num(e.get("capital")) > 0]
    if len(pts) < 2:
        return "<p class='muted'>Courbe d'equity en construction (donnees insuffisantes).</p>"
    W, H, P = 680, 240, 55
    caps = [v for _, v in pts]
    vmin, vmax = min(caps), max(caps)
    if vmax == vmin:
        vmax = vmin + 1
    tmin, tmax = pts[0][0], pts[-1][0]
    if tmax == tmin:
        tmax = tmin + 1
    coords = []
    for ts, v in pts:
        x = P + (W - 2 * P) * ((ts - tmin) / (tmax - tmin))
        y = H - P - (H - 2 * P) * ((v - vmin) / (vmax - vmin))
        coords.append(f"{x:.1f},{y:.1f}")
    color = "#4ade80" if caps[-1] >= caps[0] else "#f87171"
    # ligne du capital initial
    cap_init = 1000.0
    yi = H - P - (H - 2 * P) * ((cap_init - vmin) / (vmax - vmin)) if vmin <= cap_init <= vmax else None
    base_line = ""
    if yi is not None:
        base_line = f'<line x1="{P}" y1="{yi:.1f}" x2="{W-P}" y2="{yi:.1f}" stroke="#30363d" stroke-dasharray="4,4" /><text x="{W-P}" y="{yi-4:.1f}" text-anchor="end" fill="#8b949e" font-size="9">initial 1000</text>'
    return f'''<svg viewBox="0 0 {W} {H}" style="width:100%;height:auto;background:#161b22;border:1px solid #30363d;border-radius:8px" preserveAspectRatio="xMidYMid meet">
      {base_line}
      <line x1="{P}" y1="{H-P}" x2="{W-P}" y2="{H-P}" stroke="#30363d" />
      <text x="{P-8}" y="{P+4}" text-anchor="end" fill="#8b949e" font-size="10">{vmax:.2f}</text>
      <text x="{P-8}" y="{H-P}" text-anchor="end" fill="#8b949e" font-size="10">{vmin:.2f}</text>
      <polyline points="{" ".join(coords)}" fill="none" stroke="{color}" stroke-width="2.5" />
      <text x="{P}" y="{P-8}" fill="#8b949e" font-size="9">{pts[0][1] if False else ""}</text>
    </svg>'''


def render_risk_metrics(trades, equity=None):
    """Cartes de metriques de risque."""
    m = calculer_metriques(trades, equity)
    if not m:
        return "<p class='muted'>Pas assez de trades pour les metriques.</p>"
    pf_str = "inf" if m["pf"] == float("inf") else f"{m['pf']:.2f}"
    return f"""
    <div class="cards">
      <div class="card {'pos' if m['expectancy']>=0 else 'neg'}"><div class="lbl">Expectancy/trade</div><div class="val">{m['expectancy']:+.2f} €</div></div>
      <div class="card"><div class="lbl">Sharpe (approx)</div><div class="val">{m['sharpe']:.2f}</div></div>
      <div class="card"><div class="lbl">Sortino (approx)</div><div class="val">{m['sortino']:.2f}</div></div>
      <div class="card warn"><div class="lbl">Max Drawdown</div><div class="val">{m['max_dd']:.2f}%</div></div>
      <div class="card"><div class="lbl">Gain moy</div><div class="val pos">{m['avg_win']:+.2f} €</div></div>
      <div class="card"><div class="lbl">Perte moy</div><div class="val neg">{m['avg_loss']:+.2f} €</div></div>
      <div class="card"><div class="lbl">Streak gain max</div><div class="val">{m['max_win_streak']}</div></div>
      <div class="card"><div class="lbl">Streak perte max</div><div class="val">{m['max_loss_streak']}</div></div>
      <div class="card"><div class="lbl">Meilleur trade</div><div class="val pos">{m['best']:+.2f} €</div></div>
      <div class="card"><div class="lbl">Pire trade</div><div class="val neg">{m['worst']:+.2f} €</div></div>
      <div class="card"><div class="lbl">Profit factor</div><div class="val">{pf_str}</div></div>
    </div>"""


def render_breakdown(trades):
    """Tables breakdown live par strategie et marche."""
    rows_strat, rows_marche = breakdown_strategies(trades)
    if not rows_strat:
        return ""
    def _table(rows, titre):
        h = f"<h3>{titre}</h3><table><thead><tr><th>Clé</th><th>Trades</th><th>Gagnés</th><th>Win rate</th><th>P&L €</th><th>Expectancy</th></tr></thead><tbody>"
        for r in rows:
            gc = "pos" if r["pnl"] >= 0 else "neg"
            wr = r["win_rate"]
            wrc = "pos" if wr >= 50 else "neg"
            h += f"<tr><td>{_esc(r['cle'])}</td><td>{r['n']}</td><td>{r['wins']}</td><td class='{wrc}'>{wr:.0f}%</td><td class='{gc}'>{r['pnl']:+.2f}</td><td class='{gc}'>{r['expectancy']:+.2f}</td></tr>"
        h += "</tbody></table>"
        return h
    return _table(rows_strat, "Performance live par stratégie") + _table(rows_marche, "Performance live par marché")


def render_section_obs(trades=None, token=""):
    """Section complete a injecter dans /perf: equity + metriques + breakdown."""
    if trades is None:
        try:
            pt = json.load(open(PT_FILE, encoding="utf-8"))
            trades = pt.get("trades_fermes", [])
        except Exception:
            trades = []
    equity = charger_equity()
    out = "<h3>📈 Courbe d'equity (capital total)</h3>"
    out += render_equity_chart(equity)
    out += f"<div class='muted'>{len(equity)} points · pic capital mis à jour en continu</div>"
    out += "<h3>⚖️ Métriques de risque (live)</h3>"
    out += render_risk_metrics(trades, equity)
    out += render_breakdown(trades)
    return out


# ---------------------------------------------------------------- CLI
if __name__ == "__main__":
    import sys
    cmd = sys.argv[1] if len(sys.argv) > 1 else "stats"
    if cmd == "snapshot":
        snapshot_equity()
        print("snapshot OK")
    elif cmd == "stats":
        pt = json.load(open(PT_FILE, encoding="utf-8"))
        trades = pt.get("trades_fermes", [])
        eq = charger_equity()
        print(f"Equity points: {len(eq)}")
        if eq:
            print(f"  Dernier: {eq[-1].get('date')} capital={eq[-1].get('capital')}€")
        m = calculer_metriques(trades, eq)
        if m:
            print("\nMetriques live:")
            for k, v in m.items():
                print(f"  {k}: {v}")
        rs, rm = breakdown_strategies(trades)
        print("\nPar strategie:")
        for r in rs:
            print(f"  {r['cle']:<25} n={r['n']} wr={r['win_rate']:.0f}% pnl={r['pnl']:+.2f}€")
    elif cmd == "test":
        # genere un snapshot test pour verifier
        snapshot_equity()
        print(render_section_obs()[:500])
