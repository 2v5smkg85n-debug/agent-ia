#!/usr/bin/env python3
"""
memoire_episodique.py — retrouver les trades passes VRAIMENT similaires a la situation actuelle.

Avant : score entier (meme symbole +3, meme heure +1, meme signe BTC +1, RSI proche +1) -> on retombait
toujours sur les 3 derniers trades du symbole, le plus souvent des gagnants recents (biais de recence).
Maintenant : chaque trade devient un vecteur normalise d'indicateurs (RSI, ATR, variation BTC 1h/24h,
variation 24h du symbole, distance au plus haut 24h, heure en sinus/cosinus, regime) ; on calcule la
similarite cosinus, on garde les top-k au-dessus d'un seuil et on impose qu'au moins 2 des 5 trades
montres soient des PERTES (pour que l'IA voie aussi ce qui a mal tourne dans ce contexte).
Pure Python, sans numpy.
"""
import math
import os

DOSSIER = os.path.dirname(os.path.abspath(__file__))
SEUIL = float(os.getenv("MEMOIRE_SEUIL", "0.65"))
MIN_PERTES = int(os.getenv("MEMOIRE_MIN_PERTES", "2"))

# (cle, centre, echelle) -> (valeur - centre) / echelle
_DIMS = [("rsi", 50.0, 15.0), ("atr_pct", 0.6, 0.4), ("btc_var_1h", 0.0, 0.5), ("btc_var_24h", 0.0, 2.5),
         ("var_24h", 0.0, 3.0), ("dist_haut_24h", 1.5, 1.5), ("sl_recents_1h", 0.0, 1.0)]
_POIDS_SYM = 0.8        # bonus si meme symbole (dimension supplementaire)


def vecteur(ctx, sym=None):
    """Transforme un contexte d'entree en vecteur (liste de floats). Les None deviennent 0 (= moyenne)."""
    ctx = ctx or {}
    v = []
    for k, c, s in _DIMS:
        x = ctx.get(k)
        try:
            v.append(max(-3.0, min(3.0, (float(x) - c) / s)) if x is not None else 0.0)
        except Exception:
            v.append(0.0)
    h = ctx.get("heure")
    if h is None:
        v += [0.0, 0.0]
    else:
        a = 2 * math.pi * float(h) / 24.0
        v += [math.sin(a), math.cos(a)]
    reg = str(ctx.get("regime", "")).lower()
    v += [1.0 if reg == "tendance" else 0.0, 1.0 if reg == "range" else 0.0, 1.0 if reg == "turbulent" else 0.0]
    return v


def cosinus(a, b):
    num = sum(x * y for x, y in zip(a, b))
    na, nb = math.sqrt(sum(x * x for x in a)), math.sqrt(sum(y * y for y in b))
    return num / (na * nb) if na and nb else 0.0


def similaires(trades, sym, ctx, n=5, seuil=None, min_pertes=None):
    """trades: liste de dicts avec 'contexte', 'sym', 'gain'. Retourne les n plus proches (avec 'similarite')."""
    seuil = SEUIL if seuil is None else seuil
    min_pertes = MIN_PERTES if min_pertes is None else min_pertes
    vq = vecteur(ctx, sym)
    if not any(vq):
        return []
    scores = []
    for t in trades:
        c = t.get("contexte")
        if not c:
            continue
        s = cosinus(vq, vecteur(c, t.get("sym")))
        if t.get("sym") == sym:
            s = min(1.0, s + 0.1 * _POIDS_SYM)
        if s >= seuil:
            scores.append((s, t))
    scores.sort(key=lambda x: (x[0], str(x[1].get("date_fermeture", ""))), reverse=True)
    top = [t for _, t in scores[:n]]
    pertes_top = [t for t in top if (t.get("gain") or 0) < 0]
    if len(pertes_top) < min_pertes:
        pertes_dispo = [t for _, t in scores if (t.get("gain") or 0) < 0 and t not in top]
        for p in pertes_dispo[: min_pertes - len(pertes_top)]:
            # remplace le gagnant le moins similaire par une perte similaire
            gagnants = [t for t in top if (t.get("gain") or 0) >= 0]
            if gagnants:
                top.remove(gagnants[-1])
            top.append(p)
    sim_par_id = {id(t): s for s, t in scores}
    out = []
    for t in top:
        tt = dict(t)
        tt["similarite"] = round(sim_par_id.get(id(t), 0.0), 3)
        out.append(tt)
    out.sort(key=lambda t: t["similarite"], reverse=True)
    return out


def bilan_contexte(trades, sym, ctx, n=20):
    """Taux de reussite et P&L des n trades les plus proches : donne a l'IA une base de taux honnete."""
    sims = similaires(trades, sym, ctx, n=n, min_pertes=0)
    if not sims:
        return None
    g = [t for t in sims if (t.get("gain") or 0) >= 0]
    return {"n": len(sims), "wr": round(len(g) / len(sims) * 100), "pnl": round(sum(t.get("gain") or 0 for t in sims), 2),
            "similarite_moy": round(sum(t["similarite"] for t in sims) / len(sims), 3)}


if __name__ == "__main__":
    import json
    try:
        d = json.load(open(os.path.join(DOSSIER, "journal_erreurs.json")))
        trades = d.get("trades", [])
    except Exception:
        trades = []
    print(f"{len(trades)} trades avec contexte dans le journal")
    ctx = {"rsi": 42, "atr_pct": 0.5, "btc_var_1h": -0.2, "btc_var_24h": 1.0, "var_24h": -1.5, "dist_haut_24h": 2.0, "heure": 9}
    for t in similaires(trades, "ETHUSDT", ctx):
        print(f"  sim {t['similarite']:.2f} {t.get('sym')} {t.get('date_fermeture','')[:16]} {t.get('gain'):+.2f} EUR {t.get('raison','')[:20]}")
    print("bilan:", bilan_contexte(trades, "ETHUSDT", ctx))
