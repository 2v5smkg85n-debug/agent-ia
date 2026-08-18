import json, sys
pf = json.load(open('paper_trading.json'))
print('Liquidites:', pf['liquidites'])
print('Capital initial:', pf['capital_initial'])
print('Positions ouvertes:')
for p in pf['positions']:
    print(' ', p['symbole'], 'entree:', p['prix_entree'], 'montant:', p['montant_eur'])
print('Trades fermes:', len(pf.get('trades_fermes', [])))
print()
import prix_revolut as pr
for p in pf['positions']:
    sym = p['symbole']
    prix = pr.get_prix_revolut(sym)
    print(sym, 'prix Revolut X:', prix, 'EUR | entree:', p['prix_entree'])
