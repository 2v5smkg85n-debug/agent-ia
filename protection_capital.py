#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""protection_capital.py — Circuit breaker: protège le capital en suspendant
les nouvelles entrées en cas de drawdown profond ou de pertes consécutives.

LEÇON #1 de la mémoire du marché: "survis aux bears" (BTC -83%, ETH -94%).
Avant le vrai argent, il faut un filet de sécurité automatique.

Déclencheurs:
  - drawdown >= 12% depuis le peak du portefeuille -> pause
  - >= 5 pertes consécutives (trades fermés) -> pause
  - auto-resume (paper) quand drawdown < 6% ET plus de pertes consécutives

État persisté dans protection_capital.json (peak, paused, raison, last_alert).
Alerte Telegram throttlée (1x/h max) sur transition pause.

Intégration: ouvrir_position appelle verifier_pause(pf) au tout début;
si True, skip l'entrée. Toggle: PROTECTION_CAPITAL=0 pour désactiver."""
import os
import json
import time
from datetime import datetime

DOSSIER = os.path.dirname(os.path.abspath(__file__))
STATE_FILE = os.path.join(DOSSIER, "protection_capital.json")
PAPER_FILE = os.path.join(DOSSIER, "paper_trading.json")
TELEGRAM_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN", "")
TELEGRAM_CHAT = os.getenv("TELEGRAM_CHAT_ID", "")

MAX_DRAWDOWN = 0.12      # 12% drawdown -> pause
MAX_PERTES = 5           # 5 pertes consecutives -> pause
RESUME_DRAWDOWN = 0.06   # auto-resume si drawdown < 6%


def _load():
    try:
        with open(STATE_FILE) as f:
            return json.load(f)
    except Exception:
        return {"peak": 0, "paused": False, "raison": "", "last_alert": 0,
                "consecutive_losses": 0}


def _save(s):
    try:
        with open(STATE_FILE, "w") as f:
            json.dump(s, f, indent=2)
    except Exception:
        pass


def _valeur_portefeuille(pf):
    return pf.get("liquidites", 0) + sum(p.get("montant_eur", 0) for p in pf.get("positions", []))


def _pertes_consecutives(pf):
    """Compte les pertes consécutives en partant du dernier trade fermé."""
    fermes = pf.get("trades_fermes", [])
    n = 0
    for t in reversed(fermes):
        try:
            gain = t.get("gain_eur", 0)
            if gain is None:
                gain = t.get("variation_pct", 0)
            if gain < 0:
                n += 1
            else:
                break
        except Exception:
            break
    return n


def _alerter(raison):
    if not TELEGRAM_TOKEN or not TELEGRAM_CHAT:
        return
    try:
        import requests
        msg = (f"🛑 CIRCUIT BREAKER ACTIVÉ\n\n"
               f"Entrées suspendues: {raison}\n\n"
               f"Le système protège le capital. Reprise auto quand conditions s'améliorent "
               f"(drawdown < 6% et plus de pertes consécutives).")
        requests.post(f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage",
                      json={"chat_id": TELEGRAM_CHAT, "text": msg}, timeout=10)
    except Exception:
        pass


def verifier_pause(pf):
    """Vérifie si le trading doit être suspendu. Retourne (pause_bool, raison_str).
    Met à jour l'état persisté + alerte Telegram (throttlée)."""
    s = _load()
    val = _valeur_portefeuille(pf)
    cap = pf.get("capital_initial", 1000)
    # Maj du peak
    if val > s.get("peak", 0):
        s["peak"] = val
    peak = max(s.get("peak", 0), cap)
    dd = (peak - val) / peak if peak > 0 else 0
    pertes = _pertes_consecutives(pf)
    s["consecutive_losses"] = pertes
    was_paused = s.get("paused", False)
    nouveau_pause = False
    raison = ""
    if dd >= MAX_DRAWDOWN:
        raison = f"drawdown {dd*100:.1f}% (seuil {MAX_DRAWDOWN*100:.0f}%)"
        if not was_paused:
            nouveau_pause = True
        s["paused"] = True
        s["raison"] = raison
    elif pertes >= MAX_PERTES:
        raison = f"{pertes} pertes consecutives (seuil {MAX_PERTES})"
        if not was_paused:
            nouveau_pause = True
        s["paused"] = True
        s["raison"] = raison
    elif dd < RESUME_DRAWDOWN and pertes == 0 and was_paused:
        # Auto-resume (paper): conditions améliorées
        s["paused"] = False
        s["raison"] = ""
        _save(s)
        return False, ""
    _save(s)
    # Alerte Telegram (throttlée 1/h)
    if s.get("paused") and (nouveau_pause or time.time() - s.get("last_alert", 0) > 3600):
        _alerter(s.get("raison", ""))
        s["last_alert"] = time.time()
        _save(s)
    return s.get("paused", False), s.get("raison", "")


def etat_display():
    """Retourne un résumé lisible de l'état de protection (pour digests)."""
    s = _load()
    try:
        pf = json.load(open(PAPER_FILE))
        val = _valeur_portefeuille(pf)
        cap = pf.get("capital_initial", 1000)
        peak = max(s.get("peak", 0), cap)
        dd = (peak - val) / peak * 100 if peak > 0 else 0
        pertes = _pertes_consecutives(pf)
    except Exception:
        val = dd = pertes = 0
    statut = "🛑 PAUSE" if s.get("paused") else "✅ ACTIF"
    return (f"Protection capital: {statut} | valeur {val:.2f}€ | drawdown {dd:.1f}% "
            f"(seuil {MAX_DRAWDOWN*100:.0f}%) | pertes consecutives {pertes}/{MAX_PERTES}")


if __name__ == "__main__":
    print("=" * 60)
    print("PROTECTION DU CAPITAL (circuit breaker)")
    print("=" * 60)
    try:
        pf = json.load(open(PAPER_FILE))
        pause, raison = verifier_pause(pf)
        print(f"Valeur portefeuille: {_valeur_portefeuille(pf):.2f}€")
        print(f"Peak enregistré: {_load().get('peak', 0):.2f}€")
        print(f"Pertes consecutives: {_pertes_consecutives(pf)}")
        print(f"Statut: {'🛑 PAUSE — ' + raison if pause else '✅ ACTIF (entrées autorisées)'}")
        print()
        print(etat_display())
    except Exception as e:
        print(f"Erreur: {e}")
