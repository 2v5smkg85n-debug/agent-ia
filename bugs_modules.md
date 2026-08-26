# Audit de bugs — Modules trading
Date: 2026-08-26
Fichiers scannés: prix_revolut.py, sentiment_marche.py, indicateurs.py, intelligence_pro.py, gestion_risque.py

Légende sévérité: CRITIQUE (casse une fonctionnalité) / BUG (comportement incorrect) / INCONSISTANCE (doc vs code) / MINEUR

---

## 1. prix_revolut.py

### BUG-1.1 — BLACKLIST en conflit avec SYMBOLES_REVOLUT (CRITIQUE)
- **Lignes:** 20, 41, 43, 54
- **Problème:** `BLACKLIST = {"SUIA", "COMP", "IMX", "AXS", "CAKE", "SAND", "FLOKI", "PEPE", "MATIC"}`. Or `PEPE` (ligne 43), `MATIC` (ligne 41) et `FLOKI` (ligne 54) sont AUSSI présents dans `SYMBOLES_REVOLUT`. Conséquence: `get_prix_revolut("PEPEUSDT")` normalise en `PEPE`, trouve `PEPE` dans la blacklist, et retourne toujours 0. Ces symboles sont mappés mais ne fonctionneront jamais.
- **Fix:** Soit retirer PEPE/MATIC/FLOKI de `BLACKLIST` s'ils existent désormais sur Revolut X, soit les retirer de `SYMBOLES_REVOLUT` (et de `_prix_coingecko` mapping) puisqu'ils sont toujours bloqués.

### BUG-1.2 — Entrée de blacklist "SUIA" = typo (BUG)
- **Ligne:** 20
- **Problème:** "SUIA" n'est un token connu d'aucun écosystème. Le token SUI existe (`SUIUSDT` -> `"SUI"` à la ligne 50) mais n'est PAS dans la blacklist. "SUIA" ne matche aucun symbole bot et est donc un noop mort.
- **Fix:** Supprimer "SUIA", ou la corriger en le vrai symbole à blacklister.

### BUG-1.3 — Docstring cache TTL vs constante (INCONSISTANCE)
- **Lignes:** 9 vs 16
- **Problème:** La docstring (ligne 9) dit "Cache de 60 secondes pour eviter le spam API" mais `CACHE_TTL = 300` (5 minutes). Le commentaire ligne 16 confirme 5 min. La docstring est donc fausse.
- **Fix:** Mettre la docstring à "Cache de 300 secondes (5 minutes)".

### BUG-1.4 — get_prix_batch: sleep inconditionnel même sur cache (MINEUR)
- **Lignes:** 209-215
- **Problème:** `time.sleep(3.0)` s'exécute pour chaque symbole (i>0) avant l'appel à `get_prix_revolut`, même si le prix est servi depuis le cache (retour immédiat). Sur 30 symboles, cela gaspille jusqu'à 87s de sleep inutile si tout est en cache.
- **Fix:** Déplacer le sleep à l'intérieur de `get_prix_revolut` (uniquement sur cache miss / avant l'appel HTTP réel), ou vérifier le cache avant le sleep.

### BUG-1.5 — get_prix_avec_variation: "var_24h" n'est pas une variation 24h (BUG)
- **Lignes:** 219-242
- **Problème:** `var_24h` est calculée comme `(prix - old["prix"]) / old["prix"]` où `old` est la valeur du PRECEDENT appel à `get_prix_avec_variation` (cachée sous clé `_hist`), pas la valeur d'il y a 24h. Si la fonction est appelée toutes les 5 min, `var_24h` est en réalité une variation sur 5 min. Le nom et la sémantique sont trompeurs.
- **Fix:** Soit renommer en `var_depuis_dernier_appel`, soit stocker un prix horodaté et ne comparer qu'avec une entrée vieille d'au moins 24h (avec TTL/garbage collection sur les entrées `_hist`).

### BUG-1.6 — get_prix_revolut: spread_pct nom trompeur (MINEUR)
- **Ligne:** 137
- **Problème:** `spread_pct = abs(best_ask - best_bid) / best_bid` est une FRACTION (ex. 0.05 = 5%), pas un pourcentage. Le nom `spread_pct` suggère un pourcentage. Cohérent en interne (comparé à 0.05) mais source de confusion vs `get_spread_pct` qui lui retourne un vrai pourcentage (*100).
- **Fix:** Renommer en `spread_frac` pour cohérence.

