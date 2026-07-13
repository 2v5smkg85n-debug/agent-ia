#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
TELEGRAM MONITOR — service non-invasif qui surveille paper_trading.json.
Envoie des alertes push sur iPhone:
  - Trade ouvert (nouvelle position)
  - Trade fermé (+/- gain EUR)
  - paper_trading.service DOWN / recover
  - Résumé capital quotidien

Aucune modification de paper_trading.py: lit juste le JSON.
Lancé comme service systemd (telegram_monitor.service).
"""
import os
import json
import time
import subprocess
from datetime import datetime

from dotenv import load_dotenv
from telegram_alerte import envoyer

load_dotenv()
DOSSIER = os.path.dirname(os.path.abspath(__file__))
FICHIER = os.path.join(DOSSIER, "paper_trading.json")
SERVICE = "paper_trading.service"
INTERVALLE = 60  # secondes
HEURE_DIGEST = 8   # résumé quotidien à 08:00 UTC


def charger():
    try:
        with open(FICHIER, "r") as f:
            return json.load(f)
    except Exception:
        return {}


def service_actif():
    try:
        r = subprocess.run(
            ["systemctl", "is-active", SERVICE],
            capture_output=True, text=True, timeout=5,
        )
        return r.stdout.strip() == "active"
    except Exception:
        return True  # ne spam pas en cas d'erreur systemctl


def cle_trade(t):
    return f"{t.get('date_fermeture','')}{t.get('symbole','')}{t.get('prix_sortie','')}"


def formater_ferme(t):
    gain = t.get("gain_eur", 0)
    var = t.get("variation_pct", 0)
    sym = t.get("symbole", "?")
    raison = t.get("raison", "")[:30]
    emoji = "🟢" if gain >= 0 else "🔴"
    return (
        f"{emoji} TRADE FERMÉ\n"
        f"  {sym} | {raison}\n"
        f"  Gain: {gain:+.2f}€ ({var:+.2f}%)\n"
        f"  {t.get('date_fermeture','')}"
    )


def formater_ouvert(p):
    sym = p.get("symbole", "?")
    prix = p.get("prix_entree", 0)
    montant = p.get("montant_eur", 0)
    raison = p.get("raison", p.get("signal_raison", ""))[:40]
    return (
        f"🔵 TRADE OUVERT\n"
        f"  {sym} @ {prix:.4f}\n"
        f"  Montant: {montant:.2f}€\n"
        f"  {raison}"
    )


def digest_quotidien(etat):
    capital = etat.get("capital", 0)
    nb_pos = len(etat.get("positions", []))
    fermes = etat.get("trades_fermes", [])
    gains = sum(t.get("gain_eur", 0) for t in fermes)
    nb_g = sum(1 for t in fermes if t.get("gain_eur", 0) >= 0)
    wr = nb_g / len(fermes) * 100 if fermes else 0
    msg = (
        f"📊 DIGEST QUOTIDIEN\n"
        f"  Capital: {capital:.2f}€\n"
        f"  Positions ouvertes: {nb_pos}\n"
        f"  Trades fermés: {len(fermes)} | Win rate: {wr:.0f}%\n"
        f"  P&L cumulé: {gains:+.2f}€"
    )
    envoyer(msg)


def main():
    print(f"Telegram monitor démarré — surveillance de {FICHIER}")
    # Test connexion
    from telegram_alerte import tester
    tester()

    etat = charger()
    # État initial: marque tous les trades existants comme déjà vus
    vus_fermes = set(cle_trade(t) for t in etat.get("trades_fermes", []))
    vus_ouverts = set(p.get("symbole", "") + str(p.get("date_ouverture", "")) for p in etat.get("positions", []))
    dernier_service = service_actif()
    dernier_digest = datetime.now().strftime("%Y-%m-%d")

    print(f"État initial: {len(vus_fermes)} trades fermés vus, service={'actif' if dernier_service else 'down'}")

    while True:
        try:
            time.sleep(INTERVALLE)
            etat = charger()

            # 1. Nouveaux trades fermés
            for t in etat.get("trades_fermes", []):
                cle = cle_trade(t)
                if cle and cle not in vus_fermes:
                    vus_fermes.add(cle)
                    envoyer(formater_ferme(t))
                    print(f"Alerte: trade fermé {t.get('symbole','?')}")

            # 2. Nouvelles positions ouvertes
            for p in etat.get("positions", []):
                cle = p.get("symbole", "") + str(p.get("date_ouverture", ""))
                if cle and cle not in vus_ouverts:
                    vus_ouverts.add(cle)
                    envoyer(formater_ouvert(p))
                    print(f"Alerte: trade ouvert {p.get('symbole','?')}")

            # Nettoie les positions fermées
            actuels = set(p.get("symbole", "") + str(p.get("date_ouverture", "")) for p in etat.get("positions", []))
            vus_ouverts &= actuels

            # 3. Health check service
            actif = service_actif()
            if actif != dernier_service:
                if not actif:
                    envoyer(f"⚠️ ALERTE: {SERVICE} DOWN")
                else:
                    envoyer(f"✅ {SERVICE} récupéré")
                dernier_service = actif

            # 4. Digest quotidien
            auj = datetime.now().strftime("%Y-%m-%d")
            heure = datetime.now().hour
            if auj != dernier_digest and heure >= HEURE_DIGEST:
                dernier_digest = auj
                digest_quotidien(etat)

        except KeyboardInterrupt:
            print("Arrêt.")
            break
        except Exception as e:
            print(f"Erreur boucle: {e}")
            time.sleep(60)


if __name__ == "__main__":
    main()
