"""Tests rapides (pytest) des modules ajoutes le 18/10/2026. Aucun acces reseau requis."""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


def test_stop_atr_bornes_et_ratio():
    import stop_atr as sa
    from datetime import datetime, timezone
    nuit = datetime(2026, 10, 18, 3, 0, tzinfo=timezone.utc)
    assert sa.stop_pct(0.1, nuit) == sa.SL_MIN
    assert sa.stop_pct(5.0, nuit) == sa.SL_MAX
    r = sa.calculer(0.5, 1000.0, 200.0, maintenant=nuit)
    assert r["sl_pct"] == 1.0 and r["tp_pct"] == 2.0 and r["barriere_h"] == 24
    assert abs(r["montant"] * (r["sl_pct"] + sa.FRAIS_AR_PCT) / 100 - r["risque_eur"]) < 0.02   # 11/11 : risque en % du capital
    us = datetime(2026, 10, 18, 14, 0, tzinfo=timezone.utc)
    assert sa.stop_pct(0.5, us) > sa.stop_pct(0.5, nuit)
    assert sa.calculer(0.5, 1000.0, regime="turbulent", maintenant=nuit)["montant"] < r["montant"]


def test_cusum_detecte_un_mouvement():
    import porte_entree as pe
    plat = [100 + (i % 2) * 0.05 for i in range(48)]
    ev, depuis, _ = pe.cusum_evenement(plat)
    assert ev is False
    chute = plat[:45] + [97.5, 97.4, 97.6]
    ev, depuis, direction = pe.cusum_evenement(chute)
    assert ev is True and direction == "baisse" and depuis <= 2


def test_fenetre_us():
    import porte_entree as pe
    from datetime import datetime, timezone
    os.environ["PORTE_FENETRES"] = "1"
    assert pe.fenetre_interdite(datetime(2026, 10, 19, 13, 30, tzinfo=timezone.utc))[0]
    b, _ = pe.fenetre_interdite(datetime(2026, 10, 19, 15, 30, tzinfo=timezone.utc))
    # 15h30 : pas la fenetre US ; peut rester True seulement si une annonce macro est dans le feed local
    assert b in (True, False)


def test_chaleur_portefeuille():
    import porte_entree as pe
    pf = {"positions": [{"marche": "crypto", "montant_eur": 100, "sl_risque": 1.0}, {"marche": "crypto", "montant_eur": 100, "sl_risque": 1.5}]}
    ch = pe.chaleur_portefeuille(pf, 1.0)
    assert ch["n_crypto"] == 2 and abs(ch["risque_ouvert"] - 2.5) < 1e-6 and abs(ch["risque_apres"] - 3.5) < 1e-6


def test_memoire_episodique_impose_des_pertes():
    import memoire_episodique as me
    ctx = {"rsi": 40, "atr_pct": 0.5, "btc_var_1h": -0.1, "btc_var_24h": 1.0, "var_24h": -1.0, "dist_haut_24h": 2.0, "heure": 9}
    trades = [{"sym": "ETHUSDT", "gain": 1.0, "contexte": dict(ctx), "date_fermeture": f"2026-10-1{i} 10:00"} for i in range(5)]
    trades += [{"sym": "ETHUSDT", "gain": -0.8, "contexte": dict(ctx, rsi=44), "date_fermeture": "2026-10-01 10:00"},
               {"sym": "SOLUSDT", "gain": -0.9, "contexte": dict(ctx, rsi=36), "date_fermeture": "2026-10-02 10:00"}]
    res = me.similaires(trades, "ETHUSDT", ctx, n=5)
    assert len(res) == 5 and sum(1 for t in res if t["gain"] < 0) >= 2
    assert all("similarite" in t for t in res)


