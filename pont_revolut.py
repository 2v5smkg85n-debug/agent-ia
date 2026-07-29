#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
pont_revolut.py — Pont paper_trading -> execution reelle Revolut X (crypto).

MODE DRY-RUN par defaut (simulation, AUCUN ordre reel). Pour activer le reel:
  export PONT_REVOLUT_LIVE=1
et s'assurer que le compte Revolut X est approvisionne en EUR.

Principe (non invasif — poll paper_trading.json comme telegram_monitor):
  - Detecte les NOUVELLES positions crypto ouvertes (source=backtest-gagnant,
    symbole dans le mapping) -> miroir: achat reel petit montant (cap).
  - Detecte les NOUVELLES fermetures crypto (trades_fermes) -> miroir: vente
    de la quantite crypto detenue pour ce trade.
  - Etat persiste dans revolut_mirror.json (idempotent, re-executable).
  - Caps de securite: CAP_PAR_TRADE_EUR, CAP_TOTAL_EUR.
  - Telegram alerte a chaque action (reel ou dry-run).
  - backfill: miroire les positions crypto DEJA ouvertes (avant debut_live)
    et jamais rattrapees, pour utiliser le capital Revolut X reste inactif.
    Respecte toujours les caps de securite (CAP_PAR_TRADE_EUR, CAP_TOTAL_EUR,
    MAX_ACHATS_JOUR) — seul le filtre debut_live est court-circuite.

Lancement:
  python pont_revolut.py                # un cycle (dry-run)
  python pont_revolut.py boucle          # boucle (60s)
  python pont_revolut.py etat            # voir l'etat du miroir
  python pont_revolut.py live            # passage en live (debut_live=now)
  python pont_revolut.py backfill        # rattrape les positions ouvertes avant debut_live
  python pont_revolut.py backfill-preview  # previsualise le backfill (aucun ordre)
"""
import os
import sys
import json
import time
import logging
from datetime import datetime

DOSSIER = os.path.dirname(os.path.abspath(__file__))
PT_FILE = os.path.join(DOSSIER, "paper_trading.json")
MIRROR_FILE = os.path.join(DOSSIER, "revolut_mirror.json")

# --- Config ---
DRY_RUN = os.getenv("PONT_REVOLUT_LIVE", "0") != "1"
QUOTE = "EUR"  # paires EUR (compte approvisionne en EUR)
CAP_PAR_TRADE_EUR = float(os.getenv("PONT_CAP_TRADE", "5.0"))
CAP_TOTAL_EUR = float(os.getenv("PONT_CAP_TOTAL", "50.0"))
MAX_ACHATS_JOUR = int(os.getenv("PONT_MAX_TRADES_JOUR", "8"))  # anti-bug runaway
BOUCLE_INTERVAL = 60

# Mapping symbole Binance -> paire Revolut X (ordre, format tiret)
BINANCE_TO_REVOLUTX = {
    # === Cryptos existantes ===
    "BTCUSDT": "BTC-EUR",
    "ETHUSDT": "ETH-EUR",
    "SOLUSDT": "SOL-EUR",
    "BNBUSDT": "BNB-EUR",
    "XRPUSDT": "XRP-EUR",
    "LDOUSDT": "LDO-EUR",
    "AAVEUSDT": "AAVE-EUR",
    "UNIUSDT": "UNI-EUR",
    "PENDLEUSDT": "PENDLE-EUR",
    "ARBUSDT": "ARB-EUR",
    "DOGEUSDT": "DOGE-EUR",
    "AVAXUSDT": "AVAX-EUR",
    "LINKUSDT": "LINK-EUR",
    "OPUSDT": "OP-EUR",
    "INJUSDT": "INJ-EUR",
    "NEARUSDT": "NEAR-EUR",
    # === Nouvelles cryptos (disponibles sur Revolut X) ===
    "PEPEUSDT": "PEPE-EUR",       # meme coin — gros gains possibles
    "WIFUSDT": "WIF-EUR",         # meme coin — gros gains possibles
    "SUIUSDT": "SUI-EUR",         # Layer 1 — haute volatilite
    "SEIUSDT": "SEI-EUR",         # Layer 1 — haute volatilite
    "TIAUSDT": "TIA-EUR",         # Layer 1 — haute volatilite
    "DOTUSDT": "DOT-EUR",         # Polkadot — staking disponible
    "ATOMUSDT": "ATOM-EUR",       # Cosmos — staking disponible
    "MATICUSDT": "MATIC-EUR",     # Polygon — staking disponible
    "FILUSDT": "FIL-EUR",         # Filecoin
    "SANDUSDT": "SAND-EUR",       # The Sandbox
    "AXSUSDT": "AXS-EUR",         # Axie Infinity
    "IMXUSDT": "IMX-EUR",         # Immutable X
    "CRVUSDT": "CRV-EUR",         # Curve DAO
    "COMPUSDT": "COMP-EUR",       # Compound
    "CAKEUSDT": "CAKE-EUR",        # PancakeSwap
    # Non disponibles sur Revolut X (paper trading seulement):
    # FETUSDT, RNDRUSDT, OCEANUSDT, APTUSDT, FLOKIUSDT
}

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%H:%M:%S",
)
log = logging.getLogger("pont_revolut")


def _load(path, default):
    try:
        return json.load(open(path, encoding="utf-8"))
    except Exception:
        return default


def _save(path, data):
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)


def _tel(msg):
    """Envoie une alerte Telegram (best-effort)."""
    try:
        from telegram_alerte import envoyer_telegram
        envoyer_telegram(msg)
    except Exception:
        pass


def _prix_revolut(client, paire):
    """Prix actuel d'une paire Revolut X (read-only)."""
    try:
        t = client.get_ticker(paire.replace("-", "/"))
        entries = t if isinstance(t, list) else (
            t.get("data", t) if isinstance(t, dict) else [])
        if isinstance(entries, dict):
            entries = entries.get("data", [entries])
        for e in entries:
            if not isinstance(e, dict):
                continue
            if e.get("symbol") == paire.replace("-", "/"):
                return float(e.get("last_price") or e.get("mid") or 0)
        # fallback: premier prix trouve
        for e in entries:
            if isinstance(e, dict) and e.get("last_price"):
                return float(e["last_price"])
    except Exception as e:
        log.warning("prix %s indispo: %s", paire, e)
    return None


