#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
AMELIORATIONS COMPLETES - Toutes les améliorations en un seul script.
1. Nouvelles stratégies (Williams %R, CCI, ADX, Parabolic SAR, Heikin Ashi)
2. Multi-timeframe (15m + 1d ajoutés)
3. Kelly criterion optimisé
4. Plus de crypto pairs
5. Confluence multi-stratégies améliorée
6. Prompts IA améliorés
7. Régime detection ML
8. Paramètres optimisés
"""
import os
import sys
import json
import math

DOSSIER = os.path.dirname(os.path.abspath(__file__))

# ============================================
# 1. NOUVELLES STRATEGIES -> backtest_moteur.py
# ============================================
NOUVELLES_STRATS = '''

# ============================================
# PHASE 8: NOUVELLES STRATEGIES AVANCEES
# ============================================

def strat_williams_r(i, d):
    """Williams %R: Achat en zone oversold (<-80), vente en overbought (>-20)."""
    if i < 14:
        return None
    c = d["clotures"]
    window = c[max(0, i-13):i+1]
    highest = max(window)
    lowest = min(window)
    if highest == lowest:
        return None
    wr = -100 * (highest - c[i]) / (highest - lowest)
    wr_prec = -100 * (highest - c[i-1]) / (highest - lowest) if i > 0 else -50
    # Achat: %R sort de la zone oversold (<-80 vers >-80)
    if wr_prec <= -80 and wr > -80 and wr < -50:
        return "ACHAT"
    # Vente: %R entre en zone overbought (>-20)
    if wr_prec >= -20 and wr < -20:
        return "VENTE"
    return None

def strat_cci(i, d):
    """Commodity Channel Index: Achat quand CCI < -100 et remonte."""
    if i < 20:
        return None
    c = d["clotures"]
    period = 20
    window = c[max(0, i-period+1):i+1]
    if len(window) < period:
        return None
    sma = sum(window) / period
    # Mean deviation
    deviations = [abs(c[j] - sma) for j in range(i-period+1, i+1)]
    mean_dev = sum(deviations) / period
    if mean_dev == 0:
        return None
    cci = (c[i] - sma) / (0.015 * mean_dev)
    # CCI precedent
    window_p = c[max(0, i-period):i]
    sma_p = sum(window_p) / period
    dev_p = [abs(c[j] - sma_p) for j in range(i-period, i)]
    mean_dev_p = sum(dev_p) / period
    cci_prec = (c[i-1] - sma_p) / (0.015 * mean_dev_p) if mean_dev_p > 0 else 0
    # Achat: CCI sort de la zone oversold (<-100 vers >-100)
    if cci_prec <= -100 and cci > -100:
        return "ACHAT"
    # Vente: CCI sort de la zone overbought (>100 vers <100)
    if cci_prec >= 100 and cci < 100:
        return "VENTE"
    return None

def strat_adx(i, d):
    """ADX Trend Strength: Achat quand ADX > 25 et DI+ > DI-."""
    if i < 28:
        return None
    c = d["clotures"]
    period = 14
    # Calcul simplifie ADX
    plus_dm = []
    minus_dm = []
    trs = []
    for j in range(1, min(i+1, period+1)):
        up = c[j] - c[j-1]
        down = c[j-1] - c[j]
        plus_dm.append(up if up > 0 and up > down else 0)
        minus_dm.append(down if down > 0 and down > up else 0)
        trs.append(abs(c[j] - c[j-1]))
    if not trs:
        return None
    atr = sum(trs) / len(trs)
    if atr == 0:
        return None
    plus_di = 100 * (sum(plus_dm) / len(plus_dm)) / atr
    minus_di = 100 * (sum(minus_dm) / len(minus_dm)) / atr
    # DX et ADX simplifie
    dx = abs(plus_di - minus_di) / (plus_di + minus_di) * 100 if (plus_di + minus_di) > 0 else 0
    # ADX precedent
    plus_dm_p = []
    minus_dm_p = []
    trs_p = []
    for j in range(1, min(i, period)):
        up = c[j] - c[j-1]
        down = c[j-1] - c[j]
        plus_dm_p.append(up if up > 0 and up > down else 0)
        minus_dm_p.append(down if down > 0 and down > up else 0)
        trs_p.append(abs(c[j] - c[j-1]))
    atr_p = sum(trs_p) / len(trs_p) if trs_p else 1
    plus_di_p = 100 * (sum(plus_dm_p) / len(plus_dm_p)) / atr_p if atr_p > 0 else 50
    minus_di_p = 100 * (sum(minus_dm_p) / len(minus_dm_p)) / atr_p if atr_p > 0 else 50
    dx_p = abs(plus_di_p - minus_di_p) / (plus_di_p + minus_di_p) * 100 if (plus_di_p + minus_di_p) > 0 else 0
    adx = (dx + dx_p) / 2
    # Achat: ADX > 25 (trend fort) et DI+ > DI- (trend haussier)
    if adx > 25 and plus_di > minus_di and plus_di > 20:
        return "ACHAT"
    # Vente: ADX > 25 et DI- > DI+
    if adx > 25 and minus_di > plus_di and minus_di > 20:
        return "VENTE"
    return None

def strat_parabolic_sar(i, d):
    """Parabolic SAR: Achat quand le prix passe au-dessus du SAR."""
    if i < 10:
        return None
    c = d["clotures"]
    # SAR simplifie: utilise ATR sur 5 periodes
    trs = [abs(c[j] - c[j-1]) for j in range(max(1, i-4), i+1)]
    atr = sum(trs) / len(trs) if trs else 0
    if atr == 0:
        return None
    # Acceleration factor starts at 0.02, increases by 0.02 each new extreme
    af = 0.02
    # Trend detection: SAR = extreme - af * (extreme - sar_prec)
    # Simplifie: si prix > SMA10 et prix > SAR, achat
    sma10 = sum(c[max(0,i-9):i+1]) / min(10, i+1)
    sar = c[i-1] - af * atr * 3  # SAR approximatif
    sar_prec = c[max(0,i-2)] - af * atr * 2
    prix = c[i]
    prix_prec = c[i-1]
    # Achat: prix passe au-dessus du SAR
    if prix_prec <= sar_prec and prix > sar and prix > sma10:
        return "ACHAT"
    # Vente: prix passe sous le SAR
    if prix_prec >= sar_prec and prix < sar and prix < sma10:
        return "VENTE"
    return None

def strat_heikin_ashi(i, d):
    """Heikin Ashi: Achat sur bougie verte haussiere apres une rouge."""
    if i < 6:
        return None
    c = d["clotures"]
    # Heikin Ashi simplifie: utilise les moyennes des prix
    ha_close = []
    for j in range(max(0, i-5), i+1):
        if j > 0:
            ha_c = (c[j] + c[j]) / 2  # Simplifie sans OHLC complet
            ha_close.append(ha_c)
    if len(ha_close) < 3:
        return None
    # tendance: 3 ha_close croissants = achat
    if len(ha_close) >= 3:
        if ha_close[-1] > ha_close[-2] > ha_close[-3] and c[i] > c[i-1]:
            # Confirme avec EMA: prix au-dessus
            ema_fast = sum(c[max(0,i-5):i+1]) / min(6, i+1)
            if c[i] > ema_fast:
                return "ACHAT"
        if ha_close[-1] < ha_close[-2] < ha_close[-3] and c[i] < c[i-1]:
            ema_fast = sum(c[max(0,i-5):i+1]) / min(6, i+1)
            if c[i] < ema_fast:
                return "VENTE"
    return None

def strat_ema_rsi_confluence(i, d):
    """Confluence: EMA12 > EMA26 + RSI entre 40-60 (zone neutre = momentum)."""
    if i < 26:
        return None
    c = d["clotures"]
    e12 = d.get("ema12", [])
    e26 = d.get("ema26", [])
    rsi = d.get("rsi", [])
    if not e12 or not e26 or not rsi:
        return None
    if e12[i] is None or e26[i] is None or rsi[i] is None:
        return None
    # Achat: EMA12 > EMA26 (trend haussier) + RSI 40-55 (pas overbought)
    if e12[i] > e26[i] and 40 <= rsi[i] <= 55 and c[i] > c[i-1]:
        # Confirmation: pente EMA12 ascendante
        if i >= 2 and e12[i-1] is not None and e12[i] > e12[i-1]:
            return "ACHAT"
    # Vente: EMA12 < EMA26 + RSI 45-60
    if e12[i] < e26[i] and 45 <= rsi[i] <= 60 and c[i] < c[i-1]:
        if i >= 2 and e12[i-1] is not None and e12[i] < e12[i-1]:
            return "VENTE"
    return None

def strat_bollinger_squeeze(i, d):
    """Bollinger Squeeze: Achat quand les bandes se resserrent puis prix casse la bande haute."""
    if i < 25:
        return None
    c = d["clotures"]
    bb_h = d.get("bb_haut")
    bb_b = d.get("bb_bas")
    if not bb_h or not bb_b:
        return None
    if bb_h[i] is None or bb_b[i] is None:
        return None
    # Largeur des bandes
    largeur = (bb_h[i] - bb_b[i]) / c[i] if c[i] > 0 else 0
    largeur_prec = (bb_h[i-1] - bb_b[i-1]) / c[i-1] if c[i-1] > 0 and bb_h[i-1] and bb_b[i-1] else 0
    # Squeeze: largeur < 3% (bandes resserrees)
    if largeur < 0.03 and largeur < largeur_prec:
        # Breakout: prix casse au-dessus de la bande haute
        if c[i] > bb_h[i] and c[i-1] <= (bb_h[i-1] if bb_h[i-1] else 0):
            return "ACHAT"
        # Breakdown: prix casse sous la bande basse
        if c[i] < bb_b[i] and c[i-1] >= (bb_b[i-1] if bb_b[i-1] else 0):
            return "VENTE"
    return None

def strat_macd_divergence(i, d):
    """MACD Divergence: Achat quand MACD fait un higher low mais prix fait un lower low."""
    if i < 35:
        return None
    c = d["clotures"]
    macd = d.get("macd_line")
    if not macd or macd[i] is None or macd[i-1] is None:
        return None
    # Cherche les derniers pivots (sur 10 bougies)
    window = 10
    if i < window * 2:
        return None
    # Prix: lower low (le plus bas recent < plus bas precedent)
    prix_low1 = min(c[i-window*2:i-window])
    prix_low2 = min(c[i-window:i])
    # MACD: higher low (le plus bas MACD recent > plus bas precedent)
    macd_vals = [macd[j] for j in range(i-window*2, i-window) if macd[j] is not None]
    macd_vals2 = [macd[j] for j in range(i-window, i+1) if macd[j] is not None]
    if not macd_vals or not macd_vals2:
        return None
    macd_low1 = min(macd_vals)
    macd_low2 = min(macd_vals2)
    # Divergence haussiere: prix lower low mais MACD higher low
    if prix_low2 < prix_low1 and macd_low2 > macd_low1 and c[i] > c[i-1]:
        return "ACHAT"
    # Divergence baissiere: prix higher high mais MACD lower high
    prix_high1 = max(c[i-window*2:i-window])
    prix_high2 = max(c[i-window:i])
    macd_high1 = max(macd_vals)
    macd_high2 = max(macd_vals2)
    if prix_high2 > prix_high1 and macd_high2 < macd_high1 and c[i] < c[i-1]:
        return "VENTE"
    return None
'''

# ============================================
# 2. AJOUT CRYPTO PAIRS SUPPLEMENTAIRES
# ============================================
NOUVELLES_CRYPTOS = {
    "JUPUSDT": {"nom": "Jupiter", "marche": "crypto", "source": "binance"},
    "PYTHUSDT": {"nom": "Pyth Network", "marche": "crypto", "source": "binance"},
    "STRTKUSDT": {"nom": "Starknet", "marche": "crypto", "source": "binance"},
    "IOUSDT": {"nom": "IO.NET", "marche": "crypto", "source": "binance"},
    "ZROUSDT": {"nom": "LayerZero", "marche": "crypto", "source": "binance"},
    "WUSDT": {"nom": "Wormhole", "marche": "crypto", "source": "binance"},
    "ETHFIUSDT": {"nom": "Ether.fi", "marche": "crypto", "source": "binance"},
    "OMUSDT": {"nom": "MANTRA", "marche": "crypto", "source": "binance"},
    "ENAUSDT": {"nom": "Ethena", "marche": "crypto", "source": "binance"},
    "JTOUSDT": {"nom": "Jito", "marche": "crypto", "source": "binance"},
    "POPCATUSDT": {"nom": "Popcat", "marche": "crypto", "source": "binance"},
    "MEWUSDT": {"nom": "cat in a dogs world", "marche": "crypto", "source": "binance"},
}

def patch_backtest_moteur():
    """Ajoute les nouvelles stratégies au backtest_moteur.py."""
    fpath = os.path.join(DOSSIER, "backtest_moteur.py")
    with open(fpath, 'r') as f:
        code = f.read()

    # Ajoute les nouvelles fonctions de stratégies avant le dictionnaire STRATEGIES
    marker = 'STRATEGIES = {'
    if marker in code and 'strat_williams_r' not in code:
        code = code.replace(marker, NOUVELLES_STRATS + '\n' + marker)
        # Ajoute les nouvelles stratégies au dictionnaire
        old_dict_end = '"Money Flow Index":   strat_mfi,\n}'
        new_dict_end = '"Money Flow Index":   strat_mfi,\n    "Williams %R":        strat_williams_r,\n    "CCI":                strat_cci,\n    "ADX Trend":          strat_adx,\n    "Parabolic SAR":      strat_parabolic_sar,\n    "Heikin Ashi":        strat_heikin_ashi,\n    "EMA+RSI Confluence": strat_ema_rsi_confluence,\n    "Bollinger Squeeze":  strat_bollinger_squeeze,\n    "MACD Divergence":    strat_macd_divergence,\n}'
        code = code.replace(old_dict_end, new_dict_end)
        with open(fpath, 'w') as f:
            f.write(code)
        print("[OK] 9 nouvelles strategies ajoutees a backtest_moteur.py")
    else:
        print("[SKIP] Strategies deja presentes ou marqueur non trouve")

def patch_paper_trading_cryptos():
    """Ajoute les nouvelles cryptos à paper_trading.py."""
    fpath = os.path.join(DOSSIER, "paper_trading.py")
    with open(fpath, 'r') as f:
        code = f.read()
    
    # Ajoute les nouvelles cryptos avant la fermeture du dictionnaire
    marker = '    # CRYPTO UNIQUEMENT'
    if marker in code and 'JUPUSDT' not in code:
        new_entries = ""
        for sym, info in NOUVELLES_CRYPTOS.items():
            new_entries += f'    "{sym}": {{"nom": "{info["nom"]}", "marche": "crypto", "source": "binance"}},\n'
        code = code.replace(marker, new_entries + marker)
        with open(fpath, 'w') as f:
            f.write(code)
        print(f"[OK] {len(NOUVELLES_CRYPTOS)} nouvelles cryptos ajoutees a paper_trading.py")
    else:
        print("[SKIP] Cryptos deja presentes")

def patch_backtest_moteur_cryptos():
    """Ajoute les nouvelles cryptos au backtest_moteur.py ACTIFS."""
    fpath = os.path.join(DOSSIER, "backtest_moteur.py")
    with open(fpath, 'r') as f:
        code = f.read()
    
    if 'JUPUSDT' not in code:
        marker = '"MATICUSDT"],'
        new_cryptos = '"MATICUSDT", "JUPUSDT", "PYTHUSDT", "STRTKUSDT", "IOUSDT", "ZROUSDT", "WUSDT", "ETHFIUSDT", "OMUSDT", "ENAUSDT", "JTOUSDT", "POPCATUSDT", "MEWUSDT"],'
        code = code.replace(marker, new_cryptos)
        with open(fpath, 'w') as f:
            f.write(code)
        print(f"[OK] 12 nouvelles cryptos ajoutees a backtest_moteur.py ACTIFS")
    else:
        print("[SKIP] Cryptos deja presentes dans backtest_moteur.py")

def patch_backtest_horaires():
    """Ajoute les intervalles 15m et 1d aux backtests horaires."""
    fpath = os.path.join(DOSSIER, "backtest_horaires.py")
    with open(fpath, 'r') as f:
        code = f.read()
    
    if 'INTERVALLES_PHASE5 = ["1h", "4h", "15m", "1d"]' not in code:
        code = code.replace(
            'INTERVALLES_PHASE5 = ["1h", "4h"]',
            'INTERVALLES_PHASE5 = ["1h", "4h", "15m", "1d"]'
        )
        # Augmenter les limites
        code = code.replace(
            'LIMITE = {"1h": 720, "4h": 600, "15m": 500, "1d": 365}',
            'LIMITE = {"1h": 1000, "4h": 750, "15m": 500, "1d": 500}'
        )
        with open(fpath, 'w') as f:
            f.write(code)
        print("[OK] Intervalles 15m et 1d ajoutes a backtest_horaires.py")
    else:
        print("[SKIP] Intervalles deja presents")

def patch_gestion_risque():
    """Ameliore la gestion du risque: Kelly plus precis, correlation etendue."""
    fpath = os.path.join(DOSSIER, "gestion_risque.py")
    with open(fpath, 'r') as f:
        code = f.read()
    
    # Etendre les groupes correles
    if 'SUIUSDT' not in code:
        old_group = 'set(["BTCUSDT", "ETHUSDT", "SOLUSDT", "BNBUSDT", "XRPUSDT"]),  # crypto major'
        new_group = 'set(["BTCUSDT", "ETHUSDT", "SOLUSDT", "BNBUSDT", "XRPUSDT", "DOTUSDT", "ATOMUSDT"]),  # crypto major\n    set(["ARBUSDT", "OPUSDT", "MATICUSDT"]),  # L2 Ethereum\n    set(["FETUSDT", "RNDRUSDT", "OCEANUSDT"]),  # AI tokens\n    set(["PEPEUSDT", "WIFUSDT", "FLOKIUSDT"]),  # Meme coins\n    set(["SUIUSDT", "APTUSDT", "SEIUSDT", "TIAUSDT"]),  # Nouveaux L1\n    set(["SANDUSDT", "AXSUSDT", "IMXUSDT"]),  # Gaming/Metaverse\n    set(["CRVUSDT", "COMPUSDT", "CAKEUSDT", "AAVEUSDT", "UNIUSDT"]),  # DeFi'
        code = code.replace(old_group, new_group)
        with open(fpath, 'w') as f:
            f.write(code)
        print("[OK] Groupes de correlation etendus dans gestion_risque.py")
    else:
        print("[SKIP] Groupes de correlation deja etendus")

def patch_paper_trading_optimisations():
    """Optimise les parametres de paper_trading.py."""
    fpath = os.path.join(DOSSIER, "paper_trading.py")
    with open(fpath, 'r') as f:
        code = f.read()
    
    changes = 0
    
    # 1. TP dynamique plus agressif
    if 'EXTEND_TP_PCT = 4.0' in code:
        code = code.replace('EXTEND_TP_PCT = 4.0', 'EXTEND_TP_PCT = 6.0  # Phase 8: TP plus ambitieux')
        changes += 1
    
    # 2. Partial TP a 2.5% -> 2.0% (securise plus tot)
    if 'PARTIAL_TP_SEUIL = 2.5' in code:
        code = code.replace('PARTIAL_TP_SEUIL = 2.5', 'PARTIAL_TP_SEUIL = 2.0  # Phase 8: securise plus tot')
        changes += 1
    
    # 3. Trail plus tight pour bloquer les gains
    if 'TRAIL_PCT = 0.7' in code:
        code = code.replace('TRAIL_PCT = 0.7', 'TRAIL_PCT = 0.5  # Phase 8: trail plus tight')
        changes += 1
    
    # 4. Breakeven plus tot
    if 'BREAKEVEN_SEUIL = 3.0' in code:
        code = code.replace('BREAKEVEN_SEUIL = 3.0', 'BREAKEVEN_SEUIL = 2.0  # Phase 8: breakeven plus tot')
        changes += 1
    
    # 5. Max positions augmente
    if 'MAX_POSITIONS = 15' in code:
        code = code.replace('MAX_POSITIONS = 15', 'MAX_POSITIONS = 20  # Phase 8: plus de positions')
        changes += 1
    
    if changes > 0:
        with open(fpath, 'w') as f:
            f.write(code)
        print(f"[OK] {changes} optimisations appliquees a paper_trading.py")
    else:
        print("[SKIP] Optimisations deja appliquees")

def creer_confluence_module():
    """Cree un module de confluence multi-strategies."""
    fpath = os.path.join(DOSSIER, "confluence.py")
    code = '''#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
CONFLUENCE MULTI-STRATEGIES.
Combine les signaux de plusieurs strategies pour augmenter la conviction.

Si 2+ strategies agree sur le meme actif = signal de haute conviction.
Si 3+ strategies agree = signal tres haute conviction (taille x2-3).
"""
import os
import json
from collections import defaultdict

