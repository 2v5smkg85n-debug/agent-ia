"""Tests hors ligne du 27/11/2026 : professeur TabPFN en observation seule. Aucune bibliotheque lourde : le modele est
remplace par une fonction injectee. On verifie surtout qu'il ne voit jamais le futur et qu'il ne touche a rien."""
import json
import os
import sys
from datetime import datetime, timedelta

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


def _prof(tmp_path, monkeypatch):
    import professeur_tabpfn as pt
    for nom, fichier in (("LOG_PORTE", "porte_log.jsonl"), ("EVAL_PORTE", "porte_eval.jsonl"), ("NOTES", "notes.jsonl"),
                         ("ETAT", "etat.json"), ("VERROU", "verrou.lock"), ("LIBS", "libs_absentes")):
        monkeypatch.setattr(pt, nom, str(tmp_path / fichier))
    for k in ("PROF_TABPFN", "PROF_TABPFN_N_MIN", "PROF_TABPFN_EMBARGO_H", "PROF_TABPFN_LOTS", "PROF_TABPFN_BILAN_N", "PROF_TABPFN_BILAN_JOURS"):
        monkeypatch.delenv(k, raising=False)
    monkeypatch.setenv("PROF_TABPFN", "1")
    return pt


def _ecrire(pt, jours=20, par_jour=20, doublons=False):
    """Candidats ou le flux d'ordres (tfi) decide du resultat : tfi > 0 -> objectif, sinon stop."""
    t0 = datetime(2026, 10, 1, 0, 0)
    log, ev = [], []
    for j in range(jours):
        for k in range(par_jour):
            d = (t0 + timedelta(days=j, hours=k)).strftime("%Y-%m-%d %H:%M")
            tfi = 0.4 if (j + k) % 2 else -0.4
            sym, strat = f"C{k % 5}USDT", ("rsi_oversold" if k % 2 else "donchian_breakout")
            rec = {"ok": bool(k % 3), "raison": "x", "prix": 10.0, "montant": 20, "sl_pct": 1.0, "tp_pct": 2.0,
                   "infos": {"sym": sym, "strategie": strat, "date": d, "famille": "reversion", "tfi_30m": tfi,
                             "verdicts": {"fenetres": True}, "regime": {"mode": "range", "adx": 18.0, "atr_pct": 0.5, "atr_percentile": 40},
                             "tendance_lente": {"haussiere": False, "ecart_pct": -5.0, "pente_pct": -0.2},
                             "liquidite": {"spread_pct": 0.05, "profondeur_eur": 100000}, "cadence": {"depuis_h": float("inf"), "n_jour": 1}}}
            log.append(rec)
            if doublons:
                log.append(rec)
            ev.append({"cle": f"{d}|{sym}|{strat}", "resultat": "tp" if tfi > 0 else "sl", "r": 2.0 if tfi > 0 else -1.0, "sl_pct": 1.0})
    with open(pt.LOG_PORTE, "w") as f:
        f.write("\n".join(json.dumps(r) for r in log) + "\n{ligne abimee\n")
    with open(pt.EVAL_PORTE, "w") as f:
        f.write("\n".join(json.dumps(r) for r in ev) + "\n")


def test_donnees_dedoublonnees_et_etiquetees_net_de_frais(tmp_path, monkeypatch):
    pt = _prof(tmp_path, monkeypatch)
    _ecrire(pt, jours=3, par_jour=10, doublons=True)
    d = pt.donnees()
    assert len(d) == 30                                   # les doublons de la meme heure ne comptent qu'une fois
    assert [r["ts"] for r in d] == sorted(r["ts"] for r in d)
    gagnant = next(r for r in d if r["resultat"] == "tp")
    perdant = next(r for r in d if r["resultat"] == "sl")
    assert gagnant["y"] == 1 and abs(gagnant["r"] - 1.8) < 1e-9      # 2 R - 0,2 % de frais / 1 % de stop
    assert perdant["y"] == 0 and abs(perdant["r"] + 1.2) < 1e-9
    assert gagnant["f"]["cad_depuis_h"] is None           # l'infini n'entre pas dans le tableau
    assert gagnant["f"]["adx_4h"] is None and gagnant["f"]["liq_log_profondeur"] == 5.0


