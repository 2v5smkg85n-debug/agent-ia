#!/usr/bin/env python3
"""
strategies_tendance.py — les deux familles de strategies qui ont fait leurs preuves sur 8 a 10 ans en achat seul
(revue du 07/11/2026, voir STRATEGIES_EPROUVEES_07_11_2026.md), portees dans le bot AVEC le droit d'ouvrir
(decision de l'utilisateur du 07/11), en probation du registre (1 position max par strategie, jugee sur ses trades).

    donchian_breakout : cloture 4 h (bougie TERMINEE) au-dessus du plus haut des 20 bougies precedentes,
                        volume de la bougie > moyenne des 20 precedentes, prix au-dessus de son EMA 84 jours.
                        Sortie propre : cloture 4 h sous le plus bas des 10 bougies precedentes.
                        (Boring Edge 2017-2026 : CAGR 48 % vs 37 % passif, pire chute -54 % vs -83 % ; CoinQuant 10 ans
                        en 1 h avec filtre volume : +774 %, Sharpe 0,79 ; Hudson & Urquhart : famille la plus robuste.)
    tsmom             : rendement 20 jours > 0 ET 90 jours > 0 ET prix > SMA 200 jours, et le rendement 20 jours
                        vient de repasser positif (dans les TSMOM_FRAICHEUR derniers jours) : on prend le retournement,
                        on ne court pas apres une hausse deja vieille. Sortie propre : rendement 20 jours < 0.
                        (Review of Asset Pricing Studies 2026 : « preuve forte » ; Backtest Everything 2017-2024 :
                        45 %/an, pire chute 38 %, Sharpe 1,3 avec cible de volatilite.)

Ce qui change pour ces positions (et seulement elles) :
    - objectif TENDANCE_TP_RATIO x stop (3:1, defaut) avec stop suiveur apres l'objectif ; barriere de temps
      TENDANCE_BARRIERE_H (168 h = 7 jours) au lieu de 24 h : une tendance se paie en jours, pas en heures ;
    - stop 2 x ATR inchange ; taille = risque / stop inchangee (le palier de risque du bot s'applique) ;
    - les sorties « 24 h » (live-exit, pattern, stale) ne s'appliquent pas : stop, objectif suivi, sortie propre, barriere ;
    - a la porte, les filtres « fenetres » et « CUSUM » sont mesures mais ne bloquent pas ces strategies (une cassure
      EST un evenement de prix ; les fenetres ont ete apprises sur des trades de 24 h) ; tout le reste bloque normalement.

Filtre de regime pour les strategies de RETOUR A LA MOYENNE (rsi_oversold, consensus_reversion, pattern_reversal...) :
    ADX(14) 4 h de la crypto > ADX_RANGE_MAX (25) -> pas d'achat a contre-tendance (Vantixs 2023-2025 : facteur de profit
    1,11 sans filtre, 1,78 avec ; en tendance ADX > 30 la meme regle perd). Filtre de la porte PORTE_ADX_RANGE, mesure.

Score de tendance (dossier de l'analyste + tri de preselection) : part des 9 canaux Donchian (5 a 360 jours) dont la
cloture est au-dessus du milieu (Catching Crypto Trends 2015-2025 : l'ensemble des 9 horizons, Sharpe 1,58).

Tout est debrayable : TENDANCE=0 dans .env coupe les deux strategies ; droits : python3 registre_strategies.py droit <s> off.
CLI : python3 strategies_tendance.py [SYMBOLE ...]   -> etat des signaux
"""
import os
import sys
import time

DOSSIER = os.path.dirname(os.path.abspath(__file__))

TENDANCE = ("donchian_breakout", "tsmom")
REVERSION = ("rsi_oversold", "consensus_reversion", "pattern_reversal", "bollinger_bounce", "divergence_rsi", "vwap_bounce")


def _env(nom, defaut):
    try:
        from config_env import lire
        v = lire(nom, None)
        if v is not None and str(v) != "":
            return v
    except Exception:
        pass
    return os.getenv(nom, defaut)


