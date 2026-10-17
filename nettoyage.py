#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""nettoyage.py — Range les fichiers morts du bot dans archive/<date>/ (rien n'est supprime).

Securite: un fichier reference par le crontab, par un service systemd ou importe par un module
vivant n'est JAMAIS deplace. Mode simulation par defaut.

Usage: python3 nettoyage.py          (simulation: montre ce qui serait range)
       python3 nettoyage.py --go     (range vraiment)
       python3 nettoyage.py --retour archive/2026xxxx_xxxx   (remet tout en place)
"""
import glob
import os
import re
import shutil
import subprocess
import sys
from datetime import datetime

DOSSIER = os.path.dirname(os.path.abspath(__file__))
os.chdir(DOSSIER)

# Modules qui font tourner le bot (services) — leurs imports (recursifs) sont proteges
RACINES = {"paper_trading", "chat_naturel", "dashboard_premium", "watchdog", "pont_revolut", "nouveau_depart", "nettoyage",
           "cerveau", "journal_erreurs", "registre_strategies", "kraken_paper"}
# Scripts d'analyse ponctuels / anciens / doublons connus (ranges s'ils ne sont pas references)
CANDIDATS_PY = ["analyse_20sept", "analyse_deep", "analyse_perf", "analyse_pertes", "analyse_pertes_v2", "analyser_trades",
                "apprentissage", "backtest_nouveaux_params", "bilan", "bilan_complet", "fix_positions_ia", "ia_render",
                "lancer_analyse", "reparer_json", "reset_portfolio", "restaurer_apprentissage", "savoir_trader_pro",
                "scanner_bot", "strategies", "test_cerveaux", "test_ollama"]
# Anciens scripts de deploiement / patchs one-shot
CANDIDATS_SH = ["deploy_5features.sh", "deploy_signaux.sh", "deploy_social.sh", "enable_scalping.sh", "relax_signals.sh",
                "dashboard_service_patch.sh", "fix_crons_v2.sh", "fix_mt5_python.sh", "install_mt5.sh"]
CANDIDATS_AUTRES = ["p1.b64", "dashboard_server.py.bak.ia", "reflection_gemini.py.bak.actions", "rapport_evolution_agent.md"]


def imports_de(fichier):
    try:
        src = open(fichier, errors="ignore").read()
    except Exception:
        return set()
    found = set()
    for pat in [r"^\s*import\s+([\w\.]+)", r"^\s*from\s+([\w\.]+)\s+import", r"import\s+(\w+)\s+as\s+\w+",
                r"importlib\.import_module\([\"'](\w+)[\"']", r"__import__\([\"'](\w+)[\"']"]:
        for x in re.findall(pat, src, re.M):
            found.add(x.split(".")[0])
    return found


def modules_vivants():
    mods = {os.path.splitext(f)[0] for f in glob.glob("*.py")}
    vivants, pile = set(), list(RACINES & mods)
    while pile:
        m = pile.pop()
        if m in vivants:
            continue
        vivants.add(m)
        pile += [x for x in imports_de(m + ".py") if x in mods and x not in vivants]
    return vivants


def references_externes():
    """Fichiers cites par le crontab et les services systemd."""
    refs = set()
    try:
        out = subprocess.run(["crontab", "-l"], capture_output=True, text=True, timeout=10).stdout
        refs |= set(re.findall(r"([\w\.-]+\.(?:py|sh))", out))
    except Exception:
        pass
    for unit in glob.glob("/etc/systemd/system/*.service") + glob.glob(os.path.expanduser("~/.config/systemd/user/*.service")):
        try:
            refs |= set(re.findall(r"([\w\.-]+\.(?:py|sh))", open(unit, errors="ignore").read()))
        except Exception:
            pass
    return refs


def main():
    if len(sys.argv) >= 3 and sys.argv[1] == "--retour":
        src = sys.argv[2]
        n = 0
        for f in os.listdir(src):
            shutil.move(os.path.join(src, f), os.path.join(DOSSIER, f)); n += 1
        print(f"{n} fichier(s) remis en place depuis {src}"); return 0

    go = "--go" in sys.argv
    vivants = modules_vivants()
    refs = references_externes()
    a_ranger, proteges = [], []

    for m in CANDIDATS_PY:
        f = m + ".py"
        if not os.path.exists(f):
            continue
        if m in vivants or f in refs:
            proteges.append((f, "importe par un module vivant" if m in vivants else "cite par crontab/systemd"))
        else:
            a_ranger.append(f)
    for f in CANDIDATS_SH + CANDIDATS_AUTRES:
        if os.path.exists(f):
            (proteges if f in refs else a_ranger).append((f, "cite par crontab/systemd") if f in refs else f)
    # sauvegardes .bak*, backups json dates, anciens resultats de backtests
    for f in glob.glob("*.bak*") + glob.glob("*_backup_*.json") + glob.glob("backtest_*_resultats.json"):
        if f not in a_ranger and f not in refs:
            a_ranger.append(f)
    # caches python
    pyc = glob.glob("**/__pycache__", recursive=True)

    print(f"Modules vivants (services + imports): {len(vivants)}")
    print(f"References crontab/systemd: {len(refs)}")
    print(f"\nA RANGER ({len(a_ranger)}):")
    for f in sorted(a_ranger):
        try:
            print(f"  {f:45s} {os.path.getsize(f)/1024:7.1f} Ko")
        except Exception:
            print(f"  {f}")
    if proteges:
        print(f"\nPROTEGES (non deplaces):")
        for f, why in proteges:
            print(f"  {f:45s} {why}")
    print(f"\nCaches __pycache__: {len(pyc)} dossier(s)")

    if not go:
        print("\nSimulation. Lance avec --go pour ranger (reversible avec --retour archive/<date>).")
        return 0
    dest = os.path.join(DOSSIER, "archive", datetime.now().strftime("%Y%m%d_%H%M"))
    os.makedirs(dest, exist_ok=True)
    for f in a_ranger:
        shutil.move(f, os.path.join(dest, f))
    for d in pyc:
        shutil.rmtree(d, ignore_errors=True)
    print(f"\n{len(a_ranger)} fichier(s) ranges dans {dest}. Retour possible: python3 nettoyage.py --retour {os.path.relpath(dest)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
