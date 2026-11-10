#!/usr/bin/env python3
"""
Professeur HYPERLIQUID : on regarde en direct les MEILLEURS traders d'une bourse de perpetuels entierement sur chaine
(Hyperliquid). Leurs positions et leurs gains sont publics et verifiables par construction : rien a declarer, rien a
maquiller. Aucune cle, aucun compte : l'API publique repond a tout le monde (1 200 unites de poids par minute et par IP).

CONSIGNE DE L'UTILISATEUR (10/11/2026) :
    * suivre SEULEMENT les meilleurs (une cohorte filtree, pas le premier du classement) ;
    * APPRENDRE leur facon de trader (sens, duree de detention, achat des creux ou de la force, heures, levier) ;
    * AUCUN droit d'ouvrir : le professeur vote, journalise, se fait juger ; le cerveau le lit.

COMMENT ON CHOISIT « LES MEILLEURS » (selectionner_cohorte) :
    1. capital >= HL_CAPITAL_MIN (250 000 $ par defaut) : des comptes serieux ;
    2. gagnants a la fois sur la SEMAINE, le MOIS et DEPUIS TOUJOURS : la regularite, pas le coup de chance ;
    3. rendement du mois entre HL_ROI_MOIS_MIN et HL_ROI_MOIS_MAX (5 % .. 300 %) : au-dela c'est une loterie a fort levier ;
    4. rotation mensuelle (volume / capital) <= HL_ROTATION_MAX (60x) : ecarte les teneurs de marche et les coffres
       (vaults) qui tournent des centaines de fois et dont les positions ne disent rien sur la direction ;
    5. note de regularite = 60 % rendement du mois (plafonne a +100 %) + 20 % rendement de la semaine (plafonne a +30 %)
       + 20 % gain total rapporte au capital (plafonne a 2x). Les HL_N_TRADERS (40) meilleurs forment la cohorte.

CE QU'ON LIT ENSUITE :
    * toutes les HL_RAFRAICHIR_POSITIONS_S (15 min) : les positions ouvertes de la cohorte (clearinghouseState) ;
      par crypto du bot : dollars longs / courts, nombre de traders de chaque cote, entrees fraiches depuis la lecture
      precedente ;
    * toutes les HL_RAFRAICHIR_COHORTE_H (6 h) : le classement complet (48 000 comptes, ~40 Mo) relu en flux pour ne
      garder que la cohorte, puis les 2 000 derniers ordres executes des HL_N_PROFILS (10) premiers pour en tirer leur
      STYLE (profiler) : part long/short, % de clotures gagnantes, duree mediane de detention, achat des creux ou de la
      force (variation 24 h avant l'entree, sur nos bougies 1 h), heures UTC les plus actives, levier moyen.

VOTES ET JUGEMENT (comme professeurs_externes) :
    * ACHAT (tags « entree_longue » si un des meilleurs vient d'ouvrir/renforcer un long, sinon « biais_long » si >= 65 %
      des dollars de la cohorte sont longs avec >= 3 traders) ; VENTE (« biais_short ») symetrique, lue comme un
      avertissement par le cerveau (le bot est acheteur au comptant, il ne vend pas a decouvert).
    * chaque vote est juge avec la barriere du bot : stop 2 x ATR 1h (0,8-3 %), objectif 2:1, 24 h. Fiabilite MESUREE
      chez nous. Influence sur la preselection (+0,5 achat / -0,5 vente) seulement a partir de 20 votes tranches et 45 %
      d'objectifs. Avant : seulement lu.
    * tout est debrayable : PROF_HYPERLIQUID=0 dans .env.

Sources : https://hyperliquid.gitbook.io/hyperliquid-docs/for-developers/api/info-endpoint ;
          classement public : https://stats-data.hyperliquid.xyz/Mainnet/leaderboard

CLI :  python3 professeur_hyperliquid.py                 -> rapport
       python3 professeur_hyperliquid.py rafraichir      -> relit le classement, la cohorte, les positions, les profils
       python3 professeur_hyperliquid.py positions       -> positions de la cohorte par crypto (lecture directe)
       python3 professeur_hyperliquid.py evaluer         -> juge les votes en attente
"""
import json
import os
import statistics
import sys
import threading
import time
import urllib.request
from datetime import datetime, timezone

DOSSIER = os.path.dirname(os.path.abspath(__file__))
FICHIER = os.path.join(DOSSIER, "professeur_hyperliquid.json")
PROF = "HYPERLIQUID"
URL_INFO = "https://api.hyperliquid.xyz/info"
URL_CLASSEMENT = "https://stats-data.hyperliquid.xyz/Mainnet/leaderboard"
N_FIABLE, WR_FIABLE = 20, 45.0
REFROIDISSEMENT_VOTE_S = 2 * 3600
BARRIERE_H = 24
SEUIL_BIAIS = 0.65          # part des dollars d'un cote pour parler de biais
MIN_TRADERS = 3             # traders du meme cote pour qu'un biais compte
_VERROU = threading.Lock()
_EN_COURS = {"cohorte": False, "positions": False}

# Symboles du bot -> coin Hyperliquid (les autres coins du bot ne sont pas listes sur Hyperliquid)
ALIAS = {"RNDRUSDT": "RENDER"}


# ------------------------------------------------------------------ reglages
def _lire(nom, defaut):
    try:
        from config_env import lire
        v = lire(nom, None)
    except Exception:
        v = os.environ.get(nom)
    return defaut if v in (None, "") else v


def _actif():
    return str(_lire("PROF_HYPERLIQUID", "1")).strip().lower() not in ("0", "false", "non", "off")


def _param(nom, defaut, typ=float):
    try:
        return typ(_lire(nom, defaut))
    except Exception:
        return defaut


