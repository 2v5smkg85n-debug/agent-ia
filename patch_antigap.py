#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""patch_antigap.py - garde anti-gap week-end (marches non-crypto).

Probleme B: Or tenu 68h, -1.92e. Le forex ferme le week-end -> le SL ne peut
pas se declencher pendant la fermeture, et un gap a la reouverture peut
overshooter le SL. L'exit stack actuel (stale 3h) ferme les positions
lun-jeudi avant le week-end, MAIS une entree du vendredi n'a pas le temps de
se fermer avant 22:00 UTC.

Solution: bloque les entrees non-crypto le vendredi + week-end. Crypto 24/7
= pas de gap = non concerne. Idempotent.

Fonction _entree_bloquee_weekend() separee -> testable directement.
"""
import os

P = os.path.join(os.path.dirname(os.path.abspath(__file__)), "paper_trading.py")
src = open(P).read()
edits = 0

# --- Edit 1: fonction helper avant ouvrir_position ---
FN = [
'def _entree_bloquee_weekend(signal, maintenant=None):',
'    """True si lentree est bloquee pour eviter le gap week-end (non-crypto, ven->week-end).',
'    Le forex/indices/matieres ferment le week-end -> gap possible a la reouverture',
'    qui peut overshooter le SL (cf. Or tenu 68h, -1.92EUR). Crypto 24/7 = non concerne."""',
'    if signal.get("marche") == "crypto":',
'        return False',
'    maintenant = maintenant or datetime.now()',
'    _jour = maintenant.weekday()  # 0=lun ... 4=ven, 5=sam, 6=dim',
'    return _jour == 4 or _jour >= 5',
'',
'',
]
fn = "\n".join(FN)
ancien = "def ouvrir_position(pf, signal, prix_actuel):"
if "_entree_bloquee_weekend" not in src:
    src = src.replace(ancien, fn + ancien, 1)
    edits += 1
    print("[paper] edit1: fonction _entree_bloquee_weekend ajoutee")

# --- Edit 2: garde dans ouvrir_position, juste apres la garde ANTI-CORR ---
# On ancre sur la fin du bloc anti-corr (le 'except Exception:\n            pass' qui suit ANTI-CORR)
ancien_garde = (
    '                        return False\n'
    '                except Exception:\n'
    '                    pass\n'
    '        except Exception:\n'
    '            pass'
)
nouveau_garde = (
    '                        return False\n'
    '                except Exception:\n'
    '                    pass\n'
    '        except Exception:\n'
    '            pass\n'
    '    # ANTI-GAP WEEK-END: bloque les entrees non-crypto le vendredi + week-end.\n'
    '    # Ces marches ferment le week-end -> un gap a la reouverture peut overshooter\n'
    '    # le SL (cf. Or tenu 68h, -1.92EUR). L exit stack (stale 3h) ferme les positions\n'
    '    # lun-jeudi avant le week-end, mais une entree vendredi n a pas le temps.\n'
    '    if os.getenv("ANTI_GAP_WEEKEND", "1") != "0":\n'
    '        try:\n'
    '            if _entree_bloquee_weekend(signal):\n'
    '                print(f"  [ANTI-GAP] {signal.get(\'nom\',signal.get(\'symbole\',\'?\'))} ({signal.get(\'marche\',\'?\')}): entree bloquee (week-end, risque de gap)")\n'
    '                return False\n'
    '        except Exception:\n'
    '            pass'
)
# ancre ambigu (plusieurs 'except Exception: pass') -> on cible le bloc ANTI-CORR precis
# en verifiant que le contexte ANTI-CORR est juste au-dessus. On utilise un ancrage plus long.
ancien_garde2 = (
    '                        print(f"  [ANTI-CORR] {signal.get(\'nom\',_sym)}: actif déjà ouvert ({_age:.0f}min<{FENETRE_CORRELATION_MIN}min) -> entrée bloquée (évite double-exposition corrélée)")\n'
    '                        return False\n'
    '                except Exception:\n'
    '                    pass\n'
    '        except Exception:\n'
    '            pass'
)
nouveau_garde2 = (
    '                        print(f"  [ANTI-CORR] {signal.get(\'nom\',_sym)}: actif déjà ouvert ({_age:.0f}min<{FENETRE_CORRELATION_MIN}min) -> entrée bloquée (évite double-exposition corrélée)")\n'
    '                        return False\n'
    '                except Exception:\n'
    '                    pass\n'
    '        except Exception:\n'
    '            pass\n'
    '    # ANTI-GAP WEEK-END: bloque les entrees non-crypto le vendredi + week-end.\n'
    '    # Ces marches ferment le week-end -> un gap a la reouverture peut overshooter\n'
    '    # le SL (cf. Or tenu 68h, -1.92EUR). L exit stack (stale 3h) ferme les positions\n'
    '    # lun-jeudi avant le week-end, mais une entree vendredi n a pas le temps.\n'
    '    if os.getenv("ANTI_GAP_WEEKEND", "1") != "0":\n'
    '        try:\n'
    '            if _entree_bloquee_weekend(signal):\n'
    '                print(f"  [ANTI-GAP] {signal.get(\'nom\',signal.get(\'symbole\',\'?\'))} ({signal.get(\'marche\',\'?\')}): entree bloquee (week-end, risque de gap)")\n'
    '                return False\n'
    '        except Exception:\n'
    '            pass'
)
if "ANTI-GAP" not in src and ancien_garde2 in src:
    src = src.replace(ancien_garde2, nouveau_garde2, 1)
    edits += 1
    print("[paper] edit2: garde ANTI-GAP ajoutee apres ANTI-CORR")
else:
    print("[paper] edit2: SKIP (deja patche ou ancre ANTI-CORR introuvable)")

open(P, "w").write(src)
print(f"\n=== ANTI-GAP APPLIQUE ===  ({edits} edits)")
