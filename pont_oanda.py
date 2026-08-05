#!/usr/bin/env python3
"""
Pont OANDA - Connecte l'agent IA a OANDA pour trader en live
- API REST native Python (pas de Wine, pas de MT5)
- Supporte: Forex, Crypto, Or, Indices, Actions CFD
- Compte demo gratuit
"""
import os
import json
import urllib.request
import urllib.error
from datetime import datetime

# === CONFIGURATION ===
OANDA_API_KEY = os.getenv("OANDA_API_KEY", "")        # Token API OANDA
OANDA_ACCOUNT_ID = os.getenv("OANDA_ACCOUNT_ID", "")    # ID du compte (ex: 101-001-12345678-001)
OANDA_ENV = os.getenv("OANDA_ENV", "practice")          # practice (demo) ou live

# URL de base selon l'environnement
BASE_URL = "https://api-fxpractice.oanda.com" if OANDA_ENV == "practice" else "https://api-fxtrade.oanda.com"

# Correspondance agent -> OANDA instruments
SYMBOLES_OANDA = {
    # Crypto
    "BTCUSDT": "BTCUSD",
    "ETHUSDT": "ETHUSD",
    "SOLUSDT": "SOLUSD",
    "BNBUSDT": "BNBUSD",
    "XRPUSDT": "XRPUSD",
    "DOGEUSDT": "DOGEUSD",
    "ADAUSDT": "ADAUSD",
    "AVAXUSDT": "AVAXUSD",
    "LINKUSDT": "LINKUSD",
    "DOTUSDT": "DOTUSD",
    "ATOMUSDT": "ATOMUSD",
    "MATICUSDT": "MATICUSD",
    "LTCUSDT": "LTCUSD",
    # Forex
    "EURUSD": "EUR_USD",
    "GBPUSD": "GBP_USD",
    "USDJPY": "USD_JPY",
    "USDCHF": "USD_CHF",
    "AUDUSD": "AUD_USD",
    "USDCAD": "USD_CAD",
    "NZDUSD": "NZD_USD",
    "EURGBP": "EUR_GBP",
    "EURJPY": "EUR_JPY",
    "GBPJPY": "GBP_JPY",
    # Or & matieres premieres
    "XAUUSD": "XAU_USD",
    "XAGUSD": "XAG_USD",
    "USOIL": "WTICO_USD",
    "UKOIL": "BCO_USD",
    # Indices
    "US500": "SPX500_USD",
    "US30": "US30_USD",
    "NAS100": "NAS100_USD",
    "GER40": "DE30_EUR",
    "FRA40": "FR40_EUR",
    # Actions CFD
    "AAPL": "AAPL_USD",
    "TSLA": "TSLA_USD",
    "NVDA": "NVDA_USD",
    "MSFT": "MSFT_USD",
    "AMZN": "AMZN_USD",
    "GOOGL": "GOOGL_USD",
    "META": "META_USD",
    "NFLX": "NFLX_USD",
}

# Risk management
RISK_PCT_OANDA = 2.0
MAX_POSITIONS_OANDA = 10


def _headers():
    """Headers HTTP pour l'API OANDA."""
    return {
        "Authorization": f"Bearer {OANDA_API_KEY}",
        "Content-Type": "application/json",
        "Accept-Datetime-Format": "RFC3339",
    }


def _request(method, path, data=None):
    """Effectue une requete HTTP vers l'API OANDA."""
    url = f"{BASE_URL}/v3/{path}"
    body = json.dumps(data).encode() if data else None
    req = urllib.request.Request(url, data=body, headers=_headers(), method=method)
    try:
        with urllib.request.urlopen(req, timeout=10) as resp:
            return json.loads(resp.read().decode())
    except urllib.error.HTTPError as e:
        err = e.read().decode()
        print(f"[OANDA] Erreur HTTP {e.code}: {err[:200]}")
        return None
    except Exception as e:
        print(f"[OANDA] Erreur: {e}")
        return None


def tester_connexion():
    """Test la connexion OANDA et affiche le compte."""
    if not OANDA_API_KEY:
        print("[OANDA] Pas de API key. Set OANDA_API_KEY")
        return False
    if not OANDA_ACCOUNT_ID:
        print("[OANDA] Pas de account ID. Set OANDA_ACCOUNT_ID")
        return False
    resp = _request("GET", f"accounts/{OANDA_ACCOUNT_ID}")
    if not resp:
        return False
    acct = resp.get("account", {})
    print(f"\n=== COMPTE OANDA ===")
    print(f"ID: {acct.get('id', '?')}")
    print(f"Balance: {acct.get('balance', '?')} {acct.get('currency', '?')}")
    print(f"NAV: {acct.get('NAV', '?')}")
    print(f"Profit flottant: {acct.get('unrealizedPL', '?')}")
    print(f"Positions ouvertes: {len(acct.get('positions', []))}")
    return True


def recuperer_prix(symbole_agent):
    """Recupere le prix actuel d'un instrument via OANDA."""
    inst = SYMBOLES_OANDA.get(symbole_agent, symbole_agent)
    resp = _request("GET", f"instruments/{inst}/candles?count=1&price=M&granularity=M1")
    if not resp:
        return None
    candles = resp.get("candles", [])
    if not candles:
        return None
    c = candles[-1]
    mid = c.get("mid", {})
    return {
        "bid": float(mid.get("c", 0)),
        "ask": float(mid.get("c", 0)),
        "last": float(mid.get("c", 0)),
        "time": c.get("time", ""),
    }


