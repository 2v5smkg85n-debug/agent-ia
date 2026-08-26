#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Rotation automatique des logs.
Garde les 3 derniers fichiers de log, supprime les plus anciens.
Appelé au démarrage du bot et à chaque minuit.
"""
import os
import glob
from datetime import datetime

DOSSIER = os.path.dirname(os.path.abspath(__file__))
LOG_PRINCIPAL = os.path.join(DOSSIER, "paper_trading.log")
TAILLE_MAX = 5 * 1024 * 1024  # 5 MB
NB_ARCHIVES = 3  # garde paper_trading.log.1, .2, .3


def rotation(force=False):
    """Effectue la rotation si le log dépasse TAILLE_MAX."""
    if not os.path.exists(LOG_PRINCIPAL):
        return False
    taille = os.path.getsize(LOG_PRINCIPAL)
    if not force and taille < TAILLE_MAX:
        return False
    # Décale les archives existantes
    for i in range(NB_ARCHIVES, 0, -1):
        src = f"{LOG_PRINCIPAL}.{i}"
        dst = f"{LOG_PRINCIPAL}.{i + 1}" if i < NB_ARCHIVES else None
        if os.path.exists(src):
            if dst:
                os.rename(src, dst)
            else:
                os.remove(src)
    # Archive le log courant
    os.rename(LOG_PRINCIPAL, f"{LOG_PRINCIPAL}.1")
    # Nettoie les vieux logs (> NB_ARCHIVES)
    for old in glob.glob(f"{LOG_PRINCIPAL}.*"):
        try:
            num = int(old.rsplit(".", 1)[-1])
            if num > NB_ARCHIVES:
                os.remove(old)
        except (ValueError, OSError):
            pass
    print(f"[LOG-ROTATION] Log roté ({taille // 1024} KB -> archive)")
    return True


if __name__ == "__main__":
    rotation(force=True)