# ---------------------------------------------------------------- LOGIQUE
def init_mirror():
    if not os.path.exists(MIRROR_FILE):
        _save(MIRROR_FILE, {"achats": {}, "ventes": [], "live": not DRY_RUN})
    return _load(MIRROR_FILE, {})


def exposition_totale(mirror):
    """Somme des achats miroires non encore vendus (en EUR)."""
    total = 0.0
    for k, v in mirror.get("achats", {}).items():
        if not v.get("vendu"):
            total += float(v.get("montant_eur", 0))
    return total


def _nb_achats_aujourdhui(mirror):
    _auj = datetime.now().strftime("%Y-%m-%d")
    _n = 0
    for _v in mirror.get("achats", {}).values():
        if str(_v.get("date_miroir", "")).startswith(_auj):
            _n += 1
    return _n

def miroirer_achat(client, position, mirror, force=False):
    """Miroire une ouverture de position crypto -> achat Revolut X.

    force=True: bypass le filtre debut_live (utilise par cmd_backfill pour
    miroirer les positions ouvertes AVANT le passage en live). Les caps de
    securite (CAP_PAR_TRADE_EUR, CAP_TOTAL_EUR, MAX_ACHATS_JOUR) restent
    toujours actifs, meme en mode force.
    """
    symbole = position.get("symbole", "")
    paire = BINANCE_TO_REVOLUTX.get(symbole)
    if not paire:
        return  # crypto non supportee
    # cle d'idempotence: symbole + date_ouverture
    cle = f"{symbole}_{position.get('date_ouverture','')}"
    if cle in mirror.get("achats", {}):
        return  # deja miroire
    # ne pas racheter les positions ouvertes avant le passage en live
    # (sauf si force=True, utilise explicitement par le backfill)
    debut = mirror.get("debut_live")
    if not force and debut and position.get("date_ouverture", "") < debut:
        return  # position historique (avant live) — skip
    montant = min(CAP_PAR_TRADE_EUR, CAP_PAR_TRADE_EUR)
    # cap total
    expo = exposition_totale(mirror)
    if expo + montant > CAP_TOTAL_EUR:
        montant = max(0.0, CAP_TOTAL_EUR - expo)
        if montant < 1.0:
            log.warning("[CAP] exposition totale %.2f€ >= cap %.2f€ — achat skip",
                        expo, CAP_TOTAL_EUR)
            return
    _naj = _nb_achats_aujourdhui(mirror)
    if _naj >= MAX_ACHATS_JOUR:
        log.warning("[GARDE] %d achats miroires aujourd hui (max %d) -> skip", _naj, MAX_ACHATS_JOUR)
        return
    prix = _prix_revolut(client, paire)
    qty_crypto = montant / prix if prix else None
    mode = "DRY-RUN" if DRY_RUN else "LIVE"
    log.info("[%s] ACHAT %s -> %s | %.2f€ %s%s",
             mode, symbole, paire, montant, f"(~{qty_crypto:.6f} {symbole[:3]}) " if qty_crypto else "",
             "(simule)" if DRY_RUN else "")
    record = {
        "symbole": symbole, "paire": paire, "montant_eur": round(montant, 2),
        "prix": prix, "qty_crypto": qty_crypto,
        "date_ouverture": position.get("date_ouverture", ""),
        "date_miroir": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "vendu": False, "order_id": None,
    }
    if not DRY_RUN:
        try:
            resp = client.place_market_order(paire, "buy", quote_size=montant)
            _d = resp.get("data", resp) if isinstance(resp, dict) else resp
            _oid = None
            if isinstance(_d, dict):
                _oid = _d.get("id") or _d.get("order_id")
            elif isinstance(_d, list) and _d:
                _oid = _d[0].get("id") or _d[0].get("order_id")
            record["order_id"] = _oid
            log.info("[LIVE] ordre achat place (order_id=%s): %s", _oid, resp)
            _tel(f"🟦 ACHAT REEL {symbole} {montant:.2f}€ sur Revolut X ({paire})")
        except Exception as e:
            log.error("[LIVE] echec achat %s: %s", symbole, e)
            _tel(f"⚠️ ECHEC achat reel {symbole}: {e}")
            return
    else:
        _tel(f"🟦 [DRY-RUN] achat simulé {symbole} {montant:.2f}€ ({paire})")
    mirror.setdefault("achats", {})[cle] = record
    _save(MIRROR_FILE, mirror)