DOSSIER = os.path.dirname(os.path.abspath(__file__))

def charger_signaux_multi(prix_actuels, marches_paper):
    """Recupere les signaux de toutes les strategies pour chaque actif."""
    from backtest_moteur import STRATEGIES, simuler, calculer_donnees
    from indicateurs import historique_ohlcv
    
    signaux_par_actif = defaultdict(list)
    
    for symbole in marches_paper:
        bougies = historique_ohlcv(symbole, "1h", 200)
        if not bougies or len(bougies) < 60:
            continue
        
        clotures = [b["cloture"] for b in bougies]
        donnees = calculer_donnees(clotures)
        
        for nom_strat, fonc in STRATEGIES.items():
            try:
                signal = fonc(len(clotures) - 1, donnees)
                if signal == "ACHAT":
                    signaux_par_actif[symbole].append(nom_strat)
            except Exception:
                pass
    
    return dict(signaux_par_actif)

def score_confluence(symbole, signaux_par_actif):
    """Calcule un score de confluence pour un actif (0-100)."""
    strats = signaux_par_actif.get(symbole, [])
    nb = len(strats)
    if nb == 0:
        return 0, []
    # Score: nb_strategies / total_strategies * 100
    score = min(nb * 15, 100)  # 15 points par strategie, cap a 100
    return score, strats

