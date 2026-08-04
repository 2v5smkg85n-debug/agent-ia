#!/usr/bin/env python3
"""
Pont MetaTrader 5 - Connecte l'agent IA a MT5 pour trader en live
- Recupere les prix en temps reel depuis MT5
- Ouvre/ferme des positions automatiquement
- Synchronise avec le paper trading
"""
import os
import sys
import json
import time
from datetime import datetime

# === CONFIGURATION ===
MT5_LOGIN = int(os.getenv("MT5_LOGIN", "0"))        # Login du compte demo
MT5_PASSWORD = os.getenv("MT5_PASSWORD", "")          # Mot de passe
MT5_SERVER = os.getenv("MT5_SERVER", "")               # Serveur (ex: Exness-MT5Demo)
MT5_PATH = os.getenv("MT5_PATH", "")                   # Chemin vers terminal64.exe (optionnel)

# Correspondance crypto/forex -> symboles MT5
SYMBOLES_MT5 = {
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
    "NEARUSDT": "NEARUSD",
    "LTCUSDT": "LTCUSD",
    # Forex
    "EURUSD": "EURUSD",
    "GBPUSD": "GBPUSD",
    "USDJPY": "USDJPY",
    "USDCHF": "USDCHF",
    "AUDUSD": "AUDUSD",
    "USDCAD": "USDCAD",
    "NZDUSD": "NZDUSD",
    "EURGBP": "EURGBP",
    "EURJPY": "EURJPY",
    "GBPJPY": "GBPJPY",
    # Or & matieres premieres
    "XAUUSD": "XAUUSD",
    "XAGUSD": "XAGUSD",
    "USOIL": "USOIL",
    "UKOIL": "UKOIL",
    # Indices
    "US500": "US500",
    "US30": "US30",
    "NAS100": "NAS100",
    "GER40": "GER40",
    "FRA40": "FRA40",
    # Actions CFD
    "AAPL": "AAPL",
    "TSLA": "TSLA",
    "NVDA": "NVDA",
    "MSFT": "MSFT",
    "AMZN": "AMZN",
    "GOOGL": "GOOGL",
    "META": "META",
    "NFLX": "NFLX",
}

# Volume minimal par trade (lot)
VOLUME_MIN = 0.01

# Risk management MT5
RISK_PCT_MT5 = 2.0  # 2% du capital MT5 par trade
CAP_MAX_TRADES_MT5 = 10  # max 10 positions simultanees


def initier_mt5():
    """Initialise la connexion a MT5."""
    try:
        import MetaTrader5 as mt5
    except ImportError:
        print("[MT5] Package MetaTrader5 non installe. Run: pip install MetaTrader5")
        return False

    # Initialiser la connexion
    kwargs = {}
    if MT5_PATH:
        kwargs["path"] = MT5_PATH
    if MT5_LOGIN:
        kwargs["login"] = MT5_LOGIN
        kwargs["password"] = MT5_PASSWORD
        kwargs["server"] = MT5_SERVER

    if not mt5.initialize(**kwargs):
        print(f"[MT5] Erreur initialisation: {mt5.last_error()}")
        return False

    info = mt5.account_info()
    if info:
        print(f"[MT5] Connecte: {info.name} | Balance: {info.balance} {info.currency} | Server: {info.server}")
    else:
        print("[MT5] Connecte (compte info non disponible)")

    return True


def recuperer_prix_mt5(symbole_agent):
    """Recupere le prix actuel d'un symbole depuis MT5."""
    import MetaTrader5 as mt5
    symbole_mt5 = SYMBOLES_MT5.get(symbole_agent, symbole_agent)
    tick = mt5.symbol_info_tick(symbole_mt5)
    if tick is None:
        # Essayer d'ajouter le symbole au Market Watch
        info = mt5.symbol_info(symbole_mt5)
        if info is None:
            return None
        mt5.symbol_select(symbole_mt5, True)
        tick = mt5.symbol_info_tick(symbole_mt5)
        if tick is None:
            return None
    return {
        "bid": tick.bid,
        "ask": tick.ask,
        "last": tick.last,
        "time": tick.time,
    }


