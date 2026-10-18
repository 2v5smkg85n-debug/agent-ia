#!/usr/bin/env python3
"""
etiquetage_triple_barriere.py — re-etiquette TOUS les trades passes (archive + courant) avec la methode de la
triple barriere (Lopez de Prado) et reconstruit les indicateurs au moment de l'entree a partir des bougies
1 minute Binance Vision. Rien n'est efface : le resultat va dans dataset_meta.jsonl (une ligne par trade).

Pour chaque trade :
  - entree  = date_ouverture (heure VPS, supposee UTC ; TZ_OFFSET_H pour corriger) + prix d'entree
  - stop    = 2 x ATR(14, 1h) borne [0.8, 3] %, objectif = 2 x stop, barriere = 24 h   (memes regles que stop_atr.py)
  - label_tb = 1 si l'objectif est touche avant le stop et avant 24 h (sur les plus hauts/plus bas 1 minute), sinon 0
  - label_reel = 1 si le trade a reellement gagne (ce que le bot a fait, avec ses sorties de l'epoque)
  - features = rsi, atr_pct, btc_var_1h, btc_var_24h, var_24h, dist_haut_24h, heure, jour, adx, regime, strategie...

Usage : python3 donnees_1m.py --tous --mois 4      (une fois, ~45 symboles x 5 mois = ~400 Mo)
        python3 etiquetage_triple_barriere.py       -> dataset_meta.jsonl + resume
"""
import json
import math
import os
import sys
from datetime import datetime, timedelta, timezone

DOSSIER = os.path.dirname(os.path.abspath(__file__))
SORTIE = os.path.join(DOSSIER, "dataset_meta.jsonl")
TZ_OFFSET_H = float(os.getenv("TZ_OFFSET_H", "0"))     # heures a AJOUTER aux dates du bot pour obtenir l'UTC
SL_MULT, SL_MIN, SL_MAX, TP_RATIO, BARRIERE_H = 2.0, 0.8, 3.0, 2.0, 24


def _rsi(cl, n=14):
    if len(cl) < n + 1:
        return None
    gains = [max(0, cl[i] - cl[i - 1]) for i in range(1, len(cl))]
    pertes = [max(0, cl[i - 1] - cl[i]) for i in range(1, len(cl))]
    ag, ap = sum(gains[:n]) / n, sum(pertes[:n]) / n
    for g, p in zip(gains[n:], pertes[n:]):
        ag, ap = (ag * (n - 1) + g) / n, (ap * (n - 1) + p) / n
    return 100.0 if ap == 0 else round(100 - 100 / (1 + ag / ap), 1)


def _atr_pct(b, n=14):
    if len(b) < n + 1:
        return None
    trs = [max(b[i]["haut"] - b[i]["bas"], abs(b[i]["haut"] - b[i - 1]["cloture"]), abs(b[i]["bas"] - b[i - 1]["cloture"])) for i in range(-n, 0)]
    return round(sum(trs) / n / b[-1]["cloture"] * 100, 3) if b[-1]["cloture"] else None


def _adx(b, n=14):
    try:
        import regime
        return regime.adx(b, n)
    except Exception:
        return None


