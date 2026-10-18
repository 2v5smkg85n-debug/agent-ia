#!/usr/bin/env python3
"""
etat_sqlite.py — copie durable et interrogeable de tout l'apprentissage dans une base SQLite (stdlib, zero dependance).

Les fichiers JSON restent la source vivante du bot (rien ne change pour lui). Cette base :
  - garde une copie de CHAQUE trade (archive + courant), decision du cerveau, entree du journal d'erreurs,
    fiche du registre et decision de la porte, sans doublon (cle unique) et sans jamais rien effacer ;
  - survit a un "nouveau depart" du paper trading (le JSON courant est vide, la base garde tout) ;
  - permet des requetes en une ligne : sqlite3 agent_ia.sqlite "select strategie, count(*), round(sum(gain_eur),2) from trades group by 1"

Usage : python3 etat_sqlite.py migrer     (idempotent : relancable a volonte, ne fait qu'ajouter)
        python3 etat_sqlite.py stats
Hook : etat_sqlite.sync_trade(trade) est appele par paper_trading.fermer_position (jamais bloquant).
Cron conseille : 17 * * * *  cd /home/ubuntu/agent-ia && venv/bin/python etat_sqlite.py migrer >> etat_sqlite.log 2>&1
"""
import json
import os
import sqlite3
import sys
from datetime import datetime

DOSSIER = os.path.dirname(os.path.abspath(__file__))
BASE = os.path.join(DOSSIER, "agent_ia.sqlite")

SCHEMA = """
create table if not exists trades (
  cle text primary key, symbole text, strategie text, source text, marche text, date_ouverture text, date_fermeture text,
  prix_entree real, prix_sortie real, montant_eur real, gain_eur real, variation_pct real, raison text, sl_risque real, tp_risque real,
  contexte text, origine text, insere_le text);
create table if not exists decisions_cerveau (
  cle text primary key, date text, action text, sym text, confiance real, etape text, raison text, modele text, modele_critique text, brut text);
create table if not exists journal_erreurs (
  cle text primary key, date_fermeture text, sym text, gain real, raison text, classes text, post_mortem text, contexte text);
create table if not exists registre (
  date text, strategie text, statut text, n integer, g integer, net real, wr real, wr_bayes real, ic_bas real, ic_haut real, point_mort real, dsr real,
  primary key (date, strategie));
create table if not exists porte (
  cle text primary key, date text, sym text, strategie text, ok integer, raison text, infos text);
create table if not exists migrations (fichier text, date text, lignes integer);
"""


def _co():
    co = sqlite3.connect(BASE, timeout=10)
    co.executescript(SCHEMA)
    return co


def _j(x):
    return json.dumps(x, ensure_ascii=False, default=str) if x is not None else None


def _cle_trade(t):
    return f"{t.get('symbole')}|{t.get('date_ouverture')}|{t.get('date_fermeture')}|{round(float(t.get('montant_eur') or 0), 2)}"


def sync_trade(t, origine="live", co=None):
    """Insere un trade ferme (dict du bot). Idempotent."""
    propre = co is None
    co = co or _co()
    try:
        co.execute("insert or ignore into trades values (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
                   (_cle_trade(t), t.get("symbole"), t.get("strategie"), t.get("source"), t.get("marche"), t.get("date_ouverture"), t.get("date_fermeture"),
                    t.get("prix_entree"), t.get("prix_sortie"), t.get("montant_eur"), t.get("gain_eur"), t.get("variation_pct"), t.get("raison"),
                    t.get("sl_risque"), t.get("tp_risque"), _j(t.get("contexte")), origine, datetime.now().strftime("%Y-%m-%d %H:%M:%S")))
        if propre:
            co.commit()
    finally:
        if propre:
            co.close()


