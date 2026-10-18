#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""kraken_paper.py — Portefeuille VIRTUEL aux conditions reelles de Kraken Pro.

Aucune cle API, aucun ordre reel: on utilise uniquement les endpoints publics
(Ticker, AssetPairs). Chaque trade du bot est rejoue "comme si" il etait passe
sur Kraken:
  - achat au prix ASK Kraken (ordre marche = taker)
  - vente au prix BID Kraken
  - frais par palier Kraken Pro selon le volume 30 jours simule
    (TP = ordre limit pose a l'avance = maker ; SL / autres = taker)

But: savoir si la strategie survit aux frais et aux prix de Kraken AVANT de
mettre un seul euro reel. Journal: kraken_paper.json
"""
import json
import os
import time
from datetime import datetime, timedelta

import requests

DOSSIER = os.path.dirname(os.path.abspath(__file__))
FICHIER = os.path.join(DOSSIER, "kraken_paper.json")
CAPITAL_INITIAL = 1000.0
API = "https://api.kraken.com/0/public"

# Paliers Kraken Pro spot (volume 30j en USD -> maker %, taker %)
# Source: kraken.com/features/fee-schedule (octobre 2026)
PALIERS = [
    (0,        0.40, 0.80),
    (2_500,    0.30, 0.60),
    (10_000,   0.22, 0.38),
    (25_000,   0.20, 0.35),
    (50_000,   0.15, 0.30),
    (100_000,  0.12, 0.25),
    (250_000,  0.10, 0.22),
    (500_000,  0.08, 0.20),
    (1_000_000, 0.06, 0.18),
]
EUR_USD = 1.12  # approximation pour convertir le volume EUR en USD (palier)

_ALIAS = {"BTC": "XBT", "DOGE": "XDG"}
_PAIRES = {}      # base -> nom de paire Kraken (ex: BTC -> XXBTZEUR)
_PAIRES_TS = 0


def _charger():
    try:
        with open(FICHIER) as f:
            return json.load(f)
    except Exception:
        return {"capital_initial": CAPITAL_INITIAL, "liquidites": CAPITAL_INITIAL,
                "positions": [], "trades_fermes": [], "total_frais": 0.0,
                "cree_le": datetime.now().strftime("%Y-%m-%d %H:%M")}


def _sauver(d):
    tmp = FICHIER + ".tmp"
    with open(tmp, "w") as f:
        json.dump(d, f, indent=2, ensure_ascii=False)
    os.replace(tmp, FICHIER)


def _paires():
    """Charge (et met en cache 6h) la liste des paires EUR disponibles sur Kraken."""
    global _PAIRES, _PAIRES_TS
    if _PAIRES and time.time() - _PAIRES_TS < 6 * 3600:
        return _PAIRES
    try:
        r = requests.get(f"{API}/AssetPairs", timeout=15).json()
        res = {}
        for nom, v in r.get("result", {}).items():
            if v.get("quote") == "ZEUR" and v.get("status") == "online":
                ws = v.get("wsname", "")  # ex: XBT/EUR
                res[ws.split("/")[0]] = nom
        if res:
            _PAIRES, _PAIRES_TS = res, time.time()
    except Exception:
        pass
    return _PAIRES


def paire_kraken(symbole):
    """BTCUSDT -> XXBTZEUR (ou None si la crypto n'est pas sur Kraken en EUR)."""
    base = symbole.upper().replace("USDT", "").replace("EUR", "")
    base = _ALIAS.get(base, base)
    return _paires().get(base)


def ticker(symbole):
    """Retourne (bid, ask) Kraken en EUR, ou None."""
    p = paire_kraken(symbole)
    if not p:
        return None
    try:
        r = requests.get(f"{API}/Ticker", params={"pair": p}, timeout=10).json()
        v = list(r["result"].values())[0]
        return float(v["b"][0]), float(v["a"][0])
    except Exception:
        return None


# ---------------------------------------------------------------- glissement (slippage) realiste
SLIPPAGE_ALPHA = float(os.getenv("SLIPPAGE_ALPHA", "0.10"))   # % de glissement quand l'ordre = toute la profondeur a 0.5 %
SLIPPAGE_BETA = float(os.getenv("SLIPPAGE_BETA", "0.6"))       # exposant de la loi de puissance (0.5-0.8 dans la litterature)
_PROF_CACHE = {}


def profondeur_eur(symbole, pct=0.5):
    """Profondeur du carnet Kraken (EUR) a +/- pct % du milieu, cote ask et bid. Cache 60 s. None si indisponible."""
    import time as _t
    e = _PROF_CACHE.get(symbole)
    if e and _t.time() - e[0] < 60:
        return e[1]
    p = paire_kraken(symbole)
    if not p:
        return None
    try:
        r = requests.get(f"{API}/Depth", params={"pair": p, "count": 100}, timeout=8).json()
        res = list(r["result"].values())[0]
        asks, bids = res["asks"], res["bids"]
        mid = (float(asks[0][0]) + float(bids[0][0])) / 2
        out = {"ask": sum(float(a[0]) * float(a[1]) for a in asks if float(a[0]) <= mid * (1 + pct / 100)),
               "bid": sum(float(b[0]) * float(b[1]) for b in bids if float(b[0]) >= mid * (1 - pct / 100)), "mid": mid}
        _PROF_CACHE[symbole] = (_t.time(), out)
        return out
    except Exception:
        return None


def glissement_pct(symbole, montant_eur, cote="ask"):
    """Glissement estime en % : alpha x (Q / profondeur)^beta (loi de puissance, impact de marche).
    Ordre de 100 EUR dans 200 000 EUR de profondeur -> ~0.001 % ; 100 EUR dans 2 000 EUR -> ~0.02 % ; 0 si inconnu."""
    prof = profondeur_eur(symbole)
    if not prof or not prof.get(cote):
        return 0.0
    q = max(0.0, float(montant_eur)) / prof[cote]
    return round(SLIPPAGE_ALPHA * (q ** SLIPPAGE_BETA), 4)


def volume_30j_usd(d):
    seuil = datetime.now() - timedelta(days=30)
    vol = 0.0
    for t in d.get("trades_fermes", []):
        try:
            if datetime.strptime(t["date_fermeture"][:16], "%Y-%m-%d %H:%M") >= seuil:
                vol += t.get("montant_eur", 0) * 2  # achat + vente
        except Exception:
            continue
    for p in d.get("positions", []):
        vol += p.get("montant_eur", 0)
    return vol * EUR_USD


def frais_pct(d, maker):
    vol = volume_30j_usd(d)
    m, t = PALIERS[0][1], PALIERS[0][2]
    for seuil, mk, tk in PALIERS:
        if vol >= seuil:
            m, t = mk, tk
    return (m if maker else t), vol


# ---------------------------------------------------------------- hooks bot

def ouvrir_shadow(position):
    """Appele par le bot a l'ouverture d'une position crypto: rejoue l'achat sur Kraken."""
    try:
        sym = position.get("symbole", "")
        tk = ticker(sym)
        if not tk:
            print(f"  [KRAKEN-VIRTUEL] {sym}: pas sur Kraken en EUR -> ignore")
            return False
        bid, ask = tk
        d = _charger()
        montant = float(position.get("montant_eur", 0))
        if montant <= 0 or d["liquidites"] < montant:
            print(f"  [KRAKEN-VIRTUEL] {sym}: liquidites insuffisantes ({d['liquidites']:.0f}EUR)")
            return False
        pct, vol = frais_pct(d, maker=False)          # achat au marche = taker
        glis = glissement_pct(sym, montant, "ask")    # impact de marche selon la profondeur du carnet
        ask = ask * (1 + glis / 100)
        frais = montant * pct / 100
        qty = (montant - frais) / ask
        d["liquidites"] -= montant
        d["total_frais"] += frais
        d["positions"].append({
            "id": position.get("date_ouverture", "") + "|" + sym,
            "symbole": sym, "nom": position.get("nom", sym),
            "paire": paire_kraken(sym),
            "prix_entree": ask, "prix_bot": position.get("prix_entree"),
            "quantite": qty, "montant_eur": montant, "frais_entree": frais,
            "frais_pct_entree": pct,
            "date_ouverture": position.get("date_ouverture", datetime.now().strftime("%Y-%m-%d %H:%M")),
            "strategie": position.get("strategie", ""),
            "raison": position.get("signal_raison", ""),
        })
        _sauver(d)
        ecart = (ask - float(position.get("prix_entree") or ask)) / ask * 100
        print(f"  [KRAKEN-VIRTUEL] ACHAT {sym} @ {ask:.4f} (bot {position.get('prix_entree', 0):.4f}, {ecart:+.2f}%) | frais {pct:.2f}% = {frais:.2f}EUR | glissement {glis:.3f}% | palier vol30j ${vol:,.0f}")
        return True
    except Exception as e:
        print(f"  [KRAKEN-VIRTUEL] erreur ouverture: {e}")
        return False


def fermer_shadow(position, raison):
    """Appele par le bot a la fermeture: rejoue la vente sur Kraken."""
    try:
        sym = position.get("symbole", "")
        d = _charger()
        pid = position.get("date_ouverture", "") + "|" + sym
        idx = next((i for i, p in enumerate(d["positions"]) if p["id"] == pid), None)
        if idx is None:
            idx = next((i for i, p in enumerate(d["positions"]) if p["symbole"] == sym), None)
        if idx is None:
            return False
        p = d["positions"].pop(idx)
        tk = ticker(sym)
        if not tk:
            d["positions"].insert(idx, p)
            _sauver(d)
            return False
        bid, ask = tk
        maker = str(raison).startswith("TP")          # TP = limit pose a l'avance
        pct, vol = frais_pct(d, maker=maker)
        if not maker:                                  # vente au marche (stop, temps) : glissement selon la profondeur
            bid = bid * (1 - glissement_pct(sym, p["quantite"] * bid, "bid") / 100)
        brut = p["quantite"] * bid
        frais = brut * pct / 100
        net = brut - frais
        gain = net - p["montant_eur"]
        var = (bid - p["prix_entree"]) / p["prix_entree"] * 100
        d["liquidites"] += net
        d["total_frais"] += frais
        d["trades_fermes"].append({**p, "prix_sortie": bid, "raison": raison,
                                   "frais_sortie": frais, "frais_pct_sortie": pct,
                                   "maker_sortie": maker, "variation_pct": round(var, 3),
                                   "gain_eur": round(gain, 2),
                                   "date_fermeture": datetime.now().strftime("%Y-%m-%d %H:%M")})
        _sauver(d)
        print(f"  [KRAKEN-VIRTUEL] VENTE {sym} @ {bid:.4f} | var {var:+.2f}% | frais {pct:.2f}% ({'maker' if maker else 'taker'}) | net {gain:+.2f}EUR | capital {d['liquidites'] + sum(x['montant_eur'] for x in d['positions']):.2f}EUR")
        return True
    except Exception as e:
        print(f"  [KRAKEN-VIRTUEL] erreur fermeture: {e}")
        return False


# ---------------------------------------------------------------- bilan

def bilan(texte=True):
    d = _charger()
    t = d.get("trades_fermes", [])
    g = [x for x in t if x.get("gain_eur", 0) > 0]
    net = sum(x.get("gain_eur", 0) for x in t)
    frais = d.get("total_frais", 0)
    capital = d["liquidites"] + sum(p["montant_eur"] for p in d["positions"])
    pct, vol = frais_pct(d, maker=False)
    res = {"capital": round(capital, 2), "net": round(net, 2), "trades": len(t),
           "gagnants": len(g), "wr": round(100 * len(g) / len(t)) if t else 0,
           "frais": round(frais, 2), "positions": len(d["positions"]),
           "palier_taker": pct, "vol30j_usd": round(vol)}
    if not texte:
        return res
    lignes = [
        "=== KRAKEN VIRTUEL (conditions reelles, 0 ordre reel) ===",
        f"Capital: {res['capital']:.2f} EUR (depart {d['capital_initial']:.0f}) | net {res['net']:+.2f} EUR",
        f"Trades: {res['trades']} | gagnants {res['gagnants']} | WR {res['wr']}% | frais payes {res['frais']:.2f} EUR",
        f"Palier actuel: taker {res['palier_taker']:.2f}% (volume 30j ${res['vol30j_usd']:,})",
        f"Positions ouvertes: {res['positions']}",
    ]
    for x in t[-8:]:
        lignes.append(f"  {x['date_fermeture'][5:16]} {x['symbole']:9s} {x['raison'][:14]:14s} {x['variation_pct']:+.2f}% frais {x['frais_entree']+x['frais_sortie']:.2f} net {x['gain_eur']:+.2f}")
    return "\n".join(lignes)


if __name__ == "__main__":
    print(bilan())
