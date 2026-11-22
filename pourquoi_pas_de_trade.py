#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
pourquoi_pas_de_trade.py — en une commande : pourquoi le bot n'ouvre plus de position.

LECTURE SEULE : ne modifie aucun fichier, n'envoie rien sur Telegram, ne redemarre rien, n'ouvre aucun trade.
Il lit ce que le bot ecrit deja et remonte la chaine dans l'ordre ou un signal meurt :

  1. Le bot tourne-t-il ?         services systemd, age du dernier cycle, erreurs du log, disque, memoire
  2. Le portefeuille              lisible ? liquidites, positions, date de la derniere ouverture, ouvertures par jour
  3. Blocages globaux MAINTENANT  porte (fenetre horaire, tendance lente BTC, chaleur, regime), pause protection du
                                  capital, coupe-circuit flash crash, plancher de liquidites, plafond de positions/jour
  4. Qui tue les signaux          entonnoir (avant la porte), porte (filtre par filtre), cerveau (ia_autonome)
  5. Verdict                      les causes classees, de la plus bloquante a la moins bloquante

Usage : python3 pourquoi_pas_de_trade.py [heures]     (fenetre d'analyse, 48 h par defaut)
"""
import json
import os
import re
import shutil
import subprocess
import sys
import threading
import time
from collections import Counter
from datetime import datetime, timedelta, timezone

DOSSIER = os.path.dirname(os.path.abspath(__file__))
os.chdir(DOSSIER)
sys.path.insert(0, DOSSIER)

CAUSES = []      # (gravite 1 = bloque tout ... 3 = ralentit, texte, quoi faire)


def cause(gravite, texte, action=""):
    CAUSES.append((gravite, texte, action))


def titre(t):
    print("\n" + t)
    print("-" * len(t))


def chemin(nom):
    return os.path.join(DOSSIER, nom)


def sh(cmd, delai=8):
    try:
        r = subprocess.run(cmd, shell=True, capture_output=True, text=True, timeout=delai)
        return (r.stdout or "").strip()
    except Exception:
        return ""


def queue(nom, octets=1_500_000):
    """Fin d'un fichier texte (les logs font vite des centaines de Mo : on ne lit que la fin)."""
    try:
        with open(chemin(nom), "rb") as f:
            f.seek(0, 2)
            taille = f.tell()
            f.seek(max(0, taille - octets))
            return f.read().decode("utf-8", "replace")
    except Exception:
        return ""


def lignes_json(nom, octets=6_000_000):
    out = []
    for l in queue(nom, octets).splitlines():
        l = l.strip()
        if l.startswith("{"):
            try:
                out.append(json.loads(l))
            except Exception:
                pass
    return out


def avec_delai(fn, secondes=30, defaut=None):
    """Appelle fn dans un fil : une API lente ne doit pas figer le diagnostic."""
    res = {"v": defaut}

    def _go():
        try:
            res["v"] = fn()
        except Exception as e:
            res["v"] = ("erreur", str(e)[:120])
    t = threading.Thread(target=_go, daemon=True)
    t.start()
    t.join(secondes)
    return res["v"]


def date_naive(s):
    try:
        return datetime.strptime(str(s)[:16], "%Y-%m-%d %H:%M")
    except Exception:
        return None


def age(secondes):
    if secondes is None:
        return "?"
    if secondes < 90:
        return f"{secondes:.0f} s"
    if secondes < 5400:
        return f"{secondes / 60:.0f} min"
    if secondes < 172800:
        return f"{secondes / 3600:.1f} h"
    return f"{secondes / 86400:.1f} j"


# ------------------------------------------------------------------ 1. le bot tourne-t-il ?
def section_services():
    titre("1. Le bot tourne-t-il ?")
    for svc, role in (("paper_trading.service", "boucle de trading"), ("chat_naturel.service", "cerveau ia_autonome + Telegram")):
        etat = sh(f"systemctl is-active {svc}") or "inconnu"
        depuis = sh(f"systemctl show {svc} -p ActiveEnterTimestamp --value")
        relances = sh(f"systemctl show {svc} -p NRestarts --value")
        print(f"  {svc:24s} {etat:9s} depuis {depuis or '?'} | relances auto : {relances or '?'}")
        if etat not in ("active", "inconnu"):
            cause(1, f"{svc} est '{etat}' ({role}) : rien ne peut s'ouvrir par ce chemin.",
                  f"sudo systemctl restart {svc} && sleep 20 && systemctl is-active {svc}")
        try:
            if int(relances or 0) >= 5:
                cause(2, f"{svc} a ete relance {relances} fois par systemd : il plante en boucle (voir les erreurs ci-dessous).",
                      f"journalctl -u {svc} -n 60 --no-pager")
        except Exception:
            pass
    # age du dernier cycle
    try:
        a = time.time() - os.path.getmtime(chemin("paper_trading.log"))
        print(f"  paper_trading.log        derniere ecriture il y a {age(a)}")
        if a > 900:
            cause(1, f"Le log du bot n'a pas bouge depuis {age(a)} : la boucle est arretee ou figee.",
                  "sudo systemctl restart paper_trading.service && sleep 30 && tail -n 30 paper_trading.log")
    except Exception:
        print("  paper_trading.log        introuvable")
        cause(1, "paper_trading.log introuvable dans ce dossier : la boucle n'ecrit pas ici (mauvais dossier ou service jamais lance).",
              "systemctl cat paper_trading.service | grep -E 'ExecStart|WorkingDirectory|Standard'")
    log = queue("paper_trading.log")
    lignes = log.splitlines()
    cycles = [l for l in lignes if "Verification des prix" in l]
    print(f"  cycles dans la fin du log : {len(cycles)}" + (f" (dernier : {cycles[-1].strip()[:40]})" if cycles else ""))
    # erreurs
    n_tb = sum(1 for l in lignes if l.startswith("Traceback"))
    erreurs = Counter()
    for i, l in enumerate(lignes):
        if l.startswith("Traceback"):
            for m in lignes[i + 1:i + 40]:
                if m and not m.startswith((" ", "\t")):
                    erreurs[m.strip()[:110]] += 1
                    break
    print(f"  plantages (Traceback) dans la fin du log : {n_tb}")
    for e, n in erreurs.most_common(3):
        print(f"     {n} x {e}")
    if n_tb >= 3:
        e0 = erreurs.most_common(1)[0][0] if erreurs else "?"
        cause(1 if len(cycles) < 3 else 2, f"Le bot plante ({n_tb} Traceback recents). Erreur la plus frequente : {e0}",
              "grep -n -A 12 Traceback paper_trading.log | tail -n 40")
    # disque et memoire
    try:
        d = shutil.disk_usage(DOSSIER)
        pct = d.used / d.total * 100
        print(f"  disque                   {pct:.0f} % plein, {d.free / 1e9:.1f} Go libres")
        if d.free < 300e6 or pct >= 97:
            cause(1, f"Disque presque plein ({pct:.0f} %, {d.free / 1e6:.0f} Mo libres) : le bot ne peut plus enregistrer son portefeuille ni ses journaux.",
                  "du -sh ~/agent-ia/revenus/tiktok/* ~/agent-ia/*.log 2>/dev/null | sort -h | tail -n 12")
        elif pct >= 90:
            cause(3, f"Disque a {pct:.0f} % : a surveiller (les videos du studio et les logs grossissent).", "")
    except Exception:
        pass
    try:
        mem = {}
        for l in open("/proc/meminfo"):
            k, v = l.split(":", 1)
            mem[k] = int(v.split()[0])
        dispo = mem.get("MemAvailable", 0) / 1e6
        print(f"  memoire                  {dispo:.1f} Go disponibles sur {mem.get('MemTotal', 0) / 1e6:.1f} Go")
        if dispo < 0.25:
            cause(2, f"Memoire presque epuisee ({dispo * 1000:.0f} Mo disponibles) : le noyau peut tuer le bot (Ollama, studio video).",
                  "ps aux --sort=-%mem | head -n 8")
    except Exception:
        pass
    return log


# ------------------------------------------------------------------ 2. le portefeuille
def section_portefeuille(heures):
    titre("2. Le portefeuille")
    pf = None
    try:
        with open(chemin("paper_trading.json")) as f:
            pf = json.load(f)
    except Exception as e:
        print(f"  paper_trading.json ILLISIBLE : {str(e)[:100]}")
        cause(1, "paper_trading.json est illisible (fichier tronque, comme le 31/10) : le bot ne peut pas charger son etat.",
              "python3 -c \"import json_sur; pf=json_sur.lire('paper_trading.json'); print('repare:', len(pf.get('positions',[])), 'positions,', round(pf.get('liquidites',0),2), 'EUR')\" && sudo systemctl restart paper_trading.service")
        return None
    pos = pf.get("positions", []) or []
    fermes = pf.get("trades_fermes", []) or []
    liq = float(pf.get("liquidites", 0) or 0)
    val = liq + sum(float(p.get("montant_eur", 0) or 0) for p in pos)
    print(f"  liquidites {liq:.2f} EUR | {len(pos)} position(s) ouverte(s) | valeur au cout {val:.2f} EUR")
    for p in pos[:8]:
        print(f"     {str(p.get('symbole', '?')):10s} {float(p.get('montant_eur', 0) or 0):7.2f} EUR  ouverte {p.get('date_ouverture', '?')}  {p.get('strategie') or p.get('source') or ''}")
    ouvertures = {}
    for t in fermes:
        if "_PARTIAL" in str(t.get("source", "")):
            continue
        ouvertures[(t.get("symbole"), str(t.get("date_ouverture"))[:16])] = t.get("strategie") or t.get("source") or "?"
    for p in pos:
        ouvertures[(p.get("symbole"), str(p.get("date_ouverture"))[:16])] = p.get("strategie") or p.get("source") or "?"
    dates = sorted((date_naive(k[1]), k[0], v) for k, v in ouvertures.items() if date_naive(k[1]))
    if dates:
        d, s, st = dates[-1]
        a = (datetime.now() - d).total_seconds()
        print(f"  derniere ouverture : {d:%Y-%m-%d %H:%M} ({s}, {st}), il y a {age(a)}")
    else:
        print("  aucune ouverture enregistree")
    auj = datetime.now().date()
    par_jour = Counter(d.date() for d, _, _ in dates)
    print("  ouvertures par jour (10 j) : " + "  ".join(f"{(auj - timedelta(days=i)):%d/%m}:{par_jour.get(auj - timedelta(days=i), 0)}" for i in range(9, -1, -1)))
    # plafonds
    max_pos, liq_min = 5, 200.0
    try:
        src = open(chemin("paper_trading.py"), encoding="utf-8", errors="replace").read(8000)
        m = re.search(r"^MAX_POSITIONS\s*=\s*(\d+)", src, re.M)
        max_pos = int(m.group(1)) if m else max_pos
        m = re.search(r"^LIQUIDITE_MIN\s*=\s*([\d.]+)", src, re.M)
        liq_min = float(m.group(1)) if m else liq_min
    except Exception:
        pass
    if len(pos) >= max_pos:
        cause(1, f"Plafond atteint : {len(pos)} positions ouvertes pour un maximum de {max_pos}. Aucune ouverture tant qu'une position ne se ferme pas.", "")
    if liq < liq_min:
        cause(1, f"Liquidites {liq:.2f} EUR sous le plancher de {liq_min:.0f} EUR : aucune ouverture possible.", "")
    return pf


# ------------------------------------------------------------------ 3. blocages globaux
def section_globaux(pf):
    titre("3. Blocages globaux en ce moment")
    print(f"  heure du VPS : {datetime.now():%Y-%m-%d %H:%M} | UTC : {datetime.now(timezone.utc):%H:%M}")
    # porte
    try:
        import porte_entree as pe
        des = avec_delai(pe.filtres_desarmes, 30, set())
        des = des if isinstance(des, set) else set()
        armes = sorted(v for k, v in pe._NOM_FILTRE.items() if v not in des and pe._actif(k))
        print(f"  porte, filtres armes    : {', '.join(armes) or 'aucun'}")
        print(f"  porte, filtres desarmes : {', '.join(sorted(des)) or 'aucun'}")
        pf_ = pf or {"positions": [], "liquidites": 0}
        bloque_tout = []
        # chaque filtre global est lu separement : on voit tout ce qui bloque, pas seulement le premier
        fen = avec_delai(pe.fenetre_interdite, 20, (False, ""))
        if isinstance(fen, tuple) and fen[0] is True:
            arme = pe._actif("FENETRES")
            print(f"  fenetre horaire : INTERDITE ({fen[1]})" + ("" if arme else " mais filtre desarme"))
            if arme:
                bloque_tout.append("fenetre horaire")
                cause(3, f"Fenetre horaire interdite en ce moment ({fen[1]}) : blocage normal et temporaire.", "")
        else:
            print("  fenetre horaire : libre")
        tl = avec_delai(pe.tendance_lente_btc, 30, {}) or {}
        if isinstance(tl, dict) and tl.get("haussiere") is not None:
            arme = pe._actif("TENDANCE_LENTE")
            print(f"  tendance lente BTC (EMA {tl.get('ema_jours')} j) : {'haussiere' if tl['haussiere'] else 'BAISSIERE'} "
                  f"(prix {tl.get('ecart_pct')} % vs EMA, pente {tl.get('pente_pct')} %/5 j) | filtre {'ARME' if arme else 'desarme'}")
            if not tl["haussiere"] and arme:
                bloque_tout.append("tendance lente")
                cause(1, f"Filtre « tendance lente » arme et BTC sous son EMA {tl.get('ema_jours')} jours ({tl.get('ecart_pct')} %) : la porte refuse TOUS "
                         "les achats et le cerveau n'est meme pas consulte, tant que BTC ne repasse pas au-dessus.", "python3 porte_entree.py bilan")
        else:
            print("  tendance lente BTC : donnees indisponibles (le filtre laisse passer)")
        reg = avec_delai(lambda: pe.regime_actuel("BTCUSDT"), 30, {}) or {}
        if isinstance(reg, dict) and reg.get("mode"):
            arme = pe._actif("REGIME")
            print(f"  regime BTC 1 h : {reg.get('mode')} (ADX {reg.get('adx')}, ATR {reg.get('atr_pct')} % = {reg.get('atr_percentile')}e centile) | filtre {'ARME' if arme else 'desarme'}")
            if reg.get("mode") == "turbulent" and arme:
                bloque_tout.append("regime turbulent")
                cause(1, f"Filtre « regime » arme et marche TURBULENT (ATR 1 h de BTC au {reg.get('atr_percentile')}e centile) : la porte refuse tous les achats "
                         "tant que la volatilite ne retombe pas. Blocage voulu, il se leve seul.", "python3 porte_entree.py bilan")
        try:
            ch = pe.chaleur_portefeuille(pf_, risque_nouveau=1.0)
            max_pos = pe.MAX_POSITIONS_CRYPTO + (1 if (isinstance(tl, dict) and tl.get("haussiere")) else 0)
            print(f"  chaleur : {ch.get('n_crypto')} position(s) crypto (max {max_pos}), risque ouvert {ch.get('risque_ouvert')} EUR (plafond {pe.risque_total_max(pf_)} EUR)")
            if pe._actif("CHALEUR") and (ch.get("n_crypto", 0) >= max_pos or ch.get("risque_apres", 0) > pe.risque_total_max(pf_)):
                bloque_tout.append("chaleur")
                cause(1, f"Chaleur du portefeuille au plafond ({ch.get('n_crypto')} positions crypto, risque ouvert {ch.get('risque_ouvert')} EUR) : "
                         "aucune ouverture tant qu'une position ne se ferme pas.", "")
        except Exception:
            pass
        print("  => la porte bloque TOUT en ce moment : " + ", ".join(bloque_tout) if bloque_tout else "  => la porte ne bloque rien de global en ce moment")
    except Exception as e:
        print(f"  porte indisponible : {str(e)[:100]}")
    # veto des professeurs (garde BTC du professeur virtuel + meilleurs traders Hyperliquid)
    try:
        import professeurs_veto as pvt
        if not pvt._actif():
            print("  veto des professeurs : coupe (PROF_VETO=0)")
        else:
            av = avec_delai(lambda: pvt.avis("BTCUSDT"), 40, (True, ""))
            arme = True
            try:
                import entonnoir as en
                arme = bool(en.armee("professeurs"))
            except Exception:
                pass
            if isinstance(av, tuple) and av[0] is False:
                print(f"  veto des professeurs : NON a tout achat — {av[1][:110]} | couche {'ARMEE' if arme else 'desarmee'}")
                if arme:
                    cause(1, f"Veto des professeurs sur tous les achats : {av[1][:110]}. La couche est armee, donc chaque signal d'achat est tue.",
                          "python3 entonnoir.py bilan")
            else:
                print(f"  veto des professeurs : rien a redire | couche {'armee' if arme else 'desarmee'}")
    except Exception as e:
        print(f"  veto des professeurs : indisponible ({str(e)[:60]})")
    # ouvertures du jour
    try:
        import porte_entree as pe
        c = pe.cadence(pf or {}, "__AUCUN__")
        print(f"  ouvertures aujourd'hui : {c.get('n_jour')} / {pe.MAX_OUVERTURES_JOUR}")
        if c.get("n_jour", 0) >= pe.MAX_OUVERTURES_JOUR:
            cause(2, f"Plafond du jour atteint : {c['n_jour']} ouvertures (max {pe.MAX_OUVERTURES_JOUR}). Reprise demain a 00:00.", "")
    except Exception:
        pass
    # protection du capital (lecture du fichier d'etat seulement : verifier_pause() ecrit et alerte)
    try:
        with open(chemin("protection_capital.json")) as f:
            s = json.load(f)
        if s.get("paused"):
            depuis = age(time.time() - float(s.get("pause_start") or 0)) if s.get("pause_start") else "?"
            print(f"  protection du capital : PAUSE depuis {depuis} — {s.get('raison')}")
            cause(1, f"Protection du capital en PAUSE ({s.get('raison')}) : toutes les entrees sont suspendues.",
                  "python3 protection_capital.py")
        else:
            print(f"  protection du capital : active, pas de pause (pertes consecutives {s.get('consecutive_losses', '?')})")
    except Exception:
        print("  protection du capital : pas de fichier d'etat (pas de pause)")
    # flash crash
    try:
        import flash_crash as fc
        if fc.circuit_breaker_actif():
            print(f"  flash crash : COUPE-CIRCUIT ACTIF (niveau {fc.get_niveau_protection()})")
            cause(1, "Coupe-circuit flash crash actif : tous les trades sont bloques jusqu'a sa levee automatique.", "python3 flash_crash.py")
        else:
            print("  flash crash : pas de coupe-circuit")
    except Exception as e:
        print(f"  flash crash : indisponible ({str(e)[:60]})")
    # registre : qui a le droit d'ouvrir
    try:
        import registre_strategies as rs
        d = rs._charger()
        droits = sorted(set(rs.DROIT_OUVERTURE) | set(d.get("droits", [])))
        stats = d.get("strategies", {})
        lignes = []
        for nom in droits:
            st = (stats.get(nom) or {}).get("statut")
            if st or nom in d.get("droits", []) or nom == "ia_autonome":
                lignes.append(f"{nom} ({st or 'candidate'})")
        print("  droit d'ouvrir : " + ", ".join(lignes))
        retirees = [n for n in droits if (stats.get(n) or {}).get("statut") == "retiree"]
        if retirees:
            cause(2, "Strategie(s) avec droit d'ouvrir mais RETIREE(S) du registre : " + ", ".join(retirees) + ".", "python3 registre_strategies.py")
    except Exception as e:
        print(f"  registre : indisponible ({str(e)[:60]})")


# ------------------------------------------------------------------ 4. qui tue les signaux
def section_signaux(heures, log):
    titre(f"4. Qui tue les signaux (depuis {heures} h)")
    t0 = time.time() - heures * 3600
    # 4a. log du bot
    lignes = log.splitlines()
    n_achat = sum(1 for l in lignes if "[ACHAT]" in l)
    tags = Counter()
    for l in lignes:
        if re.search(r"bloqu|skip|SKIP|STOP|suspendu|interdit|trop faible|cooldown|COOLDOWN", l):
            m = re.match(r"\s*\[([^\]]{2,28})\]", l)
            if m:
                tags[m.group(1)] += 1
    print(f"  fin du log ({len(lignes)} lignes) : {n_achat} ligne(s) [ACHAT] ; lignes de blocage par etiquette :")
    for k, n in tags.most_common(10):
        print(f"     {n:5d}  [{k}]")
    if not tags:
        print("     aucune ligne de blocage : aucun signal n'arrive jusqu'aux filtres (ou le log ne tourne plus)")
    # 4b. entonnoir
    ent = [e for e in lignes_json("entonnoir_log.jsonl") if float(e.get("ts", 0) or 0) >= t0]
    c_ent = Counter((e.get("couche"), bool(e.get("armee", True))) for e in ent)
    print(f"  entonnoir (avant la porte) : {len(ent)} candidat(s) tue(s)")
    for (couche, armee), n in c_ent.most_common(10):
        print(f"     {n:5d}  {str(couche):22s} {'bloque' if armee else 'desarmee (laisse passer)'}")
    strat_ent = Counter(e.get("strategie") for e in ent)
    if strat_ent:
        print("     strategies concernees : " + ", ".join(f"{k} {n}" for k, n in strat_ent.most_common(6)))
    # 4c. porte
    limite = datetime.now(timezone.utc) - timedelta(hours=heures)
    porte = []
    for d in lignes_json("porte_entree_log.jsonl"):
        dt = date_naive((d.get("infos") or {}).get("date"))
        if dt and dt.replace(tzinfo=timezone.utc) >= limite:
            porte.append(d)
    ok = sum(1 for d in porte if d.get("ok"))
    print(f"  porte : {len(porte)} passage(s), {ok} ouvert(s), {len(porte) - ok} bloque(s)")
    c_porte = Counter(re.split(r"[:(]", str(d.get("raison", "")))[0].strip()[:44] for d in porte if not d.get("ok"))
    for k, n in c_porte.most_common(8):
        print(f"     {n:5d}  {k}")
    # 4d. cerveau
    dec = []
    try:
        with open(chemin("journal_decisions.json")) as f:
            dec = json.load(f).get("decisions", [])
    except Exception:
        pass
    lim_naive = datetime.now() - timedelta(hours=heures)
    lim_utc = datetime.now(timezone.utc).replace(tzinfo=None) - timedelta(hours=heures)
    recents = [x for x in dec if (date_naive(x.get("date")) or datetime.min) >= min(lim_naive, lim_utc)]
    achats = sum(1 for x in recents if x.get("action") == "ACHAT")
    print(f"  cerveau (ia_autonome) : {len(recents)} decision(s), {achats} ACHAT")
    c_cerv = Counter(x.get("etape") for x in recents if x.get("action") != "ACHAT")
    for k, n in c_cerv.most_common(6):
        print(f"     {n:5d}  RIEN a l'etape '{k}'")
    for x in recents[-3:]:
        print(f"     {str(x.get('date'))[5:16]} {x.get('action')} {x.get('sym') or ''} conf {x.get('confiance')} [{x.get('etape')}] {str(x.get('raison', ''))[:90]}")
    if dec and not recents:
        dern = date_naive(dec[-1].get("date"))
        a = (datetime.now() - dern).total_seconds() if dern else None
        cause(1, f"Le cerveau (ia_autonome, le seul droit d'ouvrir de base) n'a rendu AUCUNE decision depuis {age(a)} : "
                 "chat_naturel est arrete, ou ses modeles (Gemini, Ollama) ne repondent plus.",
              "systemctl is-active chat_naturel.service; journalctl -u chat_naturel.service -n 40 --no-pager | tail -n 40")
    # modeles
    lr = queue("llm_router.log", 200_000).splitlines()
    if lr:
        err = [l for l in lr[-300:] if re.search(r"429|quota|timeout|erreur|error|echec|indisponible", l, re.I)]
        print(f"  routeur des modeles : {len(err)} ligne(s) d'erreur sur les {min(300, len(lr))} dernieres")
        for l in err[-2:]:
            print(f"     {l.strip()[:120]}")
        if len(err) > 150:
            cause(2, "Les modeles d'IA echouent tres souvent (quota ou cle expiree) : le cerveau ne peut plus proposer d'achat.", "tail -n 20 llm_router.log")
    # causes tirees des comptages
    if recents and not achats:
        top = c_cerv.most_common(1)[0] if c_cerv else (None, 0)
        part = top[1] / max(1, len(recents))
        if top[0] == "porte" and part >= 0.6:
            raisons = Counter(str(x.get("raison", ""))[:60] for x in recents if x.get("etape") == "porte")
            cause(1, f"Le cerveau est arrete par la porte dans {part * 100:.0f} % des cas : {raisons.most_common(1)[0][0]}.", "python3 porte_entree.py bilan")
        elif top[0] == "preselection" and part >= 0.6:
            cause(2, f"La preselection du cerveau ne trouve aucune crypto avec un score positif ({part * 100:.0f} % des cas) : marche juge defavorable, pas une panne.", "python3 cerveau.py")
        elif top[0] == "analyste" and part >= 0.6:
            cause(2, f"L'analyste repond RIEN dans {part * 100:.0f} % des cas : il ne voit pas de setup (confiance sous le seuil).", "python3 cerveau.py")
        elif top[0] == "critique" and part >= 0.4:
            cause(2, f"Le critique oppose son veto dans {part * 100:.0f} % des cas.", "python3 cerveau.py")
    if porte and ok == 0 and c_porte:
        k, n = c_porte.most_common(1)[0]
        cause(1 if n / len(porte) >= 0.7 else 2, f"La porte a refuse les {len(porte)} candidats ; premier motif : « {k} » ({n} fois).", "python3 porte_entree.py bilan")
    if ent and not porte:
        (couche, armee), n = c_ent.most_common(1)[0]
        if armee:
            cause(2, f"Aucun candidat n'atteint la porte : tout meurt avant, d'abord a la couche « {couche} » ({n} sur {len(ent)}).", "python3 entonnoir.py bilan")
    if not ent and not porte and not recents:
        cause(1, f"Aucun signal en {heures} h : ni veto, ni passage a la porte, ni decision du cerveau. Le bot ne genere plus de candidats "
                 "(boucle arretee, version du code sans entonnoir, ou source de prix en panne).", "tail -n 40 paper_trading.log")


# ------------------------------------------------------------------ 5. verdict
def verdict():
    titre("5. Verdict")
    if not CAUSES:
        print("  Aucune panne detectee : le bot tourne, rien ne bloque globalement.")
        print("  S'il n'ouvre pas, c'est que ses filtres jugent les setups insuffisants ; voir les comptages du point 4.")
        return
    libelle = {1: "BLOQUANT", 2: "IMPORTANT", 3: "A SAVOIR"}
    vus = set()
    for g, t, a in sorted(CAUSES, key=lambda c: c[0]):
        if t in vus:
            continue
        vus.add(t)
        print(f"  [{libelle.get(g, '?')}] {t}")
        if a:
            print(f"      a lancer : {a}")


if __name__ == "__main__":
    try:
        heures = int(sys.argv[1]) if len(sys.argv) > 1 else 48
    except Exception:
        heures = 48
    print(f"POURQUOI PAS DE TRADE — {datetime.now():%Y-%m-%d %H:%M} (lecture seule, fenetre {heures} h)")
    version = sh("git log -1 --format='%h %ad' --date=short 2>/dev/null")
    if version:
        print(f"code : {version} | paper_trading.py modifie le {datetime.fromtimestamp(os.path.getmtime(chemin('paper_trading.py'))):%Y-%m-%d %H:%M}")
    log = ""
    pf = None
    try:
        log = section_services() or ""
    except Exception as e:
        print(f"  (section 1 interrompue : {e})")
    try:
        pf = section_portefeuille(heures)
    except Exception as e:
        print(f"  (section 2 interrompue : {e})")
    try:
        section_globaux(pf)
    except Exception as e:
        print(f"  (section 3 interrompue : {e})")
    try:
        section_signaux(heures, log)
    except Exception as e:
        print(f"  (section 4 interrompue : {e})")
    verdict()
