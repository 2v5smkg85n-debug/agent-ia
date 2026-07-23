#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""patch_notif_trade.py — notifie Telegram à chaque ouverture de position.

Quand une stratégie ouvre une position (via ouvrir_position), envoie un message
Telegram avec: stratégie, actif, prix, montant, conviction multiplier, raison.
L'utilisateur sait immédiatement quand le système suit une stratégie et ouvre.

Idempotent: skip si 'tg_envoyer' déjà présent.
"""
import os

P = os.path.join(os.path.dirname(os.path.abspath(__file__)), "paper_trading.py")
src = open(P).read()
edits = 0

ancien = (
    '    print(f"  [ACHAT] {signal.get(\'nom\',signal[\'symbole\'])} ({signal.get(\'marche\',\'?\')}) @ {prix_actuel:.2f} | {montant:.2f} EUR | qty {quantite:.6f}")\n'
    '    notify_ifft("Paper Trade ACHAT", f"Achat {signal.get(\'nom\',\'?\')} @ {prix_actuel:.2f} EUR")'
)
nouveau = (
    '    print(f"  [ACHAT] {signal.get(\'nom\',signal[\'symbole\'])} ({signal.get(\'marche\',\'?\')}) @ {prix_actuel:.2f} | {montant:.2f} EUR | qty {quantite:.6f}")\n'
    '    # Notif Telegram: prévient qu\'une stratégie a ouvert une position\n'
    '    try:\n'
    '        from telegram_alerte import envoyer as _tg_envoyer\n'
    '        _conv = ""\n'
    '        try:\n'
    '            if _mult and _mult != 1.0:\n'
    '                _conv = f" (conviction x{_mult:.2f})"\n'
    '        except Exception:\n'
    '            pass\n'
    '        _tg_envoyer(f"📈 Position ouverte{_conv}\\n"\n'
    '                    f"Stratégie: {position.get(\'strategie\', \'?\')}\\n"\n'
    '                    f"Actif: {position[\'nom\']} ({position.get(\'marche\',\'?\')})\\n"\n'
    '                    f"Prix: {prix_actuel:.2f} | Montant: {montant:.2f} EUR\\n"\n'
    '                    f"Raison: {signal.get(\'raison\', \'\')}")\n'
    '    except Exception:\n'
    '        pass\n'
    '    notify_ifft("Paper Trade ACHAT", f"Achat {signal.get(\'nom\',\'?\')} @ {prix_actuel:.2f} EUR")'
)
if ancien in src and "_tg_envoyer" not in src:
    src = src.replace(ancien, nouveau)
    edits += 1
    print("[paper] notif Telegram ajoutée à l'ouverture de position")
else:
    print("[paper] ancre introuvable ou déjà appliqué")

open(P, "w").write(src)
print(f"\n=== NOTIF TRADE APPLIQUÉE ===  ({edits} edits)")
print("Telegram envoyé à chaque ouverture de position (stratégie + actif + prix + conviction)")
