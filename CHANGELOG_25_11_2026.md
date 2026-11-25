# 25/11/2026 — garde de baisse : le même pari n'est plus pris huit fois

## Constat (portefeuille du VPS, 24/11)

- 8 achats dans la journée, 8 stops, −17,66 EUR ; 7 par `rsi_oversold`, 1 par `volume_spike`.
- Jusqu'à 5 positions crypto ouvertes en même temps (plafond « chaleur » : 4), 8 ouvertures (plafond « cadence » : 6),
  PENDLE rachetée 1 h 31 après son stop (refroidissement : 2 h). Ces limites ne bloquaient donc plus sur le VPS.
- BTC est sous son EMA 84 jours (−18 % le 25/11) : toutes les cryptos tombent ensemble, les 8 achats étaient un seul pari.
- Aucun trade du 14 au 22/11 ; les achats reprennent après le correctif du 22/11 (taille à zéro en `baisse_forte` remplacée par x0,60).
  Le correctif était juste (plus de veto silencieux), mais plus rien ne bornait le risque en marché baissier.

## Corrections (mesurées, réversibles)

1. **Les limites de risque ne se désarment plus seules.** `chaleur`, `cadence` et `baisse` sont exclues de `PORTE_AUTO` : le bilan
   contrefactuel juge chaque candidat seul et ne voit pas la corrélation. Retour arrière : `PORTE_AUTO_LIMITES=1`.
2. **Garde de baisse** (`porte_entree.garde_baisse`, filtre `baisse`) : tant que BTC est sous son EMA lente, au plus
   `BAISSE_MAX_POSITIONS` (2) positions crypto à la fois et plus d'achat après `BAISSE_STOPS_MAX` (2) stops en `BAISSE_STOPS_H` (24) heures.
   Chaque refus est écrit dans le journal de la porte avec l'heure de reprise ; le verdict est jugé comme les autres. Rien ne change
   quand la tendance lente est haussière ou inconnue. Couper : `PORTE_BAISSE=0`.
3. **Message du coupe-circuit** (`protection_capital`) : il annonçait une reprise « quand les conditions s'améliorent » ; le code
   reprend après 30 min puis ignore les pertes consécutives pendant 1 h. Le message dit maintenant ce que fait le code (comportement inchangé).
4. **Diagnostic** : `python3 porte_entree.py baisse` (lecture seule) et une ligne « garde de baisse » dans `pourquoi_pas_de_trade.py`.

## Effet attendu

Journée du 24/11 rejouée dans les tests : 3 achats au lieu de 8 (FET, NEAR, BTC), soit environ −5 EUR au lieu de −17,66 EUR.
La garde ne rend pas ces trades gagnants ; elle borne la perte d'une journée de baisse.

## Non traité

- Le coupe-circuit rouvre toujours après 30 min, y compris pour une pause de drawdown (choix d'origine contre le blocage définitif).
- `rsi_oversold` reste jugée par le registre et le laboratoire ; aucune stratégie n'a été retirée à la main.
