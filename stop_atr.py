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
RISQUE_EUR = float(os.getenv("RISQUE_EUR", "1.0"))                # plancher et valeur de secours (le risque reel est en % : voir risque_courant)
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


# ---------------------------------------------------------------- risque par trade (22/10/2026, revu le 11/11/2026)
# Jusqu'au 11/11 le risque etait 1 EUR fixe (0,1 % du capital) et le palier x2 exigeait que TOUTES les strategies melangees
# soient prouvees gagnantes : il n'a jamais ete atteint -> 76 trades, WR 50 %, net -0,56 EUR, « sur place » mathematique.
# Desormais :
#   - base = RISQUE_PCT du capital (0,25 % = 2,5 EUR sur 1 000 ; un systematique prudent risque 0,25-0,5 %, 1 % au plus),
#   - la preuve se mesure PAR STRATEGIE sur son epoque courante (registre) : >= 30 trades et borne basse 90 % du gain
#     moyen > 0 -> x2 ; >= 60 -> x3 ; une strategie en probation -> x0,5 ; plafond RISQUE_MAX_PCT (1 %) du capital,
#   - protocole de drawdown (paliers) : capital sous le depart de 5 % -> x0,75 ; 10 % -> x0,5 ; 15 % -> x0,25.
# Tout redescend seul quand la preuve disparait. RISQUE_EUR reste le plancher (1 EUR) et la valeur de secours.
RISQUE_PCT = float(os.getenv("RISQUE_PCT", "0.25"))
RISQUE_MAX_PCT = float(os.getenv("RISQUE_MAX_PCT", "1.0"))
PALIERS = [(60, 3.0), (30, 2.0)]
DRAWDOWN_PALIERS = [(15.0, 0.25), (10.0, 0.5), (5.0, 0.75)]
_RC = {}


def _borne_basse(gains):
    n = len(gains)
    if n < 2:
        return None, None
    m = sum(gains) / n
    sd = (sum((g - m) ** 2 for g in gains) / (n - 1)) ** 0.5
    return m, m - 1.645 * sd / (n ** 0.5)


def _trades_strategie(trades, strategie):
    """Trades de la strategie dans son epoque courante (registre : reprise ou vehicule) ; sinon tous ses trades."""
    def _nom(t):
        return str(t.get("strategie") or t.get("source") or "inconnu")
    mine = [t for t in trades if _nom(t) == str(strategie) and "_PARTIAL" not in str(t.get("source", ""))]
    try:
        import json as _j
        reg = _j.load(open(os.path.join(os.path.dirname(os.path.abspath(__file__)), "registre_strategies.json")))
        depuis = ((reg.get("strategies", {}).get(str(strategie)) or {}).get("epoque") or {}).get("depuis")
        if depuis:
            mine = [t for t in mine if str(t.get("date_fermeture") or t.get("date_ouverture") or "") >= str(depuis)]
    except Exception:
        pass
    return mine


def _statut_strategie(strategie):
    try:
        import json as _j
        reg = _j.load(open(os.path.join(os.path.dirname(os.path.abspath(__file__)), "registre_strategies.json")))
        return (reg.get("strategies", {}).get(str(strategie)) or {}).get("statut")
    except Exception:
        return None


