#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
INTELLIGENCE BOOSTER - Phase 8.
Rend l'agent plus intelligent en connectant tous les modules d'apprentissage.

1. ANALYSE DE PATTERNS GAGNANTS/PERDANTS
   - Apprend de chaque trade fermé
   - Détecte les conditions qui mènent aux gains
   - Crée des règles de filtrage automatiques

2. MEMOIRE DE CONTEXTE
   - Se souvient des conditions de marché lors de chaque trade
   - Corrèle le régime (bull/bear/sideways) avec les résultats
   - Ajuste le comportement selon le contexte actuel

3. OPTIMISATION ADAPTATIVE
   - Ajuste TP/SL selon la volatilité actuelle
   - Augmente la taille sur les setups gagnants
   - Réduit l'activité sur les marchés défavorables

4. CONSENSUS IA AMELIORÉ
   - Prompts structurés avec contexte de marché
   - Fusion des analyses multi-modèles
   - Score de conviction basé sur l'historique

5. AUTO-REFLEXION
   - Analyse quotidienne des performances
   - Identification des erreurs récurrentes
   - Génération de règles correctives
"""
import os
import sys
import json
import math
import time
from datetime import datetime, timedelta
from collections import defaultdict, Counter

DOSSIER = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, DOSSIER)

try:
    from dotenv import load_dotenv
    load_dotenv()
except Exception:
    pass

# Fichiers
PT_FILE = os.path.join(DOSSIER, "paper_trading.json")
BACKTESTS_FILE = os.path.join(DOSSIER, "backtests_horaires.json")
LECONS_FILE = os.path.join(DOSSIER, "lecons.json")
STRAT_PARAMS_FILE = os.path.join(DOSSIER, "strat_params.json")
INTELLIGENCE_FILE = os.path.join(DOSSIER, "intelligence_memory.json")
PATTERNS_FILE = os.path.join(DOSSIER, "patterns_gagnants.json")

TELEGRAM_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN", "")
TELEGRAM_CHAT = os.getenv("TELEGRAM_CHAT_ID", "")
PPLX_KEY = os.getenv("PPLX_API_KEY", "")


def load_json(path, default=None):
    if default is None:
        default = []
    try:
        with open(path, 'r') as f:
            return json.load(f)
    except Exception:
        return default


def save_json(path, data):
    with open(path, 'w') as f:
        json.dump(data, f, indent=2, ensure_ascii=False)


def envoyer_telegram(message):
    if not TELEGRAM_TOKEN or not TELEGRAM_CHAT:
        return
    try:
        import requests
        requests.post(
            f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage",
            json={"chat_id": TELEGRAM_CHAT, "text": message, "parse_mode": "HTML"},
            timeout=15
        )
    except Exception:
        pass


# ============================================
# 1. ANALYSE DE PATTERNS GAGNANTS/PERDANTS
# ============================================
def analyser_trades():
    """Analyse tous les trades fermés pour trouver des patterns."""
    pf = load_json(PT_FILE, {})
    trades = pf.get("trades", [])
    
    if not trades:
        print("[intelligence] Aucun trade à analyser")
        return
    
    # Regroupe par stratégie, actif, heure, régime
    stats = {
        "par_strategie": defaultdict(lambda: {"gagnes": 0, "perdus": 0, "pnl": 0}),
        "par_actif": defaultdict(lambda: {"gagnes": 0, "perdus": 0, "pnl": 0}),
        "par_heure": defaultdict(lambda: {"gagnes": 0, "perdus": 0, "pnl": 0}),
        "par_duree": defaultdict(lambda: {"gagnes": 0, "perdus": 0, "pnl": 0}),
    }
    
    for t in trades:
        strategie = t.get("strategie", "inconnu")
        actif = t.get("symbole", t.get("actif", "inconnu"))
        pnl = t.get("pnl", t.get("gain_perte", 0))
        gagne = pnl > 0
        
        # Heure
        heure_str = t.get("date_fermeture", t.get("date", ""))
        try:
            heure = datetime.fromisoformat(heure_str.replace("Z", "")).hour
        except Exception:
            heure = -1
        
        # Durée
        duree = t.get("duree_min", 0)
        if duree < 60:
            duree_cat = "<1h"
        elif duree < 180:
            duree_cat = "1-3h"
        elif duree < 360:
            duree_cat = "3-6h"
        else:
            duree_cat = "6h+"
        
        # Stats
        stats["par_strategie"][strategie]["gagnes" if gagne else "perdus"] += 1
        stats["par_strategie"][strategie]["pnl"] += pnl
        stats["par_actif"][actif]["gagnes" if gagne else "perdus"] += 1
        stats["par_actif"][actif]["pnl"] += pnl
        if heure >= 0:
            stats["par_heure"][heure]["gagnes" if gagne else "perdus"] += 1
            stats["par_heure"][heure]["pnl"] += pnl
        stats["par_duree"][duree_cat]["gagnes" if gagne else "perdus"] += 1
        stats["par_duree"][duree_cat]["pnl"] += pnl
    
    # Convertit defaultdict en dict
    for key in stats:
        stats[key] = dict(stats[key])
    
    # Sauvegarde
    memoire = load_json(INTELLIGENCE_FILE, {})
    memoire["analyse_trades"] = stats
    memoire["derniere_analyse"] = datetime.now().isoformat()
    save_json(INTELLIGENCE_FILE, memoire)
    
    # Affiche les insights
    print("\n[intelligence] === ANALYSE DES TRADES ===")
    
    # Top stratégies
    strats = sorted(stats["par_strategie"].items(), 
                    key=lambda x: x[1]["pnl"], reverse=True)
    print("\nTop stratégies (par PnL):")
    for name, s in strats[:5]:
        total = s["gagnes"] + s["perdus"]
        wr = s["gagnes"] / total * 100 if total > 0 else 0
        print(f"  {name}: {s['gagnes']}G/{s['perdus']}P | WR {wr:.0f}% | PnL {s['pnl']:+.2f}€")
    
    # Meilleures heures
    heures = sorted(stats["par_heure"].items(), 
                   key=lambda x: x[1]["pnl"], reverse=True)
    print("\nMeilleures heures:")
    for h, s in heures[:5]:
        total = s["gagnes"] + s["perdus"]
        wr = s["gagnes"] / total * 100 if total > 0 else 0
        print(f"  {h}h: {s['gagnes']}G/{s['perdus']}P | WR {wr:.0f}% | PnL {s['pnl']:+.2f}€")
    
    # Meilleures durées
    durees = sorted(stats["par_duree"].items(),
                    key=lambda x: x[1]["pnl"], reverse=True)
    print("\nMeilleures durées:")
    for d, s in durees:
        total = s["gagnes"] + s["perdus"]
        wr = s["gagnes"] / total * 100 if total > 0 else 0
        print(f"  {d}: {s['gagnes']}G/{s['perdus']}P | WR {wr:.0f}% | PnL {s['pnl']:+.2f}€")
    
    return stats


# ============================================
# 2. GÉNÉRATION DE RÈGLES INTELLIGENTES
# ============================================
def generer_regles(stats):
    """Génère des règles de filtrage basées sur l'analyse des trades."""
    regles = []
    
    if not stats:
        return regles
    
    # Règle 1: Désactiver les stratégies avec WR < 40% après 5+ trades
    for strat, s in stats.get("par_strategie", {}).items():
        total = s["gagnes"] + s["perdus"]
        if total >= 5:
            wr = s["gagnes"] / total
            if wr < 0.40:
                regles.append({
                    "type": "desactiver_strategie",
                    "cible": strat,
                    "raison": f"WR {wr*100:.0f}% sur {total} trades",
                    "confiance": min(0.9, total / 20),
                })
            elif wr > 0.70:
                regles.append({
                    "type": "booster_strategie",
                    "cible": strat,
                    "raison": f"WR {wr*100:.0f}% sur {total} trades",
                    "confiance": min(0.9, total / 20),
                })
    
    # Règle 2: Éviter les heures avec WR < 30% après 5+ trades
    for heure, s in stats.get("par_heure", {}).items():
        total = s["gagnes"] + s["perdus"]
        if total >= 5:
            wr = s["gagnes"] / total
            if wr < 0.30:
                regles.append({
                    "type": "eviter_heure",
                    "cible": f"{heure}h",
                    "raison": f"WR {wr*100:.0f}% à {heure}h sur {total} trades",
                    "confiance": min(0.8, total / 15),
                })
    
    # Règle 3: Privilégier les actifs avec WR > 60%
    for actif, s in stats.get("par_actif", {}).items():
        total = s["gagnes"] + s["perdus"]
        if total >= 5:
            wr = s["gagnes"] / total
            if wr > 0.60:
                regles.append({
                    "type": "privilegier_actif",
                    "cible": actif,
                    "raison": f"WR {wr*100:.0f}% sur {total} trades",
                    "confiance": min(0.85, total / 15),
                })
            elif wr < 0.35:
                regles.append({
                    "type": "eviter_actif",
                    "cible": actif,
                    "raison": f"WR {wr*100:.0f}% sur {total} trades",
                    "confiance": min(0.85, total / 15),
                })
    
    # Sauvegarde
    memoire = load_json(INTELLIGENCE_FILE, {})
    memoire["regles_generees"] = regles
    memoire["derniere_generation_regles"] = datetime.now().isoformat()
    save_json(INTELLIGENCE_FILE, memoire)
    
    print(f"\n[intelligence] {len(regles)} règles générées")
    for r in regles[:10]:
        print(f"  [{r['type']}] {r['cible']}: {r['raison']}")
    
    return regles


