#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""filtre_multitemporel.py — Filtre multi-temporel: ne pas acheter contre la
tendance journalière. Un signal d'achat 1h est bien plus fort si le daily
confirme. Le système est long-only -> ce filtre protège en marché baissier.

Comportement (tendance daily via EMA20 vs EMA50 + prix):
  - hausse        (EMA20>EMA50, prix>EMA20) -> autorise, pleine taille
  - neutre        (EMAs mélangés)            -> autorise, taille x0.85
  - baisse_moyenne (EMA20<EMA50, prix>EMA50) -> autorise, taille x0.60 (contre-tendance modérée)
  - baisse_forte   (EMA20<EMA50, prix<EMA50) -> VETO (acheter contre un bear fort = risque)

Cache 1h par symbole (évite de refetcher le daily à chaque trade).
Leçon mémoire marché: BTC 2025 -7%, 2026 -25% -> le daily filtre les achats contre-tendance.

Plugin auto-chargé par paper_trading. Safe-fallback: autorise si erreur."""
import time

_CACHE = {}            # symbole -> (timestamp, tendance)
_CACHE_TTL = 3600      # 1h


def _ema(values, period):
    """EMA sur les `period` dernières valeurs."""
    vals = values[-period:] if len(values) >= period else values
    if not vals:
        return 0.0
    k = 2.0 / (period + 1)
    ema = float(vals[0])
    for v in vals[1:]:
        ema = float(v) * k + ema * (1 - k)
    return ema


def _tendance_daily(symbole):
    """Retourne 'hausse'/'neutre'/'baisse_moyenne'/'baisse_forte' sur le daily."""
    now = time.time()
    cached = _CACHE.get(symbole)
    if cached and now - cached[0] < _CACHE_TTL:
        return cached[1]
    tend = "neutre"
    try:
        from indicateurs import historique_ohlcv
        bougies = historique_ohlcv(symbole, "1d", 60)
        closes = [b["cloture"] for b in bougies if b.get("cloture")]
        if len(closes) >= 30:
            ema20 = _ema(closes, 20)
            ema50 = _ema(closes, 50)
            prix = float(closes[-1])
            if ema20 > ema50 and prix > ema20:
                tend = "hausse"
            elif ema20 < ema50 and prix < ema50:
                tend = "baisse_forte"
            elif ema20 < ema50:
                tend = "baisse_moyenne"
            else:
                tend = "neutre"
    except Exception:
        tend = "neutre"
    _CACHE[symbole] = (now, tend)
    return tend


def hook_entree(pf, signal):
    """Veto d'entrée: bloque les achats en tendance daily baissière forte."""
    try:
        sym = signal.get("symbole") if isinstance(signal, dict) else None
        if not sym:
            return (True, "sans_symbole")
        tend = _tendance_daily(sym)
        if tend == "baisse_forte":
            return (False, "contre-tendance daily (bear fort)")
        return (True, f"daily {tend}")
    except Exception:
        return (True, "safe_fallback")


def hook_sizing(pf, signal, montant, prix_actuel):
    """Réduction de taille selon l'alignement de la tendance daily."""
    try:
        sym = signal.get("symbole") if isinstance(signal, dict) else None
        base = float(montant) if montant else 0.0
        if not sym:
            return base
        tend = _tendance_daily(sym)
        facteur = {"hausse": 1.0, "neutre": 0.85,
                   "baisse_moyenne": 0.60, "baisse_forte": 0.0}.get(tend, 1.0)
        return max(0.0, base * facteur)
    except Exception:
        return float(montant) if montant else 0.0


def self_test():
    try:
        assert _ema([1, 2, 3, 4, 5, 6, 7, 8], 3) > 0
        # Tendance sur un symbole crypto connu (réseau; neutre acceptable si indispo)
        t = _tendance_daily("BTCEUR")
        assert t in ("hausse", "neutre", "baisse_moyenne", "baisse_forte"), t
        allow, r = hook_entree({}, {"symbole": "BTCEUR"})
        assert isinstance(allow, bool) and isinstance(r, str)
        s = hook_sizing({}, {"symbole": "BTCEUR"}, 200.0, 100.0)
        assert 0 <= s <= 200.0
        # Sans symbole -> autorise
        allow2, _ = hook_entree({}, {})
        assert allow2 is True
        return True
    except Exception:
        return False


if __name__ == "__main__":
    print("=" * 60)
    print("FILTRE MULTI-TEMPOREL (tendance journalière)")
    print("=" * 60)
    for sym in ("BTCEUR", "ETHEUR", "AAPL", "NVDA"):
        t = _tendance_daily(sym)
        allow, r = hook_entree({}, {"symbole": sym})
        mult = {"hausse": 1.0, "neutre": 0.85, "baisse_moyenne": 0.60,
                "baisse_forte": 0.0}.get(t, 1.0)
        print(f"  {sym:8s} daily={t:16s} entrée={'BLOQUÉ' if not allow else 'OK':4s} sizing x{mult:.2f}")
    print(f"\nself_test: {'OK' if self_test() else 'ÉCHEC'}")
