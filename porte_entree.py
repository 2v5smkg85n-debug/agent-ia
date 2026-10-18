#!/usr/bin/env python3
"""
porte_entree.py — LA porte unique par laquelle passe toute ouverture de position.

Appelee par journal_erreurs.preparer_entree (donc par paper_trading.ouvrir_position) APRES les regles apprises
et AVANT le calcul du stop/taille. Chaque filtre est independant, desactivable par variable d'environnement
(PORTE_xxx=0) et "fail-open" : si une API ne repond pas, le filtre laisse passer et le note dans le log.

Filtres (dans l'ordre, du moins cher au plus cher) :
  1. PORTE_FENETRES       13h00-15h00 UTC par defaut (FENETRES_UTC=...) + annonce macro USD High dans l'heure
  2. PORTE_TENDANCE_LENTE BTC au-dessus de son EMA 12 semaines (journalier) et EMA en hausse
  3. PORTE_CHALEUR        max N positions crypto ouvertes (meme cluster BTC) et risque total ouvert <= RISQUE_TOTAL_MAX EUR
  4. PORTE_REGIME         pas d'entree en regime "turbulent" (ATR 1h au-dessus du 90e percentile sur 100 bougies)
  5. PORTE_CUSUM          un evenement de prix (CUSUM symetrique, seuil max(1 %, 2.5 x ATR 1h)) dans les 4 dernieres heures
  6. PORTE_LIQUIDITE      spread Kraken <= 0.15 % et profondeur a +/-0.5 % >= 10 x le montant
  7. PORTE_FLUX           flux d'ordres Kraken (30 min) pas franchement vendeur (TFI >= -0.3)
  8. PORTE_META           si un meta-modele entraine existe : probabilite de succes >= META_SEUIL

Toutes les decisions (passees ET bloquees) sont ecrites dans porte_entree_log.jsonl : c'est la matiere premiere
pour mesurer plus tard combien de pertes chaque filtre a evitees (et combien de gains il a coutes).
"""
import json
import math
import os
import threading
import time
from datetime import datetime, timezone

DOSSIER = os.path.dirname(os.path.abspath(__file__))
LOG = os.path.join(DOSSIER, "porte_entree_log.jsonl")
_LOCK = threading.Lock()
_CACHE = {}

RISQUE_TOTAL_MAX = float(os.getenv("RISQUE_TOTAL_MAX", "3.0"))
MAX_POSITIONS_CRYPTO = int(os.getenv("MAX_POSITIONS_CRYPTO", "2"))
EMA_LENTE_JOURS = int(os.getenv("EMA_LENTE_JOURS", "84"))           # 12 semaines
CUSUM_SEUIL_PCT = float(os.getenv("CUSUM_SEUIL_PCT", "1.0"))        # seuil minimum ; seuil reel = max(1 %, CUSUM_ATR_MULT x ATR 1h)
CUSUM_ATR_MULT = float(os.getenv("CUSUM_ATR_MULT", "2.5"))
CUSUM_FENETRE_BARRES = int(os.getenv("CUSUM_FENETRE_BARRES", "4"))
SPREAD_MAX_PCT = float(os.getenv("SPREAD_MAX_PCT", "0.15"))
PROFONDEUR_MULT = float(os.getenv("PROFONDEUR_MULT", "10"))
TFI_MIN = float(os.getenv("TFI_MIN", "-0.3"))
META_SEUIL = float(os.getenv("META_SEUIL", "0.5"))
# Fenetres interdites UTC, modifiables sans code : FENETRES_UTC="13:00-15:00,17:00-18:00"
def _fenetres():
    out = []
    for f in os.getenv("FENETRES_UTC", "13:00-15:00").split(","):
        try:
            a, b = f.strip().split("-")
            out.append((tuple(int(x) for x in a.split(":")), tuple(int(x) for x in b.split(":"))))
        except Exception:
            continue
    return out or [((13, 0), (15, 0))]