def _features(sym, t_entree_ms, prix, b1h_sym, b1h_btc):
    """Indicateurs calcules UNIQUEMENT avec les bougies 1h cloturees avant l'entree."""
    avant = [x for x in b1h_sym if (x["temps"] + 3600) * 1000 <= t_entree_ms][-130:]
    avant_btc = [x for x in b1h_btc if (x["temps"] + 3600) * 1000 <= t_entree_ms][-30:]
    if len(avant) < 30:
        return None
    cl = [x["cloture"] for x in avant]
    f = {"rsi": _rsi(cl), "atr_pct": _atr_pct(avant), "var_24h": round((cl[-1] - cl[-25]) / cl[-25] * 100, 2) if len(cl) > 25 else None,
         "dist_haut_24h": round((max(x["haut"] for x in avant[-24:]) - cl[-1]) / max(x["haut"] for x in avant[-24:]) * 100, 3),
         "adx": _adx(avant), "btc_var_1h": None, "btc_var_24h": None}
    if len(avant_btc) >= 26:
        cb = [x["cloture"] for x in avant_btc]
        f["btc_var_1h"] = round((cb[-1] - cb[-2]) / cb[-2] * 100, 3)
        f["btc_var_24h"] = round((cb[-1] - cb[-25]) / cb[-25] * 100, 2)
    atrs = [_atr_pct(avant[:i]) for i in range(30, len(avant) + 1)]
    atrs = [a for a in atrs if a]
    pct = round(sum(1 for a in atrs if a <= atrs[-1]) / len(atrs) * 100) if atrs else None
    f["atr_percentile"] = pct
    f["regime"] = "turbulent" if pct is not None and pct >= 90 else ("tendance" if (f["adx"] or 0) >= 25 else ("range" if f["adx"] is not None else "inconnu"))
    return f


def _label(b1m, t_entree_ms, prix_entree, sl_pct, tp_pct, barriere_h=BARRIERE_H):
    """Parcourt les bougies 1m apres l'entree ; retourne (label, barriere_touchee, heures, rendement_sortie_pct)."""
    fin = t_entree_ms + barriere_h * 3600 * 1000
    sl_px, tp_px = prix_entree * (1 - sl_pct / 100), prix_entree * (1 + tp_pct / 100)
    dernier = None
    for ts, o, h, l, c, *_ in b1m:
        if ts < t_entree_ms:
            continue
        if ts > fin:
            break
        dernier = (ts, c)
        touche_sl, touche_tp = l <= sl_px, h >= tp_px
        if touche_sl and touche_tp:        # les deux dans la meme minute : pessimiste
            return 0, "stop", round((ts - t_entree_ms) / 3.6e6, 2), -sl_pct
        if touche_sl:
            return 0, "stop", round((ts - t_entree_ms) / 3.6e6, 2), -sl_pct
        if touche_tp:
            return 1, "objectif", round((ts - t_entree_ms) / 3.6e6, 2), tp_pct
    if dernier:
        r = (dernier[1] - prix_entree) / prix_entree * 100
        return (1 if r > 0.2 else 0), "temps", round((dernier[0] - t_entree_ms) / 3.6e6, 2), round(r, 3)
    return None, "pas de donnees", None, None


def _ts_ms(date_str):
    try:
        d = datetime.strptime(str(date_str)[:16], "%Y-%m-%d %H:%M").replace(tzinfo=timezone.utc) + timedelta(hours=TZ_OFFSET_H)
        return int(d.timestamp() * 1000)
    except Exception:
        return None


def tous_les_trades():
    try:
        import registre_strategies as rs
        return rs.tous_les_trades()
    except Exception:
        try:
            return json.load(open(os.path.join(DOSSIER, "paper_trading.json"))).get("trades_fermes", [])
        except Exception:
            return []


