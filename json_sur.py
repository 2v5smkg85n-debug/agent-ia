#!/usr/bin/env python3
"""json_sur.py — ecriture atomique et lecture tolerante des fichiers JSON vitaux (paper_trading.json en tete).

Pourquoi (31/10/2026, 19:56 UTC) : paper_trading.json a ete tronque en pleine ecriture (open(..., "w") vide le fichier
PUIS ecrit ; si le processus est coupe entre les deux, ou si deux processus ecrivent en meme temps, le fichier est
mutile). Le bot ne pouvait plus charger son portefeuille (« Portefeuille non initialise ») : plus aucune ouverture ni
surveillance des stops pendant des heures, et le watchdog restaurait un .bak qui etait la copie du fichier deja casse.

Regles :
  - ecrire(chemin, obj)  : ecrit dans chemin.tmp, fsync, puis os.replace -> le fichier est toujours complet ou absent.
  - lire(chemin)         : json.load ; si echec, tente la reparation (texte tronque, donnees en trop), garde une copie
                           du fichier casse (chemin.corrompu.<horodatage>), reecrit la version reparee, et renvoie l'objet.
  - reparer_texte(txt)   : « Extra data » -> premier objet complet ; troncature -> recule jusqu'au dernier element complet
                           et referme les crochets/accolades ouverts.
"""
import json
import os
import re
import shutil
import tempfile
import time


def ecrire(chemin, obj, indent=2, ensure_ascii=False):
    """Ecriture atomique : le lecteur voit soit l'ancien fichier complet, soit le nouveau, jamais un fichier a moitie ecrit."""
    dossier = os.path.dirname(os.path.abspath(chemin)) or "."
    fd, tmp = tempfile.mkstemp(prefix=os.path.basename(chemin) + ".", suffix=".tmp", dir=dossier)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            json.dump(obj, f, indent=indent, ensure_ascii=ensure_ascii)
            f.flush()
            os.fsync(f.fileno())
        os.replace(tmp, chemin)
    except Exception:
        try:
            os.unlink(tmp)
        except Exception:
            pass
        raise


def _fermetures_manquantes(txt):
    """Pile des ouvrants non fermes (hors chaines) -> chaine de fermeture."""
    pile = []
    dans_chaine = False
    echap = False
    for c in txt:
        if dans_chaine:
            if echap:
                echap = False
            elif c == "\\":
                echap = True
            elif c == '"':
                dans_chaine = False
            continue
        if c == '"':
            dans_chaine = True
        elif c in "{[":
            pile.append(c)
        elif c in "}]":
            if pile:
                pile.pop()
    if dans_chaine:
        return None  # coupe au milieu d'une chaine : ce point de coupe n'est pas utilisable
    return "".join("}" if o == "{" else "]" for o in reversed(pile))


def reparer_texte(txt, max_essais=4000):
    """Renvoie (objet, methode) ou (None, raison)."""
    txt = txt or ""
    if not txt.strip():
        return None, "vide"
    # 1) Cas simple : JSON valide
    try:
        return json.loads(txt), "intact"
    except Exception:
        pass
    # 2) Donnees en trop apres un objet complet (deux ecritures superposees, la seconde plus courte)
    try:
        obj, fin = json.JSONDecoder().raw_decode(txt.lstrip())
        return obj, "extra_data"
    except Exception:
        pass
    # 3) Troncature : on recule jusqu'a un point ou un element vient d'etre termine ('}' ou ']'), on retire la
    #    virgule / la cle orpheline eventuelle, puis on referme ce qui est ouvert.
    essais = 0
    for m in reversed(list(re.finditer(r"[}\]]", txt))):
        essais += 1
        if essais > max_essais:
            break
        prefixe = txt[: m.end()]
        fermetures = _fermetures_manquantes(prefixe)
        if fermetures is None:
            continue
        candidat = prefixe.rstrip().rstrip(",") + fermetures
        try:
            return json.loads(candidat), f"tronque_repare(coupe_a={m.end()})"
        except Exception:
            continue
    return None, "irreparable"


