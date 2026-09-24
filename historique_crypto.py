"""
Historique crypto long-terme — mémoire du marché pour le bot et le chat.

Fetch les bougies journalières depuis KuCoin pour les 37 cryptos Revolut X.
Calcule: regime de marché, distance ATH, RSI hebdomadaire, volatilite, cycle.
Stockage: historique_crypto.json (compact, mis a jour 1x/jour).

Usage:
  python3 historique_crypto.py          # Met a jour les donnees
  from historique_crypto import contexte_pour_bot, contexte_pour_chat, charger
"""

import json, os, time, requests
from datetime import datetime

DOSSIER = os.path.dirname(os.path.abspath(__file__))
FICHIER_HIST = os.path.join(DOSSIER, "historique_crypto.json")

# 37 cryptos Revolut X
CRYPTOS = [
    "BTCUSDT", "ETHUSDT", "SOLUSDT", "BNBUSDT", "XRPUSDT", "ADAUSDT", "DOGEUSDT",
    "AVAXUSDT", "DOTUSDT", "LTCUSDT", "TRXUSDT", "ARBUSDT", "NEARUSDT", "AAVEUSDT",
    "PENDLEUSDT", "SHIBUSDT", "ALGOUSDT", "ICPUSDT", "XLMUSDT", "INJUSDT", "SEIUSDT",
    "TIAUSDT", "CRVUSDT", "WIFUSDT", "FETUSDT", "LDOUSDT", "FILUSDT", "ETCUSDT",
    "OPUSDT", "SUIUSDT", "APTUSDT", "PEPEUSDT", "LINKUSDT", "UNIUSDT", "ATOMUSDT",
    "FLOKIUSDT", "RNDRUSDT",
]


# ============================================
# FETCH KUCOIN
# ============================================

def _fetch_daily_kucoin(symbole, start_ts, end_ts):
    """Fetch daily candles from KuCoin for a date range."""
    _sym = symbole.replace("USDT", "-USDT")
    url = "https://api.kucoin.com/api/v1/market/candles"
    params = {"type": "1day", "symbol": _sym, "startAt": int(start_ts), "endAt": int(end_ts)}
    try:
        r = requests.get(url, params=params, timeout=15)
        if r.status_code != 200:
            return []
        data = r.json()
        if not data or data.get("code") != "200":
            return []
        items = data.get("data", [])
        bougies = []
        for b in items:
            try:
                bougies.append({
                    "t": int(b[0]) // 1000,
                    "o": float(b[1]), "h": float(b[2]), "l": float(b[3]),
                    "c": float(b[4]), "v": float(b[5]),
                })
            except:
                continue
        bougies.sort(key=lambda x: x["t"])
        return bougies
    except:
        return []


def _fetch_all_history(symbole):
    """Fetch all available daily history for one crypto (chunked)."""
    now = int(time.time())
    # Start from 2017-01-01 — covers BTC since early days
    start = int(datetime(2017, 1, 1).timestamp())
    all_bougies = []
    chunk_start = start
    while chunk_start < now:
        chunk_end = min(chunk_start + 1500 * 86400, now)
        chunk = _fetch_daily_kucoin(symbole, chunk_start, chunk_end)
        if not chunk:
            break
        all_bougies.extend(chunk)
        if len(chunk) < 1500:
            break
        chunk_start = chunk[-1]["t"] + 86400
        time.sleep(0.3)
    # Deduplicate
    seen = set()
    unique = []
    for b in all_bougies:
        if b["t"] not in seen:
            seen.add(b["t"])
            unique.append(b)
    return unique


# ============================================
# INDICATEURS LONG-TERME
# ============================================

def _rsi(closes, period=14):
    if len(closes) < period + 1:
        return None
    gains, losses = [], []
    for i in range(1, len(closes)):
        d = closes[i] - closes[i-1]
        gains.append(d if d > 0 else 0)
        losses.append(abs(d) if d < 0 else 0)
    ag = sum(gains[:period]) / period
    al = sum(losses[:period]) / period
    for i in range(period, len(gains)):
        ag = (ag * (period - 1) + gains[i]) / period
        al = (al * (period - 1) + losses[i]) / period
    if al == 0:
        return 100.0
    return round(100 - 100 / (1 + ag / al), 1)


