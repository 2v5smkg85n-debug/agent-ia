#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""live_lessons.py — BOUCLE D'AUTO-APPRENTISSAGE LIVE -> GENERATION.

AVANT: l'evolver enregistrait des lecons (lecons_apprises.jsonl) mais ne les
relisait JAMAIS. La performance live (quelles stratégies gagnent/perdent en
réel) ne nourrissait pas la génération. L'IA n'apprenait pas de ses trades.

MAINTENANT: live_lessons_prompt() extrait les leçons de:
  1. trades_fermes (paper_trading.json) -> PnL réel par stratégie, win rate, stop-loss
  2. classement_strategies.json -> live_mult bayésien (qui sous/sur-performe en live)
  3. lecons_apprises.jsonl -> leçons enregistrées (étaient mortes avant)
et les formate pour injection dans le prompt de génération de l'evolver.

Chaque génération apprend désormais des résultats live réels. C'est la boucle
d'auto-amélioration qui manquait: live perf -> leçons -> génération plus intelligente.
"""
import os
import json

DOSSIER = os.path.dirname(os.path.abspath(__file__))


def _lire_trades_fermes():
    try:
        pf = json.load(open(os.path.join(DOSSIER, "paper_trading.json"), encoding="utf-8"))
        return pf.get("trades_fermes", [])
    except Exception:
        return []


def _lire_classement():
    try:
        return json.load(open(os.path.join(DOSSIER, "classement_strategies.json"), encoding="utf-8"))
    except Exception:
        return {}


def _lire_lecons():
    """Lit lecons_apprises.jsonl (10 plus recentes). Étaient écrites mais jamais lues."""
    out = []
    try:
        with open(os.path.join(DOSSIER, "lecons_apprises.jsonl"), encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                try:
                    l = json.loads(line)
                    txt = l.get("texte") or l.get("lesson") or l.get("lecon") or ""
                    if txt:
                        out.append(txt)
                except Exception:
                    pass
    except Exception:
        pass
    return out[-10:]


def live_lessons_prompt():
    """Retourne un bloc de texte injecté dans le prompt de génération.
    Vide si pas assez de données live (graceful degradation)."""
    lessons = []

    # 1. PERF LIVE PAR STRATÉGIE (depuis trades_fermes = résultats réels)
    tf = _lire_trades_fermes()
    if len(tf) >= 5:
        by_strat = {}
        for t in tf:
            st = t.get("strategie") or t.get("source") or ""
            if not st:
                continue
            try:
                var = float(t.get("variation_pct", 0) or 0)
            except Exception:
                var = 0.0
            raison = t.get("raison", "") or ""
            d = by_strat.setdefault(st, {"vars": [], "raisons": []})
            d["vars"].append(var)
            d["raisons"].append(raison)
        # synthétise les stratégies avec assez de trades (>=3)
        for st, d in sorted(by_strat.items()):
            if len(d["vars"]) < 3:
                continue
            avg = sum(d["vars"]) / len(d["vars"])
            win = sum(1 for v in d["vars"] if v > 0) / len(d["vars"])
            sl = sum(1 for r in d["raisons"] if "stop" in r.lower())
            if avg < -1.0:
                lessons.append(
                    f"PERTE LIVE: '{st}' a perdu {avg:+.1f}% en moyenne sur "
                    f"{len(d['vars'])} trades (win {win*100:.0f}%, {sl} stop-loss). "
                    f"Ce pattern échoue en conditions réelles — ÉVITE les variantes similaires."
                )
            elif avg > 1.0:
                lessons.append(
                    f"GAIN LIVE: '{st}' a gagné {avg:+.1f}% en moyenne sur "
                    f"{len(d['vars'])} trades (win {win*100:.0f}%). "
                    f"Edge confirmé en réel — inspire-t'en."
                )

    # 2. LIVE_MULT BAYÉSIEN (depuis classement_strategies.json)
    cl = _lire_classement()
    if cl:
        perdantes, gagnantes = set(), set()
        for actif, info in cl.items():
            for s in info.get("strategies", []):
                lm = s.get("live_mult", 1.0)
                nom = s.get("strategie", "")
                if not nom:
                    continue
                if lm < 0.85:
                    perdantes.add(nom)
                elif lm > 1.15:
                    gagnantes.add(nom)
        if perdantes:
            lessons.append(
                f"SOUS-PERF LIVE (classement bayésien): {sorted(perdantes)} — "
                f"live_mult<0.85, le backtest surévaluait ces stratégies. Ne les repropose pas."
            )
        if gagnantes:
            lessons.append(
                f"SUR-PERF LIVE (classement bayésien): {sorted(gagnantes)} — "
                f"live_mult>1.15, edge réel supérieur au backtest."
            )

    # 3. LEÇONS ENREGISTRÉES (lecons_apprises.jsonl — mortes avant ce module)
    for l in _lire_lecons():
        lessons.append(f"LECON ENREGISTRÉE: {l}")

    if not lessons:
        return ""
    lessons = lessons[:8]  # limite pour éviter le bloat du prompt
    return (
        "\n\n## LECONS DE PERFORMANCE LIVE (auto-apprentissage)\n"
        "Le système a tradé en réel. Voici ce qui marche et ce qui échoue EN LIVE. "
        "Intègre ces leçons: évite les patterns qui perdent, inspire-toi de ceux qui gagnent.\n"
        + "\n".join(f"- {l}" for l in lessons)
    )


if __name__ == "__main__":
    print("=" * 60)
    print("BOUCLE D'AUTO-APPRENTISSAGE LIVE -> GENERATION")
    print("=" * 60)
    txt = live_lessons_prompt()
    print(txt if txt else "(aucune leçon live disponible — pas encore assez de trades)")
