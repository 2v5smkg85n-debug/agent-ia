#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""patch_plugins_reload.py — Rend le loader de plugins mtime-aware: recharge
automatiquement quand le contenu de plugins/ change, pour que les nouveaux
plugins du méta-evolver soient actifs SANS restart de paper_trading."""
import sys

f = "paper_trading.py"
p = open(f, encoding="utf-8").read()
ok = True

# Edit 1: ajouter _plugins_sig
A1 = '_plugins_charges = []\ndef _charger_plugins():'
B1 = '_plugins_charges = []\n_plugins_sig = None\ndef _charger_plugins():'

# Edit 2: header mtime-aware (remplace le cache-forever)
A2 = '    """Charge une fois les modules de plugins/ (idempotent)."""\n    global _plugins_charges\n    if _plugins_charges:\n        return'
B2 = ('    """Charge les modules de plugins/. Recharge si le set change (actif SANS restart)."""\n'
      '    global _plugins_charges, _plugins_sig')

# Edit 3: signature mtime + boucle sur fichiers
A3 = ('    for fn in sorted(os.listdir(pdir)):\n'
      '        if not fn.endswith(".py") or fn.startswith("_"):\n'
      '            continue')
B3 = ('    try:\n'
      '        fichiers = sorted(f for f in os.listdir(pdir) if f.endswith(".py") and not f.startswith("_"))\n'
      '        sig = tuple((f, os.path.getmtime(os.path.join(pdir, f))) for f in fichiers)\n'
      '    except Exception:\n'
      '        return\n'
      '    if _plugins_sig == sig and _plugins_charges:\n'
      '        return  # inchangé\n'
      '    _plugins_sig = sig\n'
      '    _plugins_charges = []\n'
      '    for fn in fichiers:')

# Edit 4: log de chargement
A4 = '            _plugins_charges.append((fn, mod))\n        except Exception as _e:'
B4 = '            _plugins_charges.append((fn, mod))\n            print(f"  [PLUGIN] {fn} chargé")\n        except Exception as _e:'

if "_plugins_sig" in p:
    print("[paper] mtime-aware déjà présent - skip"); sys.exit(0)
for i, (a, b) in enumerate([(A1,B1),(A2,B2),(A3,B3),(A4,B4)], 1):
    if a in p:
        p = p.replace(a, b, 1); print(f"[paper] edit{i} ok")
    else:
        print(f"[paper] ERREUR ancre edit{i}"); ok = False
if not ok:
    sys.exit(1)
open(f, "w", encoding="utf-8").write(p)
print("\n=== LOADER PLUGINS MTIME-AWARE ===")
print("Recharge auto quand plugins/ change -> nouveaux plugins actifs sans restart")