def calculer_volume(balance, prix, risk_pct=RISK_PCT_MT5):
    """Calcule le volume (lot) base sur le risk et le balance."""
    montant_risque = balance * risk_pct / 100
    # Volume = montant / (prix * 100000) pour forex standard
    if prix > 0:
        volume = montant_risque / (prix * 1000)  # approximation
        volume = max(VOLUME_MIN, round(volume, 2))
        return volume
    return VOLUME_MIN


def ouvrir_position_mt5(symbole_agent, direction="ACHAT", volume=None):
    """Ouvre une position sur MT5."""
    import MetaTrader5 as mt5
    symbole_mt5 = SYMBOLES_MT5.get(symbole_agent, symbole_agent)

    # Verifier le nombre de positions
    positions = mt5.positions_total()
    if positions >= CAP_MAX_TRADES_MT5:
        print(f"[MT5] Max {CAP_MAX_TRADES_MT5} positions atteint")
        return None

    # Recuperer le prix
    tick = mt5.symbol_info_tick(symbole_mt5)
    if tick is None:
        mt5.symbol_select(symbole_mt5, True)
        tick = mt5.symbol_info_tick(symbole_mt5)
        if tick is None:
            print(f"[MT5] Symbole {symbole_mt5} non disponible")
            return None

    # Calculer le volume
    if volume is None:
        info = mt5.account_info()
        balance = info.balance if info else 1000
        prix = tick.ask if direction == "ACHAT" else tick.bid
        volume = calculer_volume(balance, prix)

    # Creer la requete
    request = {
        "action": mt5.TRADE_ACTION_DEAL,
        "symbol": symbole_mt5,
        "volume": float(volume),
        "type": mt5.ORDER_TYPE_BUY if direction == "ACHAT" else mt5.ORDER_TYPE_SELL,
        "price": tick.ask if direction == "ACHAT" else tick.bid,
        "deviation": 20,  # slippage max en points
        "magic": 20260804,  # magic number de l'agent
        "comment": "Agent-IA",
        "type_time": mt5.ORDER_TIME_GTC,
        "type_filling": mt5.ORDER_FILLING_IOC,
    }

    result = mt5.order_send(request)
    if result.retcode != mt5.TRADE_RETCODE_DONE:
        print(f"[MT5] Erreur ordre {symbole_mt5}: {result.retcode} - {result.comment}")
        return None

    print(f"[MT5] Position ouverte: {symbole_mt5} {direction} {volume} lot @ {request['price']}")
    return {
        "ticket": result.order,
        "symbole": symbole_mt5,
        "direction": direction,
        "volume": volume,
        "prix": request["price"],
    }


def fermer_position_mt5(ticket):
    """Ferme une position sur MT5 par son ticket."""
    import MetaTrader5 as mt5
    position = mt5.positions_get(ticket=ticket)
    if position is None or len(position) == 0:
        print(f"[MT5] Position {ticket} non trouvee")
        return False

    pos = position[0]
    symbole = pos.symbol
    tick = mt5.symbol_info_tick(symbole)
    if tick is None:
        return False

    request = {
        "action": mt5.TRADE_ACTION_DEAL,
        "symbol": symbole,
        "volume": pos.volume,
        "type": mt5.ORDER_TYPE_SELL if pos.type == mt5.POSITION_TYPE_BUY else mt5.ORDER_TYPE_BUY,
        "position": ticket,
        "price": tick.bid if pos.type == mt5.POSITION_TYPE_BUY else tick.ask,
        "deviation": 20,
        "magic": 20260804,
        "comment": "Agent-IA-Fermeture",
        "type_time": mt5.ORDER_TIME_GTC,
        "type_filling": mt5.ORDER_FILLING_IOC,
    }

    result = mt5.order_send(request)
    if result.retcode != mt5.TRADE_RETCODE_DONE:
        print(f"[MT5] Erreur fermeture {ticket}: {result.retcode}")
        return False

    print(f"[MT5] Position {ticket} fermee @ {request['price']}")
    return True


