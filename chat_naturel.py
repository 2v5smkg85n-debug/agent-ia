#!/usr/bin/env python3
"""
Conversation Naturelle Telegram — L'agent comprend le langage naturel.

Comme Perplexity Computer: pose des questions en langage naturel, l'agent répond.

Au lieu de commandes rigides (/status, /positions), tu peux écrire:
- "Comment va mon portefeuille ?"
- "Quelles positions sont ouvertes ?"
- "Montre-moi les trades récents"
- "Le bot a-t-il fait des erreurs ?"
- "Quel est le win rate ?"
- "Redémarre le bot"
- "Analyse BTC"

Fonctionnement:
1. Polling Telegram (getUpdates) en boucle
2. NLP: comprend l'intention via mots-clés + Gemini si ambigu
3. Exécute la commande correspondante
4. Répond en langage naturel

Lance ce module comme service systemd séparé.
"""

import os
import sys
import json
import time
import re
import subprocess
from datetime import datetime

DOSSIER = os.path.dirname(os.path.abspath(__file__))
FICHIER_PAPER = os.path.join(DOSSIER, "paper_trading.json")
FICHIER_LOG = os.path.join(DOSSIER, "paper_trading.log")

# Charger les clés Telegram
TELEGRAM_TOKEN = ""
TELEGRAM_CHAT = ""
env_path = os.path.join(DOSSIER, ".env")
if os.path.exists(env_path):
    with open(env_path) as f:
        for line in f:
            line = line.strip()
            if line.startswith("TELEGRAM_BOT_TOKEN="):
                TELEGRAM_TOKEN = line.split("=", 1)[1].strip()
            elif line.startswith("TELEGRAM_CHAT_ID="):
                TELEGRAM_CHAT = line.split("=", 1)[1].strip()

API_URL = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}"
_last_update_id = 0
_cooldown = {}  # anti-spam par utilisateur


def _telegram_send(texte):
    """Envoie un message Telegram."""
    import requests
    try:
        r = requests.post(f"{API_URL}/sendMessage", data={"chat_id": TELEGRAM_CHAT, "text": texte}, timeout=15)
        return r.status_code == 200
    except Exception:
        return False


def _run(cmd):
    """Exécute une commande shell."""
    try:
        r = subprocess.run(cmd, shell=True, capture_output=True, text=True, timeout=30)
        return r.stdout.strip(), r.returncode
    except Exception as e:
        return str(e), 1


def _charger_paper():
    """Charge paper_trading.json."""
    if not os.path.exists(FICHIER_PAPER):
        return None
    try:
        with open(FICHIER_PAPER) as f:
            return json.load(f)
    except Exception:
        return None


def _lire_logs(n=30):
    """Lit les N dernières lignes du log."""
    if not os.path.exists(FICHIER_LOG):
        return "Aucun log disponible"
    out, _ = _run(f"tail -{n} '{FICHIER_LOG}'")
    return out


# ============================================
# NLP — COMPRÉHENSION DU LANGAGE NATUREL
# ============================================

def _comprendre(message):
    """
    Comprend l'intention du message en langage naturel.
    Retourne une intention: 'status', 'positions', 'trades', 'erreurs', 'winrate',
    'restart', 'analyse', 'scanner', 'capital', 'liquidite', 'aide', 'inconnu'
    """
    msg = message.lower().strip()
    
    # Status / portefeuille / comment ça va
    if any(w in msg for w in ["portefeuille", "portfolio", "comment", "comment ça va", "status", "solde", "ca va", "cv", "état", "etat", "global", "bilan"]):
        return "status"
    
    # Positions ouvertes
    if any(w in msg for w in ["position", "ouvert", "ouverte", "hold", "actif", "crypto détenue", "qu'est-ce que j'ai"]):
        return "positions"
    
    # Trades fermés / historique
    if any(w in msg for w in ["trade", "historique", "fermé", "ferme", "fermee", "récent", "recent", "dernier"]):
        return "trades"
    
    # Erreurs / problèmes
    if any(w in msg for w in ["erreur", "bug", "problème", "probleme", "crash", "sl-retard", "429", "rate limit", "cassé", "casse", "marche pas"]):
        return "erreurs"
    
    # Win rate / performance
    if any(w in msg for w in ["win rate", "winrate", "performance", "ratio", "pourcentage", "réussite", "reussite", "gagné", "gagne", "perdu", "pertes"]):
        return "winrate"
    
    # Restart
    if any(w in msg for w in ["redémarre", "redemarre", "restart", "reboot", "relance", "relancer"]):
        return "restart"
    
    # Scanner
    if any(w in msg for w in ["scan", "scanner", "diagnostic", "vérifie", "verifie", "check", "problème", "santé", "sante"]):
        return "scanner"
    
    # Capital / liquidités
    if any(w in msg for w in ["capital", "liquidité", "liquidite", "cash", "dispo", "disponible", "argent"]):
        return "capital"
    
    # Analyse d'un actif
    if any(w in msg for w in ["analyse", "analyser", "btc", "eth", "sol", "bitcoin", "ethereum", "solana", "prix"]):
        return "analyse"
    
    # Aide
    if any(w in msg for w in ["aide", "help", "commande", "que peux-tu", "que peut tu", "comment utiliser"]):
        return "aide"
    
    return "inconnu"


