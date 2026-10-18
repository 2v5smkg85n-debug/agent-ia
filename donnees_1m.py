#!/usr/bin/env python3
"""
donnees_1m.py — historique 1 minute gratuit et complet depuis Binance Vision (data.binance.vision).

Fichiers : https://data.binance.vision/data/spot/monthly/klines/<SYM>/1m/<SYM>-1m-YYYY-MM.zip  (~2 Mo / mois / symbole)
           https://data.binance.vision/data/spot/daily/klines/<SYM>/1m/<SYM>-1m-YYYY-MM-DD.zip  (mois en cours)
Colonnes : open_time, open, high, low, close, volume, close_time, quote_volume, trades, taker_buy_base, taker_buy_quote, ignore
Attention : depuis 2025 les fichiers spot ont des timestamps en MICROsecondes (16 chiffres) -> normalises ici en millisecondes.

Stockage local : data/1m/<SYM>/YYYY-MM.csv.gz (ts_ms,o,h,l,c,v,taker_buy_base) — stdlib uniquement.
Usage : python3 donnees_1m.py BTCUSDT ETHUSDT --mois 4        (telecharge les 4 derniers mois + les jours du mois courant)
        python3 donnees_1m.py --tous --mois 4                  (tous les symboles de MARCHES_PAPER)
"""
import csv
import gzip
import io
import os
import sys
import time
import zipfile
from datetime import datetime, timedelta, timezone

DOSSIER = os.path.dirname(os.path.abspath(__file__))
DATA = os.path.join(DOSSIER, "data", "1m")
BASE = "https://data.binance.vision/data/spot"
_CACHE = {}


def _norm_ts(v):
    v = int(v)
    return v // 1000 if v > 10 ** 14 else v      # us -> ms


def _telecharger_zip(url):
    import requests
    for tentative in range(3):
        try:
            r = requests.get(url, timeout=60)
            if r.status_code == 404:
                return None
            if r.status_code == 200:
                return r.content
        except Exception:
            time.sleep(2)
    return None


def _parser(contenu_zip):
    z = zipfile.ZipFile(io.BytesIO(contenu_zip))
    nom = z.namelist()[0]
    lignes = []
    for row in csv.reader(io.TextIOWrapper(z.open(nom), encoding="utf-8")):
        if not row or not row[0].isdigit():
            continue
        lignes.append((_norm_ts(row[0]), float(row[1]), float(row[2]), float(row[3]), float(row[4]), float(row[5]),
                       float(row[9]) if len(row) > 9 else 0.0))
    return lignes


def _ecrire(sym, mois, lignes):
    os.makedirs(os.path.join(DATA, sym), exist_ok=True)
    chemin = os.path.join(DATA, sym, f"{mois}.csv.gz")
    tmp = chemin + ".tmp"
    with gzip.open(tmp, "wt", newline="") as f:
        w = csv.writer(f)
        for l in sorted(set(lignes)):
            w.writerow(l)
    os.replace(tmp, chemin)
    return chemin


def telecharger_mois(sym, annee, mois_num, forcer=False):
    mois = f"{annee:04d}-{mois_num:02d}"
    chemin = os.path.join(DATA, sym, f"{mois}.csv.gz")
    now = datetime.now(timezone.utc)
    courant = (annee, mois_num) == (now.year, now.month)
    if os.path.exists(chemin) and not forcer and not courant:
        return chemin, "deja present"
    if not courant:
        z = _telecharger_zip(f"{BASE}/monthly/klines/{sym}/1m/{sym}-1m-{mois}.zip")
        if z:
            return _ecrire(sym, mois, _parser(z)), "mensuel"
    # mois en cours (ou mensuel absent) : fichiers journaliers
    lignes = []
    jour = datetime(annee, mois_num, 1, tzinfo=timezone.utc)
    fin = min(now - timedelta(days=1), (jour + timedelta(days=32)).replace(day=1) - timedelta(days=1))
    while jour <= fin:
        z = _telecharger_zip(f"{BASE}/daily/klines/{sym}/1m/{sym}-1m-{jour.strftime('%Y-%m-%d')}.zip")
        if z:
            lignes += _parser(z)
        jour += timedelta(days=1)
    if not lignes:
        return None, "introuvable (symbole absent de Binance ?)"
    return _ecrire(sym, mois, lignes), f"journalier ({len(lignes)} bougies)"


