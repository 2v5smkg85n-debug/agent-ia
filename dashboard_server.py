#!/usr/bin/env python3
"""Serveur dashboard LIVE pour l'agent IA. Lit paper_trading.json a chaque requete.
Accessible sur iPhone via http://IP:PORT/?token=XXX"""
import json
import os
import html
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import urlparse, parse_qs
import performance
import ia_render  # IA-ROUTE-INSTALLE
import revolut_live_render  # LIVE-ROUTE-INSTALLE


def load_env():
    env = {}
    try:
        for line in open(".env"):
            line = line.strip()
            if "=" in line and not line.startswith("#"):
                k, v = line.split("=", 1)
                env[k.strip()] = v.strip().strip('"').strip("'")
    except FileNotFoundError:
        pass
    return env


ENV = load_env()
TOKEN = ENV.get("DASHBOARD_TOKEN", "changeme")
PORT = int(ENV.get("DASHBOARD_PORT", "8765"))
DATA_FILE = "paper_trading.json"
SERVICES = ["paper_trading", "protection", "dashboard"]
LOG_FILES = {
    "paper_trading": "paper_trading.log",
    "protection": "protection.log",
    "dashboard": "dashboard.log",
}
ERROR_MARKERS = ("Traceback", "Error", "ERREUR", "ECHEC", "CRITICAL", "Exception")


import shutil
import subprocess