def miroirer_vente(client, trade, mirror):
    """Miroire une fermeture de position crypto -> vente Revolut X."""
    symbole = trade.get("symbole", "")
    if symbole not in BINANCE_TO_REVOLUTX:
        return
    paire = BINANCE_TO_REVOLUTX[symbole]
    cle = f"{symbole}_{trade.get('date_ouverture','')}"
    achat = mirror.get("achats", {}).get(cle)
    if not achat or achat.get("vendu"):
        return  # pas miroire en achat ou deja vendu
    qty = achat.get("qty_crypto")
    mode = "DRY-RUN" if DRY_RUN else "LIVE"
    log.info("[%s] VENTE %s -> %s | qty %s %s%s",
             mode, symbole, paire, qty, symbole[:3],
             " (simule)" if DRY_RUN else "")
    if not DRY_RUN and qty:
        try:
            resp = client.place_market_order(paire, "sell", base_size=qty)
            log.info("[LIVE] ordre vente place: %s", resp)
            _tel(f"🟩 VENTE REEL {symbole} qty {qty} sur Revolut X ({paire})")
        except Exception as e:
            log.error("[LIVE] echec vente %s: %s", symbole, e)
            _tel(f"⚠️ ECHEC vente reel {symbole}: {e}")
            return
    else:
        _tel(f"🟩 [DRY-RUN] vente simulée {symbole} qty {qty} ({paire})")
    achat["vendu"] = True
    achat["date_vente"] = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    mirror.setdefault("ventes", []).append({**achat, "gain_paper": trade.get("gain_eur")})
    _save(MIRROR_FILE, mirror)


