#!/usr/bin/env python3
"""
Watchdog — Auto-réparation continue (comme Perplexity Computer).

Surveille le bot de trading et répare automatiquement les problèmes:
1. Service paper_trading arrêté → redémarre
2. Log stale (pas d'écriture depuis >10min) → redémarre
3. JSON corrompu (paper_trading.json) → restaure backup
4. Circuit breaker bloqué (3+ pertes) → reset
5. SL-RETARD détecté dans les logs → alerte Telegram
6. Dashboard down → redémarre
7. Espace disque <10% → nettoie vieux logs
8. RAM >90% → alerte

Boucle toutes les 60s. Envoie alertes Telegram sur chaque réparation.
Ne modifie jamais le code — ne fait que restart/restore/reset.
"""

import os
import sys
import json
import time
import subprocess
import shutil
from pathlib import Path

DOSSIER = os.path.expanduser("~/agent-ia")
LOG_FILE = os.path.join(DOSSIER, "paper_trading.log")
JSON_FILE = os.path.join(DOSSIER, "paper_trading.json")
WATCHDOG_LOG = os.path.join(DOSSIER, "watchdog.log")
INTERVALLE = 60  # 60s
STALE_SEUIL = 600  # 10min sans log = stale
TELEGRAM_TOKEN = None
TELEGRAM_CHAT = None

# Charger les clés Telegram depuis .env
def _load_telegram():
    global TELEGRAM_TOKEN, TELEGRAM_CHAT
    env_path = os.path.join(DOSSIER, ".env")
    if os.path.exists(env_path):
        with open(env_path) as f:
            for line in f:
                line = line.strip()
                if line.startswith("TELEGRAM_BOT_TOKEN="):
                    TELEGRAM_TOKEN = line.split("=", 1)[1].strip()
                elif line.startswith("TELEGRAM_CHAT_ID="):
                    TELEGRAM_CHAT = line.split("=", 1)[1].strip()

_load_telegram()


def _log(msg):
    """Log avec timestamp."""
    ts = time.strftime("%Y-%m-%d %H:%M:%S")
    line = f"[{ts}] {msg}"
    print(line, flush=True)
    try:
        with open(WATCHDOG_LOG, "a") as f:
            f.write(line + "\n")
    except Exception:
        pass


def _telegram(msg):
    """Envoie une alerte Telegram."""
    if not TELEGRAM_TOKEN or not TELEGRAM_CHAT:
        return
    try:
        import urllib.request
        url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage"
        data = json.dumps({"chat_id": TELEGRAM_CHAT, "text": msg, "parse_mode": None}).encode()
        req = urllib.request.Request(url, data=data, headers={"Content-Type": "application/json"})
        urllib.request.urlopen(req, timeout=10)
    except Exception:
        pass


def _run(cmd):
    """Exécute une commande shell, retourne (stdout, returncode)."""
    try:
        r = subprocess.run(cmd, shell=True, capture_output=True, text=True, timeout=30)
        return r.stdout.strip(), r.returncode
    except Exception as e:
        return str(e), 1


# ============================================
# CHECKS ET RÉPARATIONS
# ============================================

def check_service():
    """Check 1: paper_trading.service actif ?"""
    out, code = _run("systemctl is-active paper_trading.service")
    if code != 0 or out != "active":
        _log("ALERT: paper_trading.service INACTIF — redémarrage...")
        # Apprentissage: cherche si une solution connue existe
        try:
            from apprentissage_session import chercher_solution, enregistrer_solution, incrementer_stat
            sol = chercher_solution("Service crash")
            if sol and sol.get("succes_rate", 0) >= 70:
                _log(f"  Solution connue (freq {sol.get('frequence',0)}): {sol.get('solution','')[:60]}")
            incrementer_stat("Service crash", auto=True)
        except Exception:
            pass
        _run("sudo systemctl restart paper_trading.service")
        time.sleep(5)
        out2, _ = _run("systemctl is-active paper_trading.service")
        if out2 == "active":
            _log("OK: service redémarré avec succès")
            _telegram("🔧 WATCHDOG: paper_trading.service redémarré automatiquement")
            try:
                enregistrer_solution("Service crash", "sudo systemctl restart paper_trading.service")
            except Exception:
                pass
        else:
            _log("CRITICAL: échec redémarrage service!")
            _telegram("🚨 WATCHDOG CRITICAL: échec redémarrage paper_trading.service!")
            try:
                from apprentissage_session import enregistrer_echec
                enregistrer_echec("Service crash")
            except Exception:
                pass
        return False
    return True


