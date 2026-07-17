#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Patch actions_executor.py:
1) desactiver_strategie gère actif='ALL' (coupe sur tous les actifs perdants, validé)
2) nouveau handler assigner_strategie (sécurisé: suggestion + Telegram, pas d'auto-trade)
3) dispatch reconnait assigner_strategie
+ test live: coupe MACD Momentum partout si perdant."""
import os, sys

FICHIER = os.path.join(os.getcwd(), "actions_executor.py")
src = open(FICHIER, encoding="utf-8").read()
orig = src

# ---------- EDIT 1: branche ALL dans desactiver_strategie ----------
E1_OLD = '''    data = _load(PRUNING_FILE, {"desactivees": {}, "dernier_cycle": None})
    desact = data.setdefault("desactivees", {})
    cle = _cle(strategie, actif)'''
E1_NEW = '''    data = _load(PRUNING_FILE, {"desactivees": {}, "dernier_cycle": None})
    desact = data.setdefault("desactivees", {})
    # --- Mode multi-actifs : désactive sur TOUS les actifs où la stratégie est perdante ---
    if isinstance(actif, str) and actif.upper() in ("ALL", "TOUS", "*"):
        return _desactiver_strategie_all(strategie, raison, data, desact)
    cle = _cle(strategie, actif)'''
assert E1_OLD in src, "EDIT1: bloc desactiver_strategie introuvable"
src = src.replace(E1_OLD, E1_NEW)

# ---------- EDIT 2: ajouter helpers _desactiver_strategie_all + assigner_strategie ----------
E2_OLD = '''def stats_strategies():
    try:
        from auto_pruning import stats_strategies as _s
        return _s()
    except Exception:
        return {}


'''
E2_NEW = '''def stats_strategies():
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
        f.write(json.dumps(entry, ensure_ascii=False) + "\\n")
    _tel(f"💡 Suggestion réflexion: assigner '{strategie}' à {actif} "
         f"— {(raison or '')[:80]} (validation manuelle recommandée)")
    return True, (f"suggestion enregistrée: {strategie}→{actif} "
                  f"(auto-assign désactivée pour sécurité)")


'''
assert E2_OLD in src, "EDIT2: bloc stats_strategies introuvable"
src = src.replace(E2_OLD, E2_NEW)

# ---------- EDIT 3: dispatch reconnait assigner_strategie ----------
E3_OLD = '''            elif atype == "ajuster_sl":
                ok, msg = ajuster_tp_sl(a.get("actif"), sl=a.get("sl"),
                                        raison=a.get("raison", ""))
                results.append((atype, ok, msg))
            else:
                results.append((atype, False, f"type inconnu: {atype}")'''
E3_NEW = '''            elif atype == "ajuster_sl":
                ok, msg = ajuster_tp_sl(a.get("actif"), sl=a.get("sl"),
                                        raison=a.get("raison", ""))
                results.append((atype, ok, msg))
            elif atype == "assigner_strategie":
                ok, msg = assigner_strategie(a.get("actif"), a.get("strategie"),
                                            a.get("raison", ""))
                results.append((atype, ok, msg))
            else:
                results.append((atype, False, f"type inconnu: {atype}")'''
assert E3_OLD in src, "EDIT3: bloc dispatch introuvable"
src = src.replace(E3_OLD, E3_NEW)

# ---------- ecriture ----------
if src == orig:
    print("⚠️ Aucune modification appliquée (déjà patché ?)")
    sys.exit(1)
open(FICHIER, "w", encoding="utf-8").write(src)
print("✅ actions_executor.py patché (3 éditions)")

# ---------- verif syntaxe ----------
import py_compile
try:
    py_compile.compile(FICHIER, doraise=True)
    print("✅ compilation OK")
except py_compile.PyCompileError as e:
    print(f"❌ erreur syntaxe: {e}")
    sys.exit(1)

# ---------- import test ----------
sys.path.insert(0, os.getcwd())
import importlib
import actions_executor
importlib.reload(actions_executor)
print("✅ import actions_executor OK")
print("✅ fonctions présentes:", hasattr(actions_executor, "_desactiver_strategie_all"),
      hasattr(actions_executor, "assigner_strategie"))