# ============================================
# 3. OPTIMISATION ADAPTATIVE DES PARAMÈTRES
# ============================================
def optimiser_parametres():
    """Ajuste les paramètres TP/SL selon les conditions de marché actuelles."""
    try:
        from indicateurs import historique_ohlcv
    except Exception:
        print("[intelligence] Module indicateurs non disponible")
        return
    
    # Volatilité moyenne du marché
    cryptos = ["BTCUSDT", "ETHUSDT", "SOLUSDT", "BNBUSDT"]
    volatilites = []
    
    for sym in cryptos:
        try:
            bougies = historique_ohlcv(sym, "1h", 50)
            if not bougies or len(bougies) < 20:
                continue
            clotures = [b["cloture"] for b in bougies]
            # ATR simplifié
            trs = [abs(clotures[j] - clotures[j-1]) / clotures[j-1] 
                   for j in range(1, len(clotures)) if clotures[j-1] > 0]
            vol = sum(trs[-14:]) / 14 if len(trs) >= 14 else 0
            volatilites.append(vol)
        except Exception:
            continue
    
    if not volatilites:
        print("[intelligence] Impossible de calculer la volatilité")
        return
    
    vol_moyenne = sum(volatilites) / len(volatilites)
    print(f"\n[intelligence] Volatilité moyenne: {vol_moyenne*100:.2f}%")
    
    # Paramètres adaptatifs
    params = load_json(STRAT_PARAMS_FILE, {})
    
    # TP adaptatif: plus de volatilité = TP plus élevé
    if vol_moyenne > 0.03:  # Haute volatilité
        tp_suggere = 5.0
        sl_suggere = 1.5
        regime = "HAUTE_VOLATILITE"
    elif vol_moyenne > 0.02:  # Volatilité normale
        tp_suggere = 4.0
        sl_suggere = 1.0
        regime = "NORMAL"
    else:  # Faible volatilité
        tp_suggere = 2.5
        sl_suggere = 0.8
        regime = "FAIBLE_VOLATILITE"
    
    params["tp_adaptatif"] = tp_suggere
    params["sl_adaptatif"] = sl_suggere
    params["regime_volatilite"] = regime
    params["volatilite_moyenne"] = round(vol_moyenne * 100, 2)
    params["derniere_optimisation"] = datetime.now().isoformat()
    
    save_json(STRAT_PARAMS_FILE, params)
    print(f"[intelligence] Paramètres: TP={tp_suggere}% SL={sl_suggere}% ({regime})")
    
    return params


