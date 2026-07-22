#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""patch_sentiment_integration.py — Intègre sentiment_multiplier() dans ouvrir_position,
après le filtre régime. Sizing contrarian: achète plein en Extreme Fear, réduit en Greed.
Crypto uniquement (Fear & Greed = index crypto). Compose avec le filtre régime:
montant = base × régime × sentiment. Désactivable: SENTIMENT_FILTER=0. Fallback gracieux."""
import sys

f = "paper_trading.py"
p = open(f, encoding="utf-8").read()

ANCHOR = '''        except Exception as _e:
            print(f"  [RÉGIME erreur {_e}] taille inchangée")
    if montant < 5:
        return False'''

NEW = '''        except Exception as _e:
            print(f"  [RÉGIME erreur {_e}] taille inchangée")
    # FILTRE SENTIMENT (Fear & Greed): sizing contrarian, crypto uniquement.
    # Achète plein en Extreme Fear (zone achat), réduit en Greed (euphorie = risque).
    # Compose avec le filtre régime: montant = base × régime × sentiment.
    # Désactivable: SENTIMENT_FILTER=0.
    if os.getenv("SENTIMENT_FILTER", "1") != "0" and signal.get("marche") == "crypto":
        try:
            from sentiment_marche import sentiment_multiplier
            _smult, _sclass = sentiment_multiplier()
            if _smult < 1.0:
                _avant = montant
                montant = montant * _smult
                print(f"  [SENTIMENT] {_sclass} -> x{_smult:.2f} ({_avant:.0f}->{montant:.0f}EUR)")
        except ImportError:
            pass  # module sentiment absent -> sizing inchangé
        except Exception as _e:
            print(f"  [SENTIMENT erreur {_e}] taille inchangée")
    if montant < 5:
        return False'''

if "from sentiment_marche import sentiment_multiplier" in p:
    print("[paper] intégration sentiment déjà présente - skip")
elif ANCHOR in p:
    p = p.replace(ANCHOR, NEW, 1)
    print("[paper] filtre sentiment intégré dans ouvrir_position (après régime)")
else:
    print("[paper] ERREUR ancre régime/if montant introuvable"); sys.exit(1)

open(f, "w", encoding="utf-8").write(p)
print("\n=== PATCH INTÉGRATION SENTIMENT APPLIQUE ===")
print("Sizing final: base × régime × sentiment | Toggle: SENTIMENT_FILTER=0 | Crypto only")
