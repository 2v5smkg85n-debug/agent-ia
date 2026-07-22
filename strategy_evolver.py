#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""strategy_evolver.py — Génération AUTONOME de stratégies + déploiement si valides.

L'agent écrit lui-même une nouvelle fonction stratégie, la valide, et la déploie
seulement si TOUS les gates passent. Aide l'évolution sans danger.

4 GATES obligatoires pour déployer:
1. Syntaxe + import sandbox
2. Look-ahead detection: CausalView (runtime) + analyse statique (regex)
   -> la stratégie ne peut lire QUE d[key][i], d[key][i-1], d[key][i-2]
3. Sanity: run sur bougies factices -> signaux valides (ACHAT/VENTE/None), pas de crash
4. Walk-forward: in-sample 70% + OOS 30%
   -> OOS_avg > 1.5% (profitable) ET < 40% (anti-leakage) ET win_rate >= 50% ET trades >= 5

Si tout passe: ajoute à strategies_evolved.json + regen strategies_evolved.py
-> backtest_moteur charge la nouvelle stratégie + regen backtests -> classement.

Cron 2x/semaine (dim/mer 04:00 UTC).
"""
import os, sys, json, re, time, random, importlib.util, subprocess, ast
from datetime import datetime
import backtest_moteur as bm
from indicateurs import historique_ohlcv, historique_ohlcv_long
from dotenv import load_dotenv
try:
    from sagesse_traders import sagesse_prompt
except Exception:
    sagesse_prompt = None
load_dotenv()

DOSSIER = os.path.dirname(os.path.abspath(__file__))
EVOLVED_JSON = os.path.join(DOSSIER, "strategies_evolved.json")
EVOLVED_PY = os.path.join(DOSSIER, "strategies_evolved.py")
LECONS = os.path.join(DOSSIER, "lecons_apprises.jsonl")
LOGDIR = os.path.join(DOSSIER, "logs")
LOG = os.path.join(LOGDIR, "strategy_evolver.log")

# LLM
GEMINI_KEY = os.getenv("GEMINI_API_KEY", "")
GEMINI_MODEL = os.getenv("GEMINI_MODEL", "gemini-2.0-flash")
GEMINI_URL = (f"https://generativelanguage.googleapis.com/v1beta/models/"
              f"{GEMINI_MODEL}:generateContent?key={GEMINI_KEY}")
PPLX_KEY = os.getenv("PPLX_API_KEY", "")
PPLX_URL = "https://api.perplexity.ai/chat/completions"
PPLX_MODEL = os.getenv("PPLX_MODEL", "sonar")

CRYPTOS = bm.ACTIFS["crypto"]
INTERVALLE = "1h"
N_BOUGIES = 17520  # BACKTEST LONG TERME: ~2 ans en 1h. OOS = ~730j (au lieu de 10j). Fetch pagine.
SPLIT = 0.70
NUM_RUN = datetime.utcnow().strftime("%H%M")

# Gates de déploiement
OOS_MIN = 1.5      # OOS_avg > 1.5% (profitable)
OOS_MAX = 40.0     # OOS_avg < 40% (anti-leakage: trop beau = fuite)
WIN_MIN = 50.0     # win_rate moyen >= 50%
TRADES_MIN = 5     # au moins 5 trades total (robuste, pas chance)


def varied_dummy(n=220):
    """Donnees factices MULTI-REGIMES (hausse, crash, range, recovery)
    pour que tout type de strategie (mean-reversion, trend, breakout) puisse
    emettre au moins un signal lors du sanity/causal test."""
    out = []
    p = 100.0
    for i in range(n):
        if i < n // 4:            # hausse (RSI haut, EMA croise up)
            p *= (1 + 0.004)
        elif i < n // 2:          # crash (RSI oversold, Bollinger bas touche)
            p *= (1 - 0.006)
        elif i < 3 * n // 4:      # range (Stochastic, oscillation)
            p *= (1 + 0.0015 * ((-1) ** i))
        else:                      # recovery
            p *= (1 + 0.0035)
        p += 0.4 * (i % 5 - 2)    # bruit
        out.append({"cloture": round(max(p, 1.0), 4)})
    return out


def exploration_seed():
    """Seed aleatoire pour forcer la DIVERSITE: chaque run explore un angle different.
    Evite que le LLM regenere la meme strategie (cache Perplexity / determinisme)."""
    focus = random.choice([
        "RSI (survente <35 / surachat >70)",
        "Bollinger (prix touche bb_bas / bb_haut)",
        "MACD (croisement ligne/signal)",
        "Stochastique (k/d cross, survente <20)",
        "Donchian (breakout de canal haut/bas)",
        "EMA (crossover 12/26)",
        "combinaison RSI + Bollinger (acheter quand RSI<35 ET prix<=bb_bas)",
        "combinaison Stochastique + RSI (double confirmation survente)",
        "combinaison MACD + EMA (momentum + trend)",
        "combinaison Donchian + RSI (breakout confirme)",
    ])
    trader = random.choice([
        "Buffett (contrarian, acheter sous-evalue)",
        "Rogers (acheter quand il y a du sang dans les rues)",
        "Soros (retournement apres extension extreme)",
        "Paul Tudor Jones (point de retournement, R:R eleve)",
        "Simons (pattern data-driven, frequent)",
        "Yass (expected value positive)",
        "Dalio (conditionnel au regime)",
    ])
    approche = random.choice([
        "mean-reversion (acheter apres une baisse, vendre apres une hausse)",
        "momentum (acheter sur acceleration haussiere)",
        "breakout (acheter sur cassure d'un niveau)",
        "divergence (prix fait un nouveau bas mais l'indicateur remonte)",
    ])
    return (f"EXPLORATION DE CE RUN (genere une strategie DIFFERENTE, ne recopie pas une strategie deja faite):\n"
            f"- Focus indicateur: {focus}\n"
            f"- Inspiration trader: {trader}\n"
            f"- Approche: {approche}\n"
            f"IMPORTANT: construis ta strategie autour de CETTE combinaison specifique.")


MUTATION_TYPES = [
    "changer un seuil numerique (ex: RSI 35->28, ou 70->75, ou ecart Bollinger 2.0->1.8)",
    "remplacer un indicateur par un autre equivalent (ex: Donchian -> Bollinger, RSI -> Stochastique)",
    "ajouter UNE condition de confirmation (ex: momentum MACD positif, pente EMA12 haussiere)",
    "modifier la condition de sortie/vente (ex: RSI>60 au lieu de >70, sortie sur EMA12<EMA26)",
    "retarder le signal d'un bar (confirmation sur i-1) pour reduire les faux signaux",
    "ajouter un filtre de volatilite via l'ecart Bollinger (bb_haut - bb_bas) pour ne trader qu'en regime modere",
    "resserrer les bornes d'entree (ex: RSI<30 au lieu de <35, exiger 2 confirmations)",
]


def mutation_type():
    return random.choice(MUTATION_TYPES)


MUTATION_PROMPT = """Tu es un quant trader expert. Voici une strategie QUI MARCHE (strategie parent):