def construire(verbose=True):
    import donnees_1m as d1
    trades = [t for t in tous_les_trades() if t.get("marche", "crypto") in ("crypto", "?") and str(t.get("symbole", "")).endswith("USDT")]
    syms = sorted(set(t["symbole"] for t in trades))
    if verbose:
        print(f"{len(trades)} trades crypto, {len(syms)} symboles")
    btc_1m = d1.charger("BTCUSDT")
    b1h_btc = d1.resample(btc_1m, 60) if btc_1m else []
    n_ok, n_sans = 0, 0
    with open(SORTIE + ".tmp", "w") as f:
        for sym in syms:
            b1m = d1.charger(sym)
            if not b1m:
                n_sans += sum(1 for t in trades if t["symbole"] == sym)
                if verbose:
                    print(f"  {sym}: pas de donnees 1m (python3 donnees_1m.py {sym} --mois 4)")
                continue
            b1h = d1.resample(b1m, 60)
            for t in (x for x in trades if x["symbole"] == sym):
                t0 = _ts_ms(t.get("date_ouverture"))
                prix = float(t.get("prix_entree") or 0)
                if not t0 or not prix:
                    n_sans += 1
                    continue
                feats = _features(sym, t0, prix, b1h, b1h_btc)
                if not feats:
                    n_sans += 1
                    continue
                # prix du bot en EUR vs bougies USDT : on travaille en % autour du premier cours 1m apres l'entree
                prem = next((c for ts, o, h, l, c, *_ in b1m if ts >= t0), None)
                if not prem:
                    n_sans += 1
                    continue
                sl = round(min(SL_MAX, max(SL_MIN, SL_MULT * (feats["atr_pct"] or 0))), 2) if feats["atr_pct"] else SL_MIN
                tp = round(sl * TP_RATIO, 2)
                lab, barr, heures, rend = _label(b1m, t0, prem, sl, tp)
                if lab is None:
                    n_sans += 1
                    continue
                d_utc = datetime.fromtimestamp(t0 / 1000, timezone.utc)
                rec = {"sym": sym, "date": d_utc.strftime("%Y-%m-%d %H:%M"), "heure": d_utc.hour, "jour": d_utc.weekday(),
                       "strategie": str(t.get("strategie") or t.get("source") or "inconnu"), "sl_pct": sl, "tp_pct": tp,
                       "label_tb": lab, "barriere": barr, "heures": heures, "rend_tb_pct": rend,
                       "label_reel": 1 if float(t.get("gain_eur", 0) or 0) > 0 else 0, "gain_reel": round(float(t.get("gain_eur", 0) or 0), 3),
                       "raison_reelle": str(t.get("raison", ""))[:30], **feats}
                f.write(json.dumps(rec, ensure_ascii=False) + "\n")
                n_ok += 1
    os.replace(SORTIE + ".tmp", SORTIE)
    if verbose:
        print(f"-> {SORTIE}: {n_ok} trades etiquetes, {n_sans} sans donnees")
    return n_ok


def resume():
    try:
        recs = [json.loads(l) for l in open(SORTIE) if l.strip()]
    except Exception:
        return "dataset_meta.jsonl absent"
    if not recs:
        return "dataset vide"
    n = len(recs)
    tb = sum(r["label_tb"] for r in recs)
    reel = sum(r["label_reel"] for r in recs)
    lignes = [f"{n} trades | reussite reelle {reel / n * 100:.0f}% | reussite si triple barriere 2xATR / 2:1 / 24h : {tb / n * 100:.0f}% "
              f"(rendement moyen {sum(r['rend_tb_pct'] for r in recs) / n:+.2f}% par trade avant frais)"]
    for cle in ("regime", "barriere"):
        groupes = {}
        for r in recs:
            g = groupes.setdefault(r.get(cle), [0, 0, 0.0])
            g[0] += 1; g[1] += r["label_tb"]; g[2] += r["rend_tb_pct"]
        lignes.append(f"  par {cle}: " + " | ".join(f"{k}: {v[0]} trades, {v[1] / v[0] * 100:.0f}% ok, {v[2] / v[0]:+.2f}%" for k, v in sorted(groupes.items(), key=lambda x: -x[1][0])))
    heures = {}
    for r in recs:
        g = heures.setdefault(r["heure"], [0, 0.0]); g[0] += 1; g[1] += r["rend_tb_pct"]
    pires = sorted(heures.items(), key=lambda x: x[1][1] / x[1][0])[:4]
    lignes.append("  pires heures UTC (rendement TB moyen): " + ", ".join(f"{h}h ({v[1] / v[0]:+.2f}% sur {v[0]})" for h, v in pires))
    return "\n".join(lignes)


if __name__ == "__main__":
    if "--resume" not in sys.argv:
        construire()
    print(resume())
