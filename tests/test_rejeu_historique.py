"""Tests hors ligne du 27/11/2026 : rejeu historique (observation seule). Series synthetiques, aucun appel reseau.
On verifie surtout : meme jugement que le laboratoire, aucun regard vers le futur, aucun fichier du bot touche,
aucun module du bot n'importe le rejeu."""
import csv
import math
import os
import random
import subprocess
import sys

import pytest

RACINE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, RACINE)

T0 = 1577836800          # 2020-01-01 00:00 UTC


def _serie_brute(n=24 * 430, graine=7, derive=0.0):
    """Marche aleatoire horaire avec quelques pics de volume."""
    alea = random.Random(graine)
    O, H, L, C, V, prix = [], [], [], [], [], 100.0
    for i in range(n):
        o = prix
        c = o * math.exp(alea.gauss(derive, 0.006))
        h, l = max(o, c) * (1 + abs(alea.gauss(0, 0.002))), min(o, c) * (1 - abs(alea.gauss(0, 0.002)))
        O.append(o); H.append(h); L.append(l); C.append(c)
        V.append(alea.uniform(50, 150) * (4.0 if alea.random() < 0.04 else 1.0))
        prix = c
    return {"t0": T0, "O": O, "H": H, "L": L, "C": C, "V": V, "vide": [0] * n}


@pytest.fixture(scope="module")
def rejeu():
    """Module de rejeu branche sur le code du bot ; tout est remis en place a la fin pour les autres tests."""
    import indicateurs as ind
    import strategies_tendance as st
    import rejeu_historique as rh
    avant = (ind.historique_ohlcv, st._bougies, os.environ.get("REJEU_DEPUIS"))
    os.environ["REJEU_DEPUIS"] = "2020-01-01"
    rh._M.clear()
    rh._CTX.clear()
    rh._CTX[0] = (1, 0.0, 0.0, None)          # contexte BTC vide mais charge : aucun fichier lu
    s = rh.Serie(_serie_brute())
    res = rh.rejouer_crypto("TESTUSDT", serie=s, ecrire=False)
    yield rh, s, res
    ind.historique_ohlcv, st._bougies = avant[0], avant[1]
    rh._M.clear()
    rh._CTX.clear()
    if avant[2] is None:
        os.environ.pop("REJEU_DEPUIS", None)
    else:
        os.environ["REJEU_DEPUIS"] = avant[2]


def _col(rh, ligne, nom):
    return ligne[rh.COLONNES.index(nom)]


def test_le_rejeu_produit_des_trades_pour_les_strategies_du_bot(rejeu):
    rh, s, res = rejeu
    vues = {_col(rh, l, "strat") for l in res["lignes"]}
    assert {"rsi_oversold", "pattern_reversal", "volume_spike"} <= vues
    assert res["n_signaux"] > 1000 and res["n_trades"] > 500
    assert all(_col(rh, l, "res") in ("tp", "sl", "neutre", "sortie", "ecart") for l in res["lignes"])


def test_jugement_identique_au_laboratoire(rejeu):
    import laboratoire as lab
    import stop_atr as sa
    rh, s, res = rejeu
    n = 0
    for l in res["lignes"]:
        if _col(rh, l, "strat") not in rh.TECH:
            continue
        ts, sl = _col(rh, l, "ts"), _col(rh, l, "sl")
        i = (ts - s.t0) // 3600 - 1
        attendu = lab.jouer({"ts": ts, "sl_pct": sl, "prix": s.C[i]}, s.B[i + 1:i + 1 + 40], heures=int(sa.BARRIERE_H))
        assert attendu is not None
        assert attendu["resultat"] == _col(rh, l, "res")
        assert abs(attendu["r_brut"] - _col(rh, l, "r_brut")) < 1e-9
        assert abs(attendu["r"] - _col(rh, l, "r")) < 1e-9
        n += 1
    assert n > 500


def test_stop_calcule_par_le_code_du_bot(rejeu):
    import stop_atr as sa
    from datetime import datetime, timezone
    rh, s, res = rejeu
    for l in res["lignes"][:300]:
        ts = _col(rh, l, "ts")
        i = (ts - s.t0) // 3600 - 1
        assert _col(rh, l, "sl") == sa.stop_pct(sa.atr_pct(s.B[i - 15:i + 1]), maintenant=datetime.fromtimestamp(ts, timezone.utc))