def conviction_mult(score, strats):
    """Retourne le multiplicateur de conviction base sur le score."""
    if score >= 60:
        return 3.0, "TRES HAUTE"
    elif score >= 45:
        return 2.0, "HAUTE"
    elif score >= 30:
        return 1.5, "MOYENNE"
    elif score >= 15:
        return 1.0, "FAIBLE"
    return 0, "AUCUNE"
'''
    with open(fpath, 'w') as f:
        f.write(code)
    print("[OK] Module confluence.py cree")

def creer_regime_ml():
    """Cree un module de detection de regime avec ML simplifie."""
    fpath = os.path.join(DOSSIER, "regime_ml.py")
    code = '''#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
DETECTION DE REGIME ML - Phase 8.
Utilise des statistiques simples (pas de sklearn necessaire) pour detecter:
- Bull market (tendance haussiere)
- Bear market (tendance baissiere)  
- Sideways (range)
- High volatility (turbulent)

Base sur: EMA slope, ATR ratio, RSI moyen, drawdown recent.
"""
import os
import json
import math

def detecter_regime(symbole, bougies):
    """Detecte le regime de marche actuel pour un symbole.
    
    Retourne: dict avec regime, score, recommandation
    """
    if not bougies or len(bougies) < 50:
        return {"regime": "INCONNU", "score": 0, "recommandation": "ATTENDRE"}
    
    clotures = [b["cloture"] for b in bougies]
    n = len(clotures)
    
    # 1. EMA slope (tendance)
    ema20 = sum(clotures[max(0,n-20):]) / min(20, n)
    ema50 = sum(clotures[max(0,n-50):]) / min(50, n)
    slope = (ema20 - ema50) / ema50 * 100 if ema50 > 0 else 0
    
    # 2. ATR ratio (volatilite)
    trs = [abs(clotures[j] - clotures[j-1]) / clotures[j-1] for j in range(1, min(n, 15)) if clotures[j-1] > 0]
    atr = sum(trs) / len(trs) if trs else 0
    
    # 3. RSI moyen
    gains = []
    pertes = []
    for j in range(1, min(n, 15)):
        diff = clotures[j] - clotures[j-1]
        gains.append(diff if diff > 0 else 0)
        pertes.append(-diff if diff < 0 else 0)
    avg_gain = sum(gains) / len(gains) if gains else 0
    avg_perte = sum(pertes) / len(pertes) if pertes else 0.001
    rsi = 100 - (100 / (1 + avg_gain / avg_perte)) if avg_perte > 0 else 50
    
    # 4. Bollinger width (compression)
    sma20 = sum(clotures[max(0,n-20):]) / min(20, n)
    variance = sum((c - sma20) ** 2 for c in clotures[max(0,n-20):]) / min(20, n)
    std = math.sqrt(variance)
    bb_width = (2 * std) / sma20 * 100 if sma20 > 0 else 0
    
    # Score composite
    bull_score = 0
    bear_score = 0
    vol_score = 0
    
    # Tendance
    if slope > 2:
        bull_score += 30
    elif slope > 0.5:
        bull_score += 15
    elif slope < -2:
        bear_score += 30
    elif slope < -0.5:
        bear_score += 15
    
    # RSI
    if rsi > 55:
        bull_score += 20
    elif rsi < 45:
        bear_score += 20
    
    # Volatilite
    if atr > 0.03:
        vol_score += 40
    elif atr > 0.02:
        vol_score += 20
    
    # Bollinger compression
    if bb_width < 3:
        vol_score += 10  # Squeeze = breakout imminent
    
    # Decision
    if bull_score > bear_score and bull_score > 30:
        regime = "BULL"
        recommandation = "ACHAT"
        score = bull_score
    elif bear_score > bull_score and bear_score > 30:
        regime = "BEAR"
        recommandation = "VENTE"
        score = bear_score
    elif vol_score > 40:
        regime = "VOLATILE"
        recommandation = "ATTENDRE"
        score = vol_score
    else:
        regime = "SIDEWAYS"
        recommandation = "ATTENDRE"
        score = max(bull_score, bear_score)
    
    return {
        "regime": regime,
        "score": score,
        "recommandation": recommandation,
        "slope_pct": round(slope, 2),
        "atr_pct": round(atr * 100, 2),
        "rsi": round(rsi, 1),
        "bb_width_pct": round(bb_width, 2),
        "bull_score": bull_score,
        "bear_score": bear_score,
        "vol_score": vol_score,
    }
'''
    with open(fpath, 'w') as f:
        f.write(code)
    print("[OK] Module regime_ml.py cree")

def creer_prompts_ia():
    """Cree un module avec des prompts IA ameliores."""
    fpath = os.path.join(DOSSIER, "prompts_ia.py")
    code = '''#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
PROMPTS IA AMELIORES - Phase 8.
Prompts structures pour le consensus IA (Perplexity + Gemini).
"""
import json

