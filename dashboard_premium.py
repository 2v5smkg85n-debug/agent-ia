#!/usr/bin/env python3
"""Dashboard PREMIUM pour l'agent IA - Design moderne avec graphiques temps reel."""
import json
import os
import html
import time
import requests
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import urlparse, parse_qs

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

# CoinGecko pour prix temps reel
COINGECKO_MAP = {
    "BTC": "bitcoin", "ETH": "ethereum", "SOL": "solana", "BNB": "binancecoin",
    "XRP": "ripple", "LDO": "lido-dao", "AAVE": "aave", "PENDLE": "pendle",
    "ARB": "arbitrum", "DOGE": "dogecoin", "AVAX": "avalanche-2",
    "LINK": "chainlink", "NEAR": "near", "FET": "fetch-ai", "RNDR": "render-token",
}

NOMS = {
    "BTCUSDT": "Bitcoin", "ETHUSDT": "Ethereum", "SOLUSDT": "Solana",
    "BNBUSDT": "BNB", "XRPUSDT": "XRP", "LDOUSDT": "Lido DAO",
    "AAVEUSDT": "Aave", "PENDLEUSDT": "Pendle", "ARBUSDT": "Arbitrum",
    "DOGEUSDT": "Dogecoin", "AVAXUSDT": "Avalanche", "LINKUSDT": "Chainlink",
    "NEARUSDT": "NEAR", "FETUSDT": "FET", "RNDRUSDT": "Render",
}

def esc(s):
    return html.escape(str(s))

def fmt(x):
    try:
        f = float(x)
        if abs(f) >= 1000:
            return f"{f:,.0f}".replace(",", " ")
        return f"{f:.2f}"
    except (ValueError, TypeError):
        return str(x)

def get_prix_batch(symboles):
    """Recupere les prix de plusieurs cryptos en une seule requete CoinGecko."""
    ids = []
    id_to_sym = {}
    for sym in symboles:
        base = sym.replace("USDT", "")
        cg_id = COINGECKO_MAP.get(base, base.lower())
        ids.append(cg_id)
        id_to_sym[cg_id] = sym
    try:
        url = f"https://api.coingecko.com/api/v3/simple/price?ids={','.join(ids)}&vs_currencies=eur&include_24hr_change=true"
        r = requests.get(url, timeout=10)
        if r.status_code == 200:
            result = {}
            for cg_id, data in r.json().items():
                sym = id_to_sym.get(cg_id, cg_id)
                result[sym] = {
                    "prix": data.get("eur", 0),
                    "var_24h": data.get("eur_24h_change", 0)
                }
            return result
    except:
        pass
    return {}

