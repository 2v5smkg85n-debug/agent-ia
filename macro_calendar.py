#!/usr/bin/env python3
"""
macro_calendar.py — Calendrier macroéconomique pour l'agent IA.

Source: Forex Factory JSON feed (gratuit, sans API key).
Cache de 6h pour éviter les requêtes répétées.

Fonctions principales:
  - evenements_jour()          → événements d'aujourd'hui
  - evenements_proches(h=2)    → événements dans les prochaines h heures
  - evenement_proche(sym, h=2)  → True si un event High impact dans les h heures
  - gate_achat(symbole)        → True si OK pour acheter, False si bloqué
  - prochaines_evenements(n=5) → les N prochains événements (pour dashboard/digest)

Intégration:
  - paper_trading.py: gate avant ouverture position (MACRO_GATE=1)
  - dashboard: section calendrier
  - digest_quotidien: section événements du jour

Env vars:
  MACRO_GATE=1          → active le gate
  MACRO_GATE_HEURES=2   → fenêtre de blocage en heures (défaut 2)
  MACRO_GATE_IMPACT=High → impact minimum pour bloquer (High, Medium)
"""

import os
import json
import time
import logging
from datetime import datetime, timezone, timedelta
import requests

logger = logging.getLogger("macro_calendar")

# Feed Forex Factory (gratuit, sans clé)
FEED_URL = "https://nfs.faireconomy.media/ff_calendar_thisweek.json"
FEED_NEXT_URL = "https://nfs.faireconomy.media/ff_calendar_nextweek.json"

# Cache en mémoire
_CACHE = {"data": None, "ts": 0}
_CACHE_TTL = 6 * 3600  # 6 heures

# Devises pertinentes pour le trading crypto/forex
DEVISES_GLOBALES = {"USD", "EUR"}  # impact global (crypto + forex)

# Mapping symbole → devise
def _devise_symbole(symbole):
    """Extrait la devise d'un symbole de trading."""
    s = symbole.upper()
    if s.endswith("USDT"):
        return "USD"
    if s.endswith("EUR"):
        return "EUR"
    if s.endswith("GBP"):
        return "GBP"
    if s.endswith("JPY"):
        return "JPY"
    # Forex pairs: EURUSD → EUR, USDCAD → USD (devise de base)
    for dev in ["USD", "EUR", "GBP", "JPY", "CAD", "AUD", "NZD", "CHF", "CNY"]:
        if s.startswith(dev):
            return dev
    return "USD"  # défaut: impact USD (crypto)


def _charger_feed():
    """Charge le feed Forex Factory avec cache de 6h."""
    now = time.time()
    if _CACHE["data"] is not None and (now - _CACHE["ts"]) < _CACHE_TTL:
        return _CACHE["data"]

    events = []
    for url in [FEED_URL, FEED_NEXT_URL]:
        try:
            resp = requests.get(url, timeout=10, headers={"User-Agent": "Mozilla/5.0"})
            if resp.status_code == 200:
                events.extend(resp.json())
                logger.info(f"Feed chargé: {len(resp.json())} events depuis {url}")
        except Exception as e:
            logger.warning(f"Feed {url} indisponible: {e}")

    if events:
        _CACHE["data"] = events
        _CACHE["ts"] = now
    return _CACHE["data"] or []


def _parse_date(date_str):
    """Parse une date ISO du feed Forex Factory."""
    try:
        # Format: "2026-07-20T08:30:00-04:00"
        dt = datetime.fromisoformat(date_str)
        return dt.astimezone(timezone.utc)
    except Exception:
        return None


def evenements_jour(devise=None, impact_min=None):
    """
    Retourne les événements d'aujourd'hui.
    Filtre par devise et impact minimum si fournis.
    """
    events = _charger_feed()
    if not events:
        return []

    maintenant = datetime.now(timezone.utc)
    debut_jour = maintenant.replace(hour=0, minute=0, second=0, microsecond=0)
    fin_jour = debut_jour + timedelta(days=1)

    impacts_ordre = {"Holiday": 0, "Low": 1, "Medium": 2, "High": 3}
    seuil = impacts_ordre.get(impact_min, 0) if impact_min else 0

    resultats = []
    for ev in events:
        dt = _parse_date(ev.get("date", ""))
        if dt is None:
            continue
        if not (debut_jour <= dt < fin_jour):
            continue
        if devise and ev.get("country", "") != devise:
            continue
        if impacts_ordre.get(ev.get("impact", ""), 0) < seuil:
            continue
        resultats.append({
            "heure": dt.strftime("%H:%M UTC"),
            "titre": ev.get("title", ""),
            "devise": ev.get("country", ""),
            "impact": ev.get("impact", ""),
            "forecast": ev.get("forecast", ""),
            "previous": ev.get("previous", ""),
            "datetime": dt,
        })

    resultats.sort(key=lambda x: x["datetime"])
    return resultats


def evenements_proches(heures=2, devise=None, impact_min="High"):
    """
    Retourne les événements dans les prochaines N heures.
    Par défaut: événements High impact uniquement.
    """
    events = _charger_feed()
    if not events:
        return []

    maintenant = datetime.now(timezone.utc)
    fin = maintenant + timedelta(hours=heures)

    impacts_ordre = {"Holiday": 0, "Low": 1, "Medium": 2, "High": 3}
    seuil = impacts_ordre.get(impact_min, 3) if impact_min else 0

    resultats = []
    for ev in events:
        dt = _parse_date(ev.get("date", ""))
        if dt is None:
            continue
        if not (maintenant <= dt <= fin):
            continue
        if devise and ev.get("country", "") != devise:
            continue
        if impacts_ordre.get(ev.get("impact", ""), 0) < seuil:
            continue
        resultats.append({
            "heure": dt.strftime("%H:%M UTC"),
            "titre": ev.get("title", ""),
            "devise": ev.get("country", ""),
            "impact": ev.get("impact", ""),
            "forecast": ev.get("forecast", ""),
            "previous": ev.get("previous", ""),
            "datetime": dt,
        })

    resultats.sort(key=lambda x: x["datetime"])
    return resultats


