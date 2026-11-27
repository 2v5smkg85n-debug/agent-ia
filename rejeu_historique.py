#!/usr/bin/env python3
"""
rejeu_historique.py — rejoue les VRAIES strategies du bot sur des annees de bougies Kraken (27/11/2026).

OBSERVATION SEULE. Ce module n'ouvre rien, ne bloque rien, ne modifie aucun reglage et ne donne aucun droit :
il tourne dans son propre processus, hors ligne une fois les bougies telechargees, et n'ecrit que dans
rejeu_data/, rejeu_etat.json, rejeu_bilan.txt et rejeu_bilan.json. Un bon resultat ici n'autorise rien :
c'est une piece de plus au dossier, la decision reste commune. Couper : REJEU=0 dans .env.

Pourquoi : le bot juge ses strategies sur quelques jours (128 notes en 10 jours le 27/11). Dix jours ne
contiennent qu'un seul marche. Kraken publie l'historique complet de ses bougies ; on y rejoue le code du bot,
tel qu'il est, sur plusieurs marches haussiers et baissiers.

Ce qui est rejoue, avec le code du bot et non une copie :
    - signaux techniques : indicateurs.analyser_actif (bougies 1 h + 4 h), signal si score >= 1, noms de
      strategies par paper_trading._strategies_detectees (lu dans le fichier, paper_trading n'est pas importe) ;
    - stop : stop_atr.atr_pct + stop_atr.stop_pct (2 x ATR, 2,5 en session americaine, bornes SL_MIN / SL_MAX) ;
    - tendance : strategies_tendance.donchian / tsmom et leurs sorties propres ;
    - tendance_multi (nouveau, rejeu seul) : strategies_tendance.score_tendance passe a 7 canaux haussiers sur 9
      ou plus alors qu'il etait en dessous la veille ; sortie a 4 sur 9 ou moins. Regle fixee avant tout resultat.
Jugement = convention du laboratoire (laboratoire.jouer) : entree a l'ouverture de la bougie suivante, stop et
objectif (stop x TP_RATIO), barriere de 24 h, stop et objectif dans la meme bougie = stop, frais aller-retour
retires, un essai par (strategie, crypto) toutes les 24 h + decalage de 0 a 4 h.
Tendance : objectif 3 x stop, barriere 168 h, sortie propre ; le stop suiveur n'est pas rejoue.

Mesures ajoutees :
    - ordres limite (deux variantes fixees a l'avance, valables 3 h) : au cours de cloture du signal, et
      0,25 ATR plus bas ; servi seulement si le cours passe STRICTEMENT sous le prix ; frais 0,1 % ;
    - episodes de baisse (meme definition que la garde de la porte : BTC sous son EMA 84 jours ou EMA en baisse) ;
    - garde-fous : intervalle par grappes journalieres, tableau par annee, ratio de Sharpe degonfle
      (Bailey & Lopez de Prado 2014), probabilite de surapprentissage par CSCV (Bailey et al. 2017).

Limites a garder en tete : bougies sans carnet (ni ecart achat-vente ni file d'attente) ; prix Kraken en euros
et non Revolut X ; decisions prises sur des bougies closes (en reel le bot voit la bougie en cours) ; seuils
actuels de strat_params.json ; ia_autonome et les professeurs externes ne sont pas rejouables ; la porte
d'entree (cadence, chaleur, garde de baisse) n'est pas rejouee : on mesure les strategies nues.

Commandes :
    python3 rejeu_historique.py tout          telecharge, rejoue, calcule le bilan, puis lance rejeu_modeles.py
    python3 rejeu_historique.py bilan         relit le bilan (ajouter « detail » pour les tableaux par annee)
    python3 rejeu_historique.py etat          avancement
Donnees : https://support.kraken.com/articles/360047124832
"""
import ast
import csv
import io
import itertools
import json
import math
import os
import statistics
import sys
import time
import zipfile
from datetime import datetime, timezone

DOSSIER = os.path.dirname(os.path.abspath(__file__))
DATA = os.path.join(DOSSIER, "rejeu_data")
BRUT = os.path.join(DATA, "brut")
TRADES = os.path.join(DATA, "trades")
SIGNAUX = os.path.join(DATA, "signaux")
CONTEXTE = os.path.join(DATA, "btc_contexte.csv")
ETAT = os.path.join(DOSSIER, "rejeu_etat.json")
BILAN_TXT = os.path.join(DOSSIER, "rejeu_bilan.txt")
BILAN_JSON = os.path.join(DOSSIER, "rejeu_bilan.json")
MODELES_JSON = os.path.join(DOSSIER, "rejeu_modeles.json")
VERROU = os.path.join(DOSSIER, "rejeu.lock")
VERSION = 1

URL = "https://assets.kraken.com/marketing/institutions/Kraken_OHLCVT_Full.zip.part%02d"
AGENT = "curl/8.5.0"          # le serveur refuse les requetes sans en-tete User-Agent

CRYPTOS_DEFAUT = [
    "BTCUSDT", "ETHUSDT", "SOLUSDT", "BNBUSDT", "XRPUSDT", "ADAUSDT", "DOGEUSDT", "AVAXUSDT", "DOTUSDT", "LTCUSDT",
    "TRXUSDT", "ARBUSDT", "NEARUSDT", "AAVEUSDT", "PENDLEUSDT", "SHIBUSDT", "ALGOUSDT", "ICPUSDT", "XLMUSDT", "INJUSDT",
    "SEIUSDT", "TIAUSDT", "CRVUSDT", "WIFUSDT", "FETUSDT", "LDOUSDT", "FILUSDT", "ETCUSDT", "OPUSDT", "SUIUSDT",
    "APTUSDT", "PEPEUSDT", "LINKUSDT", "UNIUSDT", "ATOMUSDT", "FLOKIUSDT", "RNDRUSDT",
]
ALIAS = {"BTC": ["XBT"], "DOGE": ["XDG"], "RNDR": ["RNDR", "RENDER"]}     # noms Kraken ; RNDR est devenu RENDER en 2024

TECH = ["rsi_oversold", "pattern_reversal", "volume_spike", "bollinger_bounce", "divergence_rsi", "macd_cross",
        "vwap_bounce", "momentum", "breakout", "sma_trend", "technique"]
TENDANCE = ["donchian_breakout", "tsmom", "tendance_multi"]
MULTI_ENTREE, MULTI_SORTIE = 7, 4          # tendance_multi : entree a >= 7 canaux sur 9, sortie a <= 4
LIMITE_VALIDITE_H = 3
LIMITE_RECUL_ATR = 0.25
CHAUFFE_J = 420                            # jours charges avant REJEU_DEPUIS pour amorcer les moyennes longues
EPISODE_FUSION_J = 10
EPISODE_N_MIN = 20
EPISODE_JOURS_MIN = 7
Z = 2.0

FEATURES = ["rsi", "d_sma20", "sma_2050", "macd_h", "bb_pos", "bb_larg", "vol_ratio", "ret1", "ret4", "ret24", "ret168",
            "vides24", "lvol24", "heure", "jsem", "htf", "btc_ecart", "btc_pente", "btc_ret24", "tend9"]
COLONNES = ["sym", "ts", "strat", "rang", "nb", "score", "sens", "pat", "atr", "sl", "res", "r_brut", "r", "h", "baisse",
            "l0", "l0_r", "l25", "l25_r"] + FEATURES


# ------------------------------------------------------------------ reglages
def _env(nom, defaut):
    try:
        from config_env import lire
        v = lire(nom, None)
        if v not in (None, ""):
            return v
    except Exception:
        pass
    return os.getenv(nom, defaut)


def actif():
    return str(_env("REJEU", "1")).strip().lower() not in ("0", "false", "non", "off")


def depuis_ts():
    try:
        d = datetime.strptime(str(_env("REJEU_DEPUIS", "2018-01-01"))[:10], "%Y-%m-%d")
    except Exception:
        d = datetime(2018, 1, 1)
    return int(d.replace(tzinfo=timezone.utc).timestamp())


