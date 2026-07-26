#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
reflection_action.py — Pipeline Reflexion -> Action (auto-execution).

Lit la derniere reflexion IA (reflection_log.jsonl) et AUTO-EXECUTE les
actions suggerees dans son champ 'actions' (voir reflection_gemini.py):
  - desactiver_strategie : coupe une strategie (ecrit strategies_desactivees.json)
  - ajuster_tp           : ajuste le TP d'un actif (ecrit strat_params.json)
  - ajuster_sl           : ajuste le SL d'un actif (ecrit strat_params.json)

SAFETY:
  - Seules les actions avec confiance >= SEUIL_CONFIANCE sont executees
    (defaut 0.7, override via REFLECTION_ACTION_SEUIL).
  - Max MAX_ACTIONS_PAR_RUN actions executees par run (anti-cascade).
  - COOLDOWN de 12h: une action identique (meme type+cible) recemment
    executee est ignoree (relit reflection_action_log.jsonl).
  - Ne plante jamais: tout est encapsule dans des try/except.
  - Chaque action loggee dans reflection_action_log.jsonl + alerte Telegram,
    et un digest Telegram est envoye en fin de run.

CLI:
  python reflection_action.py              # execute le pipeline
  python reflection_action.py --dry-run    # simule sans rien ecrire/executer
  python reflection_action.py etat         # voir les dernieres executions
