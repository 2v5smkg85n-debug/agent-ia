import json, copy
from datetime import datetime

pf = json.load(open('paper_trading.json'))
print("=== ETAT ACTUEL (CORROMPU) ===")
print("Liquidites:", round(pf['liquidites'], 2), "EUR")
print("Positions ouvertes:", len(pf['positions']))
print("Trades fermes:", len(pf.get('trades_fermes', [])))
print()

# Trouver les trades fermes apres le deploiement Revolut X (16:00 le 18 aout)
trades = pf.get('trades_fermes', [])
trades_a_supprimer = []
for i, t in enumerate(trades):
    date_str = t.get('date_fermeture', '')
    # Les trades fermes apres 16:00 le 18 aout sont suspects
    if '2026-08-18 16:' in date_str or '2026-08-18 17:' in date_str or '2026-08-18 18:' in date_str:
        trades_a_supprimer.append(i)
        print("Trade suspect:", t.get('symbole'), 'gain:', t.get('gain_eur', 0), 'date:', date_str, 'raison:', t.get('raison', ''))

print()
print("Trades suspects a supprimer:", len(trades_a_supprimer))

# Recalculer les liquidites depuis zero
# Commencer avec le capital initial
# Pour chaque trade ferme: ajouter le gain_eur + montant - montant (complique)
# Plus simple: refaire le calcul a partir du dernier etat correct connu

# Le dernier etat correct (avant Revolut X): liq=889.69, 1 position LDO, 39 trades
# Si on supprime les trades suspects, on doit aussi restaurer les positions fermees

# Recalculer: partir de 1000, soustraire chaque ouverture de position, ajouter chaque fermeture
liq = pf['capital_initial']
positions_actives = []
total_frais = 0.0

# Reconstruire l'historique depuis le debut
for trade in trades:
    if trades.index(trade) in trades_a_supprimer:
        # Ce trade ne s'est pas reellement ferme a ce prix - restaurer la position
        positions_actives.append({
            'symbole': trade['symbole'],
            'nom': trade.get('nom', ''),
            'marche': trade.get('marche', 'crypto'),
            'prix_entree': trade['prix_entree'],
            'quantite': trade['quantite'],
            'montant_eur': trade['montant_eur'],
            'frais_entree': trade.get('frais_entree', trade['montant_eur'] * 0.001),
            'date_ouverture': trade.get('date_ouverture', ''),
            'signal_raison': trade.get('signal_raison', ''),
            'source': trade.get('source', ''),
            'strategie': trade.get('strategie', ''),
            'prix_peak': trade['prix_entree'],
            'tp_adaptatif': 3.0,
            'sl_adaptatif': 1.5,
        })
        # Ne pas ajouter le gain ni les frais de fermeture
        continue
    # Trade legit: fermer la position
    # Le gain_eur inclut deja les frais
    gain = float(trade.get('gain_eur', 0))
    montant = float(trade.get('montant_eur', 0))
    frais = float(trade.get('frais_total', 0))
    # Quand une position se ferme, on recupere montant + gain
    liq += montant + gain
    total_frais += frais
    # Retirer de positions actives
    positions_actives = [p for p in positions_actives if p['symbole'] != trade['symbole']]

# Pour les positions encore ouvertes, soustraire leur montant des liquidites
for p in positions_actives:
    liq -= float(p['montant_eur'])
    total_frais += float(p.get('frais_entree', 0))

print()
print("=== ETAT CORRIGE ===")
print("Liquidites:", round(liq, 2), "EUR")
print("Positions ouvertes:", len(positions_actives))
for p in positions_actives:
    print("  ", p['symbole'], 'entree:', p['prix_entree'], 'montant:', p['montant_eur'])
print("Trades fermes valides:", len(trades) - len(trades_a_supprimer))
print("Frais total:", round(total_frais, 2))
print("Capital total:", round(liq + sum(float(p['montant_eur']) for p in positions_actives), 2))

# Sauvegarder
pf_corrige = copy.deepcopy(pf)
pf_corrige['liquidites'] = round(liq, 2)
pf_corrige['positions'] = positions_actives
pf_corrige['total_frais'] = round(total_frais, 2)
# Supprimer les trades suspects
nouveaux_trades = [t for i, t in enumerate(trades) if i not in trades_a_supprimer]
pf_corrige['trades_fermes'] = nouveaux_trades

# Backup
with open('paper_trading_backup.json', 'w') as f:
    json.dump(pf, f, ensure_ascii=False, indent=2)
print()
print("Backup sauvegarde: paper_trading_backup.json")

# Sauvegarder le corrige
with open('paper_trading.json', 'w') as f:
    json.dump(pf_corrige, f, ensure_ascii=False, indent=2)
print("Portefeuille corrige sauvegarde: paper_trading.json")
