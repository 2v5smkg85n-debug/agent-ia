import json

# Charger le backup (etat corrompu original)
pf = json.load(open('paper_trading_backup.json'))

print("=== RESTAURATION ETAT CORRECT ===")
print("Backup - Liquidites:", round(pf['liquidites'], 2))
print("Backup - Trades:", len(pf.get('trades_fermes', [])))
print("Backup - Positions:", len(pf['positions']))
print()

# Les trades fermes avant 16:10 sont corrects (39 trades)
# L'etat correct connu: liq=889.69, 1 position LDO, 39 trades
trades = pf.get('trades_fermes', [])
trades_valides = []
for t in trades:
    date_str = t.get('date_fermeture', '')
    # Garder seulement les trades avant 16:10 le 18 aout
    if '2026-08-18 16:' in date_str or '2026-08-18 17:' in date_str or '2026-08-18 18:' in date_str:
        print("Trade a supprimer:", t.get('symbole'), 'gain:', round(t.get('gain_eur', 0), 2), 'date:', date_str)
    else:
        trades_valides.append(t)

print()
print("Trades valides conserves:", len(trades_valides))

# Restaurer la position LDO (le dernier etat correct connu)
position_ldo = {
    "symbole": "LDOUSDT",
    "nom": "Lido DAO",
    "marche": "crypto",
    "prix_entree": 0.3051,
    "quantite": 262.214,
    "montant_eur": 80.0,
    "frais_entree": 0.08,
    "date_ouverture": "2026-08-18 15:37",
    "signal_raison": "breakout",
    "source": "binance",
    "strategie": "breakout",
    "prix_peak": 0.3051,
    "tp_adaptatif": 3.0,
    "sl_adaptatif": 1.5,
    "intel_score": 0,
    "intel_fg": 0,
    "intel_regime": "",
    "mtf_confirmation": "",
    "si_score": 0,
    "si_verdict": ""
}

# Etat correct
pf['liquidites'] = 889.69
pf['positions'] = [position_ldo]
pf['trades_fermes'] = trades_valides
pf['total_frais'] = 10.29
pf['dernier_tick'] = "2026-08-18 16:09"

# Sauvegarder
with open('paper_trading.json', 'w') as f:
    json.dump(pf, f, ensure_ascii=False, indent=2)

print()
print("=== ETAT RESTAURE ===")
print("Liquidites:", pf['liquidites'], "EUR")
print("Capital total:", round(pf['liquidites'] + 80, 2), "EUR")
print("Positions:", len(pf['positions']))
print("  LDOUSDT entree: 0.3051 montant: 80 EUR")
print("Trades fermes:", len(pf['trades_fermes']))
print()
print("OK - Portefeuille restaure correctement")