# ============================================
# 4. ANALYSE IA AMÉLIORÉE
# ============================================
def analyser_avec_ia(symbole, prix, bougies, regime=None):
    """Analyse un actif avec Perplexity en utilisant un prompt structuré."""
    if not PPLX_KEY:
        return None
    
    import requests
    
    # Prépare les données
    clotures = [b["cloture"] for b in bougies[-20:]] if bougies else []
    if not clotures:
        return None
    
    prix_actuel = clotures[-1]
    variation = (prix_actuel - clotures[0]) / clotures[0] * 100
    highest = max(clotures)
    lowest = min(clotures)
    
    # Prompt structuré
    prompt = f"""Tu es un trader crypto professionnel. Analyse en JSON:

Symbole: {symbole}
Prix: {prix_actuel:.4f}
Variation 20h: {variation:+.2f}%
Range 20h: {lowest:.4f} - {highest:.4f}
Position dans range: {((prix_actuel - lowest) / (highest - lowest) * 100):.0f}%"""
    
    if regime:
        prompt += f"\nRégime: {regime.get('regime', '?')}"
        prompt += f"\nVolatilité: {regime.get('atr_pct', '?')}%"
        prompt += f"\nRSI: {regime.get('rsi', '?')}"
    
    prompt += """

Réponds en JSON:
{"decision": "ACHAT" ou "NEUTRE", "conviction": 0.0-1.0, "raison": "..."}

Règle: ACHAT seulement si ratio risque/récompense >= 2:1."""
    
    try:
        r = requests.post(
            "https://api.perplexity.ai/chat/completions",
            headers={"Authorization": f"Bearer {PPLX_KEY}"},
            json={
                "model": "sonar",
                "messages": [{"role": "user", "content": prompt}],
                "temperature": 0.3,
            },
            timeout=30
        )
        if r.status_code != 200:
            return None
        
        texte = r.json()["choices"][0]["message"]["content"]
        # Extract JSON
        import re
        match = re.search(r'\{[^}]+\}', texte)
        if match:
            return json.loads(match.group())
    except Exception as e:
        print(f"[intelligence] Erreur IA: {e}")
    
    return None