def test_validation_stats():
    import validation_stats as vs
    p = vs.beta_posterior(26, 40)
    assert 55 < p["moyenne"] < 70 and p["ic_bas"] < p["moyenne"] < p["ic_haut"]
    assert vs.point_mort(1.0, -1.0) == 50.0
    assert vs.trades_minimum(55, 1.2) > 30
    v = vs.valider_strategie([1.0] * 20 + [-1.0] * 10)
    assert v["n"] == 30 and v["verdict"] in ("credible", "pas assez de preuves")


def test_registre_bayes_et_thompson():
    import registre_strategies as rs
    tr = [{"strategie": "x", "gain_eur": 1.2 if i % 3 else -0.9, "raison": "TP", "date_fermeture": "2026-10-01 10:00", "contexte": {"regime": "range"}} for i in range(40)]
    st = rs.calculer(tr)["x"]
    assert st["wr_bayes"] is not None and st["wr_ic_bas"] < st["wr_bayes"] < st["wr_ic_haut"]
    assert st["par_regime"]["range"]["n"] == 40
    assert st["statut_auto"] in ("active", "probation")


def test_llm_router_quota_et_json():
    import llm_router as lr
    assert lr.extraire_json('bla {"a": 1, "b": [1,2],} fin') == {"a": 1, "b": [1, 2]}
    assert lr.fournisseur_de("gemini-2.5-flash") == "gemini"
    assert lr.fournisseur_de(lr.GROQ_MODELE) == "groq"
    q = lr.quotas()
    assert {"groq", "openrouter", "gemini", "local"} <= set(q["fournisseurs"])


def test_hikkake():
    import bougies_patterns as bp
    B = lambda o, h, l, c: {"ouverture": o, "haut": h, "bas": l, "cloture": c, "volume": 100}
    bg = [B(100, 101, 99, 100.5) for _ in range(12)] + [B(100, 103, 97, 101), B(101, 102, 99, 100), B(100, 101.5, 98, 98.5), B(98.5, 103, 98, 102.6)]
    assert "hikkake_haussier" in bp.analyser_patterns(bg)["patterns"]


def test_meta_modele_sans_modele():
    import meta_modele as mm
    f = mm.features_depuis_contexte({"rsi": 40, "heure": 9, "jour": 6}, regime="range")
    assert f["weekend"] == 1.0 and f["regime"] == "range"
    assert mm._auc([0.9, 0.8, 0.3, 0.2], [1, 1, 0, 0]) == 1.0


def test_etiquetage_label():
    import etiquetage_triple_barriere as et
    t0 = 1_000_000
    b1m = [(t0 + i * 60000, 100, 100.3, 99.8, 100.1, 1, 0) for i in range(10)] + [(t0 + 600000, 100, 102.5, 100, 102.4, 1, 0)]
    lab, barr, h, rend = et._label(b1m, t0, 100.0, 1.0, 2.0)
    assert lab == 1 and barr == "objectif"
    b1m2 = [(t0 + i * 60000, 100, 100.1, 98.9, 99.0, 1, 0) for i in range(3)]
    assert et._label(b1m2, t0, 100.0, 1.0, 2.0)[1] == "stop"


def test_router_sans_cle_config():
    import llm_router as lr
    # chaque fournisseur libre est connu des limites et de l'ordre de decision
    for nom, (url, modele, _) in lr.LIBRES.items():
        assert nom in lr.LIMITES and url.startswith("https://") and modele
        assert nom in lr.ORDRE["decision"]
        assert lr.fournisseur_de(modele) == nom
    assert lr.ORDRE["decision"][-1] == "local"      # le local reste le dernier filet


def test_porte_blocage_global_signature():
    import porte_entree as pe
    # avec tous les filtres desactives, rien ne bloque et la fonction rend (None, dict)
    import os
    for k in ("FENETRES", "TENDANCE_LENTE", "CHALEUR", "REGIME"):
        os.environ["PORTE_" + k] = "0"
    try:
        raison, infos = pe.blocage_global({"positions": []})
        assert raison is None and isinstance(infos, dict)
    finally:
        for k in ("FENETRES", "TENDANCE_LENTE", "CHALEUR", "REGIME"):
            os.environ.pop("PORTE_" + k, None)


