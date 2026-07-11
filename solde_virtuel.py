#!/usr/bin/env python3
"""Affiche le solde reel du paper trading : capital, P&L, positions marquees au marche."""
import json
import urllib.request
import urllib.parse
from datetime import datetime, timezone, timedelta

try:
    d = json.load(open("paper_trading.json"))
except FileNotFoundError:
    print("paper_trading.json introuvable.")
    raise SystemExit

tz_paris = timezone(timedelta(hours=2))


def prix_yahoo(symbole):
    """Prix actuel via Yahoo Finance (meme methode que indicateur.py)."""
    enc = urllib.parse.quote(symbole, safe="")
    url = f"https://query1.finance.yahoo.com/v8/finance/chart/{enc}?interval=1m&range=1d"
    req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
    with urllib.request.urlopen(req, timeout=8) as r:
        data = json.load(r)
    return data["chart"]["result"][0]["meta"]["regularMarketPrice"]


capital_initial = float(d.get("capital_initial", 1000))
liquidites = float(d.get("liquidites", 0))
total_frais = float(d.get("total_frais", 0))
pic_capital = d.get("pic_capital")
positions = d.get("positions", [])
dernier_tick = d.get("dernier_tick")

print("=" * 56)
print("PAPER TRADING — Solde virtuel (marque au marche)")
print("=" * 56)

valeur_positions = 0.0
print(f"{'Symbole':<12}{'Entree':>10}{'Courant':>10}{'Var%':>9}{'Valeur':>10}")
print("-" * 56)
for p in positions:
    sym = p.get("symbole", "?")
    nom = p.get("nom", "")
    pe = float(p.get("prix_entree", 0))
    qte = float(p.get("quantite", 0))
    try:
        pc = prix_yahoo(sym)
    except Exception as e:
        print(f"{sym:<12}{pe:>10.4f}{'ERREUR':>10}{'?':>9}{'?':>10}  ({e})")
        continue
    var = (pc - pe) / pe * 100 if pe else 0
    val = qte * pc
    valeur_positions += val
    print(f"{sym:<12}{pe:>10.4f}{pc:>10.4f}{var:>+8.2f}%{val:>9.2f}€")

capital_actuel = liquidites + valeur_positions
perf = (capital_actuel - capital_initial) / capital_initial * 100
drawdown = 0
if pic_capital:
    drawdown = (capital_actuel - float(pic_capital)) / float(pic_capital) * 100

print("-" * 56)
print(f"Liquidites :        {liquidites:>10.2f} €")
print(f"Valeur positions :  {valeur_positions:>10.2f} €")
print(f"CAPITAL ACTUEL :    {capital_actuel:>10.2f} €")
print(f"Capital initial :   {capital_initial:>10.2f} €")
print(f"PERFORMANCE :       {perf:>+9.2f}%")
print(f"Frais cumules :     {total_frais:>10.2f} €")
if pic_capital:
    print(f"Pic capital :       {float(pic_capital):>10.2f} €  (drawdown {drawdown:+.2f}%)")
if dernier_tick:
    try:
        t = datetime.fromisoformat(str(dernier_tick)).astimezone(tz_paris)
        print(f"Dernier tick :      {t.strftime('%d/%m %H:%M:%S')} (Paris)")
    except Exception:
        print(f"Dernier tick :      {dernier_tick}")
print("=" * 56)