def recuperer_positions_mt5():
    """Liste toutes les positions ouvertes sur MT5."""
    import MetaTrader5 as mt5
    positions = mt5.positions_get()
    if positions is None:
        return []

    result = []
    for pos in positions:
        result.append({
            "ticket": pos.ticket,
            "symbole": pos.symbol,
            "type": "ACHAT" if pos.type == mt5.POSITION_TYPE_BUY else "VENTE",
            "volume": pos.volume,
            "prix_ouverture": pos.price_open,
            "prix_courant": pos.price_current,
            "profit": pos.profit,
            "swap": pos.swap,
        })
    return result


def bilan_mt5():
    """Affiche le bilan du compte MT5."""
    import MetaTrader5 as mt5
    info = mt5.account_info()
    if not info:
        print("[MT5] Compte non connecte")
        return

    print(f"\n=== BILAN MetaTrader 5 ===")
    print(f"Compte: {info.name}")
    print(f"Balance: {info.balance:.2f} {info.currency}")
    print(f"Equity: {info.equity:.2f} {info.currency}")
    print(f"Marge: {info.margin:.2f}")
    print(f"Marge libre: {info.margin_free:.2f}")
    print(f"Profit flottant: {info.profit:.2f} {info.currency}")

    positions = recuperer_positions_mt5()
    print(f"\nPositions ouvertes: {len(positions)}")
    for p in positions:
        print(f"  {p['symbole']:<10} {p['type']:<6} vol={p['volume']:.2f} "
              f"ouvert={p['prix_ouverture']:.5f} actuel={p['prix_courant']:.5f} "
              f"P&L={p['profit']:+.2f} {info.currency}")

    return {
        "balance": info.balance,
        "equity": info.equity,
        "profit": info.profit,
        "positions": positions,
    }


def tester_connexion():
    """Test rapide de la connexion MT5."""
    if not initier_mt5():
        return False
    import MetaTrader5 as mt5
    # Lister les symboles disponibles
    symbols = mt5.symbols_total()
    print(f"[MT5] {symbols} symboles disponibles")
    # Tester un prix
    for sym in ["EURUSD", "BTCUSD", "XAUUSD"]:
        tick = mt5.symbol_info_tick(sym)
        if tick:
            print(f"[MT5] {sym}: bid={tick.bid} ask={tick.ask}")
        else:
            mt5.symbol_select(sym, True)
            tick = mt5.symbol_info_tick(sym)
            if tick:
                print(f"[MT5] {sym}: bid={tick.bid} ask={tick.ask}")
            else:
                print(f"[MT5] {sym}: non disponible")
    bilan_mt5()
    mt5.shutdown()
    return True


if __name__ == "__main__":
    import sys
    if len(sys.argv) > 1 and sys.argv[1] == "test":
        tester_connexion()
    elif len(sys.argv) > 1 and sys.argv[1] == "bilan":
        if initier_mt5():
            bilan_mt5()
            import MetaTrader5 as mt5
            mt5.shutdown()
    elif len(sys.argv) > 1 and sys.argv[1] == "prix":
        if initier_mt5():
            for sym in ["BTCUSDT", "ETHUSDT", "EURUSD", "XAUUSD"]:
                prix = recuperer_prix_mt5(sym)
                if prix:
                    print(f"  {sym}: bid={prix['bid']} ask={prix['ask']}")
                else:
                    print(f"  {sym}: non disponible")
            import MetaTrader5 as mt5
            mt5.shutdown()
    else:
        print("Usage: python pont_mt5.py [test|bilan|prix]")
        print("  test  - Test la connexion et liste les symboles")
        print("  bilan - Affiche le bilan du compte")
        print("  prix  - Affiche les prix en temps reel")