def migrer(verbose=True):
    co = _co()
    n = {}
    # trades : archive + courant
    try:
        import registre_strategies as rs
        trades = rs.tous_les_trades()
    except Exception:
        trades = []
    for t in trades:
        sync_trade(t, "migration", co)
    n["trades"] = len(trades)
    # decisions du cerveau
    try:
        d = json.load(open(os.path.join(DOSSIER, "journal_decisions.json")))
        for r in d.get("decisions", []):
            co.execute("insert or ignore into decisions_cerveau values (?,?,?,?,?,?,?,?,?,?)",
                       (f"{r.get('date')}|{r.get('sym')}|{r.get('etape')}", r.get("date"), r.get("action"), r.get("sym"), r.get("confiance"), r.get("etape"),
                        r.get("raison"), r.get("modele"), r.get("modele_critique"), _j(r)))
        n["decisions_cerveau"] = len(d.get("decisions", []))
    except Exception:
        pass
    # journal des erreurs
    try:
        d = json.load(open(os.path.join(DOSSIER, "journal_erreurs.json")))
        for r in d.get("trades", []):
            co.execute("insert or ignore into journal_erreurs values (?,?,?,?,?,?,?,?)",
                       (f"{r.get('sym')}|{r.get('date_fermeture')}|{r.get('gain')}", r.get("date_fermeture"), r.get("sym"), r.get("gain"), r.get("raison"),
                        _j(r.get("classes")), r.get("post_mortem"), _j(r.get("contexte"))))
        n["journal_erreurs"] = len(d.get("trades", []))
    except Exception:
        pass
    # registre (photo du jour)
    try:
        d = json.load(open(os.path.join(DOSSIER, "registre_strategies.json")))
        jour = datetime.now().strftime("%Y-%m-%d")
        for k, s in d.get("strategies", {}).items():
            co.execute("insert or replace into registre values (?,?,?,?,?,?,?,?,?,?,?,?)",
                       (jour, k, s.get("statut"), s.get("n"), s.get("g"), s.get("net"), s.get("wr"), s.get("wr_bayes"), s.get("wr_ic_bas"), s.get("wr_ic_haut"),
                        s.get("point_mort"), s.get("dsr")))
        n["registre"] = len(d.get("strategies", {}))
    except Exception:
        pass
    # porte d'entree
    try:
        c = 0
        for l in open(os.path.join(DOSSIER, "porte_entree_log.jsonl")):
            if not l.strip():
                continue
            r = json.loads(l)
            inf = r.get("infos") or {}
            co.execute("insert or ignore into porte values (?,?,?,?,?,?,?)",
                       (f"{inf.get('date')}|{inf.get('sym')}|{r.get('raison')}"[:200], inf.get("date"), inf.get("sym"), inf.get("strategie"), 1 if r.get("ok") else 0,
                        r.get("raison"), _j(inf)))
            c += 1
        n["porte"] = c
    except Exception:
        pass
    co.execute("insert into migrations values (?,?,?)", ("tous", datetime.now().strftime("%Y-%m-%d %H:%M:%S"), sum(n.values())))
    co.commit()
    tot = co.execute("select count(*) from trades").fetchone()[0]
    co.close()
    if verbose:
        print(f"Migration OK -> {BASE} : sources {n} ; {tot} trades au total dans la base")
    return n


def stats():
    co = _co()
    lignes = [f"Base {BASE}"]
    for table in ("trades", "decisions_cerveau", "journal_erreurs", "registre", "porte"):
        lignes.append(f"  {table}: {co.execute(f'select count(*) from {table}').fetchone()[0]} lignes")
    lignes.append("  P&L par strategie (base complete):")
    for row in co.execute("select coalesce(strategie, source, '?'), count(*), round(sum(gain_eur),2), round(100.0*sum(gain_eur>0)/count(*)) from trades group by 1 order by 3 desc limit 12"):
        lignes.append(f"    {row[0]:28s} {row[1]:4d} trades  {row[2]:+8.2f} EUR  WR {row[3]:.0f}%")
    co.close()
    return "\n".join(lignes)


if __name__ == "__main__":
    cmd = sys.argv[1] if len(sys.argv) > 1 else "stats"
    if cmd == "migrer":
        migrer()
    print(stats())