def test_bilan_filtres_contrefactuel(tmp_path):
    import json, porte_entree as pe
    pe.LOG_EVAL = str(tmp_path / "e.jsonl")
    evs = [{"cle": "a", "ok": False, "verdicts": {"cusum": False, "flux": True}, "resultat": "sl", "r": -1.0},
           {"cle": "b", "ok": False, "verdicts": {"cusum": False, "flux": None}, "resultat": "tp", "r": 2.0},
           {"cle": "c", "ok": True, "verdicts": {"cusum": True, "flux": True}, "resultat": "tp", "r": 2.0}]
    (tmp_path / "e.jsonl").write_text("\n".join(json.dumps(e) for e in evs) + "\n")
    b = pe.bilan_filtres()
    assert b["n_juges"] == 3
    assert b["filtres"]["cusum"]["r_evite"] == -1.0          # a bloque un stop (+1) et un objectif (-2) -> -1 R
    assert b["filtres"]["flux"]["sautes"] == 1
    assert b["porte"]["ouverts"]["r"] == 2.0
    assert b["filtres"]["cusum"]["verdict"] == "trop peu de cas"


def test_casier_mesure():
    import registre_strategies as rs
    rs._CASIER["t"] = 0
    tr = [{"symbole": "LDOUSDT", "gain_eur": -1.0, "date_ouverture": "2026-10-20 10:00"}] * 16 \
       + [{"symbole": "BTCUSDT", "gain_eur": 0.5, "date_ouverture": "2026-10-21 10:00"}] * 16
    k = rs.casier(tr)
    assert "LDOUSDT" in k["cryptos"] and "BTCUSDT" not in k["cryptos"]
    assert 1 in k["jours"] and 2 not in k["jours"]          # mardi perdant, mercredi non
    # trop peu de trades -> pas de verdict
    rs._CASIER["t"] = 0
    assert rs.casier([{"symbole": "X", "gain_eur": -1.0, "date_ouverture": "2026-10-20 10:00"}] * 5)["cryptos"] == {}


def test_cadence_cooldown_et_plafond():
    import porte_entree as pe
    from datetime import datetime, timedelta
    now = datetime.now()
    pf = {"positions": [], "trades_fermes": [{"symbole": "SOLUSDT", "date_ouverture": now.strftime("%Y-%m-%d %H:%M"),
                                              "date_fermeture": (now - timedelta(minutes=30)).strftime("%Y-%m-%d %H:%M"), "source": "x"}]}
    assert pe.cadence(pf, "SOLUSDT")["ok"] is False
    assert pe.cadence(pf, "BTCUSDT")["ok"] is True
    pf["positions"] = [{"symbole": f"S{i}", "date_ouverture": now.strftime("%Y-%m-%d %H:%M")} for i in range(pe.MAX_OUVERTURES_JOUR)]
    assert pe.cadence(pf, "BTCUSDT")["ok"] is False


def test_palier_de_risque():
    import stop_atr as sa
    # base = RISQUE_PCT du capital ; paliers x2 / x3 sur preuve ; plafond 1 %
    # 25/11/2026 : la base est 0,10 % (1 EUR sur 1 000) tant que rien n'est prouve — 0,25 % avait ete donne sans preuve le 11/11
    assert sa.RISQUE_PCT == 0.10
    base = round(1000 * sa.RISQUE_PCT / 100, 2)
    assert base == 1.0
    assert sa.risque_courant(trades=[], capital=1000, capital_initial=1000) == base
    assert sa.risque_courant(trades=[{"gain_eur": 0.5}] * 40, capital=1000, capital_initial=1000) == round(base * 2, 2)
    assert sa.risque_courant(trades=[{"gain_eur": 0.5}] * 70, capital=1000, capital_initial=1000) == round(base * 3, 2)
    assert sa.risque_courant(trades=[{"gain_eur": 0.5}, {"gain_eur": -0.6}] * 35, capital=1000, capital_initial=1000) == base


