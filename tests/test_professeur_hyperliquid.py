"""Tests hors ligne du professeur Hyperliquid (aucun appel reseau)."""
import json
import os
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import professeur_hyperliquid as hl  # noqa: E402

P = {"n_traders": 3, "n_profils": 3, "capital_min": 250_000.0, "roi_mois_min": 0.05, "roi_mois_max": 3.0,
     "rotation_max": 60.0, "detention_min_h": 1.0, "rafraichir_cohorte_s": 1, "rafraichir_positions_s": 1}


def ligne(adr, cap, sem, mois, total, vlm_mois=None, vlm_sem=1.0):
    vm = vlm_mois if vlm_mois is not None else cap * 5
    return {"ethAddress": adr, "accountValue": str(cap), "displayName": None, "prize": 0,
            "windowPerformances": [["day", {"pnl": "0", "roi": "0", "vlm": "0"}],
                                   ["week", {"pnl": str(sem * cap), "roi": str(sem), "vlm": str(vlm_sem * cap)}],
                                   ["month", {"pnl": str(mois * cap), "roi": str(mois), "vlm": str(vm)}],
                                   ["allTime", {"pnl": str(total * cap), "roi": str(total), "vlm": str(vm * 10)}]]}


def test_coin_de():
    assert hl.coin_de("BTCUSDT") == "BTC"
    assert hl.coin_de("RNDRUSDT") == "RENDER"
    assert hl.coin_de("ETHEUR") == "ETH"
    assert hl.coin_de("USDT") is None


def test_filtres_les_meilleurs():
    bon = hl.compacter(ligne("0xa", 1e6, 0.1, 0.5, 1.0))
    assert hl.passe_filtres(bon, P)
    assert not hl.passe_filtres(hl.compacter(ligne("0xb", 100_000, 0.1, 0.5, 1.0)), P)       # trop petit
    assert not hl.passe_filtres(hl.compacter(ligne("0xc", 1e6, -0.1, 0.5, 1.0)), P)           # perd cette semaine
    assert not hl.passe_filtres(hl.compacter(ligne("0xd", 1e6, 0.1, 4.0, 1.0)), P)            # +400 % le mois : loterie
    assert not hl.passe_filtres(hl.compacter(ligne("0xe", 1e6, 0.1, 0.5, 1.0, vlm_mois=1e6 * 500)), P)  # teneur de marche
    assert not hl.passe_filtres(hl.compacter(ligne("0xf", 1e6, 0.1, 0.5, -0.2)), P)           # perdant depuis toujours


def test_selection_et_flux():
    lignes = [ligne("0x1", 1e6, 0.1, 0.5, 1.0), ligne("0x2", 2e6, 0.2, 1.5, 3.0), ligne("0x3", 5e5, 0.05, 0.2, 0.1),
              ligne("0x4", 9e5, 0.3, 0.9, 0.5), ligne("0xmm", 9e7, 0.1, 0.3, 0.2, vlm_mois=4e10)]
    txt = json.dumps({"leaderboardRows": lignes})
    cohorte, lus, filtres = hl.selectionner_cohorte(hl.iterer_classement(txt), P)
    assert lus == 5 and filtres == 4 and len(cohorte) == 3
    assert cohorte[0]["adresse"] == "0x2" and cohorte[0]["rang"] == 1
    assert all("0xmm" != c["adresse"] for c in cohorte)
    assert 0 < cohorte[0]["note"] <= 1.0


def _pos(adr, coin, taille, valeur, lev=10.0):
    return {adr: {"capital": 1e6, "positions": {coin: {"taille": taille, "valeur": valeur, "levier": lev, "entree": 1.0, "pnl": 0.0}}}}


def test_agreger_et_votes():
    positions = {}
    for i in range(4):
        positions.update(_pos(f"0xl{i}", "BTC", 1.0, 1e6))
    positions.update(_pos("0xs0", "BTC", -1.0, 5e5))
    positions.update(_pos("0xscalp", "BTC", -1.0, 9e6))          # scalpeur : doit etre ignore
    agg = hl.agreger(positions, {"BTC"}, exclus={"0xscalp"})
    assert agg["BTC"]["n_long"] == 4 and agg["BTC"]["n_short"] == 1 and agg["BTC"]["biais_long"] > 0.85
    votes = hl.votes_depuis(agg, [], {"BTC": "BTCUSDT"})
    assert votes[0][:3] == ("BTCUSDT", "achat", "biais_long")
    # entree fraiche d'un des meilleurs -> tag entree_longue prioritaire
    votes = hl.votes_depuis(agg, [("0xl0", "BTC", "ouvre_long")], {"BTC": "BTCUSDT"})
    assert votes[0][2] == "entree_longue"
    # biais court
    agg2 = hl.agreger({**_pos("0xa", "ETH", -1, 3e6), **_pos("0xb", "ETH", -1, 2e6), **_pos("0xc", "ETH", -1, 1e6), **_pos("0xd", "ETH", 1, 1e5)}, {"ETH"})
    votes = hl.votes_depuis(agg2, [], {"ETH": "ETHUSDT"})
    assert votes[0][1:3] == ("vente", "biais_short")
    # partage -> neutre
    agg3 = hl.agreger({**_pos("0xa", "SOL", -1, 1e6), **_pos("0xb", "SOL", 1, 1e6)}, {"SOL"})
    assert hl.votes_depuis(agg3, [], {"SOL": "SOLUSDT"})[0][1] == "neutre"


