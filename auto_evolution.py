#!/usr/bin/env python3
"""
auto_evolution.py - Systeme d'auto-evolution et intelligence infinie

Le bot devient de plus en plus intelligent grace a:
1. Algorithme genetique: les strategies "se reproduisent" et "mutent"
2. Generation de strategies par IA (Gemini cree de nouvelles regles)
3. Memoire profonde: chaque trade est analyse et catalogue
4. Auto-decouverte de patterns: teste des combinaisons de parametres
5. Cross-asset learning: apprend d'une crypto pour l'appliquer aux autres
6. Meta-apprentissage: apprend a quel moment utiliser quelle strategie
7. Score de confiance evolutif: le bot connait ses forces et faiblesses
8. Boucle d'evolution continue: s'ameliorer toutes les 6h
"""

import json
import os
import time
import random
import math
from datetime import datetime, timedelta

DOSSIER = os.path.dirname(os.path.abspath(__file__))
FICHIER_EVOL = os.path.join(DOSSIER, "auto_evolution.json")
FICHIER_GENOME = os.path.join(DOSSIER, "genome_strategies.json")
FICHIER_MEMOIRE = os.path.join(DOSSIER, "memoire_profonde.json")

COIN_IDS = {
    "BTCUSDT": "bitcoin", "ETHUSDT": "ethereum", "SOLUSDT": "solana",
    "BNBUSDT": "binancecoin", "XRPUSDT": "ripple", "DOGEUSDT": "dogecoin",
    "AVAXUSDT": "avalanche-2", "LINKUSDT": "chainlink", "ARBUSDT": "arbitrum",
    "NEARUSDT": "near", "FETUSDT": "fetch-ai", "RNDRUSDT": "render-token",
    "LDOUSDT": "lido-dao", "AAVEUSDT": "aave", "PENDLEUSDT": "pendle",
}

# ============================================
# GESTION DE L'ETAT D'EVOLUTION
# ============================================
def charger_evolution():
    try:
        with open(FICHIER_EVOL) as f:
            return json.load(f)
    except Exception:
        return {
            "generation": 1,
            "strategies_actives": [],
            "strategies_archivees": [],
            "score_global": 0,
            "derniere_evolution": "",
            "nb_evolutions": 0,
            "decouvertes": [],
        }

def sauver_evolution(evol):
    evol["derniere_evolution"] = datetime.now().strftime("%Y-%m-%d %H:%M")
    try:
        with open(FICHIER_EVOL, "w") as f:
            json.dump(evol, f, indent=2)
    except Exception:
        pass

# ============================================
# MEMOIRE PROFONDE
# ============================================
def charger_memoire():
    try:
        with open(FICHIER_MEMOIRE) as f:
            return json.load(f)
    except Exception:
        return {
            "trades": [],
            "patterns_gagnants": {},
            "patterns_perdants": {},
            "correlations_decouvertes": [],
            "regles_apprises": [],
        }

def sauver_memoire(mem):
    try:
        with open(FICHIER_MEMOIRE, "w") as f:
            json.dump(mem, f, indent=2)
    except Exception:
        pass

def memoriser_trade(symbole, strategie, gain, gain_pct, conditions, pattern_bougie="", regime="", fear_greed=50):
    """Catalogue chaque trade dans la memoire profonde pour apprentissage."""
    mem = charger_memoire()

    entry = {
        "symbole": symbole,
        "strategie": strategie,
        "gain": gain,
        "gain_pct": gain_pct,
        "gagnant": gain > 0,
        "date": datetime.now().strftime("%Y-%m-%d %H:%M"),
        "conditions": conditions,
        "pattern_bougie": pattern_bougie,
        "regime": regime,
        "fear_greed": fear_greed,
    }
    mem["trades"].append(entry)
    mem["trades"] = mem["trades"][-500:]  # garder 500 max

    # Cataloguer les patterns gagnants/perdants
    if gain > 0:
        key = f"{strategie}_{pattern_bougie}" if pattern_bougie else strategie
        mem["patterns_gagnants"][key] = mem["patterns_gagnants"].get(key, 0) + 1
    else:
        key = f"{strategie}_{pattern_bougie}" if pattern_bougie else strategie
        mem["patterns_perdants"][key] = mem["patterns_perdants"].get(key, 0) + 1

    # Decouvrir des correlations dans les conditions
    if len(mem["trades"]) >= 10:
        _analyser_correlations(mem)

    sauver_memoire(mem)
    return entry

