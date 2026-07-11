#!/usr/bin/env python3
"""
protection.py v2 — Stop suiveur (trailing stop) multi-positions pour Revolut X.

L'API Revolut X ne permet PAS de placer des ordres stop/tpsl natifs (testé en
production 2026-07-02 : POST /orders rejette toutes les formes tpsl). Cette
boucle de surveillance est donc la seule facon d'implementer un SL/TP via API.

AMELIORATIONS v2 :
  - Trailing stop : le seuil de vente MONTE avec le prix. Si le BTC grimpe,
    le stop suit vers le haut et verrouille les gains. Meilleur qu'un TP fixe.
  - Multi-positions : scanne TOUS les soldes crypto non nuls et protege
    chaque position (pas seulement le BTC).
  - Filtre mini : ignore les positions < 1.5 EUR (non vendables, min exchange 1 EUR).

Logique par position :
  - peak = prix le plus haut depuis le demarrage
  - Si prix <= peak * (1 - trail%/100)  -> VENTE (stop suiveur declenche)
  - Option : take-profit dur a +tp%  -> VENTE (verrouillage)

Usage:
    python protection.py                 # trailing 5%, verif 60s
    python protection.py 3.0             # trailing 3%
    python protection.py 5.0 60 20.0      # trailing 5%, verif 60s, TP dur +20%
    python protection.py 5.0 30           # trailing 5%, verif 30s

Lancer en arriere-plan :
    nohup python -u protection.py > protection.log 2>&1 & disown
"""
import sys
import time
import logging

from revolut_x import RevolutX, RevolutXError

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%H:%M:%S",
)
log = logging.getLogger("protection")

# Devises de cotation essayees dans l'ordre (le compte a de l'EUR)
QUOTE_CANDIDATES = ["EUR", "USD"]
# Valeur minimale pour proteger une position (min exchange ~1 EUR + marge)
VALEUR_MIN_PROTECTION = 1.5


def _est_crypto_ignorable(currency):
    """Devises fiat / stablecoins a ne pas trader comme base."""
    return currency in {
        "EUR", "USD", "GBP", "USDC", "USDT", "RLUSD", "TRX",  # TRX = token fee, pas une position
    }


def trouver_paire(c, currency):
    """Trouve une paire active {CURRENCY}-{QUOTE} pour la crypto donnee."""
    try:
        pairs = c.get_pairs()
    except RevolutXError:
        return None, None
    if not isinstance(pairs, dict):
        return None, None
    for quote in QUOTE_CANDIDATES:
        for key, p in pairs.items():
            if (
                p.get("base") == currency
                and p.get("quote") == quote
                and p.get("status") == "active"
            ):
                return f"{currency}-{quote}", quote
    return None, None


def prix_courant(c, pair):
    """Prix actuel via le carnet public (mid best bid / best ask)."""
    book = c.get_public_order_book(pair)
    data = book.get("data", book) if isinstance(book, dict) else book
    asks = data.get("asks", [])
    bids = data.get("bids", [])
    if not asks or not bids:
        raise RevolutXError(f"Carnet vide pour {pair}")
    best_ask = float(asks[0]["p"])
    best_bid = float(bids[0]["p"])
    return (best_ask + best_bid) / 2


def soldes_non_nuls(c):
    """Retourne {currency: available} pour les soldes crypto > 0."""
    balances = c.get_balances()
    if not isinstance(balances, list):
        return {}
    result = {}
    for b in balances:
        cur = b.get("currency")
        if not cur or _est_crypto_ignorable(cur):
            continue
        try:
            avail = float(b.get("available", 0))
        except (ValueError, TypeError):
            continue
        if avail > 0:
            result[cur] = avail
    return result


def vendre_tout(c, pair, currency):
    """Vend toute la quantite disponible de `currency` au marche."""
    balances = c.get_balances()
    if not isinstance(balances, list):
        return None, 0.0
    qty = 0.0
    for b in balances:
        if b.get("currency") == currency:
            try:
                qty = float(b.get("available", 0))
            except (ValueError, TypeError):
                qty = 0.0
            break
    if qty <= 0:
        return None, 0.0
    r = c.place_market_order(pair, "sell", base_size=qty)
    return r, qty


