#!/usr/bin/env python3
"""page_porte.py — page /porte du dashboard : porte d'entree, quotas LLM, registre bayesien, meta-modele, infra."""
import html
import json
import os

DOSSIER = os.path.dirname(os.path.abspath(__file__))


def etat():
    e = {}
    try:
        import llm_router
        e["llm"] = llm_router.quotas()
    except Exception as ex:
        e["llm"] = {"erreur": str(ex)}
    try:
        import porte_entree as pe
        e["porte_stats"] = pe.statistiques()
        e["bilan_filtres"] = pe.bilan_filtres()
        try:
            import registre_strategies as _rs
            e["casier"] = _rs.casier()
        except Exception as ex:
            e["casier"] = {"erreur": str(ex)}
        try:
            import stop_atr as _sa
            e["risque_par_trade"] = _sa.risque_courant()
        except Exception as ex:
            e["risque_par_trade"] = None
        e["porte_dernieres"] = pe.dernieres_decisions(25)[::-1]
        e["tendance_lente"] = pe.tendance_lente_btc()
        e["regime"] = pe.regime_actuel("BTCUSDT")
        e["fenetre"] = pe.fenetre_interdite()
    except Exception as ex:
        e["porte_stats"] = {"erreur": str(ex)}
    try:
        d = json.load(open(os.path.join(DOSSIER, "registre_strategies.json")))
        e["registre"] = sorted(d.get("strategies", {}).values(), key=lambda s: -s.get("n", 0))
        for s in e["registre"]:
            s["nom"] = next((k for k, v in d["strategies"].items() if v is s), "?")
    except Exception:
        e["registre"] = []
    try:
        import meta_modele
        e["meta"] = meta_modele.resume()
    except Exception as ex:
        e["meta"] = str(ex)
    try:
        import etiquetage_triple_barriere as et
        e["triple_barriere"] = et.resume()
    except Exception as ex:
        e["triple_barriere"] = str(ex)
    try:
        p = os.path.join(DOSSIER, "prix_ws.json")
        import time
        e["ws"] = {"age_s": round(time.time() - os.path.getmtime(p)), "n": json.load(open(p)).get("n")} if os.path.exists(p) else None
    except Exception:
        e["ws"] = None
    return e


def json_etat():
    return json.dumps(etat(), ensure_ascii=False, default=str, indent=1)


