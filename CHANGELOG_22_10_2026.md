# Changements du 22 octobre 2026 — « carte blanche »

Objectif : que le bot se comporte comme un pro, c'est-à-dire que chaque règle soit mesurée, révisable par les faits, et qu'aucune ne soit figée sur un bilan de septembre. Lignes rouges respectées : aucune nouvelle clé API, aucun prix via Binance, aucun ordre réel.

## Ce qui change

| # | Changement | Avant | Après |
|---|---|---|---|
| 1 | **Porte auto-calibrée** (`PORTE_AUTO`, défaut 1) | tous les filtres bloquent, même ceux qui coûtent | un filtre jugé « à revoir » par le bilan contrefactuel (≥ 10 cas bloqués, R évité négatif) cesse de bloquer, reste mesuré, se réarme seul. Aujourd'hui : CUSUM (il bloquait 5 objectifs pour 2 stops) |
| 2 | **Chaque filtre est toujours jugé** | un filtre désactivé n'était plus mesuré | verdict enregistré à chaque passage, blocage seulement si actif |
| 3 | **Casier mesuré** (`registre_strategies.casier`) | liste noire fixe LDO/ADA/DOT/PEPE/AVAX/BNB + lundi interdit (bilan de 211 trades) | une crypto ou un jour n'est interdit que s'il est perdant avec confiance (≥ 15 trades, borne haute 90 % du gain moyen < 0) ; révisé toutes les 10 min ; appliqué aux deux chemins (bot et IA) via la porte |
| 4 | **Heures unifiées** | 4 tables contradictoires (14h/3h/11h bloquées ; bonus 12-13h et 16-17h ; porte 13-15h ; journal 13-14h) | une seule source : la porte (`PORTE_FENETRES_UTC`, défaut 13h-15h) + règles mesurées du journal. Le bonus « fort volume » est supprimé (16-17h est la pire heure en triple barrière) |
| 5 | **Refroidissement par crypto** (`PORTE_COOLDOWN_H`, 2 h) | réouverture possible immédiatement après une fermeture (cascades) | pas de réouverture sur la même crypto pendant 2 h après une fermeture, quel que soit le chemin |
| 6 | **Plafond d'ouvertures commun** (`MAX_OUVERTURES_JOUR`, 6) | 5/jour côté bot seulement, rien côté IA | plafond commun bot + IA, mesuré comme les autres filtres |
| 7 | **Fin du « mode évolution »** | objectifs x10/an ; cible manquée = l'IA change de stratégie au hasard | désactivé (`MODE_EVOLUTION=1` pour le réactiver). L'IA reste vivante ; ce sont le registre, le journal et la porte qui font évoluer le bot, sur des faits |
| 8 | **Palier de risque automatique** (`stop_atr.risque_courant`) | 1 € par trade, fixe | 1 € par défaut ; ×2 dès 30 trades depuis le nouveau départ avec borne basse 90 % du gain moyen > 0 ; ×3 dès 60 ; plafond 0,5 % du capital ; redescend seul si la preuve disparaît |
| 9 | **Mémoire des réussites** | la mémoire épisodique forçait ≥ 2 pertes parmi les cas similaires, souvent aucun gagnant | garantit aussi au moins un gagnant similaire : l'analyste raisonne par contraste |
| 10 | **Force relative vs BTC** dans la présélection | aucune comparaison entre cryptos | +1 si la crypto surperforme BTC de plus de 2 points sur 7 jours, -1 si elle sous-performe de plus de 5 points. Un tri, pas un filtre |
| 11 | **Lecture de `.env`** (`config_env.py`) | `LLM_LIBRE`, `CRITIQUE_MODE`, `PORTE_*`, `REVENUS_PARALLELES` lus seulement dans l'environnement du processus : `LLM_LIBRE=0` était sans effet (OVH encore appelé 39 fois le 22/10) | tous ces réglages lisent `.env` |
| 12 | **rsi_oversold ouvre à nouveau** | professeur seulement | droit d'ouvrir rendu (74 % en tendance sur 19 trades, 67 % à vie sur 43) ; passe par la porte complète, taille Thompson, retrait automatique si elle redevient perdante |

## Ce qui ne change pas

- Stop 2×ATR, objectif 2:1, barrière 24 h ; sorties intelligentes (TP partiel, pattern, stop suiveur) ; registre à vie ; journal des erreurs ; veto du critique auto-calibré.
- Filtres utiles conservés et armés : liquidité (8 stops évités sur 8 blocages), flux d'ordres (5 sur 5), tendance lente, chaleur, régime, fenêtres.
- Aucun ordre réel. Kraken virtuel et Revolut X virtuel continuent en parallèle.

## Commandes

```
python3 porte_entree.py bilan          # bilan contrefactuel par filtre + filtres désarmés
python3 registre_strategies.py casier  # cryptos / jours interdits par les faits
python3 stop_atr.py risque             # palier de risque courant et sa preuve
python3 cerveau.py rapport | head -4   # calibration + « qui a raison »
```

Retour arrière possible réglage par réglage dans `.env` : `PORTE_AUTO=0`, `PORTE_CADENCE=0`, `PORTE_CASIER=0`, `MODE_EVOLUTION=1`, `RISQUE_MAX_PCT=0.1`, `python3 registre_strategies.py droit rsi_oversold off`.