# ============================================
# RÉPONSES PAR INTENTION
# ============================================

def _reponse_status():
    """Répond avec un résumé du portefeuille."""
    data = _charger_paper()
    if not data:
        return "Je n'arrive pas à lire le portefeuille. Le bot tourne-t-il ?"
    
    capital = data.get("capital_initial", 1000)
    liquidites = data.get("liquidites", 0)
    positions = data.get("positions", [])
    trades = data.get("trades_fermes", [])
    frais = data.get("frais_totaux", 0)
    
    valeur_pos = sum(p.get("montant_eur", 0) for p in positions)
    total = liquidites + valeur_pos
    pnl = total - capital
    pnl_pct = (pnl / capital * 100) if capital else 0
    
    # Win rate
    gagnants = sum(1 for t in trades if t.get("gain_eur", t.get("pnl", 0)) > 0)
    total_trades = len(trades)
    wr = (gagnants / total_trades * 100) if total_trades else 0
    
    emoji = "🟢" if pnl >= 0 else "🔴"
    
    lignes = [
        f"{emoji} Portefeuille — {datetime.now().strftime('%d/%m %H:%M')}",
        f"",
        f"Capital: {total:.2f} EUR",
        f"P&L: {pnl:+.2f} EUR ({pnl_pct:+.1f}%)",
        f"Liquidités: {liquidites:.2f} EUR",
        f"Positions: {len(positions)}",
        f"Trades fermés: {total_trades}",
        f"Win rate: {wr:.0f}% ({gagnants}W / {total_trades - gagnants}L)",
        f"Frais: {frais:.2f} EUR",
    ]
    
    if positions:
        lignes.append("")
        lignes.append("Positions ouvertes:")
        for p in positions:
            sym = p.get("symbole", p.get("nom", "?"))
            val = p.get("montant_eur", 0)
            prix = p.get("prix_entree", 0)
            lignes.append(f"  {sym}: {val:.0f} EUR @ {prix:.4f}")
    
    return "\n".join(lignes)


def _reponse_positions():
    """Répond avec les positions ouvertes."""
    data = _charger_paper()
    if not data:
        return "Portefeuille illisible."
    
    positions = data.get("positions", [])
    if not positions:
        return "Aucune position ouverte. Le bot attend des signaux."
    
    lignes = [f"Positions ouvertes ({len(positions)}):", ""]
    for p in positions:
        sym = p.get("symbole", p.get("nom", "?"))
        val = p.get("montant_eur", 0)
        prix = p.get("prix_entree", 0)
        strategie = p.get("strategie", "?")
        ouvert = p.get("date_ouverture", "?")
        lignes.append(f"  {sym}: {val:.0f} EUR @ {prix:.4f}")
        lignes.append(f"    stratégie: {strategie}, ouvert: {ouvert}")
    
    return "\n".join(lignes)