FENETRES = _fenetres()


def _actif(nom, defaut="1"):
    return os.getenv(f"PORTE_{nom}", defaut) == "1"


def _cache(cle, ttl, fn):
    e = _CACHE.get(cle)
    now = time.time()
    if e and now - e[0] < ttl:
        return e[1]
    v = fn()
    _CACHE[cle] = (now, v)
    return v


def _ema(vals, n):
    if len(vals) < n:
        return None
    k = 2 / (n + 1)
    e = sum(vals[:n]) / n
    for v in vals[n:]:
        e = v * k + e * (1 - k)
    return e


# ------------------------------------------------------------------ 1. fenetres interdites
def fenetre_interdite(maintenant=None):
    now = maintenant or datetime.now(timezone.utc)
    hm = (now.hour, now.minute)
    for deb, fin in FENETRES:
        if deb <= hm < fin:
            return True, f"fenetre {deb[0]:02d}h{deb[1]:02d}-{fin[0]:02d}h{fin[1]:02d} UTC (ouverture US / heures perdantes)"
    try:
        import macro_calendar as mc
        evs = mc.evenements_proches(heures=1, devise="USD", impact_min="High")
        if evs:
            ev = evs[0]
            return True, f"annonce macro USD {ev['impact']} a {ev['heure']}: {str(ev['titre'])[:40]}"
    except Exception:
        pass
    return False, ""


# ------------------------------------------------------------------ 2. tendance lente BTC
def tendance_lente_btc():
    """{'haussiere': bool|None, 'ecart_pct': float, 'pente_pct': float, 'ema_jours': 84}. None si donnees absentes."""
    def _calc():
        out = {"haussiere": None, "ecart_pct": None, "pente_pct": None, "ema_jours": EMA_LENTE_JOURS}
        try:
            import indicateurs as ind
            b = ind.historique_ohlcv("BTCUSDT", "1d", EMA_LENTE_JOURS + 40)
            if not b or len(b) < EMA_LENTE_JOURS + 6:
                return out
            cl = [x["cloture"] for x in b]
            e_now, e_prev = _ema(cl, EMA_LENTE_JOURS), _ema(cl[:-5], EMA_LENTE_JOURS)
            if not e_now or not e_prev:
                return out
            out["ecart_pct"] = round((cl[-1] - e_now) / e_now * 100, 2)
            out["pente_pct"] = round((e_now - e_prev) / e_prev * 100, 3)
            out["haussiere"] = cl[-1] > e_now and e_now >= e_prev
        except Exception:
            pass
        return out
    return _cache("tendance_lente", 3600, _calc)


# ------------------------------------------------------------------ 3. chaleur du portefeuille
def chaleur_portefeuille(pf, risque_nouveau=1.0, sl_defaut=1.0):
    positions = (pf or {}).get("positions", [])
    crypto = [p for p in positions if p.get("marche", "crypto") in ("crypto", "?")]
    risque = 0.0
    for p in positions:
        sl = p.get("sl_risque") or p.get("sl_adaptatif") or sl_defaut
        try:
            risque += float(p.get("montant_eur", 0)) * float(sl) / 100.0
        except Exception:
            risque += risque_nouveau
    return {"n_crypto": len(crypto), "risque_ouvert": round(risque, 2), "risque_apres": round(risque + risque_nouveau, 2)}