def actif():
    return str(_env("TENDANCE", "1")).strip().lower() not in ("0", "false", "non", "off")


DONCHIAN_ENTREE = int(_env("DONCHIAN_ENTREE", "20"))
DONCHIAN_SORTIE = int(_env("DONCHIAN_SORTIE", "10"))
DONCHIAN_VOL = float(_env("DONCHIAN_VOL", "1.0"))        # volume de la bougie de cassure > 1,0 x moyenne 20
EMA_JOURS = int(_env("TENDANCE_EMA_JOURS", "84"))          # meme horizon que la tendance lente de la porte
TSMOM_COURT = int(_env("TSMOM_COURT", "20"))
TSMOM_LONG = int(_env("TSMOM_LONG", "90"))
TSMOM_SMA = int(_env("TSMOM_SMA", "200"))
TSMOM_FRAICHEUR = int(_env("TSMOM_FRAICHEUR", "5"))        # le rendement 20 j doit avoir ete <= 0 dans les 5 derniers jours
TP_RATIO = float(_env("TENDANCE_TP_RATIO", "3.0"))
BARRIERE_H = int(_env("TENDANCE_BARRIERE_H", "168"))
ADX_RANGE_MAX = float(_env("ADX_RANGE_MAX", "25"))
HORIZONS_SCORE = (5, 10, 20, 30, 60, 90, 150, 250, 360)

_CACHE = {}          # (sym, "4h"/"1d") -> (ts, bougies)
_TTL = {"4h": 900, "1d": 3600}


# ------------------------------------------------------------------ donnees
def _bougies(sym, intervalle, n):
    cle = (sym, intervalle)
    now = time.time()
    if cle in _CACHE and now - _CACHE[cle][0] < _TTL.get(intervalle, 900):
        return _CACHE[cle][1]
    try:
        import indicateurs as ind
        b = ind.historique_ohlcv(sym, intervalle, n) or []
    except Exception:
        b = []
    if b:
        _CACHE[cle] = (now, b)
    return b


def _f(b, k):
    try:
        return float(b.get(k))
    except Exception:
        return None


def _ema(valeurs, n):
    if len(valeurs) < n:
        return None
    k = 2.0 / (n + 1)
    e = sum(valeurs[:n]) / n
    for v in valeurs[n:]:
        e = v * k + e * (1 - k)
    return e


def _bougie_en_cours(b, intervalle):
    """La derniere bougie renvoyee par les sources est souvent celle EN COURS : on ne decide que sur une bougie
    terminee (sinon une meche intra-bougie declencherait une cassure qui n'existera peut-etre plus a la cloture)."""
    if not b:
        return False
    t = _f(b[-1], "temps")
    if not t:
        return True
    if t > 1e11:
        t = t / 1000.0
    duree = 4 * 3600 if intervalle == "4h" else 24 * 3600
    return time.time() - t < duree


def _series(b):
    return ([_f(x, "cloture") for x in b], [_f(x, "haut") for x in b], [_f(x, "bas") for x in b], [_f(x, "volume") or 0.0 for x in b])


# ------------------------------------------------------------------ tendance longue de la crypto
def au_dessus_ema(sym, b1d=None):
    """(bool|None, ecart_pct) : cloture journaliere au-dessus de son EMA 84 jours."""
    b1d = b1d or _bougies(sym, "1d", max(EMA_JOURS * 2, 220))
    c = [x for x in _series(b1d)[0] if x]
    if len(c) < EMA_JOURS + 5:
        return None, None
    e = _ema(c, EMA_JOURS)
    if not e:
        return None, None
    return c[-1] > e, round((c[-1] / e - 1) * 100, 2)


