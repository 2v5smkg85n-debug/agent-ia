# Bug Report: paper_trading.py

**File:** `/tmp/agent-ia-inspect/paper_trading.py` (1954 lines)
**Scan date:** 2026-08-26

---

## CRITICAL BUGS

### BUG-01: `gain_pct` undefined — `NameError` in `fermer_position` (line 1394)

`ae.memoriser_trade()` is called with `gain_pct=gain_pct`, but `gain_pct` is never defined in `fermer_position`. Only `gain` (line 1306) and `variation` (parameter, the percentage) exist. This throws `NameError: name 'gain_pct' is not defined`, caught by the `except` at line 1411, so auto-evolution memory **never records any trade**.

```python
# Line 1394 (BROKEN):
gain_pct=gain_pct,
```

**Fix:** Use `variation` (which is the gain percentage):
```python
gain_pct=variation,
```

---

### BUG-02: `t.get("date", "")` uses wrong field name — daily loss check NEVER fires (line 1425)

```python
trades_aujourdhui = [t for t in pf.get("trades_fermes", []) if t.get("date", "").startswith(...)]
```

Trade dicts store the close timestamp as `"date_fermeture"` (line 1295/1324), **not** `"date"`. So `t.get("date", "")` always returns `""`, and `"".startswith(...)` is always `False`. Result: `trades_aujourdhui` is **always empty**. This means:
- The daily loss limit (`PERTE_JOUR_MAX_PCT`, line 1428) **never triggers**
- The max trades per day limit (`MAX_TRADES_PAR_JOUR`, line 1444) **never triggers**

Both risk management features are dead.

**Fix:**
```python
trades_aujourdhui = [t for t in pf.get("trades_fermes", []) if t.get("date_fermeture", "").startswith(datetime.now().strftime("%Y-%m-%d"))]
```

---

### BUG-03: `p.get("montant", 0)` uses wrong field name — capital calculation ignores open positions (lines 968, 1427)

Positions store their EUR value as `"montant_eur"` (line 1067), **not** `"montant"`. But two capital calculations use the wrong field:

```python
# Line 968 (drawdown check in ouvrir_position):
capital_actuel = pf["liquidites"] + sum(p.get("montant", 0) for p in pf.get("positions", []))

# Line 1427 (daily loss check in tick):
capital_actuel = pf["liquidites"] + sum(p.get("montant", 0) for p in pf.get("positions", []))
```

`p.get("montant", 0)` always returns `0`, so `capital_actuel` = `liquidites` only. Open positions are ignored. This means:
- The drawdown reduction check (line 969) compares **liquidites only** against 95% of initial capital, triggering false drawdowns when capital is tied up in positions.
- The daily loss threshold (line 1428) is calculated against liquidites only, not total capital.

**Fix:** Use `p.get("montant_eur", 0)`:
```python
capital_actuel = pf["liquidites"] + sum(p.get("montant_eur", 0) for p in pf.get("positions", []))
```

---

### BUG-04: `circuit_breaker` field never updated — consecutive-loss protection is dead (line 1432)

```python
pertes_consec = pf.get("circuit_breaker", {}).get("consecutive_losses", 0)
```

Two problems:
1. **Never written:** `fermer_position` never updates `pf["circuit_breaker"]` or any consecutive-loss counter. The field is never set anywhere in this file. So `pf.get("circuit_breaker", {})` returns `{}` (default), and `.get("consecutive_losses", 0)` always returns `0`.
2. **Structure mismatch:** From production data, `pf["circuit_breaker"]` is stored as a **boolean** (`False`), not a dict. Calling `.get()` on a boolean raises `AttributeError: 'bool' object has no attribute 'get'`, which would crash `tick()`.

**Fix:** Either:
- Store consecutive losses as a top-level field and update it in `fermer_position`:
```python
# In fermer_position, after computing gain:
if gain < 0:
    pf["pertes_consecutives"] = pf.get("pertes_consecutives", 0) + 1
else:
    pf["pertes_consecutives"] = 0

# In tick():
pertes_consec = pf.get("pertes_consecutives", 0)
```
- Or guard against non-dict values:
```python
_cb = pf.get("circuit_breaker", {})
if not isinstance(_cb, dict):
    _cb = {}
pertes_consec = _cb.get("consecutive_losses", 0)
```

---

### BUG-05: `prix` undefined in `ouvrir_position` — regime detection is dead code (line 989)

