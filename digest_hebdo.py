#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""digest_hebdo.py — Bilan hebdomadaire envoyé sur Telegram. Synthétise TOUTES
les couches du système en un message: portefeuille, stratégies, sentiment,
protection capital, plugins actifs, leçons live. Ferme la boucle d'autonomie:
l'agent agit + apprend + s'améliore + RAPPORTE.

Cron: dimanche 06:00 UTC (08:00 CEST), juste après le méta-evolver (05:00 UTC)
→ tu te réveilles avec le nouveau plugin + le bilan complet.

Chaque section est isolée en try/except: une indispo n'empêche pas le reste."""
import os
import json
from datetime import datetime

try:
    from dotenv import load_dotenv
    load_dotenv(os.path.join(os.path.dirname(os.path.abspath(__file__)), ".env"))
except Exception:
    pass

DOSSIER = os.path.dirname(os.path.abspath(__file__))
TELEGRAM_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN", "")
TELEGRAM_CHAT = os.getenv("TELEGRAM_CHAT_ID", "")


def _charger(nom):
    try:
        with open(os.path.join(DOSSIER, nom)) as f:
            return json.load(f)
    except Exception:
        return {}


def _sec_portefeuille():
    pf = _charger("paper_trading.json")
    liq = pf.get("liquidites", 0)
    pos = pf.get("positions", [])
    val_pos = sum(p.get("montant_eur", 0) for p in (pos if isinstance(pos, list) else pos.values()))
    val = liq + val_pos
    cap = pf.get("capital_initial", 1000)
    pnl = val - cap
    pct = pnl / cap * 100 if cap > 0 else 0
    fermes = pf.get("trades_fermes", [])
    gagnants = sum(1 for t in fermes if (t.get("gain_eur", 0) or 0) > 0)
    wr = gagnants / len(fermes) * 100 if fermes else 0
    return (f"💼 Portefeuille: {val:.2f}€ (PnL {pnl:+.2f}€ / {pct:+.1f}%)\n"
            f"📈 Trades: {len(fermes)} fermés ({gagnants} gagnants, {wr:.0f}% win) | "
            f"{len(pos) if isinstance(pos,list) else len(pos)} ouvertes")


def _sec_strategies():
    cs = _charger("classement_strategies.json")
    if not cs or not isinstance(cs, dict):
        return "🏆 Stratégies: (indisponible)"
    toutes = []
    for actif, bloc in cs.items():
        if not isinstance(bloc, dict):
            continue
        for s in bloc.get("strategies", []):
            if isinstance(s, dict):
                s2 = dict(s)
                s2["_actif"] = actif
                s2["_regime"] = bloc.get("regime", "?")
                toutes.append(s2)
    if not toutes:
        return "🏆 Stratégies: 0"
    top = sorted(toutes, key=lambda e: e.get("live_n", 0) or 0, reverse=True)[:3]
    lignes = [f"🏆 Stratégies: {len(toutes)} stratégies sur {len(cs)} actifs"]
    for e in top:
        nom = e.get("strategie", "?")
        actif = e.get("_actif", "?")
        n = e.get("live_n", 0)
        wr = e.get("live_wr", 0) or 0
        pnl = e.get("live_pnl", 0) or 0
        lignes.append(f"   • {nom} ({actif}): {n} trades, {wr:.0f}% win, {pnl:+.2f}€")
    return "\n".join(lignes)


def _sec_sentiment():
    try:
        from sentiment_marche import fetch_fear_greed, _stats_sentiment
        data = fetch_fear_greed(30)
        s = _stats_sentiment(data)
        if not s:
            return "🧠 Sentiment: (indisponible)"
        actuel, classe, moy7, trend, extremes = s
        fleche = "↑ moins peur" if trend > 3 else ("↓ plus peur" if trend < -3 else "→ stable")
        return (f"🧠 Sentiment: {actuel}/100 ({classe}) | moy7j {moy7:.0f} {fleche} | "
                f"{extremes}/30j Extreme Fear")
    except Exception:
        return "🧠 Sentiment: (indisponible)"


def _sec_protection():
    try:
        from protection_capital import etat_display
        return f"🛡️ {etat_display()}"
    except Exception:
        return "🛡️ Protection: (indisponible)"


def _sec_plugins():
    pdir = os.path.join(DOSSIER, "plugins")
    if not os.path.isdir(pdir):
        return "🧬 Plugins: 0 actif"
    plugs = sorted(f for f in os.listdir(pdir) if f.endswith(".py") and not f.startswith("_"))
    if not plugs:
        return "🧬 Plugins: 0 actif"
    lignes = [f"🧬 Plugins: {len(plugs)} actif(s)"]
    for f in plugs[:5]:
        lignes.append(f"   • {f}")
    return "\n".join(lignes)


def _sec_lecons():
    """Affiche l'activité récente (lecons_apprises.jsonl = log d'évolution)."""
    try:
        path = os.path.join(DOSSIER, "lecons_apprises.jsonl")
        if not os.path.isfile(path):
            return "📚 Activité: (fichier absent)"
        with open(path) as f:
            lignes = [l.strip() for l in f if l.strip()]
        if not lignes:
            return "📚 Activité: (vide)"
        out = ["📚 Activité récente:"]
        for l in lignes[-3:]:
            try:
                d = json.loads(l)
                date = d.get("date", "?")
                src = d.get("source", "?")
                typ = d.get("type", "?")
                out.append(f"   • {date} | {src} | {typ}")
            except Exception:
                out.append(f"   • {l[:90]}")
        return "\n".join(out)
    except Exception:
        return "📚 Activité: (indisponible)"


def composer():
    titre = f"📊 BILAN HEBDOMADAIRE — {datetime.utcnow().strftime('%d/%m/%Y')}"
    sections = [titre]
    for fn in [_sec_portefeuille, _sec_strategies, _sec_sentiment,
               _sec_protection, _sec_plugins, _sec_lecons]:
        try:
            sections.append(fn())
        except Exception as _e:
            sections.append(f"(section erreur: {_e})")
    sections.append("⚙️ L'agent évolue seul. Bonne semaine.")
    return "\n\n".join(sections)


def envoyer():
    msg = composer()
    print(msg)
    print("\n---")
    if not TELEGRAM_TOKEN or not TELEGRAM_CHAT:
        print("(Telegram non configuré — digest affiché seulement)")
        return
    try:
        import requests
        r = requests.post(f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage",
                          json={"chat_id": TELEGRAM_CHAT, "text": msg, "parse_mode": "Markdown"},
                          timeout=15)
        print("✅ Digest envoyé sur Telegram" if r.ok else f"❌ Erreur Telegram: {r.status_code}")
    except Exception as e:
        print(f"❌ Erreur envoi: {e}")


if __name__ == "__main__":
    envoyer()
