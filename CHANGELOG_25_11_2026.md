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

## Complément

- Une panne de l'historique BTC rendait la tendance lente « inconnue » pendant une heure (garde de baisse et filtre de tendance muets).
  La dernière tendance connue est maintenant gardée 48 h au plus et l'échec n'est retenu que 5 minutes.

## Soir — la mise par trade revient à 1 EUR tant que rien n'est prouvé

Historique complet du VPS (89 trades depuis le 19/10, −23,24 EUR) :

- octobre : 47 trades, +1,45 EUR ; novembre : 42 trades, −24,69 EUR ;
- 77 trades avant le 11/11 : −1,83 EUR ; 12 trades après : −21,41 EUR, dont 10 stops à environ 2,5 EUR ;
- par sortie : les 30 stops coûtent −37,50 EUR, toutes les autres sorties réunies rapportent +14,26 EUR ;
- aucune des 7 stratégies n'est positive sur sa vie.

Le 11/11 la mise de base était passée de 1 EUR à 0,25 % du capital (2,5 EUR) pour toutes les stratégies, au motif que le bot
« faisait du sur place ». C'était une erreur : 76 trades à l'équilibre montrent une absence d'avantage, pas une mise trop petite.

Correction : `RISQUE_PCT` vaut 0,10 % par défaut (1 EUR sur 1 000). La mise ne monte que sur preuve, stratégie par stratégie
(x2 à 30 trades prouvés, x3 à 60). `RISQUE_PCT` est maintenant lu aussi dans `.env`. Taille minimale d'un trade : 10 EUR au lieu
de 20 (sinon un stop de 3 % en demi-taille était refusé). Retour arrière : `RISQUE_PCT=0.25` dans `.env`.