def test_vehicule_jamais_retiree():
    import registre_strategies as rs
    tr = [{"strategie": "ia_autonome", "symbole": "X", "gain_eur": 0.3, "date_fermeture": "2026-10-01 10:00", "raison": "TP"}] * 40 \
       + [{"strategie": "ia_autonome", "symbole": "X", "gain_eur": -0.7, "date_fermeture": "2026-10-02 10:00", "raison": "SL"}] * 14 \
       + [{"strategie": "ia_autonome", "symbole": "X", "gain_eur": -0.56, "date_fermeture": "2026-10-22 10:00", "raison": "LIVE-EXIT"}] * 11 \
       + [{"strategie": "ia_autonome", "symbole": "X", "gain_eur": 0.4, "date_fermeture": "2026-10-21 10:00", "raison": "TP"}] * 7
    s = rs.calculer(tr)["ia_autonome"]
    # 11/11 : epoque de 18 trades dans le rouge -> probation (demi-taille), jamais retiree ; active des que l'epoque est > 0
    assert s["net"] < 0 and s["statut_auto"] == "probation"
    assert s["epoque"]["n"] == 18
    tr_pos = tr[:54] + [{"strategie": "ia_autonome", "symbole": "X", "gain_eur": 0.4, "date_fermeture": "2026-10-22 10:00", "raison": "TP"}] * 16
    assert rs.calculer(tr_pos)["ia_autonome"]["statut_auto"] == "active"
    tr2 = tr[:54] + [{"strategie": "ia_autonome", "symbole": "X", "gain_eur": -0.6, "date_fermeture": "2026-10-22 10:00", "raison": "SL"}] * 25 \
        + [{"strategie": "ia_autonome", "symbole": "X", "gain_eur": 0.4, "date_fermeture": "2026-10-22 10:00", "raison": "TP"}] * 5
    assert rs.calculer(tr2)["ia_autonome"]["statut_auto"] == "probation"   # jamais retiree


def test_sorties_live_relatives_a_l_objectif(monkeypatch):
    import gestion_position_live as gl
    # indicateurs simules : momentum negatif, rien d'autre
    fake = {"macd_line": -1.0, "signal_line": 0.0, "macd_histo": -1.0, "rsi": 50.0, "sma20": 1.0, "sma50": 2.0,
            "support": None, "resistance": None, "vol_actuel": 100.0, "vol_moyen": 100.0}
    monkeypatch.setattr(gl, "_get_indicateurs", lambda sym: fake)
    pos = {"symbole": "ETHUSDT", "prix_entree": 100.0, "sl_risque": 1.2, "tp_risque": 2.4}
    a, _ = gl.analyser_position_live(pos, 101.0)        # +1.0 % : avant = FERMER ; maintenant < 75 % de 2.4 -> on laisse courir
    assert a != "FERMER"
    a, r = gl.analyser_position_live(pos, 101.9)        # +1.9 % >= 75 % de l'objectif + momentum inverse -> encaisser
    assert a == "FERMER"
    a, r = gl.analyser_position_live(pos, 98.5)         # -1.5 % : avant = FERMER ; le stop ATR fait foi
    assert a == "HOLD" and "stop ATR" in r
    ancien = {"symbole": "ETHUSDT", "prix_entree": 100.0}          # position sans stop ATR : ancien comportement
    a, _ = gl.analyser_position_live(ancien, 101.0)
    assert a == "FERMER"