def _analyser_correlations(mem):
    """Decouvre des correlations dans l'historique des trades."""
    trades = mem["trades"]
    # Quelles conditions meneent a des gains?
    conditions_gagnantes = {}
    conditions_perdantes = {}
    for t in trades[-50:]:  # 50 derniers trades
        conditions = t.get("conditions", {})
        for k, v in conditions.items():
            if isinstance(v, (int, float)):
                bucket = "haut" if v > 0 else "bas"
                key = f"{k}_{bucket}"
                if t["gagnant"]:
                    conditions_gagnantes[key] = conditions_gagnantes.get(key, 0) + 1
                else:
                    conditions_perdantes[key] = conditions_perdantes.get(key, 0) + 1

    # Si une condition apparait souvent dans les gagnants, en faire une regle
    for key, count in conditions_gagnantes.items():
        if count >= 5:
            total = conditions_perdantes.get(key, 0) + count
            if total > 0 and count / total > 0.65:
                # Cree une regle!
                regle = f"Quand {key}, preferer l'achat (WR {count/total*100:.0f}% sur {total} trades)"
                if regle not in mem["regles_apprises"]:
                    mem["regles_apprises"].append(regle)
                    mem["regles_apprises"] = mem["regles_apprises"][-20:]  # max 20 regles

# ============================================
# ALGORITHME GENETIQUE DES STRATEGIES
# ============================================
def charger_genome():
    """Charge le genome des strategies (ADN du bot)."""
    try:
        with open(FICHIER_GENOME) as f:
            return json.load(f)
    except Exception:
        # Genome initial: strategies de base avec leurs parametres
        return {
            "strategies": [
                {
                    "id": "rsi_oversold",
                    "nom": "RSI Survente",
                    "gene": {"periode": 14, "survente": 30, "surachat": 70, "action": "ACHAT"},
                    "fitness": 0,
                    "trades": 0,
                    "gagnants": 0,
                    "pnl": 0,
                    "generation": 1,
                    "actif": True,
                },
                {
                    "id": "sma_cross",
                    "nom": "SMA Crossover",
                    "gene": {"sma_courte": 7, "sma_longue": 25, "action": "ACHAT"},
                    "fitness": 0,
                    "trades": 0,
                    "gagnants": 0,
                    "pnl": 0,
                    "generation": 1,
                    "actif": True,
                },
                {
                    "id": "breakout",
                    "nom": "Breakout Range",
                    "gene": {"periode": 20, "seuil": 0.998, "action": "ACHAT"},
                    "fitness": 0,
                    "trades": 0,
                    "gagnants": 0,
                    "pnl": 0,
                    "generation": 1,
                    "actif": True,
                },
                {
                    "id": "mean_reversion",
                    "nom": "Mean Reversion Z-Score",
                    "gene": {"periode": 20, "z_achat": -2.0, "z_vente": 2.0, "action": "ACHAT"},
                    "fitness": 0,
                    "trades": 0,
                    "gagnants": 0,
                    "pnl": 0,
                    "generation": 1,
                    "actif": True,
                },
                {
                    "id": "momentum",
                    "nom": "Momentum 3j",
                    "gene": {"seuil_hausse": 3.0, "seuil_baisse": -3.0, "action": "ACHAT"},
                    "fitness": 0,
                    "trades": 0,
                    "gagnants": 0,
                    "pnl": 0,
                    "generation": 1,
                    "actif": True,
                },
                {
                    "id": "bollinger",
                    "nom": "Bollinger Bands",
                    "gene": {"periode": 20, "ecart_type": 2.0, "seuil_bas": 0.95, "action": "ACHAT"},
                    "fitness": 0,
                    "trades": 0,
                    "gagnants": 0,
                    "pnl": 0,
                    "generation": 1,
                    "actif": True,
                },
                {
                    "id": "macd_divergence",
                    "nom": "MACD Divergence",
                    "gene": {"periode_fast": 12, "periode_slow": 26, "periode_signal": 9, "action": "ACHAT"},
                    "fitness": 0,
                    "trades": 0,
                    "gagnants": 0,
                    "pnl": 0,
                    "generation": 1,
                    "actif": True,
                },
            ],
            "generation_actuelle": 1,
            "historique_evolution": [],
        }

