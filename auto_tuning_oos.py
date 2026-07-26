#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
auto_tuning_oos.py — Auto-application du meilleur genome genetique quand
la fitness OUT-OF-SAMPLE (OOS) le justifie (self-improvement supervise).

genetic_optimizer.py fait deja evoluer une population et valide en walk-forward,
mais ne deploie que si un seul run bat la baseline+marge (voir DEPLOI_MARGE).
Ce module ajoute une couche de securite complementaire: il relit l'historique
des derniers runs (genetic_log.jsonl) et n'applique le genome que si l'OOS
est STABLE (>= seuil sur plusieurs runs consecutifs), pas juste un coup de
chance sur un seul cycle.

Genome (5 genes, cf. genetic_optimizer.BOUNDS):
  rsi_achat, rsi_vente, tp, sl, bb_ecart

Garde-fous:
  - OOS_FITNESS_MIN (env, defaut 1.5)   : fitness OOS minimale pour justifier
  - N_CONSECUTIF (defaut 3)             : nb de runs consecutifs >= seuil requis
  - COOLDOWN_HOURS = 24                 : pas de re-application avant 24h
  - jamais de crash: tout est wrappe try/except
  - alerte Telegram a chaque application reelle

CLI:
  python auto_tuning_oos.py               # pipeline complet (applique si justifie)
  python auto_tuning_oos.py --dry-run     # montre ce qui serait fait, n'applique rien
  python auto_tuning_oos.py --force       # applique le meilleur genome sans conditions