def lire(chemin, reparer=True, journal=print):
    """Charge un JSON ; en cas de corruption, repare, archive le fichier casse et reecrit proprement."""
    with open(chemin, "r", encoding="utf-8") as f:
        txt = f.read()
    try:
        return json.loads(txt)
    except Exception as e:
        if not reparer:
            raise
        obj, methode = reparer_texte(txt)
        if obj is None:
            raise ValueError(f"{chemin}: JSON irreparable ({e})")
        horodatage = time.strftime("%Y%m%d-%H%M%S")
        copie = f"{chemin}.corrompu.{horodatage}"
        try:
            shutil.copy2(chemin, copie)
        except Exception:
            copie = "(copie impossible)"
        try:
            ecrire(chemin, obj)
        except Exception:
            pass
        if journal:
            journal(f"  [JSON-SUR] {os.path.basename(chemin)} corrompu ({e}) -> repare ({methode}), original garde : {copie}")
        return obj


def completer_trades_depuis_sqlite(pf, journal=print):
    """Apres une reparation, remet dans pf['trades_fermes'] les trades que la base SQLite connait et que le JSON a perdus."""
    try:
        import sqlite3
        import etat_sqlite as es
        if not os.path.exists(es.BASE):
            return 0
        connus = {es._cle_trade(t) for t in pf.get("trades_fermes", [])}
        co = sqlite3.connect(es.BASE, timeout=10)
        co.row_factory = sqlite3.Row
        ajoutes = 0
        if not pf.get("trades_fermes"):
            co.close()
            return 0  # sans repere temporel on ne melange pas les archives anterieures au JSON courant
        for r in co.execute("select * from trades order by date_fermeture"):
            t = {k: r[k] for k in r.keys() if k not in ("cle", "origine", "insere_le")}
            if t.get("contexte"):
                try:
                    t["contexte"] = json.loads(t["contexte"])
                except Exception:
                    pass
            if es._cle_trade(t) in connus:
                continue
            # on n'ajoute que les trades plus recents que le dernier connu, pour ne pas melanger des archives anterieures
            if str(t.get("date_fermeture") or "") < str(pf["trades_fermes"][0].get("date_fermeture") or ""):
                continue
            pf.setdefault("trades_fermes", []).append(t)
            connus.add(es._cle_trade(t))
            ajoutes += 1
        co.close()
        if ajoutes:
            pf["trades_fermes"].sort(key=lambda t: str(t.get("date_fermeture") or ""))
            if journal:
                journal(f"  [JSON-SUR] {ajoutes} trade(s) ferme(s) recupere(s) depuis la base SQLite")
        return ajoutes
    except Exception as e:
        if journal:
            journal(f"  [JSON-SUR] recuperation SQLite impossible : {e}")
        return 0


if __name__ == "__main__":
    import sys
    chemin = sys.argv[1] if len(sys.argv) > 1 else "paper_trading.json"
    txt = open(chemin, encoding="utf-8").read()
    obj, methode = reparer_texte(txt)
    if obj is None:
        print(f"IRREPARABLE : {methode}")
        sys.exit(1)
    print(f"Methode : {methode}")
    if isinstance(obj, dict):
        print(f"  liquidites : {obj.get('liquidites')}  positions : {len(obj.get('positions', []))}  trades fermes : {len(obj.get('trades_fermes', []))}")
    if "--appliquer" in sys.argv:
        copie = f"{chemin}.corrompu.{time.strftime('%Y%m%d-%H%M%S')}"
        shutil.copy2(chemin, copie)
        if isinstance(obj, dict) and "trades_fermes" in obj:
            completer_trades_depuis_sqlite(obj)
        ecrire(chemin, obj)
        print(f"Repare et reecrit. Original garde : {copie}")
