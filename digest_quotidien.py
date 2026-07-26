#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""digest_quotidien.py — Bilan quotidien (matinal) envoyé sur Telegram. Version
condensée du digest_hebdo: portefeuille, pont Revolut + staking, actions
d'auto-amélioration des dernières 24h, apprentissages récents, dernière
réflexion IA. Message concis (~4000 caractères max) pour un café du matin.

Cron: tous les jours 06:00 UTC (08:00 CEST) — juste après les cycles de nuit
(pruning / meta-tuning / evolutia) → tu te réveilles avec le résumé du jour.

Chaque section est isolée en try/except: une indispo n'empêche pas le reste.
"""
import os
import json
from datetime import datetime, timedelta

try:
    from dotenv import load_dotenv
    load_dotenv(os.path.join(os.path.dirname(os.path.abspath(__file__)), ".env"))
except Exception:
    pass

DOSSIER = os.path.dirname(os.path.abspath(__file__))
TELEGRAM_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN", "")
TELEGRAM_CHAT = os.getenv("TELEGRAM_CHAT_ID", "")

FENETRE_24H = timedelta(hours=24)


def _charger(nom):
    """Charge un fichier JSON du dossier de l'agent. {} si absent/invalide."""
    try:
        with open(os.path.join(DOSSIER, nom)) as f:
            return json.load(f)
    except Exception:
        return {}


def _charger_jsonl(nom):
    """Charge un fichier JSONL en liste de dicts. [] si absent/invalide."""
    try:
        path = os.path.join(DOSSIER, nom)
        if not os.path.isfile(path):
            return []
        out = []
        with open(path, encoding="utf-8") as f:
            for l in f:
                l = l.strip()
                if not l:
                    continue
                try:
                    out.append(json.loads(l))
                except Exception:
                    continue
        return out
    except Exception:
        return []


def _parse_ts(val):
    """Parse un timestamp souple (plusieurs formats utilisés dans les logs)."""
    if not val:
        return None
    val = str(val)
    formats = ("%Y-%m-%dT%H:%M:%S.%f", "%Y-%m-%dT%H:%M:%S",
               "%Y-%m-%d %H:%M:%S", "%Y-%m-%d %H:%M", "%Y-%m-%d")
    for fmt in formats:
        try:
            return datetime.strptime(val[:len(fmt.replace("%f", "000000"))], fmt)
        except Exception:
            continue
    try:
        return datetime.fromisoformat(val.replace("Z", ""))
    except Exception:
        return None


def _depuis_24h(entree, cles=("ts", "date", "apply_time")):
    """True si l'entrée a un timestamp situé dans les dernières 24h."""
    maintenant = datetime.utcnow()
    for cle in cles:
        if cle in entree:
            dt = _parse_ts(entree.get(cle))
            if dt and (maintenant - dt) <= FENETRE_24H:
                return True
            if dt:
                return False  # timestamp trouve mais trop vieux
    return False  # pas de timestamp exploitable -> exclu par prudence


# ---------------------------------------------------------------- SECTION 1
def _sec_portefeuille():
    """Capital, P&L, trades du jour, win rate, positions ouvertes."""
    try:
        pf = _charger("paper_trading.json")
        if not pf:
            return "💼 Portefeuille: (indisponible)"
        liq = pf.get("liquidites", 0)
        pos = pf.get("positions", [])
        pos_list = pos if isinstance(pos, list) else list(pos.values())
        val_pos = sum(p.get("montant_eur", 0) for p in pos_list)
        val = liq + val_pos
        cap = pf.get("capital_initial", 1000)
        pnl = val - cap
        pct = pnl / cap * 100 if cap > 0 else 0
        fermes = pf.get("trades_fermes", [])
        # trades fermes dans les dernieres 24h (via date_fermeture)
        fermes_24h = [t for t in fermes if _depuis_24h(t, cles=("date_fermeture",))]
        gagnants_24h = sum(1 for t in fermes_24h if (t.get("gain_eur", 0) or 0) > 0)
        wr_24h = gagnants_24h / len(fermes_24h) * 100 if fermes_24h else 0
        pnl_24h = sum(t.get("gain_eur", 0) or 0 for t in fermes_24h)
        return (f"💼 Portefeuille: {val:.2f}€ (PnL total {pnl:+.2f}€ / {pct:+.1f}%)\n"
                f"📈 Aujourd'hui: {len(fermes_24h)} trade(s) fermé(s) ({pnl_24h:+.2f}€), "
                f"{wr_24h:.0f}% win | {len(pos_list)} position(s) ouverte(s)")
    except Exception:
        return "💼 Portefeuille: N/A"


