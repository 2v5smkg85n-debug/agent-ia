#!/usr/bin/env python3
"""
Professeurs externes : trois strategies open source parmi les mieux classees sur 2022-2025 (classement Freqle, 6 146
strategies backtestees), portees en Python pur et branchees sur le cerveau EN MODE PROFESSEUR.

    - NASOS  : NotAnotherSMAOffsetStrategy (Rallipanos) — achat sous une EMA decalee quand l'Elliott Wave Oscillator
               (EMA50-EMA200) confirme la tendance de fond ou signale une capitulation (5 min).
    - E0V1E  : (TheoBrigitte / ssssi) — RSI lent qui baisse, RSI rapide bas, prix sous SMA15 x 0,973, CTI < 0,69,
               variation 24h entre -15 % et +50 % (5 min).
    - NFI    : NostalgiaForInfinity (iterativv) — coeur des conditions "normal mode" #1 et #2 : capitulation sous la
               Bollinger basse avec ecart EMA26/EMA12 fort, ou Aroon/StochRSI ecrases sous EMA20 x 0,944, plus la
               protection "pas en pleine chute" (RSI 3 periodes > 3 sur 5 min et 15 min).

REGLES DE LA MAISON :
    * Elles n'ouvrent RIEN. Elles votent. Leurs votes sont ecrits dans le dossier de l'analyste (cerveau.decider via
      chat_naturel) et journalises ici.
    * Chaque vote est juge par la MEME barriere que le bot : stop = 2 x ATR 1h (0,8-3 %), objectif = 2 x stop, 24 h.
      Le cerveau voit leur fiabilite mesuree chez nous, pas leur reputation.
    * Influence gagnee, pas accordee : un professeur ajoute +0,5 a la preselection d'une crypto seulement s'il a
      >= 20 votes evalues et >= 45 % d'objectifs (point mort 2:1 ~40 % frais compris). Sinon il est seulement lu.
    * Tout est desactivable : PROFESSEURS_EXTERNES=0 dans .env.

Sources : https://github.com/devilsinthedetail/shafqatsuri/blob/main/NotAnotherSMAOffsetStrategy.py ;
          https://github.com/ssssi/freqtrade_strs/blob/main/binance/dry_run/E0V1EN.py ;
          https://github.com/iterativv/NostalgiaForInfinity/blob/main/NostalgiaForInfinityX6.py ;
          classement : https://freqle.org/ranking

CLI :  python3 professeurs_externes.py            -> rapport
       python3 professeurs_externes.py test SOLUSDT -> indicateurs et votes pour une crypto
       python3 professeurs_externes.py evaluer    -> juge les votes en attente
"""
import json
import math
import os
import sys
import time
from datetime import datetime, timezone

DOSSIER = os.path.dirname(os.path.abspath(__file__))
FICHIER = os.path.join(DOSSIER, "professeurs_externes.json")
PROFESSEURS = ("NASOS", "E0V1E", "NFI")
N_FIABLE, WR_FIABLE = 20, 45.0          # influence sur la preselection seulement a partir de la
REFROIDISSEMENT_VOTE_S = 2 * 3600        # un vote par professeur et par crypto toutes les 2 h
BARRIERE_H = 24
_CACHE = {}                              # sym -> (ts, resultat) ; recalcul au plus toutes les 5 min


def _actif():
    try:
        from config_env import lire
        return str(lire("PROFESSEURS_EXTERNES", "1")).strip().lower() not in ("0", "false", "non", "off")
    except Exception:
        return os.environ.get("PROFESSEURS_EXTERNES", "1") not in ("0", "false", "non", "off")


# ------------------------------------------------------------------ indicateurs (python pur)
def _ema(v, n):
    out = [None] * len(v)
    if len(v) < n:
        return out
    k = 2.0 / (n + 1)
    e = sum(v[:n]) / n
    out[n - 1] = e
    for i in range(n, len(v)):
        e = v[i] * k + e * (1 - k)
        out[i] = e
    return out


def _sma(v, n):
    out = [None] * len(v)
    s = 0.0
    for i, x in enumerate(v):
        s += x
        if i >= n:
            s -= v[i - n]
        if i >= n - 1:
            out[i] = s / n
    return out