def test_un_essai_par_strategie_toutes_les_24_h_plus_decalage(rejeu):
    rh, s, res = rejeu
    dernier = {}
    for l in res["lignes"]:
        st, ts = _col(rh, l, "strat"), _col(rh, l, "ts")
        if st in rh.TECH:
            if st in dernier:
                assert ts >= dernier[st] + 24 * 3600 + dernier[st] % 18000
            dernier[st] = ts


def test_aucun_regard_vers_le_futur(rejeu):
    """On change tout ce qui suit la bougie 6000 : les signaux decides avant doivent etre strictement identiques."""
    rh, s, res = rejeu
    d = _serie_brute()
    coupe = 6000
    alea = random.Random(99)
    for i in range(coupe + 1, len(d["C"])):
        f = 1.0 + alea.uniform(0.2, 0.6)
        for k in ("O", "H", "L", "C"):
            d[k][i] *= f
        d["V"][i] *= 3
    autre = rh.rejouer_crypto("TESTUSDT", serie=rh.Serie(d), ecrire=False)
    limite = s.ts(coupe)
    assert [x for x in res["signaux"] if x[0] <= limite] == [x for x in autre["signaux"] if x[0] <= limite]
    cles = ["sym", "ts", "strat", "rang", "nb", "score", "sens", "pat", "atr", "sl"] + rh.FEATURES
    idx = [rh.COLONNES.index(c) for c in cles]

    def decisions(r):
        return [[l[k] for k in idx] for l in r["lignes"] if l[1] <= limite]
    assert decisions(res) == decisions(autre)
    assert len(decisions(res)) > 200


def test_vue_4h_et_jour_comme_en_direct(rejeu):
    rh, s, res = rejeu
    i = 24 * 300 + 5                       # 05:59 : le bloc 4 h de 04:00 est en cours (2 bougies), le jour aussi
    b4 = s.h4(i, 60)
    assert len(b4) == 60 and b4[-1]["temps"] == s.B[i - 1]["temps"] and b4[-1]["cloture"] == s.C[i]
    assert b4[-1]["haut"] == max(s.H[i - 1], s.H[i]) and b4[-2]["cloture"] == s.C[i - 2]
    j = s.j1(i, 10)
    assert j[-1]["ouverture"] == s.O[24 * 300] and j[-1]["cloture"] == s.C[i] and j[-2]["cloture"] == s.C[24 * 300 - 1]
    assert s.h1(i, 200)[-1]["cloture"] == s.C[i] and len(s.h1(i, 200)) == 200
    i = 24 * 300 + 23
    assert s.j1(i, 10)[-1]["cloture"] == s.C[i] and s.j1(i, 10)[-1]["ouverture"] == s.O[24 * 300]


def test_tendance_multi_n_entre_que_sur_un_passage_a_sept_canaux(rejeu):
    import strategies_tendance as st
    rh, s, res = rejeu
    n = 0
    for l in res["lignes"]:
        if _col(rh, l, "strat") != "tendance_multi":
            continue
        k = (_col(rh, l, "ts") - s.t0) // 86400 - 1
        auj = st.score_tendance("TESTUSDT", s.D[max(0, k - 399):k + 1])
        hier = st.score_tendance("TESTUSDT", s.D[max(0, k - 400):k])
        assert auj[1] == 9 and hier[1] == 9 and auj[0] >= rh.MULTI_ENTREE > hier[0]
        n += 1
    assert n >= 3


def test_entrees_de_tendance_decidees_par_le_code_du_bot(rejeu):
    import strategies_tendance as st
    rh, s, res = rejeu
    n = 0
    for l in res["lignes"]:
        nom, ts = _col(rh, l, "strat"), _col(rh, l, "ts")
        i = (ts - s.t0) // 3600 - 1
        if nom == "donchian_breakout":
            assert i % 4 == 3 and st.donchian("TESTUSDT", s.h4(i, 50), s.j1(i, 220))["signal"] is True
            n += 1
        elif nom == "tsmom":
            assert i % 24 == 23 and st.tsmom("TESTUSDT", s.j1(i, 260))["signal"] is True
            n += 1
        if nom in rh.TENDANCE:
            assert _col(rh, l, "h") <= int(st.BARRIERE_H) and _col(rh, l, "res") in ("tp", "sl", "sortie", "neutre")
    assert n >= 10


