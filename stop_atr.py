#!/usr/bin/env python3
"""
stop_atr.py — stop, objectif, barriere de temps et taille de position, selon la volatilite.

Regles (sources dans plan-amelioration du 18/10/2026) :
  - stop = ATR_MULT x ATR(14, 1h) en %, borne [SL_MIN, SL_MAX]. Un stop sous 1 ATR est touche par une bougie
    ordinaire ; 2 x ATR est le meilleur multiplicateur sur 9 433 trades (Quant Signals 2026).
  - pendant la session US (13h-17h UTC) le multiplicateur monte a ATR_MULT_US (les sauts y sont concentres).
  - objectif = RATIO x stop (2:1 par defaut), barriere de temps = BARRIERE_H heures (triple barriere).
  - taille = risque_eur / (stop% + frais aller-retour%) : meme perte maximale quel que soit l'actif.
  - regime turbulent : risque divise par 2 ; regime range : objectif reduit a 1.5 x stop (retour a la moyenne).

Tout est surchargeable par variables d'environnement (ATR_MULT, ATR_MULT_US, SL_MIN, SL_MAX, TP_RATIO, BARRIERE_H,
RISQUE_EUR, FRAIS_AR_PCT) sans toucher au code.
"""
import os
from datetime import datetime, timezone

ATR_MULT = float(os.getenv("ATR_MULT", "2.0"))
ATR_MULT_US = float(os.getenv("ATR_MULT_US", "2.5"))
SL_MIN = float(os.getenv("SL_MIN", "0.8"))
SL_MAX = float(os.getenv("SL_MAX", "3.0"))
TP_RATIO = float(os.getenv("TP_RATIO", "2.0"))
TP_RATIO_RANGE = float(os.getenv("TP_RATIO_RANGE", "1.5"))
BARRIERE_H = int(os.getenv("BARRIERE_H", "24"))
RISQUE_EUR = float(os.getenv("RISQUE_EUR", "1.0"))
FRAIS_AR_PCT = float(os.getenv("FRAIS_AR_PCT", "0.2"))     # 0.1 % par cote dans le paper
SESSION_US = (13, 17)                                       # heures UTC incluses/exclues : 13 <= h < 17


def atr_pct(bougies, periode=14):
    """ATR en % du dernier cours. bougies: liste de dicts {haut, bas, cloture}."""
    if not bougies or len(bougies) < periode + 1:
        return None
    trs = []
    for i in range(-periode, 0):
        b, prev = bougies[i], bougies[i - 1]
        tr = max(b["haut"] - b["bas"], abs(b["haut"] - prev["cloture"]), abs(b["bas"] - prev["cloture"]))
        trs.append(tr)
    c = bougies[-1]["cloture"]
    return round(sum(trs) / periode / c * 100, 3) if c else None


def en_session_us(maintenant=None):
    h = (maintenant or datetime.now(timezone.utc)).hour
    return SESSION_US[0] <= h < SESSION_US[1]


def stop_pct(atr, maintenant=None):
    """Stop en % a partir de l'ATR % (None -> SL_MIN)."""
    if not atr or atr <= 0:
        return SL_MIN
    mult = ATR_MULT_US if en_session_us(maintenant) else ATR_MULT
    return round(min(SL_MAX, max(SL_MIN, mult * atr)), 2)


def calculer(atr, liquidites, liquidite_min=200.0, regime="normal", maintenant=None, risque_eur=None, frais_ar_pct=None):
    """Retourne dict: sl_pct, tp_pct, barriere_h, montant, risque_eur, raison."""
    risque = RISQUE_EUR if risque_eur is None else float(risque_eur)
    frais = FRAIS_AR_PCT if frais_ar_pct is None else float(frais_ar_pct)
    if regime == "turbulent":
        risque = risque / 2.0
    sl = stop_pct(atr, maintenant)
    ratio = TP_RATIO_RANGE if regime == "range" else TP_RATIO
    tp = round(sl * ratio, 2)
    # taille : la perte au stop + les frais aller-retour = le risque accepte
    montant_risque = risque / ((sl + frais) / 100.0)
    dispo = max(0.0, liquidites - liquidite_min)
    montant = round(min(montant_risque, dispo), 2)
    raison = (f"stop {sl}% (ATR {atr if atr is not None else '?'}% x {ATR_MULT_US if en_session_us(maintenant) else ATR_MULT}"
              f"{', session US' if en_session_us(maintenant) else ''}) | objectif {tp}% ({ratio}:1) | barriere {BARRIERE_H}h | "
              f"montant {montant:.0f} EUR = risque {montant * (sl + frais) / 100:.2f} EUR frais compris | regime {regime}")
    return {"sl_pct": sl, "tp_pct": tp, "barriere_h": BARRIERE_H, "montant": montant, "risque_eur": risque, "raison": raison}


def point_mort_wr(sl, tp, frais_ar):
    """Taux de reussite minimum (%) pour une esperance nulle, frais compris."""
    return round((sl + frais_ar) / (sl + tp) * 100, 1)


if __name__ == "__main__":
    print("Exemples (ATR -> stop / objectif / montant pour 1 EUR de risque, 1000 EUR de liquidites) :")
    for a in (0.3, 0.5, 0.8, 1.2, 2.0):
        r = calculer(a, 1000.0)
        print(f"  ATR {a:.1f}% -> SL {r['sl_pct']}%  TP {r['tp_pct']}%  montant {r['montant']:.0f} EUR  "
              f"point mort {point_mort_wr(r['sl_pct'], r['tp_pct'], FRAIS_AR_PCT)}% (paper) / "
              f"{point_mort_wr(r['sl_pct'], r['tp_pct'], 0.18)}% (Revolut X) / {point_mort_wr(r['sl_pct'], r['tp_pct'], 1.6)}% (Kraken palier 1)")