def vides_max():
    try:
        return int(_env("REJEU_VIDES_MAX", "6"))
    except Exception:
        return 6


def frais_limite():
    try:
        return float(_env("REJEU_FRAIS_LIMITE_AR", "0.1"))
    except Exception:
        return 0.1


def cryptos():
    try:
        if DOSSIER not in sys.path:
            sys.path.insert(0, DOSSIER)
        import historique_crypto as hc
        return list(hc.CRYPTOS)
    except Exception:
        return list(CRYPTOS_DEFAUT)


def fichiers_kraken(sym):
    base = sym[:-4] if sym.endswith("USDT") else sym
    return [f"{b}EUR_60.csv" for b in ALIAS.get(base, [base])]


def _jour(ts):
    return time.strftime("%Y-%m-%d", time.gmtime(ts))


def _sauver_etat(**maj):
    try:
        d = etat()
        d.update(maj)
        d["maj"] = time.strftime("%Y-%m-%d %H:%M UTC", time.gmtime())
        with open(ETAT + ".tmp", "w") as f:
            json.dump(d, f, indent=1, ensure_ascii=False)
        os.replace(ETAT + ".tmp", ETAT)
    except Exception:
        pass


def etat():
    try:
        with open(ETAT) as f:
            d = json.load(f)
        return d if isinstance(d, dict) else {}
    except Exception:
        return {}


# ------------------------------------------------------------------ archive Kraken lue a distance
class ZipDistant(io.RawIOBase):
    """Fichier en lecture seule reparti sur plusieurs adresses, lu par morceaux (requetes Range).
    L'archive Kraken pese 9,5 Go ; on n'en lit que la table des matieres et les fichiers voulus."""

    def __init__(self, urls, bloc=1 << 20):
        super().__init__()
        self.urls, self.bloc, self.pos, self.cache, self.octets, self.requetes = list(urls), bloc, 0, {}, 0, 0
        self.tailles = [self._taille(u) for u in self.urls]
        self.total = sum(self.tailles)

    def _ouvrir(self, requete, delai):
        import urllib.request
        derniere = None
        for essai in range(4):
            try:
                return urllib.request.urlopen(requete, timeout=delai)
            except Exception as e:
                derniere = e
                time.sleep(2 + 3 * essai)
        raise derniere

    def _taille(self, u):
        import urllib.request
        with self._ouvrir(urllib.request.Request(u, method="HEAD", headers={"User-Agent": AGENT}), 30) as r:
            return int(r.headers["Content-Length"])

    def seekable(self):
        return True

    def readable(self):
        return True

    def tell(self):
        return self.pos

    def seek(self, off, whence=0):
        self.pos = off if whence == 0 else self.pos + off if whence == 1 else self.total + off
        return self.pos

    def _plage(self, deb, fin):
        import urllib.request
        out, base = b"", 0
        for u, t in zip(self.urls, self.tailles):
            a, b = max(deb, base), min(fin, base + t)
            if a < b:
                rq = urllib.request.Request(u, headers={"User-Agent": AGENT, "Range": f"bytes={a - base}-{b - base - 1}"})
                with self._ouvrir(rq, 120) as r:
                    d = r.read()
                if len(d) != b - a:
                    raise IOError("le serveur n'a pas respecte la plage demandee")
                out += d
                self.octets += len(d)
                self.requetes += 1
            base += t
        return out

    def _bloc(self, i):
        if i not in self.cache:
            if len(self.cache) > 12:
                self.cache.pop(next(iter(self.cache)))
            self.cache[i] = self._plage(i * self.bloc, min(self.total, (i + 1) * self.bloc))
        return self.cache[i]

    def read(self, n=-1):
        if n is None or n < 0:
            n = self.total - self.pos
        n = max(0, min(n, self.total - self.pos))
        out = []
        while n > 0:
            i, o = divmod(self.pos, self.bloc)
            d = self._bloc(i)[o:o + n]
            if not d:
                break
            out.append(d)
            self.pos += len(d)
            n -= len(d)
        return b"".join(out)

    def readinto(self, b):
        d = self.read(len(b))
        b[:len(d)] = d
        return len(d)


def telecharger(syms=None, journal=print):
    """Telecharge dans rejeu_data/brut les bougies 1 h manquantes. Renvoie le nombre de fichiers ecrits."""
    os.makedirs(BRUT, exist_ok=True)
    voulus = [n for s in (syms or cryptos()) for n in fichiers_kraken(s)]
    manquants = [n for n in voulus if not os.path.exists(os.path.join(BRUT, n))]
    if not manquants:
        return 0
    modele = str(_env("REJEU_URL", URL))
    parties = int(_env("REJEU_PARTIES", "5"))
    z = ZipDistant([modele % i for i in range(parties)])
    zf = zipfile.ZipFile(z)
    index = {os.path.basename(n): n for n in zf.namelist()}
    ecrits = 0
    for n in manquants:
        if n not in index:
            journal(f"  absent de l'archive Kraken : {n}")
            continue
        d = zf.read(index[n])
        with open(os.path.join(BRUT, n + ".tmp"), "wb") as f:
            f.write(d)
        os.replace(os.path.join(BRUT, n + ".tmp"), os.path.join(BRUT, n))
        ecrits += 1
        _sauver_etat(phase="telechargement", telecharges=ecrits, a_telecharger=len(manquants))
    journal(f"  {ecrits} fichiers telecharges ({z.octets >> 20} Mo lus sur {z.total >> 20} Mo, {z.requetes} requetes)")
    return ecrits


def couper_reseau():
    """Apres le telechargement, plus aucune connexion n'est possible depuis ce processus ni ses enfants :
    si un module du bot tentait un appel reseau pendant le rejeu, il echouerait au lieu de fausser la mesure."""
    import socket

    def _refus(*a, **k):
        raise OSError("reseau coupe pendant le rejeu (mesure hors ligne)")
    socket.socket.connect = _refus
    socket.socket.connect_ex = _refus
    socket.create_connection = _refus
    socket.getaddrinfo = _refus


# ------------------------------------------------------------------ bougies
def _lire_brut(sym):
    d = {}
    for n in fichiers_kraken(sym):
        try:
            with open(os.path.join(BRUT, n), newline="") as f:
                for l in csv.reader(f):
                    try:
                        t = int(float(l[0]))
                        d[t - t % 3600] = (float(l[1]), float(l[2]), float(l[3]), float(l[4]), float(l[5]))
                    except Exception:
                        continue
        except OSError:
            continue
    return d


def charger_bougies(sym, depuis=None):
    """Serie horaire CONTINUE qui commence a minuit UTC : les heures sans echange (absentes du fichier Kraken)
    deviennent des bougies plates de volume nul. Renvoie None si moins de 60 jours.
    {'t0', 'O', 'H', 'L', 'C', 'V', 'vide'} ; la bougie i commence a t0 + 3600 i."""
    brut = _lire_brut(sym)
    if not brut:
        return None
    depuis = depuis_ts() if depuis is None else depuis
    cles = sorted(brut)
    debut = max(cles[0], depuis - CHAUFFE_J * 86400)
    premier = next((t for t in cles if t >= debut), None)
    if premier is None:
        return None
    t0 = premier + (-premier) % 86400
    fin = cles[-1]
    if fin - t0 < 60 * 86400:
        return None
    avant = [t for t in cles if t < t0]
    c_prec = brut[avant[-1]][3] if avant else None
    O, H, L, C, V, vide = [], [], [], [], [], []
    for t in range(t0, fin + 1, 3600):
        b = brut.get(t)
        if b is None:
            if c_prec is None:
                c_prec = brut[next(x for x in cles if x >= t)][0]
            b, v = (c_prec, c_prec, c_prec, c_prec, 0.0), 1
        else:
            v = 0
        O.append(b[0]); H.append(b[1]); L.append(b[2]); C.append(b[3]); V.append(b[4]); vide.append(v)
        c_prec = b[3]
    return {"t0": t0, "O": O, "H": H, "L": L, "C": C, "V": V, "vide": vide}