def test_tendance_lente_identique_a_celle_de_la_porte(monkeypatch):
    import indicateurs as ind
    import porte_entree as pe
    import rejeu_historique as rh
    for graine, derive in ((1, 0.004), (2, -0.004), (3, 0.0)):
        alea = random.Random(graine)
        cl, p = [], 100.0
        for _ in range(124):
            p *= math.exp(alea.gauss(derive, 0.02))
            cl.append(p)
        monkeypatch.setattr(ind, "historique_ohlcv", lambda *a, **k: [{"cloture": c} for c in cl])
        pe._CACHE.clear()
        attendu = pe.tendance_lente_btc()
        h, ecart, pente = rh.tendance_lente(cl)
        assert (h, ecart, pente) == (attendu["haussiere"], attendu["ecart_pct"], attendu["pente_pct"])
    pe._CACHE.clear()
    assert rh.tendance_lente([1.0] * 50) == (None, None, None)


def test_episodes_de_baisse_fusionnes_sous_dix_jours():
    import rejeu_historique as rh
    j = 86400
    ctx = {}
    for k in range(1, 61):
        baisse = (5 <= k <= 14) or (20 <= k <= 22) or (50 <= k <= 52)       # 2e suite a 5 jours de la 1re, 3e a 27 jours
        ctx[k * j] = (0 if baisse else 1, 0.0, 0.0, None)
    eps = rh.episodes_de_baisse(ctx)
    assert eps == [(4 * j, 22 * j), (49 * j, 52 * j)]


def test_ordre_limite_servi_seulement_si_le_cours_passe_sous_le_prix():
    import rejeu_historique as rh
    n = 80
    d = {"t0": T0, "O": [100.0] * n, "H": [100.5] * n, "L": [99.9] * n, "C": [100.0] * n, "V": [1.0] * n, "vide": [0] * n}
    d["L"][11] = 99.5                                   # le cours touche 99,5 a la bougie 11
    s = rh.Serie(d)
    assert rh.jouer_limite(s, 10, 99.5, 1.0, 2.0, 24, 0.1) == (0, None)          # toucher ne suffit pas
    servi = rh.jouer_limite(s, 10, 99.6, 1.0, 2.0, 24, 0.1)
    assert servi[0] == 1 and abs(servi[1] - ((100.0 - 99.6) / 99.6 * 100 / 1.0 - 0.1)) < 0.002
    d["L"][11] = 98.0                                   # servi puis stop dans la meme bougie
    assert rh.jouer_limite(rh.Serie(d), 10, 99.6, 1.0, 2.0, 24, 0.1) == (1, -1.1)
    d["L"][11], d["H"][11] = 99.5, 103.0                # objectif dans la bougie de service : non credite
    assert rh.jouer_limite(rh.Serie(d), 10, 99.6, 1.0, 2.0, 24, 0.1)[1] < 1.0
    d["L"][14] = 90.0                                   # hors des 3 heures de validite
    d["L"][11] = 99.9
    assert rh.jouer_limite(rh.Serie(d), 10, 99.6, 1.0, 2.0, 24, 0.1) == (0, None)
    assert rh.jouer_limite(s, n - 5, 99.6, 1.0, 2.0, 24, 0.1) is None


def test_stop_et_objectif_dans_la_meme_bougie_comptent_stop():
    import rejeu_historique as rh
    n = 60
    d = {"t0": T0, "O": [100.0] * n, "H": [100.2] * n, "L": [99.8] * n, "C": [100.0] * n, "V": [1.0] * n, "vide": [0] * n}
    d["L"][12], d["H"][12] = 98.0, 103.0
    assert rh.jouer(rh.Serie(d), 10, 1.0, 2.0, 24, 0.2)[:3] == ("sl", -1.0, -1.2)
    d["L"][12] = 99.8
    assert rh.jouer(rh.Serie(d), 10, 1.0, 2.0, 24, 0.2)[:3] == ("tp", 2.0, 1.8)
    assert rh.jouer(rh.Serie(d), n - 10, 1.0, 2.0, 24, 0.2) is None