# ------------------------------------------------------------------ 4. regime
def regime_actuel(sym="BTCUSDT"):
    """'tendance' | 'range' | 'turbulent' | 'inconnu' + details (ADX, ATR percentile)."""
    def _calc():
        out = {"mode": "inconnu", "adx": None, "atr_pct": None, "atr_percentile": None}
        try:
            import indicateurs as ind
            import regime as rg
            import stop_atr as sa
            b = ind.historique_ohlcv(sym, "1h", 130)
            if not b or len(b) < 60:
                return out
            out["adx"] = rg.adx(b)
            atrs = []
            for i in range(30, len(b) + 1):
                a = sa.atr_pct(b[:i])
                if a:
                    atrs.append(a)
            if atrs:
                out["atr_pct"] = atrs[-1]
                out["atr_percentile"] = round(sum(1 for a in atrs if a <= atrs[-1]) / len(atrs) * 100)
            if out["atr_percentile"] is not None and out["atr_percentile"] >= 90:
                out["mode"] = "turbulent"
            elif out["adx"] is not None and out["adx"] >= 25:
                out["mode"] = "tendance"
            elif out["adx"] is not None:
                out["mode"] = "range"
        except Exception:
            pass
        return out
    return _cache(f"regime_{sym}", 900, _calc)


# ------------------------------------------------------------------ 5. CUSUM (sans etat)
def cusum_evenement(clotures, seuil_pct=None, fenetre=None):
    """Filtre CUSUM symetrique (Lopez de Prado). Retourne (evenement_recent, barres_depuis, direction).
    On cumule les rendements ; des que la somme depasse +/-seuil on note un evenement et on repart de zero."""
    seuil = (seuil_pct or CUSUM_SEUIL_PCT) / 100.0
    fen = fenetre or CUSUM_FENETRE_BARRES
    if not clotures or len(clotures) < 5:
        return None, None, None
    s_pos = s_neg = 0.0
    dernier, direction = None, None
    for i in range(1, len(clotures)):
        if not clotures[i - 1]:
            continue
        r = math.log(clotures[i] / clotures[i - 1]) if clotures[i] > 0 else 0.0
        s_pos = max(0.0, s_pos + r)
        s_neg = min(0.0, s_neg + r)
        if s_pos > seuil:
            dernier, direction, s_pos = i, "hausse", 0.0
        elif s_neg < -seuil:
            dernier, direction, s_neg = i, "baisse", 0.0
    if dernier is None:
        return False, None, None
    depuis = len(clotures) - 1 - dernier
    return depuis < fen, depuis, direction


# ------------------------------------------------------------------ 6. liquidite (Kraken public)
def liquidite(sym, montant):
    """{'spread_pct', 'profondeur_eur', 'ok', 'raison'} — fail-open si Kraken ne repond pas."""
    def _calc():
        out = {"spread_pct": None, "profondeur_eur": None, "ok": True, "raison": ""}
        try:
            import requests
            import kraken_paper as kp
            paire = kp.paire_kraken(sym)
            if not paire:
                out["raison"] = "pas sur Kraken EUR (non verifie)"
                return out
            r = requests.get(f"{kp.API}/Depth", params={"pair": paire, "count": 100}, timeout=8).json()
            res = list(r["result"].values())[0]
            asks, bids = res["asks"], res["bids"]
            best_ask, best_bid = float(asks[0][0]), float(bids[0][0])
            mid = (best_ask + best_bid) / 2
            out["spread_pct"] = round((best_ask - best_bid) / mid * 100, 3)
            prof = sum(float(p) * float(q) for p, q, *_ in asks if float(p) <= mid * 1.005)
            prof += sum(float(p) * float(q) for p, q, *_ in bids if float(p) >= mid * 0.995)
            out["profondeur_eur"] = round(prof)
            if out["spread_pct"] > SPREAD_MAX_PCT:
                out["ok"], out["raison"] = False, f"spread Kraken {out['spread_pct']}% > {SPREAD_MAX_PCT}%"
            elif prof < PROFONDEUR_MULT * float(montant or 0):
                out["ok"], out["raison"] = False, f"profondeur +/-0.5% = {prof:.0f} EUR < {PROFONDEUR_MULT:.0f} x {float(montant or 0):.0f} EUR"
        except Exception as e:
            out["raison"] = f"liquidite non verifiee ({str(e)[:40]})"
        return out
    return _cache(f"liq_{sym}_{int(float(montant or 0) // 50)}", 60, _calc)