def _rsi(v, n):
    out = [None] * len(v)
    if len(v) <= n:
        return out
    g = l = 0.0
    for i in range(1, n + 1):
        d = v[i] - v[i - 1]
        if d > 0: g += d
        else: l -= d
    g /= n; l /= n
    out[n] = 100.0 if l == 0 else 100 - 100 / (1 + g / l)
    for i in range(n + 1, len(v)):
        d = v[i] - v[i - 1]
        g = (g * (n - 1) + max(d, 0)) / n
        l = (l * (n - 1) + max(-d, 0)) / n
        out[i] = 100.0 if l == 0 else 100 - 100 / (1 + g / l)
    return out


def _stdev_pop(v, n):
    out = [None] * len(v)
    for i in range(n - 1, len(v)):
        w = v[i - n + 1:i + 1]
        m = sum(w) / n
        out[i] = math.sqrt(sum((x - m) ** 2 for x in w) / n)
    return out


def _stochrsi_k(closes, rsi_len=14, stoch_len=14, k=3):
    r = _rsi(closes, rsi_len)
    st = [None] * len(closes)
    for i in range(len(closes)):
        if i < rsi_len + stoch_len - 1:
            continue
        w = [x for x in r[i - stoch_len + 1:i + 1] if x is not None]
        if len(w) < stoch_len:
            continue
        lo, hi = min(w), max(w)
        st[i] = 0.0 if hi == lo else (r[i] - lo) / (hi - lo) * 100
    out = [None] * len(closes)
    for i in range(len(closes)):
        w = st[i - k + 1:i + 1] if i >= k - 1 else []
        if w and all(x is not None for x in w):
            out[i] = sum(w) / k
    return out


def _aroon_up(highs, n=14):
    """pandas_ta : fenetre n+1, up = (n - periodes depuis le plus haut) / n * 100."""
    out = [None] * len(highs)
    for i in range(n, len(highs)):
        w = highs[i - n:i + 1]
        idx = max(range(len(w)), key=lambda j: w[j])
        out[i] = (n - (len(w) - 1 - idx)) / n * 100.0
    return out


def _cti(closes, n=20):
    """Correlation Trend Indicator (Ehlers) : correlation de Pearson entre le prix et le temps sur n barres."""
    out = [None] * len(closes)
    xs = list(range(n))
    mx = sum(xs) / n
    vx = sum((x - mx) ** 2 for x in xs)
    for i in range(n - 1, len(closes)):
        w = closes[i - n + 1:i + 1]
        my = sum(w) / n
        vy = sum((y - my) ** 2 for y in w)
        if vy == 0:
            out[i] = 0.0
            continue
        cov = sum((xs[j] - mx) * (w[j] - my) for j in range(n))
        out[i] = cov / math.sqrt(vx * vy)
    return out


def _atr_pct(bougies, n=14):
    if len(bougies) < n + 1:
        return None
    trs = []
    for i in range(1, len(bougies)):
        h, l, pc = bougies[i]["haut"], bougies[i]["bas"], bougies[i - 1]["cloture"]
        trs.append(max(h - l, abs(h - pc), abs(l - pc)))
    atr = sum(trs[-n:]) / n
    c = bougies[-1]["cloture"]
    return round(atr / c * 100, 3) if c else None


def _dernier(serie, i):
    return serie[i] if i < len(serie) else None