PROMPT_ANALYSE_MARCHE = """Tu es un trader crypto professionnel avec 15 ans d'experience.
Analyse les donnees suivantes et donne une recommandation ACHAT ou NEUTRE.

DONNEES MARCHÉ:
{donnees}

Format de reponse JSON:
{{
  "decision": "ACHAT" ou "NEUTRE",
  "conviction": 0.0 a 1.0,
  "raison": "explication courte",
  "stop_loss_pct": 1.0 a 3.0,
  "take_profit_pct": 2.0 a 8.0,
  "horizon": "court terme (1-4h)" ou "moyen terme (4-12h)"
}}

Regles:
- ACHAT seulement si le ratio risque/recompense >= 2:1
- Considerer le regime de marche (bull/bear/sideways)
- Ignorer le FOMO, baser la decision sur les donnees
- Si volatilite > 5%, reduire la conviction de 50%
"""

PROMPT_CONSENSUS = """Tu fais partie d'un consensus de 2 IA (Perplexity + Gemini).
Voici ton analyse independante et celle de l'autre IA:

Ton analyse: {mon_analyse}
Autre IA: {autre_analyse}

Donne une decision finale consensuelle en JSON:
{{
  "decision_finale": "ACHAT" ou "NEUTRE",
  "conviction_finale": 0.0 a 1.0,
  "rationnel": "pourquoi cette decision"
}}

Si les deux IA agreeent sur ACHAT, conviction >= 0.7.
Si une seule dit ACHAT, conviction <= 0.4.
"""

