#!/usr/bin/env python3
"""Reset le portefeuille a 1000 EUR. Garde l'apprentissage (learning_trader.json)."""
import json

pf = json.load(open('paper_trading.json'))
pf['pertes_consecutives'] = 0
pf['trades_fermes'] = []
pf['historique'] = []
pf['total_frais'] = 0
pf['liquidites'] = 1000.0
pf['positions'] = []
pf['capital_initial'] = 1000.0
json.dump(pf, open('paper_trading.json', 'w'), ensure_ascii=False, indent=2)
print('Reset OK — 1000 EUR, 0 positions, apprentissage conserve')