# ------------------------------------------------------------------ les trois professeurs
def _votes_5m(b5, b15=None):
    """b5 : bougies 5 min (anciennes -> recentes). Retourne (votes, indicateurs, protection_nfi_ok, motif_protection)."""
    c = [x["cloture"] for x in b5]
    h = [x["haut"] for x in b5]
    lo = [x["bas"] for x in b5]
    o = [x["ouverture"] for x in b5]
    vol = [x.get("volume", 0.0) for x in b5]
    i = len(c) - 2 if len(c) >= 2 else len(c) - 1       # derniere bougie CLOTUREE (comme Freqtrade)
    if i < 300:
        return [], {}, True, "donnees insuffisantes"
    ema14, ema24, ema50, ema200 = _ema(c, 14), _ema(c, 24), _ema(c, 50), _ema(c, 200)
    ema12, ema26, ema20 = _ema(c, 12), _ema(c, 26), _ema(c, 20)
    sma15, sma20 = _sma(c, 15), _sma(c, 20)
    rsi14, rsi4, rsi20, rsi3 = _rsi(c, 14), _rsi(c, 4), _rsi(c, 20), _rsi(c, 3)
    sd20 = _stdev_pop(c, 20)
    cti20 = _cti(c, 20)
    aroon = _aroon_up(h, 14)
    srsi = _stochrsi_k(c)
    ewo = (ema50[i] - ema200[i]) / lo[i] * 100 if ema50[i] and ema200[i] and lo[i] else None
    var24 = (c[i] / c[i - 288] - 1) * 100 if i >= 288 and c[i - 288] else None
    bbl = sma20[i] - 2 * sd20[i] if sma20[i] is not None and sd20[i] is not None else None
    ind = {"close": c[i], "ema14": ema14[i], "ema24": ema24[i], "ewo": ewo, "rsi14": rsi14[i], "rsi4": rsi4[i],
           "rsi20": rsi20[i], "rsi20_prev": rsi20[i - 1], "sma15": sma15[i], "cti20": cti20[i], "var24h": var24,
           "ema12": ema12[i], "ema26": ema26[i], "bb_bas": bbl, "aroon_up": aroon[i], "stochrsi_k": srsi[i],
           "ema20": ema20[i], "rsi3": rsi3[i]}
    votes = []
    # --- NASOS (achat spot, 5 min) ---
    if None not in (ema14[i], ema24[i], ewo, rsi14[i], rsi4[i]) and vol[i] > 0:
        base = rsi4[i] < 35 and c[i] < ema24[i] * 0.991
        if base and c[i] < ema14[i] * 0.975 and ewo > 2.327 and rsi14[i] < 69:
            votes.append(("NASOS", "ewo1", f"RSI4 {rsi4[i]:.0f}, prix {(c[i]/ema14[i]-1)*100:+.1f}% sous EMA14, EWO {ewo:+.1f} (tendance de fond haussiere)"))
        elif base and c[i] < ema14[i] * 0.955 and ewo > -2.327 and rsi14[i] < 25:
            votes.append(("NASOS", "ewo2", f"RSI14 {rsi14[i]:.0f} ecrase, prix {(c[i]/ema14[i]-1)*100:+.1f}% sous EMA14, EWO {ewo:+.1f}"))
        elif base and c[i] < ema14[i] * 0.975 and ewo < -20.988:
            votes.append(("NASOS", "ewolow", f"capitulation : EWO {ewo:+.1f}, RSI4 {rsi4[i]:.0f}"))
    # --- E0V1E (5 min) ---
    if None not in (rsi20[i], rsi20[i - 1], rsi4[i], rsi14[i], sma15[i], cti20[i], var24):
        commun = rsi20[i] < rsi20[i - 1] and cti20[i] < 0.69 and -15.0 < var24 < 50.0
        if commun and rsi4[i] < 40 and rsi14[i] > 42 and c[i] < sma15[i] * 0.973:
            votes.append(("E0V1E", "buy_1", f"RSI20 en baisse, RSI4 {rsi4[i]:.0f}, RSI14 {rsi14[i]:.0f}, prix {(c[i]/sma15[i]-1)*100:+.1f}% sous SMA15, CTI {cti20[i]:+.2f}, 24h {var24:+.1f}%"))
        elif commun and rsi4[i] < 34 and rsi14[i] > 28 and c[i] < sma15[i] * 0.96:
            votes.append(("E0V1E", "buy_new", f"RSI20 en baisse, RSI4 {rsi4[i]:.0f}, prix {(c[i]/sma15[i]-1)*100:+.1f}% sous SMA15, CTI {cti20[i]:+.2f}"))
    # --- NFI : protection globale "pas en pleine chute" (RSI 3 periodes 5m et 15m > 3), puis coeur des conditions #1 / #2 ---
    prot_ok, motif = True, ""
    if rsi3[i] is not None and rsi3[i] <= 3.0:
        prot_ok, motif = False, f"RSI3 5m = {rsi3[i]:.1f} (chute verticale en cours)"
    if prot_ok and b15 and len(b15) > 10:
        r3_15 = _rsi([x["cloture"] for x in b15], 3)
        j = len(r3_15) - 2
        if r3_15[j] is not None and r3_15[j] <= 3.0:
            prot_ok, motif = False, f"RSI3 15m = {r3_15[j]:.1f} (chute en cours)"
    if prot_ok and None not in (ema12[i], ema26[i], ema12[i - 1], ema26[i - 1], bbl):
        if (ema26[i] > ema12[i] and (ema26[i] - ema12[i]) > o[i] * 0.034 and (ema26[i - 1] - ema12[i - 1]) > o[i] / 100.0
                and c[i] < bbl * 0.999):
            votes.append(("NFI", "#1", f"prix sous la Bollinger basse, ecart EMA26/EMA12 {(ema26[i]-ema12[i])/o[i]*100:.1f}% (capitulation)"))
    if prot_ok and None not in (aroon[i], srsi[i], ema20[i]):
        a15_ok = True
        if b15 and len(b15) > 20:
            a15 = _aroon_up([x["haut"] for x in b15], 14)
            a15_ok = a15[len(a15) - 2] is not None and a15[len(a15) - 2] < 25.0
        if aroon[i] < 25.0 and srsi[i] < 20.0 and a15_ok and c[i] < ema20[i] * 0.944:
            votes.append(("NFI", "#2", f"Aroon up {aroon[i]:.0f}, StochRSI {srsi[i]:.0f}, prix {(c[i]/ema20[i]-1)*100:+.1f}% sous EMA20"))
    return votes, ind, prot_ok, motif