def read_system():
    import shutil
    m = {}
    try:
        la = open("/proc/loadavg").read().split()
        m["load"] = f"{la[0]} / {la[1]} / {la[2]}"
    except:
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
    except:
        m["ram_pct"] = 0
        m["ram"] = "?"
    try:
        du = shutil.disk_usage("/")
        m["disk_pct"] = du.used / du.total * 100
        m["disk"] = f"{du.used/1e9:.1f} / {du.total/1e9:.1f} GB"
    except:
        m["disk_pct"] = 0
        m["disk"] = "?"
    try:
        up = float(open("/proc/uptime").read().split()[0])
        d = int(up // 86400); h = int((up % 86400) // 3600); mn = int((up % 3600) // 60)
        m["uptime"] = f"{d}j {h}h {mn}m"
    except:
        m["uptime"] = "?"
    return m

def service_status(name):
    import subprocess
    try:
        r = subprocess.run(["systemctl", "is-active", name],
                           capture_output=True, text=True, timeout=2)
        return r.stdout.strip()
    except:
        return "unknown"

def build_premium_page(d):
    cap_init = float(d.get("capital_initial", 1000))
    liq = float(d.get("liquidites", 0))
    positions = d.get("positions", [])
    hist = d.get("historique", [])
    frais = float(d.get("total_frais", 0))
    pic = float(d.get("pic_capital", cap_init))
    fermes = d.get("trades_fermes", [])
    tick = d.get("dernier_tick", "?")
    
    # Prix temps reel
    symboles = [p.get("symbole", "") for p in positions if isinstance(p, dict)]
    prix_temps_reel = get_prix_batch(symboles)
    
    # Calcul PnL par position
    total_valeur = 0
    total_investi = 0
    total_pnl = 0
    positions_html = ""
    
    for p in positions:
        sym = p.get("symbole", "")
        nom = NOMS.get(sym, sym)
        prix_entree = float(p.get("prix_entree", 0))
        quantite = float(p.get("quantite", 0))
        montant = float(p.get("montant_eur", 0))
        strategie = p.get("strategie", "?")
        date_ouv = p.get("date_ouverture", "?")
        
        prix_actuel = prix_temps_reel.get(sym, {}).get("prix", prix_entree)
        var_24h = prix_temps_reel.get(sym, {}).get("var_24h", 0)
        
        valeur_actuelle = prix_actuel * quantite
        pnl_eur = valeur_actuelle - montant
        pnl_pct = (pnl_eur / montant * 100) if montant > 0 else 0
        
        total_valeur += valeur_actuelle
        total_investi += montant
        total_pnl += pnl_eur
        
        emoji = "🟢" if pnl_pct >= 0 else "🔴"
        pnl_color = "#4ade80" if pnl_pct >= 0 else "#f87171"
        bar_width = min(abs(pnl_pct) * 10, 100)
        
        positions_html += f"""
        <div class="pos-card" onclick="this.classList.toggle('expanded')">
          <div class="pos-header">
            <span class="pos-emoji">{emoji}</span>
            <span class="pos-name">{esc(nom)}</span>
            <span class="pos-pnl" style="color:{pnl_color}">{pnl_eur:+.2f}€ ({pnl_pct:+.1f}%)</span>
          </div>
          <div class="pos-details">
            <span>Entree: {prix_entree:.4f}€</span>
            <span>Actuel: {prix_actuel:.4f}€</span>
            <span>24h: {var_24h:+.1f}%</span>
            <span>Qty: {quantite:.6f}</span>
            <span>Montant: {montant:.2f}€</span>
            <span>Strat: {esc(strategie)}</span>
            <span>Depuis: {esc(date_ouv)}</span>
          </div>
          <div class="pnl-bar"><div class="pnl-fill" style="width:{bar_width}%;background:{pnl_color}"></div></div>
        </div>"""
    
    cap_actuel = liq + total_valeur
    perf = ((cap_actuel - cap_init) / cap_init * 100) if cap_init else 0
    dd = ((cap_actuel - pic) / pic * 100) if pic else 0
    nb_pos = len(positions)
    nb_gagnants = len([p for p in positions if isinstance(p, dict) and prix_temps_reel.get(p.get("symbole",""),{}).get("prix",0) * p.get("quantite",0) >= p.get("montant_eur",0)])
    nb_perdants = nb_pos - nb_gagnants
    
    # Historique pour graphique
    hist_vals = []
    hist_labels = []
    for i, h in enumerate(hist):
        v = None
        if isinstance(h, dict):
            for k in ("capital", "valeur", "solde", "total", "capital_total"):
                if k in h:
                    try: v = float(h[k])
                    except: pass
                    break
            t = h.get("date") or h.get("timestamp") or str(i)
            hist_labels.append(str(t))
        elif isinstance(h, (int, float)):
            v = float(h)
            hist_labels.append(str(i))
        if v is not None:
            hist_vals.append(v)
    
    # Graphique SVG evolution capital
    chart_svg = ""
    if len(hist_vals) >= 2:
        W, H, P = 700, 250, 50
        vmin, vmax = min(hist_vals), max(hist_vals)
        if vmax == vmin: vmax = vmin + 1
        n = len(hist_vals)
        pts = []
        for i, v in enumerate(hist_vals):
            x = P + (W - 2*P) * (i / (n-1))
            y = H - P - (H - 2*P) * ((v - vmin) / (vmax - vmin))
            pts.append(f"{x:.1f},{y:.1f}")
        poly = " ".join(pts)
        color = "#4ade80" if hist_vals[-1] >= hist_vals[0] else "#f87171"
        # Aire sous la courbe
        area_pts = f"{P},{H-P} " + poly + f" {W-P},{H-P}"
        chart_svg = f"""
        <svg viewBox="0 0 {W} {H}" class="chart-svg" preserveAspectRatio="xMidYMid meet">
          <defs><linearGradient id="grad" x1="0" y1="0" x2="0" y2="1">
            <stop offset="0%" stop-color="{color}" stop-opacity="0.3"/>
            <stop offset="100%" stop-color="{color}" stop-opacity="0"/>
          </linearGradient></defs>
          <polygon points="{area_pts}" fill="url(#grad)"/>
          <line x1="{P}" y1="{H-P}" x2="{W-P}" y2="{H-P}" stroke="#30363d"/>
          <line x1="{P}" y1="{P}" x2="{P}" y2="{H-P}" stroke="#30363d"/>
          <text x="{P-8}" y="{P+4}" text-anchor="end" fill="#8b949e" font-size="10">{fmt(vmax)}</text>
          <text x="{P-8}" y="{H-P}" text-anchor="end" fill="#8b949e" font-size="10">{fmt(vmin)}</text>
          <polyline points="{poly}" fill="none" stroke="{color}" stroke-width="2.5"/>
          <circle cx="{W-P}" cy="{H-P - (H-2*P)*((hist_vals[-1]-vmin)/(vmax-vmin))}" r="4" fill="{color}"/>
        </svg>"""
    else:
        chart_svg = "<p class='muted'>Pas assez d'historique</p>"
    
    # Systeme
    sys = read_system()
    svc_paper = service_status("paper_trading")
    svc_dash = service_status("dashboard")
    
    # Trades fermes
    trades_html = ""
    if fermes:
        for t in fermes[-10:]:
            sym = t.get("symbole", "?")
            pnl = t.get("pnl", 0)
            raison = t.get("raison_fermeture", "?")
            date_f = t.get("date_fermeture", "?")
            color = "#4ade80" if pnl >= 0 else "#f87171"
            trades_html += f"<tr><td>{esc(sym)}</td><td style='color:{color}'>{pnl:+.2f}€</td><td>{esc(raison)}</td><td>{esc(date_f)}</td></tr>"
    
    perf_color = "#4ade80" if perf >= 0 else "#f87171"
    pnl_color_total = "#4ade80" if total_pnl >= 0 else "#f87171"
    
    return f"""<!DOCTYPE html><html lang="fr"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Agent IA - Dashboard Premium</title>
<meta http-equiv="refresh" content="30">
<style>
:root{{--bg:#0d1117;--card:#161b22;--card2:#1c2331;--txt:#e6edf3;--muted:#8b949e;--pos:#4ade80;--neg:#f87171;--accent:#58a6ff;--border:#30363d;--gold:#fbbf24}}
*{{box-sizing:border-box;margin:0;padding:0}}
body{{background:var(--bg);color:var(--txt);font-family:-apple-system,BlinkMacSystemFont,"Segoe UI",Roboto,sans-serif;padding:12px;max-width:820px;margin:0 auto}}
.header{{display:flex;justify-content:space-between;align-items:center;margin-bottom:14px;padding-bottom:10px;border-bottom:2px solid var(--accent)}}
.header h1{{font-size:20px;background:linear-gradient(90deg,var(--accent),var(--gold));-webkit-background-clip:text;-webkit-text-fill-color:transparent}}
.header .live{{display:flex;align-items:center;gap:6px;font-size:12px;color:var(--muted)}}
.header .live::before{{content:"";width:8px;height:8px;border-radius:50%;background:var(--pos);animation:pulse 2s infinite}}
@keyframes pulse{{0%,100%{{opacity:1}}50%{{opacity:0.3}}}}
.cards{{display:grid;grid-template-columns:repeat(4,1fr);gap:8px;margin-bottom:16px}}
.card{{background:var(--card);border:1px solid var(--border);border-radius:10px;padding:12px;transition:transform 0.2s}}
.card:hover{{transform:translateY(-2px);border-color:var(--accent)}}
.card .lbl{{font-size:10px;color:var(--muted);text-transform:uppercase;letter-spacing:.5px;margin-bottom:4px}}
.card .val{{font-size:18px;font-weight:700}}
.card .sub{{font-size:10px;color:var(--muted);margin-top:2px}}
.card.pos .val{{color:var(--pos)}}
.card.neg .val{{color:var(--neg)}}
.card.gold .val{{color:var(--gold)}}
.section{{margin-bottom:18px}}
.section h2{{font-size:14px;margin-bottom:10px;color:var(--accent);display:flex;align-items:center;gap:6px}}
.section h2::before{{content:"";width:4px;height:16px;background:var(--accent);border-radius:2px}}
.chart-svg{{width:100%;height:auto;background:var(--card);border:1px solid var(--border);border-radius:10px}}
.pos-card{{background:var(--card);border:1px solid var(--border);border-radius:10px;padding:10px;margin-bottom:8px;cursor:pointer;transition:border-color 0.2s}}
.pos-card:hover{{border-color:var(--accent)}}
.pos-card.expanded .pos-details{{display:flex}}
.pos-header{{display:flex;justify-content:space-between;align-items:center}}
.pos-emoji{{font-size:16px}}
.pos-name{{font-weight:600;font-size:14px;flex:1;margin-left:6px}}
.pos-pnl{{font-weight:700;font-size:13px}}
.pos-details{{display:none;flex-wrap:wrap;gap:8px;margin-top:8px;padding-top:8px;border-top:1px solid var(--border);font-size:11px;color:var(--muted)}}
.pos-details span{{background:var(--card2);padding:3px 8px;border-radius:4px}}
.pnl-bar{{height:3px;background:var(--border);border-radius:2px;margin-top:6px;overflow:hidden}}
.pnl-fill{{height:100%;border-radius:2px;transition:width 0.5s}}
table{{width:100%;border-collapse:collapse;font-size:12px}}
th,td{{text-align:left;padding:6px 8px;border-bottom:1px solid var(--border)}}
th{{color:var(--muted);font-size:11px;text-transform:uppercase}}
.muted{{color:var(--muted);font-size:13px}}
.stats-row{{display:flex;gap:16px;margin-bottom:14px;font-size:12px;color:var(--muted)}}
.stats-row span{{display:flex;align-items:center;gap:4px}}
.dot{{width:8px;height:8px;border-radius:50%}}
.dot.g{{background:var(--pos)}}.dot.r{{background:var(--neg)}}
.sys-grid{{display:grid;grid-template-columns:repeat(4,1fr);gap:8px}}
.sys-card{{background:var(--card);border:1px solid var(--border);border-radius:8px;padding:8px;text-align:center}}
.sys-card .lbl{{font-size:9px;color:var(--muted);text-transform:uppercase}}
.sys-card .val{{font-size:13px;font-weight:600;margin-top:2px}}
.badge{{padding:2px 8px;border-radius:10px;font-size:10px;font-weight:600}}
.badge.ok{{background:rgba(74,222,128,0.15);color:var(--pos)}}
.badge.bad{{background:rgba(248,113,113,0.15);color:var(--neg)}}
.footer{{text-align:center;color:var(--muted);font-size:11px;margin-top:18px;padding-top:10px;border-top:1px solid var(--border)}}
</style></head><body>
<div class="header">
  <h1>🤖 Agent IA Trading</h1>
  <div class="live">LIVE · {esc(str(tick))}</div>
</div>

<div class="cards">
  <div class="card gold"><div class="lbl">Capital total</div><div class="val">{fmt(cap_actuel)}€</div><div class="sub">Initial: {fmt(cap_init)}€</div></div>
  <div class="card {'pos' if perf>=0 else 'neg'}"><div class="lbl">Performance</div><div class="val">{perf:+.2f}%</div><div class="sub">{('+' if perf>=0 else '')}{fmt(cap_actuel-cap_init)}€</div></div>
  <div class="card"><div class="lbl">Liquidites</div><div class="val">{fmt(liq)}€</div><div class="sub">{liq/cap_init*100:.0f}% du capital</div></div>
  <div class="card {'neg' if dd<0 else 'pos'}"><div class="lbl">Drawdown</div><div class="val">{dd:+.2f}%</div><div class="sub">Pic: {fmt(pic)}€</div></div>
</div>

<div class="stats-row">
  <span><div class="dot g"></div> {nb_gagnants} gagnants</span>
  <span><div class="dot r"></div> {nb_perdants} perdants</span>
  <span>📊 {nb_pos} positions</span>
  <span style="color:{pnl_color_total}">💰 PnL latent: {total_pnl:+.2f}€</span>
  <span>💸 Frais: {fmt(frais)}€</span>
</div>

<div class="section">
  <h2>📈 Evolution du capital</h2>
  {chart_svg}
</div>

<div class="section">
  <h2>💼 Positions ({nb_pos})</h2>
  {positions_html if positions_html else '<p class="muted">Aucune position ouverte</p>'}
</div>

<div class="section">
  <h2>📋 Trades fermes ({len(fermes)})</h2>
  {f'<table><thead><tr><th>Crypto</th><th>PnL</th><th>Raison</th><th>Date</th></tr></thead><tbody>{trades_html}</tbody></table>' if trades_html else '<p class="muted">Aucun trade ferme</p>'}
</div>

<div class="section">
  <h2>🖥️ Systeme VPS</h2>
  <div class="sys-grid">
    <div class="sys-card"><div class="lbl">RAM</div><div class="val" style="color:{'#f87171' if sys['ram_pct']>85 else '#4ade80'}">{sys['ram_pct']:.0f}%</div></div>
    <div class="sys-card"><div class="lbl">Disque</div><div class="val" style="color:{'#f87171' if sys['disk_pct']>85 else '#4ade80'}">{sys['disk_pct']:.0f}%</div></div>
    <div class="sys-card"><div class="lbl">Uptime</div><div class="val">{esc(sys['uptime'])}</div></div>
    <div class="sys-card"><div class="lbl">Load</div><div class="val" style="font-size:11px">{esc(sys['load'])}</div></div>
  </div>
  <div style="margin-top:8px;display:flex;gap:8px">
    <span class="badge {'ok' if svc_paper=='active' else 'bad'}">Paper Trading: {esc(svc_paper)}</span>
    <span class="badge {'ok' if svc_dash=='active' else 'bad'}">Dashboard: {esc(svc_dash)}</span>
  </div>
</div>

<div class="footer">
  Agent IA Trading v2 · 37+ commandes Telegram · Auto-refresh 30s · Donnees CoinGecko temps reel
</div>
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
        try:
            d = json.load(open(DATA_FILE))
        except Exception as e:
            self.send_response(500)
            self.send_header("Content-Type", "text/plain")
            self.end_headers()
            self.wfile.write(f"Erreur: {e}".encode())
            return
        out = build_premium_page(d)
        self.send_response(200)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.end_headers()
        self.wfile.write(out.encode())

    def log_message(self, *a):
        pass

if __name__ == "__main__":
    print(f"Dashboard PREMIUM sur http://0.0.0.0:{PORT}/?token=***")
    try:
        ThreadingHTTPServer(("0.0.0.0", PORT), Handler).serve_forever()
    except KeyboardInterrupt:
        pass