def _compute_metrics(bougies):
    """Compute long-term metrics from daily candles."""
    if len(bougies) < 30:
        return None
    closes = [b["c"] for b in bougies]
    prix = closes[-1]

    # ATH
    ath = max(b["h"] for b in bougies)
    ath_date = next((datetime.fromtimestamp(b["t"]).strftime("%Y-%m-%d")
                     for b in bougies if b["h"] == ath), "?")
    dd_ath = round((prix - ath) / ath * 100, 1)

    # Moving averages
    ma200 = round(sum(closes[-200:]) / 200, 4) if len(closes) >= 200 else None
    ma50 = round(sum(closes[-50:]) / 50, 4) if len(closes) >= 50 else None
    ma20 = round(sum(closes[-20:]) / 20, 4) if len(closes) >= 20 else None

    # Regime: bull si prix > MA200, bear sinon
    regime = "bull" if ma200 and prix > ma200 else ("bear" if ma200 else "jeune")

    # RSI
    rsi_d = _rsi(closes, 14)
    # RSI hebdo (closes tous les 7 jours)
    weekly = [closes[min(i + 6, len(closes) - 1)] for i in range(0, len(closes), 7)]
    rsi_w = _rsi(weekly, 14) if len(weekly) >= 15 else None

    # Volatilite 30j
    vol = None
    if len(closes) >= 31:
        rets = [(closes[i] - closes[i-1]) / closes[i-1] for i in range(-30, 0)]
        vol = round((sum(r**2 for r in rets) / len(rets)) ** 0.5 * 100, 1)

    # Rendements
    ret_1a = round((prix - closes[-365]) / closes[-365] * 100, 1) if len(closes) >= 365 else None
    ret_6m = round((prix - closes[-180]) / closes[-180] * 100, 1) if len(closes) >= 180 else None
    ret_3m = round((prix - closes[-90]) / closes[-90] * 100, 1) if len(closes) >= 90 else None
    ret_1m = round((prix - closes[-30]) / closes[-30] * 100, 1) if len(closes) >= 30 else None

    # Phase de cycle (Wyckoff simplifie)
    if dd_ath > -20 and regime == "bull":
        phase = "markup"  # Hausse
    elif dd_ath > -20 and regime == "bear":
        phase = "distribution"  # Sommet
    elif dd_ath < -50 and regime == "bear":
        phase = "decline"  # Baisse
    elif dd_ath < -50 and regime == "bull":
        phase = "accumulation"  # Bottom
    else:
        phase = "transition"

    # Support/resistance historiques (min/max 90 derniers jours)
    recent = bougies[-90:] if len(bougies) >= 90 else bougies
    support_90 = round(min(b["l"] for b in recent), 4)
    resistance_90 = round(max(b["h"] for b in recent), 4)

    return {
        "prix": round(prix, 4),
        "ath": round(ath, 4),
        "ath_date": ath_date,
        "drawdown_ath": dd_ath,
        "ma20": ma20, "ma50": ma50, "ma200": ma200,
        "regime": regime,
        "phase_cycle": phase,
        "rsi_j": rsi_d,
        "rsi_sem": rsi_w,
        "vol_30j": vol,
        "ret_1m": ret_1m, "ret_3m": ret_3m, "ret_6m": ret_6m, "ret_1a": ret_1a,
        "support_90j": support_90,
        "resistance_90j": resistance_90,
        "jours": len(bougies),
        "depuis": datetime.fromtimestamp(bougies[0]["t"]).strftime("%Y-%m-%d"),
    }


# ============================================
# MISE A JOUR
# ============================================

def mettre_a_jour():
    """Fetch all history, compute metrics, save to JSON."""
    print("=== Mise a jour historique crypto ===")
    t0 = time.time()

    metrics = {}
    for i, sym in enumerate(CRYPTOS):
        print(f"  [{i+1}/37] {sym}...", end=" ", flush=True)
        bougies = _fetch_all_history(sym)
        if bougies:
            m = _compute_metrics(bougies)
            if m:
                metrics[sym] = m
                print(f"{len(bougies)}j depuis {m['depuis']} | {m['regime']} | {m['drawdown_ath']}% ATH")
            else:
                print("pas assez de donnees")
        else:
            print("echec KuCoin")
        time.sleep(0.5)

    bull = sum(1 for m in metrics.values() if m.get("regime") == "bull")
    bear = sum(1 for m in metrics.values() if m.get("regime") == "bear")
    jeune = sum(1 for m in metrics.values() if m.get("regime") == "jeune")

    # Regime global pondere par market cap approx
    btc_reg = metrics.get("BTCUSDT", {}).get("regime", "?")
    eth_reg = metrics.get("ETHUSDT", {}).get("regime", "?")

    summary = {
        "date_maj": datetime.now().strftime("%Y-%m-%d %H:%M"),
        "nb_cryptos": len(metrics),
        "bull": bull, "bear": bear, "jeune": jeune,
        "regime_global": "bull" if bull > bear + 5 else "bear" if bear > bull + 5 else "neutre",
        "btc_regime": btc_reg,
        "eth_regime": eth_reg,
    }

    output = {"summary": summary, "metrics": metrics}

    with open(FICHIER_HIST, "w") as f:
        json.dump(output, f, ensure_ascii=False, indent=2)

    elapsed = time.time() - t0
    print(f"\nDone en {elapsed:.0f}s | {len(metrics)} cryptos | {bull} bull / {bear} bear / {jeune} jeune")
    print(f"Regime global: {summary['regime_global']} | BTC: {btc_reg} | ETH: {eth_reg}")
    return output