def cycle():
    """Un cycle de miroirage. Cree le client seulement si necessaire."""
    if os.getenv("PONT_KILL", "0") == "1":
        log.warning("[KILL] pont Revolut X desactive (PONT_KILL=1) -> cycle skip")
        return
    pt = _load(PT_FILE, {})
    positions = pt.get("positions", [])
    trades = pt.get("trades_fermes", [])
    mirror = init_mirror()
    client = None
    if positions or trades:
        try:
            from revolut_x import RevolutX
            client = RevolutX()
        except Exception as e:
            log.error("Client Revolut X indispo: %s", e)
            return
    # 1. achats: positions crypto ouvertes non miroirees
    for p in positions:
        if p.get("source") == "backtest-gagnant" or p.get("symbole") in BINANCE_TO_REVOLUTX:
            miroirer_achat(client, p, mirror)
    # 2. ventes: trades fermes crypto non miroires en vente
    for t in trades:
        miroirer_vente(client, t, mirror)


def cmd_etat():
    mirror = init_mirror()
    a = mirror.get("achats", {})
    achats_actifs = [v for v in a.values() if not v.get("vendu")]
    n_ventes = len(mirror.get("ventes", []))
    expo = exposition_totale(mirror)
    print("=" * 50)
    print(f"PONT REVOLUT X — ETAT")
    print(f"Mode: {'DRY-RUN (simulation)' if DRY_RUN else 'LIVE (reel)'}")
    print(f"Paire quote: {QUOTE}")
    print(f"Cap par trade: {CAP_PAR_TRADE_EUR}€ | Cap total: {CAP_TOTAL_EUR}€")
    print(f"Achats miroires: {len(a)} (dont {len(achats_actifs)} non vendus)")
    print(f"Ventes miroires: {n_ventes}")
    print(f"Exposition actuelle: {expo:.2f}€ / {CAP_TOTAL_EUR}€")
    print("=" * 50)
    for k, v in a.items():
        statut = "vendu" if v.get("vendu") else "OUVERT"
        print(f"  {v['symbole']:<10} {v['montant_eur']:.2f}€ {statut} "
              f"({v.get('date_miroir','')[:16]})")


def cmd_live():
    """Passe en live: efface l'etat dry-run, fixe debut_live=now.
    Les positions deja ouvertes (avant maintenant) ne seront PAS rachetees.
    Seuls les nouveaux trades crypto seront miroires en reel."""
    from datetime import datetime
    maintenant = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    _save(MIRROR_FILE, {
        "achats": {}, "ventes": [],
        "debut_live": maintenant, "live": True,
    })
    print("=" * 50)
    print("PONT REVOLUT X — PASSAGE EN LIVE")
    print(f"Debut live: {maintenant}")
    print("Etat dry-run efface. Les positions crypto ouvertes AVANT")
    print("maintenant ne seront pas rachetees (evite l'entree tardive).")
    print("Seuls les NOUVEAUX trades crypto seront miroires en reel.")
    print("=" * 50)


def cmd_backfill():
    """Backfill: miroire les positions crypto DEJA ouvertes (avant debut_live)
    qui n'ont jamais ete miroirees. Sert a utiliser le capital Revolut X
    (CAP_TOTAL_EUR) reste inactif depuis le passage en live, en rattrapant
    les positions ouvertes historiquement. Les caps de securite restent
    actifs (CAP_PAR_TRADE_EUR, CAP_TOTAL_EUR, MAX_ACHATS_JOUR)."""
    if os.getenv("PONT_KILL", "0") == "1":
        log.warning("[KILL] pont Revolut X desactive (PONT_KILL=1) -> backfill skip")
        return
    pt = _load(PT_FILE, {})
    positions = pt.get("positions", [])
    mirror = init_mirror()
    a_traiter = []
    for p in positions:
        symbole = p.get("symbole", "")
        if symbole not in BINANCE_TO_REVOLUTX:
            continue
        cle = f"{symbole}_{p.get('date_ouverture','')}"
        if cle in mirror.get("achats", {}):
            continue  # deja miroire
        a_traiter.append(p)
    print("=" * 50)
    print("PONT REVOLUT X — BACKFILL")
    print(f"Positions ouvertes non miroirees detectees: {len(a_traiter)}")
    print("=" * 50)
    if not a_traiter:
        print("Rien a rattraper.")
        return
    client = None
    try:
        from revolut_x import RevolutX
        client = RevolutX()
    except Exception as e:
        log.error("Client Revolut X indispo: %s", e)
        return
    avant = set(mirror.get("achats", {}).keys())
    for p in a_traiter:
        miroirer_achat(client, p, mirror, force=True)
    apres = mirror.get("achats", {})
    nouveaux = [k for k in apres.keys() if k not in avant]
    print("-" * 50)
    print(f"Backfill termine: {len(nouveaux)} position(s) miroiree(s)")
    total = 0.0
    for k in nouveaux:
        v = apres[k]
        total += float(v.get("montant_eur", 0))
        print(f"  {v['symbole']:<10} {v['montant_eur']:.2f}€ ({v.get('paire')})")
    print(f"Montant total miroire: {total:.2f}€")
    print(f"Exposition totale apres backfill: {exposition_totale(mirror):.2f}€ / {CAP_TOTAL_EUR}€")
    print("=" * 50)
    _tel(f"🔄 Backfill Revolut X: {len(nouveaux)} position(s) rattrapee(s), {total:.2f}€ miroires")


