#!/usr/bin/env python3
"""Dashboard PREMIUM pour l'agent IA - Design moderne avec graphiques temps reel."""
import json
import os
import html
import time
import urllib.request
import urllib.parse
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
CACHE_FILE = "prix_cache.json"

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
    """Recupere les prix depuis Revolut X (API publique, en EUR).
    Utilise un cache local de 90s pour eviter les faux PnL quand l'API ne repond pas."""
    try:
        import prix_revolut as pr
        resultats = pr.get_prix_batch(symboles)
        # Formater comme l'ancien format CoinGecko
        result = {}
        for sym, prix in resultats.items():
            result[sym] = {"prix": prix, "var_24h": 0}
        if result:
            return result
    except Exception as e:
        print("  [DASHBOARD] Prix Revolut X erreur: " + str(e))
    
    # Fallback: cache local
    cache = {}
    try:
        with open(CACHE_FILE) as f:
            cache = json.load(f)
    except:
        pass
    return cache.get("prix", {})

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

def get_ohlc_batch(symboles):
    """Récupère les bougies OHLC via Revolut X (avec cache 5min)."""
    result = {}
    # Cache local 5min
    cache = {}
    try:
        with open("/tmp/ohlc_cache.json") as f:
            cache = json.load(f)
    except:
        pass
    cache_age = time.time() - cache.get("timestamp", 0)
    if cache_age < 300 and cache.get("data", {}):
        cached = cache["data"]
        for sym in symboles:
            if sym in cached:
                result[sym] = cached[sym]
    # Fetch les manquants via Revolut X (max 6 par requete avec cache persistant)
    to_fetch = [s for s in symboles if s not in result][:6]
    for sym in to_fetch:
        base = sym.replace("USDT", "")
        try:
            import prix_revolut as pr
            candles = pr.get_candles_revolut(base, intervalle=15, nombre=20)
            if candles and len(candles) > 1:
                result[sym] = candles
            time.sleep(3.0)  # Rate-limit Revolut X
        except:
            pass
    # Sauver cache
    try:
        with open("/tmp/ohlc_cache.json", "w") as f:
            json.dump({"timestamp": time.time(), "data": result}, f)
    except:
        pass
    return result