# ============================================
# CONTEXTES POUR LE BOT ET LE CHAT
# ============================================

def charger():
    """Charge les metriques cachees."""
    if os.path.exists(FICHIER_HIST):
        try:
            with open(FICHIER_HIST) as f:
                return json.load(f)
        except:
            pass
    return None


def contexte_pour_bot():
    """Contexte compact pour le bot de trading (injecte dans le professeur)."""
    data = charger()
    if not data:
        return ""

    s = data.get("summary", {})
    m = data.get("metrics", {})

    lines = [f"HISTORIQUE: Regime {s.get('regime_global','?').upper()} ({s.get('bull',0)}B/{s.get('bear',0)}H)"]

    # BTC et ETH en premier (poids le plus fort)
    for sym in ["BTCUSDT", "ETHUSDT"]:
        met = m.get(sym, {})
        if met:
            lines.append(f"  {sym[:3]}: {met.get('regime','?')} | RSIj {met.get('rsi_j','?')} RSIsem {met.get('rsi_sem','?')} | {met.get('drawdown_ath','?')}% ATH | phase {met.get('phase_cycle','?')}")

    # Cryptos en survente en regime bull (opportunites)
    survente = [(sym, met) for sym, met in m.items()
                if met.get("regime") == "bull" and met.get("rsi_j", 100) and met.get("rsi_j", 100) < 45]
    if survente:
        survente.sort(key=lambda x: x[1].get("rsi_j", 100))
        names = [f"{sym[:4].replace('USDT','')} RSI{met['rsi_j']}" for sym, met in survente[:5]]
        lines.append(f"  Survente bull: {', '.join(names)}")

    # Cryptos en surachat extreme (a eviter)
    surachat = [(sym, met) for sym, met in m.items()
                if met.get("rsi_j", 0) and met.get("rsi_j", 0) > 75]
    if surachat:
        names = [sym[:4].replace("USDT", "") for sym, _ in surachat[:5]]
        lines.append(f"  Surachat: {', '.join(names)}")

    return "\n".join(lines)


def contexte_pour_chat():
    """Contexte compact pour le chat IA (injecte dans le system prompt)."""
    data = charger()
    if not data:
        return ""

    s = data.get("summary", {})
    m = data.get("metrics", {})

    lines = ["CONTEXTE HISTORIQUE MARCHÉ:"]

    # Regime global
    regime = s.get("regime_global", "?")
    bull = s.get("bull", 0)
    bear = s.get("bear", 0)
    lines.append(f"Régime: {regime} ({bull} bull / {bear} bear)")

    # BTC
    btc = m.get("BTCUSDT", {})
    if btc:
        lines.append(f"BTC: {btc.get('drawdown_ath','?')}% sous ATH ({btc.get('ath_date','?')}), RSI sem {btc.get('rsi_sem','?')}, phase {btc.get('phase_cycle','?')}, {btc.get('ret_1a','?')}% sur 1 an")

    # ETH
    eth = m.get("ETHUSDT", {})
    if eth:
        lines.append(f"ETH: {eth.get('drawdown_ath','?')}% sous ATH, RSI sem {eth.get('rsi_sem','?')}, phase {eth.get('phase_cycle','?')}, {eth.get('ret_1a','?')}% sur 1 an")

    # Top opportunités (bull + survente)
    opp = [(sym, met) for sym, met in m.items()
           if met.get("regime") == "bull" and met.get("rsi_j", 100) and met.get("rsi_j", 100) < 50]
    if opp:
        opp.sort(key=lambda x: x[1].get("rsi_j", 100))
        names = [f"{sym.replace('USDT','')} (RSI {met['rsi_j']}, {met.get('drawdown_ath','?')}% ATH)" for sym, met in opp[:4]]
        lines.append(f"Opportunités: {', '.join(names)}")

    # Danger (surachat extreme)
    danger = [(sym, met) for sym, met in m.items() if met.get("rsi_j", 0) and met.get("rsi_j", 0) > 78]
    if danger:
        names = [sym.replace("USDT", "") for sym, _ in danger[:4]]
        lines.append(f"Surachat: {', '.join(names)}")

    return "\n".join(lines)


if __name__ == "__main__":
    mettre_a_jour()