def check_log_stale():
    """Check 2: Log stale (pas d'écriture depuis >10min) ?"""
    if not os.path.exists(LOG_FILE):
        return True
    age = time.time() - os.path.getmtime(LOG_FILE)
    if age > STALE_SEUIL:
        _log(f"ALERT: log stale ({age:.0f}s sans écriture) — redémarrage...")
        _run("sudo systemctl restart paper_trading.service")
        time.sleep(5)
        _telegram(f"🔧 WATCHDOG: log stale ({age:.0f}s), service redémarré")
        return False
    return True


def check_json_corrompu():
    """Check 3: paper_trading.json corrompu ?"""
    if not os.path.exists(JSON_FILE):
        return True
    try:
        with open(JSON_FILE) as f:
            data = json.load(f)
        # Vérifications minimales
        if not isinstance(data, dict):
            raise ValueError("pas un dict")
        if "capital_initial" not in data and "positions" not in data:
            raise ValueError("clés manquantes")
        return True
    except Exception as e:
        _log(f"ALERT: JSON corrompu ({e}) — recherche backup...")
        # Apprentissage: cherche la solution connue
        try:
            from apprentissage_session import chercher_solution, enregistrer_solution, incrementer_stat
            sol = chercher_solution("JSON corrompu")
            if sol:
                _log(f"  Solution connue: {sol.get('solution','')[:60]}")
            incrementer_stat("JSON corrompu", auto=True)
        except Exception:
            pass
        # Cherche un backup
        backups = sorted(Path(DOSSIER).glob("paper_trading.json.bak*"))
        if backups:
            backup = str(backups[-1])
            _log(f"Restauration depuis {backup}")
            shutil.copy2(backup, JSON_FILE)
            _telegram(f"🔧 WATCHDOG: paper_trading.json corrompu, restauré depuis {backup}")
            try:
                enregistrer_solution("JSON corrompu", f"Restore backup {backup}")
            except Exception:
                pass
        else:
            # Crée un JSON minimal valide
            _log("Aucun backup — création JSON minimal")
            minimal = {
                "capital_initial": 1000.0,
                "liquidites": 1000.0,
                "positions": [],
                "trades_fermes": [],
                "frais_totaux": 0.0,
                "circuit_breaker": {"consecutive_losses": 0},
                "pertes_consecutives": 0,
                "date_demarrage": time.strftime("%Y-%m-%d %H:%M:%S"),
            }
            with open(JSON_FILE, "w") as f:
                json.dump(minimal, f, indent=2)
            _telegram("🔧 WATCHDOG: JSON corrompu sans backup, recréé minimal (1000€)")
            try:
                enregistrer_solution("JSON corrompu", "Recréer JSON minimal 1000€")
            except Exception:
                pass
        return False


def check_circuit_breaker():
    """Check 4: Circuit breaker bloqué ?"""
    if not os.path.exists(JSON_FILE):
        return True
    try:
        with open(JSON_FILE) as f:
            data = json.load(f)
        cb = data.get("circuit_breaker", {})
        pertes = data.get("pertes_consecutives", 0)
        consec = cb.get("consecutive_losses", 0) if isinstance(cb, dict) else 0
        if consec >= 3 or pertes >= 3:
            _log(f"ALERT: Circuit breaker actif ({consec} pertes consec) — reset...")
            try:
                from apprentissage_session import chercher_solution, enregistrer_solution, incrementer_stat
                sol = chercher_solution("Circuit breaker bloqué")
                if sol:
                    _log(f"  Solution connue: {sol.get('solution','')[:60]}")
                incrementer_stat("Circuit breaker bloqué", auto=True)
            except Exception:
                pass
            data["circuit_breaker"] = {"consecutive_losses": 0}
            data["pertes_consecutives"] = 0
            with open(JSON_FILE, "w") as f:
                json.dump(data, f, indent=2)
            _telegram("🔧 WATCHDOG: Circuit breaker reset (3+ pertes consecutives)")
            try:
                enregistrer_solution("Circuit breaker bloqué", "Reset pertes_consecutives=0")
            except Exception:
                pass
            return False
    except Exception:
        pass
    return True