def build_positions_chart(d):
    """Genere une page avec graphiques en chandeliers + TP/SL en temps reel."""
    positions = d.get("positions", [])
    liquidites = d.get("liquidites", 0)
    capital_initial = d.get("capital_initial", 1000)
    
    syms = [p.get("symbole", "") for p in positions]
    prix_tr = get_prix_batch(syms) if syms else {}
    ohlc_data = get_ohlc_batch(syms) if syms else {}
    
    TAKE_PROFIT_PCT = 3.0
    STOP_LOSS_PCT = 1.0
    EXTEND_TP_PCT = 4.0
    
    cards_html = ""
    charts_js = ""
    total_valeur = 0
    total_pnl = 0
    
    for idx, p in enumerate(positions):
        sym = p.get("symbole", "")
        nom = NOMS.get(sym, sym)
        prix_entree = p.get("prix_entree", 0)
        quantite = p.get("quantite", 0)
        montant = p.get("montant_eur", p.get("montant", 0))
        date_ouv = p.get("date_ouverture", "?")
        strategie = p.get("strategie", p.get("source", "?"))
        
        p_data = prix_tr.get(sym, {})
        prix_actuel = p_data.get("prix", 0)
        var_24h = p_data.get("var_24h", 0)
        prix_disponible = prix_actuel > 0
        if not prix_disponible:
            prix_actuel = prix_entree
        
        valeur_actuelle = prix_actuel * quantite if prix_disponible else montant
        pnl_eur = (valeur_actuelle - montant) if prix_disponible else 0
        pnl_pct = (pnl_eur / montant * 100) if montant > 0 and prix_disponible else 0
        
        total_valeur += valeur_actuelle
        total_pnl += pnl_eur
        
        tp_price = prix_entree * (1 + TAKE_PROFIT_PCT / 100)
        sl_price = prix_entree * (1 - STOP_LOSS_PCT / 100)
        tp_ext_price = prix_entree * (1 + EXTEND_TP_PCT / 100)
        dist_tp = ((tp_price - prix_actuel) / prix_actuel * 100) if prix_actuel > 0 else 0
        dist_sl = ((prix_actuel - sl_price) / prix_actuel * 100) if prix_actuel > 0 else 0
        
        pnl_color = "#4ade80" if pnl_pct >= 0 else "#f87171"
        emoji = "🟢" if pnl_pct >= 0 else "🔴"
        var_text = f"{var_24h:+.1f}%" if prix_disponible and var_24h is not None else "N/A"
        
        candles = ohlc_data.get(sym, [])
        candles_json = json.dumps(candles) if candles else "[]"
        
        if candles and len(candles) > 1:
            # SVG candlestick chart
            candle_count = len(candles)
            chart_w = 340
            chart_h = 160
            padding = 30
            all_prices = []
            for c in candles:
                all_prices.extend([c["high"], c["low"]])
            all_prices.extend([tp_price, sl_price, prix_entree, tp_ext_price])
            pmin = min(all_prices) * 0.995
            pmax = max(all_prices) * 1.005
            prange = pmax - pmin if pmax > pmin else 1
            tmin = candles[0]["time"]
            tmax = candles[-1]["time"]
            trange = tmax - tmin if tmax > tmin else 1
            def sx(t):
                return padding + (t - tmin) / trange * (chart_w - padding - 10)
            def sy(p):
                return chart_h - 10 - (p - pmin) / prange * (chart_h - 20)
            candle_w = max(3, (chart_w - padding - 10) / candle_count * 0.5)
            svg_parts = [f'<svg viewBox="0 0 {chart_w} {chart_h}" style="width:100%;max-width:400px;height:160px">']
            svg_parts.append(f'<rect width="{chart_w}" height="{chart_h}" fill="#161b22" rx="6"/>')
            for i in range(4):
                y = 10 + i * (chart_h - 20) / 3
                svg_parts.append(f'<line x1="{padding}" y1="{y:.0f}" x2="{chart_w-10}" y2="{y:.0f}" stroke="#21262d" stroke-width="0.5"/>')
            for pline, pcolor, plabel, pdash in [(tp_price, "#4ade80", "TP", "4"), (sl_price, "#f87171", "SL", "4"), (prix_entree, "#fbbf24", "E", "2"), (tp_ext_price, "#60a5fa", "TP+", "6")]:
                yy = sy(pline)
                if 5 < yy < chart_h - 5:
                    svg_parts.append(f'<line x1="{padding}" y1="{yy:.1f}" x2="{chart_w-10}" y2="{yy:.1f}" stroke="{pcolor}" stroke-width="1" stroke-dasharray="{pdash}"/>')
                    svg_parts.append(f'<text x="{chart_w-12}" y="{yy-3:.0f}" fill="{pcolor}" font-size="8" text-anchor="end">{plabel}</text>')
            for c in candles:
                x = sx(c["time"])
                is_up = c["close"] >= c["open"]
                cc = "#4ade80" if is_up else "#f87171"
                svg_parts.append(f'<line x1="{x:.1f}" y1="{sy(c["high"]):.1f}" x2="{x:.1f}" y2="{sy(c["low"]):.1f}" stroke="{cc}" stroke-width="1"/>')
                bt = min(sy(c["open"]), sy(c["close"]))
                bh = max(1, abs(sy(c["close"]) - sy(c["open"])))
                svg_parts.append(f'<rect x="{x-candle_w/2:.1f}" y="{bt:.1f}" width="{candle_w:.1f}" height="{bh:.1f}" fill="{cc}"/>')
            svg_parts.append(f'<circle cx="{sx(tmax):.1f}" cy="{sy(prix_actuel):.1f}" r="3" fill="#fff" stroke="#000" stroke-width="1"/>')
            svg_parts.append('</svg>')
            chart_html = ''.join(svg_parts)
        else:
            chart_html = '<div style="display:flex;align-items:center;justify-content:center;height:40px;color:#8b949e;font-size:12px">📊 Donnees indisponibles</div>'
        
        cards_html += f"""
        <div class="pos-card" data-sym="{sym}">
          <div class="pos-header">
            <span class="pos-emoji">{emoji}</span>
            <span class="pos-name">{esc(nom)}</span>
            <span class="pos-pnl" style="color:{pnl_color}">{pnl_eur:+.2f}€ ({pnl_pct:+.1f}%)</span>
          </div>
          <div class="pos-info">
            <span>Entree: {prix_entree:.4f}€</span>
            <span>Actuel: <span class="actuel-val">{prix_actuel:.4f}€</span></span>
            <span class="var-val">24h: {var_text}</span>
            <span>Qty: {quantite:.6f}</span>
          </div>
          <div class="chart-container">{chart_html}</div>
          <div class="pos-labels">
            <span class="sl-label">🟥 SL: {sl_price:.4f}€ (-{STOP_LOSS_PCT}%)</span>
            <span class="dist-label">TP: {dist_tp:+.1f}% | SL: {dist_sl:.1f}%</span>
            <span class="tp-label">🟩 TP: {tp_price:.4f}€ (+{TAKE_PROFIT_PCT}%)</span>
          </div>
          <div class="pos-footer">
            <span>📊 {esc(strategie)}</span>
            <span>📅 {esc(date_ouv)}</span>
          </div>
        </div>"""
    
    total_capital = liquidites + total_valeur
    perf_pct = ((total_capital - capital_initial) / capital_initial * 100) if capital_initial > 0 else 0
    perf_color = "#4ade80" if perf_pct >= 0 else "#f87171"
    
    return f"""<!DOCTYPE html>
<html lang="fr">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<meta http-equiv="refresh" content="30">
<title>Positions Live - Agent IA</title>
<style>
* {{ margin:0; padding:0; box-sizing:border-box; }}
body {{ background:#0d1117; color:#e6edf3; font-family:-apple-system,BlinkMacSystemFont,sans-serif; padding:12px; }}
.header {{ text-align:center; padding:12px 0; border-bottom:1px solid #30363d; margin-bottom:16px; }}
.header h1 {{ font-size:20px; color:#58a6ff; }}
.header .stats {{ display:flex; justify-content:center; gap:20px; margin-top:8px; flex-wrap:wrap; }}
.header .stat {{ font-size:14px; }}
.header .stat-value {{ font-weight:bold; }}
.pos-card {{ background:#161b22; border:1px solid #30363d; border-radius:12px; padding:12px; margin-bottom:12px; }}
.pos-header {{ display:flex; justify-content:space-between; align-items:center; margin-bottom:8px; }}
.pos-name {{ font-weight:bold; font-size:16px; }}
.pos-pnl {{ font-weight:bold; font-size:16px; }}
.pos-info {{ display:flex; gap:12px; font-size:12px; color:#8b949e; margin-bottom:8px; flex-wrap:wrap; }}
.chart-container {{ width:100%; height:200px; margin:8px 0; border-radius:8px; overflow:hidden; }}
.pos-labels {{ display:flex; justify-content:space-between; font-size:11px; margin-top:4px; }}
.sl-label {{ color:#f87171; }}
.dist-label {{ color:#8b949e; }}
.tp-label {{ color:#4ade80; }}
.pos-footer {{ display:flex; justify-content:space-between; font-size:11px; color:#8b949e; margin-top:8px; padding-top:8px; border-top:1px solid #30363d; }}
.legend {{ display:flex; gap:16px; justify-content:center; margin:16px 0; font-size:12px; flex-wrap:wrap; }}
.legend-item {{ display:flex; align-items:center; gap:4px; }}
.legend-dot {{ width:12px; height:12px; border-radius:3px; }}
.back-link {{ text-align:center; margin-top:16px; }}
.back-link a {{ color:#58a6ff; text-decoration:none; font-size:14px; }}
</style>
</head>
<body>
<div class="header">
  <h1>📊 Positions Live - TP/SL</h1>
  <div class="stats">
    <div class="stat">Capital: <span class="stat-value" id="capital-val" style="color:#58a6ff">{total_capital:.2f}€</span></div>
    <div class="stat">PnL: <span class="stat-value" id="pnl-total" style="color:{perf_color}">{total_pnl:+.2f}€ ({perf_pct:+.1f}%)</span></div>
    <div class="stat">Positions: <span class="stat-value">{len(positions)}</span></div>
    <div class="stat">Liquidites: <span class="stat-value">{liquidites:.2f}€</span></div>
  </div>
  <div style="text-align:center;font-size:10px;color:#8b949e;margin-top:4px"><span id="live-ts">MAJ: {time.strftime('%H:%M:%S')}</span> | 🔴 Live 30s</div>
</div>
<div class="legend">
  <div class="legend-item"><div class="legend-dot" style="background:#f87171"></div> Stop Loss</div>
  <div class="legend-item"><div class="legend-dot" style="background:#fbbf24"></div> Entree</div>
  <div class="legend-item"><div class="legend-dot" style="background:#4ade80"></div> Take Profit</div>
  <div class="legend-item"><div class="legend-dot" style="background:#60a5fa"></div> TP Extended</div>
</div>
{cards_html}
<div class="back-link"><a href="/?token={TOKEN}">← Retour Dashboard</a></div>
<script>
var TOKEN = '{TOKEN}';
var iframe = document.createElement('iframe');
iframe.style.display = 'none';
iframe.src = '/api/prices?token=' + TOKEN + '&t=' + Date.now();
document.body.appendChild(iframe);
function reloadIframe() {{
  iframe.src = '/api/prices?token=' + TOKEN + '&t=' + Date.now();
}}
function updateLive() {{
  try {{
    var url = '/api/prices?token=' + TOKEN + '&t=' + Date.now();
    var xhr = new XMLHttpRequest();
    xhr.open('GET', url, true);
    xhr.timeout = 8000;
    xhr.onreadystatechange = function() {{
      if (xhr.readyState != 4) return;
      if (xhr.status != 200) {{ document.getElementById('live-ts').textContent = 'MAJ: connexion...'; return; }}
      try {{
        var data = JSON.parse(xhr.responseText);
      }} catch(e) {{ document.getElementById('live-ts').textContent = 'MAJ: parse error'; return; }}
      if (!data.positions) return;
      var totalPnl = 0;
      var totalVal = 0;
      data.positions.forEach(function(p) {{
        var card = document.querySelector('[data-sym="' + p.sym + '"]');
        if (!card) return;
        var elPrix = card.querySelector('.actuel-val');
        var elPnl = card.querySelector('.pos-pnl');
        var elVar = card.querySelector('.var-val');
        if (elPrix) elPrix.textContent = p.prix.toFixed(4) + '€';
        if (elPnl) {{
          var sign = p.pnl >= 0 ? '+' : '';
          elPnl.textContent = sign + p.pnl.toFixed(2) + '€ (' + sign + p.pnl_pct.toFixed(1) + '%)';
          elPnl.style.color = p.pnl >= 0 ? '#4ade80' : '#f87171';
        }}
        if (elVar) elVar.textContent = '24h: ' + (p.var24h >= 0 ? '+' : '') + p.var24h.toFixed(1) + '%';
        totalPnl += p.pnl;
        totalVal += (p.montant_eur || p.montant || 0) + (p.pnl || 0);
      }});
      var liq = data.liquidites || 0;
      var elCap = document.getElementById('capital-val');
      var elPnlT = document.getElementById('pnl-total');
      if (elCap) elCap.textContent = (liq + totalVal).toFixed(2) + '€';
      if (elPnlT) {{
        var capTotal = liq + totalVal;
        var pct = ((capTotal - 1000) / 1000 * 100).toFixed(1);
        elPnlT.textContent = (totalPnl >= 0 ? '+' : '') + totalPnl.toFixed(2) + '€ (' + (parseFloat(pct) >= 0 ? '+' : '') + pct + '%)';
        elPnlT.style.color = parseFloat(pct) >= 0 ? '#4ade80' : '#f87171';
      }}
      document.getElementById('live-ts').textContent = 'MAJ: ' + new Date().toLocaleTimeString('fr-FR') + ' ✓';
    }};
    xhr.send();
  }} catch(e) {{
    document.getElementById('live-ts').textContent = 'MAJ: ' + new Date().toLocaleTimeString('fr-FR') + ' (refresh)';
  }}
}}
setInterval(updateLive, 30000);
setTimeout(updateLive, 1500);
</script>
</body>
</html>"""

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
        
        prix_actuel = prix_temps_reel.get(sym, {}).get("prix", 0)
        var_24h = prix_temps_reel.get(sym, {}).get("var_24h", 0)
        
        # Si pas de prix temps reel, on affiche N/A au lieu d'utiliser prix_entree
        prix_disponible = prix_actuel > 0
        if not prix_disponible:
            prix_actuel = prix_entree  # fallback pour calcul mais on l'indique
        
        valeur_actuelle = (prix_actuel * quantite) if prix_disponible else montant
        pnl_eur = (valeur_actuelle - montant) if prix_disponible else 0
        pnl_pct = (pnl_eur / montant * 100) if montant > 0 and prix_disponible else 0
        
        total_valeur += valeur_actuelle
        total_investi += montant
        total_pnl += pnl_eur
        
        emoji = "🟢" if pnl_pct >= 0 else "🔴"
        pnl_color = "#4ade80" if pnl_pct >= 0 else "#f87171"
        bar_width = min(abs(pnl_pct) * 10, 100)
        pnl_text = f"{pnl_eur:+.2f}€ ({pnl_pct:+.1f}%)" if prix_disponible else "N/A (prix indisponible)"
        prix_actuel_text = f"{prix_actuel:.4f}€" if prix_disponible else "N/A"
        var_text = f"{var_24h:+.1f}%" if prix_disponible and var_24h is not None else "N/A"
        
        positions_html += f"""
        <div class="pos-card" onclick="this.classList.toggle('expanded')">
          <div class="pos-header">
            <span class="pos-emoji">{emoji}</span>
            <span class="pos-name">{esc(nom)}</span>
            <span class="pos-pnl" style="color:{pnl_color}">{pnl_text}</span>
          </div>
          <div class="pos-details">
            <span>Entree: {prix_entree:.4f}€</span>
            <span>Actuel: {prix_actuel_text}</span>
            <span>24h: {var_text}</span>
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
    nb_gagnants = len([p for p in positions if isinstance(p, dict) and prix_temps_reel.get(p.get("symbole",""),{}).get("prix",0) > 0 and prix_temps_reel.get(p.get("symbole",""),{}).get("prix",0) * p.get("quantite",0) >= p.get("montant_eur",0)])
    nb_perdants = len([p for p in positions if isinstance(p, dict) and prix_temps_reel.get(p.get("symbole",""),{}).get("prix",0) > 0 and prix_temps_reel.get(p.get("symbole",""),{}).get("prix",0) * p.get("quantite",0) < p.get("montant_eur",0)])
    nb_indispo = nb_pos - nb_gagnants - nb_perdants
    
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
            pnl = t.get("gain_eur", t.get("pnl", 0))
            raison = t.get("raison", t.get("raison_fermeture", "?"))
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
.cards{{display:grid;grid-template-columns:repeat(2,1fr);gap:8px;margin-bottom:16px}}
.card{{background:var(--card);border:1px solid var(--border);border-radius:10px;padding:12px;transition:transform 0.2s}}
.card:hover{{transform:translateY(-2px);border-color:var(--accent)}}
.card .lbl{{font-size:10px;color:var(--muted);text-transform:uppercase;letter-spacing:.5px;margin-bottom:4px}}
.card .val{{font-size:16px;font-weight:700;white-space:nowrap;overflow:hidden;text-overflow:ellipsis}}
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
  <div class="live">LIVE · {esc(str(tick))} · <a class="lnk" href="/rapport?token={TOKEN}" style="font-size:11px">📄 Rapport</a></div>
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
  {f'<span style="color:#fbbf24">⚠️ {nb_indispo} prix indispo</span>' if nb_indispo > 0 else ''}
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
  <a href="/maitres?token={TOKEN}" style="color:#58a6ff;text-decoration:none">🏆 Maitres</a> · <a href="/learning?token={TOKEN}" style="color:#58a6ff;text-decoration:none">🧠 Apprentissage</a> · <a href="/positions?token={TOKEN}" style="color:#58a6ff;text-decoration:none">📊 Positions Live</a> · <a href="/rapport?token={TOKEN}" style="color:#58a6ff;text-decoration:none">📄 Rapport</a>
  <br>Agent IA Trading v2 · Auto-refresh 30s · Donnees Revolut X temps reel
</div>
</body></html>"""

