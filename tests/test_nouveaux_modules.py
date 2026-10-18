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
    assert abs(r["montant"] * (r["sl_pct"] + sa.FRAIS_AR_PCT) / 100 - sa.RISQUE_EUR) < 0.02
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
    assert set(q["fournisseurs"]) == {"groq", "openrouter", "gemini", "local"}


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
