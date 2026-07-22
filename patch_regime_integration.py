#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""patch_regime_integration.py — Intègre le module filtre_regime_vol_corr (généré
par le méta-evolver) dans ouvrir_position de paper_trading.py.

Après le sizing (gestion_risque.calculer_taille) et le cap liquidités, ajuste la
taille selon le régime de marché détecté:
  - risk_off_contagion (crash) -> ×0.25
  - mean_reversion             -> ×0.55
  - mixed                      -> ×0.75
  - high_momentum              -> ×1.00
  - calm                       -> ×0.90
+ multiplicateur de risque supplémentaire (floor ×0.10).

DÉSACTIVABLE: REGIME_FILTER=0 dans l'env -> sizing inchangé (comportement d'avant).
Fallback gracieux: si le module absent ou fetch échoue -> taille inchangée.
Aucun blocage: ne réduit que la taille, n'empêche jamais un signal (floor 10%)."""
import sys

f = "paper_trading.py"
p = open(f, encoding="utf-8").read()

OLD = '''    # Plafonne au liquide dispo
    montant = min(montant, pf["liquidites"])
    if montant < 5:
        return False'''

NEW = '''    # Plafonne au liquide dispo
    montant = min(montant, pf["liquidites"])
    # FILTRE RÉGIME (méta-évolution): ajuste la taille selon le régime de marché.
    # En contagion baissière (crash), réduit la taille (floor ×0.10). Désactivable: REGIME_FILTER=0.
    if os.getenv("REGIME_FILTER", "1") != "0":
        try:
            from filtre_regime_vol_corr import ajuster_exposition
            from indicateurs import historique_ohlcv
            _sym = signal["symbole"]
            _is_crypto = signal.get("marche") == "crypto"
            _peer = "BTCUSDT" if _is_crypto and _sym != "BTCUSDT" else None
            _prices = [b["cloture"] for b in historique_ohlcv(_sym, "1h", 30) if b.get("cloture")]
            _peer_prices = None
            if _peer:
                _peer_prices = [b["cloture"] for b in historique_ohlcv(_peer, "1h", 30) if b.get("cloture")]
            if len(_prices) >= 5:
                _avant = montant
                montant, _meta = ajuster_exposition(montant, _prices, prices_peer=_peer_prices, window=20)
                if montant < _avant:
                    print(f"  [RÉGIME] {signal.get('nom', _sym)}: {_meta['regime']} risk={_meta['risk_score']:.2f} -> x{_meta['multiplier']:.2f} ({_avant:.0f}->{montant:.0f}EUR)")
        except ImportError:
            pass  # module filtre_regime absent -> sizing inchangé
        except Exception as _e:
            print(f"  [RÉGIME erreur {_e}] taille inchangée")
    if montant < 5:
        return False'''

if "from filtre_regime_vol_corr import ajuster_exposition" in p:
    print("[paper] intégration régime déjà présente - skip")
elif OLD in p:
    p = p.replace(OLD, NEW, 1)
    print("[paper] filtre régime intégré dans ouvrir_position")
else:
    print("[paper] ERREUR ancre ouvrir_position introuvable"); sys.exit(1)

open(f, "w", encoding="utf-8").write(p)
print("\n=== PATCH INTÉGRATION RÉGIME APPLIQUE ===")
print("Module: filtre_regime_vol_corr.py (généré par le méta-evolver)")
print("Toggle: REGIME_FILTER=0 pour désactiver | Fallback gracieux si module absent")
