# Changements du 10 novembre 2026 — le professeur Hyperliquid (suivre les meilleurs, apprendre leur façon de trader)

Demande de l'utilisateur : une plateforme où l'on voit **en direct** des gens qui tradent et qui gagnent, **vérifiée**, pour
aider le bot ; « construis le professeur Hyperliquid sans droit d'ouvrir, donne au bot comme consigne de suivre que les
meilleurs et d'apprendre leur stratégie ».

## Pourquoi Hyperliquid
Bourse de perpétuels entièrement sur chaîne : chaque position et chaque gain est public et impossible à maquiller.
L'API publique répond **sans clé ni compte** (1 200 unités de poids / min / IP). Le classement complet (48 073 comptes,
PnL jour / semaine / mois / total) est public lui aussi. Respecte la règle « je ne veux pas rajouter d'API ».

## Nouveau module `professeur_hyperliquid.py`
- **Les meilleurs** = cohorte de 40 comptes filtrés (pas « le premier du classement ») : capital ≥ 250 k$ ; gagnants à la fois
  sur la semaine, le mois et depuis toujours ; rendement du mois entre 5 % et 300 % (au-delà : loterie) ; rotation
  volume/capital ≤ 60× (écarte teneurs de marché et coffres). Note de régularité = 60 % mois + 20 % semaine + 20 % total.
  Le 10/11 à 13:23 UTC : 632 comptes passent les filtres sur 48 073, 40 gardés.
- **Lecture des positions** toutes les 15 min (1 appel par trader) : par crypto du bot, dollars longs / courts, nombre de
  traders de chaque côté, entrées fraîches depuis la lecture précédente (ouvre / renforce / ferme).
- **Apprendre leur façon de trader** (toutes les 6 h, 2 000 derniers ordres de chaque trader) : part long/short, % de
  clôtures gagnantes, durée médiane de détention, achat des creux ou de la force (variation 24 h avant l'entrée, sur nos
  bougies 1 h), heures UTC actives, levier. Une **leçon de cohorte** résume ce qu'ils ont en commun. Les scalpeurs
  (détention médiane < 1 h) sont profilés mais leurs positions ne sont pas lues : elles changent plus vite que nos lectures.
- **Votes** : ACHAT (`entree_longue` si un des meilleurs vient d'ouvrir/renforcer un long ; `biais_long` si ≥ 65 % des dollars
  sont longs avec ≥ 3 traders) et VENTE (symétrique, lu comme un signal de prudence : le bot achète au comptant).
  Jugés avec la barrière du bot (stop 2×ATR 1 h, objectif 2:1, 24 h), **dans le sens du vote**.
- **Influence gagnée, pas accordée** : +0,5 (achat) / −0,5 (vente) sur la présélection seulement après 20 votes tranchés
  et ≥ 45 % d'objectifs. Avant : seulement lu par l'analyste.
- Première lecture réelle : les meilleurs sont massivement **short** BTC (16 shorts 29 M$ contre 2 longs 0,5 M$), ETH
  (13 shorts 27 M$), SOL (7 shorts 6 M$) ; exposition longue médiane 4 % ; détention médiane 38 h ; 8 sur 10 achètent la
  force plutôt que les creux ; levier moyen 19×.
- Tout en arrière-plan (fils séparés) : le bot n'attend jamais. Classement complet lu en flux (pas 48 000 lignes en mémoire).

## Branchements
- `paper_trading.py` : déclenche les rafraîchissements et écrit une ligne `[HYPERLIQUID]` à chaque cycle.
- `cerveau.py` présélection : bonus/malus ±0,5 seulement si FIABLE.
- `chat_naturel.py` : bloc « PROFESSEUR HYPERLIQUID » dans le dossier de l'analyste, avec la consigne de l'utilisateur ;
  commande Telegram rapide `hyperliquid` (ou `meilleurs traders`, `baleines`) → rapport.
- `.env.example` : `PROF_HYPERLIQUID`, `HL_N_TRADERS`, `HL_CAPITAL_MIN`, `HL_ROI_MOIS_MIN/MAX`, `HL_ROTATION_MAX`,
  `HL_DETENTION_MIN_H`, `HL_N_PROFILS`, `HL_RAFRAICHIR_COHORTE_H`, `HL_RAFRAICHIR_POSITIONS_S`.
- Tests : `tests/test_professeur_hyperliquid.py` (8 tests hors ligne) ; 57 tests passent.

## Ce que ça ne fait PAS
Aucun droit d'ouvrir, aucun ordre, aucune clé, aucun copy trading. Le levier et la taille des meilleurs ne se copient
pas au comptant : on apprend leur sens et leur timing.

## Retour arrière
`PROF_HYPERLIQUID=0` dans `.env` puis `sudo systemctl restart paper_trading.service chat_naturel.service`
(ou `git checkout c5eeaa0 -- paper_trading.py cerveau.py chat_naturel.py`).

## CLI
`python3 professeur_hyperliquid.py` (rapport) · `rafraichir` (classement + positions + profils, ~1 min) · `positions` · `evaluer`