def telecharger(sym, nb_mois=4, forcer=False, verbose=True):
    now = datetime.now(timezone.utc)
    res = []
    for i in range(nb_mois, -1, -1):
        d = (now.replace(day=1) - timedelta(days=28 * i)).replace(day=1)
        chemin, statut = telecharger_mois(sym, d.year, d.month, forcer)
        if verbose:
            print(f"  {sym} {d.year}-{d.month:02d}: {statut}")
        res.append((chemin, statut))
    return res


def charger(sym, debut_ms=None, fin_ms=None):
    """Liste triee de tuples (ts_ms, o, h, l, c, v, taker_buy) entre debut et fin (ms UTC)."""
    dossier = os.path.join(DATA, sym)
    if not os.path.isdir(dossier):
        return []
    out = []
    for nom in sorted(os.listdir(dossier)):
        if not nom.endswith(".csv.gz"):
            continue
        mois = nom[:-7]
        if debut_ms and mois < datetime.fromtimestamp(debut_ms / 1000, timezone.utc).strftime("%Y-%m"):
            continue
        if fin_ms and mois > datetime.fromtimestamp(fin_ms / 1000, timezone.utc).strftime("%Y-%m"):
            continue
        cle = (sym, nom)
        if cle not in _CACHE:
            with gzip.open(os.path.join(dossier, nom), "rt") as f:
                _CACHE[cle] = [tuple(float(x) if i else int(x) for i, x in enumerate(row)) for row in csv.reader(f)]
        out += _CACHE[cle]
    if debut_ms or fin_ms:
        out = [r for r in out if (not debut_ms or r[0] >= debut_ms) and (not fin_ms or r[0] <= fin_ms)]
    return out


def resample(bougies_1m, minutes=60):
    """Agrege des bougies 1m en bougies de `minutes` (dicts temps/ouverture/haut/bas/cloture/volume, temps en secondes)."""
    out, bloc = [], None
    pas = minutes * 60 * 1000
    for ts, o, h, l, c, v, *_ in bougies_1m:
        debut = ts - ts % pas
        if bloc is None or bloc["temps"] != debut // 1000:
            if bloc:
                out.append(bloc)
            bloc = {"temps": debut // 1000, "ouverture": o, "haut": h, "bas": l, "cloture": c, "volume": v}
        else:
            bloc["haut"] = max(bloc["haut"], h); bloc["bas"] = min(bloc["bas"], l); bloc["cloture"] = c; bloc["volume"] += v
    if bloc:
        out.append(bloc)
    return out


def symboles_du_bot():
    try:
        import re
        c = open(os.path.join(DOSSIER, "paper_trading.py")).read()
        i = c.find("MARCHES_PAPER = {")
        return list(dict.fromkeys(re.findall(r'"([A-Z]+USDT)"', c[i:i + 8000])))
    except Exception:
        return ["BTCUSDT", "ETHUSDT", "SOLUSDT"]


if __name__ == "__main__":
    args = [a for a in sys.argv[1:] if not a.startswith("--")]
    nb = 4
    if "--mois" in sys.argv:
        nb = int(sys.argv[sys.argv.index("--mois") + 1])
        args = [a for a in args if a != str(nb)]
    syms = symboles_du_bot() if "--tous" in sys.argv else (args or ["BTCUSDT", "ETHUSDT"])
    print(f"Telechargement 1m Binance Vision : {len(syms)} symbole(s), {nb} mois + mois courant -> {DATA}")
    for s in syms:
        telecharger(s, nb, forcer="--forcer" in sys.argv)
    b = charger(syms[0])
    print(f"{syms[0]}: {len(b)} bougies 1m chargees, {len(resample(b, 60))} bougies 1h")