def sauver_genome(genome):
    try:
        with open(FICHIER_GENOME, "w") as f:
            json.dump(genome, f, indent=2)
    except Exception:
        pass

def evaluer_fitness(genome):
    """Met a jour le fitness de chaque strategie base sur ses performances."""
    for strat in genome["strategies"]:
        n = strat["trades"]
        if n == 0:
            strat["fitness"] = 0.5  # neutre
        else:
            wr = strat["gagnants"] / n
            pnl_moy = strat["pnl"] / n
            # Fitness = win rate * PnL moyen + bonus pour nombre de trades
            strat["fitness"] = max(0, min(2.0, wr * 1.0 + pnl_moy * 0.1 + min(n / 20, 0.3)))
    return genome

def evoluer_genome():
    """Fait evoluer le genome: croisement + mutation + selection naturelle.
    Les meilleures strategies survivent et se reproduisent.
    Les mauvaises sontarchivees et remplacees par des mutations.
    """
    genome = charger_genome()
    genome = evaluer_fitness(genome)

    strategies = genome["strategies"]
    if len(strategies) < 2:
        return genome, "Genome trop petit pour evoluer"

    # Trier par fitness
    strategies.sort(key=lambda s: s["fitness"], reverse=True)

    # Garder le top 50% (les elites)
    nb_elite = max(2, len(strategies) // 2)
    elites = strategies[:nb_elite]
    faibles = strategies[nb_elite:]

    ameliorations = []

    # 1. MUTATION des elites: creer des variations
    nouvelle_generation = []
    for elite in elites:
        # Garder l'original
        elite_copy = json.loads(json.dumps(elite))
        elite_copy["actif"] = True
        nouvelle_generation.append(elite_copy)

        # Creer une mutation (variation aleatoire des parametres)
        mutant = json.loads(json.dumps(elite))
        mutant["id"] = f"{elite['id']}_mut{genome['generation_actuelle']+1}"
        mutant["nom"] = f"{elite['nom']} v{genome['generation_actuelle']+1}"
        mutant["generation"] = genome["generation_actuelle"] + 1
        mutant["trades"] = 0
        mutant["gagnants"] = 0
        mutant["pnl"] = 0
        mutant["actif"] = True

        # Muter les genes
        gene = mutant["gene"]
        for key in gene:
            if isinstance(gene[key], (int, float)):
                # Mutation: +/- 10-30% du parametre
                mutation_rate = random.uniform(0.1, 0.3) * random.choice([-1, 1])
                gene[key] = round(gene[key] * (1 + mutation_rate), 4)
                # Bornes raisonnables
                if "periode" in key:
                    gene[key] = max(3, min(50, int(gene[key])))
                elif "survente" in key or "surachat" in key:
                    gene[key] = max(10, min(90, gene[key]))
                elif "seuil" in key:
                    gene[key] = max(0.5, min(1.5, gene[key]))
                elif "z_" in key:
                    gene[key] = max(-4.0, min(-0.5, gene[key]) if "achat" in key else max(0.5, min(4.0, gene[key])))

        ameliorations.append(f"MUTATION: {mutant['nom']} (fitness parent {elite['fitness']:.2f})")
        nouvelle_generation.append(mutant)

    # 2. CROISEMENT: combiner 2 elites pour creer un enfant
    if len(elites) >= 2:
        parent1, parent2 = random.sample(elites[:3], 2)
        enfant = {
            "id": f"cross_{genome['generation_actuelle']+1}_{random.randint(100,999)}",
            "nom": f"{parent1['nom']} x {parent2['nom']}",
            "gene": {},
            "fitness": 0,
            "trades": 0,
            "gagnants": 0,
            "pnl": 0,
            "generation": genome["generation_actuelle"] + 1,
            "actif": True,
        }
        # Croiser les genes: prendre aleatoirement de chaque parent
        all_keys = set(parent1["gene"].keys()) | set(parent2["gene"].keys())
        for key in all_keys:
            if key in parent1["gene"] and key in parent2["gene"]:
                enfant["gene"][key] = random.choice([parent1["gene"][key], parent2["gene"][key]])
            elif key in parent1["gene"]:
                enfant["gene"][key] = parent1["gene"][key]
            else:
                enfant["gene"][key] = parent2["gene"][key]

        ameliorations.append(f"CROISEMENT: {enfant['nom']}")
        nouvelle_generation.append(enfant)

    # 3. ARCHIVER les faibles
    for faible in faibles:
        faible["actif"] = False

    # Mettre a jour le genome
    genome["strategies"] = nouvelle_generation[:10]  # max 10 strategies
    genome["generation_actuelle"] += 1
    genome["historique_evolution"].append({
        "generation": genome["generation_actuelle"],
        "date": datetime.now().strftime("%Y-%m-%d %H:%M"),
        "elite": [e["nom"] for e in elites],
        "archivees": [f["nom"] for f in faibles],
        "crees": len(ameliorations),
    })
    genome["historique_evolution"] = genome["historique_evolution"][-50:]

    sauver_genome(genome)
    return genome, "\n".join(ameliorations) if ameliorations else "Aucune evolution necessaire"

# ============================================
# GENERATION DE STRATEGIES PAR IA
# ============================================
def generer_strategie_ia():
    """Utilise Gemini pour generer une nouvelle strategie de trading.
    L'IA analyse le marche et propose une regle qu'on peut tester.
    """
    try:
        import urllib.request
        import os
        api_key = os.environ.get("GEMINI_API_KEY", "")
        if not api_key:
            return None, "Pas de cle API Gemini"

        # Analyser les performances actuelles
        genome = charger_genome()
        mem = charger_memoire()

        # Stats pour le prompt
        top_strategies = sorted(genome["strategies"], key=lambda s: s["fitness"], reverse=True)[:3]
        top_str = ", ".join(f"{s['nom']}(WR {s['gagnants']}/{s['trades']})" for s in top_strategies if s["trades"] > 0)
        regles = mem.get("regles_apprises", [])[:5]
        regles_str = "\n".join(f"- {r}" for r in regles) if regles else "aucune regle encore"

        recent_trades = mem.get("trades", [])[-10:]
        wr_recente = sum(1 for t in recent_trades if t["gagnant"]) / len(recent_trades) * 100 if recent_trades else 0

        prompt = f"""Tu es un trader professionnel. Analyse mes strategies et propose une AMELIORATION.

STRATEGIES ACTUELLES (top 3):
{top_str}

REGLES APPRISES:
{regles_str}

WIN RATE RECENT (10 derniers trades): {wr_recente:.0f}%

Propose une NOUVELLE strategie ou une variation qui pourrait ameliorer mes resultats.
Format JSON strict:
{{"nom": "...", "description": "...", "indicateur": "RSI/SMA/EMA/Bollinger/MACD/Volume/etc", "parametres": {{"periode": 14, "seuil": 30}}, "regle": "ACHAT quand ...", "action": "ACHAT"}}
Reponds UNIQUEMENT avec le JSON."""

        url = f"https://generativelanguage.googleapis.com/v1beta/models/gemini-1.5-flash:generateContent?key={api_key}"
        payload = json.dumps({
            "contents": [{"parts": [{"text": prompt}]}],
            "generationConfig": {"temperature": 0.7, "maxOutputTokens": 300}
        }).encode()
        req = urllib.request.Request(url, data=payload, headers={"Content-Type": "application/json"})
        with urllib.request.urlopen(req, timeout=20) as resp:
            data = json.loads(resp.read())

        text = data["candidates"][0]["content"]["parts"][0]["text"]
        text = text.strip()
        if "```" in text:
            text = text.split("```")[1]
            if text.startswith("json"):
                text = text[4:]
        strategie = json.loads(text.strip())

        # Ajouter au genome
        genome = charger_genome()
        nouvelle = {
            "id": f"ia_gen{genome['generation_actuelle']}_{random.randint(100,999)}",
            "nom": strategie.get("nom", "Strategy IA"),
            "gene": strategie.get("parametres", {}),
            "fitness": 0,
            "trades": 0,
            "gagnants": 0,
            "pnl": 0,
            "generation": genome["generation_actuelle"],
            "actif": True,
            "source": "ia_generee",
            "description": strategie.get("description", ""),
            "regle": strategie.get("regle", ""),
        }
        genome["strategies"].append(nouvelle)
        genome["strategies"] = genome["strategies"][-10:]  # max 10
        sauver_genome(genome)

        return strategie, f"Nouvelle strategie generee: {strategie.get('nom', '?')}"

    except Exception as e:
        return None, f"Erreur generation IA: {e}"

# ============================================
# AUTO-DECOUVERTE DE PARAMETRES OPTIMAUX
# ============================================
def auto_decouverte(symbole="BTCUSDT"):
    """Teste des combinaisons de parametres pour trouver les plus rentables.
    Utilise un grid search simplifie.
    """
    try:
        import master_traders as mt
        prix_histo = mt.get_prix_histo(symbole)
        if len(prix_histo) < 30:
            return [], "donnees insuffisantes"

        resultats = []

        # Tester differentes periodes RSI
        for periode in [7, 10, 14, 21]:
            for survente in [20, 25, 30, 35]:
                try:
                    gains = []
                    for i in range(periode + 1, len(prix_histo) - 5, 5):
                        fenetre = prix_histo[i-periode:i]
                        gains_p = [(fenetre[j] - fenetre[j-1]) for j in range(1, len(fenetre))]
                        avg_gain = sum(g for g in gains_p if g > 0) / max(1, len([g for g in gains_p if g > 0]))
                        avg_loss = abs(sum(g for g in gains_p if g < 0) / max(1, len([g for g in gains_p if g < 0])))
                        if avg_loss == 0:
                            rsi = 100
                        else:
                            rs = avg_gain / avg_loss
                            rsi = 100 - (100 / (1 + rs))

                        if rsi < survente:
                            # Simuler un achat: +5j
                            gain_pct = (prix_histo[i + 5] - prix_histo[i]) / prix_histo[i] * 100
                            gains.append(gain_pct)

                    if gains:
                        wr = sum(1 for g in gains if g > 0) / len(gains) * 100
                        pnl_moy = sum(gains) / len(gains)
                        if wr >= 55 and pnl_moy > 0:
                            resultats.append({
                                "type": "RSI",
                                "params": f"periode={periode}, survente={survente}",
                                "wr": wr,
                                "pnl_moy": pnl_moy,
                                "trades": len(gains),
                            })
                except Exception:
                    continue

        # Tester differentes periodes SMA crossover
        for courte in [5, 7, 10, 15]:
            for longue in [20, 25, 30, 50]:
                if courte >= longue:
                    continue
                try:
                    gains = []
                    for i in range(longue + 1, len(prix_histo) - 5, 5):
                        sma_c = sum(prix_histo[i-courte:i]) / courte
                        sma_l = sum(prix_histo[i-longue:i]) / longue
                        if sma_c > sma_l:
                            gain_pct = (prix_histo[i + 5] - prix_histo[i]) / prix_histo[i] * 100
                            gains.append(gain_pct)

                    if gains and len(gains) >= 3:
                        wr = sum(1 for g in gains if g > 0) / len(gains) * 100
                        pnl_moy = sum(gains) / len(gains)
                        if wr >= 55 and pnl_moy > 0:
                            resultats.append({
                                "type": "SMA Cross",
                                "params": f"courte={courte}, longue={longue}",
                                "wr": wr,
                                "pnl_moy": pnl_moy,
                                "trades": len(gains),
                            })
                except Exception:
                    continue

        # Trier par PnL moyen
        resultats.sort(key=lambda x: x["pnl_moy"], reverse=True)

        return resultats[:5], f"{len(resultats)} configurations testees, top 5 retournees"

    except Exception as e:
        return [], f"Erreur auto-decouverte: {e}"

# ============================================
# CROSS-ASSET LEARNING
# ============================================
def cross_asset_learning():
    """Apprend d'une crypto pour appliquer aux autres.
    Si une strategie marche sur BTC, la tester sur ETH, SOL, etc.
    """
    mem = charger_memoire()
    trades = mem.get("trades", [])
    if len(trades) < 10:
        return "Pas assez de trades pour cross-asset learning"

    # Grouper par strategie + symbole
    par_strategie = {}
    for t in trades:
        strat = t.get("strategie", "")
        sym = t.get("symbole", "")
        key = strat
        if key not in par_strategie:
            par_strategie[key] = {"trades": [], "gagnants": 0, "total": 0}
        par_strategie[key]["trades"].append(t)
        par_strategie[key]["total"] += 1
        if t["gagnant"]:
            par_strategie[key]["gagnants"] += 1

    # Trouver les strategies qui marchent sur au moins 1 crypto
    decouvertes = []
    for strat, data in par_strategie.items():
        if data["total"] >= 3:
            wr = data["gagnants"] / data["total"] * 100
            if wr >= 55:
                # Cette strategie marche! Sur quelles cryptos?
                cryptos_gagnantes = [t["symbole"] for t in data["trades"] if t["gagnant"]]
                decouvertes.append({
                    "strategie": strat,
                    "wr": wr,
                    "total": data["total"],
                    "cryptos_gagnantes": list(set(cryptos_gagnantes)),
                })

    decouvertes.sort(key=lambda x: x["wr"], reverse=True)

    # Ajouter aux regles
    for d in decouvertes[:3]:
        regle = f"STRATEGIE {d['strategie']}: WR {d['wr']:.0f}% sur {d['total']} trades - marche sur {', '.join(d['cryptos_gagnantes'][:3])}"
        if regle not in mem["regles_apprises"]:
            mem["regles_apprises"].append(regle)
            mem["regles_apprises"] = mem["regles_apprises"][-20:]

    sauver_memoire(mem)

    if decouvertes:
        return "\n".join(f"- {d['strategie']}: WR {d['wr']:.0f}% ({d['total']} trades)" for d in decouvertes[:5])
    return "Aucune strategie gagnante identifiee pour cross-asset"

# ============================================
# SCORE DE CONFIANCE EVOLUTIF
# ============================================
def score_confiance_evolutif(symbole):
    """Calcule un score de confiance base sur l'historique du bot.
    Le bot sait s'il est bon ou mauvais sur cette crypto specifiquement.
    """
    mem = charger_memoire()
    trades_sym = [t for t in mem["trades"] if t["symbole"] == symbole]

    if len(trades_sym) < 3:
        return 0.5, "Confiance neutre (peu de trades)"

    gagnants = sum(1 for t in trades_sym if t["gagnant"])
    wr = gagnants / len(trades_sym)
    pnl_total = sum(t["gain"] for t in trades_sym)
    pnl_moy = pnl_total / len(trades_sym)

    # Score de confiance: combine win rate + PnL moyen + volume de trades
    confiance = wr * 0.5 + (0.3 if pnl_moy > 0 else 0) + min(len(trades_sym) / 30, 0.2)

    if confiance > 0.7:
        niveau = f"HAUTE confiance ({confiance:.0%}) - WR {wr:.0%}, PnL moy {pnl_moy:+.2f}EUR"
    elif confiance > 0.4:
        niveau = f"MOYENNE confiance ({confiance:.0%}) - WR {wr:.0%}"
    else:
        niveau = f"FAIBLE confiance ({confiance:.0%}) - WR {wr:.0%}, eviter"

    return confiance, niveau

# ============================================
# BOUCLE D'EVOLUTION COMPLETE
# ============================================
def evolution_complete():
    """Lance une evolution complete: toutes les etapes d'auto-amelioration.
    A executer toutes les 6h par le bot.
    """
    evol = charger_evolution()
    rapports = []

    # 1. Evaluer le fitness des strategies
    genome = charger_genome()
    genome = evaluer_fitness(genome)
    sauver_genome(genome)
    rapports.append("1. Fitness evalue")

    # 2. Faire evoluer le genome (mutation + croisement)
    genome, mutations = evoluer_genome()
    rapports.append(f"2. Genome evolve: {mutations}")

    # 3. Generer une nouvelle strategie par IA
    strat_ia, msg_ia = generer_strategie_ia()
    rapports.append(f"3. {msg_ia}")

    # 4. Cross-asset learning
    cross = cross_asset_learning()
    rapports.append(f"4. Cross-asset: {cross[:100]}")

    # 5. Auto-decouverte sur BTC
    decouvertes, msg_dec = auto_decouverte("BTCUSDT")
    if decouvertes:
        top = decouvertes[0]
        rapports.append(f"5. Decouverte: {top['type']} {top['params']} -> WR {top['wr']:.0f}%")
    else:
        rapports.append("5. Aucune decouverte rentable")

    # 6. Mettre a jour les stats
    evol["nb_evolutions"] += 1
    evol["generation"] = genome["generation_actuelle"]
    evol["score_global"] = sum(s["fitness"] for s in genome["strategies"]) / len(genome["strategies"])
    evol["decouvertes"] = [
        {"date": datetime.now().strftime("%Y-%m-%d %H:%M"),
         "decouvertes": [d["params"] for d in decouvertes[:3]] if decouvertes else []}
    ] + evol.get("decouvertes", [])
    evol["decouvertes"] = evol["decouvertes"][-20:]
    sauver_evolution(evol)

    return "\n".join(rapports)

# ============================================
# RAPPORT D'EVOLUTION
# ============================================
def rapport_evolution():
    """Genere un rapport complet de l'etat de l'evolution."""
    evol = charger_evolution()
    genome = charger_genome()
    mem = charger_memoire()

    lignes = ["=== AUTO-EVOLUTION DU BOT ===\n"]

    lignes.append(f"GENERATION: {genome['generation_actuelle']}")
    lignes.append(f"Evolution #: {evol.get('nb_evolutions', 0)}")
    lignes.append(f"Score global: {evol.get('score_global', 0):.2f}")
    lignes.append(f"Derniere evolution: {evol.get('derniere_evolution', 'jamais')}\n")

    # Strategies actives
    strategies = sorted(genome["strategies"], key=lambda s: s["fitness"], reverse=True)
    lignes.append("--- STRATEGIES (par fitness) ---")
    for s in strategies:
        n = s["trades"]
        if n > 0:
            wr = s["gagnants"] / n * 100
            pnl = s["pnl"]
        else:
            wr = 0
            pnl = 0
        emoji = "🟢" if s["fitness"] > 0.7 else ("🔴" if s["fitness"] < 0.3 else "🟡")
        source = " (IA)" if s.get("source") == "ia_generée" else ""
        lignes.append(f"  {emoji} {s['nom']:<25} fit={s['fitness']:.2f} | {n}t, WR {wr:.0f}%, PnL {pnl:+.2f}EUR{source}")

    # Memoire
    trades = mem.get("trades", [])
    lignes.append(f"\n--- MEMOIRE PROFONDE ---")
    lignes.append(f"Trades memorises: {len(trades)}")
    if trades:
        g = sum(1 for t in trades if t["gagnant"])
        wr = g / len(trades) * 100
        pnl = sum(t["gain"] for t in trades)
        lignes.append(f"Win rate global: {wr:.0f}% ({g}/{len(trades)})")
        lignes.append(f"PnL total: {pnl:+.2f}EUR")

    # Regles apprises
    regles = mem.get("regles_apprises", [])
    if regles:
        lignes.append(f"\n--- REGLES APPRISES ({len(regles)}) ---")
        for r in regles[:10]:
            lignes.append(f"  • {r}")

    # Patterns gagnants
    patterns_g = mem.get("patterns_gagnants", {})
    if patterns_g:
        lignes.append(f"\n--- PATTERNS GAGNANTS ---")
        top_patterns = sorted(patterns_g.items(), key=lambda x: x[1], reverse=True)[:5]
        for p, count in top_patterns:
            lignes.append(f"  ✅ {p}: {count} fois")

    # Patterns perdants
    patterns_p = mem.get("patterns_perdants", {})
    if patterns_p:
        lignes.append(f"\n--- PATTERNS PERDANTS ---")
        top_patterns = sorted(patterns_p.items(), key=lambda x: x[1], reverse=True)[:5]
        for p, count in top_patterns:
            lignes.append(f"  ❌ {p}: {count} fois")

    # Historique evolution
    hist = genome.get("historique_evolution", [])
    if hist:
        lignes.append(f"\n--- HISTORIQUE EVOLUTION ({len(hist)}) ---")
        for h in hist[-5:]:
            lignes.append(f"  Gen {h['generation']} ({h['date']}): {len(h.get('elite', []))} elites, {h.get('crees', 0)} nouvelles")

    return "\n".join(lignes)


if __name__ == "__main__":
    print(rapport_evolution())