def lister_instruments():
    """Liste les instruments disponibles sur le compte."""
    resp = _request("GET", f"accounts/{OANDA_ACCOUNT_ID}/instruments")
    if not resp:
        return []
    instruments = resp.get("instruments", [])
    print(f"\n=== INSTRUMENTS DISPONIBLES ({len(instruments)}) ===")
    # Filtrer ceux qu'on supporte
    for name, oanda_name in sorted(SYMBOLES_OANDA.items()):
        match = [i for i in instruments if i["name"] == oanda_name]
        if match:
            inst = match[0]
            print(f"  {name:<12} -> {oanda_name:<15} pip={inst.get('pip', '?')} margin={inst.get('marginRate', '?')}")
    return [i["name"] for i in instruments]


def ouvrir_position(symbole_agent, direction="ACHAT", units=None):
    """Ouvre une position sur OANDA."""
    inst = SYMBOLES_OANDA.get(symbole_agent, symbole_agent)
    if units is None:
        # Calculer les unites base sur le balance et le risk
        acct = _request("GET", f"accounts/{OANDA_ACCOUNT_ID}")
        if acct:
            balance = float(acct.get("account", {}).get("balance", 1000))
            units = max(1, int(balance * RISK_PCT_OANDA / 100))
        else:
            units = 100
    # Direction: ACHAT = positif, VENTE = negatif
    if direction == "VENTE":
        units = -units
    data = {
        "order": {
            "type": "MARKET",
            "instrument": inst,
            "units": str(units),
            "timeInForce": "FOK",
        }
    }
    resp = _request("POST", f"accounts/{OANDA_ACCOUNT_ID}/orders", data)
    if not resp:
        print(f"[OANDA] Erreur ouverture {inst}")
        return None
    fill = resp.get("orderFillTransaction", resp.get("orderCreateTransaction", {}))
    print(f"[OANDA] Position ouverte: {inst} {direction} {abs(units)} units @ {fill.get('price', '?')}")
    return {
        "id": fill.get("id", ""),
        "symbole": inst,
        "direction": direction,
        "units": abs(units),
        "prix": fill.get("price", "0"),
    }


def fermer_position(symbole_agent):
    """Ferme toutes les positions sur un instrument."""
    inst = SYMBOLES_OANDA.get(symbole_agent, symbole_agent)
    data = {"longUnits": "ALL", "shortUnits": "ALL"}
    resp = _request("PUT", f"accounts/{OANDA_ACCOUNT_ID}/positions/{inst}/close", data)
    if not resp:
        print(f"[OANDA] Erreur fermeture {inst}")
        return False
    print(f"[OANDA] Position fermee: {inst}")
    return True


def recuperer_positions():
    """Liste toutes les positions ouvertes."""
    resp = _request("GET", f"accounts/{OANDA_ACCOUNT_ID}/positions")
    if not resp:
        return []
    positions = resp.get("positions", [])
    result = []
    for p in positions:
        long_u = int(p.get("long", {}).get("units", 0))
        short_u = int(p.get("short", {}).get("units", 0))
        if long_u > 0:
            result.append({
                "symbole": p["instrument"],
                "direction": "ACHAT",
                "units": long_u,
                "prix": float(p["long"].get("averagePrice", 0)),
                "pl": float(p.get("unrealizedPL", 0)),
            })
        if short_u > 0:
            result.append({
                "symbole": p["instrument"],
                "direction": "VENTE",
                "units": short_u,
                "prix": float(p["short"].get("averagePrice", 0)),
                "pl": float(p.get("unrealizedPL", 0)),
            })
    return result


def bilan():
    """Affiche le bilan complet du compte OANDA."""
    if not tester_connexion():
        return None
    positions = recuperer_positions()
    print(f"\nPositions ouvertes: {len(positions)}")
    for p in positions:
        print(f"  {p['symbole']:<15} {p['direction']:<6} units={p['units']:>5} "
              f"prix={p['prix']:.5f} P&L={p['pl']:+.2f}")
    return {"positions": positions}


if __name__ == "__main__":
    import sys
    cmd = sys.argv[1] if len(sys.argv) > 1 else "help"
    if cmd == "test":
        tester_connexion()
    elif cmd == "instruments":
        lister_instruments()
    elif cmd == "bilan":
        bilan()
    elif cmd == "prix":
        for sym in ["BTCUSDT", "ETHUSDT", "EURUSD", "XAUUSD", "AAPL"]:
            prix = recuperer_prix(sym)
            if prix:
                print(f"  {sym}: {prix['last']}")
            else:
                print(f"  {sym}: non disponible")
    elif cmd == "achat" and len(sys.argv) > 2:
        ouvrir_position(sys.argv[2], "ACHAT")
    elif cmd == "vente" and len(sys.argv) > 2:
        ouvrir_position(sys.argv[2], "VENTE")
    elif cmd == "fermer" and len(sys.argv) > 2:
        fermer_position(sys.argv[2])
    else:
        print("Usage: python pont_oanda.py [test|instruments|bilan|prix|achat SYM|vente SYM|fermer SYM]")
        print("")
        print("Setup:")
        print("  1. Cree un compte demo gratuit: https://www.oanda.com/demo-account/")
        print("  2. Recupere ton API key: https://www.oanda.com/account/ (onglet 'API Access')")
        print("  3. Export les variables:")
        print('     export OANDA_API_KEY="ton_api_key"')
        print('     export OANDA_ACCOUNT_ID="ton_account_id"')
        print("  4. Test: python pont_oanda.py test")
