"""31/10 : paper_trading.json tronque en pleine ecriture -> reparation + ecriture atomique."""
import json, os, sys
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import json_sur


def _pf():
    return {"capital_initial": 1000.0, "liquidites": 912.5, "positions": [{"symbole": "ETHUSDT", "montant_eur": 80.0, "sl_pct": 1.5}],
            "trades_fermes": [{"symbole": "BTCUSDT", "date_ouverture": "2026-10-30 10:00", "date_fermeture": "2026-10-30 12:00", "montant_eur": 50.0, "gain_eur": 0.5, "raison": "TP"},
                               {"symbole": "SOLUSDT", "date_ouverture": "2026-10-31 18:00", "date_fermeture": "2026-10-31 19:56", "montant_eur": 50.0, "gain_eur": 0.03, "raison": "TEMPS-stale (+0.32%)", "signal_raison": "RSI: survente"}]}


def test_troncature_au_milieu_d_une_cle():
    txt = json.dumps(_pf(), indent=2)
    coupe = txt.index('"signal_raison": ') + len('"signal_raison": ')
    obj, methode = json_sur.reparer_texte(txt[:coupe])
    assert obj is not None and methode.startswith("tronque_repare")
    assert obj["liquidites"] == 912.5 and len(obj["positions"]) == 1
    assert len(obj["trades_fermes"]) == 1 and obj["trades_fermes"][0]["symbole"] == "BTCUSDT"


def test_troncature_au_milieu_d_une_chaine():
    txt = json.dumps(_pf(), indent=2)
    coupe = txt.index("TEMPS-sta") + 5
    obj, methode = json_sur.reparer_texte(txt[:coupe])
    assert obj is not None and obj["liquidites"] == 912.5


def test_extra_data():
    txt = json.dumps(_pf()) + json.dumps({"x": 1})[3:]
    obj, methode = json_sur.reparer_texte(txt)
    assert methode == "extra_data" and obj["liquidites"] == 912.5


def test_intact_et_irreparable():
    assert json_sur.reparer_texte(json.dumps(_pf()))[1] == "intact"
    assert json_sur.reparer_texte("   ")[0] is None
    assert json_sur.reparer_texte('{"a": "jamais fermee')[0] is None


def test_ecrire_atomique_et_lire_repare(tmp_path):
    chemin = str(tmp_path / "pf.json")
    json_sur.ecrire(chemin, _pf())
    assert json.load(open(chemin))["liquidites"] == 912.5
    assert not [f for f in os.listdir(tmp_path) if f.endswith(".tmp")]
    txt = open(chemin).read()
    open(chemin, "w").write(txt[: txt.index('"signal_raison"')])
    obj = json_sur.lire(chemin, journal=None)
    assert obj["liquidites"] == 912.5
    assert json.load(open(chemin))["liquidites"] == 912.5  # reecrit proprement
    assert [f for f in os.listdir(tmp_path) if ".corrompu." in f]