def _reponse_trades():
    """Répond avec les trades récents."""
    data = _charger_paper()
    if not data:
        return "Portefeuille illisible."
    
    trades = data.get("trades_fermes", [])
    if not trades:
        return "Aucun trade fermé pour l'instant."
    
    recents = trades[-10:]  # 10 derniers
    lignes = [f"Trades récents ({len(recents)} derniers sur {len(trades)}):", ""]
    
    for t in reversed(recents):
        sym = t.get("symbole", "?")
        gain = t.get("gain_eur", t.get("pnl", 0))
        raison = t.get("raison", "?")
        emoji = "✅" if gain > 0 else "❌"
        lignes.append(f"  {emoji} {sym}: {gain:+.2f} EUR — {raison[:50]}")
    
    gagnants = sum(1 for t in trades if t.get("gain_eur", t.get("pnl", 0)) > 0)
    wr = (gagnants / len(trades) * 100) if trades else 0
    pnl_total = sum(t.get("gain_eur", t.get("pnl", 0)) for t in trades)
    
    lignes.append("")
    lignes.append(f"Win rate: {wr:.0f}% ({gagnants}W / {len(trades) - gagnants}L)")
    lignes.append(f"P&L trades: {pnl_total:+.2f} EUR")
    
    return "\n".join(lignes)


def _reponse_erreurs():
    """Vérifie les erreurs dans les logs."""
    logs = _lire_logs(100)
    
    sl_retard = logs.count("SL-RETARD")
    erreurs_429 = logs.count("429")
    crash = logs.count("Traceback") + logs.count("Error")
    
    if sl_retard == 0 and erreurs_429 == 0 and crash == 0:
        return "✅ Aucune erreur détectée dans les logs récents.\n\nLe bot tourne proprement."
    
    lignes = ["Erreurs détectées:", ""]
    if sl_retard:
        lignes.append(f"  ⚠️ SL-RETARD: {sl_retard} dans les logs récents")
    if erreurs_429:
        lignes.append(f"  ⚠️ Rate limit 429: {erreurs_429}")
    if crash:
        lignes.append(f"  🚨 Crash/erreur: {crash}")
    
    return "\n".join(lignes)


def _reponse_winrate():
    """Répond avec les statistiques de performance."""
    data = _charger_paper()
    if not data:
        return "Portefeuille illisible."
    
    trades = data.get("trades_fermes", [])
    if not trades:
        return "Pas encore assez de trades pour calculer le win rate."
    
    gagnants = [t for t in trades if t.get("gain_eur", t.get("pnl", 0)) > 0]
    perdants = [t for t in trades if t.get("gain_eur", t.get("pnl", 0)) <= 0]
    wr = (len(gagnants) / len(trades) * 100) if trades else 0
    
    gain_moyen = sum(t.get("gain_eur", t.get("pnl", 0)) for t in gagnants) / max(1, len(gagnants))
    perte_moyenne = sum(t.get("gain_eur", t.get("pnl", 0)) for t in perdants) / max(1, len(perdants))
    pnl_total = sum(t.get("gain_eur", t.get("pnl", 0)) for t in trades)
    
    # Raerais de fermeture
    raisons = {}
    for t in trades:
        r = t.get("raison", "autre")
        raisons[r] = raisons.get(r, 0) + 1
    top_raisons = sorted(raisons.items(), key=lambda x: -x[1])[:5]
    
    lignes = [
        f"Performance — {len(trades)} trades",
        f"",
        f"Win rate: {wr:.0f}%",
        f"Gagnants: {len(gagnants)} (gain moyen: {gain_moyen:+.2f} EUR)",
        f"Perdants: {len(perdants)} (perte moyenne: {perte_moyenne:+.2f} EUR)",
        f"P&L total: {pnl_total:+.2f} EUR",
        f"",
        f"Motifs de fermeture:",
    ]
    for r, n in top_raisons:
        lignes.append(f"  {r}: {n}x")
    
    return "\n".join(lignes)


def _reponse_capital():
    """Répond avec le capital et les liquidités."""
    data = _charger_paper()
    if not data:
        return "Portefeuille illisible."
    
    capital = data.get("capital_initial", 1000)
    liquidites = data.get("liquidites", 0)
    positions = data.get("positions", [])
    valeur_pos = sum(p.get("montant_eur", 0) for p in positions)
    total = liquidites + valeur_pos
    
    pct_investi = (valeur_pos / total * 100) if total else 0
    pct_liquide = (liquidites / total * 100) if total else 0
    
    lignes = [
        f"Capital: {total:.2f} EUR",
        f"",
        f"Liquidités: {liquidites:.2f} EUR ({pct_liquide:.0f}%)",
        f"Investi: {valeur_pos:.2f} EUR ({pct_investi:.0f}%)",
        f"Plancher liquidité: 200 EUR",
    ]
    
    if liquidites < 200:
        lignes.append("⚠️ Liquidités sous le plancher de 200 EUR!")
    
    return "\n".join(lignes)