# ------------------------------------------------------------------ donchian
def donchian(sym, b4h=None, b1d=None):
    """Signal de cassure sur la DERNIERE bougie 4 h terminee. Retourne un dict (signal, raison, niveaux)."""
    out = {"strategie": "donchian_breakout", "signal": False, "raison": ""}
    b4h = b4h or _bougies(sym, "4h", DONCHIAN_ENTREE + 30)
    if len(b4h) < DONCHIAN_ENTREE + 3:
        out["raison"] = "pas assez de bougies 4h"
        return out
    c, h, l, v = _series(b4h)
    i = len(b4h) - 2 if _bougie_en_cours(b4h, "4h") else len(b4h) - 1     # indice de la derniere bougie terminee
    if i < DONCHIAN_ENTREE + 1 or c[i] is None:
        out["raison"] = "pas assez de bougies 4h"
        return out
    plus_haut = max(x for x in h[i - DONCHIAN_ENTREE:i] if x is not None)
    plus_bas_sortie = min(x for x in l[i - DONCHIAN_SORTIE:i] if x is not None)
    vol_moy = sum(v[i - DONCHIAN_ENTREE:i]) / float(DONCHIAN_ENTREE)
    ratio_vol = (v[i] / vol_moy) if vol_moy > 0 else None
    cassure = c[i] > plus_haut
    vol_ok = ratio_vol is None or ratio_vol >= DONCHIAN_VOL     # pas de volume (source) -> on ne bloque pas, on note
    ema_ok, ecart = au_dessus_ema(sym, b1d)
    out.update({"cloture": c[i], "plus_haut_20": plus_haut, "sortie_10": plus_bas_sortie, "ratio_volume": None if ratio_vol is None else round(ratio_vol, 2),
                "ema84_ok": ema_ok, "ecart_ema84_pct": ecart, "cassure": cassure})
    if not cassure:
        out["raison"] = f"pas de cassure (cloture {c[i]:.6g} <= plus haut 20 {plus_haut:.6g})"
    elif not vol_ok:
        out["raison"] = f"cassure sans volume (x{ratio_vol:.2f} < x{DONCHIAN_VOL})"
    elif ema_ok is False:
        out["raison"] = f"cassure sous l'EMA {EMA_JOURS} j ({ecart:+.1f} %) : pas de tendance de fond"
    else:
        out["signal"] = True
        out["raison"] = (f"cassure Donchian {DONCHIAN_ENTREE} (cloture 4h {c[i]:.6g} > {plus_haut:.6g}), volume x{ratio_vol if ratio_vol is None else round(ratio_vol, 2)}, "
                         f"EMA {EMA_JOURS} j {'ok' if ema_ok else 'inconnue'} ; sortie sous {plus_bas_sortie:.6g}")
    return out


def sortie_donchian(sym, b4h=None):
    """(True, raison) si la derniere cloture 4 h terminee est sous le plus bas des DONCHIAN_SORTIE bougies precedentes."""
    b4h = b4h or _bougies(sym, "4h", DONCHIAN_SORTIE + 30)
    if len(b4h) < DONCHIAN_SORTIE + 3:
        return False, "pas assez de bougies 4h"
    c, h, l, v = _series(b4h)
    i = len(b4h) - 2 if _bougie_en_cours(b4h, "4h") else len(b4h) - 1
    if i < DONCHIAN_SORTIE + 1 or c[i] is None:
        return False, "pas assez de bougies 4h"
    plus_bas = min(x for x in l[i - DONCHIAN_SORTIE:i] if x is not None)
    if c[i] < plus_bas:
        return True, f"cloture 4h {c[i]:.6g} sous le plus bas {DONCHIAN_SORTIE} bougies ({plus_bas:.6g})"
    return False, f"cloture {c[i]:.6g} > plus bas {DONCHIAN_SORTIE} ({plus_bas:.6g})"


# ------------------------------------------------------------------ tsmom
def _rendements(c, i, n):
    if i - n < 0 or not c[i] or not c[i - n]:
        return None
    return c[i] / c[i - n] - 1.0