def reglages():
    return {
        "n_traders": _param("HL_N_TRADERS", 40, int),
        "n_profils": _param("HL_N_PROFILS", 40, int),
        "detention_min_h": _param("HL_DETENTION_MIN_H", 1.0),
        "capital_min": _param("HL_CAPITAL_MIN", 250_000.0),
        "roi_mois_min": _param("HL_ROI_MOIS_MIN", 0.05),
        "roi_mois_max": _param("HL_ROI_MOIS_MAX", 3.0),
        "rotation_max": _param("HL_ROTATION_MAX", 60.0),
        "rafraichir_cohorte_s": _param("HL_RAFRAICHIR_COHORTE_H", 6.0) * 3600,
        "rafraichir_positions_s": _param("HL_RAFRAICHIR_POSITIONS_S", 900.0),
    }


def coin_de(sym):
    """BTCUSDT -> BTC ; RNDRUSDT -> RENDER ; None si pas une paire USDT/USD/EUR."""
    if sym in ALIAS:
        return ALIAS[sym]
    for suf in ("USDT", "USDC", "USD", "EUR"):
        if sym.endswith(suf) and len(sym) > len(suf):
            return sym[: -len(suf)]
    return None


# ------------------------------------------------------------------ acces reseau (sans cle)
def _info(body, timeout=20):
    req = urllib.request.Request(URL_INFO, data=json.dumps(body).encode(), headers={"Content-Type": "application/json",
                                                                                  "User-Agent": "agent-ia-professeur/1.0"})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return json.load(r)


def _telecharger_classement(timeout=90):
    req = urllib.request.Request(URL_CLASSEMENT, headers={"User-Agent": "agent-ia-professeur/1.0"})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        morceaux = []
        while True:
            m = r.read(1 << 20)
            if not m:
                break
            morceaux.append(m)
    return b"".join(morceaux).decode("utf-8", "replace")


# ------------------------------------------------------------------ cohorte : « les meilleurs »
def _fen(r, k):
    for nom, w in r.get("windowPerformances") or []:
        if nom == k:
            return w
    return {}


def _f(x):
    try:
        return float(x)
    except Exception:
        return 0.0


def compacter(r):
    """Ne garde que ce qui sert d'une ligne du classement."""
    try:
        return {"adresse": r["ethAddress"], "nom": r.get("displayName") or "", "capital": _f(r.get("accountValue")),
                "pnl_sem": _f(_fen(r, "week").get("pnl")), "roi_sem": _f(_fen(r, "week").get("roi")),
                "vlm_sem": _f(_fen(r, "week").get("vlm")),
                "pnl_mois": _f(_fen(r, "month").get("pnl")), "roi_mois": _f(_fen(r, "month").get("roi")),
                "vlm_mois": _f(_fen(r, "month").get("vlm")),
                "pnl_total": _f(_fen(r, "allTime").get("pnl")), "roi_total": _f(_fen(r, "allTime").get("roi"))}
    except Exception:
        return None


def passe_filtres(c, p=None):
    """Les 4 filtres « meilleur » : capital, gagnant partout, rendement du mois sain, pas un teneur de marche."""
    p = p or reglages()
    if not c or c["capital"] < p["capital_min"]:
        return False
    if c["pnl_sem"] <= 0 or c["pnl_mois"] <= 0 or c["pnl_total"] <= 0 or c["roi_total"] <= 0:
        return False
    if not (p["roi_mois_min"] <= c["roi_mois"] <= p["roi_mois_max"]):
        return False
    if c["vlm_sem"] <= 0 or c["vlm_mois"] / max(c["capital"], 1.0) > p["rotation_max"]:
        return False
    return True


def note_regularite(c):
    return round(0.6 * min(c["roi_mois"], 1.0) + 0.2 * min(max(c["roi_sem"], 0.0), 0.3) / 0.3
                 + 0.2 * min(c["pnl_total"] / max(c["capital"], 1.0), 2.0) / 2.0, 4)


def iterer_classement(txt):
    """Lit le JSON du classement EN FLUX (objet par objet) pour ne pas garder 48 000 lignes en memoire."""
    dec = json.JSONDecoder()
    i = txt.find('"leaderboardRows"')
    i = txt.index("[", i if i >= 0 else 0) + 1
    n = len(txt)
    while i < n:
        while i < n and txt[i] in " \n\r\t,":
            i += 1
        if i >= n or txt[i] == "]":
            return
        obj, i = dec.raw_decode(txt, i)
        yield obj


def selectionner_cohorte(lignes, p=None):
    """lignes : iterable de lignes brutes du classement -> (cohorte triee, nb_lus, nb_filtres)."""
    p = p or reglages()
    gardes, lus = [], 0
    for r in lignes:
        lus += 1
        c = compacter(r)
        if c and passe_filtres(c, p):
            c["note"] = note_regularite(c)
            gardes.append(c)
    gardes.sort(key=lambda c: (-c["note"], -c["pnl_total"]))
    for rang, c in enumerate(gardes[: p["n_traders"]], 1):
        c["rang"] = rang
    return gardes[: p["n_traders"]], lus, len(gardes)


# ------------------------------------------------------------------ positions en direct
def lire_positions(cohorte, coins_suivis=None, pause=0.05):
    """-> {adresse: {"capital": x, "positions": {coin: {taille, valeur, levier, entree, pnl}}}} (erreurs ignorees)."""
    out = {}
    for c in cohorte:
        adr = c["adresse"]
        try:
            st = _info({"type": "clearinghouseState", "user": adr})
        except Exception:
            continue
        pos = {}
        for ap in st.get("assetPositions") or []:
            p = ap.get("position") or {}
            coin = p.get("coin")
            if not coin or (coins_suivis and coin not in coins_suivis):
                continue
            taille = _f(p.get("szi"))
            if abs(taille) <= 0:
                continue
            pos[coin] = {"taille": taille, "valeur": _f(p.get("positionValue")),
                         "levier": _f((p.get("leverage") or {}).get("value")), "entree": _f(p.get("entryPx")),
                         "pnl": _f(p.get("unrealizedPnl"))}
        out[adr] = {"capital": _f((st.get("marginSummary") or {}).get("accountValue")), "positions": pos}
        if pause:
            time.sleep(pause)
    return out


