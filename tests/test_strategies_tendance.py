"""Strategies de tendance (07/11/2026) : cassure Donchian, TSMOM, sorties, score, exemptions des regles."""
import os
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import strategies_tendance as st  # noqa: E402


def _bougies(clotures, volumes=None, duree_s=4 * 3600, en_cours=False):
    """Bougies synthetiques terminees (temps anciens) ; la derniere peut etre EN COURS."""
    n = len(clotures)
    fin = time.time() - (0 if en_cours else duree_s * 2)
    out = []
    for i, c in enumerate(clotures):
        t = fin - (n - 1 - i) * duree_s
        v = volumes[i] if volumes else 100.0
        out.append({"temps": t, "ouverture": c * 0.999, "haut": c * 1.005, "bas": c * 0.995, "cloture": c, "volume": v})
    return out


def _patch(monkeypatch, b4h=None, b1d=None):
    def faux(sym, intervalle, n):
        return (b4h if intervalle == "4h" else b1d) or []
    monkeypatch.setattr(st, "_bougies", faux)


def test_donchian_cassure_avec_volume_et_ema(monkeypatch):
    # 40 bougies 4h plates a 100, puis la derniere terminee casse a 110 avec volume x3 ; journalier haussier (EMA 84 sous le prix)
    c4 = [100.0] * 40 + [110.0]
    v4 = [100.0] * 40 + [300.0]
    c1d = [50.0 + i * 0.5 for i in range(220)]
    _patch(monkeypatch, _bougies(c4, v4), _bougies(c1d, duree_s=86400))
    d = st.donchian("XUSDT")
    assert d["signal"] is True
    assert d["plus_haut_20"] < 110.0 and d["ema84_ok"] is True and d["ratio_volume"] == 3.0
    assert "sortie sous" in d["raison"]


def test_donchian_sans_volume_ni_cassure(monkeypatch):
    c1d = [50.0 + i * 0.5 for i in range(220)]
    # cassure mais volume plat -> refuse (x1.0 >= 1.0 passe ; on met 0.5)
    _patch(monkeypatch, _bougies([100.0] * 40 + [110.0], [100.0] * 40 + [50.0]), _bougies(c1d, duree_s=86400))
    d = st.donchian("XUSDT")
    assert d["signal"] is False and "volume" in d["raison"]
    # pas de cassure
    _patch(monkeypatch, _bougies([100.0] * 40 + [100.2], [100.0] * 40 + [300.0]), _bougies(c1d, duree_s=86400))
    assert st.donchian("XUSDT")["signal"] is False


def test_donchian_ignore_la_bougie_en_cours(monkeypatch):
    # la cassure n'existe que sur la bougie EN COURS -> pas de signal (on attend la cloture)
    c1d = [50.0 + i * 0.5 for i in range(220)]
    _patch(monkeypatch, _bougies([100.0] * 40 + [110.0], [100.0] * 40 + [300.0], en_cours=True), _bougies(c1d, duree_s=86400))
    assert st.donchian("XUSDT")["signal"] is False


def test_donchian_refuse_sous_ema84(monkeypatch):
    c1d = [200.0 - i * 0.5 for i in range(220)]   # tendance de fond baissiere
    _patch(monkeypatch, _bougies([100.0] * 40 + [110.0], [100.0] * 40 + [300.0]), _bougies(c1d, duree_s=86400))
    d = st.donchian("XUSDT")
    assert d["signal"] is False and "EMA" in d["raison"]


def test_sortie_donchian(monkeypatch):
    _patch(monkeypatch, _bougies([100.0] * 30 + [90.0]))
    fin, why = st.sortie_donchian("XUSDT")
    assert fin is True and "plus bas" in why
    _patch(monkeypatch, _bougies([100.0] * 30 + [101.0]))
    assert st.sortie_donchian("XUSDT")[0] is False
    assert st.sortie({"strategie": "donchian_breakout", "symbole": "XUSDT"})[0] is False
    assert st.sortie({"strategie": "rsi_oversold", "symbole": "XUSDT"})[0] is False


