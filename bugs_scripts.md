# Audit des bugs — Scripts inspectés

Référence (source de vérité) — `paper_trading.py` :
- `MAX_POSITIONS = 5` (ligne 47)
- `RISK_PAR_TRADE = 0.08` (8 %) (ligne 50)
- `TAKE_PROFIT_PCT = 3.0` (ligne 61)
- `STOP_LOSS_PCT = 1.0` (ligne 62)
- `EXTEND_TP_PCT = 4.0` (ligne 68)

Structure réelle de `paper_trading.json` (champs vérifiés) :
- Top-level : `liquidites`, `capital_initial` (=1000.0), `total_frais`, `pic_capital`, `positions`, `trades_fermes`, `historique`, `dernier_tick`
- Trades fermés : `gain_eur`, `raison`, `variation_pct`, `montant_eur`, `frais_total`, `date_fermeture`, `symbole`, `prix_entree`, `prix_sortie`, `quantite`
- Positions : `symbole`, `montant_eur`, `prix_entree`, `quantite`, `date_ouverture`, `strategie`, `source`
- ⚠️ Aucune clé `pnl`, `raison_fermeture`, `total_fais` ou `montant` n'existe dans le JSON.

---

## 1. dashboard_premium.py

### BUG 1 — TP/SL hardcodés ne correspondent pas au bot (build_positions_chart)
- **Lignes 173-175** :
  ```python
  TAKE_PROFIT_PCT = 2.0
  STOP_LOSS_PCT = 1.5
  EXTEND_TP_PCT = 4.0
  ```
- `paper_trading.py` utilise `TAKE_PROFIT_PCT = 3.0` et `STOP_LOSS_PCT = 1.0`.
- Conséquence : les lignes TP/SL affichées sur les graphiques chandeliers (lignes 205-209, 244, 278-280) sont fausses (TP à +2 % au lieu de +3 %, SL à -1.5 % au lieu de -1 %).
- **Correctif** : `TAKE_PROFIT_PCT = 3.0`, `STOP_LOSS_PCT = 1.0` (ou importer depuis `paper_trading`).

### BUG 2 — TP/SL hardcodés dans la route /api/prices
- **Lignes 1101-1102, 1107** :
  ```python
  tp = prix_entree * 1.02     # 2 %
  sl = prix_entree * 0.985    # 1.5 %
  ...
  "tp_pct": 2.0, "sl_pct": 1.5,
  ```
- Même incohérence que BUG 1 : le JS live affiche des TP/SL à 2 %/1.5 % alors que le bot trade à 3 %/1 %.
- **Correctif** : `tp = prix_entree * 1.03`, `sl = prix_entree * 0.99`, `"tp_pct": 3.0, "sl_pct": 1.0`.

### BUG 3 — Capital total live sous-estimé (champ `montant` manquant)
- **Ligne 382 (JS)** : `totalVal += (p.montant || 0) + (p.pnl || 0);`
- La réponse `/api/prices` (lignes 1103-1108) ne renvoie **pas** de champ `montant` :
  ```python
  result["positions"].append({
      "sym": sym, "prix": prix_actuel, "pnl": round(pnl_eur, 2),
      "pnl_pct": round(pnl_pct, 1), "var24h": var_24h,
      "tp": tp, "sl": sl, "entry": prix_entree,
      "tp_pct": 2.0, "sl_pct": 1.5,
  })
  ```
- `p.montant` est donc toujours `undefined` → `totalVal` n'accumule que les PnL, pas le capital investi. Le "Capital total" mis à jour en live (lignes 387, 389) est sous-estimé du montant total investi dans les positions.
- **Correctif** : ajouter `"montant": round(montant, 2),` au dictionnaire renvoyé (ligne 1104).

### BUG 4 — Libellé de source des prix obsolète
- **Ligne 663** : `Donnees CoinGecko temps reel`
- Or le code utilise désormais Revolut X (ligne 62 : `import prix_revolut as pr`), plus CoinGecko.
- **Correctif** : `Donnees Revolut X temps reel`.

