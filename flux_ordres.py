#!/usr/bin/env python3
"""
flux_ordres.py — desequilibre du flux d'ordres (Trade Flow Imbalance) depuis les trades publics Kraken.

Kraken GET /0/public/Trades?pair=XXBTZEUR renvoie jusqu'a 1 000 derniers trades avec, pour chacun,
[prix, volume, temps, cote 'b'/'s', type 'm'/'l', misc, id]. Le TFI sur N minutes vaut
    (volume achete - volume vendu) / (volume total)   dans [-1, +1].
Un TFI < -0.3 signifie que les vendeurs agressifs dominent : mauvais moment pour acheter.
Cache 60 s par symbole. Retourne None si Kraken ne repond pas (la porte laisse alors passer).
"""
import os
import time

DOSSIER = os.path.dirname(os.path.abspath(__file__))
_CACHE = {}


def trades_recents(sym, minutes=30):
    """Liste de (temps, prix, volume, cote) des `minutes` dernieres minutes, ou None."""
    try:
        import requests
        import kraken_paper as kp
        paire = kp.paire_kraken(sym)
        if not paire:
            return None
        depuis = int((time.time() - minutes * 60) * 1e9)      # 'since' en nanosecondes
        r = requests.get(f"{kp.API}/Trades", params={"pair": paire, "since": depuis}, timeout=8).json()
        if r.get("error"):
            return None
        res = r["result"]
        lst = next((v for k, v in res.items() if k != "last"), [])
        return [(float(t[2]), float(t[0]), float(t[1]), t[3]) for t in lst]
    except Exception:
        return None


def tfi(sym, minutes=30):
    """Trade Flow Imbalance en volume (base) sur `minutes` minutes, dans [-1, 1], ou None."""
    cle = (sym, minutes)
    e = _CACHE.get(cle)
    if e and time.time() - e[0] < 60:
        return e[1]
    tr = trades_recents(sym, minutes)
    val = None
    if tr:
        achat = sum(v for _, _, v, c in tr if c == "b")
        vente = sum(v for _, _, v, c in tr if c == "s")
        tot = achat + vente
        val = round((achat - vente) / tot, 3) if tot > 0 else None
    _CACHE[cle] = (time.time(), val)
    return val


def resume(sym):
    """Pour l'IA : TFI 5/30 min + nombre de trades."""
    tr = trades_recents(sym, 30) or []
    if not tr:
        return f"{sym}: flux d'ordres indisponible"
    now = time.time()
    def _tfi(sec):
        a = sum(v for t, _, v, c in tr if c == "b" and now - t <= sec)
        s = sum(v for t, _, v, c in tr if c == "s" and now - t <= sec)
        return round((a - s) / (a + s), 2) if a + s > 0 else None
    return f"{sym}: TFI 5min {_tfi(300)} | 30min {_tfi(1800)} | {len(tr)} trades Kraken en 30 min"


if __name__ == "__main__":
    import sys
    for s in (sys.argv[1:] or ["BTCUSDT", "ETHUSDT", "SOLUSDT"]):
        print(resume(s))