```python
{parent_code}
```

Performances du parent: OOS {parent_oos}% | win {parent_win}% | {parent_trades} trades.

Cree une VARIANTE de cette strategie en MUTANT UN SEUL element:
- Mutation demandee: {mutation}

CONTRAINTES:
- Garde la structure generale du parent, change UN seul composant.
- La strategie mutee doit rester SIMPLE (max 2-3 conditions).
- Gestion None OBLIGATOIRE: verifie `if x is None: return None` avant TOUTE comparaison d'indicateur.
- Pas de look-ahead: uniquement d[key][i], d[key][i-1], d[key][i-2].
- Nom de fonction: strat_evolved_{num}

INDICATEURS DISPONIBLES dans d (utilise UNIQUEMENT ces cles, rien d'autre):
  d["clotures"], d["sma20"], d["sma50"], d["rsi"],
  d["bb_haut"], d["bb_bas"], d["macd_line"], d["macd_signal"],
  d["donchian_haut"], d["donchian_bas"], d["stoch_k"], d["stoch_d"],
  d["ema12"], d["ema26"]
  INTERDIT: d["atr"], d["volume"], d["bb_moyenne"] ou tout autre cle non listee (crash KeyError = rejet).

Reponds UNIQUEMENT avec la fonction Python dans un bloc ```python ... ```. Pas d'explication."""


def log(msg):
    line = f"[{datetime.utcnow():%Y-%m-%d %H:%M:%S} UTC] {msg}"
    print(line, flush=True)
    try:
        os.makedirs(LOGDIR, exist_ok=True)
        with open(LOG, "a") as fh:
            fh.write(line + "\n")
    except Exception:
        pass


# ============================================
# LLM
# ============================================
def call_gemini(prompt):
    import requests
    if not GEMINI_KEY:
        return None
    payload = {"contents": [{"parts": [{"text": prompt}]}],
               "generationConfig": {"temperature": 0.7, "maxOutputTokens": 1000}}
    for delay in [10, 30, None]:
        try:
            r = requests.post(GEMINI_URL, json=payload, timeout=90)
            if r.status_code == 429 and delay is not None:
                time.sleep(delay); continue
            r.raise_for_status()
            return r.json()["candidates"][0]["content"]["parts"][0]["text"]
        except Exception as e:
            if delay is None:
                log(f"Gemini indispo: {e}")
                return None
            time.sleep(delay)
    return None


def call_perplexity(prompt):
    import requests
    if not PPLX_KEY:
        return None
    headers = {"Authorization": f"Bearer {PPLX_KEY}", "content-type": "application/json"}
    payload = {"model": PPLX_MODEL, "max_tokens": 1200,
               "messages": [{"role": "user", "content": prompt}]}
    try:
        r = requests.post(PPLX_URL, headers=headers, json=payload, timeout=90)
        r.raise_for_status()
        return r.json()["choices"][0]["message"]["content"]
    except Exception as e:
        log(f"Perplexity indispo: {e}")
        return None


def call_llm(prompt):
    t = call_gemini(prompt)
    if t:
        return t, "gemini"
    log("Gemini KO — fallback Perplexity")
    t = call_perplexity(prompt)
    if t:
        return t, "perplexity"
    return None, None


# ============================================
# GENERATION
# ============================================
PROMPT = """Tu es un quant developer. Ecris UNE nouvelle strategie de trading en Python.

SIGNATURE OBLIGATOIRE (respecte exactement):
def strat_evolved_{num}(i, d):
    # retourne "ACHAT", "VENTE" ou None
    ...

VARIABLE d (dictionnaire precalcule, index i = bougie courante):
  d["clotures"]    -> liste des prix de cloture
  d["sma20"], d["sma50"]  -> moyennes mobiles
  d["rsi"]         -> RSI Wilder 14
  d["bb_haut"], d["bb_bas"]  -> bandes Bollinger
  d["macd_line"], d["macd_signal"]  -> MACD
  d["donchian_haut"], d["donchian_bas"]  -> canal Donchian
  d["stoch_k"], d["stoch_d"]  -> Stochastique
  d["ema12"], d["ema26"]  -> EMA

REGLES STRICTES (toute violation = rejet):
  - Tu ne peux lire QUE: d[key][i], d[key][i-1], d[key][i-2] (present + passe recent)
  - INTERDIT: d[key][i+1] ou index futur, indexation negative (d[key][-1])
  - INTERDIT: max(), min(), sum(), len() sur les series (agregation = look-ahead)
  - INTERDIT: import, open(), os, subprocess, eval, exec, __, getattr
  - Utilise None comme garde si indicateur indispo (voir CRITIQUE ci-dessous)

CRITIQUE - GESTION OBLIGATOIRE DES None:
  TOUS les indicateurs (rsi, bb_haut, bb_bas, ema, macd, donchian, stoch) contiennent
  None au debut (periode de chauffe: RSI=14 bars, Bollinger=20, EMA26=26). Une
  comparaison float < None fait CRASHER la strategie = REJET AUTOMATIQUE.
  REGLE ABSOLUE: avant TOUTE comparaison, extrais la valeur et verifie `is None`.

  MAUVAIS (crash):                   BON (correct):
    r = d["rsi"][i]                    r = d["rsi"][i]
    if r < 30: return "ACHAT"         if r is None: return None
                                      if r < 30: return "ACHAT"

  Pour les comparaisons entre 2 indicateurs, verifie TOUS les None:
    bb = d["bb_bas"][i]
    if bb is None: return None
    prix = d["clotures"][i]
    if prix <= bb: return "ACHAT"

  Si tu utilises [i-1], verifie aussi [i-1] is None (et i >= 1).
  - Logique saine: achète sur signal de retournement/momentum, vends sur signal oppose

EXEMPLES (style attendu):
def strat_rsi_reversion(i, d):
    r = d["rsi"][i]
    if r is None:
        return None
    if r < 35:
        return "ACHAT"
    if r > 70:
        return "VENTE"
    return None

def strat_ema_crossover(i, d):
    if i < 1:
        return None
    e12, e26 = d["ema12"], d["ema26"]
    if e12[i] is None or e26[i] is None or e12[i-1] is None or e26[i-1] is None:
        return None
    if e12[i-1] <= e26[i-1] and e12[i] > e26[i]:
        return "ACHAT"
    if e12[i-1] >= e26[i-1] and e12[i] < e26[i]:
        return "VENTE"
    return None

SIMPLICITE OBLIGATOIRE:
  - Max 2 conditions combinees (pas 3-4). Une strategie qui ne se declenche jamais ne sert a rien.
  - Les conditions doivent etre ASSEZ FREQUENTES: un signal d'achat doit apparaitre regulierement sur des donnees reelles (pas un evenement rare).
  - Prends exemple sur les strategies existantes: 1-2 conditions, declenchement frequent.

Sois CREATIVE mais PRAGMATIQUE: combine au plus 2 indicateurs d'une facon nouvelle (ex: RSI + Bollinger, MACD + Donchian, Stochastic + EMA). Cherche un edge simple et declencheable.

Réponds UNIQUEMENT avec la fonction Python dans un bloc ```python ... ```. Pas d'explication."""


def extract_function(text, num):
    """Extrait le code de la fonction depuis la réponse LLM."""
    # cherche bloc python
    m = re.search(r"```(?:python)?\s*(def strat_evolved_\d+.*?)```", text, re.DOTALL | re.IGNORECASE)
    code = m.group(1) if m else None
    if not code:
        # fallback: cherche def strat
        m = re.search(r"(def strat_evolved_\d+\([^)]*\):.*?return.*?(?:\n    .*)*)", text, re.DOTALL)
        code = m.group(1) if m else None
    if not code:
        return None
    # normalise le nom
    code = re.sub(r"def strat_evolved_\d+", f"def strat_evolved_{num}", code)
    return code.strip()


# ============================================
# GATE 1+2: VALIDATION SECURITE
# ============================================
DANGEROUS = ["import ", "open(", "os.", "subprocess", "eval(", "exec(",
             "__", "globals", "getattr", "setattr", "compile(", "input("]


def static_check(code):
    """Analyse statique: rejette patterns dangereux + look-ahead obvious."""
    for pat in DANGEROUS:
        if pat in code:
            return False, f"pattern dangereux: {pat}"
    if re.search(r"\[i\s*\+\s*\d", code):
        return False, "acces futur [i+...]"
    if re.search(r"\[-\d+\]", code):
        return False, "indexation negative [-N]"
    # agregation sur series
    for fn in ["max(", "min(", "sum(", "len("]:
        if fn in code:
            return False, f"agregation interdite: {fn}"
    return True, "OK"


class CausalIndicator:
    """Wrap une serie: autorise uniquement [i], [i-1], [i-2]. Detecte look-ahead runtime."""
    def __init__(self, series, current_i):
        self.series = series
        self.i = current_i
    def __getitem__(self, idx):
        if isinstance(idx, slice):
            raise ValueError("slice interdite (look-ahead possible)")
        if not isinstance(idx, int):
            raise ValueError("index non-int interdit")
        if idx > self.i:
            raise ValueError(f"look-ahead: acces futur [{idx}] > i={self.i}")
        if idx < 0:
            raise ValueError("look-ahead: indexation negative")
        if idx < self.i - 2:
            raise ValueError(f"passe trop lointain [{idx}] (max i-2={self.i-2})")
        if 0 <= idx < len(self.series):
            return self.series[idx]
        return None


def causal_test(func, bougies):
    """Run la fonction avec CausalView a plusieurs indices -> detecte look-ahead runtime."""
    clotures = [b["cloture"] for b in bougies]
    # construit d avec CausalIndicator pour chaque serie
    sma = bm.sma_series(clotures, 20)
    rsi = bm.rsi_series(clotures, 14)
    bbh, bbl = bm.bollinger_series(clotures, 20, 2.0)
    dh, dl = bm.donchian_series(clotures, 20)
    sk, sd = bm.stochastic_series(clotures, 14, 3)
    e12 = bm.ema_simple_series(clotures, 12)
    e26 = bm.ema_simple_series(clotures, 26)
    ml, ms = bm._macd_full(clotures)
    for test_i in [60, 80, 100, len(clotures) - 1]:
        d = {
            "clotures": CausalIndicator(clotures, test_i),
            "sma20": CausalIndicator(sma, test_i), "sma50": CausalIndicator(bm.sma_series(clotures, 50), test_i),
            "rsi": CausalIndicator(rsi, test_i),
            "bb_haut": CausalIndicator(bbh, test_i), "bb_bas": CausalIndicator(bbl, test_i),
            "macd_line": CausalIndicator(ml, test_i), "macd_signal": CausalIndicator(ms, test_i),
            "donchian_haut": CausalIndicator(dh, test_i), "donchian_bas": CausalIndicator(dl, test_i),
            "stoch_k": CausalIndicator(sk, test_i), "stoch_d": CausalIndicator(sd, test_i),
            "ema12": CausalIndicator(e12, test_i), "ema26": CausalIndicator(e26, test_i),
        }
        try:
            sig = func(test_i, d)
            if sig not in ("ACHAT", "VENTE", None):
                return False, f"signal invalide: {sig!r} a i={test_i}"
        except ValueError as e:
            return False, f"look-ahead detecte: {e}"
        except Exception as e:
            return False, f"crash a i={test_i}: {e}"
    return True, "OK"


def sanity_test(func, bougies):
    """Run sur vraies donnees (d full) -> verifie signaux valides + pas de crash."""
    clotures = [b["cloture"] for b in bougies]
    d = {
        "clotures": clotures,
        "sma20": bm.sma_series(clotures, 20), "sma50": bm.sma_series(clotures, 50),
        "rsi": bm.rsi_series(clotures, 14),
        "bb_haut": None, "bb_bas": None, "macd_line": None, "macd_signal": None,
        "donchian_haut": None, "donchian_bas": None, "stoch_k": None, "stoch_d": None,
        "ema12": None, "ema26": None,
    }
    d["bb_haut"], d["bb_bas"] = bm.bollinger_series(clotures, 20, 2.0)
    d["donchian_haut"], d["donchian_bas"] = bm.donchian_series(clotures, 20)
    d["stoch_k"], d["stoch_d"] = bm.stochastic_series(clotures, 14, 3)
    d["ema12"] = bm.ema_simple_series(clotures, 12)
    d["ema26"] = bm.ema_simple_series(clotures, 26)
    d["macd_line"], d["macd_signal"] = bm._macd_full(clotures)
    sigs = set()
    nb_signaux = 0
    for i in range(len(clotures)):
        try:
            s = func(i, d)
            if s not in ("ACHAT", "VENTE", None):
                return False, f"signal invalide {s!r}"
            if s:
                sigs.add(s)
                nb_signaux += 1
        except Exception as e:
            return False, f"crash i={i}: {e}"
    # pas de rejection sur "inactive" ici: le walk-forward sur donnees reelles
    # jugera si la strategie se declenche assez (gate 4). Le dummy peut manquer
    # le regime specifique de la strategie.
    return True, f"OK ({nb_signaux} signaux sur dummy)"


# ============================================
# GATE 4: WALK-FORWARD BACKTEST
# ============================================
def walk_forward(func, bougies_map, split_idx):
    """Retourne (oos_avg, is_avg, win_avg, total_trades) ou None si echec."""
    is_pnls, oos_pnls, wins, trades = [], [], [], 0
    for sym in CRYPTOS:
        bougies = bougies_map.get(sym, [])
        if not bougies or len(bougies) < 60:
            continue
        # in-sample
        st_is = bm.simuler(bougies[:split_idx], func)
        st_oos = bm.simuler(bougies[split_idx:], func)
        if st_is and st_is["trades"] >= 1:
            is_pnls.append(st_is["retour_pct"])
        if st_oos and st_oos["trades"] >= 1:
            oos_pnls.append(st_oos["retour_pct"])
            wins.append(st_oos["win_rate"])
            trades += st_oos["trades"]
    if len(oos_pnls) < 3:
        return None
    oos_avg = sum(oos_pnls) / len(oos_pnls)
    is_avg = sum(is_pnls) / len(is_pnls) if is_pnls else 0
    win_avg = sum(wins) / len(wins) if wins else 0
    return oos_avg, is_avg, win_avg, trades


# ============================================
# DEPLOIEMENT
# ============================================
def load_evolved():
    try:
        return json.load(open(EVOLVED_JSON, encoding="utf-8"))
    except Exception:
        return []


def load_parent():
    """Charge la meilleure strategie deployee comme parent pour mutation.
    Retourne dict(name, code, oos, win, trades) ou None."""
    strats = load_evolved()
    if not strats:
        return None
    best = max(strats, key=lambda s: s.get("oos_avg", 0))
    return {
        "name": best.get("name", "?"),
        "code": best.get("code", ""),
        "oos": best.get("oos_avg", 0),
        "win": best.get("win_rate", 0),
        "trades": best.get("trades", 0),
    }


def regen_evolved_module(strats):
    """Regenere strategies_evolved.py depuis le JSON (code + nom)."""
    lines = ['#!/usr/bin/env python3',
             '# -*- coding: utf-8 -*-',
             '"""strategies_evolved.py — Stratégies générées par strategy_evolver.py.',
             'NE PAS ÉDITER MANUELLEMENT — géré par strategy_evolver.py."""',
             '']
    names = []
    for s in strats:
        lines.append(s["code"].rstrip())
        lines.append("")
        names.append((s["name"], s["func_name"]))
    lines.append("EVOLVED_STRATEGIES = {")
    for name, fn in names:
        lines.append(f'    "{name}": {fn},')
    lines.append("}")
    open(EVOLVED_PY, "w", encoding="utf-8").write("\n".join(lines))


CURRENT_PARENT = None  # lineage: nom du parent si mutation


def deploy(name, func_name, code, wf, llm_source, parent=None):
    oos_avg, is_avg, win_avg, trades = wf
    strats = load_evolved()
    strats.append({
        "name": name, "func_name": func_name, "code": code,
        "date": datetime.utcnow().strftime("%Y-%m-%d %H:%M"),
        "oos_avg": round(oos_avg, 2), "is_avg": round(is_avg, 2),
        "win_rate": round(win_avg, 1), "trades": trades,
        "llm_source": llm_source,
        "parent": parent,
    })
    json.dump(strats, open(EVOLVED_JSON, "w"), indent=2, ensure_ascii=False)
    regen_evolved_module(strats)
    # regen backtests pour la nouvelle strategie
    log("Regen backtests pour la nouvelle strategie...")
    try:
        subprocess.run([sys.executable, "-u", "backtest_horaires.py", "crypto"],
                       cwd=DOSSIER, timeout=400, capture_output=True)
        log("Backtests regenérés — stratégie entrée au classement")
    except Exception as e:
        log(f"regen backtests: {e}")


def record_lecon(name, code, verdict, raison, wf=None, llm_source=None):
    # log debug complet (code entier) pour analyse
    try:
        with open(os.path.join(DOSSIER, "strategies_generated.jsonl"), "a") as fh:
            fh.write(json.dumps({
                "date": datetime.utcnow().strftime("%Y-%m-%d %H:%M"),
                "name": name, "verdict": verdict, "raison": raison,
                "llm_source": llm_source, "code": code,
            }, ensure_ascii=False) + "\n")
    except Exception:
        pass
    entry = {
        "date": datetime.utcnow().strftime("%Y-%m-%d %H:%M"),
        "source": "strategy_evolver",
        "type": "generation_strategie",
        "name": name,
        "llm_source": llm_source,
        "verdict": verdict,
        "raison": raison,
        "code": code[:2000] if code else "",
        "parent": CURRENT_PARENT,
    }
    if wf:
        oos_avg, is_avg, win_avg, trades = wf
        entry["oos_avg"] = round(oos_avg, 2)
        entry["is_avg"] = round(is_avg, 2)
        entry["win_rate"] = round(win_avg, 1)
        entry["trades"] = trades
    try:
        with open(LECONS, "a") as fh:
            fh.write(json.dumps(entry, ensure_ascii=False) + "\n")
    except Exception:
        pass


# ============================================
# MAIN
# ============================================
def main():
    log("=" * 55)
    log("STRATEGY EVOLVER START")
    random.seed(int(time.time()))
    num = f"{int(time.time()) % 100000:05d}"
    name = f"Evolved {num}"
    func_name = f"strat_evolved_{num}"

    # 0. charge bougies
    bougies_map = {}
    for sym in CRYPTOS:
        try:
            b = historique_ohlcv_long(sym, INTERVALLE, N_BOUGIES)
            if b and len(b) >= 60:
                bougies_map[sym] = b
        except Exception:
            pass
        time.sleep(0.15)
    log(f"Bougies: {len(bougies_map)}/{len(CRYPTOS)} cryptos")
    if len(bougies_map) < 3:
        log("PAS ASSEZ DE BOUGIES - abandon")
        return
    n = min(len(b) for b in bougies_map.values())
    split_idx = int(n * SPLIT)

    # 1. GENERATION (mode mutation 60% si parent dispo, sinon fresh)
    global CURRENT_PARENT
    CURRENT_PARENT = None
    parent = load_parent()
    use_mutation = parent is not None and random.random() < 0.60
    if use_mutation:
        CURRENT_PARENT = parent["name"]
        log(f"Generation strategie {name} via LLM [MUTATION de {parent['name']} OOS {parent['oos']:+.2f}% win {parent['win']:.0f}%]...")
        prompt = MUTATION_PROMPT.format(
            parent_code=parent["code"],
            parent_oos=f"{parent['oos']:+.2f}",
            parent_win=int(parent["win"]),
            parent_trades=parent["trades"],
            mutation=mutation_type(), num=num)
        if sagesse_prompt:
            prompt += "\n\n" + sagesse_prompt()
    else:
        log(f"Generation strategie {name} via LLM [FRESH]...")
        prompt = PROMPT.format(num=num)
        # SEED ALEATOIRE en tete: force la diversite (chaque run explore un angle different)
        prompt = exploration_seed() + "\n\n" + prompt
        # INJECTE LA SAGESSE DES 10 MAITRES TRADERS (principes + lecons backtestees)
        if sagesse_prompt:
            prompt += "\n\n" + sagesse_prompt()
            prompt += ("\n\nINSTRUCTION CLE: sois INSPIRE par ces principes et les lecons ci-dessus. "
                      "Ne repropose PAS les approches deja rejetees (deep contrarian RSI<20, "
                      "cut-losers-fast, trend-following en regime quiet). Cherche un edge aligne "
                      "avec le systeme mean-reversion: contrarian modere (RSI 20-35), patience, "
                      "cassure de canal, momentum sur retournement. Max 2 conditions, declencheable souvent.")
    # LIVE FEEDBACK LOOP: injecte les lecons de perf live (auto-apprentissage)
    # Avant l'evolver n'apprenait pas de ses trades live. Maintenant si.
    try:
        from live_lessons import live_lessons_prompt as _llp
        _ll = _llp()
        if _ll:
            prompt += _ll
            log("Lecons live injectees dans le prompt")
    except Exception as _e:
        pass
    texte, llm_source = call_llm(prompt)
    if not texte:
        log("LLM indispo - abandon")
        record_lecon(name, "", "REJETEE", "LLM indisponible", None, None)
        return
    code = extract_function(texte, num)
    if not code:
        log("Extraction code echouee - abandon")
        record_lecon(name, "", "REJETEE", "code non extrait", None, llm_source)
        return
    log(f"Code genere ({len(code)} chars, source={llm_source})")

    # GATE 1: syntaxe
    try:
        ast.parse(code)
    except SyntaxError as e:
        log(f"GATE 1 REJET: syntaxe invalide: {e}")
        record_lecon(name, code, "REJETEE", f"syntaxe: {e}", None, llm_source)
        return
    log("GATE 1 OK: syntaxe valide")

    # compile + load fonction
    ns = {}
    try:
        exec(compile(ast.Module(body=[ast.parse(code).body[0]], type_ignores=[]), "<evolved>", "exec"), ns)
        func = ns[func_name]
    except Exception as e:
        log(f"Chargement fonction echoue: {e}")
        record_lecon(name, code, "REJETEE", f"load: {e}", None, llm_source)
        return

    # GATE 2: look-ahead (statique + CausalView)
    ok, raison = static_check(code)
    if not ok:
        log(f"GATE 2 REJET (statique): {raison}")
        record_lecon(name, code, "REJETEE", f"static: {raison}", None, llm_source)
        return
    dummy = varied_dummy(220)
    ok, raison = causal_test(func, dummy)
    if not ok:
        log(f"GATE 2 REJET (causal): {raison}")
        record_lecon(name, code, "REJETEE", f"causal: {raison}", None, llm_source)
        return
    log("GATE 2 OK: pas de look-ahead detecte")

    # GATE 3: sanity (signaux valides)
    ok, raison = sanity_test(func, dummy)
    if not ok:
        log(f"GATE 3 REJET: {raison}")
        record_lecon(name, code, "REJETEE", f"sanity: {raison}", None, llm_source)
        return
    log(f"GATE 3 OK: {raison}")

    # GATE 4: walk-forward
    wf = walk_forward(func, bougies_map, split_idx)
    if not wf:
        log("GATE 4 REJET: pas assez de trades OOS")
        record_lecon(name, code, "REJETEE", "pas assez de trades OOS", None, llm_source)
        return
    oos_avg, is_avg, win_avg, trades = wf
    log(f"GATE 4: IS={is_avg:+.2f}% OOS={oos_avg:+.2f}% win={win_avg:.0f}% trades={trades}")
    if oos_avg <= OOS_MIN:
        log(f"REJET: OOS {oos_avg:+.2f}% <= {OOS_MIN}% (pas assez profitable)")
        record_lecon(name, code, "REJETEE", f"OOS {oos_avg:.2f}% <= {OOS_MIN}", wf, llm_source)
        return
    if oos_avg >= OOS_MAX:
        log(f"REJET: OOS {oos_avg:+.2f}% >= {OOS_MAX}% (SUSPECT DE LEAKAGE)")
        record_lecon(name, code, "REJETEE", f"OOS {oos_avg:.2f}% >= {OOS_MAX} (leakage suspect)", wf, llm_source)
        return
    if win_avg < WIN_MIN:
        log(f"REJET: win_rate {win_avg:.0f}% < {WIN_MIN}%")
        record_lecon(name, code, "REJETEE", f"win {win_avg:.0f}% < {WIN_MIN}", wf, llm_source)
        return
    if trades < TRADES_MIN:
        log(f"REJET: trades {trades} < {TRADES_MIN}")
        record_lecon(name, code, "REJETEE", f"trades {trades} < {TRADES_MIN}", wf, llm_source)
        return

    # TOUS LES GATES PASSENT -> DEPLOIEMENT
    log(f"TOUS GATES PASSANTS -> DEPLOIEMENT de {name}")
    if use_mutation:
        delta = oos_avg - parent["oos"]
        tag = "AMELIORATION" if delta > 0.1 else ("EQUIVALENT" if abs(delta) <= 0.5 else "DEGRADE")
        log(f"  vs parent {parent['name']}: OOS {oos_avg:+.2f}% vs {parent['oos']:+.2f}% ({tag} {delta:+.2f}pp)")
    deploy(name, func_name, code, wf, llm_source, parent=CURRENT_PARENT)
    record_lecon(name, code, "DEPLOYED", f"OOS {oos_avg:.2f}% win {win_avg:.0f}% trades {trades}", wf, llm_source)
    log(f"STRATEGIE {name} DEPLOYEE: OOS {oos_avg:+.2f}% | win {win_avg:.0f}% | {trades} trades")
    log("STRATEGY EVOLVER END")
    log("=" * 55)


if __name__ == "__main__":
    main()