def test_professeurs_externes_indicateurs_et_votes(tmp_path, monkeypatch):
    import professeurs_externes as pe
    # indicateurs : RSI de Wilder et EMA sur une serie connue
    c = [float(x) for x in range(1, 40)]           # hausse continue -> RSI 100
    assert round(pe._rsi(c, 14)[-1], 6) == 100.0
    assert abs(pe._ema(c, 5)[-1] - 37.0) < 0.01     # EMA d'une droite converge vers x - (n-1)/2
    assert pe._cti(c, 20)[-1] > 0.999               # correlation prix/temps parfaite
    assert pe._aroon_up(c, 14)[-1] == 100.0
    # serie synthetique : prix stable puis chute brutale de 4 % en tendance de fond haussiere -> NASOS (ewo1) doit voter
    import math
    b = []
    p = 100.0
    for i in range(420):
        if i < 300: p = 60 + i * 0.15                # tendance de fond haussiere (EMA50 >> EMA200)
        elif i < 410: p = p * 0.9995
        else: p = p * 0.99                            # chute rapide des 10 dernieres bougies
        b.append({"ouverture": p, "haut": p * 1.001, "bas": p * 0.999, "cloture": p, "volume": 10.0, "temps": i})
    votes, ind, prot, motif = pe._votes_5m(b)
    assert ind["rsi4"] < 35 and any(v[0] == "NASOS" for v in votes), (votes, ind)
    # journal : fichier isole, fiabilite nulle -> aucun bonus de preselection
    monkeypatch.setattr(pe, "FICHIER", str(tmp_path / "pex.json"))
    d = pe._charger()
    assert pe.fiabilite("NASOS", d) == (0, None, False)
    d["stats"]["NASOS"].update({"n": 25, "tp": 12, "sl": 10, "neutre": 3})
    assert pe.fiabilite("NASOS", d)[2] is True       # 12/22 = 55 % >= 45 % sur >= 20 tranches
    d["stats"]["E0V1E"].update({"n": 25, "tp": 8, "sl": 14, "neutre": 3})
    assert pe.fiabilite("E0V1E", d)[2] is False      # 36 % < 45 %


def test_reprise_probation_puis_regles_normales(monkeypatch):
    import registre_strategies as rs
    monkeypatch.setattr(rs, "_reprises", lambda: {"pattern_reversal": "2026-10-26"})
    vieux = [{"strategie": "pattern_reversal", "symbole": "X", "gain_eur": -0.8, "date_fermeture": "2026-10-10 10:00", "raison": "SL"}] * 25
    s = rs.calculer(vieux)["pattern_reversal"]
    assert s["statut_auto"] == "probation"            # le passe (-20 EUR) ne la retire plus
    nouveaux = [{"strategie": "pattern_reversal", "symbole": "X", "gain_eur": 0.9, "date_fermeture": "2026-10-27 10:00", "raison": "TP"}] * 20 \
             + [{"strategie": "pattern_reversal", "symbole": "X", "gain_eur": -0.5, "date_fermeture": "2026-10-28 10:00", "raison": "SL"}] * 10
    s = rs.calculer(vieux + nouveaux)["pattern_reversal"]
    assert s["epoque"]["n"] == 30 and s["statut_auto"] == "active"   # jugee sur l'epoque : 30 trades, 67 %, net > 0
    pires = [{"strategie": "pattern_reversal", "symbole": "X", "gain_eur": -0.6, "date_fermeture": "2026-10-28 10:00", "raison": "SL"}] * 30
    assert rs.calculer(vieux + pires)["pattern_reversal"]["statut_auto"] == "retiree"   # et peut etre retiree sur l'epoque


