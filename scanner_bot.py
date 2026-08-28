#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
SCANNER BOT - Diagnostic complet de l'agent de trading.

Vérifie:
1. État du service systemd
2. Santé du portefeuille (capital, positions, P&L)
3. Erreurs dans les logs (SL-RETARD, 429, crashes)
4. Performance des trades (win rate, frais, P&L)
5. Modules importés (8 agents, live, indicateurs)
6. Config (TP/SL/trail/ATR/params)
7. Prix Revolut X (spreads anormaux)
8. Fichiers critiques (JSON, .env, git)
9. Alertes Telegram
10. Dashboard

Usage: python3 scanner_bot.py
"""
import os
import sys
import json
import subprocess
import re
from datetime import datetime, timedelta
from collections import Counter

DOSSIER = os.path.dirname(os.path.abspath(__file__))
LOG_FILE = os.path.join(DOSSIER, "paper_trading.log")
LOG_ARCHIVE = os.path.join(DOSSIER, "paper_trading.log.1")
PF_FILE = os.path.join(DOSSIER, "paper_trading.json")

LIGNE = "=" * 60
PROBLEMES = []


def probleme(niveau, msg):
    PROBLEMES.append((niveau, msg))
    icon = "🔴" if niveau == "CRITIQUE" else "🟡" if niveau == "WARN" else "🔵"
    print(f"  {icon} [{niveau}] {msg}")


def ok(msg):
    print(f"  ✅ {msg}")


def info(msg):
    print(f"  ℹ️  {msg}")


def section(titre):
    print(f"\n{LIGNE}")
    print(f"  {titre}")
    print(LIGNE)


# ============================================
# 1. ÉTAT DU SERVICE
# ============================================
def check_service():
    section("1. ÉTAT DU SERVICE SYSTEMD")
    try:
        r = subprocess.run(["systemctl", "is-active", "paper_trading.service"],
                         capture_output=True, text=True, timeout=5)
        status = r.stdout.strip()
        if status == "active":
            ok("paper_trading.service: ACTIVE")
        else:
            probleme("CRITIQUE", f"paper_trading.service: {status.upper()}")
        # Uptime
        r2 = subprocess.run(["systemctl", "show", "paper_trading.service",
                           "--property=ActiveEnterTimestamp", "--value"],
                          capture_output=True, text=True, timeout=5)
        if r2.stdout.strip():
            info(f"Démarré: {r2.stdout.strip()}")
        # Memory
        r3 = subprocess.run(["systemctl", "show", "paper_trading.service",
                           "--property=MemoryCurrent", "--value"],
                          capture_output=True, text=True, timeout=5)
        mem = r3.stdout.strip()
        if mem and mem != "[not set]":
            mem_mb = int(mem) / 1024 / 1024
            if mem_mb > 100:
                probleme("WARN", f"RAM élevée: {mem_mb:.1f} MB")
            else:
                ok(f"RAM: {mem_mb:.1f} MB")
        # Dashboard
        r4 = subprocess.run(["systemctl", "is-active", "dashboard.service"],
                           capture_output=True, text=True, timeout=5)
        dstatus = r4.stdout.strip()
        if dstatus == "active":
            ok("dashboard.service: ACTIVE")
        else:
            probleme("WARN", f"dashboard.service: {dstatus.upper()}")
    except Exception as e:
        probleme("CRITIQUE", f"Impossible de vérifier systemd: {e}")


# ============================================
# 2. PORTEFEUILLE
# ============================================
def check_portefeuille():
    section("2. PORTEFEUILLE")
    if not os.path.exists(PF_FILE):
        probleme("CRITIQUE", "paper_trading.json introuvable")
        return None
    try:
        pf = json.load(open(PF_FILE))
    except Exception as e:
        probleme("CRITIQUE", f"paper_trading.json corrompu: {e}")
        return None

    capital = pf.get("liquidites", 0) + sum(p.get("montant_eur", 0) for p in pf.get("positions", []))
    capital_init = 1000.0
    pnl = capital - capital_init
    pnl_pct = (pnl / capital_init) * 100
    frais = pf.get("total_frais", 0)

    info(f"Capital: {capital:.2f} EUR (P&L: {pnl:+.2f} EUR / {pnl_pct:+.1f}%)")
    info(f"Liquidités: {pf.get('liquidites', 0):.2f} EUR")
    info(f"Positions ouvertes: {len(pf.get('positions', []))}")
    info(f"Frais payés: {frais:.2f} EUR")

    # Alertes
    if pnl < -5:
        probleme("WARN", f"P&L négatif: {pnl:+.2f} EUR")
    if frais > 15:
        probleme("WARN", f"Frais élevés: {frais:.2f} EUR (mangent les profits)")
    if len(pf.get("positions", [])) == 0:
        info("Aucune position ouverte")
    if pf.get("liquidites", 0) < 100:
        probleme("WARN", f"Liquidités faibles: {pf.get('liquidites', 0):.2f} EUR")

    # Détail positions
    for pos in pf.get("positions", []):
        sym = pos.get("symbole", "?")
        prix_e = pos.get("prix_entree", 0)
        montant = pos.get("montant_eur", 0)
        date_o = pos.get("date_ouverture", "?")
        info(f"  → {sym}: {montant:.2f} EUR @ {prix_e:.2f} (ouvert {date_o})")

    # Circuit breaker
    cb = pf.get("circuit_breaker", {})
    if isinstance(cb, dict):
        pertes = cb.get("consecutive_losses", pf.get("pertes_consecutives", 0))
    else:
        pertes = pf.get("pertes_consecutives", 0)
    if pertes >= 3:
        probleme("WARN", f"Circuit breaker actif: {pertes} pertes consécutives")
    else:
        ok(f"Circuit breaker: {pertes} pertes consécutives")

    # Trades fermés
    trades = pf.get("trades_fermes", pf.get("historique", []))
    info(f"Trades fermés: {len(trades)}")
    if trades:
        gains = sum(t.get("gain_eur", 0) for t in trades)
        gagnes = sum(1 for t in trades if t.get("gain_eur", 0) > 0)
        perdus = len(trades) - gagnes
        wr = (gagnes / len(trades) * 100) if trades else 0
        info(f"Win rate: {wr:.0f}% ({gagnes}W / {perdus}L)")
        info(f"P&L trades: {gains:+.2f} EUR")
        if wr < 40:
            probleme("WARN", f"Win rate faible: {wr:.0f}%")
        # Raisons de fermeture
        raisons = Counter(t.get("raison", "?") for t in trades)
        info("Raisons de fermeture:")
        for r, n in raisons.most_common(5):
            info(f"  {r}: {n}x")

    return pf


# ============================================
# 3. ERREURS DANS LES LOGS
# ============================================
def check_logs():
    section("3. ERREURS DANS LES LOGS")
    lignes = []
    for f in [LOG_FILE, LOG_ARCHIVE]:
        if os.path.exists(f):
            try:
                with open(f, "r", errors="replace") as fh:
                    lignes.extend(fh.readlines()[-500:])
            except Exception:
                pass

    if not lignes:
        probleme("WARN", "Aucun log trouvé")
        return

    # Compteurs d'erreurs
    sl_retard = 0
    erreurs_429 = 0
    erreurs_400 = 0
    crashes = 0
    prix_invalide = 0
    timeouts = 0
    live_exits = 0
    live_tighten = 0
    live_partial = 0
    cut_stagnation = 0
    sl_urgence = 0

    for ligne in lignes:
        if "SL-RETARD" in ligne:
            sl_retard += 1
        if "429" in ligne and ("error" in ligne.lower() or "rate" in ligne.lower()):
            erreurs_429 += 1
        if "400 Bad Request" in ligne:
            erreurs_400 += 1
        if "Traceback" in ligne or "Exception" in ligne:
            crashes += 1
        if "PRIX INVALIDE" in ligne:
            prix_invalide += 1
        if "WATCHDOG" in ligne or "TickTimeout" in ligne:
            timeouts += 1
        if "LIVE-EXIT" in ligne:
            live_exits += 1
        if "LIVE] " in ligne and "SL resserré" in ligne:
            live_tighten += 1
        if "LIVE-PARTIAL" in ligne:
            live_partial += 1
        if "CUT-STAGNATION" in ligne:
            cut_stagnation += 1
        if "SL-URGENCE" in ligne:
            sl_urgence += 1

    if sl_retard > 0:
        probleme("WARN", f"SL-RETARD: {sl_retard}x (prix gap entre checks)")
    else:
        ok("Aucun SL-RETARD")
    if erreurs_429 > 0:
        probleme("WARN", f"Erreurs 429 (rate limit): {erreurs_429}x")
    else:
        ok("Aucune erreur 429")
    if erreurs_400 > 0:
        probleme("WARN", f"Erreurs 400 (bad request): {erreurs_400}x")
    if crashes > 0:
        probleme("CRITIQUE", f"Crashes/exceptions: {crashes}x")
    else:
        ok("Aucun crash")
    if prix_invalide > 0:
        probleme("WARN", f"Prix invalides: {prix_invalide}x")
    if timeouts > 0:
        probleme("WARN", f"Timeouts watchdog: {timeouts}x")

    # Modules live
    if live_exits or live_tighten or live_partial:
        ok(f"Gestion live active: {live_exits} exits, {live_tighten} SL resserrés, {live_partial} partials")
    else:
        info("Gestion live: aucune action déclenchée (HOLD uniquement)")
    if cut_stagnation:
        ok(f"Cut-stagnation: {cut_stagnation}x (positions plates fermées)")
    if sl_urgence:
        info(f"SL-urgence: {sl_urgence}x (hard stop déclenché)")

    # Dernier tick
    for ligne in reversed(lignes):
        if "Dernier tick" in ligne:
            info(f"Dernier tick: {ligne.strip().split('Dernier tick:')[1].strip()}")
            break


# ============================================
# 4. MODULES
# ============================================
def check_modules():
    section("4. MODULES")
    modules = [
        ("agents_consensus", "Multi-agents IA (8 agents)"),
        ("gestion_position_live", "Gestion position live"),
        ("intelligence_pro", "Intelligence pro (MTF, Fear&Greed)"),
        ("indicateurs", "Indicateurs techniques (RSI, MACD, ATR)"),
        ("prix_revolut", "Prix Revolut X"),
        ("gestion_risque", "Gestion du risque (sizing)"),
        ("master_traders", "Master traders consensus"),
        ("ml_filtre", "Filtre ML"),
        ("sentiment_marche", "Sentiment marché"),
        ("trader_pro", "Trader pro (score multi-facteurs)"),
        ("rotation_logs", "Rotation des logs"),
    ]
    for mod, desc in modules:
        path = os.path.join(DOSSIER, f"{mod}.py")
        if os.path.exists(path):
            try:
                # Test import
                spec = __import__(mod)
                ok(f"{desc}: OK")
            except Exception as e:
                probleme("WARN", f"{desc}: erreur import ({e})")
        else:
            probleme("WARN", f"{desc}: fichier manquant ({mod}.py)")


# ============================================
# 5. CONFIG
# ============================================
def check_config():
    section("5. CONFIGURATION")
    try:
        # Lit la config avec grep au lieu d'importer (évite les dépendances manquantes)
        r = subprocess.run(["python3", "-c", f"""
