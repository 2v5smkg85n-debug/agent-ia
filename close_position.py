import json, sys, time
sys.path.insert(0, '/home/ubuntu/agent-ia')
import prix_revolut as pr

pf = json.load(open('paper_trading.json'))

print("=== FERMETURE MANUELLE ===")
print("Positions ouvertes:")
for p in pf['positions']:
    print("  " + p['symbole'] + " entree: " + str(p['prix_entree']) + " montant: " + str(p['montant_eur']) + " EUR")

if not pf['positions']:
    print("Aucune position a fermer.")
    sys.exit(0)

# Prix actuel via Revolut X
for p in pf['positions']:
    sym = p['symbole']
    prix_actuel = pr.get_prix_revolut(sym)
    if prix_actuel <= 0:
        print("Erreur: prix Revolut X indisponible pour " + sym)
        continue

    qty = float(p['quantite'])
    montant = float(p['montant_eur'])
    prix_entree = float(p['prix_entree'])
    frais = montant * 0.001

    valeur = qty * prix_actuel
    gain = valeur - montant - frais

    print()
    print("Fermeture " + sym + ":")
    print("  Prix entree: " + str(prix_entree))
    print("  Prix actuel: " + str(prix_actuel))
    print("  Quantite: " + str(qty))
    print("  Valeur: " + str(round(valeur, 2)) + " EUR")
    print("  Frais: " + str(round(frais, 2)) + " EUR")
    print("  Gain/Perte: " + str(round(gain, 2)) + " EUR")

    # Mettre a jour les liquidites
    pf['liquidites'] += valeur - frais
    pf['total_frais'] = pf.get('total_frais', 0) + frais

    # Ajouter au trades fermes
    trade = {
        'symbole': sym,
        'nom': p.get('nom', ''),
        'marche': p.get('marche', 'crypto'),
        'prix_entree': prix_entree,
        'prix_sortie': prix_actuel,
        'quantite': qty,
        'montant_eur': montant,
        'gain_eur': round(gain, 4),
        'variation_pct': round((prix_actuel - prix_entree) / prix_entree * 100, 2),
        'raison': 'FERMETURE MANUELLE',
        'signal_raison': p.get('signal_raison', ''),
        'strategie': p.get('strategie', ''),
        'source': p.get('source', 'binance'),
        'frais_total': round(frais, 4),
        'date_ouverture': p.get('date_ouverture', ''),
        'date_fermeture': time.strftime('%Y-%m-%d %H:%M'),
    }
    pf.setdefault('trades_fermes', []).append(trade)

# Vider les positions
pf['positions'] = []
pf['dernier_tick'] = time.strftime('%Y-%m-%d %H:%M')

# Sauvegarder
with open('paper_trading.json', 'w') as f:
    json.dump(pf, f, ensure_ascii=False, indent=2)

print()
print("=== RESULTAT ===")
print("Liquidites: " + str(round(pf['liquidites'], 2)) + " EUR")
print("Capital total: " + str(round(pf['liquidites'], 2)) + " EUR")
print("Positions ouvertes: 0")
print("Trades fermes: " + str(len(pf['trades_fermes'])))
print()
print("OK - Position(s) fermee(s)")