def check_sl_retard():
    """Check 5: SL-RETARD dans les logs récents ?"""
    if not os.path.exists(LOG_FILE):
        return True
    try:
        # Lit les 200 dernières lignes
        out, _ = _run(f"tail -200 '{LOG_FILE}' | grep -c 'SL-RETARD'")
        count = int(out) if out.isdigit() else 0
        if count > 0:
            _log(f"ALERT: {count} SL-RETARD détectés dans les logs récents!")
            # Apprentissage: cherche la solution connue
            try:
                from apprentissage_session import chercher_solution, enregistrer_solution, incrementer_stat
                sol = chercher_solution("SL-RETARD")
                if sol:
                    _log(f"  Solution connue: {sol.get('solution','')[:60]}")
                incrementer_stat("SL-RETARD", auto=False)
            except Exception:
                pass
            _telegram(f"⚠️ WATCHDOG: {count} SL-RETARD détectés — vérifie les logs")
            return False
    except Exception:
        pass
    return True


def check_dashboard():
    """Check 6: Dashboard répond ?"""
    # Lit le token depuis .env
    token = ""
    env_path = os.path.join(DOSSIER, ".env")
    if os.path.exists(env_path):
        with open(env_path) as f:
            for line in f:
                if line.strip().startswith("DASHBOARD_TOKEN="):
                    token = line.split("=", 1)[1].strip()
                    break
    url = f"http://localhost:8765/?token={token}" if token else "http://localhost:8765/"
    out, code = _run(f"curl -s -o /dev/null -w '%{{http_code}}' '{url}' 2>/dev/null")
    if code != 0 or out not in ("200", "301", "302"):
        _log("ALERT: Dashboard down — redémarrage...")
        _run("sudo systemctl restart dashboard.service")
        time.sleep(3)
        out2, _ = _run(f"curl -s -o /dev/null -w '%{{http_code}}' '{url}' 2>/dev/null")
        if out2 in ("200", "301", "302"):
            _log("OK: dashboard redémarré")
            _telegram("🔧 WATCHDOG: dashboard.service redémarré")
        else:
            _log("WARNING: dashboard toujours down après restart")
        return False
    return True


def check_disque():
    """Check 7: Espace disque <10% ?"""
    out, _ = _run("df / | tail -1 | awk '{print $5}'")
    try:
        pct = int(out.replace("%", ""))
        if pct > 90:
            _log(f"ALERT: disque {pct}% plein — nettoyage...")
            # Nettoie vieux logs (>7 jours)
            _run(f"find {DOSSIER} -name '*.log.*' -mtime +7 -delete 2>/dev/null")
            _run(f"find /tmp -name '*.log' -mtime +3 -delete 2>/dev/null")
            _telegram(f"🔧 WATCHDOG: disque {pct}% plein, vieux logs nettoyés")
            return False
    except Exception:
        pass
    return True


def check_ram():
    """Check 8: RAM >90% ?"""
    out, _ = _run("free | awk '/Mem/ {printf \"%.0f\", $3/$2*100}'")
    try:
        pct = int(out)
        if pct > 90:
            _log(f"ALERT: RAM {pct}% utilisée")
            _telegram(f"⚠️ WATCHDOG: RAM {pct}% utilisée — risque de crash")
            return False
    except Exception:
        pass
    return True


def backup_json():
    """Crée un backup du JSON toutes les 30 min."""
    if not os.path.exists(JSON_FILE):
        return
    bak = JSON_FILE + ".bak"
    try:
        shutil.copy2(JSON_FILE, bak)
        # Garde seulement les 3 derniers backups
        baks = sorted(Path(DOSSIER).glob("paper_trading.json.bak*"), key=lambda p: p.stat().st_mtime)
        for old in baks[:-3]:
            old.unlink()
    except Exception:
        pass


# ============================================
# BOUCLE PRINCIPALE
# ============================================

_dernier_backup = 0
_dernier_etat = {}

def boucle():
    """Boucle principale du watchdog."""
    global _dernier_backup
    _log("Watchdog démarré — surveillance toutes les 60s")
    
    while True:
        try:
            etat = {}
            
            # Checks dans l'ordre de priorité
            etat["service"] = check_service()
            etat["log_stale"] = check_log_stale()
            etat["json"] = check_json_corrompu()
            etat["circuit_breaker"] = check_circuit_breaker()
            etat["sl_retard"] = check_sl_retard()
            etat["dashboard"] = check_dashboard()
            etat["disque"] = check_disque()
            etat["ram"] = check_ram()
            
            # Backup toutes les 30 min
            now = time.time()
            if now - _dernier_backup > 1800:
                backup_json()
                _dernier_backup = now
            
            # Résumé si tout va bien (toutes les 10 min)
            if all(etat.values()):
                _log(f"OK: tous les checks passent (service: actif, dashboard: OK, JSON: OK)")
            
        except Exception as e:
            _log(f"ERREUR watchdog: {e}")
        
        time.sleep(INTERVALLE)


if __name__ == "__main__":
    boucle()