import re
with open('{DOSSIER}/paper_trading.py') as f:
    code = f.read()
consts = [
    'TAKE_PROFIT_PCT', 'STOP_LOSS_PCT', 'TRAIL_ACTIF', 'TRAIL_PCT',
    'MAX_TRADES_PAR_JOUR', 'MAX_POSITIONS', 'INTERVALLE_BOUCLE',
    'STALE_DUREE_MAX', 'BREAKEVEN_SEUIL', 'PARTIAL_TP_SEUIL',
    'SEUIL_BENEFICE_MIN', 'STAGNATION_PERTE_SEUIL', 'STAGNATION_PERTE_DUREE',
    'ATR_LOOKBACK', 'ATR_TP_MULT', 'ATR_TP_MIN', 'ATR_TP_MAX',
    'CIRCUIT_BREAKER_CONSECUTIF'
]
for c in consts:
    m = re.search(rf'^{{c}}\s*=\s*([0-9.]+)', code, re.MULTILINE)
    if m:
        print(f"{{c}}={{m.group(1)}}")
"""], capture_output=True, text=True, timeout=10)
        if r.returncode == 0:
            for ligne in r.stdout.strip().split("\n"):
                if "=" in ligne:
                    info(ligne)
            # Vérifications
            config = dict(l.split("=", 1) for l in r.stdout.strip().split("\n") if "=" in l)
            if float(config.get("TAKE_PROFIT_PCT", 0)) > 5:
                probleme("WARN", f"TP très élevé: {config['TAKE_PROFIT_PCT']}%")
            if float(config.get("STOP_LOSS_PCT", 0)) > 2:
                probleme("WARN", f"SL large: {config['STOP_LOSS_PCT']}%")
            if int(config.get("MAX_TRADES_PAR_JOUR", 0)) > 50:
                probleme("WARN", f"Max trades élevé: {config['MAX_TRADES_PAR_JOUR']}")
            ok("Config lue avec succès")
        else:
            probleme("WARN", f"Impossible de lire la config: {r.stderr[:200]}")
    except Exception as e:
        probleme("WARN", f"Check config erreur: {e}")


# ============================================
# 6. SPREADS REVOLUT X
# ============================================
def check_spreads():
    section("6. SPREADS REVOLUT X")
    try:
        sys.path.insert(0, DOSSIER)
        from prix_revolut import SPREAD_BLACKLIST, BLACKLIST, get_prix_secours
        info(f"Blacklist complète: {sorted(BLACKLIST)}")
        info(f"Spread blacklist: {sorted(SPREAD_BLACKLIST)}")
        # Test quelques prix
        test_syms = ["BTCUSDT", "ETHUSDT", "SOLUSDT", "XRPUSDT", "DOGEUSDT", "AVAXUSDT", "LINKUSDT"]
        for sym in test_syms:
            prix = get_prix_secours(sym)
            if prix and prix > 0:
                ok(f"{sym}: {prix:.4f}")
            else:
                probleme("WARN", f"{sym}: prix indisponible")
    except Exception as e:
        probleme("WARN", f"Check spreads erreur: {e}")


# ============================================
# 7. FICHIERS CRITIQUES
# ============================================
def check_fichiers():
    section("7. FICHIERS CRITIQUES")
    critiques = [
        "paper_trading.json",
        ".env",
        "classement_strategies.json",
        "top_cryptos.json",
    ]
    for f in critiques:
        path = os.path.join(DOSSIER, f)
        if os.path.exists(path):
            taille = os.path.getsize(path)
            if taille > 10 * 1024 * 1024:
                probleme("WARN", f"{f}: {taille // 1024 // 1024} MB (trop gros)")
            else:
                ok(f"{f}: {taille // 1024} KB")
        else:
            if f == ".env":
                probleme("CRITIQUE", f"{f}: MANQUANT (clés API absentes)")
            else:
                info(f"{f}: absent (optionnel)")

    # Taille du log
    for f in [LOG_FILE, LOG_ARCHIVE]:
        if os.path.exists(f):
            taille = os.path.getsize(f)
            if taille > 5 * 1024 * 1024:
                probleme("WARN", f"{f}: {taille // 1024 // 1024} MB (rotation needed)")
            else:
                info(f"{f}: {taille // 1024} KB")

    # Git status
    try:
        r = subprocess.run(["git", "-C", DOSSIER, "log", "--oneline", "-3"],
                         capture_output=True, text=True, timeout=5)
        if r.returncode == 0:
            info("Derniers commits:")
            for ligne in r.stdout.strip().split("\n"):
                info(f"  {ligne}")
    except Exception:
        pass


# ============================================
# 8. DASHBOARD
# ============================================
def check_dashboard():
    section("8. DASHBOARD")
    try:
        r = subprocess.run(["curl", "-s", "-o", "/dev/null", "-w", "%{http_code}",
                          "http://localhost:8765/?token=LlVcM309UvV0aZMsUGl4FA"],
                         capture_output=True, text=True, timeout=5)
        code = r.stdout.strip()
        if code == "200":
            ok("Dashboard répond (HTTP 200)")
        else:
            probleme("WARN", f"Dashboard: HTTP {code}")
    except Exception as e:
        probleme("WARN", f"Dashboard inaccessible: {e}")


# ============================================
# 9. TELEGRAM
# ============================================
def check_telegram():
    section("9. TELEGRAM")
    try:
        # Lit .env manuellement (pas de dépendance dotenv)
        env = {}
        env_path = os.path.join(DOSSIER, ".env")
        if os.path.exists(env_path):
            for ligne in open(env_path):
                ligne = ligne.strip()
                if "=" in ligne and not ligne.startswith("#"):
                    k, v = ligne.split("=", 1)
                    env[k.strip()] = v.strip()
        token = env.get("TELEGRAM_BOT_TOKEN", "")
        chat = env.get("TELEGRAM_CHAT_ID", "")
        if token and chat:
            ok(f"Token: {token[:10]}... | Chat: {chat}")
            # Test envoi
            r = subprocess.run(["curl", "-s", "-o", "/dev/null", "-w", "%{http_code}",
                              f"https://api.telegram.org/bot{token}/getMe"],
                             capture_output=True, text=True, timeout=10)
            code = r.stdout.strip()
            if code == "200":
                ok("Bot Telegram: en ligne")
            else:
                probleme("WARN", f"Bot Telegram: HTTP {code}")
        else:
            probleme("WARN", "Telegram: token ou chat ID manquant")
    except Exception as e:
        probleme("WARN", f"Telegram check erreur: {e}")


# ============================================
# 10. RÉSUMÉ
# ============================================
def resume():
    section("RÉSUMÉ DU SCAN")
    if not PROBLEMES:
        print("  ✅ AUCUN PROBLÈME DÉTECTÉ — Le bot fonctionne parfaitement")
        return 0

    critiques = [p for n, p in PROBLEMES if n == "CRITIQUE"]
    warns = [p for n, p in PROBLEMES if n == "WARN"]
    infos = [p for n, p in PROBLEMES if n == "INFO"]

    print(f"  🔴 Critiques: {len(critiques)}")
    for p in critiques:
        print(f"    → {p}")
    print(f"  🟡 Warnings: {len(warns)}")
    for p in warns:
        print(f"    → {p}")

    if critiques:
        print(f"\n  ⚠️  {len(critiques)} problème(s) critique(s) à corriger en priorité")
        return 2
    elif warns:
        print(f"\n  ⚠️  {len(warns)} warning(s) à surveiller")
        return 1
    else:
        return 0


# ============================================
# MAIN
# ============================================
def main():
    print(LIGNE)
    print(f"  SCANNER BOT — {datetime.now().strftime('%Y-%m-%d %H:%M')}")
    print(LIGNE)

    check_service()
    pf = check_portefeuille()
    check_logs()
    check_modules()
    check_config()
    check_spreads()
    check_fichiers()
    check_dashboard()
    check_telegram()
    code = resume()

    sys.exit(code)


if __name__ == "__main__":
    main()