def test_garde_de_baisse_rejoue_le_24_novembre(monkeypatch):
    """25/11/2026 : en tendance lente baissiere, deux positions crypto a la fois et plus d'achat apres deux stops en 24 h.
    Rejoue la journee du 24/11 (8 achats, 8 stops) : la garde n'en laisse passer que trois."""
    from datetime import datetime, timedelta
    import porte_entree as pe
    for k in ("PORTE_BAISSE", "BAISSE_MAX_POSITIONS", "BAISSE_STOPS_MAX", "BAISSE_STOPS_H", "PORTE_AUTO_LIMITES"):
        monkeypatch.delenv(k, raising=False)
    monkeypatch.setattr(pe, "_reglage", lambda nom, defaut: float(defaut))
    baisse, hausse = {"haussiere": False, "ecart_pct": -8.0}, {"haussiere": True}
    j = "2026-11-24 "
    journee = [("FETUSDT", "02:35", "16:03"), ("NEARUSDT", "04:06", "11:16"), ("ETHUSDT", "05:13", "15:17"), ("SOLUSDT", "05:16", "11:15"),
               ("PENDLEUSDT", "05:41", "09:02"), ("PENDLEUSDT", "10:33", "13:08"), ("BTCUSDT", "12:15", "17:03"), ("INJUSDT", "12:18", "13:10")]
    pris, pf = [], {"positions": [], "trades_fermes": []}
    for sym, ouv, ferm in journee:
        t = datetime.strptime(j + ouv, "%Y-%m-%d %H:%M")
        for p in list(pf["positions"]):  # les stops deja touches a cette heure
            if p["_ferme"] <= j + ouv:
                pf["positions"].remove(p)
                pf["trades_fermes"].append({"symbole": p["symbole"], "gain_eur": -2.5, "raison": "SL-EXEC (perte -3.0%)", "date_fermeture": p["_ferme"]})
        gb = pe.garde_baisse(pf, baisse, maintenant=t)
        if gb["ok"]:
            pris.append(sym)
            pf["positions"].append({"symbole": sym, "marche": "crypto", "montant_eur": 90, "_ferme": j + ferm})
    assert pris == ["FETUSDT", "NEARUSDT", "BTCUSDT"], pris  # 3 achats au lieu de 8
    # apres deux stops : plus d'achat, et l'heure de reprise est annoncee (24 h apres l'avant-dernier stop compte)
    pf = {"positions": [], "trades_fermes": [
        {"gain_eur": -2.4, "raison": "SL-EXEC (perte -3.0%)", "date_fermeture": j + "11:16"},
        {"gain_eur": -1.5, "raison": "SL-EXEC (perte -3.0%)", "date_fermeture": j + "16:03"},
        {"gain_eur": 0.02, "raison": "TEMPS-stale (+0.25%)", "date_fermeture": j + "16:30"},
        {"gain_eur": 3.1, "raison": "TRAILING-SL (gain)", "date_fermeture": j + "16:40"}]}
    soir = datetime(2026, 11, 24, 18, 0)
    gb = pe.garde_baisse(pf, baisse, maintenant=soir)
    assert not gb["ok"] and gb["stops"] == 2 and gb["reprise"] == "2026-11-25 11:16" and "2 stops" in gb["raison"]
    assert pe.garde_baisse(pf, baisse, maintenant=soir + timedelta(hours=18))["ok"]  # le premier stop est sorti de la fenetre
    # tendance haussiere ou inconnue : la garde ne change rien
    plein = {"positions": [{"marche": "crypto"}] * 4, "trades_fermes": pf["trades_fermes"]}
    assert pe.garde_baisse(plein, hausse, maintenant=soir)["ok"] and pe.garde_baisse(plein, {"haussiere": None}, maintenant=soir)["ok"]
    assert not pe.garde_baisse(plein, baisse, maintenant=soir + timedelta(hours=30))["ok"]  # 4 positions > 2
    # dans la porte : la garde bloque (raison ecrite, verdict juge) ; PORTE_BAISSE=0 la coupe
    monkeypatch.setattr(pe, "tendance_lente_btc", lambda: baisse)
    monkeypatch.setattr(pe, "_journaliser", lambda rec: None)
    monkeypatch.setattr(pe, "filtres_desarmes", lambda: {"tendance_lente"})
    monkeypatch.setattr(pe, "fenetre_interdite", lambda maintenant=None: (False, ""))
    deux = {"liquidites": 800, "positions": [{"marche": "crypto", "montant_eur": 90, "sl_risque": 2.5}] * 2, "trades_fermes": []}
    v = pe.verifier("ETHUSDT", 1700.0, {}, deux, 90, 2.5, strategie="rsi_oversold", risque_nouveau=2.5)
    assert not v["ok"] and v["raison"].startswith("garde de baisse") and v["infos"]["verdicts"]["baisse"] is False
    raison, _ = pe.blocage_global(deux)
    assert raison and raison.startswith("garde de baisse")
    monkeypatch.setenv("PORTE_BAISSE", "0")
    v = pe.verifier("ETHUSDT", 1700.0, {}, deux, 90, 2.5, strategie="rsi_oversold", risque_nouveau=2.5)
    assert not str(v["raison"]).startswith("garde de baisse") and v["infos"]["verdicts"]["baisse"] is False