def _reponse_restart():
    """Redémarre le service."""
    out, code = _run("sudo systemctl restart paper_trading.service")
    time.sleep(3)
    out2, _ = _run("systemctl is-active paper_trading.service")
    if out2 == "active":
        return "✅ Bot redémarré avec succès. Le service est actif."
    else:
        return "❌ Échec du redémarrage. Vérifie avec: python3 scanner_bot.py"


def _reponse_scanner():
    """Lance le scanner."""
    out, code = _run(f"cd {DOSSIER} && python3 scanner_bot.py")
    # Prend les 40 dernières lignes
    lignes = out.split("\n")
    return "\n".join(lignes[-40:])


def _reponse_analyse(message):
    """Analyse un actif spécifique."""
    msg = message.upper()
    symboles = {
        "BTC": "BTCUSDT", "BITCOIN": "BTCUSDT",
        "ETH": "ETHUSDT", "ETHEREUM": "ETHUSDT",
        "SOL": "SOLUSDT", "SOLANA": "SOLUSDT",
        "BNB": "BNBUSDT", "XRP": "XRPUSDT",
        "DOGE": "DOGEUSDT", "AVAX": "AVAXUSDT",
        "LINK": "LINKUSDT", "NEAR": "NEARUSDT",
        "FET": "FETUSDT", "ARB": "ARBUSDT",
    }
    
    sym = None
    for key, val in symboles.items():
        if key in msg:
            sym = val
            break
    
    if not sym:
        return "Quel actif veux-tu que j'analyse ? (BTC, ETH, SOL, BNB, XRP, DOGE, AVAX, LINK, NEAR, FET, ARB)"
    
    # Récupère le prix
    out, _ = _run(f"cd {DOSSIER} && python3 -c \"from prix_revolut import get_prix; print(get_prix('{sym}'))\"")
    
    return f"Analyse {sym}:\nPrix actuel: {out}\n\nPour une analyse complète, regarde le dashboard: http://51.38.227.237:8765/positions?token=LlVcM309UvV0aZMsUGl4FA"


def _reponse_aide():
    """Affiche l'aide."""
    lignes = [
        "🤖 Agent IA — Commandes en langage naturel",
        "",
        "Tu peux me demander:",
        "  'Comment va mon portefeuille ?'",
        "  'Quelles positions sont ouvertes ?'",
        "  'Montre-moi les trades récents'",
        "  'Quel est le win rate ?'",
        "  'Y a-t-il des erreurs ?'",
        "  'Combien de liquidités ?'",
        "  'Redémarre le bot'",
        "  'Lance un scan'",
        "  'Analyse BTC'",
        "",
        "Je comprends le langage naturel, pas besoin de commandes exactes.",
    ]
    return "\n".join(lignes)


def _traiter_message(message):
    """Traite un message et retourne la réponse."""
    intention = _comprendre(message)
    
    responses = {
        "status": _reponse_status,
        "positions": _reponse_positions,
        "trades": _reponse_trades,
        "erreurs": _reponse_erreurs,
        "winrate": _reponse_winrate,
        "capital": _reponse_capital,
        "restart": _reponse_restart,
        "scanner": _reponse_scanner,
        "analyse": lambda: _reponse_analyse(message),
        "aide": _reponse_aide,
    }
    
    if intention in responses:
        try:
            return responses[intention]()
        except Exception as e:
            return f"Erreur lors du traitement: {e}"
    elif intention == "inconnu":
        # Essaie avec Gemini si disponible
        return _reponse_gemini_fallback(message)
    
    return "Je n'ai pas compris. Tape 'aide' pour voir ce que je peux faire."