# ============================================
# 5. AUTO-RÉFLEXION QUOTIDIENNE
# ============================================
def reflexion_quotidienne():
    """Analyse quotidienne des performances et génère des insights."""
    pf = load_json(PT_FILE, {})
    trades = pf.get("trades", [])
    
    # Trades du jour
    aujourd = datetime.now().strftime("%Y-%m-%d")
    trades_jour = [t for t in trades 
                   if aujourd in str(t.get("date_fermeture", t.get("date", "")))]
    
    if not trades_jour:
        print("[intelligence] Aucun trade aujourd'hui")
        return None
    
    gagnes = sum(1 for t in trades_jour if t.get("pnl", 0) > 0)
    perdus = len(trades_jour) - gagnes
    pnl_total = sum(t.get("pnl", 0) for t in trades_jour)
    wr = gagnes / len(trades_jour) * 100 if trades_jour else 0
    
    insights = {
        "date": aujourd,
        "trades": len(trades_jour),
        "gagnes": gagnes,
        "perdus": perdus,
        "wr": round(wr, 1),
        "pnl_total": round(pnl_total, 2),
        "erreurs": [],
        "succes": [],
        "actions": [],
    }
    
    # Analyse les erreurs
    for t in trades_jour:
        if t.get("pnl", 0) < 0:
            raison = t.get("raison_sortie", "stop-loss")
            insights["erreurs"].append({
                "symbole": t.get("symbole", "?"),
                "strategie": t.get("strategie", "?"),
                "pnl": t.get("pnl", 0),
                "raison": raison,
            })
        else:
            insights["succes"].append({
                "symbole": t.get("symbole", "?"),
                "strategie": t.get("strategie", "?"),
                "pnl": t.get("pnl", 0),
            })
    
    # Génère des actions correctives
    if wr < 40 and len(trades_jour) >= 3:
        insights["actions"].append({
            "type": "reduire_activite",
            "raison": f"WR {wr:.0f}% aujourd'hui, réduire le sizing",
        })
    
    if perdus > gagnes * 2:
        insights["actions"].append({
            "type": "revoir_strategies",
            "raison": f"{perdus} pertes vs {gagnes} gains, revoir les stratégies actives",
        })
    
    # Cherche les patterns d'erreur récurrents
    erreurs_par_strat = Counter(e["strategie"] for e in insights["erreurs"])
    for strat, count in erreurs_par_strat.items():
        if count >= 2:
            insights["actions"].append({
                "type": "desactiver_strategie_temp",
                "cible": strat,
                "raison": f"{count} pertes avec {strat} aujourd'hui",
            })
    
    # Sauvegarde
    memoire = load_json(INTELLIGENCE_FILE, {})
    if "reflexions" not in memoire:
        memoire["reflexions"] = []
    memoire["reflexions"].append(insights)
    # Garde seulement 30 derniers jours
    memoire["reflexions"] = memoire["reflexions"][-30:]
    save_json(INTELLIGENCE_FILE, memoire)
    
    # Affiche
    print(f"\n[intelligence] === RÉFLEXION DU {aujourd} ===")
    print(f"Trades: {gagnes}G/{perdus}P | WR: {wr:.0f}% | PnL: {pnl_total:+.2f}€")
    
    if insights["erreurs"]:
        print("\nErreurs:")
        for e in insights["erreurs"][:5]:
            print(f"  {e['symbole']} ({e['strategie']}): {e['pnl']:+.2f}€ ({e['raison']})")
    
    if insights["succes"]:
        print("\nSuccès:")
        for s in insights["succes"][:5]:
            print(f"  {s['symbole']} ({s['strategie']}): {s['pnl']:+.2f}€")
    
    if insights["actions"]:
        print("\nActions recommandées:")
        for a in insights["actions"]:
            print(f"  [{a['type']}] {a.get('cible', '')} - {a['raison']}")
    
    # Envoie un résumé Telegram si PnL significatif
    if abs(pnl_total) > 5:
        emoji = "📈" if pnl_total > 0 else "📉"
        msg = f"{emoji} Réflexion du {aujourd}\n"
        msg += f"Trades: {gagnes}G/{perdus}P | WR: {wr:.0f}%\n"
        msg += f"PnL: {pnl_total:+.2f}€\n"
        if insights["actions"]:
            msg += "\nActions:\n"
            for a in insights["actions"][:3]:
                msg += f"- {a['raison']}\n"
        envoyer_telegram(msg)
    
    return insights