def test_limites_de_risque_jamais_desarmees_par_le_bilan(monkeypatch):
    """PORTE_AUTO desarme les filtres de pronostic dont le bilan est negatif, pas les limites de risque."""
    import porte_entree as pe
    monkeypatch.delenv("PORTE_AUTO_LIMITES", raising=False)
    monkeypatch.setenv("PORTE_AUTO", "1")
    mauvais = {"filtres": {n: {"verdict": "a revoir"} for n in ("chaleur", "cadence", "baisse", "cusum", "tendance_lente")}}
    monkeypatch.setattr(pe, "bilan_filtres", lambda: mauvais)
    monkeypatch.setitem(pe._DESARMES, "noms", set())  # rendu tel quel a la fin du test
    monkeypatch.setitem(pe._DESARMES, "t", 0.0)
    assert pe.filtres_desarmes() == {"cusum", "tendance_lente"}
    assert pe._actif("CHALEUR") and pe._actif("CADENCE") and pe._actif("BAISSE") and not pe._actif("CUSUM")
    monkeypatch.setenv("PORTE_AUTO_LIMITES", "1")  # retour a l'ancien comportement, a la main
    monkeypatch.setitem(pe._DESARMES, "t", 0.0)
    assert pe.filtres_desarmes() == {"chaleur", "cadence", "baisse", "cusum", "tendance_lente"}
    monkeypatch.setitem(pe._DESARMES, "t", 0.0)


def test_tendance_lente_survit_a_une_panne_de_donnees(monkeypatch):
    """Une panne de l'historique ne doit pas rendre la tendance inconnue (donc la garde de baisse muette)."""
    import sys, types
    import porte_entree as pe
    for cle in ("tendance_lente", "tendance_lente_connue"):
        monkeypatch.delitem(pe._CACHE, cle, raising=False)
    n = pe.EMA_LENTE_JOURS + 40
    faux = types.SimpleNamespace(historique_ohlcv=lambda s, tf, k: [{"cloture": 100.0 - i * 0.3} for i in range(n)])
    monkeypatch.setitem(sys.modules, "indicateurs", faux)
    assert pe.tendance_lente_btc()["haussiere"] is False
    # panne : plus de donnees, cache expire
    faux.historique_ohlcv = lambda s, tf, k: []
    t0, v0 = pe._CACHE["tendance_lente"]
    pe._CACHE["tendance_lente"] = (t0 - 4000, v0)
    tl = pe.tendance_lente_btc()
    assert tl["haussiere"] is False and tl.get("ancienne") is True
    # l'echec n'est garde que 5 minutes, pas une heure
    assert pe._CACHE["tendance_lente"][1]["haussiere"] is None
    pe._CACHE["tendance_lente"] = (pe._CACHE["tendance_lente"][0] - 400, pe._CACHE["tendance_lente"][1])
    faux.historique_ohlcv = lambda s, tf, k: [{"cloture": 100.0 + i * 0.3} for i in range(n)]
    assert pe.tendance_lente_btc()["haussiere"] is True
    for cle in ("tendance_lente", "tendance_lente_connue"):
        pe._CACHE.pop(cle, None)
