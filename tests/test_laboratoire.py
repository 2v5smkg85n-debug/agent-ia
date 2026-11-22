"""Tests hors ligne du 22/11/2026 : laboratoire (trades virtuels, bilan par jour, promotion automatique) et etat de
l'entonnoir conserve au redemarrage."""
import json
import os
import sys
import time
from datetime import datetime, timedelta, timezone

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


def _labo(tmp_path, monkeypatch):
    import laboratoire as lab
    import registre_strategies as rs
    monkeypatch.setattr(lab, "LOG", str(tmp_path / "labo_log.jsonl"))
    monkeypatch.setattr(lab, "LOG_EVAL", str(tmp_path / "labo_eval.jsonl"))
    monkeypatch.setattr(lab, "ETAT", str(tmp_path / "labo_etat.json"))
    monkeypatch.setattr(rs, "FICHIER", str(tmp_path / "registre.json"))
    monkeypatch.setattr(rs, "PT_FILE", str(tmp_path / "pt.json"))
    monkeypatch.setattr(rs, "ARCHIVE_FILE", str(tmp_path / "archive.json"))
    monkeypatch.setenv("LABO", "1")
    monkeypatch.setenv("LABO_AUTO", "1")
    monkeypatch.setenv("REGISTRE_REPRISES", "")
    lab._DEDUP["src"] = None
    for k in lab._DERNIER:
        lab._DERNIER[k] = 0.0
    return lab, rs


def _bougies(t0, prix, suite):
    """suite : liste de (haut %, bas %, cloture %) par rapport a `prix`, une bougie 1h chacune a partir de t0."""
    out = []
    for i, (h, b, c) in enumerate(suite):
        out.append({"temps": t0 + i * 3600, "ouverture": prix, "haut": prix * (1 + h / 100), "bas": prix * (1 + b / 100),
                    "cloture": prix * (1 + c / 100)})
    return out


def _evals(lab, strat, rs_par_jour, debut_j=30, contexte="normal"):
    """Ecrit des jugements : rs_par_jour = liste (un element par jour) de listes de R nets."""
    now = time.time()
    with open(lab.LOG_EVAL, "a") as f:
        for j, rs in enumerate(rs_par_jour):
            ts = now - (debut_j - j) * 86400
            date = datetime.fromtimestamp(ts, timezone.utc).strftime("%Y-%m-%d %H:%M")
            for i, r in enumerate(rs):
                f.write(json.dumps({"cle": f"{strat}|S{i}|{round(ts)}|{contexte}", "ts": round(ts), "date": date, "strategie": strat,
                                    "sym": f"S{i}USDT", "contexte": contexte, "resultat": "tp" if r > 0 else "sl", "r": r}) + "\n")


# ------------------------------------------------------------------ jugement d'un trade virtuel
def test_jouer_objectif_stop_et_frais(tmp_path, monkeypatch):
    lab, _ = _labo(tmp_path, monkeypatch)
    t0 = 1_800_000_000
    rec = {"ts": t0 - 600, "prix": 100.0, "sl_pct": 2.0, "tp_pct": 4.0}
    plat = [(0.5, -0.5, 0.0)]
    # objectif touche a la 3e bougie : +2 R brut, moins les frais (0,2 % / 2 % = 0,1 R)
    v = lab.jouer(rec, _bougies(t0, 100.0, plat * 2 + [(4.2, -0.3, 3.0)] + plat * 30), heures=24)
    assert v["resultat"] == "tp" and v["r_brut"] == 2.0 and abs(v["r"] - 1.9) < 1e-9
    # stop : -1 R brut, -1,1 R net
    v = lab.jouer(rec, _bougies(t0, 100.0, plat + [(0.2, -2.1, -1.5)] + plat * 30), heures=24)
    assert v["resultat"] == "sl" and abs(v["r"] + 1.1) < 1e-9
    # stop et objectif dans la meme bougie : on compte le stop
    v = lab.jouer(rec, _bougies(t0, 100.0, [(4.5, -2.5, 0.0)] + plat * 30), heures=24)
    assert v["resultat"] == "sl"
    # ni l'un ni l'autre : variation finale / stop, frais deduits
    v = lab.jouer(rec, _bougies(t0, 100.0, plat * 23 + [(1.2, -0.2, 1.0)] + plat * 5), heures=24)
    assert v["resultat"] == "neutre" and abs(v["r"] - (0.5 - 0.1)) < 1e-9


