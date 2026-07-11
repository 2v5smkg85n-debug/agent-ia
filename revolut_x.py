#!/usr/bin/env python3
"""
revolut_x.py — Wrapper API pour Revolut X (échange crypto pro de Revolut)

Spécification officielle vérifiée contre le SDK open-source revolutx
(https://github.com/justpresident/revolutx) et l'inventaire OpenAPI Revolut X.

Revolut X expose une API REST signée en Ed25519 :
  - Base URL : https://revx.revolut.com/api/1.0
  - Headers : X-Revx-API-Key, X-Revx-Timestamp, X-Revx-Signature
  - Signature : Ed25519 sur message = concaténation directe (SANS séparateur) de :
        1. timestamp (epoch millisecondes, décimal)
        2. méthode HTTP MAJUSCULE
        3. chemin depuis /api/1.0  (ex: /api/1.0/balances)
        4. query string SANS le '?' (vide si absent)
        5. corps JSON minifié (vide si absent)
    Les bytes signés doivent être EXACTEMENT les bytes envoyés sur le wire.
  - 2 endpoints publics (sans auth) : /public/last-trades, /public/order-book/{symbol}

Endpoints (18 opérations) :
  GET    /balances                        soldes
  GET    /configuration/currencies         devises
  GET    /configuration/pairs              paires
  POST   /orders                           créer ordre
  DELETE /orders                           annuler tous
  GET    /orders/active                    ordres actifs
  GET    /orders/historical                historique ordres
  GET    /orders/{id}                      détail ordre
  DELETE /orders/{id}                       annuler ordre
  PUT    /orders/{id}                       remplacer ordre
  GET    /orders/fills/{id}                exécutions d'un ordre
  GET    /trades/all/{symbol}              tous trades (public)
  GET    /trades/private/{symbol}          trades privés
  GET    /order-book/{symbol}              carnet (auth)
  GET    /candles/{symbol}                 bougies (auth)
  GET    /tickers                          tickers (auth)
  GET    /public/last-trades              derniers trades (PAS d'auth)
  GET    /public/order-book/{symbol}       carnet public (PAS d'auth)

Format des symboles : BTC-USD (avec tiret), pas BTCUSDT.

Format ordre (POST /orders) :
  {
    "client_order_id": "<uuid>",
    "symbol": "BTC-USD",
    "side": "buy" | "sell",
    "order_configuration": {
      "limit":  {"quote_size": "0.1", "price": "50000.50"},  # quote_size=montant en USD
      "market": {"quote_size": "0.1"}  # ou "base_size": "0.001"
    }
  }

Dépendances : requests, cryptography
  pip install requests cryptography

Variables .env :
  REVOLUT_X_API_KEY=0fEG...        (clé publique, visible dans Revolut X)
  REVOLUT_X_PRIVATE_KEY=/home/ubuntu/agent-ia/revolut_private.pem
  # ou directement le contenu PEM :
  REVOLUT_X_PRIVATE_KEY_PEM=-----BEGIN PRIVATE KEY-----...
"""

import os
import sys
import json
import time
import uuid
import base64
import logging
from urllib.parse import urlencode

import requests
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
from cryptography.exceptions import UnsupportedAlgorithm

# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------

BASE_URL = "https://revx.revolut.com"
API_PREFIX = "/api/1.0"

TIMEOUT = 15
RETRY_ON_5XX = 2

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%H:%M:%S",
)
log = logging.getLogger("revolut_x")


# ---------------------------------------------------------------------------
# Erreurs
# ---------------------------------------------------------------------------

class RevolutXError(Exception):
    """Erreur générique Revolut X."""

class RevolutXAuthError(RevolutXError):
    """Clé manquante ou signature invalide (401/403)."""

class RevolutXRateLimit(RevolutXError):
    """Rate limit atteint (429)."""

class RevolutXOrderError(RevolutXError):
    """Erreur lors du placement/annulation d'un ordre."""


# ---------------------------------------------------------------------------
# Client
# ---------------------------------------------------------------------------