```python
# Line 988-996:
try:
    sma50 = prix.get("sma50", None)   # 'prix' is not defined in this scope!
    if sma50 and prix_actuel:
        if prix_actuel > sma50 * 1.02:
            montant = montant * 1.2
        elif prix_actuel < sma50 * 0.98:
            montant = montant * 0.5
except:
    pass
```

The function signature is `def ouvrir_position(pf, signal, prix_actuel):` — `prix_actuel` is a **float** (scalar), not a dict. There is no variable named `prix` in scope. `prix.get("sma50", None)` raises `NameError`, caught by the bare `except: pass`. The entire bull/bear regime detection block **never executes**.

**Fix:** Either remove this dead block, or pass an OHLCV/SMA dict to the function and reference it correctly.

---

### BUG-06: Unprotected `from gestion_risque import GROUPES_CORRELES` — crashes if module missing (line 953)

```python
# Line 952-953 (NOT inside any try/except):
# ANTI-CORRELATION: si on a deja une position sur un actif correle, on reduit
from gestion_risque import GROUPES_CORRELES
```

Earlier at line 792, `from gestion_risque import calculer_taille` is inside a `try/except ImportError`. If `gestion_risque` is missing, the sizing fallback works, but then line 953 raises `ImportError` **outside any try/except**, crashing `ouvrir_position`. This is inconsistent — the anti-correlation import should be guarded the same way.

**Fix:** Wrap in try/except:
```python
try:
    from gestion_risque import GROUPES_CORRELES
except ImportError:
    GROUPES_CORRELES = []
```

---

### BUG-07: `SL-RETARD` format string has double `%%` (line 1147)

```python
positions_a_fermer.append((pos, prix_actuel, f"SL-RETARD (perte {variation:+.1f}%, SL={-_sl_check}%%)", variation))
```

In Python f-strings, `%%` is **not** an escape sequence — it produces two literal `%` characters. The output is `SL=-1.0%%` (double percent, and a spurious negative sign). Should be a single `%`.

**Fix:**
```python
f"SL-RETARD (perte {variation:+.1f}%, SL={_sl_check}%)"
```

---

## FIELD NAME / DATA ISSUES

### BUG-08: `SUIAUSDT` / "Sui Alpha" is not a real cryptocurrency (line 134)

```python
"SUIAUSDT": {"nom": "Sui Alpha", "marche": "crypto", "source": "binance"},
```

"Sui Alpha" is not a known cryptocurrency. The symbol `SUIAUSDT` does not exist on Binance. Production logs show it always returns price `0.00`. This is likely an erroneous/fictitious entry. `SUI` already exists at line 130.

**Fix:** Remove the `SUIAUSDT` entry.

---

### BUG-09: `_niveau_performance` uses `prix_actuel` field that positions never have (line 518)

```python
val = liq + sum(p.get("quantite", 0) * p.get("prix_actuel", p.get("prix_entree", 0)) for p in pos)
```