def construire_positions(c):
    """Construit la liste des positions a proteger."""
    positions = []
    soldes = soldes_non_nuls(c)
    for currency, qty in soldes.items():
        pair, quote = trouver_paire(c, currency)
        if not pair:
            log.info(f"{currency}: aucune paire active trouvee, ignore")
            continue
        try:
            prix = prix_courant(c, pair)
        except RevolutXError as e:
            log.warning(f"{currency}: prix indisponible ({e}), ignore")
            continue
        valeur = qty * prix
        if valeur < VALEUR_MIN_PROTECTION:
            log.info(
                f"{currency}: valeur {valeur:.2f} EUR < {VALEUR_MIN_PROTECTION} EUR (min exchange), ignore"
            )
            continue
        positions.append(
            {
                "currency": currency,
                "pair": pair,
                "qty": qty,
                "peak": prix,
                "prix_ref": prix,
            }
        )
    return positions


def main():
    trail_pct = float(sys.argv[1]) if len(sys.argv) > 1 else 5.0
    intervalle = int(sys.argv[2]) if len(sys.argv) > 2 else 60
    tp_dur_pct = float(sys.argv[3]) if len(sys.argv) > 3 else None

    c = RevolutX()
    positions = construire_positions(c)

    if not positions:
        print("Aucune position a proteger (solde crypto < min ou aucune paire).")
        return

    print("=" * 55)
    print(f"PROTECTION MULTI-POSITIONS — Trailing stop {trail_pct}%")
    print("=" * 55)
    for pos in positions:
        stop = pos["peak"] * (1 - trail_pct / 100)
        tp_txt = (
            f" | TP dur {pos['prix_ref'] * (1 + tp_dur_pct / 100):.2f} (+{tp_dur_pct}%)"
            if tp_dur_pct
            else ""
        )
        print(
            f"  {pos['currency']}: {pos['qty']} @ {pos['prix_ref']:.2f} | "
            f"stop {stop:.2f} (-{trail_pct}%){tp_txt}"
        )
    print(f"Verification: toutes les {intervalle}s | Arret: Ctrl+C")
    print("=" * 55)

    while True:
        for pos in positions:
            cur = pos["currency"]
            pair = pos["pair"]
            try:
                prix = prix_courant(c, pair)
            except RevolutXError as e:
                log.error(f"{cur}: prix indisponible ({e})")
                continue
            except Exception as e:
                log.error(f"{cur}: erreur ({e})")
                continue

            # Le stop suit le prix vers le haut
            if prix > pos["peak"]:
                pos["peak"] = prix

            stop = pos["peak"] * (1 - trail_pct / 100)
            var_ref = (prix - pos["prix_ref"]) / pos["prix_ref"] * 100
            var_peak = (prix - pos["peak"]) / pos["peak"] * 100
            log.info(
                f"{cur} {prix:.2f} | ref {var_ref:+.2f}% | peak {pos['peak']:.2f} "
                f"({var_peak:+.2f}%) | stop {stop:.2f}"
            )

            # Take-profit dur optionnel
            if tp_dur_pct and prix >= pos["prix_ref"] * (1 + tp_dur_pct / 100):
                log.info(
                    f"{cur}: TAKE-PROFIT dur atteint ({prix:.2f}) -> VENTE"
                )
                r, vendu = vendre_tout(c, pair, cur)
                log.info(f"{cur}: vendu {vendu}. {r}")
                positions = [p for p in positions if p["currency"] != cur]
                continue

            # Stop suiveur : prix retombe sous le stop
            if prix <= stop:
                log.info(
                    f"{cur}: STOP SUIVEUR declenche ({prix:.2f} <= {stop:.2f}, "
                    f"peak {pos['peak']:.2f}) -> VENTE"
                )
                r, vendu = vendre_tout(c, pair, cur)
                log.info(f"{cur}: vendu {vendu}. {r}")
                positions = [p for p in positions if p["currency"] != cur]

        if not positions:
            log.info("Toutes les positions sont fermees. Fin de la protection.")
            break

        time.sleep(intervalle)

    print("Protection terminee.")


if __name__ == "__main__":
    main()