# ------------------------------------------------------------------ verdict
def verifier(sym, prix, ctx, pf, montant, sl_pct=None, strategie=None, risque_nouveau=1.0):
    """Retourne {'ok', 'raison', 'infos'}. infos contient regime/tendance/tfi/p_meta pour l'IA et le log."""
    infos = {"sym": sym, "strategie": strategie, "date": datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M"), "filtres_sautes": []}
    bloque = None

    # 1. fenetres
    if _actif("FENETRES"):
        b, why = fenetre_interdite()
        if b:
            bloque = f"fenetre interdite: {why}"
    # 2. tendance lente
    tl = tendance_lente_btc() if _actif("TENDANCE_LENTE") else {}
    infos["tendance_lente"] = tl
    if not bloque and _actif("TENDANCE_LENTE"):
        if tl.get("haussiere") is False:
            bloque = f"BTC sous son EMA {EMA_LENTE_JOURS} jours ({tl.get('ecart_pct')}%, pente {tl.get('pente_pct')}%): pas d'achat tant que la tendance lente est baissiere"
        elif tl.get("haussiere") is None:
            infos["filtres_sautes"].append("tendance_lente")
    # 3. chaleur
    if _actif("CHALEUR"):
        ch = chaleur_portefeuille(pf, risque_nouveau=risque_nouveau)
        infos["chaleur"] = ch
        max_pos = MAX_POSITIONS_CRYPTO + (1 if tl.get("haussiere") else 0)
        if not bloque and ch["n_crypto"] >= max_pos:
            bloque = f"deja {ch['n_crypto']} positions crypto ouvertes (max {max_pos}, toutes correlees a BTC)"
        elif not bloque and ch["risque_apres"] > RISQUE_TOTAL_MAX:
            bloque = f"risque total ouvert {ch['risque_ouvert']:.2f} + {risque_nouveau:.2f} > {RISQUE_TOTAL_MAX:.2f} EUR"
    # 4. regime
    reg = regime_actuel("BTCUSDT") if _actif("REGIME") else {}
    infos["regime"] = reg
    if not bloque and _actif("REGIME") and reg.get("mode") == "turbulent":
        bloque = f"regime turbulent (ATR 1h BTC au {reg.get('atr_percentile')}e percentile, ADX {reg.get('adx')})"
    # 5. CUSUM
    if not bloque and _actif("CUSUM"):
        try:
            import indicateurs as ind
            b = ind.historique_ohlcv(sym, "1h", 72)
            _atr = (ctx or {}).get("atr_pct") or 0.4
            seuil = round(max(CUSUM_SEUIL_PCT, CUSUM_ATR_MULT * float(_atr)), 2)
            ev, depuis, direction = cusum_evenement([x["cloture"] for x in b], seuil_pct=seuil) if b else (None, None, None)
            infos["cusum"] = {"evenement": ev, "barres_depuis": depuis, "direction": direction, "seuil_pct": seuil}
            if ev is False or (ev is not None and not ev):
                bloque = f"aucun evenement de prix (CUSUM {seuil}%) dans les {CUSUM_FENETRE_BARRES} dernieres heures (dernier il y a {depuis} h): c'est du bruit"
            elif ev is None:
                infos["filtres_sautes"].append("cusum")
        except Exception:
            infos["filtres_sautes"].append("cusum")
    # 6. liquidite
    if not bloque and _actif("LIQUIDITE"):
        liq = liquidite(sym, montant)
        infos["liquidite"] = liq
        if not liq["ok"]:
            bloque = liq["raison"]
        elif liq.get("spread_pct") is None:
            infos["filtres_sautes"].append("liquidite")
    # 7. flux d'ordres
    if _actif("FLUX"):
        try:
            import flux_ordres as fo
            tfi = fo.tfi(sym, minutes=30)
            infos["tfi_30m"] = tfi
            if not bloque and tfi is not None and tfi < TFI_MIN:
                bloque = f"flux d'ordres vendeur (TFI 30 min {tfi:+.2f} < {TFI_MIN})"
            if tfi is None:
                infos["filtres_sautes"].append("flux")
        except Exception:
            infos["filtres_sautes"].append("flux")
    # 8. meta-modele
    if _actif("META"):
        try:
            import meta_modele as mm
            p = mm.probabilite(mm.features_depuis_contexte(ctx or {}, regime=reg.get("mode"), tfi=infos.get("tfi_30m"), strategie=strategie))
            infos["p_meta"] = p
            if not bloque and p is not None and p < META_SEUIL:
                bloque = f"meta-modele: probabilite de succes {p:.2f} < {META_SEUIL}"
        except Exception:
            infos["filtres_sautes"].append("meta")

    rec = {"ok": bloque is None, "raison": bloque or "porte ouverte", "infos": infos, "prix": prix, "montant": montant, "sl_pct": sl_pct}
    _journaliser(rec)
    return rec


def _journaliser(rec):
    try:
        with _LOCK:
            with open(LOG, "a") as f:
                f.write(json.dumps(rec, ensure_ascii=False, default=str) + "\n")
    except Exception:
        pass


def dernieres_decisions(n=30):
    try:
        with open(LOG) as f:
            lignes = f.readlines()[-n:]
        return [json.loads(l) for l in lignes if l.strip()]
    except Exception:
        return []


def contexte_pour_ia():
    """Bloc texte pour le prompt du cerveau : tendance lente, regime, fenetres."""
    parts = []
    try:
        tl = tendance_lente_btc()
        if tl.get("haussiere") is not None:
            parts.append(f"TENDANCE LENTE BTC (EMA {EMA_LENTE_JOURS} j): {'HAUSSIERE' if tl['haussiere'] else 'BAISSIERE -> aucun achat ne passera la porte'} "
                         f"(prix {tl['ecart_pct']:+.1f}% vs EMA, pente {tl['pente_pct']:+.2f}%/5j)")
        reg = regime_actuel("BTCUSDT")
        if reg.get("mode") != "inconnu":
            parts.append(f"REGIME 1h BTC: {reg['mode'].upper()} (ADX {reg.get('adx')}, ATR {reg.get('atr_pct')}% = {reg.get('atr_percentile')}e percentile)"
                         + (" -> objectif reduit a 1.5x le stop" if reg["mode"] == "range" else "") + (" -> la porte bloque" if reg["mode"] == "turbulent" else ""))
        b, why = fenetre_interdite()
        if b:
            parts.append(f"FENETRE INTERDITE EN CE MOMENT: {why}")
    except Exception:
        pass
    return "\n".join(parts)


def statistiques(n=500):
    """Pour le dashboard : nombre de passages / blocages par filtre."""
    decs = dernieres_decisions(n)
    out = {"total": len(decs), "ouvertes": sum(1 for d in decs if d.get("ok")), "bloquees": {}}
    for d in decs:
        if not d.get("ok"):
            k = str(d.get("raison", ""))[:40].split(":")[0]
            out["bloquees"][k] = out["bloquees"].get(k, 0) + 1
    return out


if __name__ == "__main__":
    import sys
    sym = sys.argv[1] if len(sys.argv) > 1 else "ETHUSDT"
    print("Tendance lente BTC :", tendance_lente_btc())
    print("Regime BTC 1h     :", regime_actuel("BTCUSDT"))
    print("Fenetre interdite :", fenetre_interdite())
    print(f"Liquidite {sym}   :", liquidite(sym, 100))
    try:
        import indicateurs as ind
        b = ind.historique_ohlcv(sym, "1h", 48)
        print(f"CUSUM {sym}        :", cusum_evenement([x["cloture"] for x in b]))
    except Exception as e:
        print("CUSUM indisponible:", e)
    print("\nVerdict complet   :", json.dumps(verifier(sym, 0, {}, {"positions": []}, 100, 1.0, "test"), ensure_ascii=False, default=str)[:600])
    print("\nStatistiques      :", statistiques())