def _agreger(B, a, b):
    """Bougie composee des bougies 1 h d'indices a..b inclus (format du bot)."""
    return {"temps": B[a]["temps"], "ouverture": B[a]["ouverture"], "haut": max(x["haut"] for x in B[a:b + 1]),
            "bas": min(x["bas"] for x in B[a:b + 1]), "cloture": B[b]["cloture"], "volume": sum(x["volume"] for x in B[a:b + 1])}


class Serie:
    """Bougies d'une crypto au format du bot, avec les vues 4 h et 1 jour « comme en direct » : a l'indice i on ne
    voit que les bougies 1 h closes jusqu'a i, et la derniere bougie 4 h / jour est partielle si elle n'est pas finie."""

    def __init__(self, d):
        self.t0, self.O, self.H, self.L, self.C, self.V, self.vide = d["t0"], d["O"], d["H"], d["L"], d["C"], d["V"], d["vide"]
        self.n = len(self.C)
        self.B = [{"temps": (self.t0 + 3600 * i) * 1000, "ouverture": self.O[i], "haut": self.H[i], "bas": self.L[i],
                   "cloture": self.C[i], "volume": self.V[i]} for i in range(self.n)]
        self.Q = [_agreger(self.B, 4 * k, 4 * k + 3) for k in range(self.n // 4)]
        self.D = [_agreger(self.B, 24 * k, 24 * k + 23) for k in range(self.n // 24)]
        self.cv = [0]
        for v in self.vide:
            self.cv.append(self.cv[-1] + v)

    def ts(self, i):
        """Instant de decision : la cloture de la bougie i."""
        return self.t0 + 3600 * (i + 1)

    def h1(self, i, limite=200):
        return self.B[max(0, i - limite + 1): i + 1]

    def h4(self, i, limite=60):
        k = i // 4
        if i % 4 == 3:
            return self.Q[max(0, k - limite + 1): k + 1]
        return self.Q[max(0, k - limite + 1): k] + [_agreger(self.B, 4 * k, i)]

    def j1(self, i, limite=400):
        k = i // 24
        if i % 24 == 23:
            return self.D[max(0, k - limite + 1): k + 1]
        return self.D[max(0, k - limite + 1): k] + [_agreger(self.B, 24 * k, i)]

    def vides(self, i, n=24):
        return self.cv[i + 1] - self.cv[max(0, i + 1 - n)]


# ------------------------------------------------------------------ le code du bot, branche sur l'historique
_M = {}


def moteur():
    """Charge les modules du bot et remplace leur source de bougies par la serie historique courante."""
    if _M:
        return _M
    if DOSSIER not in sys.path:
        sys.path.insert(0, DOSSIER)
    import indicateurs as ind
    import stop_atr as sa
    import strategies_tendance as st
    with open(os.path.join(DOSSIER, "paper_trading.py"), encoding="utf-8") as f:
        arbre = ast.parse(f.read())
    fonction = next(n for n in arbre.body if isinstance(n, ast.FunctionDef) and n.name == "_strategies_detectees")
    espace = {}
    exec(compile(ast.Module(body=[fonction], type_ignores=[]), "paper_trading.py", "exec"), espace)
    cur = {"s": None, "i": 0}

    def bougies_historiques(symbole="BTCUSDT", intervalle="1h", limite=200):
        s, i = cur["s"], cur["i"]
        if s is None:
            return []
        if intervalle == "1h":
            return s.h1(i, limite)
        if intervalle == "4h":
            return s.h4(i, limite)
        if intervalle == "1d":
            return s.j1(i, limite)
        return []

    ind.historique_ohlcv = bougies_historiques
    st._bougies = lambda sym, intervalle, n: bougies_historiques(sym, intervalle, n)
    _M.update({"ind": ind, "sa": sa, "st": st, "detectees": espace["_strategies_detectees"], "cur": cur})
    return _M


def signature():
    """Reglages dont depend le rejeu : s'ils changent, les cryptos deja rejouees sont recalculees."""
    m = moteur()
    sa, st = m["sa"], m["st"]
    try:
        sp = {k: v for k, v in m["ind"]._strat_params().items() if k in ("rsi_achat", "rsi_vente", "bb_ecart")}
    except Exception:
        sp = {}
    return {"version": VERSION, "depuis": depuis_ts(), "vides_max": vides_max(), "frais_limite": frais_limite(),
            "stop": [sa.ATR_MULT, sa.ATR_MULT_US, sa.SL_MIN, sa.SL_MAX, sa.TP_RATIO, sa.BARRIERE_H, sa.FRAIS_AR_PCT],
            "tendance": [st.DONCHIAN_ENTREE, st.DONCHIAN_SORTIE, st.DONCHIAN_VOL, st.EMA_JOURS, st.TSMOM_COURT, st.TSMOM_LONG,
                         st.TSMOM_SMA, st.TSMOM_FRAICHEUR, st.TP_RATIO, st.BARRIERE_H], "strat_params": sp}


# ------------------------------------------------------------------ jugement
def jouer(s, i, sl, ratio, heures, frais, prix=None):
    """Trade virtuel decide a la cloture de la bougie i (meme convention que laboratoire.jouer).
    Renvoie None si l'historique ne couvre pas la barriere, sinon (resultat, r_brut, r_net, heures_tenues)."""
    j0 = i + 1
    if j0 + heures > s.n:
        return None
    ref = s.O[j0]
    if ref <= 0:
        return None
    if prix and abs(ref / prix - 1) > 0.10:
        return ("ecart", 0.0, 0.0, 0)
    tp = sl * ratio
    stop, objectif = ref * (1 - sl / 100), ref * (1 + tp / 100)
    res, tenu = "neutre", heures
    L, H = s.L, s.H
    for j in range(j0, j0 + heures):
        if L[j] <= stop:
            res, tenu = "sl", j - j0 + 1
            break
        if H[j] >= objectif:
            res, tenu = "tp", j - j0 + 1
            break
    var_fin = round((s.C[j0 + heures - 1] - ref) / ref * 100, 2)
    rapport = tp / sl if sl > 0 else ratio
    r_brut = rapport if res == "tp" else -1.0 if res == "sl" else max(-1.0, min(rapport, var_fin / sl))
    return (res, round(r_brut, 3), round(r_brut - frais / sl, 3), tenu)


def jouer_limite(s, i, prix_limite, sl, ratio, heures, frais, validite=LIMITE_VALIDITE_H):
    """Ordre d'achat a cours limite pose a la cloture de la bougie i, valable `validite` heures.
    Servi seulement si le cours passe STRICTEMENT sous le prix (toucher le prix ne suffit pas : on est dans la file).
    Dans la bougie ou l'ordre est servi, le stop compte mais pas l'objectif (on ignore l'ordre des evenements).
    Renvoie None si l'historique manque, (0, None) si non servi, sinon (1, r_net)."""
    if i + 1 + validite + heures > s.n:
        return None
    for j in range(i + 1, i + 1 + validite):
        if s.L[j] < prix_limite:
            ref = min(prix_limite, s.O[j])            # ouverture sous le prix : servi au prix d'ouverture
            if ref <= 0:
                return (0, None)
            tp = sl * ratio
            stop, objectif = ref * (1 - sl / 100), ref * (1 + tp / 100)
            res = "sl" if s.L[j] <= stop else "neutre"
            if res == "neutre":
                for k in range(j + 1, j + heures):
                    if s.L[k] <= stop:
                        res = "sl"
                        break
                    if s.H[k] >= objectif:
                        res = "tp"
                        break
            var_fin = (s.C[j + heures - 1] - ref) / ref * 100
            r_brut = ratio if res == "tp" else -1.0 if res == "sl" else max(-1.0, min(ratio, var_fin / sl))
            return (1, round(r_brut - frais / sl, 3))
    return (0, None)


def jouer_tendance(s, i, sl, ratio, heures, frais, sortie_a):
    """Trade de tendance : stop, objectif (compte comme atteint, le stop suiveur n'est pas rejoue), sortie propre
    evaluee a la cloture de chaque bougie (sortie_a(j) -> bool), barriere. Renvoie (res, r_brut, r_net, tenu, j_fin)."""
    j0 = i + 1
    if j0 + heures > s.n:
        return None
    ref = s.O[j0]
    if ref <= 0 or abs(ref / s.C[i] - 1) > 0.10:
        return None
    stop, objectif = ref * (1 - sl / 100), ref * (1 + sl * ratio / 100)
    for j in range(j0, j0 + heures):
        if s.L[j] <= stop:
            return ("sl", -1.0, round(-1.0 - frais / sl, 3), j - j0 + 1, j)
        if s.H[j] >= objectif:
            return ("tp", ratio, round(ratio - frais / sl, 3), j - j0 + 1, j)
        if sortie_a(j):
            px = s.O[j + 1] if j + 1 < s.n else s.C[j]
            rb = max(-1.0, min(ratio, (px - ref) / ref * 100 / sl))
            return ("sortie", round(rb, 3), round(rb - frais / sl, 3), j - j0 + 1, j)
    j = j0 + heures - 1
    rb = max(-1.0, min(ratio, (s.C[j] - ref) / ref * 100 / sl))
    return ("neutre", round(rb, 3), round(rb - frais / sl, 3), heures, j)


# ------------------------------------------------------------------ contexte BTC (tendance lente de la porte)
def tendance_lente(clotures_jour, ema_jours=84):
    """Meme calcul que porte_entree.tendance_lente_btc sur une liste de clotures journalieres (la derniere peut
    etre le cours du moment). Renvoie (haussiere|None, ecart_pct, pente_pct)."""
    cl = clotures_jour[-(ema_jours + 40):]
    if len(cl) < ema_jours + 6:
        return None, None, None

    def ema(v):
        k = 2 / (ema_jours + 1)
        e = sum(v[:ema_jours]) / ema_jours
        for x in v[ema_jours:]:
            e = x * k + e * (1 - k)
        return e
    e_now, e_prev = ema(cl), ema(cl[:-5])
    if not e_now or not e_prev:
        return None, None, None
    return (cl[-1] > e_now and e_now >= e_prev), round((cl[-1] - e_now) / e_now * 100, 2), round((e_now - e_prev) / e_prev * 100, 3)


def construire_contexte():
    """Ecrit rejeu_data/btc_contexte.csv : pour chaque heure, la tendance lente du BTC telle que la porte la verrait."""
    d = charger_bougies("BTCUSDT")
    if not d:
        return 0
    C, t0, n = d["C"], d["t0"], len(d["C"])
    jours = [C[24 * k + 23] for k in range(n // 24)]
    os.makedirs(DATA, exist_ok=True)
    with open(CONTEXTE + ".tmp", "w", newline="") as f:
        w = csv.writer(f)
        for i in range(n):
            k = i // 24
            cl = jours[max(0, k - 130):k] + [C[i]]
            h, ecart, pente = tendance_lente(cl)
            if h is None:
                continue
            r24 = round((C[i] / C[i - 24] - 1) * 100, 2) if i >= 24 and C[i - 24] else ""
            w.writerow([t0 + 3600 * (i + 1), 1 if h else 0, ecart, pente, r24])
    os.replace(CONTEXTE + ".tmp", CONTEXTE)
    return n


_CTX = {}


def contexte():
    """{instant de decision -> (haussiere 0/1, ecart_pct, pente_pct, rendement 24 h)}"""
    if not _CTX:
        try:
            with open(CONTEXTE, newline="") as f:
                for l in csv.reader(f):
                    _CTX[int(l[0])] = (int(l[1]), float(l[2]), float(l[3]), float(l[4]) if l[4] != "" else None)
        except OSError:
            pass
    return _CTX


def episodes_de_baisse(ctx=None):
    """Liste de (debut_ts, fin_ts) : suites de jours ou la tendance lente du BTC n'est pas haussiere a la cloture
    du jour ; deux suites separees par moins de EPISODE_FUSION_J jours forment un seul episode."""
    ctx = contexte() if ctx is None else ctx
    jours = sorted(t for t in ctx if t % 86400 == 0)
    eps = []
    for t in jours:
        if ctx[t][0]:
            continue
        j = t - 86400                                   # le jour qui vient de se clore
        if eps and j - eps[-1][1] <= EPISODE_FUSION_J * 86400:
            eps[-1][1] = j
        else:
            eps.append([j, j])
    return [(a, b + 86400) for a, b in eps]


# ------------------------------------------------------------------ rejeu d'une crypto
def _sens(lignes, prefixe):
    h = any("hauss" in x for x in lignes if x.startswith(prefixe))
    b = any("baiss" in x for x in lignes if x.startswith(prefixe))
    if not any(x.startswith(prefixe) for x in lignes):
        return ""
    return "M" if h and b else "H" if h else "B" if b else "I"


def _a(x, n=4):
    return "" if x is None or x == "" else round(x, n)


def _features(s, i, a, ctx, tend9):
    ind = a.get("indicateurs") or {}
    prix = s.C[i]

    def rel(x, y):
        return (x / y - 1) * 100 if x and y else None

    def ret(n):
        return rel(prix, s.C[i - n]) if i >= n else None
    bh, bb, bm = ind.get("BB_haut"), ind.get("BB_bas"), ind.get("BB_milieu")
    vm = sum(s.V[i - 19:i]) / 19.0 if i >= 19 else 0
    v24 = sum(s.V[j] * s.C[j] for j in range(max(0, i - 23), i + 1))
    low = [str(x).lower() for x in a.get("signaux") or []]
    htf = 1 if any(x.startswith("htf") and "haussiere" in x for x in low) else 0 if any(x.startswith("htf") for x in low) else None
    t = s.ts(i)
    g = time.gmtime(t)
    return [_a(ind.get("RSI"), 1), _a(rel(prix, ind.get("SMA20")), 3), _a(rel(ind.get("SMA20"), ind.get("SMA50")), 3),
            _a(ind["MACD_histo"] / prix * 100 if ind.get("MACD_histo") is not None and prix else None, 4),
            _a((prix - bb) / (bh - bb) if bh and bb and bh > bb else None, 3), _a((bh - bb) / bm * 100 if bh and bb and bm else None, 3),
            _a(s.V[i] / vm if vm > 0 else None, 2), _a(ret(1), 3), _a(ret(4), 3), _a(ret(24), 3), _a(ret(168), 3),
            s.vides(i), _a(math.log10(v24) if v24 > 0 else None, 2), g.tm_hour, g.tm_wday, _a(htf),
            _a(ctx[1] if ctx else None), _a(ctx[2] if ctx else None), _a(ctx[3] if ctx else None), _a(tend9)]


def rejouer_crypto(sym, serie=None, ecrire=True):
    """Rejoue toutes les strategies sur une crypto. Renvoie {'sym', 'n_bougies', 'n_signaux', 'n_trades', ...} et,
    si ecrire=False, la liste des lignes de trades sous 'lignes'."""
    m = moteur()
    ind, sa, st, detectees, cur = m["ind"], m["sa"], m["st"], m["detectees"], m["cur"]
    if serie is None:
        d = charger_bougies(sym)
        if not d:
            return {"sym": sym, "erreur": "pas de bougies (ou moins de 60 jours)"}
        serie = Serie(d)
    s = serie
    cur["s"] = s
    depuis, vmax, ctx_btc = depuis_ts(), vides_max(), contexte()
    ratio, heures, frais, f_lim = float(sa.TP_RATIO), int(sa.BARRIERE_H), float(sa.FRAIS_AR_PCT), frais_limite()
    i_debut = max(199, (depuis - s.t0) // 3600 - 1)
    lignes, signaux = [], []

    def stop_a(i):
        atr = sa.atr_pct(s.B[i - 15:i + 1])
        return atr, sa.stop_pct(atr, maintenant=datetime.fromtimestamp(s.ts(i), timezone.utc))

    # --- tendance : etats calcules a chaque cloture 4 h et a chaque cloture de jour
    n4, nj = s.n // 4, s.n // 24
    don, don_sortie = [False] * n4, [False] * n4
    for k in range(max(st.DONCHIAN_ENTREE + 3, i_debut // 4), n4):
        i = 4 * k + 3
        cur["i"] = i
        don[k] = bool(st.donchian(sym, s.Q[max(0, k - st.DONCHIAN_ENTREE - 29):k + 1], s.j1(i, max(st.EMA_JOURS * 2, 220))).get("signal"))
        don_sortie[k] = bool(st.sortie_donchian(sym, s.Q[max(0, k - st.DONCHIAN_SORTIE - 29):k + 1])[0])
    tsm, tsm_sortie, score9 = [False] * nj, [False] * nj, [None] * nj
    for k in range(max(30, i_debut // 24 - 1), nj):
        cur["i"] = 24 * k + 23
        b = s.D[max(0, k - 399):k + 1]
        tsm[k] = bool(st.tsmom(sym, b[-max(st.TSMOM_SMA + 10, 260):]).get("signal"))
        tsm_sortie[k] = bool(st.sortie_tsmom(sym, b[-(st.TSMOM_COURT + 40):])[0])
        n_h, n_t, _ = st.score_tendance(sym, b)
        score9[k] = n_h if n_t == len(st.HORIZONS_SCORE) else None
    sorties = {"donchian_breakout": lambda j: j % 4 == 3 and don_sortie[j // 4],
               "tsmom": lambda j: j % 24 == 23 and tsm_sortie[j // 24],
               "tendance_multi": lambda j: j % 24 == 23 and score9[j // 24] is not None and score9[j // 24] <= MULTI_SORTIE}
    libre_i = {x: 0 for x in TENDANCE}

    def tendances(i):
        out = []
        if i % 4 == 3 and don[i // 4]:
            out.append("donchian_breakout")
        if i % 24 == 23:
            k = i // 24
            if tsm[k]:
                out.append("tsmom")
            if k >= 1 and score9[k] is not None and score9[k - 1] is not None and score9[k] >= MULTI_ENTREE > score9[k - 1]:
                out.append("tendance_multi")
        return out

    # --- boucle principale
    libre = {}
    for i in range(i_debut, s.n - 1):
        t = s.ts(i)
        if t < depuis or s.vides(i) > vmax:
            continue
        cb = ctx_btc.get(t)
        baisse = "" if cb is None else 0 if cb[0] else 1
        for nom in tendances(i):
            if i < libre_i[nom]:
                continue
            atr, sl = stop_a(i)
            j = jouer_tendance(s, i, sl, float(st.TP_RATIO), int(st.BARRIERE_H), frais, sorties[nom])
            if j is None:
                continue
            libre_i[nom] = j[4] + 1
            lignes.append([sym, t, nom, 0, 1, "", "", "", _a(atr, 3), sl, j[0], j[1], j[2], j[3], baisse, "", "", "", ""] + [""] * len(FEATURES))
        cur["i"] = i
        a = ind.analyser_actif(sym, "1h")
        if not a or a.get("score", 0) < 1:
            continue
        noms = detectees(a.get("signaux") or [])
        atr, sl = stop_a(i)
        masque = sum(1 << TECH.index(x) for x in noms if x in TECH)
        signaux.append((t, masque, "" if atr is None else atr, a["score"]))
        ouvrir = [(r, x) for r, x in enumerate(noms) if t >= libre.get(x, 0)]
        if not ouvrir:
            continue
        j = jouer(s, i, sl, ratio, heures, frais, prix=s.C[i])
        if j is None:
            continue
        low = [str(x).lower() for x in a.get("signaux") or []]
        sens, pat = _sens(low, "volume"), _sens(low, "bougie")
        l0 = jouer_limite(s, i, s.C[i], sl, ratio, heures, f_lim) or ("", "")
        recul = s.C[i] * (1 - LIMITE_RECUL_ATR * (atr or 0) / 100)
        l25 = jouer_limite(s, i, recul, sl, ratio, heures, f_lim) or ("", "")
        k = i // 24 - (0 if i % 24 == 23 else 1)
        feats = _features(s, i, a, cb, score9[k] if 0 <= k < nj else None)
        for r, x in ouvrir:
            libre[x] = t + heures * 3600 + t % 18000
            lignes.append([sym, t, x, r, len(noms), a["score"], sens if x == "volume_spike" else "", pat if x == "pattern_reversal" else "",
                           _a(atr, 3), sl, j[0], j[1], j[2], j[3], baisse, l0[0], _a(l0[1], 3), l25[0], _a(l25[1], 3)] + feats)
    cur["s"] = None
    res = {"sym": sym, "n_bougies": s.n, "debut": _jour(max(s.t0, depuis)), "fin": _jour(s.t0 + 3600 * s.n), "n_signaux": len(signaux),
           "n_trades": len(lignes), "vides_pct": round(100.0 * sum(s.vide) / max(1, s.n), 1)}
    if not ecrire:
        res["lignes"], res["signaux"] = lignes, signaux
        return res
    os.makedirs(TRADES, exist_ok=True)
    os.makedirs(SIGNAUX, exist_ok=True)
    with open(os.path.join(SIGNAUX, sym + ".csv.tmp"), "w", newline="") as f:
        csv.writer(f).writerows(signaux)
    os.replace(os.path.join(SIGNAUX, sym + ".csv.tmp"), os.path.join(SIGNAUX, sym + ".csv"))
    with open(os.path.join(TRADES, sym + ".csv.tmp"), "w", newline="") as f:
        w = csv.writer(f)
        w.writerow(COLONNES)
        w.writerows(lignes)
    os.replace(os.path.join(TRADES, sym + ".csv.tmp"), os.path.join(TRADES, sym + ".csv"))
    res["signature"] = signature()
    with open(os.path.join(TRADES, sym + ".json"), "w") as f:
        json.dump(res, f)
    return res


def _deja_fait(sym, sig):
    try:
        with open(os.path.join(TRADES, sym + ".json")) as f:
            d = json.load(f)
        return d if d.get("signature") == sig and os.path.exists(os.path.join(TRADES, sym + ".csv")) else None
    except Exception:
        return None


def _travail(sym):
    t0 = time.time()
    try:
        r = rejouer_crypto(sym)
    except Exception as e:
        r = {"sym": sym, "erreur": f"{type(e).__name__}: {str(e)[:160]}"}
    r["secondes"] = round(time.time() - t0, 1)
    return r


# ------------------------------------------------------------------ statistiques (bibliotheque standard)
def stats(cas, z=Z):
    """cas : liste de (ts, r). R moyen net et intervalle par grappes journalieres (meme calcul que le laboratoire)."""
    n = len(cas)
    st = {"n": n, "jours": 0, "r": None, "bas": None, "haut": None}
    if not n:
        return st
    m = sum(c[1] for c in cas) / n
    par_jour = {}
    for t, r in cas:
        j = t // 86400
        par_jour[j] = par_jour.get(j, 0.0) + (r - m)
    g = len(par_jour)
    st.update({"jours": g, "r": round(m, 3)})
    if g >= 2:
        se = ((g / (g - 1.0)) * sum(v * v for v in par_jour.values())) ** 0.5 / n
        st["bas"], st["haut"] = round(m - z * se, 3), round(m + z * se, 3)
    return st


def par_annee(cas):
    d = {}
    for t, r in cas:
        a = time.gmtime(t).tm_year
        e = d.setdefault(a, [0, 0.0])
        e[0] += 1
        e[1] += r
    return {a: (n, round(sm / n, 3)) for a, (n, sm) in sorted(d.items())}


def serie_jour(cas):
    """R moyen par jour actif : la serie sur laquelle on calcule le ratio de Sharpe."""
    d = {}
    for t, r in cas:
        e = d.setdefault(t // 86400, [0, 0.0])
        e[0] += 1
        e[1] += r
    return {j: sm / n for j, (n, sm) in d.items()}


def sharpe(valeurs):
    if len(valeurs) < 3:
        return None
    sd = statistics.pstdev(valeurs)
    return statistics.fmean(valeurs) / sd if sd > 0 else None


def sharpe_degonfle(valeurs, n_essais, var_sharpes):
    """Probabilite que le vrai ratio de Sharpe soit > 0 une fois retire l'effet « on a essaye n_essais regles »
    (Bailey & Lopez de Prado, 2014). None si la serie est trop courte."""
    T = len(valeurs)
    sr = sharpe(valeurs)
    if sr is None or T < 30 or n_essais < 2 or var_sharpes is None:
        return None
    m, sd = statistics.fmean(valeurs), statistics.pstdev(valeurs)
    asym = sum(((v - m) / sd) ** 3 for v in valeurs) / T
    aplat = sum(((v - m) / sd) ** 4 for v in valeurs) / T
    N = statistics.NormalDist()
    g = 0.5772156649
    sr0 = math.sqrt(max(var_sharpes, 0.0)) * ((1 - g) * N.inv_cdf(1 - 1.0 / n_essais) + g * N.inv_cdf(1 - 1.0 / (n_essais * math.e)))
    den = 1 - asym * sr + (aplat - 1) / 4.0 * sr * sr
    if den <= 0:
        return None
    return round(N.cdf((sr - sr0) * math.sqrt(T - 1) / math.sqrt(den)), 3)


def pbo(series, blocs=10):
    """Probabilite de surapprentissage par validation croisee combinatoire symetrique (Bailey, Borwein, Lopez de
    Prado, Zhu, 2017). series : {nom: {jour: valeur}}. On coupe le calendrier en `blocs` morceaux ; pour chaque facon
    d'en prendre la moitie, on choisit la meilleure regle sur cette moitie et on regarde son rang sur l'autre.
    PBO = part des cas ou la meilleure « en echantillon » finit sous la mediane « hors echantillon »."""
    noms = sorted(series)
    jours = sorted({j for v in series.values() for j in v})
    if len(noms) < 2 or len(jours) < blocs * 20:
        return None
    taille = len(jours) // blocs
    morceau = {j: min(blocs - 1, k // taille) for k, j in enumerate(jours)}
    agg = {n: [[0, 0.0, 0.0] for _ in range(blocs)] for n in noms}        # par bloc : nb de jours, somme, somme des carres
    for n in noms:
        for j, v in series[n].items():
            e = agg[n][morceau[j]]
            e[0] += 1
            e[1] += v
            e[2] += v * v
    compte = [sum(1 for j in jours if morceau[j] == b) for b in range(blocs)]

    def sr(n, choix):
        T = sum(compte[b] for b in choix)                                # les jours sans trade comptent pour zero
        sm = sum(agg[n][b][1] for b in choix)
        s2 = sum(agg[n][b][2] for b in choix)
        var = s2 / T - (sm / T) ** 2
        return (sm / T) / math.sqrt(var) if var > 0 else 0.0
    sous, total = 0, 0
    for choix in itertools.combinations(range(blocs), blocs // 2):
        reste = [b for b in range(blocs) if b not in choix]
        meilleur = max(noms, key=lambda n: sr(n, choix))
        hors = sorted(noms, key=lambda n: sr(n, reste))
        rang = (hors.index(meilleur) + 1) / (len(noms) + 1.0)
        sous += 1 if rang <= 0.5 else 0
        total += 1
    return {"pbo": round(sous / float(total), 3), "combinaisons": total, "regles": len(noms), "jours": len(jours)}


def verdict(st, annees, dsr):
    """Regle fixee avant de voir les resultats. « TIENT » n'est pas un droit d'ouvrir."""
    if st["n"] and st["haut"] is not None and st["haut"] < 0:
        return "PERDANTE"
    pleines = [r for n, r in annees.values() if n >= 30]
    if (st["n"] >= 300 and st["bas"] is not None and st["bas"] > 0 and dsr is not None and dsr >= 0.95
            and len(pleines) >= 3 and sum(1 for r in pleines if r > 0) * 3 >= len(pleines) * 2):
        return "TIENT sur l'historique"
    return "pas de preuve"


# ------------------------------------------------------------------ bilan
def lire_trades(colonnes, syms=None):
    """Genere des tuples (une valeur par colonne demandee, texte brut) depuis rejeu_data/trades."""
    try:
        fichiers = sorted(f for f in os.listdir(TRADES) if f.endswith(".csv"))
    except OSError:
        fichiers = []
    for nom in fichiers:
        if syms and nom[:-4] not in syms:
            continue
        with open(os.path.join(TRADES, nom), newline="") as f:
            r = csv.reader(f)
            tete = next(r, None)
            if not tete:
                continue
            idx = [tete.index(c) for c in colonnes]
            for l in r:
                yield tuple(l[k] for k in idx)


def calculer_bilan():
    par, limites, sens, regime, total, brut = {}, {}, {}, {}, 0, {}
    eps = episodes_de_baisse()
    debuts = [a for a, _ in eps]
    par_episode = {}
    import bisect
    for sym, ts, strat, pat, sv, res, rb, r, baisse, l0, l0r, l25, l25r in lire_trades(
            ["sym", "ts", "strat", "pat", "sens", "res", "r_brut", "r", "baisse", "l0", "l0_r", "l25", "l25_r"]):
        if res == "ecart":
            continue
        t, r = int(ts), float(r)
        total += 1
        par.setdefault(strat, []).append((t, r))
        brut[strat] = brut.get(strat, 0.0) + float(rb)
        if baisse != "":
            regime.setdefault((strat, int(baisse)), []).append((t, r))
        marque = sv or pat
        if marque:
            sens.setdefault((strat, marque), []).append((t, r))
        if baisse == "1":
            k = bisect.bisect_right(debuts, t) - 1
            if k >= 0 and t <= eps[k][1]:
                par_episode.setdefault((strat, k), []).append((t, r))
                if marque:
                    par_episode.setdefault((strat + ":" + marque, k), []).append((t, r))
        if l0 != "":
            e = limites.setdefault(strat, {"n": 0, "marche": 0.0, "l0": [], "l0_non": [], "l25": [], "l25_non": []})
            e["n"] += 1
            e["marche"] += r
            (e["l0"].append((t, float(l0r))) if l0 == "1" else e["l0_non"].append((t, r)))
            if l25 != "":
                (e["l25"].append((t, float(l25r))) if l25 == "1" else e["l25_non"].append((t, r)))
    series = {s: serie_jour(c) for s, c in par.items() if len(c) >= 30}
    for (s, m), c in sens.items():
        if len(c) >= 30:
            series[f"{s}:{m}"] = serie_jour(c)
    sharpes = [x for x in (sharpe(list(v.values())) for v in series.values()) if x is not None]
    n_essais = len(series) + 2 * sum(1 for e in limites.values() if e["n"] >= 30)       # + les deux variantes d'ordre limite
    var_sr = statistics.pvariance(sharpes) if len(sharpes) >= 2 else None

    def fiche(nom, cas):
        st = stats(cas)
        an = par_annee(cas)
        d = sharpe_degonfle(list(serie_jour(cas).values()), n_essais, var_sr)
        return dict(st, nom=nom, annees={str(a): v for a, v in an.items()}, dsr=d, verdict=verdict(st, an, d),
                    brut=round(brut[nom] / len(cas), 3) if nom in brut and cas else None)
    out = {"date": time.strftime("%Y-%m-%d %H:%M UTC", time.gmtime()), "trades": total, "essais": n_essais,
           "strategies": [fiche(s, c) for s, c in sorted(par.items(), key=lambda kv: -len(kv[1]))],
           "sens": [fiche(f"{s}:{m}", c) for (s, m), c in sorted(sens.items())],
           "regime": {f"{s}|{'baisse' if b else 'hausse'}": stats(c) for (s, b), c in sorted(regime.items())},
           "episodes": [{"debut": _jour(a), "fin": _jour(b), "jours": (b - a) // 86400} for a, b in eps],
           "par_episode": {}, "limites": {}, "pbo": pbo({s: {j: v for j, v in sj.items()} for s, sj in series.items()})}
    for (s, k), c in sorted(par_episode.items()):
        out["par_episode"].setdefault(s, []).append(dict(stats(c), episode=k, jours=(eps[k][1] - eps[k][0]) // 86400))
    for s, e in sorted(limites.items()):
        n = e["n"]
        ligne = {"n": n, "marche_r": round(e["marche"] / n, 3)}
        for v in ("l0", "l25"):
            servis, non = e[v], e[v + "_non"]
            st, sn = stats(servis), stats(non)
            ligne[v] = {"servis_pct": round(100.0 * len(servis) / max(1, len(servis) + len(non)), 1), "r_servis": st["r"], "bas": st["bas"],
                        "haut": st["haut"], "r_marche_des_non_servis": sn["r"],
                        "r_par_signal": round(sum(x[1] for x in servis) / max(1, len(servis) + len(non)), 3)}
        out["limites"][s] = ligne
    faits = []
    try:
        for f in sorted(os.listdir(TRADES)):
            if f.endswith(".json"):
                with open(os.path.join(TRADES, f)) as g:
                    d = json.load(g)
                faits.append({k: d.get(k) for k in ("sym", "n_bougies", "debut", "fin", "n_trades", "vides_pct")})
    except OSError:
        pass
    out["cryptos"] = faits
    with open(BILAN_JSON + ".tmp", "w") as f:
        json.dump(out, f, ensure_ascii=False)
    os.replace(BILAN_JSON + ".tmp", BILAN_JSON)
    return out


def _ic(st):
    if st.get("r") is None:
        return "      -"
    if st.get("bas") is None:
        return f"{st['r']:+.3f}"
    return f"{st['r']:+.3f} [{st['bas']:+.2f} ; {st['haut']:+.2f}]"


def _milliers(n):
    return f"{int(n):,}".replace(",", " ")


def _episodes_gagnants(liste):
    assez = [e for e in liste if e["n"] >= EPISODE_N_MIN and e.get("jours", 0) >= EPISODE_JOURS_MIN]
    return sum(1 for e in assez if e["r"] > 0), sum(1 for e in assez if e.get("bas") is not None and e["bas"] > 0), len(assez)


def texte_bilan(b, detail=False):
    L = []
    cr = b.get("cryptos") or []
    L.append("REJEU HISTORIQUE — observation seule : rien ici ne donne le droit d'ouvrir")
    if cr:
        L.append(f"Bougies Kraken 1 h en euros, {len(cr)} cryptos, du {min(c['debut'] for c in cr)} au {max(c['fin'] for c in cr)} ; "
                 f"{_milliers(sum(c['n_bougies'] or 0 for c in cr))} bougies, {_milliers(b['trades'])} trades virtuels.")
    L.append("R = gain net de frais en multiples du risque ; [ ] = intervalle a 95 % par jour ; DSR = Sharpe degonfle.")
    L.append("")
    L.append("1. STRATEGIES NUES (sans la porte d'entree)")
    L.append(f"   {'strategie':<19}{'trades':>8}  {'R brut':>7}  {'R net moyen':<25}{'annees +':>9}  {'DSR':>5}  verdict")
    for f in b["strategies"]:
        pleines = [r for n, r in f["annees"].values() if n >= 30]
        an = f"{sum(1 for r in pleines if r > 0)}/{len(pleines)}"
        L.append(f"   {f['nom']:<19}{f['n']:>8}  {'-' if f.get('brut') is None else format(f['brut'], '+.3f'):>7}  {_ic(f):<25}{an:>9}  "
                 f"{'-' if f['dsr'] is None else format(f['dsr'], '.2f'):>5}  {f['verdict']}")
    L.append("   R brut = avant frais. Regle : TIENT = au moins 300 trades, borne basse > 0, DSR >= 0,95 et gagnante")
    L.append(f"   2 annees sur 3 ; {b['essais']} regles essayees (le DSR en tient compte).")
    if b.get("sens"):
        L.append("")
        L.append("2. SENS DU SIGNAL (H = haussier, B = baissier, M = les deux, I = indecision)")
        for f in b["sens"]:
            L.append(f"   {f['nom']:<22}{f['n']:>8}  {_ic(f):<25}  {f['verdict']}")
        L.append("   Le bot nomme volume_spike aussi les pics de volume BAISSIERS, et pattern_reversal toutes les figures.")
    L.append("")
    L.append("3. MARCHE HAUSSIER / BAISSIER (BTC et son EMA 84 jours, comme la garde de baisse)")
    eps = b.get("episodes") or []
    L.append(f"   {sum(1 for e in eps if e['jours'] >= EPISODE_JOURS_MIN)} episodes de baisse d'au moins {EPISODE_JOURS_MIN} jours ; un episode compte s'il contient au moins {EPISODE_N_MIN} trades.")
    L.append(f"   {'strategie':<19}{'en hausse':<28}{'en baisse':<28}episodes gagnants")
    for f in b["strategies"]:
        h, d = b["regime"].get(f["nom"] + "|hausse", {}), b["regime"].get(f["nom"] + "|baisse", {})
        g, gs, t = _episodes_gagnants(b["par_episode"].get(f["nom"], []))
        L.append(f"   {f['nom']:<19}{_ic(h):<28}{_ic(d):<28}{g}/{t} (dont {gs} avec borne basse > 0)")
    for cle in ("volume_spike:H", "volume_spike:B"):
        liste = b["par_episode"].get(cle)
        if liste:
            g, gs, t = _episodes_gagnants(liste)
            L.append(f"   {cle:<19}en baisse : gagnante sur {g}/{t} episodes (dont {gs} avec borne basse > 0)")
    if detail and b["par_episode"].get("volume_spike"):
        L.append("   Detail volume_spike par episode de baisse :")
        for e in b["par_episode"]["volume_spike"]:
            ep = eps[e["episode"]]
            L.append(f"     {ep['debut']} -> {ep['fin']} ({ep['jours']:>3} j)  {e['n']:>5} trades  {_ic(e)}")
    L.append("")
    L.append("4. ORDRES LIMITE (valables 3 h ; frais 0,1 % au lieu de 0,2 %) — R par 100 signaux")
    L.append(f"   {'strategie':<19}{'au marche':>10}{'limite au cours':>17}{'servis':>8}{'limite -0,25 ATR':>18}{'servis':>8}  non servis au marche")
    for s, e in sorted(b["limites"].items(), key=lambda kv: -kv[1]["n"]):
        L.append(f"   {s:<19}{e['marche_r'] * 100:>+10.1f}{e['l0']['r_par_signal'] * 100:>+17.1f}{e['l0']['servis_pct']:>7.0f}%"
                 f"{e['l25']['r_par_signal'] * 100:>+18.1f}{e['l25']['servis_pct']:>7.0f}%  "
                 f"{'-' if e['l0']['r_marche_des_non_servis'] is None else format(e['l0']['r_marche_des_non_servis'], '+.3f')}")
    L.append("   Derniere colonne : ce qu'auraient donne au marche les signaux que l'ordre limite a manques (selection adverse).")
    L.append("")
    p = b.get("pbo")
    L.append("5. GARDE-FOUS")
    if p:
        L.append(f"   Probabilite de surapprentissage (CSCV, {p['combinaisons']} decoupages, {p['regles']} regles, {p['jours']} jours) : {p['pbo']:.2f}"
                 f" — {'la meilleure regle du passe ne reste pas la meilleure ensuite' if p['pbo'] >= 0.5 else 'le classement des regles se maintient (cela ne dit pas qu elles gagnent)' if p['pbo'] < 0.3 else 'classement peu fiable'}.")
    else:
        L.append("   Probabilite de surapprentissage : pas assez de jours pour la calculer.")
    m = modeles()
    L.append("")
    if m and m.get("texte"):
        L.extend(m["texte"])
    else:
        L.append("6-7. FILTRE APPRIS ET REGLAGES : non calcules (bibliotheques absentes ou calcul en cours ; bash installer_rejeu.sh).")
    if detail:
        L.append("")
        L.append("TABLEAU PAR ANNEE (R net moyen, nombre de trades)")
        annees = sorted({a for f in b["strategies"] for a in f["annees"]})
        L.append("   " + f"{'strategie':<19}" + "".join(f"{a:>12}" for a in annees))
        for f in b["strategies"]:
            L.append("   " + f"{f['nom']:<19}" + "".join(
                f"{(format(f['annees'][a][1], '+.2f') + ' (' + str(f['annees'][a][0]) + ')') if a in f['annees'] else '-':>12}" for a in annees))
    L.append("")
    L.append("LIMITES : bougies sans carnet ni ecart achat-vente ; prix Kraken et non Revolut X ; bougies closes ; la porte")
    L.append("d'entree n'est pas rejouee ; ia_autonome n'est pas rejouable ; seuils actuels du bot. Un resultat du passe n'est")
    L.append("pas une promesse, et aucun reglage n'est modifie par ce module.")
    return "\n".join(L)


def modeles():
    try:
        with open(MODELES_JSON) as f:
            d = json.load(f)
        return d if isinstance(d, dict) else None
    except Exception:
        return None


def bilan(detail=False, recalculer=False):
    b = None
    if not recalculer:
        try:
            with open(BILAN_JSON) as f:
                b = json.load(f)
        except Exception:
            b = None
    if b is None:
        if not os.path.isdir(TRADES):
            return "Rejeu historique : rien n'a encore ete rejoue (python3 rejeu_historique.py etat)."
        b = calculer_bilan()
    t = texte_bilan(b, detail)
    if not detail:
        try:
            with open(BILAN_TXT, "w") as f:
                f.write(t + "\n")
        except OSError:
            pass
    return t


def texte_etat():
    e = etat()
    if not e:
        return "Rejeu historique : jamais lance."
    L = [f"Rejeu historique : {e.get('phase', '?')} (mis a jour {e.get('maj', '?')})"]
    if e.get("total"):
        L.append(f"  cryptos rejouees : {e.get('faites', 0)}/{e['total']} ; trades virtuels : {e.get('trades', 0)}")
    if e.get("erreurs"):
        L.append("  erreurs : " + " ; ".join(e["erreurs"][:5]))
    if e.get("duree_min") is not None:
        L.append(f"  duree : {e['duree_min']} min")
    if e.get("phase") == "termine":
        L.append("  Lire le bilan : python3 rejeu_historique.py bilan")
    return "\n".join(L)


# ------------------------------------------------------------------ enchainement complet
def tout(syms=None, processus=None, avec_modeles=True, journal=print):
    if not actif():
        journal("REJEU=0 dans .env : rien n'est lance.")
        return 0
    import fcntl
    verrou = open(VERROU, "w")
    try:
        fcntl.flock(verrou, fcntl.LOCK_EX | fcntl.LOCK_NB)
    except OSError:
        journal("Un rejeu est deja en cours (python3 rejeu_historique.py etat).")
        return 0
    t0 = time.time()
    complet = not syms
    syms = list(syms or cryptos())
    if complet:  # rejeu complet : les resultats d'une crypto sortie de la liste ne doivent pas rester dans le bilan
        for dossier in (TRADES, SIGNAUX):
            try:
                for nom in os.listdir(dossier):
                    if nom.rsplit(".", 1)[0] not in syms:
                        os.remove(os.path.join(dossier, nom))
            except OSError:
                pass
    if "BTCUSDT" not in syms:
        telecharger(["BTCUSDT"], journal)
    _sauver_etat(phase="telechargement des bougies Kraken", total=len(syms), faites=0, trades=0, erreurs=[], duree_min=None,
                 debut=time.strftime("%Y-%m-%d %H:%M UTC", time.gmtime()))
    try:
        telecharger(syms, journal)
    except Exception as e:
        _sauver_etat(phase=f"ARRET : telechargement impossible ({type(e).__name__}: {str(e)[:120]})")
        journal(f"ARRET : telechargement impossible ({type(e).__name__}: {str(e)[:120]}). Rien d'autre n'a ete touche.")
        return 1
    couper_reseau()
    _sauver_etat(phase="contexte BTC")
    construire_contexte()
    sig = signature()
    faits = [d for d in (_deja_fait(s, sig) for s in syms) if d]
    reste = [s for s in syms if s not in {d["sym"] for d in faits}]
    trades, erreurs = sum(d.get("n_trades", 0) for d in faits), []
    _sauver_etat(phase="rejeu en cours", faites=len(faits), trades=trades)
    if reste:
        import multiprocessing as mp
        try:
            n_proc = int(processus or _env("REJEU_PROCESSUS", "2"))
        except Exception:
            n_proc = 2
        n_proc = max(1, min(n_proc, len(reste)))
        fait = len(faits)
        with mp.get_context("fork").Pool(n_proc) as pool:
            for r in pool.imap_unordered(_travail, reste):
                fait += 1
                if r.get("erreur"):
                    erreurs.append(f"{r['sym']}: {r['erreur']}")
                    journal(f"  {r['sym']:<12} ERREUR {r['erreur']}")
                else:
                    trades += r["n_trades"]
                    journal(f"  {r['sym']:<12} {r['debut']} -> {r['fin']}  {r['n_bougies']:>7} bougies  {r['n_trades']:>6} trades  {r['secondes']:>6.0f} s")
                _sauver_etat(faites=fait, trades=trades, erreurs=erreurs)
    _sauver_etat(phase="calcul du bilan")
    try:
        os.remove(MODELES_JSON)
    except OSError:
        pass
    calculer_bilan()
    if avec_modeles:
        _sauver_etat(phase="modeles (LightGBM, Optuna)")
        import subprocess
        try:
            subprocess.run([sys.executable, os.path.join(DOSSIER, "rejeu_modeles.py"), "tout"], cwd=DOSSIER, timeout=5400,
                           stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        except Exception as e:
            erreurs.append(f"modeles: {type(e).__name__}")
    journal(bilan())
    _sauver_etat(phase="termine", erreurs=erreurs, duree_min=round((time.time() - t0) / 60.0, 1))
    return 0


def _symboles(mots):
    """BTC, btc ou BTCUSDT -> BTCUSDT (le nom que le bot utilise) ; None si rien n'est demande = toutes les cryptos."""
    out = []
    for m in mots:
        m = m.strip().upper()
        if not m.isalnum():
            continue
        if not m.endswith("USDT"):
            m += "USDT"
        if m not in out:
            out.append(m)
    return out or None


def main(argv):
    cmd = argv[0] if argv else "bilan"
    if cmd == "tout":
        return tout(_symboles(argv[1:]))
    if cmd == "etat":
        print(texte_etat())
        return 0
    if cmd == "bilan":
        print(bilan(detail="detail" in argv[1:], recalculer="recalculer" in argv[1:]))
        return 0
    if cmd == "telecharger":
        print(telecharger(_symboles(argv[1:])), "fichiers")
        return 0
    print(__doc__)
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