def mouvements(avant, apres):
    """Compare deux lectures -> [(adresse, coin, action)] avec action dans ouvre_long/renforce_long/ferme_long/
    ouvre_short/renforce_short/ferme_short. Un renfort = taille +20 % au moins."""
    mv = []
    for adr, d in apres.items():
        a0 = (avant.get(adr) or {}).get("positions") or {}
        a1 = d.get("positions") or {}
        for coin in set(a0) | set(a1):
            t0 = (a0.get(coin) or {}).get("taille", 0.0)
            t1 = (a1.get(coin) or {}).get("taille", 0.0)
            if t0 == t1:
                continue
            if t1 > 0 and t0 <= 0:
                mv.append((adr, coin, "ouvre_long"))
            elif t1 < 0 and t0 >= 0:
                mv.append((adr, coin, "ouvre_short"))
            elif t1 == 0 and t0 > 0:
                mv.append((adr, coin, "ferme_long"))
            elif t1 == 0 and t0 < 0:
                mv.append((adr, coin, "ferme_short"))
            elif t1 > 0 and t1 >= t0 * 1.2:
                mv.append((adr, coin, "renforce_long"))
            elif t1 < 0 and abs(t1) >= abs(t0) * 1.2:
                mv.append((adr, coin, "renforce_short"))
    return mv


def scalpeurs(profils, detention_min_h=1.0):
    """Adresses dont la detention mediane est sous detention_min_h : leurs positions changent plus vite que nos lectures
    (15 min), on ne peut ni les suivre ni apprendre d'elles -> exclues de la lecture des positions (pas de la cohorte)."""
    return {a for a, p in (profils or {}).items() if p.get("detention_mediane_h") is not None and p["detention_mediane_h"] < detention_min_h}


def agreger(positions, coins_suivis=None, exclus=()):
    """-> {coin: {long_usd, short_usd, n_long, n_short, biais_long (0..1), levier_moyen, pnl_latent}} (exclus = adresses ignorees)."""
    agg = {}
    for adr, d in positions.items():
        if adr in exclus:
            continue
        for coin, p in (d.get("positions") or {}).items():
            if coins_suivis and coin not in coins_suivis:
                continue
            a = agg.setdefault(coin, {"long_usd": 0.0, "short_usd": 0.0, "n_long": 0, "n_short": 0, "leviers": [],
                                      "pnl_latent": 0.0})
            if p["taille"] > 0:
                a["long_usd"] += p["valeur"]; a["n_long"] += 1
            else:
                a["short_usd"] += p["valeur"]; a["n_short"] += 1
            if p.get("levier"):
                a["leviers"].append(p["levier"])
            a["pnl_latent"] += p.get("pnl", 0.0)
    for coin, a in agg.items():
        tot = a["long_usd"] + a["short_usd"]
        a["biais_long"] = round(a["long_usd"] / tot, 3) if tot else 0.5
        a["levier_moyen"] = round(statistics.mean(a["leviers"]), 1) if a["leviers"] else None
        a.pop("leviers", None)
        a["long_usd"], a["short_usd"], a["pnl_latent"] = round(a["long_usd"]), round(a["short_usd"]), round(a["pnl_latent"])
    return agg


def votes_depuis(agg, mv, coin_vers_sym):
    """-> [(sym, sens, tag, detail)] : au plus un vote par crypto. sens = 'achat' ou 'vente'."""
    frais_long = {}
    frais_short = {}
    for adr, coin, act in mv:
        if act in ("ouvre_long", "renforce_long"):
            frais_long[coin] = frais_long.get(coin, 0) + 1
        elif act in ("ouvre_short", "renforce_short"):
            frais_short[coin] = frais_short.get(coin, 0) + 1
    votes = []
    for coin, sym in coin_vers_sym.items():
        a = agg.get(coin)
        if not a:
            continue
        n = a["n_long"] + a["n_short"]
        det = (f"{a['n_long']} longs {a['long_usd']/1e6:.1f} M$ / {a['n_short']} shorts {a['short_usd']/1e6:.1f} M$"
               f" (biais long {a['biais_long']*100:.0f} %)")
        if frais_long.get(coin) and a["biais_long"] >= 0.5 and a["n_long"] >= 1:
            votes.append((sym, "achat", "entree_longue", f"{frais_long[coin]} des meilleurs vient(nent) d'ouvrir/renforcer un long ; " + det))
        elif a["n_long"] >= MIN_TRADERS and a["biais_long"] >= SEUIL_BIAIS and a["n_long"] > a["n_short"]:
            votes.append((sym, "achat", "biais_long", det))
        elif frais_short.get(coin) and a["biais_long"] <= 0.5 and a["n_short"] >= 1:
            votes.append((sym, "vente", "entree_short", f"{frais_short[coin]} des meilleurs vient(nent) d'ouvrir/renforcer un short ; " + det))
        elif a["n_short"] >= MIN_TRADERS and (1 - a["biais_long"]) >= SEUIL_BIAIS and a["n_short"] > a["n_long"]:
            votes.append((sym, "vente", "biais_short", det))
        elif n:
            votes.append((sym, "neutre", "partage", det))
    return votes


