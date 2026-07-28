#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
APPRENTISSAGE CONTINU 24/7 — Module d'apprentissage local SANS IA externe.

Ce module fait tourner l'agent en boucle d'auto-amelioration purement
algorithmique (aucun appel Perplexity/Claude/Gemini) :

  1. BACKTESTING HISTORIQUE DE PATTERNS
     Rejoue les 200 dernieres bougies de chaque crypto, detecte les motifs
     de chandeliers (candlestick_learning.detecter_motif) et simule le
     resultat 5 bougies plus tard. Alimente pattern_learning.json avec
     des centaines d'observations en quelques minutes (au lieu d'attendre
     des semaines de trading reel).

  2. ANALYSE DE PERFORMANCE DES STRATEGIES
     Lit paper_trading.json (trades_fermes), regroupe par strategie+actif,
     calcule win rate / gain moyen / PnL total / pertes consecutives.

  3. OPTIMISATION LOCALE DES PARAMETRES
     Ajuste strat_params.json (RSI, Bollinger, TP, SL) selon des regles
     deterministes (pas d'IA) avec garde-fous stricts.

  4. DETECTION DE REGIME DE MARCHE
     Volatilite (ATR-like), force de tendance (SMA20 vs SMA50), momentum.

  5. RAPPORT D'APPRENTISSAGE
     Resume texte pret pour un digest Telegram.

Usage:
    python apprentissage_continu.py                    # cycle complet
    python apprentissage_continu.py --rapport           # affiche le rapport
    python apprentissage_continu.py --backtest BTCUSDT  # backtest un seul actif
    python apprentissage_continu.py --regime BTCUSDT    # regime de marche d'un actif

Cron recommande (toutes les 30 min):
    */30 * * * * cd /tmp/agent-ia-inspect && python3 apprentissage_continu.py >> apprentissage_cron.log 2>&1
"""
import os
import sys
import json
import math
from datetime import datetime

try:
    from dotenv import load_dotenv
    load_dotenv()
except Exception:
    pass

DOSSIER = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, DOSSIER)

# ============================================
# IMPORTS DU CODEBASE (jamais bloquants)
# ============================================
try:
    from indicateurs import historique_ohlcv
except Exception:
    historique_ohlcv = None

try:
    from candlestick_learning import detecter_motif, enregistrer_resultat, FICHIER_APPRENTISSAGE, FICHIER_APPRENTISSAGE_REPLI
except Exception:
    detecter_motif = None
    enregistrer_resultat = None
    FICHIER_APPRENTISSAGE = "/tmp/pattern_learning.json"
    FICHIER_APPRENTISSAGE_REPLI = os.path.join(DOSSIER, "pattern_learning.json")

try:
    from paper_trading import MARCHES_PAPER
except Exception:
    # Repli minimal si paper_trading.py indisponible (import lourd/echoue)
    MARCHES_PAPER = {
        "BTCUSDT": {"nom": "Bitcoin", "marche": "crypto", "source": "binance"},
        "ETHUSDT": {"nom": "Ethereum", "marche": "crypto", "source": "binance"},
        "SOLUSDT": {"nom": "Solana", "marche": "crypto", "source": "binance"},
        "BNBUSDT": {"nom": "BNB", "marche": "crypto", "source": "binance"},
        "XRPUSDT": {"nom": "XRP", "marche": "crypto", "source": "binance"},
    }

# ============================================
# FICHIERS
# ============================================
FICHIER_PAPER = os.path.join(DOSSIER, "paper_trading.json")
FICHIER_STRAT_PARAMS = os.path.join(DOSSIER, "strat_params.json")
FICHIER_LOG_APPRENTISSAGE = os.path.join(DOSSIER, "apprentissage_log.jsonl")

# ============================================
# GARDE-FOUS (bornes de securite sur les parametres)
# ============================================
BORNES = {
    "rsi_achat": (25.0, 60.0),
    "rsi_vente": (40.0, 90.0),   # surachat: reste au-dessus du seuil d'achat
    "bb_ecart": (1.0, 3.0),
    "tp": (0.5, 3.0),
    "sl": (0.3, 2.0),
}

# Liste des cryptos suivies (filtre MARCHES_PAPER sur marche == "crypto")
def _symboles_crypto():
    try:
        return [s for s, cfg in MARCHES_PAPER.items() if cfg.get("marche") == "crypto"]
    except Exception:
        return ["BTCUSDT", "ETHUSDT", "SOLUSDT", "BNBUSDT", "XRPUSDT"]


# ============================================
# UTILITAIRES
# ============================================
def _log_apprentissage(evenement, details=None):
    """Ajoute une ligne au journal JSONL d'apprentissage (ne doit jamais planter)."""
    try:
        ligne = {
            "date": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            "evenement": evenement,
            "details": details or {},
        }
        with open(FICHIER_LOG_APPRENTISSAGE, "a", encoding="utf-8") as f:
            f.write(json.dumps(ligne, ensure_ascii=False) + "\n")
    except Exception:
        pass


def _charger_json(chemin, defaut):
    try:
        if os.path.exists(chemin):
            with open(chemin, "r", encoding="utf-8") as f:
                return json.load(f)
    except Exception:
        pass
    return defaut


def _sauver_json(chemin, data):
    try:
        with open(chemin, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
        return True
    except Exception:
        return False


def _clamp(valeur, bornes):
    lo, hi = bornes
    return max(lo, min(hi, valeur))


def _envoyer_telegram(texte):
    """Envoi Telegram best-effort (ne doit jamais faire planter le module)."""
    try:
        from telegram_alerte import envoyer as _tg_envoyer
        return _tg_envoyer(texte)
    except Exception:
        try:
            # Compat: si un jour le module expose envoyer_telegram
            from telegram_alerte import envoyer_telegram as _tg_envoyer2
            return _tg_envoyer2(texte)
        except Exception:
            return False


# ============================================
# 1. BACKTESTING HISTORIQUE DE PATTERNS
# ============================================
def backtester_patterns(symbole, intervalle="15m", lookback=200):
    """
    Rejoue l'historique de bougies d'un actif et simule les trades qu'aurait
    genere chaque motif de chandelier detecte. Alimente l'apprentissage
    (pattern_learning.json via candlestick_learning.enregistrer_resultat)
    avec des centaines d'observations en quelques minutes.

    Pour chaque position de bougie i (a partir de i=4), on regarde les
    bougies precedentes (jusqu'a i inclus) pour detecter un motif, puis on
    simule: "si on achete a la cloture de la bougie i, quel est le gain
    5 bougies plus tard (ou avant si TP/SL touche)?"

    Retourne: {"patterns_tested": N, "patterns_gagnants": N,
               "patterns_perdants": N, "gain_moyen": X}
    """
    resultat = {"symbole": symbole, "patterns_tested": 0, "patterns_gagnants": 0,
                "patterns_perdants": 0, "gain_moyen": 0.0}
    try:
        if historique_ohlcv is None or detecter_motif is None or enregistrer_resultat is None:
            return resultat

        bougies = historique_ohlcv(symbole, intervalle, lookback)
        if not bougies or len(bougies) < 10:
            return resultat

        # Take-profit / stop-loss "simules" pour le backtest de pattern
        # (bornes prudentes, coherentes avec les seuils reels du bot)
        TP_SIMULE = 2.0
        SL_SIMULE = 1.5
        HORIZON = 5   # nb de bougies apres le signal

        gains = []
        n_gagnants = 0
        n_perdants = 0

        # On parcourt chaque position de bougie a partir de l'indice 4
        # (assez d'historique pour detecter motifs 3-4 bougies), et on doit
        # avoir HORIZON bougies suivantes pour simuler le resultat.
        for i in range(4, len(bougies) - HORIZON):
            fenetre = bougies[max(0, i - 3):i + 1]  # jusqu'a 4 bougies pour detecter_motif
            try:
                motifs = detecter_motif(fenetre)
            except Exception:
                motifs = []
            if not motifs:
                continue

            prix_entree = bougies[i].get("cloture")
            if not prix_entree or prix_entree <= 0:
                continue

            # Simule le trade sur les HORIZON bougies suivantes: on cherche
            # si TP ou SL est touche avant la fin de l'horizon (intraday
            # via haut/bas), sinon on prend la cloture a l'horizon.
            gain_pct = None
            for j in range(i + 1, min(i + 1 + HORIZON, len(bougies))):
                haut = bougies[j].get("haut", bougies[j].get("cloture", prix_entree))
                bas = bougies[j].get("bas", bougies[j].get("cloture", prix_entree))
                var_haut = (haut - prix_entree) / prix_entree * 100
                var_bas = (bas - prix_entree) / prix_entree * 100
                if var_haut >= TP_SIMULE:
                    gain_pct = TP_SIMULE
                    break
                if var_bas <= -SL_SIMULE:
                    gain_pct = -SL_SIMULE
                    break
            if gain_pct is None:
                # Ni TP ni SL touche: on prend la cloture a l'horizon
                idx_fin = min(i + HORIZON, len(bougies) - 1)
                prix_sortie = bougies[idx_fin].get("cloture", prix_entree)
                gain_pct = (prix_sortie - prix_entree) / prix_entree * 100

            # Pour un motif bearish, on simule un SHORT (inverse le gain);
            # pour bullish/neutral on garde le LONG classique.
            for m in motifs:
                direction = m.get("direction", "neutral")
                g = gain_pct if direction != "bearish" else -gain_pct
                try:
                    enregistrer_resultat(m["pattern"], symbole, g, direction)
                except Exception:
                    pass
                resultat["patterns_tested"] += 1
                gains.append(g)
                if g > 0:
                    n_gagnants += 1
                else:
                    n_perdants += 1

        resultat["patterns_gagnants"] = n_gagnants
        resultat["patterns_perdants"] = n_perdants
        resultat["gain_moyen"] = round(sum(gains) / len(gains), 4) if gains else 0.0
        return resultat
    except Exception as e:
        _log_apprentissage("erreur_backtest_patterns", {"symbole": symbole, "erreur": str(e)})
        return resultat


def backtester_tous_les_cryptos(intervalle="15m", lookback=200):
    """Lance backtester_patterns() sur toutes les cryptos de MARCHES_PAPER."""
    resultats = []
    for sym in _symboles_crypto():
        print(f"  [BACKTEST] {sym}...", end=" ", flush=True)
        r = backtester_patterns(sym, intervalle, lookback)
        resultats.append(r)
        print(f"{r['patterns_tested']} motifs testes | {r['patterns_gagnants']} gagnants "
              f"| {r['patterns_perdants']} perdants | gain moyen {r['gain_moyen']:+.3f}%")
    return resultats


# ============================================
# 2. ANALYSE DE PERFORMANCE DES STRATEGIES
# ============================================
def analyser_performance_strategies():
    """
    Lit paper_trading.json (trades_fermes), regroupe par strategie+symbole,
    calcule win rate, gain moyen, PnL total, pertes consecutives.

    Retourne un rapport dict:
        {"groupes": {...}, "top_gagnantes": [...], "top_perdantes": [...],
         "win_rate_global": float, "total_trades": int}
    """
    rapport = {"groupes": {}, "top_gagnantes": [], "top_perdantes": [],
               "win_rate_global": 0.0, "total_trades": 0}
    try:
        pf = _charger_json(FICHIER_PAPER, {})
        trades = pf.get("trades_fermes", [])
        if not trades:
            return rapport

        groupes = {}
        for t in trades:
            strat = t.get("strategie") or t.get("source") or "inconnu"
            sym = t.get("symbole", "?")
            cle = f"{strat}|{sym}"
            g = groupes.setdefault(cle, {
                "strategie": strat, "symbole": sym,
                "trades": [], "wins": 0, "losses": 0,
                "pnl_total": 0.0, "pertes_consecutives": 0,
                "pertes_consecutives_max": 0,
            })
            gain = t.get("gain_eur", 0.0)
            g["trades"].append(t)
            g["pnl_total"] += gain
            if gain > 0:
                g["wins"] += 1
                g["pertes_consecutives"] = 0
            else:
                g["losses"] += 1
                g["pertes_consecutives"] += 1
                g["pertes_consecutives_max"] = max(g["pertes_consecutives_max"], g["pertes_consecutives"])

        # Finalise les stats par groupe
        for cle, g in groupes.items():
            n = len(g["trades"])
            variations = [t.get("variation_pct", 0.0) for t in g["trades"]]
            g["n_trades"] = n
            g["win_rate"] = round(g["wins"] / n * 100, 2) if n else 0.0
            g["gain_moyen_pct"] = round(sum(variations) / n, 4) if n else 0.0
            g["pnl_total"] = round(g["pnl_total"], 4)
            del g["trades"]  # allege le rapport retourne

        rapport["groupes"] = groupes
        rapport["total_trades"] = len(trades)
        gagnes = sum(1 for t in trades if t.get("gain_eur", 0.0) > 0)
        rapport["win_rate_global"] = round(gagnes / len(trades) * 100, 2) if trades else 0.0

        # Top 3 gagnantes (par pnl_total) et bottom 3 perdantes, avec un
        # minimum de trades pour etre statistiquement pertinent (>=2)
        eligibles = [g for g in groupes.values() if g["n_trades"] >= 2]
        eligibles_tries = sorted(eligibles, key=lambda g: g["pnl_total"], reverse=True)
        rapport["top_gagnantes"] = eligibles_tries[:3]
        rapport["top_perdantes"] = list(reversed(eligibles_tries[-3:])) if eligibles_tries else []

        return rapport
    except Exception as e:
        _log_apprentissage("erreur_analyse_performance", {"erreur": str(e)})
        return rapport


# ============================================
# 3. OPTIMISATION LOCALE DES PARAMETRES
# ============================================
def optimiser_parametres():
    """
    Ajuste strat_params.json selon des regles deterministes (pas d'IA):
      - strategie >5 trades et win_rate <40% -> SL plus large (+0.1, borne)
      - strategie >5 trades et win_rate >70% -> SL plus serre (-0.1, borne)
      - win_rate global <50% -> RSI achat plus selectif (baisse le seuil -1)
      - win_rate global >60% -> RSI achat moins selectif (monte le seuil +1)
    Applique les changements a strat_params.json (bornes de securite) et
    journalise dans apprentissage_log.jsonl.

    Retourne: liste des changements effectues (list[dict]).
    """
    changements = []
    try:
        rapport_perf = analyser_performance_strategies()
        params = _charger_json(FICHIER_STRAT_PARAMS, {})
        params.setdefault("rsi_achat", 35.0)
        params.setdefault("rsi_vente", 70.0)
        params.setdefault("bb_ecart", 2.0)
        # tp/sl ne sont pas forcement dans strat_params.json (souvent geres
        # via constantes paper_trading.py), on les tracke ici quand meme
        # pour permettre un futur branchement (meta_tuning.py).
        params.setdefault("tp_suggere", 2.0)
        params.setdefault("sl_suggere", 1.5)

        modifie = False

        # --- Ajustement SL par strategie (win rate extreme) ---
        for cle, g in rapport_perf.get("groupes", {}).items():
            if g["n_trades"] <= 5:
                continue
            if g["win_rate"] < 40.0:
                ancien = params["sl_suggere"]
                nouveau = _clamp(ancien + 0.1, BORNES["sl"])
                if nouveau != ancien:
                    params["sl_suggere"] = nouveau
                    modifie = True
                    changements.append({
                        "param": "sl_suggere", "ancien": ancien, "nouveau": nouveau,
                        "raison": f"strategie {cle} win_rate={g['win_rate']}% (<40%, {g['n_trades']} trades) -> SL elargi"
                    })
            elif g["win_rate"] > 70.0:
                ancien = params["sl_suggere"]
                nouveau = _clamp(ancien - 0.1, BORNES["sl"])
                if nouveau != ancien:
                    params["sl_suggere"] = nouveau
                    modifie = True
                    changements.append({
                        "param": "sl_suggere", "ancien": ancien, "nouveau": nouveau,
                        "raison": f"strategie {cle} win_rate={g['win_rate']}% (>70%, {g['n_trades']} trades) -> SL resserre"
                    })

        # --- Ajustement RSI selon la performance globale ---
        win_rate_global = rapport_perf.get("win_rate_global", 0.0)
        total_trades = rapport_perf.get("total_trades", 0)
        if total_trades >= 5:  # assez de donnees pour une decision
            if win_rate_global < 50.0:
                ancien = float(params["rsi_achat"])
                # Plus selectif: on descend le seuil d'achat (attend plus de survente)
                nouveau = _clamp(ancien - 1.0, BORNES["rsi_achat"])
                if nouveau != ancien:
                    params["rsi_achat"] = nouveau
                    modifie = True
                    changements.append({
                        "param": "rsi_achat", "ancien": ancien, "nouveau": nouveau,
                        "raison": f"win_rate global {win_rate_global}% (<50%) -> RSI plus selectif"
                    })
            elif win_rate_global > 60.0:
                ancien = float(params["rsi_achat"])
                # Moins selectif: on monte le seuil d'achat (plus de signaux)
                nouveau = _clamp(ancien + 1.0, BORNES["rsi_achat"])
                if nouveau != ancien:
                    params["rsi_achat"] = nouveau
                    modifie = True
                    changements.append({
                        "param": "rsi_achat", "ancien": ancien, "nouveau": nouveau,
                        "raison": f"win_rate global {win_rate_global}% (>60%) -> RSI plus permissif"
                    })

        # S'assure que rsi_vente reste toujours au-dessus de rsi_achat + marge
        if float(params["rsi_vente"]) <= float(params["rsi_achat"]) + 10:
            ancien = params["rsi_vente"]
            params["rsi_vente"] = _clamp(float(params["rsi_achat"]) + 30, BORNES["rsi_vente"])
            if params["rsi_vente"] != ancien:
                modifie = True
                changements.append({
                    "param": "rsi_vente", "ancien": ancien, "nouveau": params["rsi_vente"],
                    "raison": "garde-fou: rsi_vente doit rester nettement au-dessus de rsi_achat"
                })

        if modifie:
            params["derniere_optimisation"] = datetime.now().strftime("%Y-%m-%d %H:%M")
            _sauver_json(FICHIER_STRAT_PARAMS, params)

        for c in changements:
            _log_apprentissage("changement_parametre", c)

        return changements
    except Exception as e:
        _log_apprentissage("erreur_optimisation_parametres", {"erreur": str(e)})
        return changements


# ============================================
# 4. DETECTION DE REGIME DE MARCHE
# ============================================
def detecter_regime(symbole):
    """
    Recupere les 50 dernieres bougies 1h et determine le regime de marche:
    trending_bull, trending_bear, ranging, volatile.

    Retourne: {"regime": str, "volatilite": float, "confiance": float}
    """
    resultat = {"symbole": symbole, "regime": "inconnu", "volatilite": 0.0, "confiance": 0.0}
    try:
        if historique_ohlcv is None:
            return resultat
        bougies = historique_ohlcv(symbole, "1h", 50)
        if not bougies or len(bougies) < 20:
            return resultat

        clotures = [b["cloture"] for b in bougies]

        # --- Volatilite (ATR-like: moyenne des true ranges en % du prix) ---
        true_ranges = []
        for i in range(1, len(bougies)):
            h = bougies[i]["haut"]
            l = bougies[i]["bas"]
            prev_close = bougies[i - 1]["cloture"]
            tr = max(h - l, abs(h - prev_close), abs(l - prev_close))
            if prev_close:
                true_ranges.append(tr / prev_close * 100)
        atr_pct = sum(true_ranges) / len(true_ranges) if true_ranges else 0.0

        # --- Force de tendance: SMA20 vs SMA50 (ou moins si historique court) ---
        periode_courte = min(20, len(clotures) // 2)
        periode_longue = min(50, len(clotures))
        sma_courte = sum(clotures[-periode_courte:]) / periode_courte
        sma_longue = sum(clotures[-periode_longue:]) / periode_longue
        ecart_sma_pct = (sma_courte - sma_longue) / sma_longue * 100 if sma_longue else 0.0

        # --- Momentum simple (variation cumulee sur les 10 dernieres bougies) ---
        n_mom = min(10, len(clotures) - 1)
        momentum_pct = (clotures[-1] - clotures[-1 - n_mom]) / clotures[-1 - n_mom] * 100 if n_mom > 0 else 0.0

        # --- Classification du regime ---
        # Volatilite elevee prime sur la tendance si l'ATR est tres eleve
        SEUIL_VOLATILITE_HAUTE = 2.5   # % ATR moyen par bougie 1h
        SEUIL_TENDANCE = 1.0           # % ecart SMA20/SMA50 pour parler de tendance

        if atr_pct >= SEUIL_VOLATILITE_HAUTE:
            regime = "volatile"
            confiance = min(1.0, atr_pct / (SEUIL_VOLATILITE_HAUTE * 2))
        elif ecart_sma_pct >= SEUIL_TENDANCE and momentum_pct > 0:
            regime = "trending_bull"
            confiance = min(1.0, abs(ecart_sma_pct) / (SEUIL_TENDANCE * 3))
        elif ecart_sma_pct <= -SEUIL_TENDANCE and momentum_pct < 0:
            regime = "trending_bear"
            confiance = min(1.0, abs(ecart_sma_pct) / (SEUIL_TENDANCE * 3))
        else:
            regime = "ranging"
            confiance = min(1.0, 1.0 - abs(ecart_sma_pct) / SEUIL_TENDANCE) if SEUIL_TENDANCE else 0.5
            confiance = max(0.0, confiance)

        resultat["regime"] = regime
        resultat["volatilite"] = round(atr_pct, 4)
        resultat["confiance"] = round(confiance, 3)
        resultat["sma_ecart_pct"] = round(ecart_sma_pct, 4)
        resultat["momentum_pct"] = round(momentum_pct, 4)
        return resultat
    except Exception as e:
        _log_apprentissage("erreur_detecter_regime", {"symbole": symbole, "erreur": str(e)})
        return resultat


# ============================================
# 5. RAPPORT D'APPRENTISSAGE
# ============================================
def _charger_pattern_learning():
    for chemin in (FICHIER_APPRENTISSAGE, FICHIER_APPRENTISSAGE_REPLI):
        try:
            if os.path.exists(chemin):
                with open(chemin, "r", encoding="utf-8") as f:
                    return json.load(f)
        except Exception:
            continue
    return {}


def rapport_apprentissage():
    """
    Lit pattern_learning.json et construit un texte-resume pret pour un
    digest Telegram: top 5 patterns gagnants / perdants, progres global.
    """
    try:
        data = _charger_pattern_learning()
        if not data:
            return "🧠 Apprentissage 24/7: aucune donnee encore. Lance un cycle de backtest."

        # Aplati toutes les entrees (symbole, pattern, stats)
        entrees = []
        total_observations = 0
        for symbole, motifs in data.items():
            for pattern_name, stats in motifs.items():
                total = stats.get("total", 0)
                total_observations += total
                if total < 3:
                    continue  # pas assez de donnees pour etre pertinent
                entrees.append({
                    "symbole": symbole, "pattern": pattern_name,
                    "total": total, "win_rate": stats.get("win_rate", 0.0),
                    "avg_gain": stats.get("avg_gain", 0.0),
                })

        entrees_gagnantes = sorted(entrees, key=lambda e: e["avg_gain"], reverse=True)[:5]
        entrees_perdantes = sorted(entrees, key=lambda e: e["avg_gain"])[:5]

        lignes = ["🧠 RAPPORT APPRENTISSAGE 24/7", ""]
        lignes.append(f"Total observations: {total_observations} (sur {len(data)} actifs)")
        lignes.append("")
        lignes.append("🏆 Top 5 patterns gagnants:")
        if entrees_gagnantes:
            for e in entrees_gagnantes:
                lignes.append(f"  {e['pattern']} ({e['symbole']}): {e['avg_gain']:+.2f}% "
                              f"moy | win rate {e['win_rate']*100:.0f}% ({e['total']} obs.)")
        else:
            lignes.append("  (pas encore assez de donnees)")
        lignes.append("")
        lignes.append("📉 Top 5 patterns perdants:")
        if entrees_perdantes:
            for e in entrees_perdantes:
                lignes.append(f"  {e['pattern']} ({e['symbole']}): {e['avg_gain']:+.2f}% "
                              f"moy | win rate {e['win_rate']*100:.0f}% ({e['total']} obs.)")
        else:
            lignes.append("  (pas encore assez de donnees)")
        lignes.append("")
        lignes.append(f"Couverture: {len(data)}/{len(_symboles_crypto())} cryptos suivies analysees")

        return "\n".join(lignes)
    except Exception as e:
        _log_apprentissage("erreur_rapport_apprentissage", {"erreur": str(e)})
        return "🧠 Apprentissage 24/7: erreur lors de la generation du rapport."


# ============================================
# 6. CYCLE PRINCIPAL / CLI
# ============================================
def cycle_complet():
    """Un cycle complet d'apprentissage: backtest + analyse + optimisation."""
    print("=" * 60)
    print(f"APPRENTISSAGE CONTINU 24/7 - {datetime.now().strftime('%d/%m/%Y %H:%M:%S')}")
    print("=" * 60)
    _log_apprentissage("debut_cycle", {})

    # 1. Backtest de patterns sur toutes les cryptos
    print("\n[1/4] Backtesting des patterns sur toutes les cryptos...")
    resultats_backtest = backtester_tous_les_cryptos()
    total_patterns = sum(r["patterns_tested"] for r in resultats_backtest)
    total_gagnants = sum(r["patterns_gagnants"] for r in resultats_backtest)
    total_perdants = sum(r["patterns_perdants"] for r in resultats_backtest)

    # 2. Analyse de performance des strategies
    print("\n[2/4] Analyse de performance des strategies (paper trading)...")
    rapport_perf = analyser_performance_strategies()
    print(f"  {rapport_perf['total_trades']} trades fermes | "
          f"win rate global {rapport_perf['win_rate_global']}%")
    if rapport_perf["top_gagnantes"]:
        print("  Top strategies gagnantes:")
        for g in rapport_perf["top_gagnantes"]:
            print(f"    {g['strategie']} / {g['symbole']}: PnL {g['pnl_total']:+.2f}€ "
                  f"| win rate {g['win_rate']}% ({g['n_trades']} trades)")
    if rapport_perf["top_perdantes"]:
        print("  Top strategies perdantes:")
        for p in rapport_perf["top_perdantes"]:
            print(f"    {p['strategie']} / {p['symbole']}: PnL {p['pnl_total']:+.2f}€ "
                  f"| win rate {p['win_rate']}% ({p['n_trades']} trades)")

    # 3. Optimisation des parametres
    print("\n[3/4] Optimisation locale des parametres...")
    changements = optimiser_parametres()
    if changements:
        for c in changements:
            print(f"  [MAJ] {c['param']}: {c['ancien']} -> {c['nouveau']} ({c['raison']})")
    else:
        print("  Aucun changement necessaire ce cycle.")

    # 4. Resume + digest Telegram
    print("\n[4/4] Resume du cycle")
    resume = (f"🧠 Apprentissage 24/7 — {total_patterns} patterns analysés "
              f"({total_gagnants} gagnants / {total_perdants} perdants), "
              f"{len(changements)} paramètre(s) ajusté(s)")
    print(f"  {resume}")

    _log_apprentissage("fin_cycle", {
        "patterns_tested": total_patterns,
        "patterns_gagnants": total_gagnants,
        "patterns_perdants": total_perdants,
        "changements_parametres": len(changements),
        "win_rate_global": rapport_perf.get("win_rate_global", 0.0),
    })

    # Notification Telegram uniquement si le cycle a produit quelque chose
    # de significatif (evite de spammer a chaque run de cron)
    if changements or total_patterns > 0:
        try:
            _envoyer_telegram(resume)
        except Exception:
            pass

    print("\n[5/5] Classement dynamique des cryptos")
    top = classer_cryptos(top_n=10)
    if top:
        print(f"  Top 10 cryptos sélectionnées:")
        for i, c in enumerate(top):
            print(f"    {i+1}. {c['symbole']} win={c['win_rate']*100:.0f}% gain={c['gain_moyen']*100:.3f}%")
    else:
        print("  Pas assez de données pour le classement")

    print("=" * 60)
    return {
        "patterns_tested": total_patterns,
        "patterns_gagnants": total_gagnants,
        "patterns_perdants": total_perdants,
        "changements": changements,
        "rapport_performance": rapport_perf,
        "top_cryptos": top,
    }


def aide():
    print("""
APPRENTISSAGE CONTINU 24/7 - Aide
===========================================
Module d'auto-apprentissage local, SANS IA externe (pur Python).

Commandes:
  python apprentissage_continu.py                    Cycle complet (backtest + analyse + optim)
  python apprentissage_continu.py --rapport           Affiche le rapport d'apprentissage
  python apprentissage_continu.py --backtest SYMBOLE  Backtest patterns sur un actif precis
  python apprentissage_continu.py --regime SYMBOLE    Detecte le regime de marche d'un actif
  python apprentissage_continu.py --aide              Affiche cette aide

Cron recommande (toutes les 30 min):
  */30 * * * * cd /tmp/agent-ia-inspect && python3 apprentissage_continu.py >> apprentissage_cron.log 2>&1
""")


# ---------------------------------------------------------------- CLASSEMENT
def classer_cryptos(top_n=10):
    """Classe toutes les cryptos par performance des patterns et selectionne
    le top N. Ecrit top_cryptos.json lu par paper_trading.py a chaque cycle.
    Critere de tri: gain moyen combine de tous les patterns sur cet actif."""
    try:
        with open(os.path.join(DOSSIER, "pattern_learning.json"), "r", encoding="utf-8") as f:
            data = json.load(f)
    except Exception:
        data = {}
    if not data:
        print("  pattern_learning.json vide — pas de classement possible")
        return []
    # Calculer le score global par crypto
    scores = []
    for symbole, patterns in data.items():
        if not isinstance(patterns, dict) or not patterns:
            continue
        total_trades = 0
        total_wins = 0
        total_gain = 0.0
        for pname, stats in patterns.items():
            if not isinstance(stats, dict):
                continue
            t = stats.get("total", 0)
            w = stats.get("wins", 0)
            g = stats.get("avg_gain", 0.0)
            total_trades += t
            total_wins += w
            total_gain += g * t  # gain pondere
        if total_trades < 5:
            continue  # pas assez de donnees
        win_rate = total_wins / total_trades if total_trades > 0 else 0
        gain_moyen = total_gain / total_trades if total_trades > 0 else 0
        scores.append({
            "symbole": symbole,
            "win_rate": round(win_rate, 4),
            "gain_moyen": round(gain_moyen, 4),
            "total_patterns": total_trades,
            "score": round(win_rate * 0.4 + gain_moyen * 0.6, 4)  # mix win_rate + gain
        })
    # Trier par score decroissant
    scores.sort(key=lambda x: x["score"], reverse=True)
    top = scores[:top_n]
    # Ecrire top_cryptos.json
    try:
        with open(os.path.join(DOSSIER, "top_cryptos.json"), "w", encoding="utf-8") as f:
            json.dump({
            "top": [s["symbole"] for s in top],
            "classement": top,
            "mis_a_jour": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            "total_evalue": len(scores)
        }, f, ensure_ascii=False, indent=2)
    except Exception:
        pass
    if top:
        print(f"  Top {top_n} cryptos: {', '.join(s['symbole'] for s in top)}")
    return top


def main():
    try:
        args = sys.argv[1:]
        if not args:
            cycle_complet()
        elif args[0] == "--rapport":
            print(rapport_apprentissage())
        elif args[0] == "--backtest":
            symbole = args[1].upper() if len(args) > 1 else "BTCUSDT"
            print(f"Backtest patterns sur {symbole}...")
            r = backtester_patterns(symbole)
            print(json.dumps(r, indent=2, ensure_ascii=False))
        elif args[0] == "--regime":
            symbole = args[1].upper() if len(args) > 1 else "BTCUSDT"
            print(f"Detection de regime pour {symbole}...")
            r = detecter_regime(symbole)
            print(json.dumps(r, indent=2, ensure_ascii=False))
        elif args[0] in ("--aide", "-h", "--help"):
            aide()
        else:
            aide()
    except Exception as e:
        print(f"Erreur (module resilient, ne devrait pas planter): {e}")
        _log_apprentissage("erreur_main", {"erreur": str(e)})


if __name__ == "__main__":
    main()
