#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""patch_conviction_sizing.py — sizing par conviction (performance live).

Amplifie les stratégies gagnantes éprouvées en live: x1.5 si >=5 trades et
>=70% win et pnl>0, x1.25 si >=3 trades et >=60% win et pnl>0, x0.5 si perdante
(>=3 trades, pnl<0), x1.0 sinon (neutre/neuf). Utilise la boucle d'apprentissage
du système (classement_strategies.json) pour parier plus gros sur ce qui marche.

Toggle: CONVICTION_SIZING=0.
Idempotent: skip si _conviction_mult déjà présent.
"""
import os

P = os.path.join(os.path.dirname(os.path.abspath(__file__)), "paper_trading.py")
src = open(P).read()
edits = 0

# --- Edit 1: fonction _conviction_mult (avant ouvrir_position) ---
if "def _conviction_mult" not in src:
    func = (
        'def _conviction_mult(signal, cs):\n'
        '    """Multiplicateur de conviction basé sur la performance LIVE de la stratégie.\n'
        '    x1.5 éprouvé (>=5t, >=70% win, pnl>0) | x1.25 solide (>=3t, >=60%, pnl>0)\n'
        '    x0.5 faible (>=3t, pnl<0) | x1.0 neuf/neutre."""\n'
        '    _sym = signal.get("symbole", "")\n'
        '    _nom = signal.get("nom", signal.get("strategie", ""))\n'
        '    _entry = cs.get(_sym) or cs.get(_sym.upper()) or cs.get(_sym.lower()) or {}\n'
        '    for _s in _entry.get("strategies", []):\n'
        '        if _s.get("strategie", "") == _nom:\n'
        '            _n = _s.get("live_n", 0); _wr = _s.get("live_wr", 0); _pnl = _s.get("live_pnl", 0)\n'
        '            if _n >= 5 and _wr >= 70 and _pnl > 0:\n'
        '                return 1.5, f"éprouvé ({_n}t {_wr:.0f}% +{_pnl:.2f}€)"\n'
        '            if _n >= 3 and _wr >= 60 and _pnl > 0:\n'
        '                return 1.25, f"solide ({_n}t {_wr:.0f}% +{_pnl:.2f}€)"\n'
        '            if _n >= 3 and _pnl < 0:\n'
        '                return 0.5, f"faible ({_n}t {_wr:.0f}% {_pnl:+.2f}€)"\n'
        '            return 1.0, f"neutre (n={_n})"\n'
        '    return 1.0, "nouveau"\n\n\n'
    )
    src = src.replace("def ouvrir_position(pf, signal, prix_actuel):", func + "def ouvrir_position(pf, signal, prix_actuel):")
    edits += 1
    print("[paper] edit1: fonction _conviction_mult()")

# --- Edit 2: bloc conviction dans le flow de sizing (après sentiment, avant plugins) ---
ancien = (
    '        except Exception as _e:\n'
    '            print(f"  [SENTIMENT erreur {_e}] taille inchangée")\n'
    '    # PLUGINS (méta-évolution): hooks de sizing (ajustent la taille).'
)
nouveau = (
    '        except Exception as _e:\n'
    '            print(f"  [SENTIMENT erreur {_e}] taille inchangée")\n'
    '    # CONVICTION SIZING: amplifie les stratégies gagnantes éprouvées en live\n'
    '    # (plus de bénéfices/trade sur ce qui marche déjà). Désactivable: CONVICTION_SIZING=0.\n'
    '    if os.getenv("CONVICTION_SIZING", "1") != "0":\n'
    '        try:\n'
    '            _cs = json.load(open("classement_strategies.json"))\n'
    '            _mult, _craison = _conviction_mult(signal, _cs)\n'
    '            if _mult != 1.0:\n'
    '                _avant = montant\n'
    '                montant = montant * _mult\n'
    '                print(f"  [CONVICTION] {signal.get(\'nom\', signal[\'symbole\'])}: x{_mult:.2f} {_craison} ({_avant:.0f}->{montant:.0f}EUR)")\n'
    '        except FileNotFoundError:\n'
    '            pass  # classement pas encore créé -> sizing par défaut\n'
    '        except Exception as _e:\n'
    '            print(f"  [CONVICTION erreur {_e}] taille inchangée")\n'
    '    # PLUGINS (méta-évolution): hooks de sizing (ajustent la taille).'
)
if ancien in src and "CONVICTION SIZING" not in src:
    src = src.replace(ancien, nouveau)
    edits += 1
    print("[paper] edit2: bloc conviction sizing dans le flow")

open(P, "w").write(src)
print(f"\n=== CONVICTION SIZING APPLIQUÉ ===  ({edits} edits)")
print("x1.5 éprouvé | x1.25 solide | x0.5 faible | x1.0 neuf/neutre | Toggle CONVICTION_SIZING=0")