def test_tsmom_retournement_recent(monkeypatch):
    # 230 jours : hausse lente (SMA 200 sous le prix, r90 > 0), creux il y a 3 jours puis rebond -> r20 vient de repasser > 0
    c = [100.0 + i * 0.2 for i in range(230)]
    for k in range(1, 8):          # creux : les 7 derniers jours sous le niveau d'il y a 20 jours
        c[-k] = c[-21] - 1.0
    c[-1] = c[-21] + 2.0           # dernier jour : rebond au-dessus -> r20 > 0, et r20 etait <= 0 hier
    _patch(monkeypatch, b1d=_bougies(c, duree_s=86400))
    t = st.tsmom("XUSDT")
    assert t["signal"] is True, t["raison"]
    assert t["r20_pct"] > 0 and t["r90_pct"] > 0 and t["au_dessus_sma200"] and t["retournement_recent"]


def test_tsmom_refuse_hausse_ancienne_et_sous_sma(monkeypatch):
    c = [100.0 + i * 0.5 for i in range(230)]     # hausse continue : r20 positif depuis toujours -> pas frais
    _patch(monkeypatch, b1d=_bougies(c, duree_s=86400))
    t = st.tsmom("XUSDT")
    assert t["signal"] is False and "ancienne" in t["raison"]
    c2 = [200.0 - i * 0.3 for i in range(230)]    # baisse -> r20 <= 0
    _patch(monkeypatch, b1d=_bougies(c2, duree_s=86400))
    assert st.tsmom("XUSDT")["signal"] is False
    fin, why = st.sortie_tsmom("XUSDT")
    assert fin is True and "negatif" in why


def test_score_tendance_et_bonus(monkeypatch):
    c = [100.0 + i * 0.5 for i in range(400)]
    _patch(monkeypatch, b1d=_bougies(c, duree_s=86400))
    n_h, n_t, _ = st.score_tendance("XUSDT")
    assert n_t == 9 and n_h == 9
    assert st.bonus_preselection("XUSDT")[0] == 0.5
    c2 = [300.0 - i * 0.5 for i in range(400)]
    _patch(monkeypatch, b1d=_bougies(c2, duree_s=86400))
    assert st.bonus_preselection("XUSDT")[0] == -0.5


def test_signaux_format_et_familles(monkeypatch):
    c4 = [100.0] * 40 + [110.0]
    v4 = [100.0] * 40 + [300.0]
    c1d = [50.0 + i * 0.5 for i in range(220)]
    _patch(monkeypatch, _bougies(c4, v4), _bougies(c1d, duree_s=86400))
    monkeypatch.setattr(st, "actif", lambda: True)
    sigs = st.signaux("XUSDT", 110.0, nom="X")
    assert [x["strategie"] for x in sigs] == ["donchian_breakout"]
    s0 = sigs[0]
    assert s0["source"] == "tendance" and s0["score"] == 2 and s0["prix_entree"] == 110.0 and s0["niveau_sortie"]
    monkeypatch.setattr(st, "actif", lambda: False)
    assert st.signaux("XUSDT", 110.0) == []
    assert st.est_tendance("tsmom") and st.est_tendance("donchian_breakout") and not st.est_tendance("rsi_oversold")
    assert st.est_reversion("consensus_reversion") and not st.est_reversion("tsmom")


def test_regles_exemptees_pour_la_tendance(tmp_path, monkeypatch):
    import journal_erreurs as je
    monkeypatch.setattr(je, "FICHIER", str(tmp_path / "journal.json"), raising=False)
    d = je._charger()
    d.setdefault("regles", {})["achat_sommet"] = {"active": True, "description": "sommet", "n_bloques": 0}
    d["regles"]["cascade"] = {"active": True, "description": "cascade", "n_bloques": 0}
    monkeypatch.setattr(je, "_charger", lambda: d)
    monkeypatch.setattr(je, "_sauver", lambda _d: None)
    ctx = {"rsi": 80, "sl_recents_1h": 0}
    assert je.regles_bloquent(ctx, compter=False)[0] is True
    assert je.regles_bloquent(ctx, compter=False, exemptees=("achat_sommet", "mauvaise_heure"))[0] is False
    # cascade reste appliquee meme pour la tendance
    assert je.regles_bloquent({"rsi": 80, "sl_recents_1h": 3}, compter=False, exemptees=("achat_sommet",))[0] is True