def cmd_backfill_dry():
    """Previsualise le backfill (aucun ordre, aucune ecriture d'etat)."""
    pt = _load(PT_FILE, {})
    positions = pt.get("positions", [])
    mirror = init_mirror()
    a_traiter = []
    for p in positions:
        symbole = p.get("symbole", "")
        if symbole not in BINANCE_TO_REVOLUTX:
            continue
        cle = f"{symbole}_{p.get('date_ouverture','')}"
        if cle in mirror.get("achats", {}):
            continue  # deja miroire
        a_traiter.append(p)
    print("=" * 50)
    print("PONT REVOLUT X — BACKFILL (PREVIEW, aucun ordre passe)")
    print(f"Cap par trade: {CAP_PAR_TRADE_EUR}€ | Cap total: {CAP_TOTAL_EUR}€")
    print(f"Exposition actuelle: {exposition_totale(mirror):.2f}€")
    print(f"Positions ouvertes non miroirees detectees: {len(a_traiter)}")
    print("=" * 50)
    if not a_traiter:
        print("Rien a rattraper.")
        return
    expo_simulee = exposition_totale(mirror)
    n_simule = _nb_achats_aujourdhui(mirror)
    for p in a_traiter:
        symbole = p.get("symbole", "")
        paire = BINANCE_TO_REVOLUTX.get(symbole)
        montant = CAP_PAR_TRADE_EUR
        statut = "OK"
        if expo_simulee + montant > CAP_TOTAL_EUR:
            montant = max(0.0, CAP_TOTAL_EUR - expo_simulee)
            if montant < 1.0:
                statut = "SKIP (cap total atteint)"
        if n_simule >= MAX_ACHATS_JOUR:
            statut = "SKIP (max achats/jour atteint)"
        print(f"  {symbole:<10} -> {paire:<10} {montant:.2f}€  [{statut}] "
              f"(ouverte le {p.get('date_ouverture','?')})")
        if statut == "OK":
            expo_simulee += montant
            n_simule += 1
    print("-" * 50)
    print(f"Exposition projetee apres backfill: {expo_simulee:.2f}€ / {CAP_TOTAL_EUR}€")
    print("=" * 50)


def main():
    if len(sys.argv) > 1 and sys.argv[1] == "etat":
        cmd_etat()
        return
    if len(sys.argv) > 1 and sys.argv[1] == "live":
        cmd_live()
        return
    if len(sys.argv) > 1 and sys.argv[1] == "backfill":
        cmd_backfill()
        return
    if len(sys.argv) > 1 and sys.argv[1] == "backfill-preview":
        cmd_backfill_dry()
        return
    if len(sys.argv) > 1 and sys.argv[1] == "boucle":
        log.info("Pont Revolut X demarré (mode %s, intervalle %ss)",
                 "DRY-RUN" if DRY_RUN else "LIVE", BOUCLE_INTERVAL)
        while True:
            try:
                cycle()
            except Exception as e:
                log.error("erreur cycle: %s", e)
            time.sleep(BOUCLE_INTERVAL)
    else:
        cycle()
        cmd_etat()


if __name__ == "__main__":
    main()