"""
import os
import json
import logging
from datetime import datetime, timedelta

DOSSIER = os.path.dirname(os.path.abspath(__file__))
REFLECTION_LOG = os.path.join(DOSSIER, "reflection_log.jsonl")
PRUNING_FILE = os.path.join(DOSSIER, "strategies_desactivees.json")
PRUNING_LOG = os.path.join(DOSSIER, "pruning_log.jsonl")
STRAT_PARAMS_FILE = os.path.join(DOSSIER, "strat_params.json")
META_TUNING_LOG = os.path.join(DOSSIER, "meta_tuning_log.jsonl")
LOG_FILE = os.path.join(DOSSIER, "reflection_action_log.jsonl")

# Charger .env
from dotenv import load_dotenv
load_dotenv(os.path.join(DOSSIER, ".env"))
TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN", "")
TELEGRAM_CHAT_ID = os.getenv("TELEGRAM_CHAT_ID", "")

# --- Garde-fous ---
SEUIL_CONFIANCE = float(os.getenv("REFLECTION_ACTION_SEUIL", "0.7"))
MAX_ACTIONS_PAR_RUN = 3
COOLDOWN_HEURES = 12
TP_MIN, TP_MAX = 1.0, 3.0
SL_MIN, SL_MAX = 0.5, 2.5

logging.basicConfig(level=logging.INFO,
                    format="%(asctime)s [%(levelname)s] %(message)s",
                    datefmt="%H:%M:%S")
log = logging.getLogger("reflection_action")


def _load(path, default):
    try:
        return json.load(open(path, encoding="utf-8"))
    except Exception:
        return default


def _save(path, data):
    try:
        with open(path, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
    except Exception as e:
        log.warning("echec sauvegarde %s: %s", path, e)


def _tel(msg):
    try:
        from telegram_alerte import envoyer_telegram
        envoyer_telegram(msg)
    except Exception:
        pass


def _log_jsonl(path, entry):
    try:
        with open(path, "a", encoding="utf-8") as f:
            f.write(json.dumps(entry, ensure_ascii=False) + "\n")
    except Exception:
        pass


def _now():
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")


def _cle(strategie, actif):
    return f"{strategie}|{actif}"


# ---------------------------------------------------------------- LECTURE
def charger_derniere_reflexion():
    """Lit reflection_log.jsonl, retourne le champ 'actions' de la derniere
    entree (liste). Retourne [] si aucune reflexion ou aucune action."""
    try:
        with open(REFLECTION_LOG, encoding="utf-8") as f:
            lignes = f.readlines()
    except Exception as e:
        log.warning("reflection_log.jsonl illisible: %s", e)
        return []
    if not lignes:
        log.info("Aucune reflexion enregistree.")
        return []
    try:
        derniere = json.loads(lignes[-1])
    except Exception as e:
        log.warning("derniere ligne reflection_log.jsonl invalide: %s", e)
        return []
    analyse = derniere.get("analyse", {}) or {}
    actions = analyse.get("actions", []) or []
    return [a for a in actions if isinstance(a, dict) and a.get("type")]


# alias retro-compatible avec l'orthographe demandee dans la spec
charger_derniere_reflection = charger_derniere_reflexion


# ---------------------------------------------------------------- COOLDOWN
def _en_cooldown(action_type, target):
    """Verifie reflection_action_log.jsonl: si la meme action (type+cible)
    a ete executee avec succes dans les COOLDOWN_HEURES dernieres heures,
    on la saute (anti-spam / anti-oscillation)."""
    try:
        with open(LOG_FILE, encoding="utf-8") as f:
            lignes = f.readlines()
    except Exception:
        return False
    limite = datetime.now() - timedelta(hours=COOLDOWN_HEURES)
    for ligne in reversed(lignes[-200:]):
        try:
            e = json.loads(ligne)
        except Exception:
            continue
        if e.get("action_type") != action_type or e.get("target") != target:
            continue
        if (e.get("result") or "").lower() != "ok":
            continue
        try:
            dt = datetime.strptime(e.get("ts", ""), "%Y-%m-%d %H:%M:%S")
        except Exception:
            continue
        if dt > limite:
            return True
    return False


def _log_action(action_type, target, details, result, confiance):
    _log_jsonl(LOG_FILE, {
        "ts": _now(), "action_type": action_type, "target": target,
        "details": details, "result": result, "confiance": confiance,
    })


# ---------------------------------------------------------------- ACTIONS
def _desactiver_strategie(action, dry_run=False):
    """desactiver_strategie: ecrit strategies_desactivees.json (format
    auto_pruning), logge dans pruning_log.jsonl, alerte Telegram."""
    strategie = action.get("strategie") or "?"
    actif = action.get("actif") or "GLOBAL"
    raison = action.get("raison", "")
    target = _cle(strategie, actif)

    if _en_cooldown("desactiver_strategie", target):
        return False, f"cooldown actif ({COOLDOWN_HEURES}h) pour {target} — skip"

    if dry_run:
        return True, f"[DRY-RUN] desactiverait {target}: {raison[:100]}"

    data = _load(PRUNING_FILE, {"desactivees": {}, "dernier_cycle": None})
    desact = data.setdefault("desactivees", {})
    entry = desact.get(target, {"strategie": strategie, "actif": actif})
    if entry.get("disabled"):
        return False, f"{target}: deja desactivee"
    entry.update({
        "strategie": strategie, "actif": actif, "disabled": True,
        "raison": f"[reflection_action] {raison}",
        "since": _now(), "source": "reflection_action",
        "confiance": action.get("confiance"),
    })
    desact[target] = entry
    data["dernier_cycle"] = _now()
    _save(PRUNING_FILE, data)

    _log_jsonl(PRUNING_LOG, {"ts": _now(), "action": "DESACTIVE",
                            "strategie": strategie, "actif": actif,
                            "raison": raison, "source": "reflection_action"})

    msg = f"✂️ REFLECTION-ACTION: desactivation {strategie} sur {actif}\n{raison}"
    log.info(msg)
    _tel(msg)
    return True, f"strategie {strategie} desactivee sur {actif}"


def _ajuster_tp_sl(action, champ, dry_run=False):
    """ajuster_tp / ajuster_sl: met a jour strat_params.json (par actif),
    logge dans meta_tuning_log.jsonl, alerte Telegram.
    champ: 'tp' ou 'sl'."""
    actif = action.get("actif")
    if not actif:
        return False, "actif manquant — skip"
    valeur = action.get(champ)
    if valeur is None:
        return False, f"valeur '{champ}' manquante — skip"
    try:
        valeur = float(valeur)
    except Exception:
        return False, f"valeur '{champ}' invalide: {valeur!r}"

    lo, hi = (TP_MIN, TP_MAX) if champ == "tp" else (SL_MIN, SL_MAX)
    valeur_bornee = max(lo, min(hi, valeur))
    raison = action.get("raison", "")
    target = actif

    if _en_cooldown(f"ajuster_{champ}", target):
        return False, f"cooldown actif ({COOLDOWN_HEURES}h) pour {champ}:{target} — skip"

    if dry_run:
        return True, f"[DRY-RUN] ajusterait {champ.upper()} de {actif} -> {valeur_bornee}%: {raison[:100]}"

    data = _load(STRAT_PARAMS_FILE, {})
    if not isinstance(data, dict):
        data = {}
    par_actif = data.setdefault("par_actif", {})
    p = par_actif.get(actif, {"tp": 1.5, "sl": 1.5})
    avant = float(p.get(champ, 1.5))
    p[champ] = valeur_bornee
    p["ajuste_le"] = _now()
    p["raison"] = f"[reflection_action] {raison}"
    p["source"] = "reflection_action"
    p["historique"] = p.get("historique", []) + [{
        "ts": _now(), champ: valeur_bornee, "raison": raison}]
    par_actif[actif] = p
    data["dernier_cycle"] = _now()
    _save(STRAT_PARAMS_FILE, data)

    _log_jsonl(META_TUNING_LOG, {
        "ts": _now(), "symbole": actif,
        f"{champ}_avant": avant, f"{champ}_apres": valeur_bornee,
        "raison": raison, "source": "reflection_action"})

    label = "TP" if champ == "tp" else "SL"
    msg = f"🔧 REFLECTION-ACTION {actif}: {label} {avant}%→{valeur_bornee}%\n{raison}"
    log.info(msg)
    _tel(msg)
    return True, f"{actif}: {label} {avant}%→{valeur_bornee}%"


def executer_action(action, dry_run=False):
    """Execute une action unique selon son type, si confiance suffisante.
    Retourne (ok: bool, message: str). Ne leve jamais d'exception."""
    atype = action.get("type", "?")
    try:
        conf = float(action.get("confiance", 0) or 0)
    except Exception:
        conf = 0.0

    if conf < SEUIL_CONFIANCE:
        msg = f"confiance {conf} < seuil {SEUIL_CONFIANCE} — skip"
        _log_action(atype, action.get("strategie") or action.get("actif") or "?",
                    action, "skip_confiance", conf)
        return False, msg

    try:
        if atype == "desactiver_strategie":
            strategie = action.get("strategie") or "?"
            actif = action.get("actif") or "GLOBAL"
            target = _cle(strategie, actif)
            ok, msg = _desactiver_strategie(action, dry_run=dry_run)
        elif atype == "ajuster_tp":
            target = action.get("actif") or "?"
            ok, msg = _ajuster_tp_sl(action, "tp", dry_run=dry_run)
        elif atype == "ajuster_sl":
            target = action.get("actif") or "?"
            ok, msg = _ajuster_tp_sl(action, "sl", dry_run=dry_run)
        else:
            target = action.get("actif") or action.get("strategie") or "?"
            ok, msg = False, f"type d'action inconnu: {atype}"
    except Exception as e:
        target = action.get("actif") or action.get("strategie") or "?"
        ok, msg = False, f"erreur execution: {e}"
        log.warning("Erreur executer_action(%s): %s", atype, e)

    resultat = "ok" if ok else ("dry_run" if dry_run and ok else "echec")
    if dry_run:
        resultat = "dry_run"
    elif ok:
        resultat = "ok"
    else:
        resultat = "echec"
    _log_action(atype, target, action, resultat, conf)
    return ok, msg