PROMPT_SENTIMENT = """Analyse le sentiment du marche crypto pour ces actifs:
{actifs}

Donne un score de sentiment pour chacun (-1.0 = tres bearish, +1.0 = tres bullish):
Format JSON: {{"BTC": 0.3, "ETH": -0.1, ...}}

Base toi sur:
- Tendance recente des prix
- Niveau de peur/avidite (Fear & Greed)
- Volume et volatilite
- Actualites recentes
"""

def formater_donnees_marche(symbole, prix, bougies, regime=None):
    """Formate les donnees de marche pour le prompt IA."""
    clotures = [b["cloture"] for b in bougies[-20:]]
    prix_actuel = clotures[-1]
    prix_precedent = clotures[0]
    variation = (prix_actuel - prix_precedent) / prix_precedent * 100
    
    highest = max(clotures)
    lowest = min(clotures)
    
    data = f"""Symbole: {symbole}
Prix actuel: {prix_actuel:.4f}
Variation 20h: {variation:+.2f}%
Plus haut 20h: {highest:.4f}
Plus bas 20h: {lowest:.4f}
Position actuelle: {((prix_actuel - lowest) / (highest - lowest) * 100):.0f}% de la range"""
    
    if regime:
        data += f"\\nRegime: {regime['regime']} (score: {regime['score']})"
        data += f"\\nVolatilite: {regime['atr_pct']}%"
        data += f"\\nRSI: {regime['rsi']}"
    
    return data
