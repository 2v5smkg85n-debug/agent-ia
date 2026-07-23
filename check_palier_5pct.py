#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""check_palier_5pct.py — notifie Telegram quand le portefeuille atteint +5% de PnL.

Lit paper_trading.json, calcule le PnL% réalisé (liquidites + valeur positions).
Si PnL >= 5% ET pas déjà notifié -> envoie un message Telegram + pose un flag.
Hystérésis: si PnL redescend sous 4.5%, le flag est levé (re-notification au prochain franchissement).

À lancer en cron toutes les 15 min (crontab ubuntu).
"""
import os, json, requests

BASE = os.path.dirname(os.path.abspath(__file__))
PF = os.path.join(BASE, "paper_trading.json")
ENV = os.path.join(BASE, ".env")
FLAG = os.path.join(BASE, ".palier5_flag")
SEUIL_HAUT = 5.0      # déclenche la notif
SEUIL_BAS = 4.5       # lève le flag (hystérésis)

def load_env():
    d = {}
    if os.path.exists(ENV):
        for line in open(ENV):
            line = line.strip()
            if "=" in line and not line.startswith("#"):
                k, v = line.split("=", 1)
                d[k.strip()] = v.strip().strip('"').strip("'")
    return d

def envoyer_telegram(token, chat_id, texte):
    try:
        r = requests.post(f"https://api.telegram.org/bot{token}/sendMessage",
                           data={"chat_id": chat_id, "text": texte, "parse_mode": "HTML"}, timeout=15)
        return r.status_code == 200
    except Exception as e:
        print(f"erreur telegram: {e}")
        return False

def main():
    env = load_env()
    token = env.get("TELEGRAM_BOT_TOKEN", "")
    chat_id = env.get("TELEGRAM_CHAT_ID", "")
    if not token or not chat_id:
        print("TELEGRAM_BOT_TOKEN/CHAT_ID manquants dans .env")
        return

    if not os.path.exists(PF):
        print("paper_trading.json introuvable")
        return
    pf = json.load(open(PF))

    cap = pf.get("capital_initial", 1000)
    liq = pf.get("liquidites", 0)
    pos = pf.get("positions", [])
    val = liq + sum(p.get("quantite", 0) * p.get("prix_actuel", p.get("prix_entree", 0)) for p in pos)
    pnl_pct = (val / cap - 1) * 100 if cap else 0
    pnl_eur = val - cap
    n_pos = len(pos)
    notifie = os.path.exists(FLAG)

    print(f"PnL: {pnl_pct:+.2f}% ({pnl_eur:+.2f}EUR) | {n_pos} positions | déjà notifié: {notifie}")

    # Hystérésis: sous le seuil bas -> on lève le flag pour re-notifier plus tard
    if pnl_pct < SEUIL_BAS and notifie:
        os.remove(FLAG)
        print(f"PnL < {SEUIL_BAS}% -> flag levé (re-notification possible au prochain franchissement)")
        notifie = False

    # Franchissement +5% pas encore notifié -> envoie
    if pnl_pct >= SEUIL_HAUT and not notifie:
        txt = (
            "🎯 <b>PALIER +5% ATTEINT</b>\n\n"
            f"Le portefeuille papier a dépassé <b>+5% de bénéfices</b>\n"
            f"📊 PnL: <b>{pnl_pct:+.2f}%</b> ({pnl_eur:+.2f}EUR)\n"
            f"💰 Capital: {cap:.0f}EUR -> {val:.2f}EUR\n"
            f"📈 {n_pos} position(s) ouverte(s)\n\n"
            "🚀 Le conviction sizing passe en bonus palier (+0.5).\n"
            "L'agent parie maintenant plus gros sur les stratégies prouvées."
        )
        if envoyer_telegram(token, chat_id, txt):
            open(FLAG, "w").write(f"{pnl_pct:.2f}")
            print("✓ Notification +5% envoyée + flag posé")
        else:
            print("✗ Échec envoi Telegram (réessayera au prochain cron)")

if __name__ == "__main__":
    main()