# ---------------------------------------------------------------- ORCHESTRATION
def executer_toutes(dry_run=False):
    """Pipeline principal: charge la derniere reflexion, filtre par confiance,
    execute jusqu'a MAX_ACTIONS_PAR_RUN actions, logge et envoie un digest
    Telegram. Retourne la liste des resultats [(type, ok, msg), ...]."""
    try:
        actions = charger_derniere_reflexion()
    except Exception as e:
        log.warning("Erreur chargement reflexion: %s", e)
        actions = []

    if not actions:
        log.info("Aucune action a evaluer.")
        return []

    # filtrer par confiance avant execution (tri par confiance decroissante)
    try:
        candidates = sorted(
            [a for a in actions if float(a.get("confiance", 0) or 0) >= SEUIL_CONFIANCE],
            key=lambda a: float(a.get("confiance", 0) or 0), reverse=True)
    except Exception:
        candidates = [a for a in actions
                     if (a.get("confiance") or 0) >= SEUIL_CONFIANCE]

    log.info("%d action(s) dans la reflexion, %d au-dessus du seuil %.2f",
             len(actions), len(candidates), SEUIL_CONFIANCE)

    resultats = []
    executees = 0
    for action in candidates:
        if executees >= MAX_ACTIONS_PAR_RUN:
            resultats.append((action.get("type", "?"), False,
                             f"MAX_ACTIONS_PAR_RUN ({MAX_ACTIONS_PAR_RUN}) atteint — skip"))
            continue
        try:
            ok, msg = executer_action(action, dry_run=dry_run)
        except Exception as e:
            ok, msg = False, f"erreur inattendue: {e}"
        resultats.append((action.get("type", "?"), ok, msg))
        if ok:
            executees += 1

    # digest Telegram
    try:
        execs = [(t, m) for t, ok, m in resultats if ok]
        if execs:
            prefixe = "🔎 [DRY-RUN] " if dry_run else "🤖 "
            resume = "\n".join(f"  - [{t}] {m}" for t, m in execs)
            msg = (f"{prefixe}REFLECTION-ACTION — {len(execs)} action(s) "
                  f"{'simulee(s)' if dry_run else 'executee(s)'}\n{resume}")
            log.info(msg)
            _tel(msg)
        else:
            log.info("Aucune action executee ce cycle (seuil confiance %.2f).",
                     SEUIL_CONFIANCE)
    except Exception as e:
        log.warning("Erreur digest Telegram: %s", e)

    return resultats


