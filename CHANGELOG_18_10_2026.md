# Changements du 18 octobre 2026 — « On met toutes les améliorations »

Mise en œuvre des 25 points du rapport *Toutes les améliorations possibles du bot* (recherche Web du 18/10/2026).
Principe : **rien n'est effacé** (403 trades, journal, registre, décisions du cerveau restent), le bot repart avec de
nouvelles règles d'entrée, de stop et de taille, un cerveau multi-modèles et des outils pour mesurer honnêtement.

## Ce qui change dans la prise de décision

| # | Amélioration | Fichier | Branché où |
|---|---|---|---|
| 1 | Routeur de modèles : Groq gpt-oss-120b → OpenRouter (modèles :free) → Gemini → Ollama, quotas comptés, avocat du diable sur un fournisseur **différent** | `llm_router.py` | `cerveau._llm` |
| 2 | Modèles locaux légers (qwen3.5:4b analyste de secours, llama3.2:3b critique) au lieu de qwen2.5:7b (5,4 Go) | `llm_router.py` (env `LLM_MODELE_LOCAL`) | Ollama |
| 3 | Prompt en étapes : « est-ce distinguable du bruit ? » avant la checklist ; case `distinguable_du_bruit` obligatoire | `cerveau.py` | analyste |
| 4 | Stop = 2 × ATR 1h (0,8–3 %), 2,5 × pendant la session US ; objectif = 2 × stop (1,5 × en range) ; barrière de temps 24 h ; taille = risque / (stop + frais) ; risque ÷ 2 en turbulent | `stop_atr.py` | `journal_erreurs.preparer_entree` → `paper_trading` (`tp_risque`, `barriere_h`, sortie `BARRIERE-TEMPS`, stale 12 h) |
| 5 | Porte d'entrée unique, 8 filtres indépendants et débrayables (`PORTE_xxx=0`) : fenêtre 13h00–14h30 UTC + macro USD, tendance lente BTC (EMA 84 j), chaleur du portefeuille (2 positions crypto, 3 € de risque total), régime turbulent, CUSUM (événement de prix récent), spread/profondeur Kraken, flux d'ordres, méta-modèle | `porte_entree.py` | `journal_erreurs.preparer_entree` |
| 6 | Flux d'ordres Kraken (Trade Flow Imbalance 30 min) | `flux_ordres.py` | porte + prompt |
| 7 | Mémoire épisodique : similarité cosinus sur les indicateurs, ≥ 2 pertes parmi les 5 trades montrés à l'IA | `memoire_episodique.py` | `journal_erreurs.similaires` |
| 8 | Registre bayésien : WR Beta(5,5) + intervalle 90 %, point mort par stratégie, Deflated Sharpe, ventilation par régime, statut auto basé sur l'intervalle | `registre_strategies.py`, `validation_stats.py` | registre |
| 9 | Taille Thompson : × 0,5 à × 1,25 selon la confiance statistique de la stratégie (et du régime) | `registre_strategies.facteur_taille` | `preparer_entree` |
| 10 | Pattern hikkake (haussier/baissier, réf. TA-Lib CDLHIKKAKE) | `bougies_patterns.py` | patterns |
| 11 | Glissement réaliste loi de puissance α(Q/profondeur)^β dans le Kraken virtuel | `kraken_paper.py` | shadow |

## Données, apprentissage, mesure

| # | Amélioration | Fichier | Commande |
|---|---|---|---|
| 12 | Bougies 1 minute gratuites (Binance Vision), stockage gzip, rééchantillonnage | `donnees_1m.py` | `python3 donnees_1m.py --tous --mois 4` |
| 13 | Ré-étiquetage triple barrière des 403 trades + reconstruction des indicateurs à l'entrée | `etiquetage_triple_barriere.py` | `python3 etiquetage_triple_barriere.py` |
| 14 | Méta-modèle (régression logistique pur Python, walk-forward avec embargo ; actif seulement si AUC ≥ 0,55 et ≥ 150 exemples) | `meta_modele.py` | `python3 meta_modele.py entrainer` |
| 15 | Base SQLite durable (trades, décisions, journal, registre, porte) — copie, jamais effacée | `etat_sqlite.py` | `python3 etat_sqlite.py migrer` (cron horaire) |
| 16 | Statistiques honnêtes : Deflated Sharpe, trades minimum, Monte-Carlo bootstrap, verdict | `validation_stats.py` | utilisé par le registre |
| 17 | Page dashboard `/porte` (+ `/api/porte`) : contexte, décisions de la porte, quotas LLM, registre bayésien, méta-modèle | `page_porte.py`, `dashboard_premium.py` | navigateur |

## Infrastructure

| # | Amélioration | Fichier |
|---|---|---|
| 18 | Prix temps réel Kraken WebSocket v2 → `prix_ws.json`, lu en priorité par `prix_revolut` (repli HTTP automatique) | `ws_kraken.py`, `prix_revolut.py` |
| 19 | zram (swap compressée zstd 50 %), NTP, erreurs dans journald, limites mémoire, logrotate, cron SQLite + heartbeat healthchecks.io | `setup_infra.sh` |
| 20 | Étalon Freqtrade (même logique, dry-run Kraken) pour comparer l'exécution | `setup_freqtrade_etalon.sh`, `freqtrade_etalon/` |
| 21 | Tests pytest + GitHub Actions à chaque push | `tests/`, `.github/workflows/tests.yml` |

Les points 22–25 du rapport (Revolut X API clés Ed25519, passage au réel, Caddy HTTPS, abonnement OpenRouter 10 $) restent
des décisions humaines : rien n'est activé sans votre accord explicite.

## Variables d'environnement utiles (`.env`)

```
GROQ_KEY=...            OPENROUTER_KEY=...      OPENROUTER_PAID=0|1
LLM_MODELE_LOCAL=qwen3.5:4b   LLM_MODELE_LOCAL_CRITIQUE=llama3.2:3b
ATR_MULT=2.0  ATR_MULT_US=2.5  SL_MIN=0.8  SL_MAX=3.0  TP_RATIO=2.0  BARRIERE_H=24  RISQUE_EUR=1.0  STALE_H_ATR=12
PORTE_FENETRES=1 PORTE_TENDANCE_LENTE=1 PORTE_CHALEUR=1 PORTE_REGIME=1 PORTE_CUSUM=1 PORTE_LIQUIDITE=1 PORTE_FLUX=1 PORTE_META=1
RISQUE_TOTAL_MAX=3.0  MAX_POSITIONS_CRYPTO=2  CUSUM_ATR_MULT=2.5  SPREAD_MAX_PCT=0.15  TFI_MIN=-0.3  META_SEUIL=0.5
HEALTHCHECK_URL=https://hc-ping.com/xxxx
```

## Ce qu'il faut savoir

- Le bot tradera **beaucoup moins** (la porte bloque la majorité des signaux) : c'est voulu, l'objectif est l'espérance par trade,
  pas le nombre de trades. Chaque blocage est journalisé (`porte_entree_log.jsonl`, page `/porte`) pour mesurer ensuite ce que
  chaque filtre a évité ou coûté.
- Les positions « triple barrière » (champ `tp_risque`) ne sont plus coupées à 3 h : stale à 12 h, durée 24 h, puis `BARRIERE-TEMPS`.
- En cas d'API muette, chaque filtre laisse passer (fail-open) et le note dans `filtres_sautes`.
- Le méta-modèle ne bloque rien tant qu'il n'a pas prouvé une AUC hors échantillon ≥ 0,55.