class RevolutX:
    """Client API Revolut X signé Ed25519."""

    def __init__(self, api_key: str = None, private_key_pem: str = None,
                 private_key_path: str = None):
        # Charger .env si python-dotenv est disponible
        try:
            from dotenv import load_dotenv
            load_dotenv()
        except ImportError:
            pass

        self.api_key = api_key or os.getenv("REVOLUT_X_API_KEY")
        if not self.api_key:
            raise RevolutXAuthError(
                "REVOLUT_X_API_KEY manquant. Crée une clé dans Revolut X "
                "(menu grille → API keys → + New, permission Spot trade)."
            )

        # Clé privée : contenu PEM direct ou chemin vers fichier
        pem = private_key_pem or os.getenv("REVOLUT_X_PRIVATE_KEY_PEM")
        if not pem:
            path = private_key_path or os.getenv("REVOLUT_X_PRIVATE_KEY")
            if not path:
                raise RevolutXAuthError(
                    "Clé privée Ed25519 manquante. Définis "
                    "REVOLUT_X_PRIVATE_KEY (chemin) ou "
                    "REVOLUT_X_PRIVATE_KEY_PEM (contenu) dans .env"
                )
            path = os.path.expanduser(path)
            if not os.path.exists(path):
                raise RevolutXAuthError(f"Fichier clé privée introuvable : {path}")
            with open(path, "rb") as f:
                pem = f.read()

        if isinstance(pem, str):
            pem = pem.encode()

        try:
            self.private_key = serialization.load_pem_private_key(pem, password=None)
            if not isinstance(self.private_key, Ed25519PrivateKey):
                raise RevolutXAuthError(
                    "La clé n'est pas une clé Ed25519. Régénère avec : "
                    "openssl genpkey -algorithm ed25519 ..."
                )
        except (ValueError, UnsupportedAlgorithm) as e:
            raise RevolutXAuthError(f"Clé privée invalide : {e}")

        self.session = requests.Session()
        log.info("Client Revolut X initialisé (API key: %s...)", self.api_key[:6])

    # --- Signature -------------------------------------------------------

    def _sign(self, timestamp: str, method: str, full_path: str,
              query: str, body: str) -> str:
        """Signe le message canonique Revolut X en Ed25519, retourne base64.

        Message = concaténation DIRECTE (sans séparateur) de :
            timestamp + METHOD + /api/1.0/chemin + query + body
        full_path doit déjà inclure le préfixe /api/1.0.
        query est la query string sans le '?'. body est le JSON minifié.
        """
        message = f"{timestamp}{method}{full_path}{query}{body}".encode()
        signature = self.private_key.sign(message)
        return base64.b64encode(signature).decode()

    def _request(self, method: str, path: str, params=None, body=None,
                 public: bool = False):
        """Effectue une requête signée vers l'API Revolut X.

        path : chemin relatif après /api/1.0 (ex: 'balances', 'orders/active').
        params : dict de query params (pour GET).
        body : dict pour POST/PUT (sera sérialisé en JSON minifié).
        public : True pour les endpoints /public/* (pas de signature).
        """
        method = method.upper()
        full_path = f"{API_PREFIX}/{path.lstrip('/')}"
        url = f"{BASE_URL}{full_path}"

        # Corps JSON minifié (les bytes signés = bytes envoyés)
        body_str = ""
        if body is not None:
            body_str = json.dumps(body, separators=(",", ":"))

        # Query string sans le '?' (ordre stable)
        query_str = ""
        if params:
            params = {k: v for k, v in params.items() if v is not None}
            if params:
                query_str = urlencode(params)
                url = f"{url}?{query_str}"

        timestamp = str(int(time.time() * 1000))

        headers = {"Accept": "application/json"}
        if body_str:
            headers["Content-Type"] = "application/json"

        if not public:
            signature = self._sign(timestamp, method, full_path, query_str, body_str)
            headers["X-Revx-API-Key"] = self.api_key
            headers["X-Revx-Timestamp"] = timestamp
            headers["X-Revx-Signature"] = signature

        last_err = None
        for attempt in range(RETRY_ON_5XX + 1):
            try:
                resp = self.session.request(
                    method, url, data=body_str if body_str else None,
                    headers=headers, timeout=TIMEOUT,
                )
            except requests.RequestException as e:
                last_err = e
                if attempt < RETRY_ON_5XX:
                    time.sleep(0.8 * (attempt + 1))
                    continue
                raise RevolutXError(f"Erreur réseau : {e}")

            if resp.status_code == 429:
                raise RevolutXRateLimit(
                    "Rate limit (429). Réessaie dans quelques secondes."
                )
            if resp.status_code in (401, 403):
                raise RevolutXAuthError(
                    f"Auth refusée ({resp.status_code}). Vérifie la clé API "
                    f"et la clé privée. Détail : {resp.text[:200]}"
                )
            if 500 <= resp.status_code < 600:
                last_err = RevolutXError(
                    f"Erreur serveur {resp.status_code} : {resp.text[:200]}"
                )
                if attempt < RETRY_ON_5XX:
                    time.sleep(0.8 * (attempt + 1))
                    continue
                raise last_err

            if resp.status_code >= 400:
                raise RevolutXError(
                    f"HTTP {resp.status_code} sur {method} {full_path} : "
                    f"{resp.text[:300]}"
                )
            if not resp.content:
                return None
            try:
                return resp.json()
            except ValueError:
                return resp.text

        raise last_err or RevolutXError("Échec inconnu")

    # --- Lecture : soldes ------------------------------------------------

    def get_balances(self):
        """GET /balances — soldes du compte (toutes devises)."""
        return self._request("GET", "balances")

    def get_pairs(self):
        """GET /configuration/pairs — paires de trading disponibles."""
        return self._request("GET", "configuration/pairs")

    def get_currencies(self):
        """GET /configuration/currencies — devises supportées."""
        return self._request("GET", "configuration/currencies")

    def get_ticker(self, symbol: str = None):
        """GET /tickers — ticker d'une paire ou de toutes les paires.

        symbol au format Revolut X, ex: 'BTC-USD'. Si None, tous les tickers.
        """
        params = {"symbol": symbol} if symbol else None
        return self._request("GET", "tickers", params=params)

    def get_order_book(self, symbol: str, limit: int = None):
        """GET /order-book/{symbol} — carnet d'ordres (authentifié)."""
        params = {"limit": limit} if limit else None
        return self._request("GET", f"order-book/{symbol}", params=params)

    def get_public_order_book(self, symbol: str):
        """GET /public/order-book/{symbol} — carnet public (PAS d'auth)."""
        return self._request("GET", f"public/order-book/{symbol}", public=True)

    def get_candles(self, symbol: str):
        """GET /candles/{symbol} — bougies (authentifié)."""
        return self._request("GET", f"candles/{symbol}")

    def get_last_trades(self, symbol: str = None):
        """GET /public/last-trades — derniers trades (PAS d'auth)."""
        params = {"symbol": symbol} if symbol else None
        return self._request("GET", "public/last-trades", params=params, public=True)

    # --- Prix (helper simple) -------------------------------------------

    def get_price(self, symbol: str) -> float:
        """Retourne le dernier prix pour un symbole (ex: 'BTC-USD')."""
        data = self.get_ticker(symbol)
        # Structure exacte à confirmer selon la réponse réelle.
        entries = data if isinstance(data, list) else [data] if isinstance(data, dict) else []
        for entry in entries:
            if not isinstance(entry, dict):
                continue
            for key in ("last_price", "lastPrice", "last", "price"):
                if key in entry:
                    return float(entry[key])
            if "bid" in entry and "ask" in entry:
                return (float(entry["bid"]) + float(entry["ask"])) / 2
        raise RevolutXError(f"Prix introuvable dans la réponse ticker : {data}")

    # --- Ordres ----------------------------------------------------------

    def place_market_order(self, symbol: str, side: str, quote_size: float = None,
                           base_size: float = None, client_order_id: str = None):
        """POST /orders — ordre au marché.

        symbol : 'BTC-USD'
        side   : 'buy' ou 'sell'
        quote_size : montant en devise de cotation (USD), ex: 100 = 100$ de BTC
        base_size  : quantité en crypto (BTC), ex: 0.001
        Utiliser quote_size OU base_size (pas les deux).
        """
        market_cfg = {}
        if quote_size is not None:
            market_cfg["quote_size"] = str(quote_size)
        if base_size is not None:
            market_cfg["base_size"] = str(base_size)
        if not market_cfg:
            raise RevolutXOrderError("Spécifie quote_size ou base_size.")
        body = {
            "client_order_id": client_order_id or str(uuid.uuid4()),
            "symbol": symbol,
            "side": side.lower(),
            "order_configuration": {"market": market_cfg},
        }
        return self._place_order(body)

    def place_limit_order(self, symbol: str, side: str, price: float,
                          quote_size: float = None, base_size: float = None,
                          client_order_id: str = None):
        """POST /orders — ordre limit.

        price      : prix limite
        quote_size : montant en USD  (ou base_size en crypto)
        """
        limit_cfg = {"price": str(price)}
        if quote_size is not None:
            limit_cfg["quote_size"] = str(quote_size)
        if base_size is not None:
            limit_cfg["base_size"] = str(base_size)
        if "quote_size" not in limit_cfg and "base_size" not in limit_cfg:
            raise RevolutXOrderError("Spécifie quote_size ou base_size.")
        body = {
            "client_order_id": client_order_id or str(uuid.uuid4()),
            "symbol": symbol,
            "side": side.lower(),
            "order_configuration": {"limit": limit_cfg},
        }
        return self._place_order(body)

    def _place_order(self, body):
        """POST /orders. Lève RevolutXOrderError si échec."""
        try:
            return self._request("POST", "orders", body=body)
        except RevolutXError as e:
            raise RevolutXOrderError(str(e)) from e

    def get_active_orders(self):
        """GET /orders/active."""
        return self._request("GET", "orders/active")

    def get_historical_orders(self):
        """GET /orders/historical."""
        return self._request("GET", "orders/historical")

    def get_order(self, order_id: str):
        """GET /orders/{id}."""
        return self._request("GET", f"orders/{order_id}")

    def cancel_order(self, order_id: str):
        """DELETE /orders/{id}."""
        try:
            return self._request("DELETE", f"orders/{order_id}")
        except RevolutXError as e:
            raise RevolutXOrderError(str(e)) from e

    def cancel_all(self):
        """DELETE /orders — annule tous les ordres actifs."""
        try:
            return self._request("DELETE", "orders")
        except RevolutXError as e:
            raise RevolutXOrderError(str(e)) from e

    def get_order_fills(self, order_id: str):
        """GET /orders/fills/{id} — exécutions d'un ordre."""
        return self._request("GET", f"orders/fills/{order_id}")

    def get_trades(self, symbol: str):
        """GET /trades/all/{symbol} — tous trades pour un symbole."""
        return self._request("GET", f"trades/all/{symbol}")

    def get_private_trades(self, symbol: str):
        """GET /trades/private/{symbol} — trades privés."""
        return self._request("GET", f"trades/private/{symbol}")

    # --- Ping / test -----------------------------------------------------

    def ping(self):
        """Test de connexion — renvoie les soldes (lecture seule, safe)."""
        try:
            balances = self.get_balances()
            log.info("✓ Connexion OK. Soldes récupérés.")
            return True, balances
        except RevolutXAuthError as e:
            log.error("✗ Auth échouée : %s", e)
            return False, str(e)
        except RevolutXError as e:
            log.error("✗ Erreur : %s", e)
            return False, str(e)


