#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
actions_executor.py — Boucle fermée réflexion -> action (self-improvement autonome).

Lit la derniere réflexion IA (reflection_log.jsonl), extrait les actions
suggérées, les VALIDATE contre les perf réelles, puis les exécute:
  - desactiver_strategie : coupe une stratégie perdante (écrit strategies_desactivees.json)
  - ajuster_tp / ajuster_sl : ajuste TP/SL par actif (écrit params_tuning.json)

SAFETY CRITIQUE: l'exécuteur ne suit JAMAIS l'IA aveuglément.
  - Une désactivation n'est appliquée QUE si la stratégie est réellement perdante
    (pnl_total < 0) dans stats_strategies() — vérification croisée donnée réelle.
  - Garde >=1 stratégie active par actif (anti-surcoupe).
  - TP/SL bornés aux mêmes limites que meta_tuning.
  - Idempotence: une réflexion déjà traitée n'est jamais ré-exécutée.
  - Max 1 désactivation par cycle (anti-cascade).

CLI:
  python actions_executor.py            # traite la dernière réflexion
  python actions_executor.py etat      # voir les actions déjà exécutées
"""
import os
import re
import json
import logging
import unicodedata
from datetime import datetime

DOSSIER = os.path.dirname(os.path.abspath(__file__))
REFLECTION_LOG = os.path.join(DOSSIER, "reflection_log.jsonl")
PRUNING_FILE = os.path.join(DOSSIER, "strategies_desactivees.json")
PARAMS_FILE = os.path.join(DOSSIER, "params_tuning.json")
STATE_FILE = os.path.join(DOSSIER, "actions_state.json")
LOG_FILE = os.path.join(DOSSIER, "actions_executor_log.jsonl")

# Bounds identiques a meta_tuning (sécurité)
TP_MIN, TP_MAX = 1.0, 3.0
SL_MIN, SL_MAX = 0.5, 2.5
CONF_MIN = 0.70          # confiance min pour actions structurées
MAX_DISABLE_CYCLE = 1    # anti-cascade

# Stratégies connues (sync regime.py)
STRATEGIES_CONNUES = ["MACD Momentum", "RSI Mean Reversion",
                      "Bollinger Breakout", "SMA Crossover"]
# Resolution symbole court -> symbole paper
SYM_MAP = {"SOL": "SOLUSDT", "BTC": "BTCUSDT", "ETH": "ETHUSDT",
           "BNB": "BNBUSDT", "XRP": "XRPUSDT"}

logging.basicConfig(level=logging.INFO,
                    format="%(asctime)s [%(levelname)s] %(message)s",
                    datefmt="%H:%M:%S")
log = logging.getLogger("actions")


def _load(path, default):
    try:
        return json.load(open(path, encoding="utf-8"))
    except Exception:
        return default


def _save(path, data):
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)


def _tel(msg):
    try:
        from telegram_alerte import envoyer_telegram
        envoyer_telegram(msg)
    except Exception:
        pass


def _log(entry):
    try:
        with open(LOG_FILE, "a", encoding="utf-8") as f:
            f.write(json.dumps(entry, ensure_ascii=False) + "\n")
    except Exception:
        pass


def _sans_accents(s):
    """Supprime les accents pour la detection de mots-cles."""
    if not s:
        return ""
    return unicodedata.normalize("NFKD", s).encode("ascii", "ignore").decode()


def _resoud_symbole(token):
    if not token:
        return None
    t = token.upper().strip()
    if t in SYM_MAP.values():
        return t
    if t in SYM_MAP:
        return SYM_MAP[t]
    # contient deja USDT/=X/=F
    return token


# ----------------------------------------------------------- lecture reflexion
def derniere_reflexion():
    try:
        with open(REFLECTION_LOG, encoding="utf-8") as f:
            lignes = f.readlines()
    except Exception:
        return None
    if not lignes:
        return None
    try:
        return json.loads(lignes[-1])
    except Exception:
        return None


def _extraire_strategie_texte(texte):
    """Cherche un nom de stratégie connu dans un texte libre."""
    if not texte:
        return None
    for nom in STRATEGIES_CONNUES:
        if nom.lower() in texte.lower():
            return nom
    return None


def extraire_actions(reflexion):
    """Extrait les actions d'une réflexion.
    1) champ structuré 'actions' (futur, si prompt enrichi)
    2) sinon heuristique sur suggestions + priorite."""
    analyse = reflexion.get("analyse", {}) or {}
    actions = []
    # 1) structuré
    for a in analyse.get("actions", []) or []:
        if isinstance(a, dict) and a.get("type"):
            actions.append(a)
    if actions:
        return actions
    # 2) heuristique
    textes = list(analyse.get("suggestions", []) or [])
    if analyse.get("priorite"):
        textes.append(analyse["priorite"])
    for txt in textes:
        tn = _sans_accents(txt).lower()  # version normalisee pour matching
        if "desactiv" in tn:
            nom = _extraire_strategie_texte(txt)
            if nom:
                actions.append({"type": "desactiver_strategie", "strategie": nom,
                                "confiance": 0.75, "raison": txt[:120]})
                continue
        # ajuster TP: "reduire/baisser TP sur SOL a 1.0%"
        m = re.search(r"(?:reduire|baisser|diminuer|serrer|monter|augmenter|elargir)?\s*TP\s*(?:sur|de)?\s*([A-Z]{3,6})?\s*[aà]\s*([0-9.]+)\s*%", tn)
        if m:
            actif = _resoud_symbole(m.group(1))
            tp = float(m.group(2))
            sens = "baisser" if any(k in tn for k in ("reduire", "baisser", "diminuer", "serrer")) else "augmenter"
            actions.append({"type": "ajuster_tp", "actif": actif, "tp": tp,
                            "sens": sens, "confiance": 0.7, "raison": txt[:120]})
            continue
        # ajuster SL
        m = re.search(r"(?:serrer|augmenter|reduire)?\s*SL\s*(?:sur|de)?\s*([A-Z]{3,6})?\s*[aà]\s*([0-9.]+)\s*%", tn)
        if m:
            actif = _resoud_symbole(m.group(1))
            actions.append({"type": "ajuster_sl", "actif": actif, "sl": float(m.group(2)),
                            "confiance": 0.7, "raison": txt[:120]})
    return actions


# ----------------------------------------------------------- EXECUTION
def _cle(strategie, actif):
    return f"{strategie}|{actif}"


def stats_strategies():
    try:
        from auto_pruning import stats_strategies as _s
        return _s()
    except Exception:
        return {}


def _desactiver_strategie_all(strategie, raison, data, desact):
    """Mode ALL: désactive la stratégie sur tous les actifs où elle est perdante.
    Chaque désactivation est validée (pnl<0, anti-surcoupe >=1 active)."""
    stats = stats_strategies()
    cibles = {k: v for k, v in stats.items() if v.get("strategie") == strategie}
    if not cibles:
        return False, (f"stratégie '{strategie}' introuvable dans stats live "
                       f"— skip (anti-hallucination)")
    faits = []
    for cle_i, s_i in cibles.items():
        actif_i = s_i.get("actif", "?")
        if desact.get(cle_i, {}).get("disabled"):
            faits.append(f"{actif_i}: déjà")
            continue
        if s_i.get("pnl_total", 0) >= 0:
            faits.append(f"{actif_i}: pnl≥0 skip")
            continue
        # anti-surcoupe : garder >=1 strategie active sur cet actif
        autres = [k for k, v in stats.items()
                  if v.get("actif") == actif_i and k != cle_i]
        nb_act = sum(1 for k in autres if not desact.get(k, {}).get("disabled"))
        if nb_act < 1:
            faits.append(f"{actif_i}: dernière active skip")
            continue
        entry = desact.get(cle_i, {"strategie": strategie, "actif": actif_i})
        entry.update({
            "strategie": strategie, "actif": actif_i, "disabled": True,
            "raison": f"[reflection ALL] {raison} (pnl {s_i.get('pnl_total')}€ sur {s_i.get('n')} trades)",
            "since": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            "source": "reflection",
            "stats": {"n": s_i.get("n"), "win_rate": s_i.get("win_rate"),
                      "pnl_total": s_i.get("pnl_total")},
        })
        desact[cle_i] = entry
        faits.append(f"{actif_i}: coupée (pnl {s_i.get('pnl_total')}€)")
    data["dernier_cycle"] = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    _save(PRUNING_FILE, data)
    ok = any("coupée" in f for f in faits)
    return ok, f"{strategie} ALL: " + "; ".join(faits)


def assigner_strategie(actif, strategie, raison=""):
    """Enregistre une suggestion d'assignation de stratégie (sécurisé, pas d'auto-trade).
    L'assignation auto à une position existante n'est pas faite (race condition + forcer
    un trade est dangereux). La suggestion est tracée + remontée sur Telegram."""
    if not actif or not strategie:
        return False, "actif/stratégie manquants — skip"
    entry = {
        "ts": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "actif": actif, "strategie": strategie, "raison": (raison or "")[:200],
        "source": "reflection", "statut": "suggestion_manuelle",
    }
    with open("assignments_suggerees.jsonl", "a", encoding="utf-8") as f:
        f.write(json.dumps(entry, ensure_ascii=False) + "\n")
    _tel(f"💡 Suggestion réflexion: assigner '{strategie}' à {actif} "
         f"— {(raison or '')[:80]} (validation manuelle recommandée)")
    return True, (f"suggestion enregistrée: {strategie}→{actif} "
                  f"(auto-assign désactivée pour sécurité)")


def desactiver_strategie(strategie, actif, raison):
    """Ecrit une desactivation dans strategies_desactivees.json (format auto_pruning)."""
    data = _load(PRUNING_FILE, {"desactivees": {}, "dernier_cycle": None})
    desact = data.setdefault("desactivees", {})
    # --- Mode multi-actifs : désactive sur TOUS les actifs où la stratégie est perdante ---
    if isinstance(actif, str) and actif.upper() in ("ALL", "TOUS", "*"):
        return _desactiver_strategie_all(strategie, raison, data, desact)
    cle = _cle(strategie, actif)
    if desact.get(cle, {}).get("disabled"):
        return False, "deja desactivee"
    # VALIDATION: verifier que la strategie est réellement perdante
    stats = stats_strategies()
    s = stats.get(cle)
    if not s:
        # strategie introuvable dans stats -> chercher sur autre actif
        cands = {k: v for k, v in stats.items()
                 if v.get("strategie") == strategie}
        if not cands:
            return False, f"strategie '{strategie}' introuvable dans stats live — skip (anti-hallucination)"
        # prendre le pire pnl
        cle = min(cands, key=lambda k: cands[k].get("pnl_total", 0))
        s = cands[cle]
        actif = s["actif"]
    if s.get("pnl_total", 0) >= 0:
        return False, (f"validation échouée: {strategie} sur {actif} a un pnl "
                       f"positif/nul ({s.get('pnl_total')}€) — l'IA se trompe, skip")
    # SECURITE: garder >=1 strategie active par actif
    cles_actif = [k for k, v in stats.items()
                  if v.get("actif") == actif and k != cle]
    nb_actives = sum(1 for k in cles_actif
                     if not desact.get(k, {}).get("disabled"))
    if nb_actives < 1:
        return False, f"sécurité: dernière stratégie active sur {actif} — skip"
    entry = desact.get(cle, {"strategie": strategie, "actif": actif})
    entry.update({
        "strategie": strategie, "actif": actif,
        "disabled": True,
        "raison": f"[reflection] {raison} (pnl {s.get('pnl_total')}€ sur {s.get('n')} trades)",
        "since": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "source": "reflection",
        "stats": {"n": s.get("n"), "win_rate": s.get("win_rate"),
                  "pnl_total": s.get("pnl_total")},
    })
    desact[cle] = entry
    data["dernier_cycle"] = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    _save(PRUNING_FILE, data)
    return True, f"stratégie {strategie} désactivée sur {actif} (pnl {s.get('pnl_total')}€)"


def ajuster_tp_sl(actif, tp=None, sl=None, raison=""):
    """Ecrit un ajustement TP/SL dans params_tuning.json (format meta_tuning)."""
    if not actif:
        return False, "actif non résolu — skip"
    data = _load(PARAMS_FILE, {"params": {}, "dernier_cycle": None})
    params = data.setdefault("params", {})
    p = params.get(actif, {"tp": 1.5, "sl": 1.5, "historique": []})
    tp_av, sl_av = float(p.get("tp", 1.5)), float(p.get("sl", 1.5))
    nouvt, nouvs = tp_av, sl_av
    if tp is not None:
        nouvt = max(TP_MIN, min(TP_MAX, float(tp)))
    if sl is not None:
        nouvs = max(SL_MIN, min(SL_MAX, float(sl)))
    if nouvt == tp_av and nouvs == sl_av:
        return False, f"{actif}: TP/SL inchangés (bornes)"
    p["tp"], p["sl"] = nouvt, nouvs
    p["ajuste_le"] = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    p["raison"] = f"[reflection] {raison}"
    p["source"] = "reflection"
    p["historique"] = p.get("historique", []) + [{
        "ts": p["ajuste_le"], "tp": nouvt, "sl": nouvs,
        "raison": raison, "source": "reflection"}]
    params[actif] = p
    data["dernier_cycle"] = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    _save(PARAMS_FILE, data)
    return True, f"{actif}: TP {tp_av}%→{nouvt}%, SL {sl_av}%→{nouvs}%"


# ----------------------------------------------------------- ORCHESTRATION
def executer():
    reflexion = derniere_reflexion()
    if not reflexion:
        log.info("Aucune réflexion trouvée. Rien à faire.")
        return []
    ts = reflexion.get("ts", "")
    state = _load(STATE_FILE, {"deja_traite": []})
    if ts in state.get("deja_traite", []):
        log.info("Réflexion %s déjà traitée. Skip.", ts)
        return []
    actions = extraire_actions(reflexion)
    if not actions:
        log.info("Réflexion %s: aucune action extractible.", ts)
        state.setdefault("deja_traite", []).append(ts)
        _save(STATE_FILE, state)
        return []
    log.info("Réflexion %s: %d action(s) extraite(s). Validation...", ts, len(actions))
    results = []
    nb_disable = 0
    for a in actions:
        conf = float(a.get("confiance", 0))
        atype = a.get("type")
        # seuil de confiance
        if conf < CONF_MIN:
            results.append((atype, False, f"confiance {conf} < {CONF_MIN} — skip"))
            continue
        try:
            if atype == "desactiver_strategie":
                if nb_disable >= MAX_DISABLE_CYCLE:
                    results.append((atype, False, "max désactivation cycle atteint — skip"))
                    continue
                strat = a.get("strategie")
                actif = a.get("actif")
                ok, msg = desactiver_strategie(strat, actif, a.get("raison", ""))
                if ok:
                    nb_disable += 1
                results.append((atype, ok, msg))
            elif atype == "ajuster_tp":
                ok, msg = ajuster_tp_sl(a.get("actif"), tp=a.get("tp"),
                                        raison=a.get("raison", ""))
                results.append((atype, ok, msg))
            elif atype == "ajuster_sl":
                ok, msg = ajuster_tp_sl(a.get("actif"), sl=a.get("sl"),
                                        raison=a.get("raison", ""))
                results.append((atype, ok, msg))
            elif atype == "assigner_strategie":
                ok, msg = assigner_strategie(a.get("actif"), a.get("strategie"),
                                            a.get("raison", ""))
                results.append((atype, ok, msg))
            else:
                results.append((atype, False, f"type inconnu: {atype}"))
        except Exception as e:
            results.append((atype, False, f"erreur: {e}"))
    # marquer traité
    state.setdefault("deja_traite", []).append(ts)
    state["dernier_cycle"] = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    _save(STATE_FILE, state)
    # logs + telegram
    now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    execs = [(t, ok, m) for t, ok, m in results if ok]
    if execs:
        resume = "\n".join(f"  - [{t}] {m}" for t, _, m in execs)
        msg = (f"🔁 BOUCLE FERMÉE — {len(execs)} action(s) exécutée(s)\n{resume}")
        log.info(msg)
        _tel(msg)
    _log({"ts": now, "reflexion": ts, "actions": results})
    return results


def cmd_etat():
    state = _load(STATE_FILE, {"deja_traite": []})
    print("=" * 55)
    print("BOUCLE FERMÉE RÉFLEXION→ACTION")
    print("=" * 55)
    print(f"Réflexions traitées: {len(state.get('deja_traite', []))}")
    print(f"Dernier cycle: {state.get('dernier_cycle', 'jamais')}")
    # dernières actions du log
    try:
        with open(LOG_FILE, encoding="utf-8") as f:
            lignes = f.readlines()[-5:]
        print("\nDernières exécutions:")
        for l in lignes:
            e = json.loads(l)
            execs = [r for r in e.get("actions", []) if r[1]]
            if execs:
                print(f"  [{e['ts']}] {len(execs)} action(s): " +
                      "; ".join(f"{t}:{m}" for t, _, m in execs))
    except Exception:
        pass


def main():
    import sys
    if len(sys.argv) > 1 and sys.argv[1] == "etat":
        cmd_etat()
        return
    results = executer()
    print(f"\n{len(results)} action(s) évaluée(s).")
    for t, ok, m in results:
        print(f"  [{'OK' if ok else '--'}] {t}: {m}")
    cmd_etat()


if __name__ == "__main__":
    main()