def read_system():
    m = {}
    try:
        la = open("/proc/loadavg").read().split()
        m["load"] = f"{la[0]} / {la[1]} / {la[2]}"
    except Exception:
        m["load"] = "?"
    try:
        mi = {}
        for line in open("/proc/meminfo"):
            k, _, v = line.partition(":")
            mi[k.strip()] = int(v.split()[0]) if v.strip() else 0
        total = mi.get("MemTotal", 1)
        avail = mi.get("MemAvailable", mi.get("MemFree", 0))
        used = total - avail
        m["ram_pct"] = used / total * 100
        m["ram"] = f"{used/1024/1024:.1f} / {total/1024/1024:.1f} GB"
    except Exception:
        m["ram_pct"] = 0
        m["ram"] = "?"
    try:
        du = shutil.disk_usage("/")
        m["disk_pct"] = du.used / du.total * 100
        m["disk"] = f"{du.used/1e9:.1f} / {du.total/1e9:.1f} GB"
    except Exception:
        m["disk_pct"] = 0
        m["disk"] = "?"
    try:
        up = float(open("/proc/uptime").read().split()[0])
        d = int(up // 86400); h = int((up % 86400) // 3600); mn = int((up % 3600) // 60)
        m["uptime"] = f"{d}j {h}h {mn}m"
    except Exception:
        m["uptime"] = "?"
    return m


def service_status(name):
    try:
        r = subprocess.run(["systemctl", "is-active", name],
                           capture_output=True, text=True, timeout=2)
        return r.stdout.strip()
    except Exception:
        return "unknown"


def count_errors(logfile, n=500):
    try:
        lines = open(logfile).read().splitlines()[-n:]
    except Exception:
        return 0
    benign = ("Connection reset by peer", "ConnectionResetError",
              "BrokenPipeError", "Broken pipe", "ConnectionAbortedError",
              "Exception occurred during processing of request")
    count = 0
    skip_block = False
    for line in lines:
        if "Exception occurred during processing of request" in line:
            skip_block = True
            continue
        if skip_block:
            if line.startswith("Traceback") or line.startswith(" ") or line.startswith("\t"):
                continue
            if any(b in line for b in benign):
                continue
            skip_block = False
        if any(e in line for e in ERROR_MARKERS):
            count += 1
    return count


def render_system():
    s = read_system()
    cards = f"""
    <div class="cards">
      <div class="card"><div class="lbl">Charge (1/5/15m)</div><div class="val small">{esc(s['load'])}</div></div>
      <div class="card {'neg' if s['ram_pct']>85 else ''}"><div class="lbl">RAM</div><div class="val small">{s['ram_pct']:.0f}%</div><div class="sub">{esc(s['ram'])}</div></div>
      <div class="card {'neg' if s['disk_pct']>85 else ''}"><div class="lbl">Disque</div><div class="val small">{s['disk_pct']:.0f}%</div><div class="sub">{esc(s['disk'])}</div></div>
      <div class="card"><div class="lbl">Uptime</div><div class="val small">{esc(s['uptime'])}</div></div>
    </div>"""
    rows = ""
    for svc in SERVICES:
        st = service_status(svc)
        badge = "<span class='ok'>actif</span>" if st == "active" else f"<span class='bad'>{esc(st)}</span>"
        err = count_errors(LOG_FILES.get(svc, ""))
        errbadge = f"<span class='bad'>{err} erreurs</span>" if err > 0 else "<span class='ok'>0</span>"
        rows += f"<tr><td>{esc(svc)}</td><td>{badge}</td><td>{errbadge}</td></tr>"
    table = f"""
    <h3>Services &amp; erreurs</h3>
    <table><thead><tr><th>Service</th><th>Statut</th><th>Erreurs (log recent)</th></tr></thead>
    <tbody>{rows}</tbody></table>"""
    return cards + table


def fmt(x):
    try:
        f = float(x)
        if abs(f) >= 1000:
            return f"{f:,.0f}".replace(",", " ")
        return f"{f:.2f}"
    except (ValueError, TypeError):
        return str(x)


def esc(s):
    return html.escape(str(s))


def render_chart(historique):
    if not historique:
        return "<p class='muted'>Pas d'historique</p>"
    vals, labels = [], []
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
                for k, val in h.items():
                    try:
                        v = float(val)
                        break
                    except (ValueError, TypeError):
                        pass
            t = h.get("date") or h.get("timestamp") or h.get("tick") or h.get("heure") or str(i)
            labels.append(str(t))
        elif isinstance(h, (int, float)):
            v = float(h)
            labels.append(str(i))
        else:
            try:
                v = float(h)
                labels.append(str(i))
            except (ValueError, TypeError):
                pass
        if v is not None:
            vals.append(v)
    if len(vals) < 2:
        return f"<p class='muted'>{len(vals)} point(s) — pas assez pour un graphique</p>"

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
    poly = " ".join(pts)
    first = vals[0]
    last = vals[-1]
    color = "#4ade80" if last >= first else "#f87171"
    return f'''
    <svg viewBox="0 0 {W} {H}" class="chart" preserveAspectRatio="xMidYMid meet">
      <line x1="{P}" y1="{H-P}" x2="{W-P}" y2="{H-P}" stroke="#30363d" />
      <line x1="{P}" y1="{P}" x2="{P}" y2="{H-P}" stroke="#30363d" />
      <text x="{P-8}" y="{P+4}" text-anchor="end" fill="#8b949e" font-size="10">{fmt(vmax)}</text>
      <text x="{P-8}" y="{H-P}" text-anchor="end" fill="#8b949e" font-size="10">{fmt(vmin)}</text>
      <polyline points="{poly}" fill="none" stroke="{color}" stroke-width="2.5" />
      <text x="{W-P}" y="{H-8}" text-anchor="end" fill="#8b949e" font-size="10">{labels[-1]}</text>
    </svg>'''


def render_table(rows, title):
    if not rows:
        return f"<h3>{title} <span class='count'>(0)</span></h3><p class='muted'>Aucun</p>"
    if not isinstance(rows[0], dict):
        return f"<h3>{title}</h3><pre class='muted'>{esc(json.dumps(rows, default=str, indent=2)[:800])}</pre>"
    keys = list(rows[0].keys())
    out = f"<h3>{title} <span class='count'>({len(rows)})</span></h3>"
    out += "<div class='tbl-wrap'><table><thead><tr>" + "".join(f"<th>{esc(k)}</th>" for k in keys) + "</tr></thead><tbody>"
    for r in reversed(rows[-25:]):
        out += "<tr>" + "".join(f"<td>{esc(fmt(r.get(k, '')))}</td>" for k in keys) + "</tr>"
    out += "</tbody></table></div>"
    return out


def build_page(d):
    cap_init = float(d.get("capital_initial", 1000))
    liq = float(d.get("liquidites", 0))
    positions = d.get("positions", [])
    hist = d.get("historique", [])
    frais = float(d.get("total_frais", 0))
    pic = float(d.get("pic_capital", cap_init))
    fermes = d.get("trades_fermes", [])
    tick = d.get("dernier_tick", "?")
    cap = d.get("capital_actuel")
    if cap is None:
        cap = liq + sum(float(p.get("valeur", p.get("valeur_actuelle", 0)) or 0) for p in positions if isinstance(p, dict))
    cap = float(cap)
    perf = ((cap - cap_init) / cap_init * 100) if cap_init else 0
    dd = ((cap - pic) / pic * 100) if pic else 0
    val_pos = cap - liq

    cards = f"""
    <div class="cards">
      <div class="card"><div class="lbl">Capital</div><div class="val">{fmt(cap)} €</div></div>
      <div class="card"><div class="lbl">Liquidités</div><div class="val">{fmt(liq)} €</div></div>
      <div class="card"><div class="lbl">Valeur positions</div><div class="val">{fmt(val_pos)} €</div></div>
      <div class="card {'pos' if perf>=0 else 'neg'}"><div class="lbl">Performance</div><div class="val">{perf:+.2f}%</div></div>
      <div class="card"><div class="lbl">Frais cumulés</div><div class="val">{fmt(frais)} €</div></div>
      <div class="card {'neg' if dd<0 else 'pos'}"><div class="lbl">Drawdown</div><div class="val">{dd:+.2f}%</div></div>
    </div>"""

    chart = f"<h3>Évolution du capital</h3>{render_chart(hist)}"
    open_t = render_table(positions, "Positions ouvertes")
    closed_t = render_table(fermes, "Trades fermés")
    system_t = render_system()

    return f"""<!DOCTYPE html><html lang="fr"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Agent IA — Paper Trading</title>
<meta http-equiv="refresh" content="60">
<style>
:root{{--bg:#0d1117;--card:#161b22;--txt:#e6edf3;--muted:#8b949e;--pos:#4ade80;--neg:#f87171;--border:#30363d}}
*{{box-sizing:border-box}}
body{{background:var(--bg);color:var(--txt);font-family:-apple-system,BlinkMacSystemFont,"Segoe UI",Roboto,sans-serif;margin:0 auto;padding:14px;max-width:760px}}
h1{{font-size:19px;margin:6px 0 2px}}
h3{{font-size:14px;margin:18px 0 8px;border-bottom:1px solid var(--border);padding-bottom:4px}}
.count{{color:var(--muted);font-size:12px}}
.muted{{color:var(--muted);font-size:13px}}
.meta{{color:var(--muted);font-size:12px;margin-bottom:4px}}
.cards{{display:grid;grid-template-columns:repeat(3,1fr);gap:8px;margin:12px 0}}
.card{{background:var(--card);border:1px solid var(--border);border-radius:8px;padding:9px}}
.card .lbl{{font-size:10px;color:var(--muted);text-transform:uppercase;letter-spacing:.5px}}
.card .val{{font-size:17px;font-weight:600;margin-top:2px}}
.card.pos .val{{color:var(--pos)}}
.card.neg .val{{color:var(--neg)}}
.card .val.small{{font-size:15px}}
.card .sub{{font-size:10px;color:var(--muted);margin-top:2px}}
.ok{{color:var(--pos);font-weight:600}}
.bad{{color:var(--neg);font-weight:600}}
.tbl-wrap{{overflow-x:auto}}
table{{width:100%;border-collapse:collapse;font-size:12px;margin-bottom:8px}}
th,td{{text-align:right;padding:6px 8px;border-bottom:1px solid var(--border);white-space:nowrap}}
th:first-child,td:first-child{{text-align:left}}
th{{color:var(--muted);font-weight:600;font-size:11px}}
.chart{{width:100%;height:auto;background:var(--card);border:1px solid var(--border);border-radius:8px}}
.lnk{{color:#58a6ff;text-decoration:none}}
</style></head><body>
<h1>Agent IA — Paper Trading</h1>
<div class="meta">Dernier tick : {esc(str(tick))} · actualisation auto 60s · <a class="lnk" href="/perf?token={TOKEN}">📈 Performance</a> · <a class="lnk" href="/ia?token={TOKEN}">🧠 IA</a> · <a class="lnk" href="/live?token={TOKEN}">💎 Live</a></div>
{cards}
{chart}
{open_t}
{closed_t}
{system_t}
<div class="meta" style="margin-top:16px">Données live depuis paper_trading.json</div>
</body></html>"""


class Handler(BaseHTTPRequestHandler):
    def do_GET(self):
        parsed = urlparse(self.path)
        qs = parse_qs(parsed.query)
        token = qs.get("token", [""])[0] or self.headers.get("X-Token", "")
        if token != TOKEN:
            self.send_response(403)
            self.send_header("Content-Type", "text/plain")
            self.end_headers()
            self.wfile.write(b"Forbidden")
            return
        # Route /perf : rapport de performance complet
        if parsed.path in ("/perf", "/performance"):
            try:
                out = performance.render_perf(token)
            except Exception as e:
                out = f"<html><body style='background:#0d1117;color:#e6edf3;font-family:sans-serif;padding:20px'><h2>Erreur rapport perf</h2><pre>{html.escape(str(e))}</pre></body></html>"
            self.send_response(200)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.end_headers()
            self.wfile.write(out.encode())
            return
        # Route /live : Revolut X live trading (bridge, staking, P&L reel)
        if parsed.path in ('/live', '/revolut'):
            try:
                out = revolut_live_render.render_live(token)
            except Exception as e:
                out = ("<html><body style='background:#0d1117;color:#e6edf3;"
                       "font-family:sans-serif;padding:20px'><h2>Erreur page Live</h2>"
                       "<pre>" + html.escape(str(e)) + "</pre></body></html>")
            self.send_response(200)
            self.send_header('Content-Type', 'text/html; charset=utf-8')
            self.end_headers()
            self.wfile.write(out.encode())
            return
        # Route /ia : IA avancee (strategies + reflexion)
        if parsed.path in ('/ia', '/ai'):
            try:
                out = ia_render.render_ia(token)
            except Exception as e:
                out = ("<html><body style='background:#0d1117;color:#e6edf3;            font-family:sans-serif;padding:20px'><h2>Erreur page IA</h2>            <pre>" + html.escape(str(e)) + "</pre></body></html>")
            self.send_response(200)
            self.send_header('Content-Type', 'text/html; charset=utf-8')
            self.end_headers()
            self.wfile.write(out.encode())
            return
        try:
            d = json.load(open(DATA_FILE))
        except Exception as e:
            self.send_response(500)
            self.send_header("Content-Type", "text/plain")
            self.end_headers()
            self.wfile.write(f"Erreur lecture {DATA_FILE}: {e}".encode())
            return
        out = build_page(d)
        self.send_response(200)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.end_headers()
        self.wfile.write(out.encode())

    def log_message(self, *a):
        pass


if __name__ == "__main__":
    print(f"Dashboard live sur http://0.0.0.0:{PORT}/?token=***")
    print(f"Token: {TOKEN[:6]}... (voir .env)")
    try:
        ThreadingHTTPServer(("0.0.0.0", PORT), Handler).serve_forever()
    except KeyboardInterrupt:
        pass