# ---------------------------------------------------------------------------
# Mapping vers l'agent (symboles Binance → paires Revolut X)
# ---------------------------------------------------------------------------

# Revolut X utilise des symboles avec tiret : BTC-USD, ETH-USD, etc.
# L'agent utilise les symboles Binance (BTCUSDT). Ce mapping convertit.
BINANCE_TO_REVOLUTX = {
    "BTCUSDT": "BTC-USD",
    "ETHUSDT": "ETH-USD",
    "SOLUSDT": "SOL-USD",
    "BNBUSDT": "BNB-USD",
    "XRPUSDT": "XRP-USD",
}


def map_symbol(symbol: str) -> str:
    """Convertit un symbole Binance en symbole Revolut X (BTC-USD).

    Lève une erreur si la paire n'est pas supportée (ex: actifs non-crypto).
    """
    if symbol in BINANCE_TO_REVOLUTX:
        return BINANCE_TO_REVOLUTX[symbol]
    raise RevolutXError(
        f"Symbole {symbol} non supporté sur Revolut X (crypto uniquement). "
        f"Supportés : {list(BINANCE_TO_REVOLUTX.keys())}"
    )


# ---------------------------------------------------------------------------
# CLI de test
# ---------------------------------------------------------------------------

def main():
    import argparse
    p = argparse.ArgumentParser(description="Client Revolut X")
    sub = p.add_subparsers(dest="cmd")

    sub.add_parser("ping", help="Test de connexion (récupère les soldes)")
    sub.add_parser("balances", help="Affiche les soldes")
    sub.add_parser("pairs", help="Liste les paires disponibles")
    p_ticker = sub.add_parser("ticker", help="Prix d'un symbole")
    p_ticker.add_argument("symbol", nargs="?", help="ex: BTC-USD")
    p_book = sub.add_parser("book", help="Carnet d'ordres public (sans auth)")
    p_book.add_argument("symbol", help="ex: BTC-USD")
    sub.add_parser("orders", help="Ordres actifs")

    args = p.parse_args()
    if not args.cmd:
        p.print_help()
        return

    # Pour ping/balances/pairs/ticker/orders : auth requise
    try:
        client = RevolutX()
    except RevolutXError as e:
        print(f"❌ Impossible d'initialiser le client : {e}", file=sys.stderr)
        sys.exit(1)

    if args.cmd == "ping":
        ok, result = client.ping()
        print(json.dumps(result, indent=2) if ok else result)
    elif args.cmd == "balances":
        print(json.dumps(client.get_balances(), indent=2))
    elif args.cmd == "pairs":
        print(json.dumps(client.get_pairs(), indent=2))
    elif args.cmd == "ticker":
        print(json.dumps(client.get_ticker(args.symbol), indent=2))
    elif args.cmd == "book":
        print(json.dumps(client.get_public_order_book(args.symbol), indent=2))
    elif args.cmd == "orders":
        print(json.dumps(client.get_active_orders(), indent=2))


if __name__ == "__main__":
    main()