def test_mouvements():
    avant = {**_pos("0xa", "BTC", 1.0, 1e6), **_pos("0xb", "ETH", -2.0, 1e6)}
    apres = {**_pos("0xa", "BTC", 1.5, 1.5e6), **_pos("0xb", "ETH", 0.0, 0.0), **_pos("0xc", "SOL", -3.0, 1e6)}
    apres["0xb"]["positions"] = {}
    mv = hl.mouvements(avant, apres)
    assert ("0xa", "BTC", "renforce_long") in mv
    assert ("0xb", "ETH", "ferme_short") in mv
    assert ("0xc", "SOL", "ouvre_short") in mv


def test_profil_depuis_fills_et_scalpeurs():
    t0 = 1_700_000_000_000
    h = 3_600_000
    fills = [
        {"coin": "BTC", "px": "100", "sz": "1", "side": "B", "time": t0, "dir": "Open Long", "closedPnl": "0", "fee": "1"},
        {"coin": "BTC", "px": "110", "sz": "1", "side": "A", "time": t0 + 5 * h, "dir": "Close Long", "closedPnl": "10", "fee": "1"},
        {"coin": "ETH", "px": "10", "sz": "10", "side": "A", "time": t0 + 6 * h, "dir": "Open Short", "closedPnl": "0", "fee": "1"},
        {"coin": "ETH", "px": "11", "sz": "10", "side": "B", "time": t0 + 9 * h, "dir": "Close Short", "closedPnl": "-10", "fee": "1"},
    ]
    bougies = {"BTC": [{"temps": (t0 - (30 - i) * h) / 1000, "cloture": 90 + i * 0.5} for i in range(31)]}
    pr = hl.profil_depuis_fills(fills, bougies, levier=5.0)
    assert pr["n_ordres"] == 4 and pr["part_long"] == 50 and pr["pct_clotures_gagnantes"] == 50
    assert pr["detention_mediane_h"] == 4.0 and pr["levier_moyen"] == 5.0
    assert pr["style_entree"] is None            # moins de 5 entrees mesurees : on n'affirme rien
    profils = {"0xa": {**pr, "detention_mediane_h": 0.3}, "0xb": pr}
    assert hl.scalpeurs(profils, 1.0) == {"0xa"}
    lecon = hl.lecon_cohorte(profils, 1.0)
    assert "1 profils mesures (1 scalpeurs" in lecon and "detention mediane 4 h" in lecon


def test_fiabilite_et_bonus(tmp_path, monkeypatch):
    monkeypatch.setattr(hl, "FICHIER", str(tmp_path / "hl.json"))
    d = hl._charger()
    d["votes_du_moment"] = [{"sym": "BTCUSDT", "sens": "achat", "tag": "biais_long", "detail": ""},
                            {"sym": "ETHUSDT", "sens": "vente", "tag": "biais_short", "detail": ""}]
    d["stats"] = {"n": 10, "tp": 6, "sl": 4, "neutre": 0, "rendement_cumule": 0.0}
    hl._sauver(d)
    assert hl.bonus_preselection("BTCUSDT") == (0.0, "")        # pas encore 20 votes tranches : seulement lu
    d["stats"] = {"n": 25, "tp": 14, "sl": 11, "neutre": 0, "rendement_cumule": 0.0}
    hl._sauver(d)
    assert hl.fiabilite()[2] is True
    assert hl.bonus_preselection("BTCUSDT")[0] == 0.5
    assert hl.bonus_preselection("ETHUSDT")[0] == -0.5
    assert hl.bonus_preselection("SOLUSDT") == (0.0, "")
    monkeypatch.setenv("PROF_HYPERLIQUID", "0")
    monkeypatch.setattr(hl, "_lire", lambda nom, defaut: os.environ.get(nom, defaut))
    assert hl.bonus_preselection("BTCUSDT") == (0.0, "")
    assert hl.contexte_pour_cerveau(["BTCUSDT"]) == ""


def test_evaluer_votes_dans_le_sens(tmp_path, monkeypatch):
    monkeypatch.setattr(hl, "FICHIER", str(tmp_path / "hl.json"))
    now = time.time()
    d = hl._charger()
    d["votes"] = [{"ts": now - 7200, "date": "x", "sym": "BTCUSDT", "prof": "HYPERLIQUID", "sens": "vente", "tag": "biais_short",
                   "detail": "", "prix": 100.0, "sl_pct": 1.0, "tp_pct": 2.0, "resultat": None, "rendement": None, "heure_utc": 0},
                  {"ts": now - 7200, "date": "x", "sym": "ETHUSDT", "prof": "HYPERLIQUID", "sens": "achat", "tag": "biais_long",
                   "detail": "", "prix": 100.0, "sl_pct": 1.0, "tp_pct": 2.0, "resultat": None, "rendement": None, "heure_utc": 0}]
    hl._sauver(d)

    class Ind:
        @staticmethod
        def historique_ohlcv(sym, iv, n):
            # le prix baisse de 2,5 % : le vote de VENTE touche son objectif, le vote d'ACHAT touche son stop
            return [{"temps": now - 3600, "haut": 100.2, "bas": 97.5, "cloture": 97.6}]
    monkeypatch.setitem(sys.modules, "indicateurs", Ind)
    assert hl.evaluer_votes() == 2
    d = hl._charger()
    res = {v["sym"]: v["resultat"] for v in d["votes"]}
    assert res == {"BTCUSDT": "tp", "ETHUSDT": "sl"}
    assert d["stats"]["tp"] == 1 and d["stats"]["sl"] == 1
