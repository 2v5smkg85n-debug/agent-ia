"""Tests hors ligne du 11/11/2026 : entonnoir (vetos mesures), risque en % du capital par strategie,
pret_pour_le_reel, negociable Revolut X, classification des erreurs par famille."""
import json
import os
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


# ------------------------------------------------------------------ entonnoir
def _entonnoir_isole(tmp_path):
    import entonnoir as en
    en.LOG = str(tmp_path / "log.jsonl")
    en.LOG_EVAL = str(tmp_path / "eval.jsonl")
    en._DEDUP.clear(); en._ETAT.clear(); en._BILAN["t"] = 0.0; en._BILAN["v"] = None
    return en


def _eval(en, couche, resultats, armee=True):
    with open(en.LOG_EVAL, "a") as f:
        for i, r in enumerate(resultats):
            f.write(json.dumps({"cle": f"{couche}|X|s|{i}", "couche": couche, "sym": "XUSDT", "strategie": "s", "armee": armee,
                                "resultat": r, "r": 2.0 if r == "tp" else -1.0 if r == "sl" else 0.0}) + "\n")
    en._BILAN["t"] = 0.0


def test_couche_desarmee_quand_elle_coute(tmp_path):
    en = _entonnoir_isole(tmp_path)
    # 30 vetos : 25 objectifs manques, 5 stops evites -> R evite = -(25*2 - 5) = -45
    _eval(en, "trader_pro", ["tp"] * 25 + ["sl"] * 5)
    b = en.bilan()
    assert b["couches"]["trader_pro"]["r_evite"] == -45.0
    assert b["couches"]["trader_pro"]["verdict"].startswith("DESARMEE")
    assert en.armee("trader_pro") is False
    assert "trader_pro" in en.desarmees()
    # le veto laisse passer mais enregistre quand meme
    sig = {"symbole": "ETHUSDT", "strategie": "rsi_oversold", "sl_pct": 1.5}
    assert en.veto("trader_pro", sig, 2000.0, msg="") is False
    assert any(json.loads(l)["armee"] is False for l in open(en.LOG))


def test_couche_utile_reste_armee_et_rearmement(tmp_path):
    en = _entonnoir_isole(tmp_path)
    _eval(en, "cooldown", ["sl"] * 25 + ["tp"] * 5)       # R evite = -(10 - 25) = +15
    assert en.armee("cooldown") is True
    assert en.bilan()["couches"]["cooldown"]["verdict"] == "utile"
    # hysteresis : desarmee puis bilan redevenu >= 0 -> rearmee
    (tmp_path / "b").mkdir()
    en2 = _entonnoir_isole(tmp_path / "b")
    _eval(en2, "ml_filtre", ["tp"] * 30)
    assert en2.armee("ml_filtre") is False
    _eval(en2, "ml_filtre", ["sl"] * 70)                   # cumul : 60 R manques - 70 evites = +10 evite
    assert en2.armee("ml_filtre") is True


def test_protegees_et_trop_peu_de_cas(tmp_path):
    en = _entonnoir_isole(tmp_path)
    _eval(en, "liquidite_plancher", ["tp"] * 50)
    assert en.armee("liquidite_plancher") is True          # jamais desarmee
    _eval(en, "bougies", ["tp"] * 10)
    assert en.armee("bougies") is True                     # < N_MIN
    assert "trop peu" in en.bilan()["couches"]["bougies"]["verdict"]


def test_appliquer_et_dedup(tmp_path):
    en = _entonnoir_isole(tmp_path)
    a = {"symbole": "BTCUSDT", "strategie": "x", "sl_pct": 1.0}
    b = {"symbole": "ETHUSDT", "strategie": "x", "sl_pct": 1.0}
    out = en.appliquer("agents_consensus", [a, b], [a], {"BTCUSDT": 1.0, "ETHUSDT": 2.0})
    assert out == [a]
    lignes = [json.loads(l) for l in open(en.LOG)]
    assert len(lignes) == 1 and lignes[0]["sym"] == "ETHUSDT" and lignes[0]["tp_pct"] == 2.0
    # meme couple dans les 2 h : pas de doublon
    en.appliquer("agents_consensus", [a, b], [a], {"BTCUSDT": 1.0, "ETHUSDT": 2.0})
    assert len(open(en.LOG).readlines()) == 1


def test_juger_sur_bougies(tmp_path, monkeypatch):
    en = _entonnoir_isole(tmp_path)
    t0 = time.time() - 10 * 3600
    with open(en.LOG, "a") as f:
        f.write(json.dumps({"ts": t0, "date": "x", "couche": "resistance", "sym": "SOLUSDT", "strategie": "s", "prix": 100.0,
                            "sl_pct": 1.0, "tp_pct": 2.0, "armee": True}) + "\n")
    import types
    fake = types.ModuleType("indicateurs")
    fake.historique_ohlcv = lambda sym, tf, n: [{"temps": t0 + i * 3600, "ouverture": 100, "haut": 101 if i < 3 else 103, "bas": 99.5, "cloture": 100.5} for i in range(12)]
    monkeypatch.setitem(sys.modules, "indicateurs", fake)
    assert en.juger() == 1
    ev = json.loads(open(en.LOG_EVAL).readline())
    assert ev["resultat"] == "tp" and ev["r"] == 2.0