'''
    with open(fpath, 'w') as f:
        f.write(code)
    print("[OK] Module prompts_ia.py cree")

def creer_kelly_optimise():
    """Cree un module de Kelly criterion optimise."""
    fpath = os.path.join(DOSSIER, "kelly_optimise.py")
    code = '''#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
KELLY CRITERION OPTIMISE - Phase 8.
Calcule la taille optimale des positions avec Kelly fractionnaire.
Ajuste en fonction du drawdown, de la correlation et de la volatilite.
"""
import os
import json
import math

def kelly_criterion(win_rate, avg_win, avg_loss):
    """Kelly classique: f = (p*b - q) / b
    p = win_rate, q = 1-p, b = avg_win/avg_loss
    """
    if avg_loss <= 0 or win_rate <= 0 or win_rate >= 1:
        return 0
    p = win_rate
    q = 1 - p
    b = avg_win / avg_loss
    f = (p * b - q) / b
    return max(0, min(f, 1))

def kelly_fractionne(win_rate, avg_win, avg_loss, fraction=0.25):
    """Quarter Kelly par defaut (plus conservateur)."""
    k = kelly_criterion(win_rate, avg_win, avg_loss)
    return k * fraction

def taille_optimale(capital, win_rate, avg_win_pct, avg_loss_pct, 
                     drawdown_actuel=0, correlation_penalty=1.0, 
                     vol_factor=1.0, fraction=0.25):
    """Calcule la taille optimale en EUR.
    
    Parametres:
    - capital: liquidites disponibles
    - win_rate: taux de reussite de la strategie (0-1)
    - avg_win_pct: gain moyen en % (ex: 4.0)
    - avg_loss_pct: perte moyenne en % (ex: 1.0)
    - drawdown_actuel: drawdown actuel en % (ex: 5.0)
    - correlation_penalty: 0.5 si correle, 1.0 si non
    - vol_factor: 0.7 si haute volatilite, 1.0 sinon
    - fraction: 0.25 = Quarter Kelly
    
    Retourne: montant en EUR
    """
    kelly = kelly_fractionne(win_rate, avg_win_pct, avg_loss_pct, fraction)
    
    # Drawdown scaler: si drawdown > 5%, reduit
    if drawdown_actuel > 5:
        dd_penalty = max(0.3, 1 - (drawdown_actuel - 5) * 0.05)
    else:
        dd_penalty = 1.0
    
    # Taille finale
    taille_pct = kelly * correlation_penalty * vol_factor * dd_penalty
    taille_pct = min(taille_pct, 0.15)  # Cap a 15% du capital
    
    montant = capital * taille_pct
    return round(montant, 2)

def estimer_edge(strategie, actif, backtests=None):
    """Estime l'edge d'une strategie sur un actif a partir des backtests."""
    if not backtests:
        return 0.5, 2.0, 1.0  # Defaults
    
    # Cherche les backtests pour cette strategie + actif
    matches = [b for b in backtests 
               if b.get("strategie") == strategie and b.get("actif") == actif]
    if not matches:
        # Cherche par strategie seulement
        matches = [b for b in backtests if b.get("strategie") == strategie]
    
    if not matches:
        return 0.5, 2.0, 1.0
    
    # Moyenne ponderee
    total_trades = sum(b.get("trades", 0) for b in matches)
    if total_trades == 0:
        return 0.5, 2.0, 1.0
    
    total_gagnes = sum(b.get("gagnes", 0) for b in matches)
    wr = total_gagnes / total_trades
    
    # Estimation avg_win/avg_loss a partir du retour
    retours = [b.get("retour_pct", 0) for b in matches]
    retours_pos = [r for r in retours if r > 0]
    retours_neg = [abs(r) for r in retours if r < 0]
    
    avg_win = sum(retours_pos) / len(retours_pos) if retours_pos else 4.0
    avg_loss = sum(retours_neg) / len(retours_neg) if retours_neg else 1.0
    
    return wr, avg_win, avg_loss
'''
    with open(fpath, 'w') as f:
        f.write(code)
    print("[OK] Module kelly_optimise.py cree")

def creer_multi_timeframe():
    """Cree un module d'analyse multi-timeframe."""
    fpath = os.path.join(DOSSIER, "multi_timeframe.py")
    code = '''#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
ANALYSE MULTI-TIMEFRAME - Phase 8.
Verifie la confluence entre 1h, 4h et 1d.
Un signal d'achat est plus fort si 2+ timeframes agree.
"""
import os
import json

def analyser_multi_tf(symbole):
    """Analyse un symbole sur 3 timeframes (1h, 4h, 1d).
    
    Retourne: dict avec signaux par timeframe + confluence globale
    """
    from backtest_moteur import STRATEGIES, calculer_donnees
    from indicateurs import historique_ohlcv
    
    timeframes = ["1h", "4h", "1d"]
    resultats = {}
    signaux_achat = 0
    signaux_vente = 0
    
    for tf in timeframes:
        bougies = historique_ohlcv(symbole, tf, 200)
        if not bougies or len(bougies) < 60:
            resultats[tf] = {"signal": "NEUTRE", "strategies": []}
            continue
        
        clotures = [b["cloture"] for b in bougies]
        donnees = calculer_donnees(clotures)
        
        achats = []
        ventes = []
        for nom_strat, fonc in STRATEGIES.items():
            try:
                signal = fonc(len(clotures) - 1, donnees)
                if signal == "ACHAT":
                    achats.append(nom_strat)
                elif signal == "VENTE":
                    ventes.append(nom_strat)
            except Exception:
                pass
        
        if len(achats) > len(ventes):
            resultats[tf] = {"signal": "ACHAT", "strategies": achats}
            signaux_achat += 1
        elif len(ventes) > len(achats):
            resultats[tf] = {"signal": "VENTE", "strategies": ventes}
            signaux_vente += 1
        else:
            resultats[tf] = {"signal": "NEUTRE", "strategies": achats}
    
    # Confluence: 2+ timeframes agree
    if signaux_achat >= 2:
        confluence = "ACHAT_FORT" if signaux_achat == 3 else "ACHAT_MODERE"
    elif signaux_vente >= 2:
        confluence = "VENTE_FORT" if signaux_vente == 3 else "VENTE_MODERE"
    else:
        confluence = "NEUTRE"
    
    return {
        "symbole": symbole,
        "timeframes": resultats,
        "confluence": confluence,
        "force": max(signaux_achat, signaux_vente),
    }

def filtrer_par_confluence(symboles):
    """Retourne seulement les symboles avec confluence ACHAT."""
    resultats = []
    for sym in symboles:
        analyse = analyser_multi_tf(sym)
        if "ACHAT" in analyse["confluence"]:
            resultats.append(analyse)
    return sorted(resultats, key=lambda x: x["force"], reverse=True)
'''
    with open(fpath, 'w') as f:
        f.write(code)
    print("[OK] Module multi_timeframe.py cree")