def build_page():
    e = etat()
    tok = ""
    try:
        import dashboard_premium
        tok = dashboard_premium.TOKEN
    except Exception:
        pass
    H = html.escape
    css = "body{background:#0d1117;color:#e6edf3;font-family:-apple-system,Segoe UI,sans-serif;padding:20px;max-width:1100px;margin:auto}" \
          "h2{color:#58a6ff;border-bottom:1px solid #30363d;padding-bottom:6px;margin-top:28px}table{border-collapse:collapse;width:100%;font-size:13px}" \
          "td,th{border-bottom:1px solid #21262d;padding:5px 8px;text-align:left}th{color:#8b949e}.ok{color:#3fb950}.ko{color:#f85149}.m{color:#8b949e}" \
          "pre{background:#161b22;padding:10px;border-radius:6px;overflow:auto;font-size:12px}a{color:#58a6ff;text-decoration:none}"
    out = [f"<html><head><meta charset='utf-8'><title>Porte & IA</title><style>{css}</style></head><body>",
           f"<div><a href='/?token={tok}'>← Dashboard</a> · <a href='/cerveau?token={tok}'>Cerveau</a> · <a href='/kraken?token={tok}'>Kraken</a> · <a href='/api/porte?token={tok}'>JSON</a></div>",
           "<h1>🚪 Porte d'entrée unique &amp; cerveau multi-modèles</h1>"]
    # contexte marche
    tl, rg, fen = e.get("tendance_lente") or {}, e.get("regime") or {}, e.get("fenetre") or (False, "")
    out.append("<h2>Contexte marché (ce que la porte regarde)</h2><table>")
    out.append(f"<tr><th>Tendance lente BTC (EMA {tl.get('ema_jours')} j)</th><td class='{'ok' if tl.get('haussiere') else 'ko'}'>{'HAUSSIÈRE' if tl.get('haussiere') else ('BAISSIÈRE → aucun achat' if tl.get('haussiere') is False else 'inconnue')}</td><td class='m'>prix {tl.get('ecart_pct')}% vs EMA, pente {tl.get('pente_pct')}%/5j</td></tr>")
    out.append(f"<tr><th>Régime 1h BTC</th><td>{H(str(rg.get('mode')))}</td><td class='m'>ADX {rg.get('adx')} · ATR {rg.get('atr_pct')}% = {rg.get('atr_percentile')}e percentile</td></tr>")
    out.append(f"<tr><th>Fenêtre interdite</th><td class='{'ko' if fen[0] else 'ok'}'>{'OUI' if fen[0] else 'non'}</td><td class='m'>{H(str(fen[1]))}</td></tr>")
    ws = e.get("ws")
    out.append(f"<tr><th>Flux WebSocket Kraken</th><td class='{'ok' if ws and ws['age_s'] < 15 else 'm'}'>{('actif, ' + str(ws['n']) + ' prix, ' + str(ws['age_s']) + ' s') if ws else 'non démarré (optionnel)'}</td><td></td></tr></table>")
    # porte stats
    ps = e.get("porte_stats") or {}
    out.append(f"<h2>Décisions de la porte (dernières {ps.get('total', 0)})</h2>")
    out.append(f"<p>Ouvertes : <b class='ok'>{ps.get('ouvertes', 0)}</b> · bloquées : " + " · ".join(f"{H(k)} <b>{v}</b>" for k, v in (ps.get("bloquees") or {}).items()) + "</p>")
    # casier mesure + palier de risque
    cas = e.get("casier") or {}
    noms_j = ["lundi", "mardi", "mercredi", "jeudi", "vendredi", "samedi", "dimanche"]
    inter = [f"{s} ({v['n']} trades, {v['net']:+.1f} €)" for s, v in (cas.get("cryptos") or {}).items()] + \
            [f"{noms_j[int(j)]} ({v['n']} trades, {v['net']:+.1f} €)" for j, v in (cas.get("jours") or {}).items()]
    out.append("<h2>Casier mesuré &amp; risque par trade</h2>")
    out.append("<p>Cryptos / jours interdits parce que perdants avec confiance (≥ 15 trades, borne haute 90 % du gain moyen &lt; 0 ; révisé toutes les 10 min) : "
               + ("<b class='ko'>" + H(", ".join(inter)) + "</b>" if inter else "<b class='ok'>aucun</b>") + "</p>")
    rp = e.get("risque_par_trade")
    out.append(f"<p>Risque par trade actuel : <b>{rp if rp is not None else '?'} €</b> (palier 1 = 1 € ; ×2 dès 30 trades prouvés gagnants, ×3 dès 60 ; plafond 0,5 % du capital)</p>")
    # bilan contrefactuel : ce que chaque filtre a evite / coute (juge 8 h apres sur les bougies)
    bf = e.get("bilan_filtres") or {}
    if isinstance(bf, dict) and bf.get("filtres"):
        pp = bf.get("porte", {})
        o, b = pp.get("ouverts", {}), pp.get("bloques", {})
        out.append(f"<h2>Ce que la porte a évité ou coûté (jugé 8 h après, {bf.get('n_juges', 0)} passages)</h2>")
        out.append("<p class='m'>Chaque candidat, ouvert ou bloqué, est rejoué sur les bougies : objectif 2×stop touché d'abord = objectif, stop d'abord = stop. "
                   "1 R = le risque d'un trade. Un filtre « utile » a évité plus de R qu'il n'en a coûté ; « à revoir » = il a surtout bloqué des gagnants. Rien n'est retiré automatiquement.</p>")
        out.append(f"<p>Porte ouverte : objectif <b class='ok'>{o.get('tp', 0)}</b> · stop <b class='ko'>{o.get('sl', 0)}</b> · neutre {o.get('neutre', 0)} → <b>{o.get('r', 0):+.1f} R</b> &nbsp;|&nbsp; "
                   f"Porte bloquée : objectif {b.get('tp', 0)} · stop {b.get('sl', 0)} · neutre {b.get('neutre', 0)} → <b>{b.get('r', 0):+.1f} R</b> (négatif = les blocages ont protégé)</p>")
        try:
            des = pe.filtres_desarmes()
            out.append("<p>Mode auto (PORTE_AUTO) : <b>" + ("actif — filtres désarmés par les faits : " + (", ".join(sorted(des)) or "aucun") if des or __import__("config_env").lire("PORTE_AUTO", "1") == "1" else "inactif (PORTE_AUTO=1 pour que les filtres « à revoir » cessent de bloquer tout en restant mesurés)") + "</b></p>")
        except Exception:
            pass
        out.append("<table><tr><th>Filtre</th><th>Aurait bloqué</th><th>dont objectif</th><th>dont stop</th><th>R évité</th><th>Sautés (API muette)</th><th>Verdict</th></tr>")
        for f, st in sorted(bf["filtres"].items(), key=lambda kv: -kv[1].get("r_evite", 0)):
            bb = st.get("bloquerait", {})
            nb = bb.get("tp", 0) + bb.get("sl", 0) + bb.get("neutre", 0)
            cls = "ok" if st.get("verdict") == "utile" else "ko" if st.get("verdict") == "a revoir" else "m"
            out.append(f"<tr><td>{H(f)}</td><td>{nb}</td><td>{bb.get('tp', 0)}</td><td>{bb.get('sl', 0)}</td><td><b>{st.get('r_evite', 0):+.1f}</b></td><td>{st.get('sautes', 0)}</td><td class='{cls}'>{H(st.get('verdict', ''))}</td></tr>")
        out.append("</table>")
    out.append("<table><tr><th>Date UTC</th><th>Symbole</th><th>Stratégie</th><th>Verdict</th><th>Raison</th><th>TFI</th><th>p méta</th></tr>")
    for d in e.get("porte_dernieres") or []:
        inf = d.get("infos") or {}
        out.append(f"<tr><td>{H(str(inf.get('date', '')))}</td><td>{H(str(inf.get('sym', '')))}</td><td>{H(str(inf.get('strategie', '')))}</td>"
                   f"<td class='{'ok' if d.get('ok') else 'ko'}'>{'OUVERTE' if d.get('ok') else 'bloquée'}</td><td>{H(str(d.get('raison', ''))[:110])}</td>"
                   f"<td>{inf.get('tfi_30m', '')}</td><td>{inf.get('p_meta', '')}</td></tr>")
    out.append("</table>")
    # LLM
    llm = e.get("llm") or {}
    out.append(f"<h2>Modèles de langage — quotas du {H(str(llm.get('jour')))} (UTC)</h2><table><tr><th>Fournisseur</th><th>Clé</th><th>Appels / limite jour</th><th>OK</th><th>Échecs</th><th>Latence</th><th>Dernier modèle</th></tr>")
    for nom, v in (llm.get("fournisseurs") or {}).items():
        out.append(f"<tr><td>{H(nom)}</td><td class='{'ok' if v.get('cle') else 'ko'}'>{'oui' if v.get('cle') else 'NON'}</td><td>{v.get('appels_jour')} / {v.get('limite_jour') or '∞'}</td>"
                   f"<td>{v.get('ok')}</td><td>{v.get('echecs')}</td><td>{v.get('latence_moy_ms') or ''} ms</td><td class='m'>{H(str(v.get('dernier_modele') or ''))}</td></tr>")
    out.append("</table>")
    # registre
    out.append("<h2>Registre des stratégies — lecture bayésienne (Beta(5,5), intervalle 90 %)</h2><table><tr><th>Stratégie</th><th>Statut</th><th>n</th><th>WR</th><th>WR bayésien [IC 90 %]</th><th>Point mort</th><th>Net €</th><th>DSR</th><th>Par régime</th></tr>")
    for s in e.get("registre") or []:
        ic = f"{s.get('wr_bayes')}% [{s.get('wr_ic_bas')}–{s.get('wr_ic_haut')}]" if s.get("wr_bayes") is not None else ""
        pm = s.get("point_mort")
        cls = "ok" if (s.get("wr_ic_bas") or 0) > (pm or 100) else ("ko" if (s.get("wr_ic_haut") or 100) < (pm or 0) else "")
        par_reg = " · ".join(f"{k}: {v['n']}t {v.get('wr', 0):.0f}%" for k, v in (s.get("par_regime") or {}).items())
        out.append(f"<tr><td>{H(str(s.get('nom')))}</td><td>{H(str(s.get('statut')))}</td><td>{s.get('n')}</td><td>{s.get('wr')}%</td><td class='{cls}'>{ic}</td><td>{pm}%</td><td>{s.get('net')}</td><td>{s.get('dsr')}</td><td class='m'>{H(par_reg)}</td></tr>")
    out.append("</table>")
    out.append(f"<h2>Méta-modèle &amp; triple barrière</h2><pre>{H(str(e.get('meta')))}\n\n{H(str(e.get('triple_barriere')))}</pre>")
    out.append("</body></html>")
    return "\n".join(out)


if __name__ == "__main__":
    print(json_etat()[:1500])