def evaluer_symbole(sym, force=False):
    """-> {"votes": [(prof, tag, detail)], "protection_nfi": bool, "motif": str, "indicateurs": {...}} (cache 5 min)."""
    now = time.time()
    if not force and sym in _CACHE and now - _CACHE[sym][0] < 300:
        return _CACHE[sym][1]
    res = {"votes": [], "protection_nfi": True, "motif": "", "indicateurs": {}}
    try:
        import indicateurs as ind
        b5 = ind.historique_ohlcv(sym, "5m", 420) or []
        b15 = []
        try:
            b15 = ind.historique_ohlcv(sym, "15m", 60) or []
        except Exception:
            pass
        votes, indic, prot, motif = _votes_5m(b5, b15)
        res = {"votes": votes, "protection_nfi": prot, "motif": motif, "indicateurs": indic}
    except Exception as e:
        res["motif"] = f"indisponible: {e}"
    _CACHE[sym] = (now, res)
    return res


# ------------------------------------------------------------------ journal des votes et evaluation
def _charger():
    try:
        with open(FICHIER, encoding="utf-8") as f:
            d = json.load(f)
    except Exception:
        d = {}
    d.setdefault("votes", [])
    d.setdefault("stats", {p: {"n": 0, "tp": 0, "sl": 0, "neutre": 0, "rendement_cumule": 0.0} for p in PROFESSEURS})
    for p in PROFESSEURS:
        d["stats"].setdefault(p, {"n": 0, "tp": 0, "sl": 0, "neutre": 0, "rendement_cumule": 0.0})
    return d


def _sauver(d):
    d["votes"] = d["votes"][-2000:]
    tmp = FICHIER + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(d, f, ensure_ascii=False, indent=1)
    os.replace(tmp, FICHIER)


def _barriere(sym, prix):
    """stop = 2 x ATR 1h borne 0,8-3 %, objectif = 2 x stop (le cadre du bot)."""
    sl = 1.5
    try:
        import indicateurs as ind
        b1 = ind.historique_ohlcv(sym, "1h", 40) or []
        a = _atr_pct(b1, 14)
        if a:
            sl = min(3.0, max(0.8, 2 * a))
    except Exception:
        pass
    return round(sl, 2), round(2 * sl, 2)