def test_bougies_continues_depuis_minuit(tmp_path, monkeypatch):
    import rejeu_historique as rh
    monkeypatch.setattr(rh, "BRUT", str(tmp_path))
    monkeypatch.setenv("REJEU_DEPUIS", "2020-01-01")
    debut = T0 + 5 * 3600                               # premiere bougie a 05:00 : la serie doit demarrer le lendemain a minuit
    with open(tmp_path / "XBTEUR_60.csv", "w", newline="") as f:
        w = csv.writer(f)
        for k in range(24 * 80):
            if k % 50 in (7, 8):                        # heures sans echange : absentes du fichier Kraken
                continue
            p = 100.0 + k * 0.01
            w.writerow([debut + 3600 * k, p, p + 1, p - 1, p + 0.5, 3.0, 12])
    d = rh.charger_bougies("BTCUSDT")
    assert d["t0"] == T0 + 86400 and d["t0"] % 86400 == 0
    assert len(d["C"]) == 24 * 80 - 19
    vides = [i for i, v in enumerate(d["vide"]) if v]
    assert vides and all(d["V"][i] == 0 and d["O"][i] == d["H"][i] == d["L"][i] == d["C"][i] == d["C"][i - 1] for i in vides)
    assert rh.fichiers_kraken("DOGEUSDT") == ["XDGEUR_60.csv"] and rh.fichiers_kraken("RNDRUSDT") == ["RNDREUR_60.csv", "RENDEREUR_60.csv"]
    assert rh.charger_bougies("ETHUSDT") is None


def test_liste_des_cryptos_identique_a_celle_du_bot():
    import historique_crypto as hc
    import rejeu_historique as rh
    assert rh.CRYPTOS_DEFAUT == list(hc.CRYPTOS)


def test_statistiques_et_garde_fous():
    import rejeu_historique as rh
    alea = random.Random(3)
    jours = range(1000)
    bonne = {j: 0.5 + alea.gauss(0, 1) for j in jours}
    bruit = {f"b{k}": {j: alea.gauss(0, 1) for j in jours} for k in range(8)}
    p = rh.pbo(dict(bruit, bonne=bonne))
    assert p["combinaisons"] == 252 and p["pbo"] < 0.1                 # une regle vraiment meilleure reste devant
    p = rh.pbo(bruit)
    assert 0.25 < p["pbo"] < 0.75                                      # que du bruit : la meilleure du passe ne vaut rien ensuite
    assert rh.pbo({"a": {1: 1.0}}) is None
    assert rh.sharpe_degonfle(list(bonne.values()), 20, 0.01) > 0.95
    assert rh.sharpe_degonfle([alea.gauss(0, 1) for _ in range(1000)], 20, 0.01) < 0.6
    assert rh.sharpe_degonfle([1.0, 2.0], 20, 0.01) is None
    cas = [(d * 86400 + h * 3600, 0.3 + alea.gauss(0, 1)) for d in range(18250, 18250 + 1500) for h in (1, 9)]
    st, an = rh.stats(cas), rh.par_annee(cas)
    assert st["n"] == 3000 and st["jours"] == 1500 and st["bas"] > 0
    assert rh.verdict(st, an, 0.99) == "TIENT sur l'historique"
    assert rh.verdict(st, an, 0.5) == "pas de preuve"                  # sans Sharpe degonfle suffisant : pas de preuve
    assert rh.verdict(rh.stats(cas[:100]), an, 0.99) == "pas de preuve"
    perd = [(t, -abs(r)) for t, r in cas]
    assert rh.verdict(rh.stats(perd), rh.par_annee(perd), 0.0) == "PERDANTE"


def test_noms_de_strategies_lus_dans_le_code_du_bot(rejeu):
    rh, s, res = rejeu
    f = rh.moteur()["detectees"]
    assert f(["RSI: survente (28.0, seuil 35) - opportunite d'achat", "VOLUME: Volume spike baissier (x3.1 moyenne)"]) == ["rsi_oversold", "volume_spike"]
    assert f(["MACD: neutre"]) == ["technique"]
    assert rh._sens(["volume: volume spike baissier (x3.1 moyenne)"], "volume") == "B"
    assert rh._sens(["bougie: marteau (haussier)", "bougie: étoile filante (baissier)"], "bougie") == "M"
    assert rh._sens(["rsi: neutre"], "volume") == ""


def test_aucun_module_du_bot_n_importe_le_rejeu():
    for nom in os.listdir(RACINE):
        if not nom.endswith(".py") or nom.startswith("rejeu_"):
            continue
        with open(os.path.join(RACINE, nom), encoding="utf-8", errors="ignore") as f:
            src = f.read()
        assert "rejeu_historique" not in src and "rejeu_modeles" not in src, nom