def build_learning_page():
    """Genere la page d'apprentissage du trader avec stats et recommandations."""
    try:
        import apprentissage_trader as ap
        # Analyser les trades fermes en temps reel
        try:
            pf = json.load(open(DATA_FILE))
            trades = pf.get("trades_fermes", [])
            if trades:
                ap.analyser_trades(trades)
        except Exception:
            pass
        learning = ap.charger_learning()
        recs = ap.get_recommandations()
    except Exception as e:
        return f"<html><body style='background:#0d1117;color:#e6edf3;font-family:sans-serif;padding:20px'><h2>Erreur apprentissage</h2><pre>{html.escape(str(e))}</pre></body></html>"

    total_trades = learning.get("total_trades", 0)
    total_gagnants = learning.get("total_gagnants", 0)
    total_perdants = learning.get("total_perdants", 0)
    win_rate = learning.get("win_rate_global", 0)
    pnl_total = learning.get("pnl_total", 0)
    derniere_analyse = learning.get("derniere_analyse", "jamais")

    # Stats par strategie
    strats = sorted(learning.get("stats_strategies", {}).items(), key=lambda x: x[1].get("pnl_total", 0), reverse=True)
    strats_html = ""
    for strat, s in strats[:15]:
        n = s.get("n", 0)
        wr = s.get("win_rate", 0)
        pnl = s.get("pnl_total", 0)
        couleur = "#4ade80" if pnl > 0 else "#f87171"
        wr_color = "#4ade80" if wr >= 60 else ("#fbbf24" if wr >= 40 else "#f87171")
        strats_html += f"""
        <div class="lr-row">
          <span class="lr-name">{html.escape(strat)}</span>
          <span class="lr-n">{n} trades</span>
          <span class="lr-wr" style="color:{wr_color}">WR {wr:.0f}%</span>
          <span class="lr-pnl" style="color:{couleur}">{pnl:+.2f}€</span>
        </div>"""

    # Stats par crypto
    cryptos = sorted(learning.get("stats_par_crypto", {}).items(), key=lambda x: x[1].get("pnl_total", 0), reverse=True)
    cryptos_html = ""
    for sym, s in cryptos[:15]:
        n = s.get("n", 0)
        wr = s.get("win_rate", 0)
        pnl = s.get("pnl_total", 0)
        tp_opt = s.get("meilleur_tp", 2.0)
        sl_opt = s.get("meilleur_sl", 1.5)
        couleur = "#4ade80" if pnl > 0 else "#f87171"
        wr_color = "#4ade80" if wr >= 60 else ("#fbbf24" if wr >= 40 else "#f87171")
        cryptos_html += f"""
        <div class="lr-row">
          <span class="lr-name">{html.escape(sym)}</span>
          <span class="lr-n">{n} trades</span>
          <span class="lr-wr" style="color:{wr_color}">WR {wr:.0f}%</span>
          <span class="lr-pnl" style="color:{couleur}">{pnl:+.2f}€</span>
          <span class="lr-tpsl">TP {tp_opt:.1f}% / SL {sl_opt:.1f}%</span>
        </div>"""

    # Heures favorables
    heures = sorted(learning.get("stats_horaires", {}).items(), key=lambda x: x[1].get("pnl_total", 0), reverse=True)
    heures_html = ""
    for heure, s in heures[:10]:
        n = s.get("n", 0)
        wr = s.get("win_rate", 0)
        pnl = s.get("pnl_total", 0)
        couleur = "#4ade80" if pnl > 0 else "#f87171"
        wr_color = "#4ade80" if wr >= 60 else ("#fbbf24" if wr >= 40 else "#f87171")
        heures_html += f"""
        <div class="lr-row">
          <span class="lr-name">{heure}h</span>
          <span class="lr-n">{n} trades</span>
          <span class="lr-wr" style="color:{wr_color}">WR {wr:.0f}%</span>
          <span class="lr-pnl" style="color:{couleur}">{pnl:+.2f}€</span>
        </div>"""

    # Recommandations
    a_eviter = recs.get("strategies_a_eviter", []) + recs.get("cryptos_a_eviter", [])
    a_privilegier = recs.get("strategies_a_privilegier", []) + recs.get("cryptos_a_privilegier", [])
    eviter_html = "<div class='lr-muted'>Aucune exclusion pour le moment</div>" if not a_eviter else ""
    for item in a_eviter:
        eviter_html += f"<div class='lr-badge bad'>{html.escape(item)}</div>"
    priv_html = "<div class='lr-muted'>Aucun pattern gagnant identifie</div>" if not a_privilegier else ""
    for item in a_privilegier:
        priv_html += f"<div class='lr-badge ok'>{html.escape(item)}</div>"

    pnl_color = "#4ade80" if pnl_total >= 0 else "#f87171"
    wr_color = "#4ade80" if win_rate >= 50 else "#f87171"

    return f"""<!DOCTYPE html>
<html lang="fr">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<meta http-equiv="refresh" content="30">
<title>Apprentissage - Agent IA</title>
<style>
* {{ margin:0; padding:0; box-sizing:border-box; }}
body {{ background:#0d1117; color:#e6edf3; font-family:-apple-system,BlinkMacSystemFont,sans-serif; padding:12px; }}
.header {{ text-align:center; padding:12px 0; border-bottom:1px solid #30363d; margin-bottom:16px; }}
.header h1 {{ font-size:20px; color:#58a6ff; }}
.cards {{ display:grid; grid-template-columns:repeat(2,1fr); gap:8px; margin-bottom:16px; }}
.card {{ background:#161b22; border:1px solid #30363d; border-radius:10px; padding:12px; text-align:center; }}
.card .lbl {{ font-size:11px; color:#8b949e; }}
.card .val {{ font-size:22px; font-weight:bold; }}
.section {{ background:#161b22; border:1px solid #30363d; border-radius:10px; padding:12px; margin-bottom:12px; }}
.section h2 {{ font-size:14px; color:#58a6ff; margin-bottom:8px; }}
.lr-row {{ display:flex; justify-content:space-between; align-items:center; padding:6px 0; border-bottom:1px solid #21262d; font-size:13px; }}
.lr-row:last-child {{ border-bottom:none; }}
.lr-name {{ font-weight:bold; min-width:80px; }}
.lr-n {{ color:#8b949e; font-size:11px; min-width:60px; }}
.lr-wr {{ font-weight:bold; min-width:60px; }}
.lr-pnl {{ font-weight:bold; min-width:80px; text-align:right; }}
.lr-tpsl {{ color:#8b949e; font-size:10px; min-width:100px; text-align:right; }}
.lr-badge {{ display:inline-block; padding:4px 10px; border-radius:12px; font-size:12px; margin:2px; }}
.lr-badge.ok {{ background:rgba(74,222,128,0.15); color:#4ade80; }}
.lr-badge.bad {{ background:rgba(248,113,113,0.15); color:#f87171; }}
.lr-muted {{ color:#8b949e; font-size:12px; padding:8px 0; }}
.back-link {{ text-align:center; margin-top:16px; }}
.back-link a {{ color:#58a6ff; text-decoration:none; font-size:14px; }}
</style>
</head>
<body>
<div class="header">
  <h1>🧠 Apprentissage Trader</h1>
  <div style="font-size:10px;color:#8b949e;margin-top:4px">Derniere analyse: {html.escape(derniere_analyse)} · Auto-refresh 30s</div>
</div>

<div class="cards">
  <div class="card"><div class="lbl">Trades analyses</div><div class="val" style="color:#58a6ff">{total_trades}</div></div>
  <div class="card"><div class="lbl">Win Rate</div><div class="val" style="color:{wr_color}">{win_rate:.1f}%</div></div>
  <div class="card"><div class="lbl">Gagnants</div><div class="val" style="color:#4ade80">{total_gagnants}</div></div>
  <div class="card"><div class="lbl">Perdants</div><div class="val" style="color:#f87171">{total_perdants}</div></div>
</div>
<div class="card" style="margin-bottom:16px"><div class="lbl">PnL Total Appris</div><div class="val" style="color:{pnl_color}">{pnl_total:+.2f}€</div></div>

<div class="section">
  <h2>✅ A Privilegier</h2>
  {priv_html}
</div>

<div class="section">
  <h2>🚫 A Eviter</h2>
  {eviter_html}
</div>

<div class="section">
  <h2>📊 Strategies</h2>
  {strats_html if strats_html else '<div class="lr-muted">Aucune donnee</div>'}
</div>

<div class="section">
  <h2>💰 Cryptos</h2>
  {cryptos_html if cryptos_html else '<div class="lr-muted">Aucune donnee</div>'}
</div>

<div class="section">
  <h2>🕐 Heures Favorables</h2>
  {heures_html if heures_html else '<div class="lr-muted">Aucune donnee</div>'}
</div>

<div class="back-link"><a href="/?token={TOKEN}">← Dashboard</a> · <a href="/positions?token={TOKEN}">Positions Live →</a></div>
</body>
</html>"""

