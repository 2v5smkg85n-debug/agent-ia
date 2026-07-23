#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""patch_pont_guards.py - ajoute kill switch + limite achats/jour au pont Revolut.

Gardes DEFENSIFS anti-bug (l'utilisateur a choisi "tout automatique", donc pas
de friction par trade, mais on protege contre un runaway):
  1. KILL SWITCH: PONT_KILL=1 -> cycle() skippe tout instantanement (stop urgence)
  2. LIMITE ACHATS/JOUR: PONT_MAX_TRADES_JOUR (defaut 8) -> bloque au-dela
     (empeche un bug de boucle de placer 100 ordres en une journee)

Additif et idempotent. Ne touche PAS au mapping BINANCE_TO_REVOLUTX.
"""
import os

P = os.path.join(os.path.dirname(os.path.abspath(__file__)), "pont_revolut.py")
src = open(P).read()

def _patch(anchor, insert_before, label, marker):
    global src
    if marker in src:
        print(f"[pont] {label} DEJA present -> skip")
        return
    if anchor not in src:
        print(f"[pont] ERREUR ancre {label} introuvable")
        raise SystemExit(1)
    src = src.replace(anchor, insert_before + anchor, 1)
    print(f"[pont] {label} ajoute")

# 1) constante MAX_ACHATS_JOUR apres BOUCLE_INTERVAL
_patch(
    "BOUCLE_INTERVAL = 60",
    "MAX_ACHATS_JOUR = int(os.getenv(\"PONT_MAX_TRADES_JOUR\", \"8\"))  # anti-bug runaway\n",
    "const MAX_ACHATS_JOUR", "MAX_ACHATS_JOUR =",
)

# 2) helper _nb_achats_aujourdhui avant miroirer_achat
HELPER = "\n".join([
    "def _nb_achats_aujourdhui(mirror):",
    "    _auj = datetime.now().strftime(\"%Y-%m-%d\")",
    "    _n = 0",
    "    for _v in mirror.get(\"achats\", {}).values():",
    "        if str(_v.get(\"date_miroir\", \"\")).startswith(_auj):",
    "            _n += 1",
    "    return _n",
    "",
    "",
])
_patch(
    "def miroirer_achat(client, position, mirror):",
    HELPER,
    "helper _nb_achats_aujourdhui", "def _nb_achats_aujourdhui",
)

# 3) kill switch en tete de cycle()
KILL = "\n".join([
    "    if os.getenv(\"PONT_KILL\", \"0\") == \"1\":",
    "        log.warning(\"[KILL] pont Revolut X desactive (PONT_KILL=1) -> cycle skip\")",
    "        return",
]) + "\n"
_patch(
    "    pt = _load(PT_FILE, {})",
    KILL,
    "kill switch", "PONT_KILL",
)

# 4) garde nb achats/jour avant le fetch prix dans miroirer_achat
GARDE = "\n".join([
    "    _naj = _nb_achats_aujourdhui(mirror)",
    "    if _naj >= MAX_ACHATS_JOUR:",
    "        log.warning(\"[GARDE] %d achats miroires aujourd hui (max %d) -> skip\", _naj, MAX_ACHATS_JOUR)",
    "        return",
]) + "\n"
_patch(
    "    prix = _prix_revolut(client, paire)",
    GARDE,
    "garde nb achats/jour", "_naj >= MAX_ACHATS_JOUR",
)

open(P, "w").write(src)
print("[pont] gardes appliques: kill switch (PONT_KILL) + limite achats/jour (PONT_MAX_TRADES_JOUR=8)")