def test_jouer_sans_regarder_le_futur_ni_juger_trop_tot(tmp_path, monkeypatch):
    lab, _ = _labo(tmp_path, monkeypatch)
    t0 = 1_800_000_000
    rec = {"ts": t0, "prix": 100.0, "sl_pct": 2.0, "tp_pct": 4.0}
    plat = [(0.5, -0.5, 0.0)]
    # la bougie deja en cours au moment du signal (elle a touche l'objectif AVANT le signal) est ignoree
    bs = [{"temps": t0 - 1800, "ouverture": 100, "haut": 110, "bas": 99, "cloture": 100}] + _bougies(t0 + 1800, 100.0, plat * 24)
    assert lab.jouer(rec, bs, heures=24)["resultat"] == "neutre"
    # pas assez de bougies apres le signal -> pas de jugement
    assert lab.jouer(rec, _bougies(t0 + 1800, 100.0, plat * 10), heures=24) is None
    # bougies en millisecondes : acceptees
    ms = [dict(b, temps=b["temps"] * 1000) for b in _bougies(t0 + 60, 100.0, [(5, -0.1, 4)] + plat * 30)]
    assert lab.jouer(rec, ms, heures=24)["resultat"] == "tp"
    # bougies qui ne parlent pas du meme prix (> 10 % d'ecart) : ecartees du bilan
    assert lab.jouer(rec, _bougies(t0 + 60, 150.0, plat * 30), heures=24)["resultat"] == "ecart"


# ------------------------------------------------------------------ observation
def test_observer_un_trade_virtuel_a_la_fois_et_survit_au_redemarrage(tmp_path, monkeypatch):
    lab, _ = _labo(tmp_path, monkeypatch)
    sigs = [{"symbole": "ETHUSDT", "strategie": "pattern_reversal", "sl_pct": 1.5, "score": 7},
            {"symbole": "BTCUSDT", "strategie": "pattern_reversal", "sl_pct": 1.5},
            {"symbole": "ETHUSDT", "strategie": "rsi_oversold", "sl_pct": 1.5}]
    prix = {"ETHUSDT": 2000.0, "BTCUSDT": 60000.0}
    assert lab.observer(sigs, prix) == 3
    assert lab.observer(sigs, prix) == 0                      # meme (strategie, crypto) : deja un trade virtuel en cours
    lab._DEDUP["src"] = None                                  # redemarrage : la memoire est relue depuis le journal
    assert lab.observer(sigs, prix) == 0
    assert lab.observer(sigs, prix, contexte="fenetre_interdite") == 3     # la fenetre interdite est mesuree a part
    assert lab.observer(sigs, prix, contexte="fenetre_interdite") == 0
    t = 1_800_000_000
    assert 24 * 3600 <= lab._libre_a(t) - t < 29 * 3600 + 1   # rejoue apres la barriere + un decalage de 0 a 5 h
    recs = [json.loads(l) for l in open(lab.LOG)]
    assert {r["strategie"] for r in recs} == {"pattern_reversal", "rsi_oversold"}
    assert recs[0]["tp_pct"] == 3.0 and recs[0]["contexte"] == "normal" and recs[0]["droit"] is False
    assert [r["contexte"] for r in recs].count("fenetre_interdite") == 3
    monkeypatch.setenv("LABO", "0")
    assert lab.observer([{"symbole": "SOLUSDT", "strategie": "x", "sl_pct": 1.0}], {"SOLUSDT": 100.0}) == 0


def test_juger_ecrit_le_resultat(tmp_path, monkeypatch):
    lab, _ = _labo(tmp_path, monkeypatch)
    t0 = round(time.time() - 30 * 3600)
    with open(lab.LOG, "w") as f:
        f.write(json.dumps({"ts": t0, "date": "2026-11-20 10:00", "strategie": "s", "sym": "ETHUSDT", "prix": 100.0, "sl_pct": 2.0,
                            "tp_pct": 4.0, "contexte": "normal"}) + "\n")
        f.write(json.dumps({"ts": round(time.time() - 3600), "date": "2026-11-21 15:00", "strategie": "s", "sym": "BTCUSDT",
                            "prix": 100.0, "sl_pct": 2.0, "tp_pct": 4.0, "contexte": "normal"}) + "\n")
    import indicateurs as ind
    monkeypatch.setattr(ind, "historique_ohlcv", lambda sym, itv, lim: _bougies(t0 + 900, 100.0, [(4.5, -0.2, 4.0)] + [(0.3, -0.3, 0)] * 30))
    assert lab.juger(force=True) == 1                         # le second est trop recent
    e = [json.loads(l) for l in open(lab.LOG_EVAL)]
    assert len(e) == 1 and e[0]["resultat"] == "tp" and e[0]["strategie"] == "s"
    assert lab.juger(force=True) == 0                         # jamais juge deux fois