def build_maitres_page():
    """Genere la page du consensus des 10 maitres traders."""
    try:
        import master_traders as mt
        master = mt.charger_master()
    except Exception as e:
        return f"<html><body style='background:#0d1117;color:#e6edf3;font-family:sans-serif;padding:20px'><h2>Erreur</h2><pre>{html.escape(str(e))}</pre></body></html>"

    # Poids des maitres
    poids_html = ""
    for key, (nom, _) in mt.MAITRES.items():
        poids = master.get("poids_traders", {}).get(key, 1.0)
        barre_w = int(poids * 100)
        couleur = "#4ade80" if poids > 1.0 else ("#f87171" if poids < 0.8 else "#8b949e")
        poids_html += f"""
        <div class="mt-row">
          <span class="mt-name">{html.escape(nom)}</span>
          <div class="mt-bar-bg"><div class="mt-bar-fill" style="width:{barre_w}%;background:{couleur}"></div></div>
          <span class="mt-poids" style="color:{couleur}">{poids:.2f}</span>
        </div>"""

    # Historique
    hist = master.get("trades_par_trader", {}).get("historique", [])
    gagnants = [h for h in hist if h.get("gagnant")]
    perdants = [h for h in hist if not h.get("gagnant")]
    pnl_total = sum(h.get("gain", 0) for h in hist)
    pnl_color = "#4ade80" if pnl_total >= 0 else "#f87171"

    # Performance et parametres par maitre
    perf_html = ""
    stats = master.get("stats_par_maitre", {})
    params = master.get("params_maitres", {})
    for key, (nom, _) in mt.MAITRES.items():
        s = stats.get(key, {})
        p = params.get(key, {})
        n = s.get("n", 0)
        wr = s.get("win_rate", 0)
        pnl = s.get("pnl", 0)
        wr_color = "#4ade80" if wr >= 60 else ("#fbbf24" if wr >= 40 else "#f87171") if n > 0 else "#8b949e"
        pnl_color = "#4ade80" if pnl >= 0 else "#f87171"
        p_str = ", ".join(f"{k}={v}" for k, v in p.items()) if p else "defaut"
        perf_html += f"""
        <div class="mt-row">
          <span class="mt-name">{html.escape(nom)}</span>
          <span style='font-size:11px;color:#8b949e;min-width:60px'>{n} trades</span>
          <span class="mt-poids" style="color:{wr_color}">WR {wr:.0f}%</span>
          <span class="mt-poids" style="color:{pnl_color}">{pnl:+.2f}€</span>
        </div>
        <div style='font-size:10px;color:#6e7681;padding:2px 0 6px 122px'>{html.escape(p_str)}</div>"""

    derniere_amel = master.get("derniere_amelioration", "jamais")
    if derniere_amel != "jamais":
        perf_html += f"<div style='text-align:center;font-size:11px;color:#8b949e;margin-top:8px'>Derniere amelioration: {html.escape(derniere_amel)}</div>"

    # Scores live sur top cryptos
    cryptos = ["BTCUSDT", "ETHUSDT", "SOLUSDT", "BNBUSDT", "XRPUSDT", "LINKUSDT", "DOGEUSDT", "AVAXUSDT"]
    cryptos_html = ""
    for sym in cryptos:
        try:
            score, details, reco, extra = mt.consensus_maitres(sym)
            emoji = "🟢" if reco in ["ACHAT", "ACHAT_FORT"] else ("🔴" if "VENTE" in reco else "🟡")
            reco_color = "#4ade80" if "ACHAT" in reco else ("#f87171" if "VENTE" in reco else "#fbbf24")
            patterns = extra.get("patterns", "aucun")
            # Top 3 votes
            top3 = sorted(details.items(), key=lambda x: x[1]["score"], reverse=True)[:3]
            votes_html = ""
            for nom, d in top3:
                v_color = "#4ade80" if d["score"] > 0 else ("#f87171" if d["score"] < 0 else "#8b949e")
                votes_html += f"<span class='mt-vote' style='color:{v_color}'>{html.escape(nom.split()[0])} {d['score']:+d}</span>"
            cryptos_html += f"""
            <div class="mt-crypto-card">
              <div class="mt-crypto-header">
                <span class="mt-crypto-sym">{emoji} {sym}</span>
                <span class="mt-crypto-reco" style="color:{reco_color}">{reco}</span>
                <span class="mt-crypto-score">{score:+.2f}</span>
              </div>
              <div class="mt-patterns">Bougies: {html.escape(patterns[:100])}</div>
              <div class="mt-votes">{votes_html}</div>
            </div>"""
        except Exception as e:
            cryptos_html += f"<div class='mt-crypto-card'><span>{sym}: erreur {html.escape(str(e))}</span></div>"

    # Intelligence globale
    intel_html = ""
    try:
        import intelligence_pro as ip
        fg = ip.get_fear_greed()
        fg_val = fg.get("value", 50)
        fg_class = fg.get("classification", "Neutral")
        fg_color = "#f87171" if fg_val < 25 else ("#fbbf24" if fg_val < 45 else ("#4ade80" if fg_val > 55 else "#8b949e"))
        regime, regime_detail, regime_score = ip.regime_global()
        regime_color = "#4ade80" if "BULL" in regime else ("#f87171" if "BEAR" in regime else "#fbbf24")

        # Macro + funding
        macro_html = ""
        funding_html = ""
        try:
            import super_intelligence as si
            macro = si.get_macro_indicators()
            btc_dom = macro.get("btc_dominance", 0)
            mc_change = macro.get("change_24h", 0)
            mc_color = "#4ade80" if mc_change > 0 else "#f87171"
            macro_html = f"""
        <div class="mt-crypto-card">
          <div class="mt-crypto-header">
            <span class="mt-crypto-sym">BTC Dominance</span>
            <span class="mt-crypto-reco" style="color:#58a6ff">{btc_dom:.1f}%</span>
            <span class="mt-crypto-score" style="color:{mc_color}">{mc_change:+.1f}%</span>
          </div>
        </div>"""
            funding = si.get_funding_rates("BTCUSDT")
            f_rate = funding.get("rate_pct", 0)
            f_color = "#4ade80" if f_rate < 0 else ("#f87171" if f_rate > 0.05 else "#8b949e")
            funding_html = f"""
        <div class="mt-crypto-card">
          <div class="mt-crypto-header">
            <span class="mt-crypto-sym">Funding Rate BTC</span>
            <span class="mt-crypto-reco" style="color:{f_color}">{f_rate:+.4f}%</span>
          </div>
          <div class="mt-patterns">{html.escape(funding.get('detail', ''))}</div>
        </div>"""
        except Exception:
            pass

        intel_html = f"""
        <div class="mt-crypto-card">
          <div class="mt-crypto-header">
            <span class="mt-crypto-sym">Fear & Greed</span>
            <span class="mt-crypto-reco" style="color:{fg_color}">{fg_val} - {fg_class}</span>
          </div>
        </div>
        <div class="mt-crypto-card">
          <div class="mt-crypto-header">
            <span class="mt-crypto-sym">Regime marche</span>
            <span class="mt-crypto-reco" style="color:{regime_color}">{regime}</span>
          </div>
          <div class="mt-patterns">{html.escape(regime_detail)}</div>
        </div>
        {macro_html}
        {funding_html}"""
    except Exception as e:
        intel_html = f"<div class='mt-crypto-card'>Erreur: {html.escape(str(e))}</div>"

    return f"""<!DOCTYPE html>
<html lang="fr">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<meta http-equiv="refresh" content="60">
<title>Maitres Traders - Agent IA</title>
<style>
* {{ margin:0; padding:0; box-sizing:border-box; }}
body {{ background:#0d1117; color:#e6edf3; font-family:-apple-system,BlinkMacSystemFont,sans-serif; padding:12px; }}
.header {{ text-align:center; padding:12px 0; border-bottom:1px solid #30363d; margin-bottom:16px; }}
.header h1 {{ font-size:20px; color:#58a6ff; }}
.header .sub {{ font-size:10px; color:#8b949e; margin-top:4px; }}
.cards {{ display:grid; grid-template-columns:repeat(3,1fr); gap:8px; margin-bottom:16px; }}
.card {{ background:#161b22; border:1px solid #30363d; border-radius:10px; padding:12px; text-align:center; }}
.card .lbl {{ font-size:11px; color:#8b949e; }}
.card .val {{ font-size:20px; font-weight:bold; }}
.section {{ background:#161b22; border:1px solid #30363d; border-radius:10px; padding:12px; margin-bottom:12px; }}
.section h2 {{ font-size:14px; color:#58a6ff; margin-bottom:8px; }}
.mt-row {{ display:flex; align-items:center; gap:8px; padding:6px 0; border-bottom:1px solid #21262d; }}
.mt-row:last-child {{ border-bottom:none; }}
.mt-name {{ font-size:13px; font-weight:bold; min-width:120px; }}
.mt-bar-bg {{ flex:1; height:8px; background:#21262d; border-radius:4px; overflow:hidden; }}
.mt-bar-fill {{ height:100%; border-radius:4px; }}
.mt-poids {{ font-size:13px; font-weight:bold; min-width:40px; text-align:right; }}
.mt-crypto-card {{ background:#0d1117; border:1px solid #30363d; border-radius:8px; padding:10px; margin-bottom:8px; }}
.mt-crypto-header {{ display:flex; justify-content:space-between; align-items:center; }}
.mt-crypto-sym {{ font-weight:bold; font-size:14px; }}
.mt-crypto-reco {{ font-size:12px; font-weight:bold; }}
.mt-crypto-score {{ font-size:14px; font-weight:bold; color:#58a6ff; }}
.mt-patterns {{ font-size:11px; color:#8b949e; margin-top:4px; }}
.mt-votes {{ margin-top:4px; }}
.mt-vote {{ display:inline-block; padding:2px 6px; border-radius:8px; font-size:11px; margin:1px; background:#161b22; }}
.back-link {{ text-align:center; margin-top:16px; }}
.back-link a {{ color:#58a6ff; text-decoration:none; font-size:14px; }}
</style>
</head>
<body>
<div class="header">
  <h1>🏆 Master Traders</h1>
  <div class="sub">Consensus des 10 plus grands traders · Auto-refresh 60s</div>
</div>

<div class="cards">
  <div class="card"><div class="lbl">Trades analyses</div><div class="val" style="color:#58a6ff">{len(hist)}</div></div>
  <div class="card"><div class="lbl">Gagnants</div><div class="val" style="color:#4ade80">{len(gagnants)}</div></div>
  <div class="card"><div class="lbl">Perdants</div><div class="val" style="color:#f87171">{len(perdants)}</div></div>
</div>
<div class="card" style="margin-bottom:16px"><div class="lbl">PnL Total Maitres</div><div class="val" style="color:{pnl_color}">{pnl_total:+.2f}€</div></div>

<div class="section">
  <h2>📊 Poids des Maitres (apprentissage)</h2>
  {poids_html}
</div>

<div class="section">
  <h2>📈 Performance & Parametres</h2>
  {perf_html}
</div>

<div class="section">
  <h2>🎯 Consensus Live</h2>
  {cryptos_html}
</div>

<div class="section">
  <h2>🧠 Intelligence Globale</h2>
  {intel_html}
</div>

<div class="back-link"><a href="/?token={TOKEN}">← Dashboard</a> · <a href="/learning?token={TOKEN}">🧠 Apprentissage</a> · <a href="/positions?token={TOKEN}">📊 Positions</a></div>
</body>
</html>"""

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
        # Route /rapport : rapport HTML complet
        if parsed.path in ('/rapport', '/report'):
            try:
                import glob
                rapports = sorted(glob.glob(os.path.join(os.path.dirname(DATA_FILE) or '.', 'rapport_*.html')), reverse=True)
                if rapports:
                    with open(rapports[0]) as f:
                        out = f.read()
                else:
                    out = '<html><body style="background:#0d1117;color:#e6edf3;font-family:sans-serif;padding:20px"><h2>Aucun rapport genere</h2><p>Envoie "rapport pdf" sur Telegram pour generer un rapport.</p></body></html>'
            except Exception as e:
                out = f"<html><body style='background:#0d1117;color:#e6edf3;font-family:sans-serif;padding:20px'><h2>Erreur</h2><pre>{html.escape(str(e))}</pre></body></html>"
            self.send_response(200)
            self.send_header('Content-Type', 'text/html; charset=utf-8')
            self.end_headers()
            self.wfile.write(out.encode())
            return
        # Route /api/prices : JSON prix temps reel pour update live
        if parsed.path == '/api/prices':
            try:
                d = json.load(open(DATA_FILE))
                positions = d.get("positions", [])
                syms = [p.get("symbole", "") for p in positions]
                prix_tr = get_prix_batch(syms) if syms else {}
                result = {"positions": [], "liquidites": d.get("liquidites", 0), "ts": int(time.time())}
                for p in positions:
                    sym = p.get("symbole", "")
                    prix_entree = p.get("prix_entree", 0)
                    quantite = p.get("quantite", 0)
                    montant = p.get("montant_eur", 0)
                    p_data = prix_tr.get(sym, {})
                    prix_actuel = p_data.get("prix", 0)
                    var_24h = p_data.get("var_24h", 0)
                    prix_disponible = prix_actuel > 0
                    if not prix_disponible:
                        prix_actuel = prix_entree
                    valeur = prix_actuel * quantite if prix_disponible else montant
                    pnl_eur = (valeur - montant) if prix_disponible else 0
                    pnl_pct = (pnl_eur / montant * 100) if montant > 0 and prix_disponible else 0
                    tp = prix_entree * 1.03
                    sl = prix_entree * 0.99
                    result["positions"].append({
                        "sym": sym, "prix": prix_actuel, "pnl": round(pnl_eur, 2),
                        "pnl_pct": round(pnl_pct, 1), "var24h": var_24h,
                        "tp": tp, "sl": sl, "entry": prix_entree,
                        "tp_pct": 3.0, "sl_pct": 1.0,
                        "montant_eur": round(montant, 2),
                    })
                self.send_response(200)
                self.send_header('Content-Type', 'application/json')
                self.end_headers()
                self.wfile.write(json.dumps(result).encode())
            except Exception as e:
                self.send_response(500)
                self.end_headers()
                self.wfile.write(json.dumps({"error": str(e)}).encode())
            return
        # Route /maitres : consensus des 10 maitres traders
        if parsed.path == '/maitres':
            try:
                out = build_maitres_page()
            except Exception as e:
                out = f"<html><body style='background:#0d1117;color:#e6edf3;font-family:sans-serif;padding:20px'><h2>Erreur</h2><pre>{html.escape(str(e))}</pre></body></html>"
            self.send_response(200)
            self.send_header('Content-Type', 'text/html; charset=utf-8')
            self.end_headers()
            self.wfile.write(out.encode())
            return
        # Route /learning : page d'apprentissage du trader
        if parsed.path == '/learning':
            try:
                out = build_learning_page()
            except Exception as e:
                out = f"<html><body style='background:#0d1117;color:#e6edf3;font-family:sans-serif;padding:20px'><h2>Erreur</h2><pre>{html.escape(str(e))}</pre></body></html>"
            self.send_response(200)
            self.send_header('Content-Type', 'text/html; charset=utf-8')
            self.end_headers()
            self.wfile.write(out.encode())
            return
        # Route /positions : graphique visuel des positions avec TP/SL
        if parsed.path == '/positions':
            try:
                d = json.load(open(DATA_FILE))
                out = build_positions_chart(d)
            except Exception as e:
                out = f"<html><body style='background:#0d1117;color:#e6edf3;font-family:sans-serif;padding:20px'><h2>Erreur</h2><pre>{html.escape(str(e))}</pre></body></html>"
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