# ------------------------------------------------------------------ apprendre leur style
def _var_24h_avant(bougies_1h, t_s):
    """Variation (%) du prix sur les 24 h qui precedent l'instant t_s, a partir de nos bougies 1 h."""
    if not bougies_1h:
        return None
    avant = [b for b in bougies_1h if b.get("temps", 0) <= t_s]
    if len(avant) < 25:
        return None
    return (avant[-1]["cloture"] / avant[-25]["cloture"] - 1) * 100


def profil_depuis_fills(fills, bougies_par_coin=None, levier=None):
    """Tire d'une liste d'ordres executes (userFills) le STYLE d'un trader. Tout est mesure, rien n'est suppose."""
    if not fills:
        return None
    fills = sorted(fills, key=lambda x: x.get("time", 0))
    t0, t1 = fills[0]["time"] / 1000, fills[-1]["time"] / 1000
    ouvertures = {"Open Long": 0, "Open Short": 0}
    usd_long = usd_short = 0.0
    clotures_gagnantes = clotures = 0
    pnl_realise = 0.0
    frais = 0.0
    durees = []
    derniere_ouverture = {}
    heures = {}
    var_entrees = []
    notional_par_coin = {}
    for x in fills:
        d = x.get("dir") or ""
        coin = x.get("coin")
        usd = _f(x.get("px")) * _f(x.get("sz"))
        frais += _f(x.get("fee"))
        notional_par_coin[coin] = notional_par_coin.get(coin, 0.0) + usd
        if d in ouvertures:
            ouvertures[d] += 1
            if d == "Open Long":
                usd_long += usd
            else:
                usd_short += usd
            derniere_ouverture.setdefault((coin, d[5:]), x["time"] / 1000)
            h = datetime.fromtimestamp(x["time"] / 1000, timezone.utc).hour
            heures[h] = heures.get(h, 0) + 1
            if bougies_par_coin and coin in bougies_par_coin:
                v = _var_24h_avant(bougies_par_coin[coin], x["time"] / 1000)
                if v is not None:
                    var_entrees.append(v if d == "Open Long" else -v)   # pour un short, « creux » = prix monte avant
        elif d.startswith("Close"):
            pnl = _f(x.get("closedPnl"))
            if pnl != 0:
                clotures += 1
                clotures_gagnantes += 1 if pnl > 0 else 0
            pnl_realise += pnl
            cle = (coin, d[6:])
            if cle in derniere_ouverture:
                durees.append((x["time"] / 1000 - derniere_ouverture.pop(cle)) / 3600)
    tot = usd_long + usd_short
    style_entree = None
    if len(var_entrees) >= 5:
        med = statistics.median(var_entrees)
        style_entree = ("achete les creux (contre-tendance)" if med < -1 else
                        "achete la force (suit le mouvement)" if med > 1 else "indifferent au mouvement des 24 h")
        style_entree += f" ; variation mediane 24 h avant l'entree {med:+.1f} %"
    top_coins = sorted(notional_par_coin.items(), key=lambda kv: -kv[1])[:3]
    heures_top = sorted(heures.items(), key=lambda kv: -kv[1])[:3]
    return {
        "n_ordres": len(fills), "jours": round((t1 - t0) / 86400, 1),
        "part_long": round(usd_long / tot * 100) if tot else None,
        "pct_clotures_gagnantes": round(clotures_gagnantes / clotures * 100) if clotures else None, "n_clotures": clotures,
        "pnl_realise": round(pnl_realise), "frais": round(frais),
        "detention_mediane_h": round(statistics.median(durees), 1) if durees else None,
        "style_entree": style_entree, "n_entrees_mesurees": len(var_entrees),
        "coins": [c for c, _ in top_coins], "heures_utc": [h for h, _ in heures_top],
        "levier_moyen": levier,
    }


def profiler(cohorte, positions, coins_suivis, sym_de_coin, n=10, pause=0.3):
    """Profil de style des n premiers de la cohorte (userFills, 2 000 derniers ordres chacun)."""
    bougies = {}
    try:
        import indicateurs as ind
        for coin in coins_suivis:
            sym = sym_de_coin.get(coin)
            if sym:
                try:
                    bougies[coin] = ind.historique_ohlcv(sym, "1h", 500) or []
                except Exception:
                    pass
    except Exception:
        pass
    profils = {}
    for c in cohorte[:n]:
        adr = c["adresse"]
        try:
            fills = _info({"type": "userFills", "user": adr}, timeout=30)
        except Exception:
            continue
        lev = [p.get("levier") for p in ((positions.get(adr) or {}).get("positions") or {}).values() if p.get("levier")]
        pr = profil_depuis_fills(fills, bougies, round(statistics.mean(lev), 1) if lev else None)
        if pr:
            pr["rang"] = c.get("rang"); pr["capital"] = c["capital"]; pr["roi_mois"] = c["roi_mois"]
            profils[adr] = pr
        if pause:
            time.sleep(pause)
    return profils


