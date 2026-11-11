#!/usr/bin/env python3
"""
pret_pour_le_reel.py — le bot sait ou il en est sur le chemin du reel, et le dit.

Le paper n'est pas de l'argent reel, mais il doit etre juge comme s'il l'etait. Ce module calcule, depuis le nouveau depart
(paper_trading.json, trades_fermes), les conditions qu'un systematique doit remplir AVANT de passer en reel, et les
affiche (dashboard /porte, commande Telegram « reel »). Rien ici n'ouvre ni ne ferme de trade.

Conditions (toutes mesurables, aucune n'est un avis) :
  1. echantillon : >= N_MIN trades fermes depuis le depart (100) — en dessous, la variance domine ;
  2. esperance apres frais > 0 avec sa borne basse 90 % > 0 (le gain moyen par trade n'est pas du bruit) ;
  3. drawdown maximal <= DD_MAX % (5 %) depuis le depart (pic -> creux de la valeur du portefeuille) ;
  4. regularite : au moins 3 des 4 dernieres semaines (avec >= 3 trades) sont positives ;
  5. au moins une strategie avec droit d'ouvrir est 'active' dans le registre (prouvee, pas en probation) ;
  6. frais reels : le resultat reste > 0 si l'on remplace les frais du paper (0,2 % A/R) par Revolut X (0,18 % A/R) ET par
     un glissement de SLIPPAGE_PCT (0,05 %) par cote — la marge ne doit pas tenir a l'absence de glissement.
Quand tout est vert, le module propose un capital reel de depart = CAPITAL_REEL_DEPART (200 EUR) avec le meme risque en %
que le paper (stop_atr.RISQUE_PCT), et rappelle le protocole : 1 mois reel a petite taille, puis monter par paliers.
Variables : REEL_N_MIN, REEL_DD_MAX, REEL_SLIPPAGE_PCT, REEL_CAPITAL_DEPART.
CLI : python3 pret_pour_le_reel.py
"""
import json
import os
from datetime import datetime, timedelta

DOSSIER = os.path.dirname(os.path.abspath(__file__))
PT_FILE = os.path.join(DOSSIER, "paper_trading.json")
N_MIN = int(os.getenv("REEL_N_MIN", "100"))
DD_MAX = float(os.getenv("REEL_DD_MAX", "5.0"))
SLIPPAGE_PCT = float(os.getenv("REEL_SLIPPAGE_PCT", "0.05"))      # par cote
FRAIS_PAPER_AR = 0.20
FRAIS_REVOLUT_AR = 0.18
CAPITAL_REEL_DEPART = float(os.getenv("REEL_CAPITAL_DEPART", "200"))


def _dt(s):
    for f in ("%Y-%m-%d %H:%M:%S", "%Y-%m-%d %H:%M"):
        try:
            return datetime.strptime(str(s)[:19] if len(str(s)) >= 19 else str(s), f)
        except Exception:
            pass
    return None


def _trades(pf):
    out = []
    for t in pf.get("trades_fermes", []) or []:
        if "_PARTIAL" in str(t.get("source", "")):
            continue
        try:
            out.append({"gain": float(t.get("gain_eur", 0) or 0), "montant": float(t.get("montant_eur", 0) or 0),
                        "date": _dt(t.get("date_fermeture")) or _dt(t.get("date_ouverture")),
                        "strategie": str(t.get("strategie") or t.get("source") or "inconnu"),
                        "frais": float(t.get("frais_total", 0) or 0)})
        except Exception:
            pass
    return out


def _borne_basse(gains):
    n = len(gains)
    if n < 2:
        return None, None
    m = sum(gains) / n
    sd = (sum((g - m) ** 2 for g in gains) / (n - 1)) ** 0.5
    return m, m - 1.645 * sd / (n ** 0.5)


def _drawdown_max(pf, trades):
    """Pic -> creux sur la courbe de capital reconstituee trade par trade (capital_initial + gains cumules)."""
    cap = float(pf.get("capital_initial", 1000) or 1000)
    pic, dd_max = cap, 0.0
    for t in sorted(trades, key=lambda x: x["date"] or datetime.min):
        cap += t["gain"]
        pic = max(pic, cap)
        dd_max = max(dd_max, (pic - cap) / pic * 100 if pic else 0.0)
    # le pic enregistre par le bot (positions ouvertes comprises) peut etre plus haut
    try:
        pic_bot = float(pf.get("pic_capital") or 0)
        val = float(pf.get("liquidites", 0) or 0) + sum(float(p.get("montant_eur", 0) or 0) for p in pf.get("positions", []))
        if pic_bot and val:
            dd_max = max(dd_max, (pic_bot - val) / pic_bot * 100)
    except Exception:
        pass
    return round(dd_max, 2)