# ------------------------------------------------------------------ bilan : les jours comptent, pas seulement le nombre
def test_bilan_un_seul_bon_jour_ne_prouve_rien(tmp_path, monkeypatch):
    lab, _ = _labo(tmp_path, monkeypatch)
    _evals(lab, "coup_de_chance", [[1.9] * 80])               # 80 gagnants, mais le meme jour
    _evals(lab, "reguliere", [[1.9, 1.9, -1.1, 1.9, -1.1, 1.9]] * 12)
    _evals(lab, "perdante", [[-1.1, -1.1, 1.9, -1.1, -1.1, -1.1]] * 12)
    _evals(lab, "bruit", [[1.9] * 5, [-1.1] * 7] * 6)          # gagne un jour, perd le lendemain : moyenne > 0 mais sans confiance
    b = lab.bilan()["strategies"]
    assert b["coup_de_chance"]["verdict"].startswith("trop peu de recul")
    assert b["reguliere"]["verdict"].startswith("PROUVEE") and b["reguliere"]["ic_bas"] > 0
    assert b["perdante"]["verdict"].startswith("perdante") and b["perdante"]["ic_haut"] < 0
    assert b["bruit"]["verdict"].startswith("indecise")
    assert "LABORATOIRE" in lab.rapport()


def test_fenetre_interdite_mesuree_a_part(tmp_path, monkeypatch):
    lab, _ = _labo(tmp_path, monkeypatch)
    _evals(lab, "s", [[1.9] * 6] * 12)
    _evals(lab, "s", [[-1.1] * 6] * 12, contexte="fenetre_interdite")
    b = lab.bilan()
    assert b["strategies"]["s"]["n"] == 72 and b["strategies"]["s"]["r_moyen"] == 1.9     # la fenetre ne pollue pas la strategie
    assert b["fenetre_interdite"]["n"] == 72 and b["fenetre_interdite"]["r_moyen"] == -1.1


# ------------------------------------------------------------------ promotion automatique
def test_promotion_donne_le_droit_en_probation(tmp_path, monkeypatch):
    lab, rs = _labo(tmp_path, monkeypatch)
    monkeypatch.setattr("telegram_alerte.envoyer", lambda *a, **k: None, raising=False)
    _evals(lab, "nouvelle_gagnante", [[1.9, 1.9, -1.1, 1.9, -1.1, 1.9]] * 12)
    _evals(lab, "autre_gagnante", [[1.9, 1.9, -1.1, 1.9, 1.9, 1.9]] * 12)
    _evals(lab, "perdante", [[-1.1] * 6] * 12)
    _evals(lab, "ia_autonome", [[1.9] * 6] * 12)              # a deja le droit : rien a faire
    assert rs.a_le_droit("nouvelle_gagnante") is False
    assert [c["strategie"] for c in lab.candidats()] == ["autre_gagnante", "nouvelle_gagnante"]
    faits = lab.promouvoir(force=True)
    assert [f["strategie"] for f in faits] == ["autre_gagnante"]           # une seule promotion par jour, la mieux prouvee
    assert rs.a_le_droit("autre_gagnante") is True and rs.a_le_droit("nouvelle_gagnante") is False
    assert rs.a_le_droit("perdante") is False
    assert lab.promouvoir(force=True) == []                                # quota du jour atteint
    reg = json.load(open(rs.FICHIER))
    assert reg["promotions_labo"]["autre_gagnante"]["n"] == 1
    assert any(h["vers"] == "DROIT D'OUVERTURE (laboratoire)" for h in reg["historique_statuts"])
    # aucune vraie fiche encore : fiche vide en probation (1 position, demi-risque), et les rapports la supportent
    assert rs.statut("autre_gagnante") == "probation"
    assert rs.autorisee("autre_gagnante", {"positions": [{"strategie": "autre_gagnante"}]})[0] is False
    assert "autre_gagnante" in rs.rapport() and "autre_gagnante" in rs.resume_pour_ia()
    import stop_atr as sa
    monkeypatch.setattr(sa.os.path, "dirname", lambda p: str(tmp_path))
    (tmp_path / "registre_strategies.json").write_text(json.dumps(json.load(open(rs.FICHIER))))
    base = round(1000 * sa.RISQUE_PCT / 100, 2)
    assert sa.risque_courant(trades=[], capital=1000, strategie="autre_gagnante", capital_initial=1000) == round(base * 0.5, 2)
    # son premier vrai trade remplace la fiche vide par une vraie fiche
    (tmp_path / "pt.json").write_text(json.dumps({"trades_fermes": [
        {"strategie": "autre_gagnante", "symbole": "X", "gain_eur": 0.4, "raison": "TP", "date_fermeture": datetime.now().strftime("%Y-%m-%d %H:%M")}]}))
    assert rs.mettre_a_jour()["strategies"]["autre_gagnante"]["n"] == 1 and rs.statut("autre_gagnante") == "probation"