"""
import os
import sys
import json
import logging
from datetime import datetime, timedelta

from dotenv import load_dotenv

load_dotenv()

DOSSIER = os.path.dirname(os.path.abspath(__file__))
GENETIC_LOG = os.path.join(DOSSIER, "genetic_log.jsonl")
LECONS = os.path.join(DOSSIER, "lecons_apprises.jsonl")
SP_FILE = os.path.join(DOSSIER, "strat_params.json")
AUTO_TUNING_LOG = os.path.join(DOSSIER, "auto_tuning_log.jsonl")

TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN", "").strip()
TELEGRAM_CHAT_ID = os.getenv("TELEGRAM_CHAT_ID", "").strip()

# --- Garde-fous (surcharge possible via variables d'environnement) ---
OOS_FITNESS_MIN = float(os.getenv("OOS_FITNESS_MIN", "1.5"))
N_CONSECUTIF = int(os.getenv("N_CONSECUTIF", "3"))
COOLDOWN_HOURS = 24

logging.basicConfig(level=logging.INFO,
                    format="%(asctime)s [%(levelname)s] %(message)s",
                    datefmt="%H:%M:%S")
log = logging.getLogger("auto_tuning_oos")


# ---------------------------------------------------------------- UTILS
def _load_json(path, default):
    try:
        return json.load(open(path, encoding="utf-8"))
    except Exception:
        return default


def _save_json(path, data):
    try:
        with open(path, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
        return True
    except Exception as e:
        log.error(f"echec ecriture {path}: {e}")
        return False


def _tel(msg):
    """Alerte Telegram best-effort, ne doit jamais faire planter le pipeline."""
    try:
        from telegram_alerte import envoyer
        envoyer(msg)
    except Exception:
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


def _now_str():
    return datetime.utcnow().strftime("%Y-%m-%d %H:%M:%S UTC")


# ---------------------------------------------------------------- LECTURE DES RUNS
def _lire_jsonl(path):
    """Lit un fichier .jsonl ligne par ligne, ignore les lignes corrompues."""
    entries = []
    try:
        with open(path, encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                try:
                    entries.append(json.loads(line))
                except Exception:
                    continue
    except Exception:
        pass
    return entries


def _normaliser_entree(e):
    """Normalise une entree venant soit de genetic_log.jsonl (format cible:
    ts, generation, best_fitness, best_is_fitness, genome, stagnation), soit
    en repli de lecons_apprises.jsonl (format ecrit par record_lecon dans
    genetic_optimizer.py). Retourne un dict uniforme:
      {ts, genome, oos_fitness, is_fitness, deployed}
    """
    if not isinstance(e, dict):
        return None
    # Format genetic_log.jsonl attendu par la tache
    if "best_fitness" in e or "best_is_fitness" in e:
        genome = e.get("genome") or {}
        oos = e.get("best_fitness")
        is_fit = e.get("best_is_fitness")
        ts = e.get("ts") or e.get("date") or _now_str()
        return {
            "ts": ts,
            "genome": genome,
            "oos_fitness": float(oos) if oos is not None else None,
            "is_fitness": float(is_fit) if is_fit is not None else None,
            "deployed": e.get("deployed"),
            "stagnation": e.get("stagnation"),
            "generation": e.get("generation"),
        }
    # Format lecons_apprises.jsonl (record_lecon de genetic_optimizer.py)
    if e.get("source") == "genetic_optimizer" or "fitness_out_of_sample" in e:
        genome = e.get("genome") or {}
        oos = e.get("fitness_out_of_sample")
        is_fit = e.get("fitness_in_sample")
        ts = e.get("date") or _now_str()
        return {
            "ts": ts,
            "genome": genome,
            "oos_fitness": float(oos) if oos is not None else None,
            "is_fitness": float(is_fit) if is_fit is not None else None,
            "deployed": e.get("deployed"),
            "stagnation": None,
            "generation": e.get("generations"),
        }
    return None


def charger_derniers_runs(n=5):
    """Lit genetic_log.jsonl (format cible) et retourne les N dernieres
    entrees normalisees, les plus recentes en dernier. Si genetic_log.jsonl
    est absent/vide, se rabat sur lecons_apprises.jsonl (source=genetic_optimizer)
    pour ne jamais planter faute de fichier."""
    raw = _lire_jsonl(GENETIC_LOG)
    if not raw:
        log.info(f"{GENETIC_LOG} absent ou vide -> repli sur {LECONS}")
        raw_lecons = _lire_jsonl(LECONS)
        raw = [e for e in raw_lecons if e.get("source") == "genetic_optimizer"]
    normalises = []
    for e in raw:
        ne = _normaliser_entree(e)
        if ne is not None:
            normalises.append(ne)
    return normalises[-n:] if n else normalises


# ---------------------------------------------------------------- STABILITE
def evaluer_stabilite(runs):
    """Verifie que le meilleur genome a une fitness OOS >= OOS_FITNESS_MIN
    sur au moins N_CONSECUTIF runs consecutifs (les plus recents).
    Retourne (should_apply: bool, best_genome: dict|None, raison: str)."""
    if not runs:
        return False, None, "aucun run disponible dans genetic_log.jsonl"

    if len(runs) < N_CONSECUTIF:
        return False, None, (
            f"pas assez de runs ({len(runs)}/{N_CONSECUTIF} requis) pour juger la stabilite")

    # on regarde les N_CONSECUTIF derniers runs (les plus recents en fin de liste)
    derniers = runs[-N_CONSECUTIF:]
    fitnesses = [r.get("oos_fitness") for r in derniers]
    if any(f is None for f in fitnesses):
        return False, None, "fitness OOS manquante sur au moins un des derniers runs"

    sous_seuil = [f for f in fitnesses if f < OOS_FITNESS_MIN]
    if sous_seuil:
        pire = min(fitnesses)
        return False, None, (
            f"OOS instable: {len(sous_seuil)}/{N_CONSECUTIF} run(s) sous le seuil "
            f"{OOS_FITNESS_MIN} (pire={pire:+.2f})")

    # stable et au-dessus du seuil -> on prend le genome du run le plus recent
    dernier = derniers[-1]
    best_genome = dernier.get("genome")
    if not best_genome or not isinstance(best_genome, dict):
        return False, None, "genome manquant sur le dernier run stable"

    raison = (
        f"OOS stable >= {OOS_FITNESS_MIN} sur {N_CONSECUTIF} runs consecutifs "
        f"({', '.join(f'{f:+.2f}' for f in fitnesses)})")
    return True, best_genome, raison


# ---------------------------------------------------------------- COOLDOWN
def _derniere_application():
    """Retourne le timestamp (datetime) de la derniere application reelle
    loguee dans auto_tuning_log.jsonl, ou None."""
    entries = _lire_jsonl(AUTO_TUNING_LOG)
    for e in reversed(entries):
        ts = e.get("ts")
        if not ts:
            continue
        for fmt in ("%Y-%m-%d %H:%M:%S UTC", "%Y-%m-%d %H:%M:%S", "%Y-%m-%dT%H:%M:%S"):
            try:
                return datetime.strptime(ts, fmt)
            except Exception:
                continue
    return None


def _cooldown_actif():
    """True si une application a eu lieu il y a moins de COOLDOWN_HOURS."""
    dt = _derniere_application()
    if dt is None:
        return False, None
    delta = datetime.utcnow() - dt
    if delta < timedelta(hours=COOLDOWN_HOURS):
        restant = timedelta(hours=COOLDOWN_HOURS) - delta
        return True, restant
    return False, None


# ---------------------------------------------------------------- DIFF
def comparer_avec_actuel(genome):
    """Compare le genome candidat aux parametres actuels de strat_params.json.
    Retourne (diff: dict, a_des_changements: bool)."""
    sp = _load_json(SP_FILE, {})
    actuel = {
        "rsi_achat": sp.get("rsi_achat"),
        "rsi_vente": sp.get("rsi_vente"),
        "bb_ecart": sp.get("bb_ecart"),
        # tp/sl ne sont pas persistes dans strat_params.json par apply_genome
        # (ils vivent en memoire dans backtest_moteur), donc on les affiche
        # a titre indicatif si presents.
        "tp": sp.get("tp"),
        "sl": sp.get("sl"),
    }
    diff = {}
    for cle in ("rsi_achat", "rsi_vente", "tp", "sl", "bb_ecart"):
        avant = actuel.get(cle)
        apres = genome.get(cle)
        if avant != apres:
            diff[cle] = {"avant": avant, "apres": apres}
    return diff, actuel


def _afficher_diff(diff, actuel, genome):
    if not diff:
        print("  (aucun changement: le genome candidat == parametres actuels)")
        return
    print("  Changements proposes:")
    for cle, v in diff.items():
        avant = v["avant"] if v["avant"] is not None else "?"
        print(f"    {cle:<10} {avant} -> {v['apres']}")


# ---------------------------------------------------------------- APPLICATION
def appliquer_genome(genome, oos_fitness=None, raison=""):
    """Applique le genome via genetic_optimizer.apply_genome(), logue le
    changement dans auto_tuning_log.jsonl et envoie une alerte Telegram.
    Ne leve jamais d'exception (retourne False en cas d'echec)."""
    try:
        old_params = _load_json(SP_FILE, {})
        diff, actuel = comparer_avec_actuel(genome)

        import genetic_optimizer as go
        go.apply_genome(genome)

        new_params = _load_json(SP_FILE, {})
        new_params["dernier_auto_tuning_oos"] = {
            "date": _now_str(),
            "genome": genome,
            "oos_fitness": oos_fitness,
            "raison": raison,
        }
        _save_json(SP_FILE, new_params)

        entry = {
            "ts": _now_str(),
            "genome": genome,
            "old_params": old_params,
            "new_params": new_params,
            "oos_fitness": oos_fitness,
            "reason": raison,
        }
        _log_jsonl(AUTO_TUNING_LOG, entry)

        msg = (
            "🧬 AUTO-TUNING OOS: nouveau genome applique\n"
            f"OOS fitness: {oos_fitness}\n"
            f"RSI achat/vente: {genome.get('rsi_achat')}/{genome.get('rsi_vente')}\n"
            f"TP/SL: {genome.get('tp')}/{genome.get('sl')} | BB ecart: {genome.get('bb_ecart')}\n"
            f"Raison: {raison}")
        log.info(msg.replace("\n", " | "))
        _tel(msg)
        return True
    except Exception as e:
        log.error(f"echec appliquer_genome: {e}")
        try:
            _log_jsonl(AUTO_TUNING_LOG, {
                "ts": _now_str(), "genome": genome, "old_params": None,
                "new_params": None, "oos_fitness": oos_fitness,
                "reason": f"ECHEC: {e}"})
        except Exception:
            pass
        return False


# ---------------------------------------------------------------- CLI PIPELINE
def main():
    dry_run = "--dry-run" in sys.argv
    force = "--force" in sys.argv

    print("=" * 60)
    print("AUTO-TUNING OOS — application conditionnelle du genome genetique")
    print(f"Seuils: OOS_FITNESS_MIN={OOS_FITNESS_MIN} | N_CONSECUTIF={N_CONSECUTIF} | "
          f"COOLDOWN_HOURS={COOLDOWN_HOURS}")
    print("=" * 60)

    try:
        runs = charger_derniers_runs(max(N_CONSECUTIF, 5))
        print(f"Runs charges: {len(runs)}")
        for r in runs:
            print(f"  ts={r.get('ts')} oos={r.get('oos_fitness')} is={r.get('is_fitness')}")

        should_apply, best_genome, raison = evaluer_stabilite(runs)
        print("-" * 60)
        print(f"Stabilite OOS: {'OK' if should_apply else 'NON'} — {raison}")

        if force:
            if not runs:
                print("--force demande mais aucun run disponible: abandon.")
                return
            # avec --force on prend le genome le plus recent, meme si instable
            best_genome = runs[-1].get("genome")
            oos_fit = runs[-1].get("oos_fitness")
            should_apply = True
            raison = f"--force applique (bypass des seuils) | dernier OOS={oos_fit}"
            print(f"FORCE: {raison}")
        else:
            oos_fit = runs[-1].get("oos_fitness") if runs else None

        if not should_apply or best_genome is None:
            print("Aucune application: conditions non remplies.")
            return

        diff, actuel = comparer_avec_actuel(best_genome)
        print("-" * 60)
        _afficher_diff(diff, actuel, best_genome)

        if not diff and not force:
            print("Genome candidat identique aux parametres actuels — rien a faire.")
            return

        cooldown, restant = _cooldown_actif()
        if cooldown and not force:
            print(f"COOLDOWN ACTIF: derniere application il y a moins de "
                  f"{COOLDOWN_HOURS}h (reste {restant}). Abandon.")
            return
        elif cooldown and force:
            print(f"COOLDOWN actif mais --force demande: application forcee malgre "
                  f"{restant} restant.")

        if dry_run:
            print("-" * 60)
            print("[--dry-run] Aucune application reelle. Voici ce qui serait fait:")
            print(f"  genome: {best_genome}")
            print(f"  raison: {raison}")
            return

        print("-" * 60)
        ok = appliquer_genome(best_genome, oos_fitness=oos_fit, raison=raison)
        print("Application reussie." if ok else "Echec de l'application (voir logs).")

    except Exception as e:
        log.error(f"erreur pipeline auto_tuning_oos: {e}")
        print(f"ERREUR: {e}")


if __name__ == "__main__":
    main()