def tsmom(sym, b1d=None):
    out = {"strategie": "tsmom", "signal": False, "raison": ""}
    b1d = b1d or _bougies(sym, "1d", max(TSMOM_SMA + 10, 260))
    c = _series(b1d)[0]
    i = len(c) - 2 if _bougie_en_cours(b1d, "1d") else len(c) - 1
    if i < TSMOM_SMA or c[i] is None:
        out["raison"] = f"pas assez de bougies journalieres ({len(c)} < {TSMOM_SMA + 1})"
        return out
    r_court = _rendements(c, i, TSMOM_COURT)
    r_long = _rendements(c, i, TSMOM_LONG)
    fen = [x for x in c[i - TSMOM_SMA + 1:i + 1] if x]
    sma = sum(fen) / len(fen) if fen else None
    frais = any((_rendements(c, i - k, TSMOM_COURT) or 0) <= 0 for k in range(1, TSMOM_FRAICHEUR + 1))
    out.update({"cloture": c[i], "r20_pct": None if r_court is None else round(r_court * 100, 2), "r90_pct": None if r_long is None else round(r_long * 100, 2),
                "sma200": sma, "au_dessus_sma200": (sma is not None and c[i] > sma), "retournement_recent": frais})
    if r_court is None or r_long is None or sma is None:
        out["raison"] = "donnees incompletes"
    elif r_court <= 0:
        out["raison"] = f"rendement {TSMOM_COURT} j {r_court * 100:+.1f} % <= 0"
    elif r_long <= 0:
        out["raison"] = f"rendement {TSMOM_LONG} j {r_long * 100:+.1f} % <= 0"
    elif c[i] <= sma:
        out["raison"] = f"sous la SMA {TSMOM_SMA} j"
    elif not frais:
        out["raison"] = f"hausse deja ancienne (rendement {TSMOM_COURT} j positif depuis plus de {TSMOM_FRAICHEUR} j) : on ne court pas apres"
    else:
        out["signal"] = True
        out["raison"] = f"momentum {TSMOM_COURT} j {r_court * 100:+.1f} % et {TSMOM_LONG} j {r_long * 100:+.1f} %, au-dessus de la SMA {TSMOM_SMA} j, retournement recent"
    return out


def sortie_tsmom(sym, b1d=None):
    b1d = b1d or _bougies(sym, "1d", TSMOM_COURT + 40)
    c = _series(b1d)[0]
    i = len(c) - 2 if _bougie_en_cours(b1d, "1d") else len(c) - 1
    r = _rendements(c, i, TSMOM_COURT) if i >= 0 else None
    if r is None:
        return False, "donnees insuffisantes"
    if r < 0:
        return True, f"rendement {TSMOM_COURT} j repasse negatif ({r * 100:+.1f} %)"
    return False, f"rendement {TSMOM_COURT} j {r * 100:+.1f} %"


# ------------------------------------------------------------------ interface pour paper_trading
def signaux(sym, prix, nom=None, marche="crypto"):
    """Liste de signaux (format paper_trading) pour ce symbole. Vide si rien ou TENDANCE=0."""
    if not actif() or marche != "crypto":
        return []
    out = []
    try:
        b1d = _bougies(sym, "1d", max(TSMOM_SMA + 10, 260))
        d = donchian(sym, b1d=b1d)
        if d.get("signal"):
            out.append({"symbole": sym, "prix_entree": prix, "nom": nom or sym, "marche": marche, "source": "tendance",
                        "strategie": "donchian_breakout", "score": 2, "raison": d["raison"], "niveau_sortie": d.get("sortie_10")})
        t = tsmom(sym, b1d=b1d)
        if t.get("signal"):
            out.append({"symbole": sym, "prix_entree": prix, "nom": nom or sym, "marche": marche, "source": "tendance",
                        "strategie": "tsmom", "score": 2, "raison": t["raison"]})
    except Exception as e:
        print(f"  [TENDANCE] {sym}: erreur {str(e)[:80]}")
    return out


def est_tendance(strategie):
    return str(strategie or "").lower() in TENDANCE


def est_reversion(strategie):
    s = str(strategie or "").lower()
    return any(x in s for x in REVERSION)


def sortie(pos):
    """(True, raison) si la sortie PROPRE de la strategie de tendance est atteinte."""
    s = str(pos.get("strategie") or "").lower()
    sym = pos.get("symbole")
    if s == "donchian_breakout":
        return sortie_donchian(sym)
    if s == "tsmom":
        return sortie_tsmom(sym)
    return False, "pas une strategie de tendance"