def evenement_proche(symbole, heures=None):
    """
    Vérifie s'il y a un événement à haut impact dans les prochaines heures
    qui pourrait affecter le symbole donné.
    Retourne True si un événement proche est détecté.
    """
    h = heures or int(os.getenv("MACRO_GATE_HEURES", "2"))
    devise = _devise_symbole(symbole)

    # Pour la crypto (USDT), on vérifie USD
    # Pour le forex, on vérifie la devise de base + USD (impact global)
    devises_a_verifier = {devise, "USD"} if devise != "USD" else {"USD"}

    for dev in devises_a_verifier:
        events = evenements_proches(heures=h, devise=dev, impact_min="High")
        if events:
            return True
    return False


def gate_achat(symbole):
    """
    Gate macroéconomique pour l'achat.
    Retourne (True, "") si OK, (False, raison) si bloqué.
    """
    if os.getenv("MACRO_GATE", "0") != "1":
        return True, ""

    heures = int(os.getenv("MACRO_GATE_HEURES", "2"))
    impact_min = os.getenv("MACRO_GATE_IMPACT", "High")
    devise = _devise_symbole(symbole)

    # Crypto (USDT) → impact USD + EUR
    devises_a_verifier = {devise, "USD"} if devise != "USD" else {"USD"}
    if os.getenv("MACRO_GATE_INCLUDE_EUR", "1") == "1":
        devises_a_verifier.add("EUR")

    for dev in devises_a_verifier:
        events = evenements_proches(heures=heures, devise=dev, impact_min=impact_min)
        if events:
            ev = events[0]
            raison = (f"Event {ev['impact']} {dev} à {ev['heure']}: "
                     f"{ev['titre']} (forecast: {ev['forecast']})")
            return False, raison

    return True, ""


def prochaines_evenements(n=5, impact_min=None):
    """
    Retourne les N prochains événements (pour dashboard/digest).
    """
    events = _charger_feed()
    if not events:
        return []

    maintenant = datetime.now(timezone.utc)
    impacts_ordre = {"Holiday": 0, "Low": 1, "Medium": 2, "High": 3}
    seuil = impacts_ordre.get(impact_min, 0) if impact_min else 0

    resultats = []
    for ev in events:
        dt = _parse_date(ev.get("date", ""))
        if dt is None or dt < maintenant:
            continue
        if impacts_ordre.get(ev.get("impact", ""), 0) < seuil:
            continue
        resultats.append({
            "heure": dt.strftime("%d/%m %H:%M UTC"),
            "titre": ev.get("title", ""),
            "devise": ev.get("country", ""),
            "impact": ev.get("impact", ""),
            "forecast": ev.get("forecast", ""),
            "previous": ev.get("previous", ""),
            "datetime": dt,
        })

    resultats.sort(key=lambda x: x["datetime"])
    return resultats[:n]


def resume_jour():
    """
    Retourne un résumé textuel pour le digest Telegram.
    """
    try:
        events_high = evenements_jour(impact_min="High")
        events_medium = evenements_jour(impact_min="Medium")
        bas_haut = [e for e in events_medium if e["impact"] == "Medium"]
        prochain = prochaines_evenements(n=3, impact_min="High")

        lignes = []
        if events_high:
            lignes.append(f"🔴 High impact ({len(events_high)}):")
            for ev in events_high:
                lignes.append(f"  {ev['heure']} {ev['devise']} — {ev['titre']}")
        else:
            lignes.append("🔴 Aucun événement High aujourd'hui")

        if bas_haut:
            lignes.append(f"🟡 Medium ({len(bas_haut)}):")
            for ev in bas_haut[:3]:
                lignes.append(f"  {ev['heure']} {ev['devise']} — {ev['titre']}")

        if prochain:
            lignes.append("📅 Prochains High:")
            for ev in prochain:
                lignes.append(f"  {ev['heure']} {ev['devise']} — {ev['titre']}")

        return "\n".join(lignes) if lignes else "📅 Calendrier indisponible"
    except Exception as e:
        return f"📅 Calendrier: erreur ({e})"


if __name__ == "__main__":
    print("=== Calendrier macroéconomique ===")
    print(f"Source: Forex Factory JSON feed")
    print()

    print("--- Aujourd'hui (High impact) ---")
    for ev in evenements_jour(impact_min="High"):
        print(f"  {ev['heure']} [{ev['devise']}] {ev['titre']} (forecast: {ev['forecast']}, prev: {ev['previous']})")

    print()
    print("--- Prochains événements (tous impacts) ---")
    for ev in prochaines_evenements(n=10):
        print(f"  {ev['heure']} [{ev['devise']}] {ev['impact']:6s} — {ev['titre']}")

    print()
    print("--- Test gate BTCUSDT ---")
    ok, raison = gate_achat("BTCUSDT")
    print(f"  Gate: {'OK' if ok else 'BLOQUÉ'} — {raison}")

    print()
    print("--- Test gate EURUSD ---")
    ok, raison = gate_achat("EURUSD")
    print(f"  Gate: {'OK' if ok else 'BLOQUÉ'} — {raison}")

    print()
    print("--- Résumé ---")
    print(resume_jour())
