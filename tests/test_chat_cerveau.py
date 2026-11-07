"""07/11 : le chat ne doit plus inventer -> calcul verifie injecte, decoupage Telegram, nettoyage."""
import os, sys, json
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import chat_naturel as cn


def _pf():
    return {"capital_initial": 1000.0, "liquidites": 880.0, "positions": [{"montant_eur": 120.0}],
            "trades_fermes": [{"date_fermeture": "2026-10-01 10:00", "gain_eur": 1.0}, {"date_fermeture": "2026-10-31 10:00", "gain_eur": 4.0}]}


def test_verite_10_milliards_5_ans():
    bloc = cn._verite_chiffree("10 milliards en 5ans fait moi le plan", _pf())
    assert "CALCUL VERIFIE" in bloc
    assert "HORS DE PORTEE" in bloc
    assert "multiplier par 10 000 000" in bloc
    # (1e10/1000)^(1/5) - 1 = 2 411 %/an
    assert "2 412 %/an" in bloc
    assert "+5.00 EUR nets sur 30 jours" in bloc


def test_verite_objectif_raisonnable():
    bloc = cn._verite_chiffree("je veux 1200 € dans 12 mois", _pf())
    assert "atteignable" in bloc


def test_pas_de_calcul_sans_montant_ni_duree():
    assert cn._verite_chiffree("comment va le bot ?", _pf()) == ""
    assert cn._verite_chiffree("10 milliards", _pf()) == ""


def test_nombre_depuis_texte():
    assert cn._nombre_depuis_texte("10 milliards") == 1e10
    assert cn._nombre_depuis_texte("500k€") == 5e5
    assert cn._nombre_depuis_texte("2,5 millions") == 2.5e6


def test_decoupage_telegram():
    texte = "\n\n".join("Paragraphe %d. " % i + "x" * 900 for i in range(10))
    morceaux = cn._decouper_telegram(texte)
    assert all(len(m) <= 3900 for m in morceaux)
    assert "".join(m.replace("\n", "") for m in morceaux).count("x") == 9000
    assert cn._decouper_telegram("court") == ["court"]


def test_nettoyage():
    t = cn._nettoyer_reponse("<think>blabla</think>## Titre\n**Gras** et 🚀 liste:\n- un\n- deux\n\n\n\nfin")
    assert "**" not in t and "#" not in t and "🚀" not in t and "<think>" not in t
    assert t.startswith("Titre") and "- un" not in t and "\n\n\n" not in t


def test_longueur_adaptative():
    assert cn._veut_reponse_longue("Explique moi de A jusqu'à Z")
    assert cn._veut_reponse_longue("Details moi le plan au maximum")
    assert not cn._veut_reponse_longue("ça va ?")


def test_prompt_compact_local_garde_la_question_et_le_calcul():
    import chat_naturel as cn
    ctx = "=== ETAT DU BOT ===\n" + "Capital 1005 EUR. ligne de stats\n" * 300
    msg = "10 milliards en 5ans fait moi le plan"
    verite = cn._verite_chiffree(msg, {"capital_initial": 1000, "liquidites": 1000, "positions": [], "trades_fermes": []})
    prompt = f"Tu es l'Agent Trader.\n\n{ctx}\n{verite}\n\nMessage de l'utilisateur: {msg}\n\nREGLES: termine ta phrase."
    compact = cn._prompt_compact_local(prompt, msg)
    assert len(compact) < len(prompt) / 2
    for morceau in ("CALCUL VERIFIE", "Message de l'utilisateur", "REGLES", "Capital 1005 EUR"):
        assert morceau in compact