def journaliser_votes(symboles, prix_data=None):
    """Calcule les votes des professeurs pour chaque crypto, les journalise (refroidissement 2 h), retourne {sym: res}."""
    if not _actif():
        return {}
    d = _charger()
    now = time.time()
    out = {}
    for sym in symboles:
        res = evaluer_symbole(sym)
        out[sym] = res
        for prof, tag, detail in res["votes"]:
            recent = any(v["sym"] == sym and v["prof"] == prof and now - v["ts"] < REFROIDISSEMENT_VOTE_S for v in d["votes"][-300:])
            if recent:
                continue
            prix = (prix_data or {}).get(sym) or res["indicateurs"].get("close")
            if not prix:
                continue
            sl, tp = _barriere(sym, prix)
            d["votes"].append({"ts": now, "date": datetime.now().strftime("%Y-%m-%d %H:%M"), "sym": sym, "prof": prof,
                               "tag": tag, "detail": detail, "prix": float(prix), "sl_pct": sl, "tp_pct": tp,
                               "resultat": None, "rendement": None, "heure_utc": datetime.now(timezone.utc).hour})
    _sauver(d)
    return out


def evaluer_votes():
    """Juge les votes en attente sur les bougies 1h : stop touche -> sl, objectif touche -> tp (les deux dans la meme
    bougie -> sl, prudence), 24 h sans rien -> neutre avec le rendement."""
    d = _charger()
    now = time.time()
    attente = [v for v in d["votes"] if v.get("resultat") is None and now - v["ts"] >= 3600]
    if not attente:
        return 0
    try:
        import indicateurs as ind
    except Exception:
        return 0
    n_eval = 0
    cache = {}
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
        p0 = v["prix"]
        stop, obj = p0 * (1 - v["sl_pct"] / 100), p0 * (1 + v["tp_pct"] / 100)
        res, rend = None, None
        for b in b1:
            if b["bas"] <= stop:
                res, rend = "sl", -v["sl_pct"]; break
            if b["haut"] >= obj:
                res, rend = "tp", v["tp_pct"]; break
        if res is None and now - v["ts"] >= BARRIERE_H * 3600:
            res, rend = "neutre", round((b1[-1]["cloture"] / p0 - 1) * 100, 2)
        if res is None:
            continue
        v["resultat"], v["rendement"], v["evalue_le"] = res, rend, datetime.now().strftime("%Y-%m-%d %H:%M")
        st = d["stats"][v["prof"]]
        st["n"] += 1; st[res] += 1; st["rendement_cumule"] = round(st["rendement_cumule"] + rend, 2)
        n_eval += 1
    _sauver(d)
    return n_eval


def fiabilite(prof, d=None):
    """-> (n_tranche, pct_objectifs, fiable) sur les votes tranches (tp/sl)."""
    d = d or _charger()
    st = d["stats"].get(prof, {})
    n = st.get("tp", 0) + st.get("sl", 0)
    pct = st["tp"] / n * 100 if n else None
    return n, pct, bool(n >= N_FIABLE and pct is not None and pct >= WR_FIABLE)


def bonus_preselection(sym):
    """+0,5 par professeur FIABLE qui vote pour sym (max +1). Influence gagnee par les faits, jamais accordee d'office."""
    if not _actif():
        return 0.0, []
    res = _CACHE.get(sym, (0, None))[1]
    if not res or not res["votes"]:
        return 0.0, []
    d = _charger()
    bonus, who = 0.0, []
    for prof, tag, _ in res["votes"]:
        _, _, ok = fiabilite(prof, d)
        if ok:
            bonus += 0.5; who.append(f"{prof}({tag})")
    return min(1.0, bonus), who