def _reponse_gemini_fallback(message):
    """Si l'intention est inconnue, utilise Gemini pour répondre."""
    # Vérifie d'abord si c'est une question non-trading
    msg_lower = message.lower()
    sujets_non_trading = ["météo", "meteo", "temps à", "restaurant", "film", "musique", "blague", "recette", "voyage", "sport", "news", "actualité"]
    if any(s in msg_lower for s in sujets_non_trading):
        return "Je gère uniquement le trading crypto et ton bot. Pose-moi une question sur ton portefeuille, tes positions, ou le marché. Tape 'aide' pour voir ce que je peux faire."
    
    try:
        import requests
        key = os.getenv("GEMINI_API_KEY", "")
        if not key:
            # Recharge depuis .env
            env_path = os.path.join(DOSSIER, ".env")
            if os.path.exists(env_path):
                with open(env_path) as f:
                    for line in f:
                        line = line.strip()
                        if line.startswith("GEMINI_API_KEY="):
                            key = line.split("=", 1)[1].strip()
                            break
        
        if not key:
            return "Je n'ai pas compris ta demande. Tape 'aide' pour voir ce que je peux faire."
        
        # Contexte du portefeuille
        data = _charger_paper()
        contexte = ""
        if data:
            positions = data.get("positions", [])
            trades = data.get("trades_fermes", [])
            liquidites = data.get("liquidites", 0)
            contexte = f"Contexte: {len(positions)} positions ouvertes, {len(trades)} trades fermés, {liquidites:.0f} EUR liquidités."
        
        prompt = f"""Tu es un assistant de trading crypto. Réponds brièvement en français.
{contexte}
Question de l'utilisateur: {message}

Si la question ne concerne pas le trading ou le bot, réponds que tu ne gères que le trading.
Réponds en 2-3 phrases maximum."""
        
        # Essaie plusieurs modèles Gemini
        modeles = ["gemini-2.5-flash", "gemini-2.0-flash", "gemini-1.5-flash-latest"]
        for modele in modeles:
            try:
                url = f"https://generativelanguage.googleapis.com/v1beta/models/{modele}:generateContent?key={key}"
                r = requests.post(url, json={"contents": [{"parts": [{"text": prompt}]}]}, timeout=30)
                if r.status_code == 200:
                    return r.json()["candidates"][0]["content"]["parts"][0]["text"][:500]
                elif r.status_code == 401:
                    continue  # Essaie le modèle suivant
                elif r.status_code == 404:
                    continue  # Modèle non trouvé
                else:
                    continue
            except Exception:
                continue
    except Exception:
        pass
    
    return "Je n'ai pas compris ta demande. Tape 'aide' pour voir ce que je peux faire."


# ============================================
# BOUCLE DE POLLING TELEGRAM
# ============================================

def boucle():
    """Boucle principale: poll Telegram et répond aux messages."""
    global _last_update_id
    
    if not TELEGRAM_TOKEN or not TELEGRAM_CHAT:
        print("[CHAT] Erreur: TELEGRAM_BOT_TOKEN ou TELEGRAM_CHAT_ID manquant dans .env")
        return
    
    print(f"[CHAT] Démarré — écoute des messages Telegram")
    _telegram_send("🤖 Conversation naturelle activée. Tu peux me poser des questions en langage naturel. Tape 'aide' pour voir ce que je peux faire.")
    
    while True:
        try:
            import requests
            # Poll Telegram (long polling 30s)
            params = {"timeout": 30}
            if _last_update_id:
                params["offset"] = _last_update_id + 1
            
            r = requests.get(f"{API_URL}/getUpdates", params=params, timeout=35)
            
            if r.status_code != 200:
                time.sleep(5)
                continue
            
            updates = r.json().get("result", [])
            
            for update in updates:
                _last_update_id = update.get("update_id", _last_update_id)
                
                if "message" not in update:
                    continue
                
                msg = update["message"]
                chat_id = str(msg.get("chat", {}).get("id", ""))
                texte = msg.get("text", "").strip()
                
                # Ignore les messages d'autres chats
                if chat_id != TELEGRAM_CHAT:
                    continue
                
                if not texte:
                    continue
                
                # Anti-spam: max 1 message / 3s
                now = time.time()
                if chat_id in _cooldown and now - _cooldown[chat_id] < 3:
                    continue
                _cooldown[chat_id] = now
                
                print(f"[CHAT] Message reçu: {texte[:60]}")
                
                # Traite et répond
                reponse = _traiter_message(texte)
                
                # Telegram limite à 4096 caractères
                if len(reponse) > 4000:
                    reponse = reponse[:4000] + "\n... (tronqué)"
                
                _telegram_send(reponse)
                print(f"[CHAT] Réponse envoyée ({len(reponse)} chars)")
        
        except Exception as e:
            print(f"[CHAT] Erreur: {e}")
            time.sleep(10)


if __name__ == "__main__":
    boucle()