def lecon_cohorte(profils, detention_min_h=1.0):
    """Ce que les meilleurs ont en commun, en une phrase mesurable (ce que le bot doit apprendre). Les scalpeurs
    (detention < detention_min_h) sont comptes a part : on ne peut pas apprendre d'eux avec des lectures toutes les 15 min."""
    if not profils:
        return ""
    excl = scalpeurs(profils, detention_min_h)
    P = [p for a, p in profils.items() if a not in excl] or list(profils.values())
    parts_long = [p["part_long"] for p in P if p.get("part_long") is not None]
    wr = [p["pct_clotures_gagnantes"] for p in P if p.get("pct_clotures_gagnantes") is not None]
    det = [p["detention_mediane_h"] for p in P if p.get("detention_mediane_h") is not None]
    lev = [p["levier_moyen"] for p in P if p.get("levier_moyen")]
    creux = sum(1 for p in P if (p.get("style_entree") or "").startswith("achete les creux"))
    force = sum(1 for p in P if (p.get("style_entree") or "").startswith("achete la force"))
    heures = {}
    for p in P:
        for h in p.get("heures_utc") or []:
            heures[h] = heures.get(h, 0) + 1
    h_top = sorted(heures.items(), key=lambda kv: -kv[1])[:3]
    L = [f"{len(P)} profils mesures" + (f" ({len(excl)} scalpeurs < {detention_min_h:g} h mis a part)" if excl else "")]
    if parts_long:
        L.append(f"exposition longue mediane {statistics.median(parts_long):.0f} % (le reste en short)")
    if wr:
        L.append(f"clotures gagnantes medianes {statistics.median(wr):.0f} %")
    if det:
        L.append(f"detention mediane {statistics.median(det):.0f} h")
    if creux or force:
        L.append(f"{creux} achetent les creux / {force} achetent la force")
    if lev:
        L.append(f"levier moyen {statistics.median(lev):.0f}x (nous : comptant, 1x)")
    if h_top:
        L.append("heures actives UTC " + ", ".join(f"{h}h" for h, _ in h_top))
    return " ; ".join(L)


# ------------------------------------------------------------------ etat partage (fichier)
def _charger():
    try:
        with open(FICHIER, encoding="utf-8") as f:
            d = json.load(f)
    except Exception:
        d = {}
    d.setdefault("votes", [])
    d.setdefault("stats", {"n": 0, "tp": 0, "sl": 0, "neutre": 0, "rendement_cumule": 0.0})
    d.setdefault("cohorte", [])
    d.setdefault("cohorte_ts", 0)
    d.setdefault("cohorte_info", {})
    d.setdefault("positions", {})
    d.setdefault("positions_ts", 0)
    d.setdefault("agregats", {})
    d.setdefault("mouvements", [])
    d.setdefault("profils", {})
    d.setdefault("lecon", "")
    d.setdefault("votes_du_moment", [])
    d.setdefault("erreurs", [])
    return d


def _sauver(d):
    d["votes"] = d["votes"][-2000:]
    d["erreurs"] = d["erreurs"][-20:]
    d["mouvements"] = d["mouvements"][-200:]
    tmp = FICHIER + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(d, f, ensure_ascii=False, indent=1)
    os.replace(tmp, FICHIER)


def _erreur(d, msg):
    d["erreurs"].append({"date": datetime.now().strftime("%Y-%m-%d %H:%M"), "msg": str(msg)[:200]})


def _coins(symboles):
    """-> (coins_suivis, coin->sym) : seulement les coins listes sur Hyperliquid (univers mis en cache 24 h)."""
    univers = _univers()
    cs = {}
    for s in symboles:
        c = coin_de(s)
        if c and (not univers or c in univers):
            cs[c] = s
    return set(cs), cs


_UNIVERS = {"ts": 0, "coins": set()}


def _univers():
    if time.time() - _UNIVERS["ts"] < 86400 and _UNIVERS["coins"]:
        return _UNIVERS["coins"]
    try:
        m = _info({"type": "meta"})
        _UNIVERS["coins"] = {u["name"] for u in m.get("universe", []) if not u.get("isDelisted")}
        _UNIVERS["ts"] = time.time()
    except Exception:
        pass
    return _UNIVERS["coins"]


def rafraichir_cohorte(symboles, avec_profils=True):
    """Relit le classement complet, choisit la cohorte, lit ses positions, profile les premiers. Lent (20-60 s)."""
    p = reglages()
    d = _charger()
    try:
        txt = _telecharger_classement()
        cohorte, lus, filtres = selectionner_cohorte(iterer_classement(txt), p)
        del txt
    except Exception as e:
        d = _charger(); _erreur(d, f"classement: {e}"); _sauver(d)
        return False
    coins_suivis, c2s = _coins(symboles)
    positions = lire_positions(cohorte, coins_suivis)
    d = _charger()
    mv = mouvements(d["positions"], positions) if d["positions"] else []
    d["cohorte"], d["cohorte_ts"] = cohorte, time.time()
    d["cohorte_info"] = {"lus": lus, "passent_filtres": filtres, "gardes": len(cohorte), "reglages": p,
                         "date": datetime.now().strftime("%Y-%m-%d %H:%M")}
    d["positions"], d["positions_ts"] = positions, time.time()
    if avec_profils:
        try:
            profils = profiler(cohorte, positions, coins_suivis, c2s, n=p["n_profils"])
            if profils:
                d["profils"] = profils
                d["lecon"] = lecon_cohorte(profils, p["detention_min_h"])
        except Exception as e:
            _erreur(d, f"profils: {e}")
    excl = scalpeurs(d["profils"], p["detention_min_h"])
    mv = [m for m in mv if m[0] not in excl]
    d["agregats"] = agreger(positions, coins_suivis, excl)
    d["mouvements"] += [{"ts": time.time(), "adresse": a, "coin": c, "action": act} for a, c, act in mv]
    _sauver(d)
    _journaliser_votes(d, c2s, mv)
    return True


def rafraichir_positions(symboles):
    """Relit seulement les positions de la cohorte (rapide : 1 appel par trader)."""
    d = _charger()
    if not d["cohorte"]:
        return False
    coins_suivis, c2s = _coins(symboles)
    positions = lire_positions(d["cohorte"], coins_suivis)
    if not positions:
        _erreur(d, "positions: aucune reponse"); _sauver(d)
        return False
    d = _charger()
    excl = scalpeurs(d["profils"], reglages()["detention_min_h"])
    mv = [m for m in mouvements(d["positions"], positions) if m[0] not in excl] if d["positions"] else []
    d["positions"], d["positions_ts"] = positions, time.time()
    d["agregats"] = agreger(positions, coins_suivis, excl)
    d["mouvements"] += [{"ts": time.time(), "adresse": a, "coin": c, "action": act} for a, c, act in mv]
    _sauver(d)
    _journaliser_votes(d, c2s, mv)
    return True