def risque_courant(trades=None, capital=None, verbose=False, strategie=None, capital_initial=None):
    """Risque en EUR par trade : base RISQUE_PCT du capital x palier prouve DE LA STRATEGIE x protocole de drawdown,
    borne [RISQUE_EUR, RISQUE_MAX_PCT du capital]. Lit paper_trading.json si trades/capital absents (cache 5 min)."""
    import time as _t
    cle = str(strategie or "")
    lu = trades is None and capital is None
    if lu and cle in _RC and _t.time() - _RC[cle][0] < 300:
        return _RC[cle][1]
    try:
        if trades is None or capital is None:
            import json as _j
            pf = _j.load(open(os.path.join(os.path.dirname(os.path.abspath(__file__)), "paper_trading.json")))
            if trades is None:
                trades = pf.get("trades_fermes", [])
                try:
                    import registre_strategies as _rs
                    trades = _rs.tous_les_trades(trades)      # archive + courant : l'epoque d'une strategie peut etre ancienne
                except Exception:
                    pass
            if capital is None:
                capital = float(pf.get("liquidites", 0) or 0) + sum(float(p.get("montant_eur", 0) or 0) for p in pf.get("positions", []))
            if capital_initial is None:
                capital_initial = float(pf.get("capital_initial", 0) or 0) or None
    except Exception:
        trades, capital = trades or [], capital or 1000.0
    capital = float(capital or 1000.0)
    base = max(RISQUE_EUR, capital * RISQUE_PCT / 100.0)
    plafond = max(RISQUE_EUR, capital * RISQUE_MAX_PCT / 100.0)
    # --- preuve par strategie (ou globale si aucune strategie donnee)
    mine = _trades_strategie(trades or [], strategie) if strategie else [t for t in (trades or []) if "_PARTIAL" not in str(t.get("source", ""))]
    gains = []
    for t in mine:
        try:
            gains.append(float(t.get("gain_eur", 0) or 0))
        except Exception:
            pass
    n = len(gains)
    m, bb = _borne_basse(gains)
    mult, preuve = 1.0, f"palier 1 ({n} trade{'s' if n != 1 else ''}{' de ' + str(strategie) if strategie else ''}"
    if bb is not None:
        for n_min, k in PALIERS:
            if n >= n_min and bb > 0:
                mult, preuve = k, f"palier x{k:g} ({n} trades{' de ' + str(strategie) if strategie else ''}, gain moyen {m:+.2f}, borne basse 90% {bb:+.2f} > 0"
                break
        else:
            preuve += f", borne basse 90% du gain moyen {bb:+.2f}{' <= 0' if bb <= 0 else ''}{', il faut >= 30 trades' if n < 30 else ''}"
    preuve += ")"
    statut = _statut_strategie(strategie) if strategie else None
    if statut == "probation":
        mult *= 0.5
        preuve += " x0.5 probation"
    # --- protocole de drawdown
    dd_mult = 1.0
    if capital_initial and capital_initial > 0:
        dd = (capital_initial - capital) / capital_initial * 100.0
        for seuil, f in DRAWDOWN_PALIERS:
            if dd >= seuil:
                dd_mult = f
                preuve += f" | drawdown {dd:.1f}% -> x{f:g}"
                break
    r = round(min(plafond, max(RISQUE_EUR, base * mult * dd_mult)), 2)
    if verbose:
        print(f"Risque par trade : {r:.2f} EUR = base {base:.2f} ({RISQUE_PCT}% de {capital:.0f}) — {preuve} ; plafond {plafond:.2f} EUR ({RISQUE_MAX_PCT}%)")
    if lu:
        _RC[cle] = (_t.time(), r)
    return r


def calculer(atr, liquidites, liquidite_min=200.0, regime="normal", maintenant=None, risque_eur=None, frais_ar_pct=None, strategie=None):
    """Retourne dict: sl_pct, tp_pct, barriere_h, montant, risque_eur, raison."""
    if risque_eur is None:
        try:
            risque = risque_courant(strategie=strategie)
        except Exception:
            risque = RISQUE_EUR
    else:
        risque = float(risque_eur)
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
    import sys
    if len(sys.argv) > 1 and sys.argv[1] == "risque":
        risque_courant(verbose=True, strategie=sys.argv[2] if len(sys.argv) > 2 else None)
        if len(sys.argv) <= 2:
            try:
                import json as _j
                reg = _j.load(open(os.path.join(os.path.dirname(os.path.abspath(__file__)), "registre_strategies.json")))
                for k, v in sorted(reg.get("strategies", {}).items()):
                    if v.get("droit_ouverture"):
                        risque_courant(verbose=True, strategie=k)
            except Exception:
                pass
        sys.exit(0)
    print("Exemples (ATR -> stop / objectif / montant pour 1 EUR de risque, 1000 EUR de liquidites) :")
    for a in (0.3, 0.5, 0.8, 1.2, 2.0):
        r = calculer(a, 1000.0)
        print(f"  ATR {a:.1f}% -> SL {r['sl_pct']}%  TP {r['tp_pct']}%  montant {r['montant']:.0f} EUR  "
              f"point mort {point_mort_wr(r['sl_pct'], r['tp_pct'], FRAIS_AR_PCT)}% (paper) / "
              f"{point_mort_wr(r['sl_pct'], r['tp_pct'], 0.18)}% (Revolut X) / {point_mort_wr(r['sl_pct'], r['tp_pct'], 1.6)}% (Kraken palier 1)")