### BUG 5 — Texte "Live 30s" incohérent avec le meta refresh
- **Ligne 334** : `Live 30s` mais le `<meta http-equiv="refresh" content="120">` (ligne 297) recharge la page toutes les 120 s. Le JS `setInterval(updateLive, 30000)` (ligne 401) ne fait que des mises à jour XHR partielles.
- Affichage trompeur : l'utilisateur croit à un refresh complet toutes les 30 s.
- **Correctif** : `Live 30s (XHR) · reload 120s` ou aligner le meta refresh à 30.

### BUG 6 — Barre de poids des maîtres peut déborder
- **Ligne 846** : `barre_w = int(poids * 100)`
- Quand `poids > 1.0` (maître sur-performant), `barre_w > 100` → la barre déborde de son conteneur CSS.
- **Correctif** : `barre_w = min(int(poids * 100), 100)`.

### NOTE — Champs `pnl` / `raison_fermeture` (gestion correcte)
- **Lignes 548-549** :
  ```python
  pnl = t.get("gain_eur", t.get("pnl", 0))
  raison = t.get("raison", t.get("raison_fermeture", "?"))
  ```
- La clé primaire `gain_eur` / `raison` est bien utilisée en premier (et existe dans le JSON). Les fallbacks `pnl` / `raison_fermeture` sont du code mort inoffensif (ces clés n'existent pas). **Pas un bug fonctionnel**, mais les fallbacks pourraient être supprimés pour la clarté.

### NOTE — Fallback `montant` inutile
- **Ligne 187** : `montant = p.get("montant_eur", p.get("montant", 0))` — la clé `montant` n'existe jamais dans le JSON. Fallback mort, inoffensif.

---

## 2. check_positions.py

### BUG 1 — Valeurs MAX_POSITIONS et RISK_PAR_TRADE hardcodées et FAUSSES
- **Ligne 7** :
  ```python
  print(f"MAX_POSITIONS: 3 | RISK_PAR_TRADE: 50%")
  ```
- `paper_trading.py` : `MAX_POSITIONS = 5`, `RISK_PAR_TRADE = 0.08` (8 %). Les deux valeurs affichées (3 et 50 %) sont erronées.
- Conséquence : le script affiche des paramètres de risque complètement faux (50 % de risque par trade au lieu de 8 %, 3 positions au lieu de 5).
- **Correctif** :
  ```python
  import paper_trading as pt
  print(f"MAX_POSITIONS: {pt.MAX_POSITIONS} | RISK_PAR_TRADE: {pt.RISK_PAR_TRADE*100:.0f}%")
  ```

---

## 3. bilan_500.py

### BUG 1 — Comparaison gain moyen net vs brut incohérente
- **Ligne 73** : `old_gain = sum(t.get("gain_eur", 0) for t in trades_old)` → **brut** (frais non déduits).
- **Ligne 76** : `Avant (80EUR): {len(trades_old)} trades, {old_gain:+.2f}EUR net` → libellé **"net"** alors que c'est du brut.
- **Ligne 79** : `gain_moyen_500 = (total_gain - frais) / len(trades_500)` → **net**.
- **Ligne 80** : `gain_moyen_80 = old_gain / max(len(trades_old), 1)` → **brut**.
- **Lignes 83-84** : le ratio `gain_moyen_500 / gain_moyen_80` compare du **net** à du **brut** → résultat faussé.
- **Correctif** : calculer les frais des trades anciens et soustraire :
  ```python
  old_frais = sum(t.get("frais_total", 0) for t in trades_old)
  old_net = old_gain - old_frais
  gain_moyen_80 = old_net / max(len(trades_old), 1)
  ```
  et corriger le libellé ligne 76 (`{old_net:+.2f}EUR net`).

### BUG 2 — Capital initial hardcodé
- **Lignes 68-69** :
  ```python
  print(f"  Capital initial: 1000.00EUR")
  print(f"  Rendement: {(capital-1000)/1000*100:+.2f}%")
  ```
- Le JSON contient `capital_initial` (= 1000.0). La valeur hardcodée coïncide aujourd'hui mais reste fragile.
- **Correctif** :
  ```python
  cap_init = pf.get("capital_initial", 1000)
  print(f"  Capital initial: {cap_init:.2f}EUR")
  print(f"  Rendement: {(capital-cap_init)/cap_init*100:+.2f}%")
  ```

### BUG 3 — Filtre de date par comparaison de chaînes (fragile)
- **Lignes 11-12** : `t.get("date_fermeture", "") >= "2026-08-23 22"`
- Ne fonctionne correctement que parce que les dates sont au format zéro-padded `"%Y-%m-%d %H:%M"`. Toute date non padding casserait le filtre.
- **Correctif** : parser avec `datetime.strptime` et comparer des objets `datetime`.

### NOTE — Noms de champs corrects
- `gain_eur`, `raison`, `variation_pct`, `montant_eur`, `frais_total`, `date_fermeture` sont tous utilisés correctement (lignes 20-23, 42-45, 73). **Pas de mismatch de champs.**

### BUG 4 — Label "Avant (80EUR)" non vérifié
- **Ligne 76** : suppose que les trades antérieurs utilisaient des positions de 80 EUR, mais aucun filtre ne le garantit (seul le filtre date est appliqué). Libellé potentiellement trompeur.

---

## 4. close_all.py

### BUG 1 — Aperçu "Prochaine position" à 50 % (faux)
- **Ligne 25** : `print(f"Prochaine position: {pf['liquidites']*0.50:.2f}EUR (50%)")`
- `RISK_PAR_TRADE = 0.08` (8 %) dans `paper_trading.py`. Afficher 50 % induit l'utilisateur en erreur sur la taille de la prochaine position.
- **Correctif** : `pf['liquidites']*0.08` et libellé `(8%)`, ou importer `RISK_PAR_TRADE`.

### BUG 2 — Accès directs aux clés (KeyError potentiel)
- **Lignes 9, 14, 19** : `p["montant_eur"]`, `p["prix_entree"]`, `p["symbole"]` — lèvent `KeyError` si la clé est absente d'une position.
- **Ligne 10** : `pf["trades_fermes"].append(...)` — `KeyError` si la clé n'existe pas.
- **Correctif** : utiliser `.get("montant_eur", 0)`, etc., et `pf.setdefault("trades_fermes", [])`.

### BUG 3 — Date de fermeture hardcodée
- **Ligne 12** : `"date_fermeture": "2026-08-23 22:03"` — date figée. Acceptable pour un script one-shot, mais erronée si réutilisé à une autre date.
- **Correctif** : `datetime.now().strftime("%Y-%m-%d %H:%M")`.

### BUG 4 — Cohérence des données non mise à jour
- Le script ne recalcule ni `total_frais` ni `pic_capital` après fermeture. Mineur, mais le dashboard peut afficher un `pic_capital` périmé.

---

## 5. close_pepe.py

### BUG 1 — Aucun enregistrement du trade fermé (perte d'historique)
- Contrairement à `close_all.py` (qui ajoute une entrée à `trades_fermes`), ce script se contente de `pf["positions"].pop(i)` (ligne 9) et de créditer les liquidités (ligne 10).
- **Aucune entrée** dans `trades_fermes` : le trade PEPE disparaît de l'historique d'audit, cassant le calcul du PnL cumulé, du win rate, et l'apprentissage (`apprentissage_trader`).
- **Correctif** : ajouter une entrée `trades_fermes` (comme dans `close_all.py`) :
  ```python
  pf.setdefault("trades_fermes", []).append({
      **p,
      "date_fermeture": datetime.now().strftime("%Y-%m-%d %H:%M"),
      "gain_eur": 0,
      "prix_sortie": p["prix_entree"],
      "raison": "Fermeture manuelle PEPE",
      "variation_pct": 0,
      "frais_total": 0,
  })
  ```

### BUG 2 — Accès directs aux clés (KeyError potentiel)
- **Lignes 6, 7, 8, 10** : `pf["positions"]`, `p["symbole"]`, `p["montant_eur"]`, `p["prix_entree"]` — `KeyError` si la clé est absente.
- **Correctif** : `pf.get("positions", [])`, `p.get("symbole", "")`, etc.

### BUG 3 — Modification de liste pendant itération
- **Lignes 6-9** : `pf["positions"].pop(i)` pendant `enumerate(pf["positions"])`. Le `break` immédiat évite le bug dans la pratique, mais le pattern reste fragile si le `break` est un jour retiré.
- **Correctif** : filtrer et reconstruire la liste :
  ```python
  pepe = next((p for p in pf.get("positions", []) if "PEPE" in p.get("symbole", "")), None)
  ```

---

## 6. compare_perf.py

### BUG 1 — Faute de frappe `total_fais` (clé inexistante)
- **Ligne 17** :
  ```python
  frais = pf.get("total_fais", pf.get("total_frais", 0))
  ```
- La clé réelle est `total_frais`. `total_fais` n'existe pas → renvoie `None` → fallback sur `pf.get("total_frais", 0)` qui est correct. Donc **pas de bug fonctionnel**, mais la première clé est du code mort et la faute de frappe est trompeuse.
- **Correctif** : `frais = pf.get("total_frais", 0)`.

### BUG 2 — Capital initial hardcodé
- **Ligne 7** : `capital_initial = 1000.0`
- Le JSON contient `capital_initial`. Valeur identique aujourd'hui mais fragile.
- **Correctif** : `capital_initial = pf.get("capital_initial", 1000.0)`.

### BUG 3 — `pnl_total` calculé mais jamais affiché
- **Ligne 16** : `pnl_total = sum(t.get("gain_eur", 0) for t in trades)` — variable calculée (et qui est du **brut**, frais non déduits) mais jamais utilisée dans l'affichage. La ligne 64 affiche `frais` séparément à la place.
- Code mort / variable trompeuse. **Correctif** : supprimer la variable, ou l'afficher correctement en net.

### NOTE — Noms de champs corrects
- `gain_eur` est utilisé correctement partout (lignes 13, 14, 16, 25, 44, 45). **Aucun mismatch de champs** dans ce script — la seule erreur est la faute de frappe `total_fais` ci-dessus.

---

## Synthèse des correctifs prioritaires

| Priorité | Fichier | Bug | Impact |
|----------|---------|-----|--------|
| 🔴 Haute | check_positions.py:7 | MAX_POSITIONS=3 / RISK=50% (faux) | Affiche paramètres risque totalement erronés |
| 🔴 Haute | dashboard_premium.py:173-175 | TP=2% / SL=1.5% (faux) | TP/SL affichés ne correspondent pas au bot |
| 🔴 Haute | dashboard_premium.py:1101-1107 | TP=2% / SL=1.5% (faux, API) | Même bug côté API live |
| 🔴 Haute | dashboard_premium.py:382 + 1104 | champ `montant` manquant | Capital total live sous-estimé |
| 🔴 Haute | close_pepe.py | pas d'enregistrement trades_fermes | Perte d'historique / apprentissage cassé |
| 🟠 Moyenne | bilan_500.py:73-84 | comparaison net vs brut | Ratio gain moyen faussé |
| 🟠 Moyenne | close_all.py:25 | aperçu 50% (faux) | Induit en erreur sur taille position |
| 🟡 Basse | compare_perf.py:17 | typo `total_fais` | Code mort, pas d'impact fonctionnel |
| 🟡 Basse | compare_perf.py:7, bilan_500.py:68 | capital_initial hardcodé | Fragile si capital change |
| 🟡 Basse | dashboard_premium.py:663 | libellé CoinGecko obsolète | Affichage inexact |
| 🟡 Basse | dashboard_premium.py:846 | barre poids déborde | Cosmétique |
