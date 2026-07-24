#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""consensus_ia.py — Consensus multi-modèles (Feature 3).

L'agent interroge plusieurs modèles (Perplexity, Gemini, Claude, ChatGPT) en
parallèle sur la même question et prend le consensus (vote à la majorité).

Mécanisme générique + helper spécialisé pour les décisions d'ACHAT trading:
  consensus(prompt, modeles, quorum) -> (reponses, meta)
    Query parallèle de chaque modèle (ThreadPoolExecutor + timeout par modèle).
    Retourne la liste [(modele, reponse)] + meta (quorum atteint?, modele_fiable).

  consensus_achats(prompt, modeles, quorum) -> (set_symboles, meta)
    Chaque modèle produit sa liste d'ACHAT. Un actif n'est retenu que s'il est
    flaggé ACHAT par >= quorum modèles (vote majorité). Plus conservateur et
    plus robuste qu'un seul modèle.

Fail-open: si < quorum modèles répondent (rate-limits, indispo), retourne None
  -> l'appelant bascule sur le chemin mono-modèle existant (safe, pas de blocage).

Intégration: analyser_signaux_ia (paper_trading) derrière CONSENSUS_IA=1.
Toggle: CONSENSUS_IA=0 (defaut) = chemin mono-modèle existant.
QUORUM via CONSENSUS_QUORUM (defaut 2). MODELES via CONSENSUS_MODELES (csv).
"""
import os
from concurrent.futures import ThreadPoolExecutor, as_completed

PER_MODEL_TIMEOUT = 70  # secondes par modèle (les LLM peuvent etre lents)
MODELES_DEFAUT = ["perplexity", "gemini", "claude", "chatgpt"]
QUORUM_DEFAUT = 2


def _modeles_disponibles(prefere=None):
    """Retourne les modèles disponibles (via agent.disponible)."""
    try:
        from agent import disponible
    except Exception:
        return []
    prefere = prefere or [m for m in MODELES_DEFAUT
                         if os.getenv("CONSENSUS_MODELES", "").lower() == "" or
                         m in os.getenv("CONSENSUS_MODELES", "").lower().split(",")]
    custom = os.getenv("CONSENSUS_MODELES", "").strip()
    if custom:
        prefere = [m.strip() for m in custom.split(",") if m.strip()]
    return [m for m in prefere if disponible(m)]


def _query_one(modele, prompt):
    """Appelle un modèle, retourne (modele, reponse). Gère erreurs/timeout."""
    try:
        from agent import appeler_ia
        rep, _ = appeler_ia(modele, prompt)
        return modele, rep
    except Exception as e:
        return modele, f"[Erreur consensus {modele}: {e}]"


def consensus(prompt, modeles=None, quorum=None):
    """Query parallèle multi-modèles. Retourne (reponses, meta).
    reponses = [(modele, texte), ...] (uniquement les réponses valides)
    meta = {quorum, n_ok, modele_fiable, quorum_atteint}
    """
    quorum = quorum or int(os.getenv("CONSENSUS_QUORUM", str(QUORUM_DEFAUT)))
    dispo = _modeles_disponibles(modeles)
    if not dispo:
        return [], {"quorum": quorum, "n_ok": 0, "quorum_atteint": False,
                    "modele_fiable": None, "raison": "aucun modele disponible"}
    reponses = []
    with ThreadPoolExecutor(max_workers=min(4, len(dispo))) as pool:
        futures = {pool.submit(_query_one, m, prompt): m for m in dispo}
        for fut in as_completed(futures, timeout=PER_MODEL_TIMEOUT + 10):
            m = futures[fut]
            try:
                modele, rep = fut.result(timeout=PER_MODEL_TIMEOUT)
            except Exception as e:
                modele, rep = m, f"[Erreur timeout {m}: {e}]"
            if rep and not str(rep).startswith("[Erreur"):
                reponses.append((modele, rep))
    n_ok = len(reponses)
    fiable = reponses[0][0] if reponses else None
    return reponses, {"quorum": quorum, "n_ok": n_ok,
                      "quorum_atteint": n_ok >= quorum,
                      "modele_fiable": fiable}


def _extraire_achats(texte):
    """Extrait les actifs flaggés ACHAT dans une réponse texte.
    Retourne un set de chaînes (lignes/noms d'actif mentionnés en ACHAT)."""
    achats = set()
    if not texte:
        return achats
    # on ne court-circuite PAS sur "AUCUN SIGNAL": une réponse peut mélanger
    # des lignes ACHAT et un "AUCUN SIGNAL pour le reste". Le loop ci-dessous
    # ne retiendra que les lignes contenant ACHAT (set vide sinon).
    for ligne in texte.split("\n"):
        if "ACHAT" not in ligne.upper():
            continue
        # extrait le nom de l'actif après "ACHAT:" ou "ACHAT -"
        rest = ligne
        for sep in ("ACHAT:", "ACHAT -", "ACHAT-", "ACHAT ", "ACHAT:"):
            if sep in ligne.upper():
                idx = ligne.upper().index(sep) + len(sep)
                rest = ligne[idx:]
                break
        # nom = texte avant " | " ou "RAISON" ou fin de ligne
        nom = rest
        for cut in (" | ", "|", "RAISON", "Raison", " - ", "(", " :"):
            if cut in nom:
                nom = nom.split(cut)[0]
                break
        nom = nom.strip(" :-|").strip()
        if nom and len(nom) < 60:
            achats.add(nom)
    return achats


def consensus_achats(prompt, modeles=None, quorum=None):
    """Consensus sur les décisions d'ACHAT.
    Retourne (set_actifs_consensus, meta).
    set_actifs_consensus = actifs flaggés ACHAT par >= quorum modèles.
    Si < quorum modèles ont répondu -> (None, meta) (fail-open).
    meta contient le détail par modèle pour audit/log.
    """
    quorum = quorum or int(os.getenv("CONSENSUS_QUORUM", str(QUORUM_DEFAUT)))
    reponses, meta = consensus(prompt, modeles, quorum)
    if not meta.get("quorum_atteint"):
        return None, {**meta, "par_modele": {m: list(_extraire_achats(r))
                                            for m, r in reponses}}
    # vote: compte par actif
    from collections import defaultdict
    votes = defaultdict(set)  # actif -> {modeles qui l'ont flaggé}
    par_modele = {}
    for modele, rep in reponses:
        achats = _extraire_achats(rep)
        par_modele[modele] = list(achats)
        for a in achats:
            votes[a].add(modele)
    # normalisation: un actif peut être nommé légèrement différemment -> on garde
    # les noms bruts; le matching fin est laissé à l'appelant (mots-clés marché)
    consensus_set = {actif for actif, ms in votes.items() if len(ms) >= quorum}
    return consensus_set, {**meta, "par_modele": par_modele,
                           "votes": {a: list(ms) for a, ms in votes.items()}}


if __name__ == "__main__":
    # smoke test rapide (nécessite agent.py + clés)
    r, meta = consensus("Donne 1 mot: OK")
    print("Réponses:", [(m, t[:40]) for m, t in r])
    print("Meta:", meta)