def _thread(nom, fn, *args):
    with _VERROU:
        if _EN_COURS.get(nom):
            return False
        _EN_COURS[nom] = True

    def run():
        try:
            fn(*args)
        except Exception as e:
            d = _charger(); _erreur(d, f"{nom}: {e}"); _sauver(d)
        finally:
            with _VERROU:
                _EN_COURS[nom] = False
    threading.Thread(target=run, name=f"hl-{nom}", daemon=True).start()
    return True


def rafraichir_si_besoin(symboles, bloquant=False):
    """Appele a chaque cycle : lance (en arriere-plan) la relecture de la cohorte toutes les 6 h et des positions toutes
    les 15 min. Ne bloque jamais le bot, sauf bloquant=True (CLI)."""
    if not _actif():
        return
    p = reglages()
    d = _charger()
    now = time.time()
    if now - d["cohorte_ts"] > p["rafraichir_cohorte_s"] or not d["cohorte"]:
        if bloquant:
            rafraichir_cohorte(symboles)
        else:
            _thread("cohorte", rafraichir_cohorte, symboles)
    elif now - d["positions_ts"] > p["rafraichir_positions_s"]:
        if bloquant:
            rafraichir_positions(symboles)
        else:
            _thread("positions", rafraichir_positions, symboles)


# ------------------------------------------------------------------ votes, jugement, fiabilite
def _prix_actuel(sym):
    try:
        import indicateurs as ind
        b = ind.historique_ohlcv(sym, "15m", 3) or []
        return float(b[-1]["cloture"]) if b else None
    except Exception:
        return None


def _barriere(sym):
    try:
        import professeurs_externes as pex
        return pex._barriere(sym, None)
    except Exception:
        return 1.5, 3.0


def _journaliser_votes(d, c2s, mv):
    votes = votes_depuis(d["agregats"], mv, c2s)
    now = time.time()
    d["votes_du_moment"] = [{"sym": s, "sens": sens, "tag": tag, "detail": det} for s, sens, tag, det in votes]
    for sym, sens, tag, det in votes:
        if sens == "neutre":
            continue
        recent = any(v["sym"] == sym and v["sens"] == sens and now - v["ts"] < REFROIDISSEMENT_VOTE_S for v in d["votes"][-300:])
        if recent:
            continue
        prix = _prix_actuel(sym)
        if not prix:
            continue
        sl, tp = _barriere(sym)
        d["votes"].append({"ts": now, "date": datetime.now().strftime("%Y-%m-%d %H:%M"), "sym": sym, "prof": PROF,
                           "sens": sens, "tag": tag, "detail": det, "prix": float(prix), "sl_pct": sl, "tp_pct": tp,
                           "resultat": None, "rendement": None, "heure_utc": datetime.now(timezone.utc).hour})
    _sauver(d)


def evaluer_votes():
    """Juge les votes en attente sur les bougies 1 h, dans le SENS du vote (achat : stop en bas ; vente : stop en haut)."""
    d = _charger()
    now = time.time()
    attente = [v for v in d["votes"] if v.get("resultat") is None and now - v["ts"] >= 3600]
    if not attente:
        return 0
    try:
        import indicateurs as ind
    except Exception:
        return 0
    n_eval, cache = 0, {}
    for v in attente:
        sym = v["sym"]
        if sym not in cache:
            try:
                cache[sym] = ind.historique_ohlcv(sym, "1h", 60) or []
            except Exception:
                cache[sym] = []
        b1 = [b for b in cache[sym] if b.get("temps", 0) > v["ts"]]
        if not b1:
            continue
        p0, achat = v["prix"], v.get("sens", "achat") == "achat"
        res, rend = None, None
        for b in b1:
            if achat:
                if b["bas"] <= p0 * (1 - v["sl_pct"] / 100):
                    res, rend = "sl", -v["sl_pct"]; break
                if b["haut"] >= p0 * (1 + v["tp_pct"] / 100):
                    res, rend = "tp", v["tp_pct"]; break
            else:
                if b["haut"] >= p0 * (1 + v["sl_pct"] / 100):
                    res, rend = "sl", -v["sl_pct"]; break
                if b["bas"] <= p0 * (1 - v["tp_pct"] / 100):
                    res, rend = "tp", v["tp_pct"]; break
        if res is None and now - v["ts"] >= BARRIERE_H * 3600:
            var = (b1[-1]["cloture"] / p0 - 1) * 100
            res, rend = "neutre", round(var if achat else -var, 2)
        if res is None:
            continue
        v["resultat"], v["rendement"], v["evalue_le"] = res, rend, datetime.now().strftime("%Y-%m-%d %H:%M")
        st = d["stats"]
        st["n"] += 1; st[res] += 1; st["rendement_cumule"] = round(st["rendement_cumule"] + rend, 2)
        n_eval += 1
    _sauver(d)
    return n_eval


def fiabilite(d=None):
    d = d or _charger()
    st = d["stats"]
    n = st.get("tp", 0) + st.get("sl", 0)
    pct = st["tp"] / n * 100 if n else None
    return n, pct, bool(n >= N_FIABLE and pct is not None and pct >= WR_FIABLE)


def vote_du_moment(sym, d=None):
    d = d or _charger()
    for v in d.get("votes_du_moment") or []:
        if v["sym"] == sym:
            return v
    return None


