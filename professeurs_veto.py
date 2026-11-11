"""Couche mesuree « professeurs » (11/11/2026) — sans droit d'ouvrir.

Les professeurs n'ouvrent rien. Mais quand ils sont d'accord pour dire NON, cette couche oppose un veto a un ACHAT :
  - professeur Hyperliquid : les meilleurs traders verifies sur chaine sont vendeurs sur la crypto visee, ou massivement
    vendeurs sur le marche (0 vote achat, >= PROF_VETO_VENTES ventes) ;
  - professeur virtuel (Joe007, Cyclop, Downshift Rider) : sa garde BTC dit STOP (BTC sous EMA50 4h, chute soudaine...).

Le veto passe par l'entonnoir (couche « professeurs ») : chaque signal bloque est enregistre et juge 8 h apres sur les
bougies. Si la couche coute des R (>= 30 cas juges, R evite <= -10), elle est desarmee toute seule et se rearme si elle
redevient utile. Elle ne donne jamais le droit d'ouvrir : elle ne peut que bloquer.

Reglages (.env) : PROF_VETO=0 coupe la couche ; PROF_VETO_VENTES (defaut 3) ; PROF_VETO_VIRTUEL=0 ignore le professeur
virtuel ; PROF_VETO_HL=0 ignore Hyperliquid ; ENTONNOIR_PROFESSEURS=0/1 force la couche desarmee/armee cote entonnoir.
"""
import os
import time

CACHE_S = 600  # la garde BTC du professeur virtuel coute des bougies : une lecture par 10 min suffit
_cache = {"ts": 0.0, "virtuel": (True, "")}


def _actif():
    return os.getenv("PROF_VETO", "1") == "1"


def _avis_hyperliquid(sym):
    """(ok, raison) : False si les meilleurs sont vendeurs sur sym ou massivement vendeurs sur le marche."""
    if os.getenv("PROF_VETO_HL", "1") != "1":
        return True, ""
    try:
        import professeur_hyperliquid as hl
        if not hl._actif():
            return True, ""
        d = hl._charger()
        v = hl.vote_du_moment(sym, d)
        if v and v.get("sens") == "vente":
            return False, f"les meilleurs d'Hyperliquid sont vendeurs sur {sym} ({str(v.get('detail') or v.get('tag') or '')[:60]})"
        votes = [x for x in d.get("votes_du_moment") or [] if x.get("sens") != "neutre"]
        n_a = sum(1 for x in votes if x.get("sens") == "achat")
        n_v = len(votes) - n_a
        seuil = int(os.getenv("PROF_VETO_VENTES", "3") or 3)
        if n_a == 0 and n_v >= seuil:
            return False, f"les meilleurs d'Hyperliquid sont vendeurs partout (0 achat / {n_v} ventes)"
    except Exception:
        pass
    return True, ""


def _avis_virtuel():
    """(ok, raison) du professeur virtuel (garde BTC), en cache 10 min."""
    if os.getenv("PROF_VETO_VIRTUEL", "1") != "1":
        return True, ""
    now = time.time()
    if now - _cache["ts"] < CACHE_S:
        return _cache["virtuel"]
    res = (True, "")
    try:
        import professeur_virtuel as pv
        ok, raison = pv._garde_btc({}, {})
        res = (bool(ok), "" if ok else f"professeur virtuel : {str(raison)[:90]}")
    except Exception:
        res = (True, "")
    _cache["ts"] = now
    _cache["virtuel"] = res
    return res


def avis(sym):
    """(ok, raison) : ok=False quand au moins un professeur dit NON a un achat sur sym. Fail-open."""
    if not _actif():
        return True, ""
    raisons = []
    ok_hl, r_hl = _avis_hyperliquid(sym)
    if not ok_hl:
        raisons.append(r_hl)
    ok_v, r_v = _avis_virtuel()
    if not ok_v:
        raisons.append(r_v)
    if raisons:
        return False, " ; ".join(raisons)
    return True, ""


def resume_court(sym="BTCUSDT"):
    ok, raison = avis(sym)
    if not _actif():
        return "Professeurs (veto) : coupe (PROF_VETO=0)"
    return "Professeurs (veto) : " + ("rien a redire" if ok else "NON — " + raison)


if __name__ == "__main__":
    import sys
    print(resume_court(sys.argv[1] if len(sys.argv) > 1 else "BTCUSDT"))