---

## 2. sentiment_marche.py

### BUG-2.1 — Aucun cache sur get_fear_greed / fetch_fear_greed (BUG)
- **Lignes:** 23-30, 85-90, 93-113
- **Problème:** `fetch_fear_greed` ne met RIEN en cache. `sentiment_prompt()` appelle `fetch_fear_greed(30)` et `sentiment_multiplier()` appelle `fetch_fear_greed(1)` — chaque appel fait une requête HTTP sur alternative.me. Si l'agent appelle `score_intelligent` ou `sentiment_prompt` + `sentiment_multiplier` dans le même cycle, c'est 2+ hits API. Le module voisin `intelligence_pro.py` a lui un cache de 900s (`_cache_fg`) — cette version n'en a aucun, d'où risque de rate-limit / 429.
- **Fix:** Ajouter un cache mémoire (ex. `_cache = {"data": None, "ts": 0}`, TTL 300-900s) partagé par les fonctions, comme dans `intelligence_pro.get_fear_greed`.

### BUG-2.2 — sentiment_multiplier: jamais de sizing-up contrarian (MINEUR/design)
- **Lignes:** 93-113
- **Problème:** La docstring dit "achète plus en fear" mais le multiplicateur ne dépasse jamais 1.0 (Extreme Fear = 1.0 = taille pleine, jamais amplifiée). De plus, en cas d'indisponibilité on retourne 1.0, mais quand le sentiment est disponible et Neutre on retourne 0.85 — donc connaître le sentiment réduit systématiquement la taille vs l'inconnu. Le comportement "contrarian" est en réalité seulement "réduction en greed", pas "amplification en fear".
- **Fix:** Si l'intention est un vrai sizing contrarian, autoriser >1.0 en Extreme Fear (ex. 1.2) et garder 1.0 comme neutre. Sinon préciser la docstring.

### BUG-2.3 — Seuils de classification incohérents avec intelligence_pro.py (INCONSISTANCE cross-module)
- **Lignes:** 33-43, 103-112
- **Problème:** Ce module utilise: Extreme Fear <25, Fear <45, Neutral ≤55, Greed ≤75, Extreme Greed >75. `intelligence_pro.fear_greed_score` utilise: <20, <35, <55, <75, ≥75. Même source API, deux grilles de seuils différentes → scores contradictoires entre modules.
- **Fix:** Centraliser les seuils de classification dans un seul endroit (ex. un `sentiment_marche.classification(valeur)`) et le réutiliser partout.

---

## 3. indicateurs.py