# ---------------------------------------------------------------- CLI
def cmd_etat():
    try:
        with open(LOG_FILE, encoding="utf-8") as f:
            lignes = f.readlines()
    except Exception:
        lignes = []
    print("=" * 55)
    print("REFLECTION-ACTION — ETAT")
    print(f"Seuil confiance: {SEUIL_CONFIANCE} | Max actions/run: {MAX_ACTIONS_PAR_RUN} "
         f"| Cooldown: {COOLDOWN_HEURES}h")
    print("=" * 55)
    if not lignes:
        print("(aucune action enregistree)")
        return
    print(f"{len(lignes)} entree(s) au total. Dernieres 10:")
    for ligne in lignes[-10:]:
        try:
            e = json.loads(ligne)
        except Exception:
            continue
        print(f"  [{e.get('ts')}] {e.get('action_type')} -> {e.get('target')} "
             f"| conf={e.get('confiance')} | {e.get('result')}")


def main():
    import sys
    argv = sys.argv[1:]
    if "etat" in argv:
        cmd_etat()
        return
    dry_run = "--dry-run" in argv or "-n" in argv
    if dry_run:
        log.info("Mode --dry-run: aucune ecriture ni alerte reelle d'execution.")
    resultats = executer_toutes(dry_run=dry_run)
    print("=" * 55)
    print(f"REFLECTION-ACTION — {'SIMULATION' if dry_run else 'EXECUTION'} — {_now()}")
    print("=" * 55)
    if not resultats:
        print("Aucune action a traiter.")
    for t, ok, m in resultats:
        print(f"  [{'OK' if ok else '--'}] {t}: {m}")
    print("=" * 55)


if __name__ == "__main__":
    main()