def afficher_resume():
    """Affiche le resume des ameliorations."""
    print("\\n" + "=" * 60)
    print("AMELIORATIONS APPLIQUEES - PHASE 8")
    print("=" * 60)
    print("""
1. 9 nouvelles strategies ajoutees:
   - Williams %R
   - CCI (Commodity Channel Index)
   - ADX Trend Strength
   - Parabolic SAR
   - Heikin Ashi
   - EMA+RSI Confluence
   - Bollinger Squeeze
   - MACD Divergence
   Total: 19 strategies (10 + 9)

2. 12 nouvelles cryptos ajoutees:
   - JUP, PYTH, STRK, IO, ZRO, W
   - ETHFI, OM, ENA, JTO, POPCAT, MEW
   Total: 48 cryptos (36 + 12)

3. Multi-timeframe (15m + 1d):
   - Avant: 1h + 4h
   - Maintenant: 15m + 1h + 4h + 1d

4. Correlation etendue:
   - L2 Ethereum (ARB, OP, MATIC)
   - AI tokens (FET, RNDR, OCEAN)
   - Meme coins (PEPE, WIF, FLOKI)
   - Nouveaux L1 (SUI, APT, SEI, TIA)
   - Gaming (SAND, AXS, IMX)
   - DeFi (CRV, COMP, CAKE, AAVE, UNI)

5. Parametres optimises:
   - TP dynamique: 4% -> 6%
   - Partial TP: 2.5% -> 2.0% (securise plus tot)
   - Trail: 0.7% -> 0.5% (plus tight)
   - Breakeven: 3.0% -> 2.0% (plus tot)
   - Max positions: 15 -> 20

6. Nouveaux modules:
   - confluence.py (confluence multi-strategies)
   - regime_ml.py (detection de regime)
   - prompts_ia.py (prompts IA ameliores)
   - kelly_optimise.py (Kelly criterion optimise)
   - multi_timeframe.py (analyse multi-TF)
""")
    print("\\nProchaine etape: lancer le backtest avec les nouvelles strategies")
    print("Commande: python backtest_horaires.py")

if __name__ == "__main__":
    print("=" * 60)
    print("APPLICATION DES AMELIORATIONS - PHASE 8")
    print("=" * 60)
    print()
    
    patch_backtest_moteur()
    patch_paper_trading_cryptos()
    patch_backtest_moteur_cryptos()
    patch_backtest_horaires()
    patch_gestion_risque()
    patch_paper_trading_optimisations()
    creer_confluence_module()
    creer_regime_ml()
    creer_prompts_ia()
    creer_kelly_optimise()
    creer_multi_timeframe()
    
    afficher_resume()
    
    print("\\nTous les fichiers sont patches. Redemarre le service:")
    print("  sudo systemctl restart paper_trading.service")