### BUG-3.1 — _historique_revolut: `_t` non défini → NameError silencieux (CRITIQUE)
- **Lignes:** 170, 184, 206
- **Problème:** `_historique_revolut` utilise `_t.time()` (lignes 170, 184, 206) mais le nom `_t` n'est JAMAIS importé dans cette fonction ni au niveau module. Le seul `import time as _t` se trouve à la ligne 244, DANS `historique_ohlcv_long` (portée locale différente). Effet réel:
  - Ligne 170 (cache HIT, hors try) → `NameError` non attrapée → crash propagé à `historique_ohlcv`. Mais le cache n'est jamais peuplé car...
  - Ligne 184 (cache MISS, dans try) → `NameError` attrapée par `except Exception` → retourne `[]`.
  - Donc `_historique_revolut` retourne TOUJOURS `[]` (la branche try échoue toujours avant de remplir le cache, la branche cache-hit n'est jamais atteinte). Le chemin Revolut X OHLCV est donc silencieusement mort et on tombe toujours sur CoinGecko/Binance. Aucune erreur n'est remontée.
- **Fix:** Ajouter `import time as _t` en haut de `_historique_revolut` (ou utiliser `time.time()` directement, le module `time` étant déjà importé au niveau module ligne 19). Vérifier aussi `_historique_revolut` ne masque pas d'autres usages de `_t`.

### BUG-3.2 — RSI: off-by-one → IndexError quand len(clotures)==15 (BUG)
- **Lignes:** 378-383
- **Problème:** Garde `if len(clotures) < periode + 1: return None` (periode=14 → garde <15, donc accepte len==15). Mais la boucle `for i in range(1, periode + 1)` accède à `clotures[-(i+2)]`. Pour i=14: `clotures[-(16)]`. Sur une liste de 15 éléments, l'index -16 est hors limite → `IndexError`. Il faut 16 éléments pour 14 différences (les indices -2..-16 = 15 valeurs, et -16 nécessite len≥16).
- **Fix:** Changer le garde en `if len(clotures) < periode + 2: return None`.

### BUG-3.3 — prix_actuel: mélange de devises EUR/USD (BUG)
- **Lignes:** 331-353
- **Problème:** La docstring dit "Prix actuel via Revolut X (EUR, identique a Revolut)". Mais:
  - Primaire (Revolut): EUR ✓
  - Fallback CoinGecko (ligne 344): `vs_currencies=usd` → retourne un prix en USD
  - Fallback Binance (ligne 350): `ticker/price` → prix USDT (≈USD)
  Donc selon la source qui réussit, `prix_actuel` retourne un mélange EUR ou USD. Tout appelant qui compare ce prix à des seuils/SL en EUR (ou à d'autres prix EUR) obtient des valeurs incohérentes (différence ~1.05x).
- **Fix:** Utiliser `vs_currencies=eur` pour CoinGecko (ligne 344), et pour Binance convertir via le taux EUR/USD ou documenter le fallback USD.

### BUG-3.4 — _historique_coingecko: volumes récupérés mais jamais utilisés (BUG)
- **Lignes:** 296, 300-311
- **Problème:** `volumes = data.get("total_volumes", [])` (ligne 296) est récupéré mais jamais assigné aux buckets. Les buckets sont initialisés avec `"volume": 0` (ligne 307) et la clé `volume` n'est jamais mise à jour. Conséquence: toutes les bougies CoinGecko ont `volume == 0`. Comme `_historique_coingecko` est le fallback principal après que `_historique_revolut` échoue (BUG-3.1), la majorité des bougies ont volume=0 → VWAP jamais calculé (BUG-3.6).
- **Fix:** Associer chaque volume à son bucket temporel (même logique d'agrégation que les prix) et accumuler dans `buckets[bucket]["volume"]`.

### BUG-3.5 — EMA mal seedée: démarre à valeurs[0] au lieu d'une SMA (BUG)
- **Lignes:** 366-374 (ema), 401-406 (calc_ema_series), 414 (signal_line)
- **Problème:** L'EMA est initialisée à `valeurs[0]` (ligne 371 / 403), pas à la SMA des `periode` premières valeurs. C'est une approximation qui surestime la réactivité des premières barres et reste biaisée sur des séries courtes. Pour le MACD 8-17-9, l'EMA longue (17) démarre donc au 1er close, ce qui fausse la ligne MACD sur les ~30 premières bougies. Même problème pour `ema()` standalone et `calc_ema_series`.
- **Fix:** Seeder avec `sum(valeurs[:periode]) / periode` et itérer à partir de l'index `periode`, ou accepter l'écart en exigeant ≥3×periode bougies.

### BUG-3.6 — VWAP: utilise close au lieu du typical price + non cumulatif (BUG)
- **Lignes:** 552-566
- **Problème:** (a) VWAP standard utilise le typical price `(H+L+C)/3`, ici on n'utilise que `cloture`. (b) Le VWAP devrait être cumulé depuis le début de session, ici c'est un rolling 20-barres. (c) Avec les données CoinGecko (volume=0, BUG-3.4) ou tout source sans volume, `_vol_total==0` → VWAP sauté. Résultat: le signal VWAP est quasi toujours absent ou inexact.
- **Fix:** Utiliser typical price, pondérer sur la fenêtre voulue (ou session), et garantir une source avec volume (lier à BUG-3.4).

### BUG-3.7 — _vwap / _vol_total définis dans try, utilisés hors try (MINEUR/latent)
- **Lignes:** 553-566 (try), 594 (référence)
- **Problème:** `_vol_total` et `_vwap` sont assignés dans le bloc `try` (556, 558) et référencés dans le dict de retour (594). En pratique c'est sûr (`_vol_total` assigné tôt, et si 0 le `else` court-circuite `_vwap`), mais si une exception surgit entre l'assignation de `_vol_total` et celle de `_vwap` avec `_vol_total>0`, `_vwap` est indéfini → `NameError` à la construction du dict. Fragile.
- **Fix:** Initialiser `_vwap = None` et `_vol_total = 0` avant le try.

### BUG-3.8 — RSI: simple average au lieu du lissage de Wilder (MINEUR/design)
- **Lignes:** 376-393
- **Problème:** Le RSI utilise une moyenne arithmétique simple des gains/pertes sur `periode`, pas le lissage de Wilder (EMA-like avec `alpha=1/periode`). La plupart des plateformes (TradingView, Binance) utilisent Wilder. Les valeurs divergent donc des RSI de référence.
- **Fix:** Implémenter le lissage de Wilder: `avg_gain = (prev_avg_gain*(periode-1) + gain) / periode`.

### BUG-3.9 — _historique_yahoo: variable `quote` masque l'import (MINEUR)
- **Lignes:** 117, 132
- **Problème:** `from urllib.parse import quote` (ligne 117) puis `quote = res["indicators"]["quote"][0]` (ligne 132) réassigne le nom `quote`. Pas de bug fonctionnel (la fonction `quote()` n'est plus utilisée après) mais masquage de nom fragile.
- **Fix:** Renommer la variable locale (ex. `quote_data`).

### BUG-3.10 — _historique_binance: pas de trim à `limite`, pas de User-Agent (MINEUR)
- **Lignes:** 211-233
- **Problème:** Contrairement aux autres sources, ne tronque pas à `[-limite:]` (retourne tout ce que l'API renvoie, soit `limit` — OK par coïncidence). Pas de header `User-Agent` (ligne 215) alors que Binance peut bloquer les requêtes sans UA.
- **Fix:** Ajouter `headers={"User-Agent": "Mozilla/5.0"}` et trimer pour cohérence.

---

## 4. intelligence_pro.py

### BUG-4.1 — Aucun handling des erreurs 429 / rate-limit (BUG)
- **Lignes:** 56-70 (get_fear_greed), 201-222 (get_ohlc_timeframe)
- **Problème:** Aucune gestion spécifique du code 429 (Too Many Requests) ni de backoff. `urlopen` lève `HTTPError` sur 429 → attrapé par `except Exception` → retourne valeur par défaut / liste vide. L'API CoinGecko gratuite est notoirement agressive sur les 429. Aucun retry, aucun `Retry-After`, pas de backoff exponentiel. `get_ohlc_timeframe` fait un `time.sleep(1)` APRÈS succès (ligne 218) mais rien sur échec. Conséquence: en cas de burst, toutes les données d'intelligence tombent silencieusement sur les défauts (Fear&Greed=50, OHLC=[]).
- **Fix:** Capturer `urllib.error.HTTPError` spécifiquement pour le 429, implémenter un backoff (ex. 2 essais avec sleep exponentiel + respect du header `Retry-After`), et logger le 429.

### BUG-4.2 — get_ohlc_timeframe: granularité CoinGecko ≠ timeframe demandé (BUG)
- **Lignes:** 203-219
- **Problème:** L'endpoint CoinGecko `/coins/{id}/ohlc` retourne une granularité AUTO basée sur `days`, indépendante du timeframe demandé:
  - `days=1` → bougies 30min (utilisé pour timeframe "1h" ligne 206 → on reçoit du 30min, pas du 1h)
  - `days=7` ou `≤90` → bougies 4h (utilisé pour timeframe "4h" ligne 208 → OK par chance; mais "1d" avec `days=30` ligne 204 → on reçoit du 4h, pas du journalier!)
  Donc `analyse_multi_timeframe` calcule des SMA/RSI sur des bougies dont la taille réelle ne correspond pas au timeframe affiché. Les scores "1h" et "1d" sont calculés sur des données 30min/4h. Résultat: comparaison multi-timeframe invalide.
- **Fix:** Soit utiliser l'endpoint market_chart + agrégation manuelle (comme `indicateurs._historique_coingecko`), soit valider/documenter que CoinGecko OHLC impose sa propre granularité et agrégeer vers le timeframe voulu. Pour "1d", il faut `days>90` ou récupérer les daily candles via un autre endpoint.

### BUG-4.3 — calculer_taille_position: champs "gain_pct" probablement absents (BUG)
- **Lignes:** 355-362
- **Problème:** Utilise `t.get("gain_eur", 0)`, `t.get("gain_pct", 3)`, `t.get("gain_pct", -1.5)`. Mais `gestion_risque._ratio_gp` (ligne 157-159) et les backtests utilisent `retour_pct` et `gain_eur` comme noms de champs. Si l'historique de trades live utilise la même convention (`retour_pct`), alors `gain_pct` n'existe pas → tous les `t.get("gain_pct", ...)` retombent sur les défauts (3.0 pour gagnants, 1.5 pour perdants), rendant le ratio gain/perte artificiellement figé et le Kelly inexact.
- **Fix:** Vérifier le schéma réel des trades (probablement `retour_pct` + `gain_eur`), aligner les clés ici, ou accepter les deux noms: `t.get("gain_pct") or t.get("retour_pct", 3)`.

### BUG-4.4 — backtester_maitres: bougies simulées avec clés EN vs FR (BUG)
- **Lignes:** 531-535
- **Problème:** Les bougies simulées utilisent les clés `"open","high","low","close"` (anglais). Or `indicateurs.py` (et probablement `master_traders`) utilise `"ouverture","haut","bas","cloture"`. Si les fonctions `mt.MAITRES[...].func` lisent les clés françaises (cohérent avec le reste du codebase), elles obtiendront `KeyError` sur chaque bougie → attrapé par `except Exception: pass` (ligne 553) → trade ignoré silencieusement. Le backtest peut alors sous-compter massivement les trades sans erreur visible.
- **Fix:** Utiliser les mêmes clés que le reste du codebase (`"ouverture","haut","bas","cloture"`) pour les bougies simulées, ou vérifier le contrat des fonctions `mt.MAITRES`.

### BUG-4.5 — verifier_diversification: docstring vs return type (MINEUR)
- **Lignes:** 431-437
- **Problème:** La docstring dit "Retourne True si OK, False si trop de correlation" mais la fonction retourne un tuple `(bool, str)` à toutes les branches (lignes 437, 441, 454, 456, 457). La signature de retour est incohérente avec la doc.
- **Fix:** Corriger la docstring: "Retourne (ok: bool, detail: str)".

### BUG-4.6 — get_ohlc_timeframe: ne vérifie pas le status_code (MINEUR)
- **Lignes:** 213-214
- **Problème:** Utilise `urlopen` puis `json.loads(resp.read())` sans vérifier le code HTTP. Un 429/500 lève une `HTTPError` (attrapée), mais un 200 avec un corps inattendu (ex. `{"status": {"error_code": 429, ...}}` que CoinGecko renvoie parfois avec 200) n'est pas détecté → `raw` contient un dict au lieu d'une liste → `analyse_multi_timeframe` fait `c[4]` sur un dict → `TypeError` attrapé plus loin. Comportement obtus.
- **Fix:** Valider que `raw` est une `list` de listes `[ts, o, h, l, c]` avant de cacher/retourner.

---

## 5. gestion_risque.py

### BUG-5.1 — Fallback 6% fixe contourne cap_dur (BUG)
- **Lignes:** 340-342
- **Problème:** `if montant_final < 1.0: montant_final = capital * 0.06`. Ce remplacement intervient APRÈS `cap_dur` (ligne 332). Le montant de remplacement (6% du capital) n'est donc PAS soumis aux plafonds par actif (15%) ni par secteur (40%). Scénario: `dispo_actif` = 5 EUR (actif déjà quasi saturé) → `montant_final` = 5 EUR (cap), puis si <1.0 on passe à capital*0.06 = 60 EUR, ignorant la limite d'exposition. On peut alors dépasser CAP_ACTIF sur l'actif.
- **Fix:** Réappliquer `cap_dur` sur le montant de fallback, ou au minimum `min(capital*0.06, dispo_actif, dispo_secteur)`.

### BUG-5.2 — Kelly=0 déclenche quand même un trade via fallback (BUG)
- **Lignes:** 317, 329, 340-342
- **Problème:** `kelly_optimal` retourne 0.0 quand il n'y a pas d'edge (`f <= 0`). Si une stratégie est "GAGNANTE" en backtest mais avec un win rate / ratio donnant Kelly≤0, `montant_base = capital * 0 * ... = 0`, `montant_final = 0`, puis le fallback 6% se déclenche → on trade quand même 6% du capital sur un setup sans edge détecté. Cela contredit l'objectif du Kelly (ne pas trader sans edge).
- **Fix:** Distinguer "Kelly trop faible mais edge positif" de "Kelly=0 / edge négatif". Si `kelly == 0.0`, retourner `0.0, "pas_d_edge"` AVANT le fallback, ou n'appliquer le fallback 6% que si `kelly > 0` mais `montant_final < 1.0`.

### BUG-5.3 — drawdown_scaler: pas de plafond à 1.0 → amplification non bornée (BUG)
- **Lignes:** 207-221
- **Problème:** Quand le capital dépasse le pic (nouveau plus-haut), `dd` devient négatif. La formule `1.0 - (dd / DRAWDOWN_SEUIL) * (1 - DRAWDOWN_REDUCTION)` devient `1.0 + valeur_positive` > 1.0. Contrairement à `vol_target_scaler` (qui plafonne à 1.0 via `min(1.0, scaler)`), `drawdown_scaler` n'a PAS de `min(1.0, ...)`. Donc en période de gain, la taille est amplifiée au-delà du Kelly, sans borne. La docstring ne mentionne que la réduction ("on reduit le sizing"), pas l'amplification.
- **Fix:** Ajouter `return min(1.0, ...)` sur la branche de retour finale, ou explicitement gérer `dd < 0` en retournant 1.0.

### BUG-5.4 — KELLY_FRACTION = 0.50 mais docstring dit Quarter Kelly (INCONSISTANCE)
- **Lignes:** 9 (docstring) vs 40
- **Problème:** Docstring module (ligne 9): "Quarter Kelly par defaut (0.25x)". Code (ligne 40): `KELLY_FRACTION = 0.50  # Half Kelly`. Le commentaire inline documente le changement ("SIZING-BOOST-INSTALLE") mais la docstring d'en-tête n'a pas été mise à jour.
- **Fix:** Mettre la docstring à "Half Kelly (0.50x)".

### BUG-5.5 — Commentaires VOL_CIBLE_JOUR / CAP_SECTEUR / cap_dur faux (INCONSISTANCE)
- **Lignes:** 41, 46, 252, 366
- **Problème:**
  - Ligne 41: `VOL_CIBLE_JOUR = 0.03` mais commentaire "2% de volatilite quotidienne" (0.03 = 3%).
  - Ligne 46: `CAP_SECTEUR = 0.40` mais commentaire "max 25% du capital sur un secteur" (0.40 = 40%).
  - Ligne 252 docstring `cap_dur`: "max 10% par actif, 25% par secteur" alors que c'est 15% / 40%.
  - Ligne 366 affichage: `"Exposition par secteur (cap 25%):"` mais `CAP_SECTEUR*100` = 40. L'alerte (ligne 373) compare à `CAP_SECTEUR*100`=40, donc cohérent avec le code mais pas avec le libellé affiché.
  Le commentaire de fin (ligne 458) confirme que 0.02→0.03 et 0.25→0.40 ont été changés, mais les commentaires inline et l'affichage n'ont pas suivi.
- **Fix:** Mettre à jour tous les commentaires et libellés affichés: "3%", "40%", "15% par actif / 40% par secteur", et l'affichage "(cap 40%)".

### BUG-5.6 — GROUPES_CORRELES: couverture partielle des cryptos (BUG)
- **Lignes:** 51-57, 186-202
- **Problème:** `GROUPES_CORRELES` ne groupe que 5 cryptos majeures (`BTC,ETH,SOL,BNB,XRP`). Les cryptos suivies dans `indicateurs.SYMBOLES_SUIVIS` (DOGE, AVAX, LINK, ADA, DOT, LTC, ATOM, APT, SUI, SEI, TIA, ARB, NEAR, LDO, AAVE, UNI, OP, INJ, etc.) ne sont dans AUCUN groupe → `groupe_correlation` retourne 1.0 (pas de haircut) pour elles, bien qu'elles soient hautement corrélées au BTC/ETH. De même, "TSLA" (présent dans `VOLATILITE_ACTIF`) n'est pas dans le groupe big-tech. Conséquence: le bot peut ouvrir DOGE+AVAX+LINK+ADA simultanément sans aucune réduction de sizing, alors qu'elles bougent souvent ensemble.
- **Fix:** Étendre `GROUPES_CORRELES` avec un groupe "altcoins L1/L2" (ex. `{DOGE,AVAX,LINK,ADA,DOT,ATOM,APT,SUI,SEI,TIA,ARB,NEAR,LDO,AAVE,UNI,OP,INJ,LTC,TRX,...}`) ou calculer la corrélation dynamiquement (cf. `intelligence_pro.calculer_correlations`).

### BUG-5.7 — valeur_portefeuille: coût d'achat, pas mark-to-market (BUG)
- **Lignes:** 223-228, 207-221
- **Problème:** `valeur_portefeuille` somme `p.get("montant_eur")` (montant investi / coût), pas la valeur de marché actuelle. Le commentaire l'admet ("estimation sans prix live"). Or `drawdown_scaler` compare ce "capital" au `pic_capital` pour mesurer le drawdown. Si `pic_capital` est lui-même mis à jour en mark-to-market (via `valeur_portefeuille` ou un autre mécanisme), le drawdown mesuré mélange cost-basis et market-value → faux drawdown. Si le portefeuille perd en valeur de marché mais que les montants investis ne changent pas, le drawdown reste à 0 et le scaler ne se déclenche jamais.
- **Fix:** Soit estimer la valeur de marché (via `prix_actuel` sur chaque position), soit clarifier que `pic_capital` est aussi en cost-basis et documenter la limite.

### BUG-5.8 — RISK_MIN_EUR = 0.0 → garde morte (MINEUR)
- **Lignes:** 48, 335-336
- **Problème:** `RISK_MIN_EUR = 0.0`. Le test `if montant_final < RISK_MIN_EUR` ne peut être vrai que pour un montant négatif, ce que `cap_dur` (qui retourne `min(...)` ≥ 0) ne produit jamais. Branche morte. Le commentaire ligne 48 indique que c'est désactivé ("minimum desactive"), mais le code mort reste.
- **Fix:** Soit supprimer la branche, soit mettre un seuil réel (ex. 5.0) si un minimum est souhaité, et documenter.

### BUG-5.9 — circuit_breaker: matching de date fragile (MINEUR)
- **Lignes:** 233-247
- **Problème:** Filtre les trades du jour via `t.get("date_fermeture","").startswith(datetime.now().strftime("%Y-%m-%d"))`. Si le format de `date_fermeture` diffère (ex. "26/08/2026 ..." ou ISO avec timezone), le `startswith` échoue silencieusement et le breaker ne se déclenche jamais. Utilise aussi l'horloge serveur (timezone non spécifiée).
- **Fix:** Normaliser `date_fermeture` à un format ISO fixe à l'écriture, et parser/comparer en date (pas `startswith`).

---

## Synthèse par sévérité

| Sévérité | Count | Items |
|----------|-------|-------|
| CRITIQUE | 2 | 1.1 (blacklist), 3.1 (_t NameError) |
| BUG | 14 | 1.2, 1.5, 2.1, 3.2, 3.3, 3.4, 3.5, 3.6, 4.1, 4.2, 4.3, 4.4, 5.1, 5.2, 5.3, 5.6, 5.7 |
| INCONSISTANCE | 5 | 1.3, 2.3, 5.4, 5.5 (+sous-items) |
| MINEUR | 8 | 1.4, 1.6, 2.2, 3.7, 3.8, 3.9, 3.10, 4.5, 4.6, 5.8, 5.9 |

## Priorité de correction recommandée
1. **3.1** `_t` non défini — casse silencieusement tout le fetch Revolut OHLCV (et rend BUG-3.4/3.6 plus impactant car CoinGecko devient la source principale).
2. **3.3** mélange EUR/USD dans `prix_actuel` — corrompt tous les seuils/SL sizing.
3. **1.1** blacklist vs mapping — PEPE/MATIC/FLOKI toujours à 0.
4. **5.1 / 5.2** fallback 6% qui contourne caps + trade sans edge — risque de sur-exposition.
5. **4.2** granularité CoinGecko OHLC ≠ timeframe — analyse multi-timeframe invalide.
6. **3.2** RSI off-by-one — crash sur len==15.
7. **5.3** drawdown_scaler non borné — amplification de taille non maîtrisée.
8. **3.4** volumes CoinGecko jamais assignés — VWAP toujours mort sur cette source.