# ============================================
# 6. PRÉDICTION DE PROBABILITÉ DE SUCCÈS
# ============================================
def predire_succes(symbole, strategie, heure_utc=None):
    """Prédit la probabilité de succès d'un trade basé sur l'historique."""
    memoire = load_json(INTELLIGENCE_FILE, {})
    stats = memoire.get("analyse_trades", {})
    
    if not stats:
        return 0.5  # Neutre si pas de données
    
    proba = 0.5  # Base 50%
    confiances = []
    
    # Facteur stratégie
    strat_stats = stats.get("par_strategie", {}).get(strategie, {})
    total_s = strat_stats.get("gagnes", 0) + strat_stats.get("perdus", 0)
    if total_s >= 3:
        wr_s = strat_stats.get("gagnes", 0) / total_s
        proba_s = wr_s
        confiances.append(("strategie", proba_s, total_s))
    
    # Facteur actif
    actif_stats = stats.get("par_actif", {}).get(symbole, {})
    total_a = actif_stats.get("gagnes", 0) + actif_stats.get("perdus", 0)
    if total_a >= 3:
        wr_a = actif_stats.get("gagnes", 0) / total_a
        confiances.append(("actif", wr_a, total_a))
    
    # Facteur heure
    if heure_utc is not None:
        heure_stats = stats.get("par_heure", {}).get(str(heure_utc), {})
        total_h = heure_stats.get("gagnes", 0) + heure_stats.get("perdus", 0)
        if total_h >= 3:
            wr_h = heure_stats.get("gagnes", 0) / total_h
            confiances.append(("heure", wr_h, total_h))
    
    if not confiances:
        return 0.5
    
    # Moyenne pondérée par la confiance (nb d'observations)
    total_poids = sum(c[2] for c in confiances)
    proba_ponderee = sum(c[1] * c[2] for c in confiances) / total_poids
    
    return round(proba_ponderee, 3)