def test_ne_voit_jamais_le_futur(tmp_path, monkeypatch):
    pt = _prof(tmp_path, monkeypatch)
    monkeypatch.setenv("PROF_TABPFN_N_MIN", "40")
    monkeypatch.setenv("PROF_TABPFN_LOTS", "100")
    _ecrire(pt, jours=12, par_jour=20)
    lignes = pt.donnees()
    appels = []

    def predire(Xtr, ytr, Xte):
        appels.append((len(Xtr), len(Xte)))
        return [0.9] * len(Xte), [0.5] * len(Xte), len(Xtr[0])

    n = pt.noter(verbose=False, predire=predire)
    assert n == len(lignes)
    notes = pt._notes()
    par_cle = {r["cle"]: r for r in lignes}
    notees = [x for x in notes.values() if x["p"] is not None]
    assert notees and any(x["p"] is None for x in notes.values())      # les premiers jours servent a apprendre
    for x in notees:
        jour = pt._ts(x["date"][:10] + " 00:00")
        vus = [r for r in lignes if r["ts"] <= jour - 12 * 3600]
        assert x["n_train"] == len(vus)                   # exactement les candidats dates d'au moins 12 h avant le jour note
        assert all(r["ts"] < par_cle[x["cle"]]["ts"] for r in vus)
    assert pt.noter(verbose=False, predire=predire) == 0  # une note ecrite n'est jamais recalculee
    assert len(pt._notes()) == len(lignes)


def test_bilan_et_verdicts(tmp_path, monkeypatch):
    pt = _prof(tmp_path, monkeypatch)
    monkeypatch.setenv("PROF_TABPFN_N_MIN", "40")
    monkeypatch.setenv("PROF_TABPFN_LOTS", "100")
    _ecrire(pt, jours=20, par_jour=20)
    col = pt._colonnes(pt.donnees()).index(("num", "tfi_30m", None))
    bon = lambda Xtr, ytr, Xte: ([0.9 if x[col] > 0 else 0.1 for x in Xte], [0.5] * len(Xte), len(Xtr[0]))
    pt.noter(verbose=False, predire=bon)
    b = pt.bilan()
    assert b["notes"] >= 200 and b["jours"] >= 10
    assert b["auc_tabpfn"] == 1.0 and b["auc_logit"] == 0.5 and b["contre_logit"].startswith("mieux")
    assert b["retenus"]["ic_bas"] > 0 and b["verdict"].startswith("PROUVE")
    assert "PROUVE" in pt.resume() and "ne bloque rien" in pt.resume()
    # un modele qui note au hasard n'obtient pas le verdict
    os.remove(pt.NOTES)
    hasard = lambda Xtr, ytr, Xte: ([0.5] * len(Xte), [0.5] * len(Xte), len(Xtr[0]))
    pt.noter(verbose=False, predire=hasard)
    assert pt.bilan()["verdict"].startswith("pas de preuve")
    # trop peu de recul : le verdict le dit au lieu de conclure
    monkeypatch.setenv("PROF_TABPFN_BILAN_N", "100000")
    assert pt.bilan()["verdict"].startswith("trop peu de recul")


def test_panne_ou_coupure_ne_casse_rien(tmp_path, monkeypatch):
    pt = _prof(tmp_path, monkeypatch)
    monkeypatch.setenv("PROF_TABPFN_N_MIN", "40")
    assert "aucun candidat" in pt.bilan()["verdict"] and pt.resume()          # aucun fichier : pas d'exception
    _ecrire(pt, jours=8, par_jour=20)

    def plante(Xtr, ytr, Xte):
        raise RuntimeError("modele en panne")

    pt.noter(verbose=False, predire=plante)
    assert "modele en panne" in pt.etat()["erreur"]
    assert all(x["p"] is None for x in pt._notes().values())                  # rien d'invente quand le modele plante
    monkeypatch.setenv("PROF_TABPFN", "0")
    assert pt.noter(verbose=False, predire=plante) == 0 and "COUPE" in pt.resume()


def test_sans_bibliotheque_le_bot_continue(tmp_path, monkeypatch):
    """TabPFN non installe : la notation ecrit l'erreur dans son etat et ne leve rien."""
    pt = _prof(tmp_path, monkeypatch)
    monkeypatch.setenv("PROF_TABPFN_N_MIN", "40")
    _ecrire(pt, jours=8, par_jour=20)
    monkeypatch.setattr(pt, "_moteur", lambda threads: (_ for _ in ()).throw(ImportError("No module named 'tabpfn'")))
    assert pt.noter(verbose=False) == 0
    assert "TabPFN indisponible" in pt.etat()["erreur"] and not os.path.exists(pt.NOTES)


def test_module_leger_et_jamais_importe_par_le_trading():
    """Le module n'importe aucune bibliotheque lourde au chargement, et le code qui gere les positions ne l'importe pas."""
    racine = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    src = open(os.path.join(racine, "professeur_tabpfn.py")).read()
    tete = src.split("def _moteur")[0]
    for lourd in ("import numpy", "import torch", "import tabpfn", "import sklearn", "import pandas"):
        assert lourd not in tete
    for fichier in ("paper_trading.py", "porte_entree.py", "journal_erreurs.py", "kraken_paper.py", "stop_atr.py"):
        chemin = os.path.join(racine, fichier)
        if os.path.exists(chemin):
            assert "professeur_tabpfn" not in open(chemin).read(), fichier