Position dicts never contain a `"prix_actuel"` key (it's not set in `ouvrir_position`). So this always falls back to `prix_entree` (cost basis). The performance level is computed on **cost basis, not actual market value** — unrealized PnL is ignored. The conviction bonus (`_niveau_performance`) only changes when positions close, not as the market moves.

**Fix:** Pass current prices to `_niveau_performance`, or fetch them:
```python
def _niveau_performance(pf, prix_actuels=None):
    ...
    val = liq + sum(p.get("quantite", 0) * (prix_actuels or {}).get(p["symbole"], p.get("prix_entree", 0)) for p in pos)
```

---

### BUG-10: `analyser_signaux_ia` references non-existent non-crypto markets (lines 356-386)

`MARCHES_PAPER` contains **only crypto** markets (all with `"marche": "crypto"`). But `analyser_signaux_ia` filters to non-crypto (line 356-358):
```python
prix_non_crypto = {s: p for s, p in prix_actuels.items()
                   if MARCHES_PAPER.get(s, {}).get("marche") != "crypto"}
```
This is always empty → function returns `[]` at line 359. The entire function (lines 350-465), including the `mots_cles` block referencing Apple/Tesla/Nvidia/Or/Petrole/S&P/Nasdaq/DAX/CAC (lines 374-387), is **dead code**.

Similarly, `_NOMS_VERS_SYMBOLE` (lines 1874-1896) maps to non-crypto symbols (`GC=F`, `AAPL`, `TSLA`, `^GSPC`, etc.) that are **not in `MARCHES_PAPER`**. `acheter_manuel` rejects them at line 1838. So the advertised `achat or`, `achat apple`, `achat cac 40` commands always fail.

**Fix:** Either re-add non-crypto markets to `MARCHES_PAPER`, or remove the dead code and update the help text.

---

### BUG-11: `prix_binance` function name is misleading (lines 205-212)

```python
def prix_binance(symbole):
    """Prix via Revolut X (API publique, EUR). Remplace Binance."""
```

The function is named `prix_binance` but the docstring says "Prix via Revolut X". All `MARCHES_PAPER` entries have `"source": "binance"` which actually means Revolut X. This causes confusion throughout the codebase (e.g., line 263 comment, line 1765 source check).

**Fix:** Rename to `prix_revolut` or `prix_crypto`, and update the `source` field in `MARCHES_PAPER` to `"revolut"`.

---

### BUG-12: `get_prix_secours` vs `get_prix_revolut` — different function names (lines 209, 1775)

```python
# Line 209 (in prix_binance):
p = pr.get_prix_revolut(symbole)

# Line 1775 (in _check_crypto_sl_rapide):
_p = pr.get_prix_secours(_s)
```

Two different function names from the `prix_revolut` module. If `get_prix_secours` doesn't exist, the crypto SL check silently fails (caught by try/except at line 1823-1826). If it does exist, it's unclear why two different functions are used for the same purpose.

**Fix:** Use a consistent function name, or verify both exist in the `prix_revolut` module.

---

## CONFIG / CONSTANT ISSUES

### BUG-13: `STALE_DUREE_MAX` defined twice (lines 71 and 79)

```python
# Line 71:
STALE_DUREE_MAX = 180           # position stale apres 3h (libere le capital plus vite)
# Line 79 (duplicate):
STALE_DUREE_MAX = 180           # position stale apres 3h (libere le capital plus vite)
```

Same value, but the duplicate is confusing and error-prone. If one is changed, the other silently overrides it.

**Fix:** Remove the duplicate at line 79.

---

### BUG-14: Stale comment on `EXTEND_TP_PCT` (line 68)

```python
EXTEND_TP_PCT = 4.0       # TP monte (2.0% -> 4.0%) une fois en profit
```

The comment says "2.0% -> 4.0%", but `TAKE_PROFIT_PCT = 3.0` (line 61), not 2.0%. The comment is stale.

**Fix:** `# TP monte (3.0% -> 4.0%) une fois en profit`

---

### BUG-15: Stale comment on `EXTEND_DUREE_MAX` (line 69)

```python
EXTEND_DUREE_MAX = 480    # cap duree des positions extended (8h, vs 90min normal)
```

"90min normal" is wrong — `SORTIE_DUREE_MIN = 720` (12h). The comment is stale.

**Fix:** `# cap duree des positions extended (8h, vs 12h normal)`

---

### BUG-16: Stale comment at line 1234 — wrong threshold value

```python
if variation >= BREAKEVEN_SEUIL:        # >= 0.60% : protégé, respire 4h
```

`BREAKEVEN_SEUIL = 1.5` (line 80), not 0.60. The comment says "0.60%" but the code checks 1.5%.

**Fix:** `# >= 1.5% : protégé, respire 4h`

---

### BUG-17: Stale comment on `SEUIL_BENEFICE_MIN` (lines 73-74)

```python
# Fermer a +0.05% = perte nette (frais 0.2%). Donc on n'accepte que gain >= 0.30%.
SEUIL_BENEFICE_MIN = 0.50       # 0.50% : couvre les 0.2% de frais + 0.3% de marge nette
```

Line 73 says "gain >= 0.30%" but the constant is `0.50`. Inconsistent.

**Fix:** `# Donc on n'accepte que gain >= 0.50%.`

---

### BUG-18: Stale comment on SCALPING mode (line 87)

```python
# MODE SCALPING (SCALPING=1): boucle 5 min, TP 3%, SL 1%, timeframe 1h
```

But SCALPING sets `TAKE_PROFIT_PCT = 4.0` (line 91), not 3%.

**Fix:** `# ...TP 4%, SL 1%, timeframe 1h`

---

### BUG-19: Stale docstring/comments — "30 min" boucle interval (lines 19, 1920)

```python
# Line 19 (docstring):
python paper_trading.py boucle        # tourne en continu (30 min)

# Line 1920 (aide):
python paper_trading.py boucle        Continu (30 min)
```

`INTERVALLE_BOUCLE = 300` (5 min), not 30 min.

**Fix:** Change "30 min" to "5 min" in both places.

---

## HARDCODED VALUES THAT SHOULD REFERENCE CONSTANTS

### BUG-20: Hardcoded `80 EUR` threshold (lines 1052, 1055)

```python
if montant > 0 and pf["liquidites"] >= 80:    # line 1052
    ...
if pf["liquidites"] < 80:                      # line 1055
    return False
```

80 EUR = 8% of 1000 = `CAPITAL_INITIAL * RISK_PAR_TRADE`. Hardcoded, so if `CAPITAL_INITIAL` changes, this threshold is wrong.

**Fix:**
```python
_SEUIL_LIQUIDITE = CAPITAL_INITIAL * RISK_PAR_TRADE
if pf["liquidites"] < _SEUIL_LIQUIDITE:
    return False
```

---

### BUG-21: Hardcoded `0.05` (5% minimum) (line 1053)

```python
_min_absolu = pf["liquidites"] * 0.05  # 5% minimum absolu
```

Should be a named constant like `MIN_PCT_LIQUIDITES = 0.05`.

---

### BUG-22: Hardcoded thresholds in stale/duration logic (line 1248)

```python
if variation >= 0.2 or variation <= -1.0:
```

`0.2` = frais aller-retour (`FRAIS_TRANSACTION * 2 * 100`), `1.0` = `STOP_LOSS_PCT`. Should reference the constants.

**Fix:**
```python
if variation >= FRAIS_TRANSACTION * 2 * 100 or variation <= -STOP_LOSS_PCT:
```

---

### BUG-23: Hardcoded `0.45` gain threshold (line 1236)

```python
elif variation >= 0.45:                 # bon gain non protégé: respire 3h
```

No constant defined for this 0.45% threshold.

---

### BUG-24: Hardcoded `0.30` cap in meta sizing fallback (line 802)

```python
montant = pf["liquidites"] * min(RISK_PAR_TRADE * 1.5, 0.30)
```

`0.30` (30%) should reference `RISK_MAX_TRADE` (0.50) or a dedicated constant. Currently `RISK_PAR_TRADE * 1.5 = 0.12`, so the `0.30` cap never binds — but it's still a magic number.

---

### BUG-25: Hardcoded fallback `1000` in multiple places (lines 515, 969, 1332)

```python
# Line 515:
cap = pf.get("capital_initial", 1000)
# Line 969:
pf.get("capital_initial", 1000)
# Line 1332:
pf.get("capital_initial", 1000.0)
```

Should use `CAPITAL_INITIAL` constant instead of hardcoded `1000`.

---

### BUG-26: Hardcoded `top5` list (line 265)

```python
top5 = ["BTCUSDT", "ETHUSDT", "SOLUSDT", "BNBUSDT", "XRPUSDT"]
```

Should reference `EXTEND_CRYPTOS` or a dedicated `TOP_CRYPTOS` constant.

---

### BUG-27: Hardcoded `"BTCUSDT"` as peer (line 884)

```python
_peer = "BTCUSDT" if _is_crypto and _sym != "BTCUSDT" else None
```

Should reference a named constant like `PEER_CRYPTO = "BTCUSDT"`.

---

## DEAD CODE

### BUG-28: `ajouter` imported but never used (line 31)

```python
from agent import disponible, appeler_ia, notify_ifft, ajouter
```

`ajouter` is never called anywhere in this file. Dead import.

---

### BUG-29: `import re` only used in dead code (line 26)

`re` is only used in `prix_perplexity_fallback` (line 239), which is never called (commented out at line 285-286). Effectively a dead import.

---

### BUG-30: `prix_perplexity_fallback` is dead code (lines 225-252)

The function is defined but never called. The call site was commented out:
```python
# Line 285-286:
# Plus de fallback Perplexity pour les prix (retournait de faux prix)
# Les symboles sans prix sont simplement ignores ce cycle
```

---

### BUG-31: `strategies_gagnantes()` is effectively dead (lines 296-298)

Only called by `analyser_signaux_ia` (line 352), which is itself dead code (see BUG-10).

---

### BUG-32: `prix_par_source["yahoo"]` is never populated (line 257)

```python
prix_par_source = {"binance": [], "yahoo": []}
```

No market in `MARCHES_PAPER` has `"source": "yahoo"`, so `prix_par_source["yahoo"]` is always empty. The Yahoo price loop (lines 279-283) never iterates.

---

### BUG-33: `tp_optimal_pro` / `sl_optimal_pro` set but never read (lines 1515-1517)

```python
if params_pro.get("tp"):
    sig["tp_optimal_pro"] = params_pro["tp"]
if params_pro.get("sl"):
    sig["sl_optimal_pro"] = params_pro["sl"]
```

These signal fields are set but never read in `ouvrir_position` (which reads `tp_adaptatif` / `sl_adaptatif`). The trader_pro TP/SL recommendations are silently discarded.

---

### BUG-34: TP/SL computed twice redundantly (lines 1132-1143 vs 1150-1159)

The `_tp_check/_sl_check` block (lines 1132-1143, used for SL-RETARD detection) and the `_tp/_sl` block (lines 1150-1159, used for actual TP/SL) have **identical logic** (SCALPING → adaptatif → meta_tuning → constants). This is duplicated code.

**Fix:** Compute once and reuse:
```python
_tp, _sl = _tp_check, _sl_check
```

---

## SL/TP LOGIC ISSUES

### BUG-35: SL-RETARD bypasses trailing stop (lines 1146-1148)

```python
if variation <= -_sl_check:
    positions_a_fermer.append((pos, prix_actuel, f"SL-RETARD ...", variation))
    continue  # <-- skips trailing stop check
```

The SL-RETARD check uses the **fixed** SL percentage (e.g., -1.0%) and fires before the trailing stop is evaluated. If a position peaked at +4% (trailing stop at +3%) but price dropped to -1% in one tick, the SL-RETARD closes at -1% instead of the trailing stop closing at +3%. Both close at `prix_actuel` (the same price), so the realized loss is the same. However, the `raison` is misleading — it says "SL-RETARD" when the trailing stop should have been the active exit. Consider checking the trailing stop first.

---

### BUG-36: Partial close doesn't update `prix_peak` (line 1205-1206)

After `fermer_position_partielle` reduces `quantite` and `montant_eur`, the `prix_peak` field is unchanged. The trailing stop uses `_pic = pos.get("prix_peak", prix_entree)` (line 1170), which is independent of quantity, so this is not a calculation error. However, if a partial close happens and then price drops, the trailing stop is based on the old peak — this is correct behavior but could be confusing.

---

### BUG-37: `montant` can be 0 or negative if liquidites >= 80 but sizing reduces to ~0 (lines 1052-1058)

If `montant` is reduced to near-zero by spread/regime filters but `liquidites >= 80`, the clamp at line 1054 bumps it to 5% minimum. But if `montant` is **exactly 0** (e.g., from some edge case), `if montant > 0` at line 1052 is `False`, the clamp is skipped, and the code proceeds to line 1057:
```python
frais = montant * FRAIS_TRANSACTION  # 0
quantite = (montant - frais) / prix_actuel  # 0
pf["liquidites"] -= montant  # no change
```
A position with `quantite: 0` is opened. This is a degenerate position that will never gain/lose value.

**Fix:** Add a guard after all sizing adjustments:
```python
if montant <= 0:
    return False
```

---

## PRICE=0 HANDLING GAPS

### BUG-38: Division by zero if `prix_entree` is 0 (lines 1004, 1129, 1698, 1714)

```python
# Line 1004 (pyramiding in ouvrir_position):
_var = (prix_actuel - _pos_existante["prix_entree"]) / _pos_existante["prix_entree"] * 100

# Line 1129 (verifier_sorties):
variation = (prix_actuel - prix_entree) / prix_entree * 100

# Line 1698 (afficher_solde):
var = (prix_actuel - p["prix_entree"]) / p["prix_entree"] * 100

# Line 1714 (afficher_positions):
var = (prix_actuel - p["prix_entree"]) / p["prix_entree"] * 100
```

Entry validation (line 561) blocks `prix_actuel <= 0`, so `prix_entree` should never be 0 for new positions. But if a corrupted JSON file has `prix_entree: 0`, these lines raise `ZeroDivisionError`. Lines 1129 and 1004 are not inside try/except (line 1129 is before any try in the loop; line 1004 is in a bare block).

**Fix:** Guard against zero:
```python
if prix_entree <= 0:
    continue  # or skip
variation = (prix_actuel - prix_entree) / prix_entree * 100
```

---

## OTHER ISSUES

### BUG-39: Relative file paths for `classement_strategies.json` (lines 918, 1111)

```python
_cs = json.load(open("classement_strategies.json"))
```

Uses relative path, while other file accesses use `os.path.join(DOSSIER, ...)` (e.g., line 312, 636, 1639). If the script is run from a different working directory, these will fail with `FileNotFoundError` (caught by except, but the conviction sizing silently doesn't work).

**Fix:**
```python
_cs = json.load(open(os.path.join(DOSSIER, "classement_strategies.json")))
```

---

### BUG-40: `fermer_position_partielle` only appends to `trades_fermes`, not `historique` (line 1297)

```python
# Line 1297 (partial close):
pf["trades_fermes"].append(trade)

# Line 1326-1328 (full close):
pf["historique"].append(trade)
pf.setdefault("trades_fermes", []).append(trade)
```

Partial closes are recorded in `trades_fermes` but NOT in `historique`. So `afficher_historique` (which reads `pf["historique"]`) will not show partial TP closes. Inconsistent.

**Fix:** Also append to `historique` in `fermer_position_partielle`:
```python
pf["historique"].append(trade)
pf["trades_fermes"].append(trade)
```

---

### BUG-41: `_mult` may be undefined in Telegram notification (line 1091)

```python
try:
    if _mult and _mult != 1.0:
        _conv = f" (conviction x{_mult:.2f})"
except Exception:
    pass
```

`_mult` is only defined inside the CONVICTION SIZING block (line 919), which is inside a `try/except`. If that block fails (e.g., `classement_strategies.json` not found → `FileNotFoundError`), `_mult` is never assigned. Line 1091 raises `NameError`, caught by the inner `except Exception: pass`. The conviction annotation is silently lost. Not a crash, but a latent bug.

**Fix:** Initialize `_mult = 1.0` before the CONVICTION SIZING block.

---

### BUG-42: `datetime.utcnow()` is deprecated (line 1437)

```python
heure_utc = datetime.utcnow().hour
```

`datetime.utcnow()` is deprecated in Python 3.12+. Should use `datetime.now(timezone.utc)`.

**Fix:**
```python
from datetime import timezone
heure_utc = datetime.now(timezone.utc).hour
```

---

### BUG-43: Misleading comment — "Restaurer les signaux bloques" (line 1497)

```python
if len(tous_signaux) < signaux_avant_app:
    # Restaurer les signaux bloques mais avec score reduit
    print(f"  [APPRENTISSAGE] {signaux_avant_app - len(tous_signaux)} signaux filtres")
```

The comment says "Restaurer les signaux bloques" (restore blocked signals), but the code does **not** restore them — it just prints how many were filtered. The signals are gone.

**Fix:** Remove or correct the comment.

---

### BUG-44: `afficher_solde` / `afficher_positions` / `valeur_totale` fetch ALL prices when called without `prix` (lines 1669, 1680, 1710)

```python
def valeur_totale(pf, prix=None):
    if not prix:
        prix = tous_les_prix()  # fetches ALL market prices (30+ seconds)
```

When called from CLI (`solde` command → `afficher_solde()` → `valeur_totale`), this triggers a full price fetch taking 30+ seconds. This is a performance issue, not a correctness bug.

---

### BUG-45: `_entree_bloquee_weekend` redundant condition (line 557)

```python
return _jour == 4 or _jour >= 5
```

`_jour == 4` (Friday) is already covered by `_jour >= 4`. The condition could be simplified to `_jour >= 4`. Not a bug, just redundant logic.

---

## SUMMARY

| Severity | Count | Key Issues |
|----------|-------|------------|
| **CRITICAL** | 7 | `gain_pct` undefined, daily loss check dead, capital calc ignores positions, circuit breaker dead, `prix` undefined, unprotected import, format string `%%` |
| **DATA/FIELD** | 5 | Fake `SUIAUSDT` symbol, performance level uses cost basis, dead IA function, misleading `prix_binance` name, inconsistent `get_prix_*` |
| **CONFIG** | 7 | Duplicate `STALE_DUREE_MAX`, 5 stale comments, "30 min" docstring |
| **HARDCODED** | 8 | 80 EUR threshold, 5% minimum, frais/SL thresholds, 0.45 gain, 0.30 cap, `1000` fallback, `top5` list, BTCUSDT peer |
| **DEAD CODE** | 7 | Unused `ajouter`, unused `re`, dead `prix_perplexity_fallback`, dead `strategies_gagnantes`, empty yahoo list, unread `tp_optimal_pro`, duplicated TP/SL computation |
| **SL/TP LOGIC** | 3 | SL-RETARD bypasses trailing, partial close peak, zero montant position |
| **PRICE=0** | 1 | Division by zero on corrupted `prix_entree` |
| **OTHER** | 7 | Relative file paths, partial close not in historique, undefined `_mult`, deprecated `utcnow`, misleading comment, performance issue, redundant condition |
| **TOTAL** | **45** | |