def _semaines(trades, n=4):
    now = datetime.now()
    out = []
    for i in range(n):
        fin = now - timedelta(days=7 * i)
        deb = fin - timedelta(days=7)
        ts = [t for t in trades if t["date"] and deb < t["date"] <= fin]
        out.append({"semaine": deb.strftime("%d/%m"), "n": len(ts), "net": round(sum(t["gain"] for t in ts), 2)})
    return list(reversed(out))


def etat(pf=None):
    if pf is None:
        try:
            pf = json.load(open(PT_FILE))
        except Exception:
            return {"erreur": "paper_trading.json illisible"}
    trades = _trades(pf)
    gains = [t["gain"] for t in trades]
    n = len(gains)
    net = round(sum(gains), 2)
    m, bb = _borne_basse(gains)
    dd = _drawdown_max(pf, trades)
    sem = _semaines(trades)
    sem_jugees = [s for s in sem if s["n"] >= 3]
    sem_pos = sum(1 for s in sem_jugees if s["net"] > 0)
    # frais reels + glissement : on retire au gain la difference de frais et le glissement sur le montant
    net_reel = 0.0
    for t in trades:
        ajust = t["montant"] * ((FRAIS_REVOLUT_AR - FRAIS_PAPER_AR) + 2 * SLIPPAGE_PCT) / 100.0
        net_reel += t["gain"] - ajust
    net_reel = round(net_reel, 2)
    actives = []
    try:
        reg = json.load(open(os.path.join(DOSSIER, "registre_strategies.json"))).get("strategies", {})
        actives = sorted(k for k, v in reg.items() if v.get("droit_ouverture") and v.get("statut") == "active")
    except Exception:
        pass
    conditions = [
        {"nom": f"echantillon >= {N_MIN} trades", "ok": n >= N_MIN, "valeur": f"{n} trades"},
        {"nom": "esperance apres frais > 0 (borne basse 90 % > 0)", "ok": bool(m is not None and m > 0 and bb is not None and bb > 0),
         "valeur": (f"{m:+.3f} EUR/trade, borne basse {bb:+.3f}" if m is not None else "pas assez de trades")},
        {"nom": f"drawdown max <= {DD_MAX:g} %", "ok": dd <= DD_MAX, "valeur": f"{dd:.2f} %"},
        {"nom": "3 des 4 dernieres semaines positives", "ok": sem_pos >= 3 and len(sem_jugees) >= 3,
         "valeur": " | ".join(f"{s['semaine']}: {s['net']:+.2f} ({s['n']} t)" for s in sem)},
        {"nom": "au moins une strategie 'active' avec droit d'ouvrir", "ok": bool(actives), "valeur": ", ".join(actives) or "aucune (toutes en probation)"},
        {"nom": f"net > 0 avec frais Revolut X 0,18 % et glissement {SLIPPAGE_PCT:g} %/cote", "ok": net_reel > 0, "valeur": f"{net_reel:+.2f} EUR (paper {net:+.2f})"},
    ]
    n_ok = sum(1 for c in conditions if c["ok"])
    risque_pct = None
    try:
        import stop_atr as _sa
        risque_pct = _sa.RISQUE_PCT
    except Exception:
        pass
    return {"n": n, "net": net, "esperance": round(m, 4) if m is not None else None, "borne_basse": round(bb, 4) if bb is not None else None,
            "drawdown_max": dd, "semaines": sem, "actives": actives, "net_reel": net_reel, "conditions": conditions,
            "n_ok": n_ok, "n_total": len(conditions), "pret": n_ok == len(conditions),
            "capital_reel_depart": CAPITAL_REEL_DEPART, "risque_pct": risque_pct,
            "depuis": pf.get("date_creation")}


def rapport(pf=None):
    e = etat(pf)
    if e.get("erreur"):
        return e["erreur"]
    l = [f"=== PRET POUR LE REEL ? {e['n_ok']}/{e['n_total']} conditions (depuis {e.get('depuis')}) ==="]
    for c in e["conditions"]:
        l.append(f"  [{'OK' if c['ok'] else '--'}] {c['nom']} : {c['valeur']}")
    if e["pret"]:
        l.append(f"  -> VERT. Proposition : demarrer en reel avec {e['capital_reel_depart']:.0f} EUR, meme risque ({e.get('risque_pct')} % par trade), "
                 "1 mois a cette taille, puis monter par paliers si les 6 conditions restent vraies en reel.")
    else:
        manque = [c["nom"] for c in e["conditions"] if not c["ok"]]
        l.append(f"  -> PAS ENCORE. Il manque : {'; '.join(manque)}.")
        l.append("  Le bot continue en paper avec les memes regles qu'en reel (risque en % du capital, frais, stop 2 x ATR). "
                 "Rien a forcer : les conditions se remplissent avec les trades.")
    return "\n".join(l)


if __name__ == "__main__":
    print(rapport())