def contexte_pour_cerveau(symboles, prix_data=None):
    """Texte insere dans le dossier de l'analyste : votes du moment + fiabilite mesuree chez nous."""
    if not _actif():
        return ""
    try:
        evaluer_votes()
    except Exception:
        pass
    res = journaliser_votes(symboles, prix_data)
    d = _charger()
    fiab = []
    for p in PROFESSEURS:
        st = d["stats"][p]
        n, pct, ok = fiabilite(p, d)
        if st["n"] == 0:
            fiab.append(f"{p}: aucun vote evalue encore")
        else:
            fiab.append(f"{p}: {st['n']} votes evalues -> {st['tp']} objectifs / {st['sl']} stops / {st['neutre']} neutres"
                        + (f" ({pct:.0f}% sur les tranches{', FIABLE' if ok else ''})" if pct is not None else ""))
    lignes = []
    for sym, r in res.items():
        if r["votes"]:
            lignes.append(f"  {sym}: " + " ; ".join(f"{p} ({tag}: {det})" for p, tag, det in r["votes"]))
    chutes = [f"{sym} ({r['motif']})" for sym, r in res.items() if not r["protection_nfi"]]
    txt = ("\nPROFESSEURS EXTERNES (NASOS, E0V1E, NFI : 3 strategies open source parmi les mieux classees 2022-2025 ; elles n'ouvrent rien, elles votent ; "
           "leur fiabilite ci-dessous est MESUREE sur nos cryptos avec notre barriere stop 2xATR / objectif 2:1 / 24h) :\n"
           "  Fiabilite : " + " | ".join(fiab) + "\n")
    txt += ("  Votes ACHAT maintenant :\n" + "\n".join(lignes) + "\n") if lignes else "  Aucun vote d'achat en ce moment.\n"
    if chutes:
        txt += "  Protection NFI 'pas en pleine chute' (NFI n'acheterait pas) : " + ", ".join(chutes) + "\n"
    txt += "  Un vote est un argument de plus dans ta checklist, pas un ordre : un professeur non fiable chez nous se lit avec prudence.\n"
    return txt


# ------------------------------------------------------------------ rapport
def rapport():
    d = _charger()
    L = [f"PROFESSEURS EXTERNES — {'actifs' if _actif() else 'DESACTIVES (PROFESSEURS_EXTERNES=0)'} — mode professeur : aucun droit d'ouvrir",
         f"Barriere de jugement : stop 2xATR 1h (0,8-3 %), objectif 2:1, {BARRIERE_H} h. Influence sur la preselection a partir de {N_FIABLE} votes tranches et {WR_FIABLE:.0f} % d'objectifs."]
    for p in PROFESSEURS:
        st = d["stats"][p]
        n, pct, ok = fiabilite(p, d)
        attente = sum(1 for v in d["votes"] if v["prof"] == p and v.get("resultat") is None)
        L.append(f"  {p:6s} {st['n']:3d} evalues | {st['tp']} objectifs / {st['sl']} stops / {st['neutre']} neutres"
                 + (f" | {pct:.0f}% sur les tranches" if pct is not None else "")
                 + f" | rendement cumule {st['rendement_cumule']:+.1f}% | {attente} en attente | {'FIABLE' if ok else 'en observation'}")
    recents = d["votes"][-12:]
    if recents:
        L.append("Derniers votes :")
        for v in reversed(recents):
            r = v.get("resultat")
            if r:
                issue = "-> " + r + ("" if v.get("rendement") is None else " %+.1f%%" % v["rendement"])
            else:
                issue = "(en attente)"
            L.append("  %s %-9s %-6s %-7s %s | %s" % (v["date"], v["sym"], v["prof"], v["tag"], issue, v["detail"][:70]))
    return "\n".join(L)


if __name__ == "__main__":
    if len(sys.argv) > 1 and sys.argv[1] == "test":
        sym = sys.argv[2] if len(sys.argv) > 2 else "BTCUSDT"
        r = evaluer_symbole(sym, force=True)
        print(json.dumps({k: (round(v, 4) if isinstance(v, float) else v) for k, v in r["indicateurs"].items()}, indent=1))
        print("votes:", r["votes"] or "aucun", "| protection NFI:", r["protection_nfi"], r["motif"])
    elif len(sys.argv) > 1 and sys.argv[1] == "evaluer":
        print(f"{evaluer_votes()} vote(s) juge(s)")
        print(rapport())
    else:
        print(rapport())
