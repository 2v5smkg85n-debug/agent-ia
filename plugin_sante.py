#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""plugin_sante.py — Santé des plugins + auto-rollback. Filet de sécurité de
l'auto-évolution: si un plugin (auto-généré ou non) veto quasi-systématiquement
ou plante trop, il est automatiquement déplacé vers plugins_disabled/. Le
loader mtime-aware le retirera au prochain trade (sans restart).

Compteurs (plugin_sante.json): par plugin {seen, vetoed, errors, disabled, raison}.
record(nom, outcome) est appelé par ouvrir_position à chaque hook (allow/veto/error).
verifier() est lancé par cron (horaire) pour désactiver les plugins défaillants.

Seuils (conservateurs — un bon plugin peut veto beaucoup en bear market):
  - MIN_OPPORTUNITES = 15  (ne juge pas avant 15 entrées tentées)
  - MAX_VETO_RATE = 0.95   (>95% de veto sur 15+ entrées -> désactive)
  - MAX_ERREURS = 5        (>5 erreurs -> désactive, plugin bugué)"""
import os
import json
import shutil
from datetime import datetime

try:
    from dotenv import load_dotenv
    load_dotenv(os.path.join(os.path.dirname(os.path.abspath(__file__)), ".env"))
except Exception:
    pass

DOSSIER = os.path.dirname(os.path.abspath(__file__))
STATE_FILE = os.path.join(DOSSIER, "plugin_sante.json")
PLUGINS_DIR = os.path.join(DOSSIER, "plugins")
DISABLED_DIR = os.path.join(DOSSIER, "plugins_disabled")
TELEGRAM_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN", "")
TELEGRAM_CHAT = os.getenv("TELEGRAM_CHAT_ID", "")

MIN_OPPORTUNITES = 15
MAX_VETO_RATE = 0.95
MAX_ERREURS = 5


def _load():
    try:
        with open(STATE_FILE) as f:
            return json.load(f)
    except Exception:
        return {}


def _save(s):
    try:
        with open(STATE_FILE, "w") as f:
            json.dump(s, f, indent=2)
    except Exception:
        pass


def record(nom_plugin, outcome):
    """outcome: 'allow' | 'veto' | 'error'. Incrémente les compteurs (appelé par ouvrir_position)."""
    try:
        s = _load()
        p = s.setdefault(nom_plugin, {"seen": 0, "vetoed": 0, "errors": 0,
                                     "disabled": False, "raison": ""})
        p["seen"] += 1
        if outcome == "veto":
            p["vetoed"] += 1
        elif outcome == "error":
            p["errors"] += 1
        _save(s)
    except Exception:
        pass


def _alerter(nom, raison):
    if not TELEGRAM_TOKEN or not TELEGRAM_CHAT:
        return
    try:
        import requests
        msg = (f"⚠️ Plugin auto-désactivé\n\n"
               f"Plugin: {nom}\nRaison: {raison}\n\n"
               f"Déplacé vers plugins_disabled/. Le loader le retirera au prochain trade.\n"
               f"Pour ré-essayer: mv plugins_disabled/{nom} plugins/")
        requests.post(f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage",
                      json={"chat_id": TELEGRAM_CHAT, "text": msg}, timeout=10)
    except Exception:
        pass


def _desactiver(nom, raison):
    """Déplace plugins/<nom> vers plugins_disabled/<nom> + marque disabled."""
    try:
        os.makedirs(DISABLED_DIR, exist_ok=True)
        src = os.path.join(PLUGINS_DIR, nom)
        dst = os.path.join(DISABLED_DIR, nom)
        if os.path.isfile(src):
            shutil.move(src, dst)
        s = _load()
        p = s.setdefault(nom, {})
        p.update({"disabled": True, "raison": raison,
                  "desactive_le": datetime.utcnow().isoformat(),
                  "seen": 0, "vetoed": 0, "errors": 0})
        _save(s)
        _alerter(nom, raison)
        print(f"[plugin_sante] DÉSACTIVÉ {nom}: {raison}")
        return True
    except Exception as e:
        print(f"[plugin_sante] erreur désactivation {nom}: {e}")
        return False


def verifier():
    """Vérifie tous les plugins trackés. Désactive les défaillants. Retourne la liste."""
    s = _load()
    desactives = []
    for nom, p in list(s.items()):
        if p.get("disabled"):
            continue
        seen = p.get("seen", 0)
        if seen < MIN_OPPORTUNITES:
            continue
        rate = p.get("vetoed", 0) / seen if seen > 0 else 0
        errs = p.get("errors", 0)
        if errs >= MAX_ERREURS:
            if _desactiver(nom, f"{errs} erreurs sur {seen} appels (buggy)"):
                desactives.append(nom)
        elif rate > MAX_VETO_RATE:
            if _desactiver(nom, f"veto {rate*100:.0f}% ({p.get('vetoed')}/{seen} entrées bloquées)"):
                desactives.append(nom)
    if not desactives:
        print("[plugin_sante] tous les plugins sains (aucune désactivation)")
    return desactives


def etat_display():
    """Résumé pour digests."""
    s = _load()
    actifs = sum(1 for p in s.values() if not p.get("disabled"))
    desact = sum(1 for p in s.values() if p.get("disabled"))
    lignes = [f"Plugins santé: {actifs} actif(s), {desact} désactivé(s)"]
    for nom, p in list(s.items())[:5]:
        st = "🛑 désactivé" if p.get("disabled") else "✅ actif"
        lignes.append(f"   • {nom}: {st} (seen={p.get('seen',0)}, veto={p.get('vetoed',0)}, err={p.get('errors',0)})")
    return "\n".join(lignes)


if __name__ == "__main__":
    print("=" * 60)
    print("PLUGIN SANTÉ (auto-rollback)")
    print("=" * 60)
    d = verifier()
    print()
    print(etat_display())