# ============================================
# 7. SCORE DE CONVICTION GLOBAL
# ============================================
def score_conviction(symbole, strategie, signal_technique, regime=None, heure_utc=None):
    """Calcule un score de conviction global (0-100) pour un trade potentiel.
    
    Combine:
    - Probabilité de succès (historique)
    - Signal technique
    - Régime de marché
    - Heure
    - Volatilité
    """
    score = 0
    
    # 1. Probabilité historique (max 40 points)
    proba = predire_succes(symbole, strategie, heure_utc)
    score += proba * 40
    
    # 2. Signal technique (max 20 points)
    if signal_technique == "ACHAT":
        score += 20
    
    # 3. Régime de marché (max 20 points)
    if regime:
        if regime.get("regime") == "BULL":
            score += 20
        elif regime.get("regime") == "BEAR":
            score += 0
        elif regime.get("regime") == "SIDEWAYS":
            score += 10
        elif regime.get("regime") == "VOLATILE":
            score += 5
    
    # 4. RSI (max 10 points)
    if regime and regime.get("rsi"):
        rsi = regime["rsi"]
        if 40 <= rsi <= 55:  # Zone neutre = momentum
            score += 10
        elif 30 <= rsi <= 40:  # Oversold
            score += 8
        elif rsi > 70:  # Overbought
            score += 0
        else:
            score += 5
    
    # 5. Volatilité (max 10 points)
    if regime and regime.get("atr_pct"):
        atr = regime["atr_pct"]
        if 1 <= atr <= 3:  # Volatilité idéale
            score += 10
        elif atr < 1:  # Trop calme
            score += 3
        elif atr > 5:  # Trop volatile
            score += 0
        else:
            score += 5
    
    return min(round(score), 100)


# ============================================
# 8. APPRENTISSAGE CONTINU
# ============================================
def apprentissage_cycle():
    """Cycle complet d'apprentissage: analyse → règles → optimisation → réflexion."""
    print("=" * 60)
    print(f"INTELLIGENCE BOOSTER - {datetime.now().strftime('%d/%m/%Y %H:%M')}")
    print("=" * 60)
    
    # 1. Analyse des trades
    stats = analyser_trades()
    
    # 2. Génération de règles
    regles = generer_regles(stats) if stats else []
    
    # 3. Optimisation des paramètres
    params = optimiser_parametres()
    
    # 4. Réflexion quotidienne
    reflexion = reflexion_quotidienne()
    
    print("\n" + "=" * 60)
    print("Cycle d'intelligence terminé")
    print("=" * 60)
    
    return {
        "stats": stats,
        "regles": regles,
        "params": params,
        "reflexion": reflexion,
    }


if __name__ == "__main__":
    apprentissage_cycle()
