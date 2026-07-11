#!/usr/bin/env python3
"""Rapport de progression de l'agent IA — vue d'ensemble en un coup d'oeil."""
import json
import os
import subprocess
import glob
import urllib.request
import urllib.parse
from datetime import datetime, timezone, timedelta

tz = timezone(timedelta(hours=2))


def section(t):
    print("\n" + "=" * 56)
    print(f" {t}")
    print("=" * 56)


# ---------- 1. PROCESSUS ----------
section("1. PROCESSUS")
progs = {"paper_trading": False, "protection.py": False}
try:
    out = subprocess.run(
        ["pgrep", "-af", "python"], capture_output=True, text=True, timeout=5
    ).stdout
    print(out.strip() if out.strip() else "  Aucun process python detecte.")
    progs["paper_trading"] = "paper_trading" in out
    progs["protection.py"] = "protection.py" in out
except Exception as e:
    print(f"  pgrep indisponible: {e}")

for nom, ok in progs.items():
    print(f"  {nom}: {'ACTIF' if ok else 'ARRETE'} {'✓' if ok else '✗'}")

# ---------- 2. PAPER TRADING ----------
section("2. PAPER TRADING (virtuel)")
try:
    d = json.load(open("paper_trading.json"))
except FileNotFoundError:
    print("  paper_trading.json introuvable.")
    d = None

if d:
    capital_initial = float(d.get("capital_initial", 1000))
    liquidites = float(d.get("liquidites", 0))
    total_frais = float(d.get("total_frais", 0))
    pic = d.get("pic_capital")
    positions = d.get("positions", [])
    trades_fermes = d.get("trades_fermes", [])
    dernier_tick = d.get("dernier_tick")

    def prix_yahoo(sym):
        enc = urllib.parse.quote(sym, safe="")
        url = f"https://query1.finance.yahoo.com/v8/finance/chart/{enc}?interval=1m&range=1d"
        req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
        with urllib.request.urlopen(req, timeout=8) as r:
            return json.load(r)["chart"]["result"][0]["meta"]["regularMarketPrice"]

    val = 0.0
    for p in positions:
        sym = p.get("symbole", "?")
        pe = float(p.get("prix_entree", 0))
        qte = float(p.get("quantite", 0))
        try:
            pc = prix_yahoo(sym)
            var = (pc - pe) / pe * 100 if pe else 0
            val += qte * pc
            print(f"  {sym:<11} entree {pe:>9.4f} -> {pc:>9.4f} ({var:+.2f}%)")
        except Exception as e:
            print(f"  {sym:<11} prix indisponible ({e})")

    capital = liquidites + val
    perf = (capital - capital_initial) / capital_initial * 100
    print(f"  Liquidites:      {liquidites:>9.2f} EUR")
    print(f"  Valeur pos.:     {val:>9.2f} EUR")
    print(f"  CAPITAL ACTUEL:  {capital:>9.2f} EUR  ({perf:+.2f}%)")
    print(f"  Pic capital:     {float(pic):>9.2f} EUR" if pic else "  Pic capital: n/a")
    print(f"  Frais cumules:   {total_frais:>9.2f} EUR")
    print(f"  Positions:       {len(positions)} ouvertes | {len(trades_fermes)} fermees")
    if dernier_tick:
        try:
            t = datetime.fromisoformat(str(dernier_tick)).astimezone(tz)
            age = datetime.now(tz) - t
            print(f"  Dernier tick:    {t.strftime('%d/%m %H:%M:%S')} (il y a {int(age.total_seconds()//60)} min)")
        except Exception:
            print(f"  Dernier tick:    {dernier_tick}")

# ---------- 3. PROTECTION BTC (reel) ----------
section("3. TRADING REEL — Protection BTC")
logpath = "protection.log"
if os.path.exists(logpath):
    try:
        with open(logpath, "r", errors="replace") as f:
            lignes = f.readlines()
        contenu = "".join(lignes)
        vendu = any(m in contenu for m in ["STOP SUIVEUR declenche", "TAKE-PROFIT dur", "vendu"])
        print(f"  Position fermee automatiquement: {'OUI' if vendu else 'NON — toujours ouverte'}")
        # Dernieres lignes utiles
        infos = [l for l in lignes if "BTC" in l and "stop" in l.lower()][-3:]
        for l in infos:
            print(f"  {l.strip()[:80]}")
        print(f"  (log: {len(lignes)} lignes)")
    except Exception as e:
        print(f"  Lecture log impossible: {e}")
else:
    print("  protection.log introuvable.")

# Solde reel via Revolut X
try:
    from revolut_x import RevolutX, RevolutXError
    c = RevolutX()
    balances = c.get_balances()
    if isinstance(balances, list):
        for b in balances:
            cur = b.get("currency")
            if cur in ("BTC", "EUR", "USD"):
                try:
                    if float(b.get("total", 0)) > 0:
                        print(f"  Revolut {cur}: {b.get('total')} (dispo {b.get('available')})")
                except (ValueError, TypeError):
                    pass
except Exception as e:
    print(f"  Solde Revolut indisponible: {e}")

# ---------- 4. SAUVEGARDE ----------
section("4. SAUVEGARDE")
backups = sorted(glob.glob(os.path.expanduser("~/backups/agent-ia-*.tar.gz")))
if backups:
    dernier = backups[-1]
    mtime = datetime.fromtimestamp(os.path.getmtime(dernier)).astimezone(tz)
    size = os.path.getsize(dernier) / 1024
    age_h = (datetime.now(tz) - mtime).total_seconds() / 3600
    print(f"  Derniere sauvegarde: {os.path.basename(dernier)}")
    print(f"  Date: {mtime.strftime('%d/%m %H:%M')} (il y a {age_h:.1f}h)")
    print(f"  Taille: {size:.0f} Ko | Total: {len(backups)} sauvegardes")
else:
    print("  Aucune sauvegarde trouvee.")

print("\n" + "=" * 56)
print(" Fin du rapport")
print("=" * 56)
