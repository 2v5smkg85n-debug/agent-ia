#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""staking_revolut_monitor.py — Moniteur de staking Revolut (Feature 4 adaptée Revolut).

L'API Revolut X n'expose AUCUN endpoint de staking (vérifié doc officielle
developer.revolut.com). Le staking Revolut (ETH/SOL/ADA/DOT, ~2.5-7% APY)
s'active MANUELLEMENT dans l'app, puis le champ 'staked' apparaît en LECTURE
SEULE dans GET /balances.

Ce module (zéro action argent réel via API — lecture seule):
  - lit /balances via le client revolut_x existant (mêmes clés .env que pont_revolut)
  - détecte les actifs stakés (champ staked > 0)
  - snapshot ledger -> détecte accrétion de récompenses / unstake / nouveaux stakes
  - alerte Telegram sur tout changement du staking
  - conseil: suggère de staker le capital EUR oisif (advisory, l'API ne peut pas staker)

CLI:
  python staking_revolut_monitor.py            # cycle (snapshot + alertes)
  python staking_revolut_monitor.py rapport    # état du staking + valeur EUR
  python staking_revolut_monitor.py conseil    # suggestion capital oisif
"""
import os
import json
import logging
from datetime import datetime

DOSSIER = os.path.dirname(os.path.abspath(__file__))
LEDGER = os.path.join(DOSSIER, "staking_revolut_ledger.jsonl")

STAKABLES_REVOLUT = {"ETH", "SOL", "ADA", "DOT", "KSM", "XTZ"}  # actifs stakables app Revolut
SEUIL_CONSEIL_EUR = float(os.getenv("STAKING_SEUIL_CONSEIL", "20"))

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s", datefmt="%H:%M:%S")
log = logging.getLogger("staking_mon")


def _client():
    """Construit le client Revolut X (clés dans .env). None si indispo."""
    try:
        from revolut_x import RevolutX
        return RevolutX()
    except Exception as e:
        log.error("Client Revolut X indispo: %s", e)
        return None


def _parse_balances(raw):
    """Normalise la réponse /balances en liste de dicts (l'API renvoie une liste)."""
    if isinstance(raw, list):
        return raw
    if isinstance(raw, dict):
        if "balances" in raw:
            return raw["balances"]
        return list(raw.values())
    return []


def lire_staking(client):
    """{currency: {staked, available, reserved, total}} pour les actifs stakés (>0)."""
    out = {}
    try:
        rows = _parse_balances(client.get_balances())
    except Exception as e:
        log.error("Lecture /balances échouée: %s", e)
        return out, 0.0
    eur_libre = 0.0
    for b in rows:
        cur = b.get("currency") or b.get("asset")
        try:
            staked = float(b.get("staked", 0) or 0)
        except (TypeError, ValueError):
            staked = 0.0
        if staked > 0:
            out[cur] = {
                "staked": staked,
                "available": float(b.get("available", 0) or 0),
                "reserved": float(b.get("reserved", 0) or 0),
                "total": float(b.get("total", 0) or 0),
            }
        if cur == "EUR":
            try:
                eur_libre = float(b.get("available", 0) or 0)
            except (TypeError, ValueError):
                eur_libre = 0.0
    return out, eur_libre


EUR_USD = float(os.getenv("EUR_USD_RATE", "1.08"))  # 1 EUR = 1.08 USD (fallback si pas de paire EUR)


def _ticker_map(client):
    """{base_currency: {quote: last_price}} depuis GET /tickers (toutes les paires)."""
    try:
        data = client.get_ticker()
    except Exception as e:
        log.debug("ticker map échouée: %s", e)
        return {}
    rows = data.get("data", []) if isinstance(data, dict) else (data if isinstance(data, list) else [])
    m = {}
    for t in rows:
        if not isinstance(t, dict):
            continue
        sym = t.get("symbol", "")
        if "/" not in sym:
            continue
        base, quote = sym.split("/", 1)
        try:
            p = float(t.get("last_price") or t.get("mid") or 0)
        except (TypeError, ValueError):
            continue
        if p > 0:
            m.setdefault(base, {})[quote] = p
    return m


def _val_eur(client, currency, amount, pmap=None):
    """Valeur EUR d'une quantité de crypto. Préfère la paire EUR, fallback USD/USDC/USDT."""
    if pmap is None:
        pmap = _ticker_map(client)
    quotes = pmap.get(currency, {})
    if not quotes:
        return 0.0
    if "EUR" in quotes:
        return amount * quotes["EUR"]
    for q in ("USD", "USDC", "USDT"):
        if q in quotes:
            return amount * quotes[q] / EUR_USD
    return 0.0


def snapshot(client):
    """Capture l'état du staking, l'écrit dans le ledger. Retourne le snapshot."""
    staking, eur_libre = lire_staking(client)
    snap = {"ts": datetime.utcnow().isoformat(), "staking": staking, "eur_libre": eur_libre}
    try:
        with open(LEDGER, "a", encoding="utf-8") as f:
            f.write(json.dumps(snap, ensure_ascii=False) + "\n")
    except Exception as e:
        log.error("Écriture ledger échouée: %s", e)
    return snap


def _dernier_snapshot():
    try:
        with open(LEDGER, encoding="utf-8") as f:
            lignes = [l for l in f.read().strip().split("\n") if l.strip()]
        return json.loads(lignes[-1]) if lignes else None
    except Exception:
        return None


def changements(actuel, precedent):
    """Compare 2 snapshots -> liste de changements (type, currency, détail)."""
    out = []
    if not precedent:
        for cur, d in actuel.get("staking", {}).items():
            out.append(("nouveau_stake", cur, f"staké {d['staked']} {cur}"))
        return out
    prec_stake = precedent.get("staking", {})
    cur_stake = actuel.get("staking", {})
    # disparus
    for cur in prec_stake:
        if cur not in cur_stake:
            out.append(("fin_staking", cur, f"plus de staking {cur} (était {prec_stake[cur]['staked']})"))
    # présents
    for cur, d in cur_stake.items():
        avant = prec_stake.get(cur)
        if not avant:
            out.append(("nouveau_stake", cur, f"staké {d['staked']} {cur}"))
            continue
        delta = d["staked"] - avant["staked"]
        if abs(delta) < 1e-9:
            continue
        if delta > 0:
            # stake manuel (available a baissé ~ montant) vs récompense (available stable)
            disp_avant = avant["available"]
            disp_delta = disp_avant - d["available"]
            if disp_delta >= delta * 0.8:
                out.append(("stake_manuel", cur, f"+{delta:.6f} {cur} (depuis available)"))
            else:
                out.append(("recompense", cur, f"+{delta:.6f} {cur} (récompense probable)"))
        else:
            out.append(("unstake", cur, f"{delta:.6f} {cur} (retrait/unstake)"))
    return out


def _notify(msg):
    try:
        from telegram_alerte import envoyer_telegram
        envoyer_telegram(f"💎 STAKING — {msg}")
    except Exception:
        pass


def cycle(client=None):
    """Snapshot + détection changements + alerte. Retourne les changements."""
    client = client or _client()
    if not client:
        log.warning("Client Revolut X indispo — cycle abandonné.")
        return []
    snap = snapshot(client)
    prec = _dernier_snapshot_excluding(snap)
    chg = changements(snap, prec)
    if chg:
        lignes = [f"{c[1]}: {c[2]}" for c in chg]
        _notify("changements staking:\n" + "\n".join(lignes))
        for c in chg:
            log.info("[%s] %s — %s", c[0], c[1], c[2])
    else:
        log.info("Aucun changement de staking. Staké: %d actif(s).", len(snap["staking"]))
    return chg


def _dernier_snapshot_excluding(current):
    """Dernier snapshot du ledger DIFFÉRENT de current (évite de se comparer à soi-même)."""
    try:
        with open(LEDGER, encoding="utf-8") as f:
            lignes = [l for l in f.read().strip().split("\n") if l.strip()]
    except Exception:
        return None
    cur_str = json.dumps(current, ensure_ascii=False, sort_keys=True)
    for l in reversed(lignes):
        try:
            snap = json.loads(l)
        except Exception:
            continue
        if json.dumps(snap, ensure_ascii=False, sort_keys=True) != cur_str:
            return snap
    return None


def rapport(client=None):
    """Affiche l'état du staking + valeur EUR estimée."""
    client = client or _client()
    if not client:
        print("Client Revolut X indispo.")
        return {}
    staking, eur_libre = lire_staking(client)
    if not staking:
        print("Aucun actif staké. (Active le staking ETH/SOL/ADA dans l'app Revolut pour le suivre.)")
        print(f"Capital EUR oisif: {eur_libre:.2f} €")
        return {}
    print("=" * 50)
    print("STAKING REVOLUT (lecture /balances)")
    pmap = _ticker_map(client)
    total_eur = 0.0
    for cur, d in staking.items():
        val = _val_eur(client, cur, d["staked"], pmap)
        total_eur += val
        marque = " ✓ stakable" if cur in STAKABLES_REVOLUT else ""
        print(f"  {cur}: {d['staked']:.6f} staké (total {d['total']:.6f}) ~{val:.2f} €{marque}")
    print("-" * 50)
    print(f"  TOTAL staking: ~{total_eur:.2f} € | EUR oisif: {eur_libre:.2f} €")
    print("=" * 50)
    return staking


def conseil(client=None):
    """Suggère de staker le capital EUR oisif (advisory — l'API ne peut pas staker)."""
    client = client or _client()
    if not client:
        print("Client Revolut X indispo.")
        return
    staking, eur_libre = lire_staking(client)
    if eur_libre >= SEUIL_CONSEIL_EUR:
        msg = (f"{eur_libre:.2f} € oisifs. Considère convertir une partie en ETH/SOL "
               f"et activer le staking dans l'app Revolut (~2.5-7% APY). "
               f"L'agent ne peut pas staker via API (lecture seule) — action manuelle dans l'app.")
        print(msg)
        _notify(msg)
    else:
        print(f"Capital EUR oisif ({eur_libre:.2f} €) < seuil conseil ({SEUIL_CONSEIL_EUR} €) — rien à suggérer.")


if __name__ == "__main__":
    import sys
    cmd = sys.argv[1] if len(sys.argv) > 1 else "cycle"
    if cmd == "rapport":
        rapport()
    elif cmd == "conseil":
        conseil()
    else:
        chg = cycle()
        print(f"{len(chg)} changement(s) détecté(s).")
