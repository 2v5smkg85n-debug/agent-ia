#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""patch_plugins_system.py — Système de plugins pour l'auto-évolution autonome.

L'agent (méta-evolver) peut déposer des modules validés dans plugins/ et ils sont
auto-chargés par paper_trading. Chaque plugin peut définir:
  - hook_entree(pf, signal) -> (allow_bool, raison)   # veto d'entrée
  - hook_sizing(pf, signal, montant, prix) -> montant  # ajuste la taille

SÉCURITÉ:
  - Additions seulement (nouveau fichier dans plugins/), JAMAIS de modification
    du code core. C'est la frontière de sécurité.
  - Plugins validés par le méta-evolver (3 gates: syntaxe + sécurité + self_test).
  - Chaque hook est wrappé try/except (un plugin bugué ne casse pas le système).
  - montant clamped [0, liquidites] après les hooks de sizing.
  - Toggle global: PLUGINS_ACTIVE=0 désactive tout chargement de plugins.
  - _charger_plugins() idempotent (charge une fois par session)."""
import sys

f = "paper_trading.py"
p = open(f, encoding="utf-8").read()

# --- Edit 1: loader de plugins avant ouvrir_position ---
A1 = '''def ouvrir_position(pf, signal, prix_actuel):
    if len(pf["positions"]) >= MAX_POSITIONS:
        return False'''

B1 = '''# ============================================
# PLUGINS (méta-évolution autonome): modules auto-chargés depuis plugins/
# L'agent dépose des modules validés -> intégration automatique sans toucher
# au code core. Hooks: hook_entree (veto) + hook_sizing (ajuste taille).
# Toggle: PLUGINS_ACTIVE=0. Hooks wrappés try/except (safe).
_plugins_charges = []
def _charger_plugins():
    """Charge une fois les modules de plugins/ (idempotent)."""
    global _plugins_charges
    if _plugins_charges:
        return
    if os.getenv("PLUGINS_ACTIVE", "1") == "0":  # désactivé
        return
    pdir = os.path.join(os.path.dirname(os.path.abspath(__file__)), "plugins")
    if not os.path.isdir(pdir):
        return
    import importlib.util
    _parent = os.path.dirname(pdir)
    if _parent not in sys.path:
        sys.path.insert(0, _parent)
    for fn in sorted(os.listdir(pdir)):
        if not fn.endswith(".py") or fn.startswith("_"):
            continue
        try:
            spec = importlib.util.spec_from_file_location("plugin_" + fn[:-3],
                                                          os.path.join(pdir, fn))
            mod = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(mod)
            _plugins_charges.append((fn, mod))
        except Exception as _e:
            print(f"  [PLUGIN] {fn} erreur chargement: {_e}")


def ouvrir_position(pf, signal, prix_actuel):
    if len(pf["positions"]) >= MAX_POSITIONS:
        return False'''

# --- Edit 2: hooks d'entrée après circuit breaker, avant sizing ---
A2 = '''        except Exception:
            pass
    # SIZING DYNAMIQUE (Phase 2): remplace le 20% fixe par Kelly fractionnaire'''

B2 = '''        except Exception:
            pass
    # PLUGINS (méta-évolution): hooks d'entrée (veto). Toggle: PLUGINS_ACTIVE=0.
    if os.getenv("PLUGINS_ACTIVE", "1") != "0":
        try:
            _charger_plugins()
            for _fn, _mod in _plugins_charges:
                if hasattr(_mod, "hook_entree"):
                    try:
                        _allow, _raison = _mod.hook_entree(pf, signal)
                        if not _allow:
                            print(f"  [PLUGIN {_fn}] entrée bloquée: {_raison}")
                            return False
                    except Exception as _e:
                        print(f"  [PLUGIN {_fn}] hook_entree erreur: {_e}")
        except Exception:
            pass
    # SIZING DYNAMIQUE (Phase 2): remplace le 20% fixe par Kelly fractionnaire'''

# --- Edit 3: hooks de sizing après sentiment, clamp de sécurité ---
A3 = '''            print(f"  [SENTIMENT erreur {_e}] taille inchangée")
    if montant < 5:
        return False'''

B3 = '''            print(f"  [SENTIMENT erreur {_e}] taille inchangée")
    # PLUGINS (méta-évolution): hooks de sizing (ajustent la taille).
    if os.getenv("PLUGINS_ACTIVE", "1") != "0":
        try:
            for _fn, _mod in _plugins_charges:
                if hasattr(_mod, "hook_sizing"):
                    try:
                        _avant = montant
                        montant = _mod.hook_sizing(pf, signal, montant, prix_actuel)
                        if montant != _avant:
                            print(f"  [PLUGIN {_fn}] sizing {_avant:.0f}->{montant:.0f}EUR")
                    except Exception as _e:
                        print(f"  [PLUGIN {_fn}] hook_sizing erreur: {_e}")
        except Exception:
            pass
    # Clamp de sécurité: un plugin bugué ne peut pas dépasser le liquide ni aller négatif
    montant = max(0, min(montant, pf["liquidites"]))
    if montant < 5:
        return False'''

ok = True
if "_charger_plugins" in p:
    print("[paper] plugins déjà présents - skip edit1")
elif A1 in p:
    p = p.replace(A1, B1, 1); print("[paper] edit1: loader plugins ajouté")
else:
    print("[paper] ERREUR ancre edit1"); ok = False

if A2 in p:
    p = p.replace(A2, B2, 1); print("[paper] edit2: hooks d'entrée ajoutés")
else:
    print("[paper] ERREUR ancre edit2"); ok = False

if A3 in p:
    p = p.replace(A3, B3, 1); print("[paper] edit3: hooks de sizing + clamp ajoutés")
else:
    print("[paper] ERREUR ancre edit3"); ok = False

if not ok:
    sys.exit(1)
open(f, "w", encoding="utf-8").write(p)
print("\n=== SYSTÈME DE PLUGINS APPLIQUÉ ===")
print("L'agent peut maintenant déposer des modules dans plugins/ -> auto-chargés")
