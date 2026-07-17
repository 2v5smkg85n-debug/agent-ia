#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""patch_lecons_reflection.py
Câble lecons_apprises.jsonl dans reflection_gemini.py:
1) Ajoute charger_lecons() — lit les hypotheses rejetees par backtest
2) Injecte une section 'LECONS APPRISES' dans le prompt (avant SAGESSE)
   pour que l'IA ne re-propose pas des idees deja infirmees.
3) Test offline: vérifie que le prompt contient la leçon ADX.
"""
import os, sys

DOSSIER = os.getcwd()
RG = os.path.join(DOSSIER, "reflection_gemini.py")
src = open(RG, encoding="utf-8").read()

# 1) Ajoute charger_lecons() avant l'import sagesse
ANCHOR_FUNC = '''        "positions_ouvertes": [{"symbole": p.get("symbole"),
                                "strategie": _extraire_strategie(p),
                                "montant": p.get("montant_eur"),
                                "variation": p.get("variation_pct")}
                               for p in positions],
    }


from sagesse_traders import sagesse_prompt'''

NEW_FUNC = '''        "positions_ouvertes": [{"symbole": p.get("symbole"),
                                "strategie": _extraire_strategie(p),
                                "montant": p.get("montant_eur"),
                                "variation": p.get("variation_pct")}
                               for p in positions],
    }


def charger_lecons():
    """Charge les lecons apprises (hypotheses rejetees par backtest).
    L'IA ne doit PAS re-proposer ces idees."""
    import os as _os
    _f = _os.path.join(_os.path.dirname(_os.path.abspath(__file__)),
                       "lecons_apprises.jsonl")
    try:
        lecons = []
        with open(_f, encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if line:
                    lecons.append(json.loads(line))
        if not lecons:
            return "(aucune lecon encore)"
        return "\\n".join(
            f"[{i}] {l.get('hypothese','?')} -> {l.get('resultat','?')} "
            f"({l.get('decision','?')})"
            for i, l in enumerate(lecons, 1)
        )
    except Exception:
        return "(aucune lecon encore)"


from sagesse_traders import sagesse_prompt'''

if "def charger_lecons" not in src:
    assert ANCHOR_FUNC in src, "ancrage gather_contexte introuvable"
    src = src.replace(ANCHOR_FUNC, NEW_FUNC, 1)
    print("✅ charger_lecons() ajoutée")
else:
    print("ℹ️ charger_lecons() déjà présente")

# 2) Injecte la section LECONS dans le prompt avant SAGESSE
ANCHOR_PROMPT = '''POSITIONS OUVERTES ACTUELLES:
{json.dumps(ctx['positions_ouvertes'], ensure_ascii=False, indent=2) or '(aucune)'}

SAGESSE DES GRANDS TRADERS (applique ces principes a ton analyse ci-dessous):'''

NEW_PROMPT = '''POSITIONS OUVERTES ACTUELLES:
{json.dumps(ctx['positions_ouvertes'], ensure_ascii=False, indent=2) or '(aucune)'}

LECONS APPRISES (NE RE-PROPOSE PAS CES IDEES, deja rejetees par backtest):
{charger_lecons()}

SAGESSE DES GRANDS TRADERS (applique ces principes a ton analyse ci-dessous):'''

if "LECONS APPRISES" not in src:
    assert ANCHOR_PROMPT in src, "ancrage prompt SAGESSE introuvable"
    src = src.replace(ANCHOR_PROMPT, NEW_PROMPT, 1)
    print("✅ section LECONS injectée dans le prompt")
else:
    print("ℹ️ section LECONS déjà présente")

open(RG, "w", encoding="utf-8").write(src)

import py_compile
py_compile.compile(RG, doraise=True)
print("✅ compile OK reflection_gemini.py")

# 3) Test offline: le prompt contient-il la leçon ADX?
sys.path.insert(0, DOSSIER)
import importlib
import reflection_gemini
importlib.reload(reflection_gemini)
ctx = reflection_gemini.gather_contexte()
prompt = reflection_gemini._prompt(ctx)
print("\n=== TEST: section LECONS dans le prompt ===")
if "LECONS APPRISES" in prompt and "ADX" in prompt:
    # extrait la section lecons
    i = prompt.find("LECONS APPRISES")
    j = prompt.find("SAGESSE DES GRANDS")
    print(prompt[i:j].strip())
    print("\n✅ L'IA verra ses leçons (ADX présent) — ne re-proposera pas le filtre ADX")
else:
    print("❌ leçon ADX absente du prompt")
