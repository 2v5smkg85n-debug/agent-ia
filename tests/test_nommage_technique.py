"""27/10 : un signal technique ne doit plus etre baptise macd_cross a cause de la ligne 'MACD: neutre'."""
import os, sys
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import paper_trading as pt


def test_macd_neutre_ne_capture_pas_le_nom():
    lignes = ["SMA: tendance haussiere (SMA20 > SMA50)", "RSI: survente (28.0, seuil 30) - opportunite d'achat", "MACD: neutre"]
    found = pt._strategies_detectees(lignes)
    assert found[0] == "rsi_oversold"
    assert "macd_cross" not in found


def test_macd_croisement_reel_compte():
    lignes = ["RSI: neutre (52.0)", "MACD: momentum positif (croisement haussier)"]
    assert pt._strategies_detectees(lignes) == ["macd_cross"]


def test_bougie_et_volume_detectes():
    lignes = ["MACD: neutre", "BOUGIE: marteau", "VOLUME: pic x2.5"]
    found = pt._strategies_detectees(lignes)
    assert found[:2] == ["pattern_reversal", "volume_spike"]


def test_rien_detecte_donne_technique():
    assert pt._strategies_detectees(["MACD: neutre", "RSI: neutre (50.0)"]) == ["technique"]


def test_nommer_choisit_une_strategie_autorisee(monkeypatch):
    import registre_strategies as rs
    monkeypatch.setattr(rs, "a_le_droit", lambda s: s == "volume_spike")
    monkeypatch.setattr(rs, "autorisee", lambda s, pf=None: (True, "active"))
    lignes = ["RSI: survente (25.0, seuil 30) - opportunite d'achat", "VOLUME: pic x3", "MACD: neutre"]
    assert pt._nommer_strategie_technique(lignes) == "volume_spike"