def test_promotion_coupee_par_labo_auto(tmp_path, monkeypatch):
    lab, rs = _labo(tmp_path, monkeypatch)
    _evals(lab, "gagnante", [[1.9, 1.9, -1.1, 1.9, -1.1, 1.9]] * 12)
    monkeypatch.setenv("LABO_AUTO", "0")
    assert lab.promouvoir(force=True) == [] and rs.a_le_droit("gagnante") is False


def test_reprise_d_une_strategie_retiree_seulement_sur_preuves_posterieures(tmp_path, monkeypatch):
    lab, rs = _labo(tmp_path, monkeypatch)
    monkeypatch.setattr("telegram_alerte.envoyer", lambda *a, **k: None, raising=False)
    dernier = datetime.now() - timedelta(days=14)
    trades = [{"strategie": "pattern_reversal", "symbole": "X", "gain_eur": -0.5, "raison": "SL",
               "date_fermeture": (dernier - timedelta(days=i % 5)).strftime("%Y-%m-%d %H:%M")} for i in range(32)]
    (tmp_path / "pt.json").write_text(json.dumps({"trades_fermes": trades}))
    rs.donner_droit("pattern_reversal", True, "test")
    assert rs.statut("pattern_reversal") == "retiree" and rs.autorisee("pattern_reversal")[0] is False
    # preuves anterieures au dernier vrai trade : elles ne comptent pas
    _evals(lab, "pattern_reversal", [[1.9, 1.9, -1.1, 1.9, -1.1, 1.9]] * 12, debut_j=40)
    assert lab.candidats() == []
    # preuves posterieures : 12 jours de trades virtuels gagnants apres le retrait
    _evals(lab, "pattern_reversal", [[1.9, 1.9, -1.1, 1.9, -1.1, 1.9]] * 12, debut_j=12)
    c = lab.candidats()
    assert len(c) == 1 and c[0]["action"] == "reprise" and c[0]["stats"]["n"] == 72
    assert len(lab.promouvoir(force=True)) == 1
    assert rs.statut("pattern_reversal") == "probation" and rs.autorisee("pattern_reversal", {"positions": []})[0] is True
    assert rs._reprises()["pattern_reversal"] == datetime.now().strftime("%Y-%m-%d")
    # un statut force a la main n'est jamais touche
    rs.forcer("pattern_reversal", "retiree", "decision humaine")
    assert lab.candidats() == []


def test_plafond_de_promotions_par_strategie(tmp_path, monkeypatch):
    lab, rs = _labo(tmp_path, monkeypatch)
    _evals(lab, "gagnante", [[1.9, 1.9, -1.1, 1.9, -1.1, 1.9]] * 12)
    d = rs._charger()
    d["promotions_labo"] = {"gagnante": {"n": lab.PROMOS_MAX}}
    rs._sauver(d)
    assert lab.candidats() == []


# ------------------------------------------------------------------ entonnoir : l'etat survit au redemarrage
def test_entonnoir_etat_conserve_au_redemarrage(tmp_path):
    import entonnoir as en
    en.LOG = str(tmp_path / "log.jsonl")
    en.LOG_EVAL = str(tmp_path / "eval.jsonl")
    en._DEDUP.clear(); en._ETAT.clear(); en._BILAN["t"] = 0.0; en._BILAN["v"] = None

    def _ev(couche, resultats):
        with open(en.LOG_EVAL, "a") as f:
            for i, r in enumerate(resultats):
                f.write(json.dumps({"cle": f"{couche}|{i}|{time.time()}", "couche": couche, "sym": "X", "strategie": "s",
                                    "resultat": r, "r": 2.0 if r == "tp" else -1.0}) + "\n")
        en._BILAN["t"] = 0.0

    _ev("trader_pro", ["tp"] * 20 + ["sl"] * 10)               # R evite -30 -> desarmee
    assert en.armee("trader_pro") is False
    assert en.veto("trader_pro", {"symbole": "ETHUSDT", "strategie": "s", "sl_pct": 1.5}, 2000.0) is False   # journalise armee=False
    _ev("trader_pro", ["sl"] * 25)                              # bilan remonte a -5 : entre -10 et 0, elle reste desarmee
    assert en.armee("trader_pro") is False
    en._ETAT.clear(); en._ETAT_JOURNAL["src"] = None            # redemarrage du service
    assert en.armee("trader_pro") is False                      # avant le correctif : True (rearmee sans preuve)
    # une couche jamais desarmee repart armee, et une couche dont le bilan redevient >= 0 se rearme
    _ev("cooldown", ["tp"] * 16 + ["sl"] * 30)                  # R evite -2
    assert en.armee("cooldown") is True
    _ev("trader_pro", ["sl"] * 10)                              # bilan +5
    assert en.armee("trader_pro") is True