# ------------------------------------------------------------------ ADX 4 h (filtre des retours a la moyenne)
def adx_4h(sym):
    try:
        import regime
        b = _bougies(sym, "4h", 80)
        return regime.adx(b, 14) if b else None
    except Exception:
        return None


# ------------------------------------------------------------------ score de tendance (9 horizons)
def score_tendance(sym, b1d=None):
    """(n_haussiers, n_horizons, detail) : pour chaque horizon, cloture > milieu du canal Donchian (plus haut + plus bas)/2."""
    b1d = b1d or _bougies(sym, "1d", 400)
    c, h, l, v = _series(b1d)
    i = len(c) - 2 if _bougie_en_cours(b1d, "1d") else len(c) - 1
    if i < HORIZONS_SCORE[0] + 1 or c[i] is None:
        return None, 0, {}
    n_h, n_t, detail = 0, 0, {}
    for n in HORIZONS_SCORE:
        if i - n < 0:
            continue
        hh = [x for x in h[i - n:i] if x is not None]
        ll = [x for x in l[i - n:i] if x is not None]
        if not hh or not ll:
            continue
        milieu = (max(hh) + min(ll)) / 2.0
        haussier = c[i] > milieu
        n_t += 1
        n_h += 1 if haussier else 0
        detail[n] = haussier
    return n_h, n_t, detail


def bonus_preselection(sym):
    """+0,5 si au moins 5 des 9 canaux sont haussiers ; -0,5 si au plus 2 ; 0 sinon ou si inconnu. Un TRI, pas un filtre."""
    try:
        n_h, n_t, _ = score_tendance(sym)
        if n_h is None or n_t < 5:
            return 0.0, None
        if n_h >= max(5, int(round(n_t * 5 / 9.0))):
            return 0.5, f"tendance {n_h}/{n_t} canaux"
        if n_h <= 2:
            return -0.5, f"tendance {n_h}/{n_t} canaux"
        return 0.0, f"tendance {n_h}/{n_t} canaux"
    except Exception:
        return 0.0, None


def contexte_pour_cerveau(symboles):
    lignes = []
    for s in symboles[:12]:
        try:
            n_h, n_t, _ = score_tendance(s)
            if n_h is None:
                continue
            d = donchian(s)
            t = tsmom(s)
            lignes.append(f"- {s}: tendance {n_h}/{n_t} canaux haussiers ; Donchian {'CASSURE' if d.get('signal') else 'non'} ; TSMOM {'OUI' if t.get('signal') else 'non'} (r20 {t.get('r20_pct')}%, r90 {t.get('r90_pct')}%)")
        except Exception:
            continue
    if not lignes:
        return ""
    return "=== TENDANCE (9 canaux Donchian 5-360 j ; strategies donchian_breakout / tsmom) ===\n" + "\n".join(lignes) + "\n"


if __name__ == "__main__":
    syms = sys.argv[1:] or ["BTCUSDT", "ETHUSDT", "SOLUSDT"]
    print(f"TENDANCE actif={actif()} | Donchian {DONCHIAN_ENTREE}/{DONCHIAN_SORTIE} vol x{DONCHIAN_VOL} EMA {EMA_JOURS} j | TSMOM {TSMOM_COURT}/{TSMOM_LONG} j SMA {TSMOM_SMA} fraicheur {TSMOM_FRAICHEUR} j | TP {TP_RATIO}:1 barriere {BARRIERE_H} h | ADX range max {ADX_RANGE_MAX}")
    for s in syms:
        d = donchian(s)
        t = tsmom(s)
        n_h, n_t, _ = score_tendance(s)
        print(f"\n{s}: tendance {n_h}/{n_t} canaux | ADX 4h {adx_4h(s)}")
        print(f"  donchian_breakout: {'SIGNAL' if d['signal'] else 'non'} — {d['raison']}")
        print(f"  tsmom            : {'SIGNAL' if t['signal'] else 'non'} — {t['raison']}")