# ------------------------------------------------------------------ risque en % du capital
def test_risque_par_strategie():
    import stop_atr as sa
    tr = [{"strategie": "rsi", "gain_eur": g, "date_fermeture": "2026-11-01 00:00"} for g in [0.5, 0.7, -0.3, 0.6, 0.4, -0.2, 0.5, 0.8, 0.3, -0.4] * 4]
    assert sa.risque_courant(tr, 1000, strategie="rsi", capital_initial=1000) == 5.0            # base 2,5 x palier 2
    assert sa.risque_courant(tr[:10], 1000, strategie="rsi", capital_initial=1000) == 2.5       # < 30 trades
    assert sa.risque_courant([], 1000, strategie=None, capital_initial=1000) == 2.5
    assert sa.risque_courant(tr, 900, strategie="rsi", capital_initial=1000) == 2.25            # drawdown 10 % -> x0,5
    perd = [{"strategie": "p", "gain_eur": -0.5, "date_fermeture": "2026-11-01 00:00"}] * 40
    assert sa.risque_courant(perd, 1000, strategie="p", capital_initial=1000) == 2.5            # pas de palier sans preuve
    assert sa.risque_courant(tr * 3, 1000, strategie="rsi", capital_initial=1000) <= 10.0       # plafond 1 %
    assert sa.calculer(1.0, 1000.0, risque_eur=2.5)["montant"] > 0


# ------------------------------------------------------------------ pret pour le reel
def test_pret_pour_le_reel_conditions():
    import pret_pour_le_reel as ppr
    from datetime import datetime, timedelta
    now = datetime.now()
    trades = []
    for i in range(120):
        d = (now - timedelta(days=27 - (i % 27), hours=1)).strftime("%Y-%m-%d %H:%M")
        trades.append({"gain_eur": 0.8 if i % 3 else -0.5, "montant_eur": 100, "date_fermeture": d, "strategie": "rsi_oversold"})
    pf = {"capital_initial": 1000, "liquidites": 1000 + sum(t["gain_eur"] for t in trades), "positions": [], "trades_fermes": trades}
    e = ppr.etat(pf)
    assert e["n"] == 120 and e["conditions"][0]["ok"] and e["conditions"][1]["ok"] and e["conditions"][2]["ok"]
    assert e["conditions"][5]["ok"]   # net > 0 meme avec frais reels + glissement
    assert isinstance(ppr.rapport(pf), str) and "PRET POUR LE REEL" in ppr.rapport(pf)
    pf2 = {"capital_initial": 1000, "liquidites": 990, "positions": [], "trades_fermes": trades[:20]}
    assert ppr.etat(pf2)["pret"] is False


# ------------------------------------------------------------------ negociable Revolut X
def test_negociable_revolut_x():
    import prix_revolut as pr
    assert pr.negociable("ETHUSDT") and pr.negociable("sol")
    assert not pr.negociable("PEPEUSDT") and not pr.negociable("FLOKIUSDT") and not pr.negociable("CRVUSDT")


# ------------------------------------------------------------------ erreurs par famille
def test_classes_fermeture_famille_tendance(monkeypatch):
    import journal_erreurs as je
    ctx = {"btc_var_1h": 0.1, "rsi": 75, "dist_haut_24h": 0.1, "sl_recents_1h": 0, "heure": 14}
    pos_t = {"strategie": "donchian_breakout", "contexte": ctx, "date_ouverture": "2026-11-10 14:00", "symbole": "XUSDT"}
    pos_r = {"strategie": "rsi_oversold", "contexte": ctx, "date_ouverture": "2026-11-10 14:00", "symbole": "XUSDT"}
    monkeypatch.setattr(je, "_famille", lambda p: "tendance" if "donchian" in str(p.get("strategie")) else "retour")
    import types
    fake = types.ModuleType("indicateurs"); fake.historique_ohlcv = lambda *a, **k: []
    monkeypatch.setitem(sys.modules, "indicateurs", fake)
    assert "achat_sommet" not in je._classes_fermeture(pos_t, "SL", -1.0, 1.0)
    assert "achat_sommet" in je._classes_fermeture(pos_r, "SL", -1.0, 1.0)


def test_professeurs_veto_sans_droit_ouvrir(monkeypatch, tmp_path):
    """La couche professeurs ne fait que bloquer : avis() renvoie (False, raison) quand un professeur dit NON, et le veto
    passe par l'entonnoir (couche 'professeurs', desarmable)."""
    import professeurs_veto as pv
    import entonnoir as en
    monkeypatch.setattr(en, "LOG", str(tmp_path / "log.jsonl"))
    monkeypatch.setattr(en, "LOG_EVAL", str(tmp_path / "eval.jsonl"))
    monkeypatch.setattr(pv, "_avis_hyperliquid", lambda sym: (False, "les meilleurs d'Hyperliquid sont vendeurs partout (0 achat / 6 ventes)"))
    monkeypatch.setattr(pv, "_avis_virtuel", lambda: (False, "professeur virtuel : BTC sous EMA50 4h"))
    ok, raison = pv.avis("ETHUSDT")
    assert ok is False and "Hyperliquid" in raison and "virtuel" in raison
    sig = {"symbole": "ETHUSDT", "strategie": "donchian_breakout", "sl_pct": 3.0}
    assert en.veto("professeurs", sig, 3000.0, msg="test") is True  # armee par defaut : bloque
    monkeypatch.setenv("ENTONNOIR_PROFESSEURS", "0")
    assert en.veto("professeurs", sig, 3000.0, msg="test") is False  # desarmee a la main : laisse passer
    monkeypatch.delenv("ENTONNOIR_PROFESSEURS")
    monkeypatch.setattr(pv, "_avis_hyperliquid", lambda sym: (True, ""))
    monkeypatch.setattr(pv, "_avis_virtuel", lambda: (True, ""))
    assert pv.avis("ETHUSDT") == (True, "")
    monkeypatch.setenv("PROF_VETO", "0")
    monkeypatch.setattr(pv, "_avis_virtuel", lambda: (False, "x"))
    assert pv.avis("ETHUSDT") == (True, "")