# ---------------------------------------------------------------- SECTION 2
def _sec_revolut():
    """Etat du pont Revolut (miroir live) + staking (via monitor ou ledger)."""
    try:
        # --- Pont Revolut (miroir) ---
        mirror = _charger("revolut_mirror.json")
        actif = bool(mirror.get("live"))
        debut = mirror.get("debut_live", "non demarre")
        achats = mirror.get("achats", {})
        auj = datetime.utcnow().strftime("%Y-%m-%d")
        trades_jour = sum(1 for v in achats.values()
                           if str(v.get("date_miroir", "")).startswith(auj))
        n_positions = sum(1 for v in achats.values() if not v.get("vendu"))
        pont_txt = (f"Pont: {'actif' if actif else 'inactif'} (depuis {debut}) | "
                    f"{n_positions} position(s) miroirée(s) | {trades_jour} trade miroiré aujourd'hui")

        # --- Staking (tentative live via staking_revolut_monitor, sinon ledger) ---
        staking_txt = None
        try:
            from staking_revolut_monitor import lire_staking, _client, _ticker_map, _val_eur
            client = _client()
            if client:
                staking, eur_libre = lire_staking(client)
                if staking:
                    pmap = _ticker_map(client)
                    lignes = []
                    for cur, d in staking.items():
                        val = _val_eur(client, cur, d["staked"], pmap)
                        lignes.append(f"{d['staked']:.4f} {cur} staké (~{val:.2f}€)")
                    staking_txt = f"{eur_libre:.2f}€ EUR libre | " + " | ".join(lignes)
                else:
                    staking_txt = f"{eur_libre:.2f}€ EUR libre | aucun actif staké"
        except Exception:
            staking_txt = None

        if staking_txt is None:
            # Repli: dernier snapshot du ledger JSONL
            snaps = _charger_jsonl("staking_revolut_ledger.jsonl")
            if snaps:
                dernier = snaps[-1]
                eur_libre = dernier.get("eur_libre", 0)
                staking = dernier.get("staking", {})
                if staking:
                    lignes = [f"{d.get('staked', 0):.4f} {cur} staké"
                              for cur, d in staking.items()]
                    staking_txt = f"{eur_libre:.2f}€ EUR libre | " + " | ".join(lignes)
                else:
                    staking_txt = f"{eur_libre:.2f}€ EUR libre | aucun actif staké"
            else:
                staking_txt = "(staking indisponible)"

        return f"🏦 Revolut: {staking_txt}\n   {pont_txt}"
    except Exception:
        return "🏦 Revolut: N/A"


# ---------------------------------------------------------------- SECTION 3
def _sec_actions():
    """Actions d'auto-amelioration des dernieres 24h: pruning, tuning, revert."""
    try:
        pruning = _charger_jsonl("pruning_log.jsonl")
        tuning = _charger_jsonl("meta_tuning_log.jsonl")
        evolutia = _charger_jsonl("evolutia_ledger.jsonl")

        pruning_24h = [e for e in pruning if _depuis_24h(e)]
        tuning_24h = [e for e in tuning if _depuis_24h(e)]
        # revert = entrees evolutia dont le statut/verdict indique un rollback
        revert_24h = [e for e in evolutia if _depuis_24h(e, cles=("eval_time", "apply_time"))
                      and str(e.get("statut", "")).upper() == "REVERT"]

        return (f"⚙️ Actions 24h: {len(pruning_24h)} pruning, "
                f"{len(tuning_24h)} tuning, {len(revert_24h)} revert")
    except Exception:
        return "⚙️ Actions 24h: N/A"


# ---------------------------------------------------------------- SECTION 4
def _sec_apprentissages():
    """Nouvelles lecons + strategies generees/testees dans les dernieres 24h."""
    try:
        lecons = _charger_jsonl("lecons_apprises.jsonl")
        lecons_24h = [l for l in lecons if _depuis_24h(l)]
        lignes = [f"📚 Apprentissages 24h: {len(lecons_24h)} nouvelle(s) leçon(s)"]
        for l in lecons_24h[-2:]:
            src = l.get("source", "?")
            texte = l.get("decision") or l.get("hypothese") or l.get("type") or "?"
            lignes.append(f"   • {src}: {str(texte)[:90]}")

        strategies = _charger_jsonl("strategies_generated.jsonl")
        strategies_24h = [s for s in strategies if _depuis_24h(s)]
        if strategies_24h:
            gagnantes = sum(1 for s in strategies_24h
                             if str(s.get("verdict", "")).upper() not in ("REJETEE", "REJETÉE"))
            lignes.append(f"🧪 Stratégies testées 24h: {len(strategies_24h)} "
                           f"({gagnantes} retenue(s))")
        else:
            lignes.append("🧪 Stratégies testées 24h: 0")
        return "\n".join(lignes)
    except Exception:
        return "📚 Apprentissages: N/A"


# ---------------------------------------------------------------- SECTION 5
def _sec_reflexion():
    """Derniere synthese de reflexion IA + derniers regimes de marche detectes."""
    try:
        lignes = []
        reflections = _charger_jsonl("reflection_log.jsonl")
        if reflections:
            derniere = reflections[-1]
            synthese = (derniere.get("analyse", {}) or {}).get("synthese", "")
            if synthese:
                lignes.append(f"🤔 Réflexion: {synthese[:220]}")
            else:
                lignes.append("🤔 Réflexion: (synthèse indisponible)")
        else:
            lignes.append("🤔 Réflexion: N/A")

        recherches = _charger_jsonl("recherche_log.jsonl")
        if recherches:
            derniere = recherches[-1]
            regimes = derniere.get("regimes", {})
            if regimes:
                resume = ", ".join(f"{a}:{r}" for a, r in list(regimes.items())[:5])
                lignes.append(f"🔎 Régimes marché: {resume}")
        return "\n".join(lignes)
    except Exception:
        return "🤔 Réflexion: N/A"


def composer():
    """Assemble le message complet, section par section (isolees try/except)."""
    titre = f"☀️ DIGEST QUOTIDIEN — {datetime.utcnow().strftime('%d/%m/%Y')}"
    sections = [titre]
    for fn in [_sec_portefeuille, _sec_revolut, _sec_actions,
               _sec_apprentissages, _sec_reflexion]:
        try:
            sections.append(fn())
        except Exception as _e:
            sections.append(f"(section erreur: {_e})")
    horodatage = datetime.utcnow().strftime("%d/%m/%Y %H:%M UTC")
    sections.append(f"🕐 Généré le {horodatage}")
    msg = "\n\n".join(sections)
    # Garde-fou: Telegram limite les messages a 4096 caracteres.
    if len(msg) > 4000:
        msg = msg[:3990] + "\n…(tronqué)"
    return msg


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