def test_le_rejeu_n_ecrit_que_dans_ses_fichiers(rejeu, tmp_path, monkeypatch):
    rh, s, res = rejeu
    for nom in ("DATA", "TRADES", "SIGNAUX", "CONTEXTE", "ETAT", "BILAN_TXT", "BILAN_JSON", "MODELES_JSON"):
        monkeypatch.setattr(rh, nom, str(tmp_path / os.path.basename(getattr(rh, nom))))

    def photo():
        return {n: os.path.getmtime(os.path.join(RACINE, n)) for n in os.listdir(RACINE) if not n.startswith((".", "__"))}
    avant = photo()
    court = rh.Serie(_serie_brute(n=24 * 90, graine=5))
    r = rh.rejouer_crypto("COURTUSDT", serie=court)
    assert r["n_trades"] > 0 and os.path.exists(tmp_path / "trades" / "COURTUSDT.csv")
    texte = rh.bilan(recalculer=True)
    assert "observation seule" in texte and "ORDRES LIMITE" in texte
    assert photo() == avant


def test_interrupteur_et_reseau_coupe(tmp_path):
    code = ("import sys, urllib.request; sys.path.insert(0, %r); import rejeu_historique as rh; rh.couper_reseau()\n"
            "try:\n    urllib.request.urlopen('http://127.0.0.1:9/', timeout=2); print('OUVERT')\n"
            "except OSError as e:\n    print('COUPE' if 'reseau coupe' in str(e) else 'AUTRE ' + str(e))\n"
            "import os; os.environ['REJEU'] = '0'; print('RETOUR', rh.tout(journal=lambda *a: None))\n") % RACINE
    out = subprocess.run([sys.executable, "-c", code], capture_output=True, text=True, timeout=120, cwd=str(tmp_path)).stdout
    assert "COUPE" in out and "RETOUR 0" in out and "OUVERT" not in out


def test_modeles_meme_resultat_que_le_rejeu(rejeu):
    np = pytest.importorskip("numpy")
    import rejeu_modeles as rm
    import stop_atr as sa
    rh, s, res = rejeu
    O, H, L, C = (np.array(x) for x in (s.O, s.H, s.L, s.C))
    p = {"atr_mult": sa.ATR_MULT, "tp_ratio": sa.TP_RATIO, "barriere": sa.BARRIERE_H, "sl_max": sa.SL_MAX}
    total = 0
    for nom in ("rsi_oversold", "pattern_reversal", "volume_spike"):
        bit = 1 << rh.TECH.index(nom)
        sig = [x for x in res["signaux"] if x[1] & bit]
        ts = np.array([x[0] for x in sig], dtype=np.int64)
        atr = np.array([float("nan") if x[2] == "" else x[2] for x in sig])
        idx = (ts - s.t0) // 3600 - 1
        g = rm.choisir(np, ts, int(sa.BARRIERE_H))
        t, r = rm.issues(np, O, H, L, C, idx[g], atr[g], ts[g], p, sa.SL_MIN, sa.ATR_MULT_US / sa.ATR_MULT, sa.FRAIS_AR_PCT)
        attendu = {_col(rh, l, "ts"): _col(rh, l, "r") for l in res["lignes"] if _col(rh, l, "strat") == nom and _col(rh, l, "res") != "ecart"}
        assert {int(x) for x in t} == set(attendu)
        assert all(abs(attendu[int(a)] - float(b)) < 1e-9 for a, b in zip(t, r))
        total += len(attendu)
    assert total > 150


def test_modeles_auc_et_regression(rejeu):
    np = pytest.importorskip("numpy")
    import rejeu_modeles as rm
    assert rm.auc(np, np.array([0.1, 0.4, 0.35, 0.8]), np.array([0, 0, 1, 1])) == 0.75
    assert rm.auc(np, np.array([0.5, 0.5, 0.5, 0.5]), np.array([0, 1, 0, 1])) == 0.5
    assert rm.auc(np, np.array([0.5, 0.6]), np.array([1, 1])) is None
    gen = np.random.default_rng(0)
    X = gen.normal(size=(4000, 3)).astype(np.float32)
    X[::50, 1] = np.nan
    y = (X[:, 0] + gen.normal(scale=0.5, size=4000)) > 0
    pr = rm.logistique(np, X[:3000], y[:3000], X[3000:])
    assert rm.auc(np, pr, y[3000:]) > 0.85


def test_symboles_de_la_ligne_de_commande():
    import rejeu_historique as rh
    assert rh._symboles(["btc", "SOLUSDT", "BTC", "detail!"]) == ["BTCUSDT", "SOLUSDT"]
    assert rh._symboles([]) is None