def bonus_preselection(sym):
    """+0,5 si le professeur est FIABLE et que les meilleurs sont longs sur sym ; -0,5 s'ils sont courts. Sinon 0."""
    if not _actif():
        return 0.0, ""
    try:
        d = _charger()
        v = vote_du_moment(sym, d)
        if not v or v["sens"] == "neutre":
            return 0.0, ""
        _, _, ok = fiabilite(d)
        if not ok:
            return 0.0, ""
        return (0.5, f"hyperliquid {v['tag']}") if v["sens"] == "achat" else (-0.5, f"hyperliquid {v['tag']}")
    except Exception:
        return 0.0, ""


def _adr_court(a):
    return a[:6] + ".." + a[-4:] if a and len(a) > 12 else a


def contexte_pour_cerveau(symboles, prix_data=None):
    """Texte insere dans le dossier de l'analyste. Declenche le rafraichissement en arriere-plan."""
    if not _actif():
        return ""
    try:
        evaluer_votes()
    except Exception:
        pass
    try:
        rafraichir_si_besoin(symboles)
    except Exception:
        pass
    d = _charger()
    if not d["cohorte"]:
        return ("\nPROFESSEUR HYPERLIQUID (les meilleurs traders verifies sur chaine) : premiere lecture en cours, rien a dire encore."
                + (" Derniere erreur : " + d["erreurs"][-1]["msg"] if d["erreurs"] else "") + "\n")
    st = d["stats"]
    n, pct, ok = fiabilite(d)
    age_pos = (time.time() - d["positions_ts"]) / 60
    info = d["cohorte_info"]
    L = ["\nPROFESSEUR HYPERLIQUID (bourse de perpetuels sur chaine : positions et gains publics, verifiables, sans cle). "
         "CONSIGNE DE L'UTILISATEUR : suivre SEULEMENT les meilleurs et APPRENDRE leur facon de trader. Il n'ouvre rien : il vote et il est juge.",
         f"  Cohorte : {info.get('gardes', len(d['cohorte']))} traders gardes sur {info.get('lus', '?')} comptes "
         f"(capital >= {info.get('reglages', {}).get('capital_min', 0)/1e3:.0f} k$, gagnants semaine+mois+total, rendement du mois sain, pas teneurs de marche) ; "
         f"positions lues il y a {age_pos:.0f} min."]
    if st["n"]:
        L.append(f"  Fiabilite mesuree chez nous (barriere stop 2xATR / objectif 2:1 / 24 h) : {st['n']} votes -> {st['tp']} objectifs / "
                 f"{st['sl']} stops / {st['neutre']} neutres" + (f" ({pct:.0f} % sur les tranches{', FIABLE' if ok else ''})" if pct is not None else ""))
    else:
        L.append("  Fiabilite : aucun vote evalue encore (seulement lu, aucune influence sur la preselection).")
    if d.get("lecon"):
        L.append("  CE QUE FONT LES MEILLEURS (mesure sur leurs 2 000 derniers ordres) : " + d["lecon"])
    _, c2s = _coins(symboles)
    lignes = []
    for coin, a in sorted(d["agregats"].items(), key=lambda kv: -(kv[1]["long_usd"] + kv[1]["short_usd"])):
        sym = c2s.get(coin)
        if not sym:
            continue
        v = vote_du_moment(sym, d)
        tag = f" -> {v['sens'].upper()} ({v['tag']})" if v and v["sens"] != "neutre" else ""
        lignes.append(f"  {sym}: {a['n_long']} longs {a['long_usd']/1e6:.1f} M$ / {a['n_short']} shorts {a['short_usd']/1e6:.1f} M$, "
                      f"biais long {a['biais_long']*100:.0f} %" + (f", levier moyen {a['levier_moyen']}x" if a.get("levier_moyen") else "") + tag)
    L.append("  Positions des meilleurs sur nos cryptos :" if lignes else "  Aucune position des meilleurs sur nos cryptos en ce moment.")
    L += lignes[:12]
    recents = [m for m in d["mouvements"] if time.time() - m["ts"] < 3 * 3600 and c2s.get(m["coin"])]
    if recents:
        L.append("  Mouvements des 3 dernieres heures : " + " ; ".join(f"{_adr_court(m['adresse'])} {m['action']} {c2s[m['coin']]}" for m in recents[-8:]))
    L.append("  A retenir : un biais des meilleurs est un argument de plus dans ta checklist, pas un ordre. Les shorts des meilleurs sont un signal de PRUDENCE pour nos achats. "
             "Leur levier et leurs durees ne se copient pas au comptant : on apprend leur sens et leur timing, pas leur taille.")
    return "\n".join(L) + "\n"


def resume_court(symboles):
    """Une ligne pour le journal du bot."""
    d = _charger()
    if not d["cohorte"]:
        return "premiere lecture de la cohorte en cours" + (" (derniere erreur : " + d["erreurs"][-1]["msg"][:60] + ")" if d["erreurs"] else "")
    _, c2s = _coins(symboles)
    morceaux = []
    for coin in ("BTC", "ETH", "SOL"):
        a = d["agregats"].get(coin)
        if a and c2s.get(coin):
            morceaux.append(f"{coin} long {a['biais_long']*100:.0f} % ({a['n_long']}L/{a['n_short']}S {(a['long_usd']+a['short_usd'])/1e6:.0f} M$)")
    votes = [v for v in d.get("votes_du_moment") or [] if v["sens"] != "neutre"]
    n_a = sum(1 for v in votes if v["sens"] == "achat"); n_v = len(votes) - n_a
    n, pct, ok = fiabilite(d)
    age = (time.time() - d["positions_ts"]) / 60
    return (f"[HYPERLIQUID] {len(d['cohorte'])} meilleurs, positions il y a {age:.0f} min | " + " | ".join(morceaux)
            + f" | votes achat {n_a} / vente {n_v} | fiabilite {n} tranches" + (f" {pct:.0f} %" if pct is not None else "")
            + (" FIABLE" if ok else " (en observation)"))


# ------------------------------------------------------------------ rapport
def rapport(symboles=None):
    d = _charger()
    p = reglages()
    n, pct, ok = fiabilite(d)
    st = d["stats"]
    info = d["cohorte_info"]
    L = [f"PROFESSEUR HYPERLIQUID — {'actif' if _actif() else 'DESACTIVE (PROF_HYPERLIQUID=0)'} — mode professeur : aucun droit d'ouvrir",
         f"Reglages : {p['n_traders']} traders, capital >= {p['capital_min']/1e3:.0f} k$, rendement du mois {p['roi_mois_min']*100:.0f}-{p['roi_mois_max']*100:.0f} %, "
         f"rotation <= {p['rotation_max']:.0f}x, cohorte toutes les {p['rafraichir_cohorte_s']/3600:.0f} h, positions toutes les {p['rafraichir_positions_s']/60:.0f} min"]
    if d["cohorte"]:
        L.append(f"Cohorte du {info.get('date')} : {info.get('gardes')} gardes / {info.get('passent_filtres')} passent les filtres / {info.get('lus')} comptes lus")
        for c in d["cohorte"][:10]:
            L.append(f"  #{c['rang']:2d} {_adr_court(c['adresse'])} {c['nom'][:14]:14s} capital {c['capital']/1e6:5.1f} M$ | mois {c['roi_mois']*100:+6.1f} % | "
                     f"semaine {c['roi_sem']*100:+5.1f} % | total {c['pnl_total']/1e6:+6.1f} M$ | note {c['note']:.2f}")
    else:
        L.append("Cohorte : pas encore lue (python3 professeur_hyperliquid.py rafraichir)")
    L.append(f"Votes : {st['n']} evalues | {st['tp']} objectifs / {st['sl']} stops / {st['neutre']} neutres"
             + (f" | {pct:.0f} % sur les tranches" if pct is not None else "") + f" | rendement cumule {st['rendement_cumule']:+.1f} % | "
             f"{sum(1 for v in d['votes'] if v.get('resultat') is None)} en attente | {'FIABLE' if ok else 'en observation'}")
    if d.get("lecon"):
        L.append("Ce que font les meilleurs : " + d["lecon"])
    for adr, pr in list(d["profils"].items())[:12]:
        L.append(f"  #{pr.get('rang')} {_adr_court(adr)} : {pr['n_ordres']} ordres sur {pr['jours']} j | long {pr['part_long']} % | "
                 f"clotures gagnantes {pr['pct_clotures_gagnantes']} % ({pr['n_clotures']}) | detention {pr['detention_mediane_h']} h | "
                 f"{pr.get('style_entree') or 'style d entree non mesure'} | coins {','.join(pr['coins'])} | levier {str(pr.get('levier_moyen')) + 'x' if pr.get('levier_moyen') else 'n/d'}"
                 + (" | SCALPEUR (positions non lues)" if pr.get("detention_mediane_h") is not None and pr["detention_mediane_h"] < p["detention_min_h"] else ""))
    if d["agregats"]:
        L.append(f"Positions de la cohorte (lues {datetime.fromtimestamp(d['positions_ts']).strftime('%H:%M')}) :")
        for coin, a in sorted(d["agregats"].items(), key=lambda kv: -(kv[1]["long_usd"] + kv[1]["short_usd"]))[:15]:
            L.append(f"  {coin:7s} {a['n_long']:2d} longs {a['long_usd']/1e6:6.1f} M$ | {a['n_short']:2d} shorts {a['short_usd']/1e6:6.1f} M$ | biais long {a['biais_long']*100:3.0f} %"
                     + (f" | levier {a['levier_moyen']}x" if a.get("levier_moyen") else ""))
    for v in d.get("votes_du_moment") or []:
        if v["sens"] != "neutre":
            L.append(f"  vote {v['sens'].upper():5s} {v['sym']:9s} {v['tag']:14s} {v['detail'][:90]}")
    recents = d["votes"][-10:]
    if recents:
        L.append("Derniers votes journalises :")
        for v in reversed(recents):
            r = v.get("resultat")
            issue = ("-> " + r + ("" if v.get("rendement") is None else " %+.1f%%" % v["rendement"])) if r else "(en attente)"
            L.append("  %s %-9s %-5s %-14s %s" % (v["date"], v["sym"], v["sens"], v["tag"], issue))
    if d["erreurs"]:
        L.append("Dernieres erreurs : " + " | ".join(f"{e['date']} {e['msg'][:80]}" for e in d["erreurs"][-3:]))
    return "\n".join(L)


def _symboles_du_bot():
    try:
        import paper_trading as pt
        return [s for s, c in pt.MARCHES_PAPER.items() if c.get("marche") == "crypto"]
    except Exception:
        return ["BTCUSDT", "ETHUSDT", "SOLUSDT", "BNBUSDT", "XRPUSDT", "DOGEUSDT", "AVAXUSDT", "LINKUSDT", "SUIUSDT", "ARBUSDT"]


if __name__ == "__main__":
    cmd = sys.argv[1] if len(sys.argv) > 1 else ""
    if cmd == "rafraichir":
        syms = _symboles_du_bot()
        t = time.time()
        ok = rafraichir_cohorte(syms)
        print(f"{'OK' if ok else 'ECHEC'} en {time.time()-t:.0f} s")
        print(rapport())
    elif cmd == "positions":
        syms = _symboles_du_bot()
        rafraichir_positions(syms)
        print(rapport())
    elif cmd == "evaluer":
        print(f"{evaluer_votes()} vote(s) juge(s)")
        print(rapport())
    else:
        print(rapport())
