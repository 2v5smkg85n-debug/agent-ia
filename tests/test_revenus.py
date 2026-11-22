# -*- coding: utf-8 -*-
"""Tests des outils de revenus hors trading (aucun réseau, aucun Telegram)."""
import os
import sys
import tempfile

import pytest

ICI = os.path.dirname(os.path.abspath(__file__))
RACINE = os.path.dirname(ICI)
sys.path.insert(0, os.path.join(RACINE, "revenus"))
sys.path.insert(0, os.path.join(RACINE, "revenus", "leads"))
sys.path.insert(0, os.path.join(RACINE, "revenus", "audit_regles"))
sys.path.insert(0, os.path.join(RACINE, "revenus", "veilleur"))
os.environ["REVENUS_TELEGRAM"] = "0"
os.environ["REVENUS_OLLAMA"] = "0"

import commun  # noqa: E402
commun.DONNEES = tempfile.mkdtemp()
import scanner_leads  # noqa: E402
import audit_regles  # noqa: E402
import regles_ombre  # noqa: E402
import veilleur  # noqa: E402


def test_notation_lead_chaud_vs_froid():
    chaud, raisons = scanner_leads.noter("Concepteur d'agent IA",
                                         "Budget : 500 € à 1 000 € - Catégories : Chatbot, ChatGPT  5 à 6 agents pour mon site")
    froid, _ = scanner_leads.noter("Graphiste PowerPoint", "Budget : Moins de 500 € - Catégories : Graphisme  logo et slides")
    assert chaud >= 75 and scanner_leads.niveau(chaud) == "CHAUD"
    assert froid < 50 and scanner_leads.niveau(froid) == "FROID"
    assert any("budget" in r for r in raisons)


def test_budget_lu_sur_grand_montant():
    pts, maxi = scanner_leads.points_budget("budget : 1 000 € à 10 000 € - catégories : vidéo ia")
    assert maxi == 10000 and pts == 25


def test_audit_detecte_regle_couteuse_et_regle_utile():
    chemin = audit_regles.demo(n=1500, graine=11)
    commandes, cols = audit_regles.charger(chemin)
    assert cols["montant"] == "total" and cols["decision"] == "fraud_status"
    res = audit_regles.analyser(commandes)
    par = {r["regle"]: r for r in res["regles"]}
    # règle très précise : gardée si assez observée, sinon prudence (mode ombre), jamais « retirer »
    assert "RETIRER" not in par["email_jetable"]["recommandation"]
    assert par["email_jetable"]["precision_estimee"] >= 0.3
    assert par["nouveau_client_nuit"]["recommandation"].startswith("ASSOUPLIR")
    assert par["nouveau_client_nuit"]["perte_nette"] > 0
    assert res["perte_nette_totale_estimee"] > 0
    md = audit_regles.rapport_markdown(res, "Test")
    assert "Règle par règle" in md and "1. " in md


def test_mode_ombre_juge_les_regles():
    o = regles_ombre.Ombre("test_unitaire", dossier=commun.DONNEES)
    o.regle("gros_montant", lambda c: c["montant"] > 300, mode="ombre")
    for i in range(30):
        v = o.evaluer({"id": f"T{i}", "montant": 400, "client_connu": True})
        assert v["bloquer"] is False and v["ombre"] == ["gros_montant"]
        o.juger(f"T{i}", "ok")
    r = o.rapport()
    assert r["regles"][0]["jugees"] == 30 and r["regles"][0]["precision"] == 0.0
    assert "NE PAS BLOQUER" in r["regles"][0]["recommandation"]


def test_mode_ombre_regles_envoyees_par_le_marchand():
    o = regles_ombre.Ombre("test_marchand", dossier=commun.DONNEES)
    v = o.evaluer({"id": "M1", "montant": 50, "decision": "refuse"}, {"pays_diff": True, "ok_regle": False})
    assert v["actives"] == ["pays_diff"] and v["bloquer"] is True


def test_veilleur_fichier_et_battement(tmp_path):
    veilleur.ETAT = str(tmp_path / "etat.json")
    veilleur.HISTO = str(tmp_path / "histo.jsonl")
    veilleur.BATTEMENTS = os.path.join(commun.DONNEES, "veilleur_battements.json")
    f = tmp_path / "frais.txt"
    f.write_text("x")
    ok, _ = veilleur.ctrl_fichier({"chemin": str(f), "age_max_min": 60})
    assert ok
    ok, det = veilleur.ctrl_battement({"cle": "jamais", "intervalle_max_min": 10})
    assert not ok and "aucun" in det
    commun.battement("jamais")
    ok, _ = veilleur.ctrl_battement({"cle": "jamais", "intervalle_max_min": 10})
    assert ok


def test_veilleur_alerte_apres_deux_echecs(tmp_path, monkeypatch):
    veilleur.ETAT = str(tmp_path / "etat.json")
    veilleur.HISTO = str(tmp_path / "histo.jsonl")
    monkeypatch.setattr(veilleur, "charger_config", lambda: {"clients": [
        {"nom": "C", "controles": [{"nom": "f", "type": "fichier", "chemin": str(tmp_path / "absent"), "age_max_min": 1}]}]})
    envoyes = []
    monkeypatch.setattr(commun, "telegram", lambda m, **k: envoyes.append(m) or True)
    veilleur.passe(envoyer=True)
    assert envoyes == []  # premier échec : pas encore d'alerte
    veilleur.passe(envoyer=True)
    assert len(envoyes) == 1 and "EN PANNE" in envoyes[0]
    (tmp_path / "absent").write_text("ok")
    veilleur.passe(envoyer=True)
    assert len(envoyes) == 2 and "rétabli" in envoyes[1]
    rap = veilleur.rapport(envoyer=False)
    assert "C" in rap and "incident" in rap


def test_veilleur_expansion_variables_env(monkeypatch):
    monkeypatch.setattr(commun, "env", lambda k, d=None: "SECRET" if k == "DASHBOARD_TOKEN" else d)
    c = veilleur._expandre({"url": "http://x/?token=${DASHBOARD_TOKEN}", "attendu": ["${DASHBOARD_TOKEN}"], "code": 200})
    assert c["url"].endswith("token=SECRET") and c["attendu"] == ["SECRET"] and c["code"] == 200


def test_prospection_campagne_et_suivi(monkeypatch):
    import prospection
    tmp = tempfile.mkdtemp()
    monkeypatch.setattr(prospection, "CSV", os.path.join(tmp, "prospection.csv"))
    monkeypatch.setattr(prospection, "DONNEES", tmp)
    camp = prospection.charger_campagne()
    assert len(camp) == 30 and len({c["id"] for c in camp}) == 30
    for c in camp:
        assert c["corps"] in prospection.CORPS
        assert c.get("email") or c.get("formulaire")
        assert "[" not in prospection.corps(c).split("\n\n")[0]  # pas de crochet dans l'accroche
    # jour 1 = 5 contacts, tous avec une adresse mail
    j1 = prospection.contacts_du_jour(5)
    assert [c["jour"] for c in j1] == [1] * 5 and all(c["email"] for c in j1)
    # on note un envoi : il sort de la file, la relance est à J+4
    prospection.noter_envoi("A", "Nodva", "mail")
    assert "nodva" in prospection.deja_contactes()
    assert all(c["nom"] != "Nodva" for c in prospection.contacts_du_jour(5))
    lignes = prospection.lire_csv()
    assert lignes[0]["statut"] == "envoye" and lignes[0]["relance"] > lignes[0]["date"]
    # réponse puis relance
    prospection.cmd_reponse("Nodva", "rdv mardi")
    assert prospection.lire_csv()[0]["statut"] == "repondu"
    # sans SMTP ni signature, l'envoi auto refuse
    monkeypatch.setenv("PROSPECTION_AUTO", "1")
    monkeypatch.setenv("PROSPECTION_SIGNATURE", "")
    assert prospection.cmd_envoyer() == []
    # un mail construit avec SMTP factice contient objet et signature
    monkeypatch.setenv("PROSPECTION_SIGNATURE", "Test Untel — test@example.org")
    monkeypatch.setenv("SMTP_EXPEDITEUR", "Test Untel <test@example.org>")
    assert prospection.envoyer_mail(j1[0], test=True)
    assert "test@example.org" in prospection.corps(j1[0])


def test_studio_tiktok_bible_et_texte_de_secours(monkeypatch, tmp_path):
    sys.path.insert(0, os.path.join(RACINE, "revenus", "tiktok"))
    import studio  # noqa: E402
    monkeypatch.setattr(studio, "ETAT", str(tmp_path / "etat.json"))
    monkeypatch.setattr(studio, "SAISONS", str(tmp_path / "saisons.json"))
    b = studio.bible()
    assert len(b["series"]) == 3
    for s in b["series"]:
        assert len(s["episodes"]) == 12 and len(s["palette"]) == 3
        for ep in s["episodes"]:
            assert ep["accroche"] and ep["suspens"] and len(ep["beats"]) >= 2
    # rotation : la série 1 jusqu'au bout, puis la 2
    e = studio.etat()
    s, n = studio.choisir(b, e)
    assert s["id"] == "ligne13" and n == 1
    e["episodes"]["ligne13"] = 12
    s, n = studio.choisir(b, e)
    assert s["id"] == "lettres2043" and n == 1
    # sans Ollama : texte de secours qui commence par l'accroche et finit par le suspens
    texte, secours = studio.ecrire_episode(b, b["series"][0], 3)
    assert secours and texte.startswith("Mon matricule") and texte.endswith("comme toi.")
    # minutage et regroupement des sous-titres
    mots = studio.minutage_mots(texte, 0.4, 30.0)
    assert len(mots) == len(texte.split()) and abs(mots[-1][2] - 30.4) < 1e-6
    grp = studio.groupes(mots)
    assert all(1 <= len(g) <= 4 for g in grp) and sum(len(g) for g in grp) == len(mots)
    # légende < 1 000 caractères (limite Telegram)
    assert len(studio.legende_tiktok(b["series"][0], 3, b["series"][0]["episodes"][2], False)) < 1000


def test_studio_tiktok_texte_propre_et_sous_titres():
    sys.path.insert(0, os.path.join(RACINE, "revenus", "tiktok"))
    import studio  # noqa: E402
    b = studio.bible()
    # le suspens entre guillemets n'est dit qu'une fois, et chaque étape commence par une majuscule
    texte, secours = studio.ecrire_episode(b, b["series"][0], 1)
    assert secours and texte.count("descendez ici") == 1 and "«" not in texte and " ." not in texte
    assert ". Il note l'heure" in texte
    # ponctuation isolée recollée au mot précédent, guillemets retirés
    assert studio.jetons("Elle dit : « Viens. » Puis rien .") == ["Elle", "dit :", "Viens.", "Puis", "rien."]
    # une fin de phrase ferme toujours le groupe de sous-titres
    mots = studio.minuter(texte, 0.4, 30.0)
    for g in studio.groupes(mots):
        assert 1 <= len(g) <= 4 and not any(m[0].endswith((".", "!", "?")) for m in g[:-1])
    assert studio.mot_fort("2043,") and studio.mot_fort("Personne") and not studio.mot_fort("lettre")


def test_studio_tiktok_sous_titres_recales_sur_les_silences():
    np = pytest.importorskip("numpy")
    sys.path.insert(0, os.path.join(RACINE, "revenus", "tiktok"))
    import studio  # noqa: E402
    sr = 8000
    rng = np.random.default_rng(1)
    parle = lambda s: (rng.random(int(s * sr)).astype("float32") - 0.5) * 0.4  # noqa: E731
    blanc = np.zeros(int(0.5 * sr), dtype="float32")
    # trois phrases de 2 s, 6 s et 1 s : un minutage « au poids » se tromperait de plusieurs secondes
    voix = np.concatenate([parle(2.0), blanc, parle(6.0), blanc, parle(1.0), blanc])
    texte = "Une phrase assez longue pour peser lourd. Courte. Fin de l'histoire ici."
    mots = studio.minuter(texte, 0.4, len(voix) / sr, voix, sr)
    assert [m[0] for m in mots] == texte.split()
    fins = [m[2] for m in mots if m[0].endswith(".")]
    assert abs(fins[0] - 2.4) < 0.05 and abs(fins[1] - 8.9) < 0.05 and abs(fins[2] - 10.4) < 0.05
    assert abs(mots[7][1] - 2.9) < 0.05  # « Courte. » démarre juste après le premier silence
    vol = studio.enveloppe(voix, sr, 24, 24 * 11, 0.4)
    assert vol.max() <= 1.0 and vol[24 * 1] > 0.5 and vol[int(24 * 2.85)] < 0.5


def test_studio_tiktok_voix_decoupe_et_prononciation():
    sys.path.insert(0, os.path.join(RACINE, "revenus", "tiktok"))
    import studio  # noqa: E402
    import voix  # noqa: E402
    b = studio.bible()
    # les prises de la voix portent exactement les mots des sous-titres, pour tous les épisodes
    for s in b["series"]:
        for n in range(1, len(s["episodes"]) + 1):
            texte, _ = studio.ecrire_episode(b, s, n)
            prises = voix.allures(voix.decouper(texte))
            assert [m for p in prises for m in p["mots"]] == studio.jetons(texte)
            assert all(0.6 <= p["vitesse"] <= 1.3 and 0 <= p["pause"] < 1.5 for p in prises) and prises[-1]["pause"] == 0
    assert voix.jetons_cites("Elle dit : « Viens. » Puis rien .") == (["Elle", "dit :", "Viens.", "Puis", "rien."],
                                                                    [False, False, True, False, False])
    # ce qui est dit n'est pas ce qui est écrit : heures, unités, guillemets
    assert voix.prononcer("À 2 h 14 précises, puis 2h14.") == "À 2 heures 14 précises, puis 2 heures 14."
    assert voix.prononcer("1 h du matin, 20 km/h, 640 € par mois, le 7B") == "1 heure du matin, 20 kilomètres heure, 640 euros par mois, le 7 B"
    assert voix.prononcer("Il dit : « Viens. »") == "Il dit : Viens."
    assert voix.prononcer("L'homme hésite.") == "L'homme hésite."
    # la parole de la radio est une prise à part, avec l'effet haut-parleur ; une parole ordinaire ne l'a pas
    p = voix.allures(voix.decouper("La radio grésille. Une voix calme annonce : Prochain arrêt, Sainte-Blaise. Je freine."))
    assert [(x["texte"], x["radio"]) for x in p] == [("La radio grésille.", False), ("Une voix calme annonce :", False),
                                                    ("Prochain arrêt, Sainte-Blaise.", True), ("Je freine.", False)]
    p = voix.decouper("Josiane sourit : « Roland avait ton âge. » Je me tais.")
    assert [x["cite"] for x in p] == [False, True, False] and not any(x["radio"] for x in p)
    p = voix.allures(voix.decouper("Une accroche qui claque fort. Une phrase du milieu, tranquille et longue. La dernière phrase du suspens."))
    assert p[0]["vitesse"] > p[1]["vitesse"] > p[2]["vitesse"] and p[1]["pause"] > p[0]["pause"]
    # les mots que le narrateur disait de travers lui sont écrits comme ils se disent ; la narratrice et les sous-titres n'en savent rien
    dit = voix.en_lettres("Au terminus, il tend à Malik un morceau de parpaing. Terminus ! Prends ce qu'elle te tend, dit Roland. Elle attend.",
                          oreille=True)
    assert dit == "Au terminusse, il tend à Malik un morceau de parpain. Terminusse ! Prends ce qu'elle te tan, dit Roland. Elle attend."
    assert voix.en_lettres("Au terminus, des parpaings.") == "Au terminus, des parpaings."


def test_studio_tiktok_voix_montage_et_reperes(tmp_path, monkeypatch):
    np = pytest.importorskip("numpy")
    sys.path.insert(0, os.path.join(RACINE, "revenus", "tiktok"))
    import studio  # noqa: E402
    import voix  # noqa: E402
    sr = 24000
    rng = np.random.default_rng(3)

    def parle(s):  # un « mot » : bruit large bande, comme une voix
        return (rng.standard_normal(int(s * sr)) * 0.2).astype("float32")

    texte = "La radio grésille, puis se tait. Une voix annonce : Prochain arrêt. Je note tout."
    blanc = np.zeros(int(0.15 * sr), dtype="float32")
    faux = [np.concatenate([blanc, parle(1.4), np.zeros(int(0.12 * sr), dtype="float32"), parle(1.1), blanc]),
            parle(1.2), parle(0.9), parle(1.1)]

    def fausse_synthese(prises, dossier, journal=None, graine=0):
        assert [p["texte"] for p in prises] == ["La radio grésille, puis se tait.", "Une voix annonce :", "Prochain arrêt.", "Je note tout."]
        return [x.copy() for x in faux], sr

    monkeypatch.setattr(voix, "synthetiser", fausse_synthese)
    wav = str(tmp_path / "v.wav")
    duree = studio.dire(texte, wav)
    reperes = voix.lire_reperes(wav)
    a, sr2 = studio.lire_wav(wav)
    assert sr2 == sr and abs(duree - len(a) / sr) < 1e-6 and duree > 5.5
    assert float(np.abs(a).max()) <= 0.99  # jamais d'écrêtage
    # la virgule coupe la première prise sur son vrai silence ; la parole radio a son propre repère
    assert [r[0] for r in reperes] == [["La", "radio", "grésille,"], ["puis", "se", "tait."], ["Une", "voix", "annonce :"],
                                       ["Prochain", "arrêt."], ["Je", "note", "tout."]]
    assert abs(reperes[0][2] - 1.4) < 0.08 and abs(reperes[1][1] - 1.54) < 0.08
    for (_, _, f0, _), (_, d1, _, _) in zip(reperes, reperes[1:]):
        assert d1 >= f0
    # sous-titres : chaque morceau démarre à son repère exact
    mots = studio.minuter(texte, 0.4, duree, a, sr, reperes)
    assert [m[0] for m in mots] == studio.jetons(texte)
    assert abs(mots[3][1] - (0.4 + reperes[1][1])) < 1e-6 and abs(mots[-1][2] - (0.4 + reperes[-1][2])) < 1e-6
    assert all(y[1] >= x[1] for x, y in zip(mots, mots[1:]))
    # des repères qui ne correspondent pas au texte sont ignorés (retour au recalage habituel)
    assert studio.minuter("Un autre texte.", 0.4, 2.0, None, 0, reperes)[0][0] == "Un"

    def aigus(x):  # part d'énergie au-dessus de 5 kHz
        sp = np.abs(np.fft.rfft(x)) ** 2
        f = np.fft.rfftfreq(len(x), 1.0 / sr)
        return float(sp[f > 5000].sum() / sp.sum())

    i0, i1 = int((reperes[3][1] + 0.1) * sr), int((reperes[3][2] - 0.1) * sr)
    j0, j1 = int((reperes[4][1] + 0.1) * sr), int((reperes[4][2] - 0.1) * sr)
    assert aigus(a[i0:i1]) < 0.02 < aigus(a[j0:j1])  # la radio : bande étroite ; la narration : pleine bande
    assert abs(voix._niveau(a[j0:j1], sr) - 0.175) < 0.04  # niveau constant de la narration
    # sans voix naturelle, le studio retombe sur Piper sans rien casser
    monkeypatch.setattr(voix, "synthetiser", lambda *a_, **k_: (None, 0))
    monkeypatch.setattr(studio, "telecharger_voix", lambda: False)
    monkeypatch.setattr(studio, "VOIX_DIR", str(tmp_path / "absent"))
    assert studio.dire(texte, wav) == 0.0 and voix.lire_reperes(wav) is None


def test_studio_tiktok_voix_du_narrateur(tmp_path, monkeypatch):
    np = pytest.importorskip("numpy")
    import json
    sys.path.insert(0, os.path.join(RACINE, "revenus", "tiktok"))
    import studio  # noqa: E402
    import voix  # noqa: E402
    b = studio.bible()
    serie = {s["id"]: s for s in b["series"]}
    # chaque série a la voix de son narrateur : Malik est un homme, Claire et Nour des femmes
    assert [serie[i]["voix"] for i in ("ligne13", "lettres2043", "sept_b")] == ["homme", "femme", "femme"]
    assert voix.profil("homme")[0] == "supertonic" and voix.profil("femme")[0] == "kokoro"
    monkeypatch.setenv("STUDIO_VOIX_HOMME", "M5")
    assert voix.profil("homme") == ("supertonic", "M5")
    # le narrateur dit ses nombres en toutes lettres (son moteur lit mal les chiffres)
    assert voix.en_lettres("À 2 heures 14, ligne 13, depuis 1972.") == "À deux heures quatorze, ligne treize, depuis mille neuf cent soixante-douze."
    assert [voix.nombre_en_lettres(n) for n in (0, 21, 71, 80, 81, 99, 200, 201, 1000, 2043)] == [
        "zéro", "vingt et un", "soixante et onze", "quatre-vingts", "quatre-vingt-un", "quatre-vingt-dix-neuf", "deux cents",
        "deux cent un", "mille", "deux mille quarante-trois"]
    # ... et dans une écriture qu'il dit d'une traite : écrits comme dans le dictionnaire, 71, 78 ou 98 sortent en deux nombres
    assert [voix.nombre_en_lettres(n, oreille=True) for n in (16, 17, 18, 19, 21, 61, 70, 71, 78, 80, 90, 98, 1971, 2043)] == [
        "seize", "dissète", "dizuit", "dizneuf", "vingtéun", "soissantéun", "soissante-disse", "soissantéonze", "soissante-dizuit",
        "quatre-vingts", "quatre-vingt-disse", "quatre-vingt-dizuit", "mille neuf cent soissantéonze", "deux mille quarante-trois"]
    dit = voix.en_lettres(voix.prononcer("Roland a 78 ans. À 18 h 05, rame 7B, soixante et onze marches, six ans, dix et demi, 70 euros, le 7e."),
                          oreille=True)
    assert dit == ("Roland a soissante-dizuit ans. À dizuit heures cinq, rame sept bé, soissantéonze marches, siz ans, dix et demi, "
                   "soissante-dise euros, le septième.")
    # les sous-titres laissent à « 1972 » le temps d'être dit, et « un » n'est pas pris pour un nombre
    mots = "Un plan de 1972, et je suis né là.".split()
    poids = voix.poids_mots(mots)
    assert poids[3] > 3 * poids[1] and voix.est_nombre("1972,") and voix.est_nombre("soixante-dix-sept") and not voix.est_nombre("un")
    # une hésitation au milieu d'un nombre est retirée ; la pause de la virgule qui le suit reste
    import numpy as np
    sr = 24000
    son = lambda d: (0.3 * np.sin(np.arange(int(d * sr)) * 0.05)).astype("float32")  # noqa: E731
    blanc = lambda d: np.zeros(int(d * sr), dtype="float32")  # noqa: E731
    prise = np.concatenate([son(0.9), son(0.5), blanc(0.40), son(0.6), blanc(0.35), son(1.2)])  # … de mille neuf cent | soixante-douze, | et…
    serre = voix.resserrer(prise, sr, mots, poids)
    assert 0.30 < (len(prise) - len(serre)) / sr < 0.40
    assert len(voix.respirations(mots, serre, sr, poids)) == 2  # la virgule a gardé son silence
    assert len(voix.resserrer(prise, sr, "Je le vois, et il attend là.".split(), voix.poids_mots("Je le vois, et il attend là.".split()))) == len(prise)
    # qui parle ? seulement quand le texte le dit sans ambiguïté
    noms = serie["ligne13"]["voix_personnages"]
    assert voix.genre_cite("Une voix de femme, très calme, annonce :") == "femme"
    assert voix.genre_cite("Josiane sourit :", noms) == "femme" and voix.genre_cite("Roland répond :", noms) == "homme"
    assert voix.genre_cite("Une voix annonce :") is None and voix.genre_cite("Josiane regarde Roland :", noms) is None
    assert voix.genre_cite("Je demande à Josiane :", noms) is None  # c'est le narrateur qui parle
    assert voix.genre_cite("J'entends la voix de Josiane :", noms) == "femme"

    def voix_de(texte, s):
        return [(p["texte"], p["voix"], p["radio"]) for p in
                voix.attribuer(voix.decouper(texte, s.get("voix_personnages")), s.get("voix", "femme"), s.get("voix_radio"))]

    malik = serie["ligne13"]
    assert voix_de("Je m'appelle Malik. Une voix de femme annonce : Prochain arrêt. Je freine.", malik) == [
        ("Je m'appelle Malik.", "homme", False), ("Une voix de femme annonce :", "homme", False),
        ("Prochain arrêt.", "femme", True), ("Je freine.", "homme", False)]
    # l'annonce de la radio garde sa voix de femme même quand la phrase ne le répète pas
    assert voix_de("La troisième nuit, l'annonce ajoute : Malik, descendez ici.", malik)[-1] == ("Malik, descendez ici.", "femme", True)
    # ce que Malik dit lui-même, même dans la radio, reste dit par Malik, sans effet haut-parleur
    assert voix_de("Je prends la radio et je dis : Ici Malik.", malik)[-1] == ("Ici Malik.", "homme", False)
    assert voix_de("Je lui réponds : Pas ce soir.", malik)[-1] == ("Pas ce soir.", "homme", False)
    assert voix_de("Je monte le son et la radio annonce : Terminus.", malik)[-1] == ("Terminus.", "femme", True)
    assert voix_de("Roland murmure : Tu es venu.", malik)[-1] == ("Tu es venu.", "homme", False)
    assert voix_de("Josiane sourit : Roland avait ton âge.", malik)[-1] == ("Roland avait ton âge.", "femme", False)
    # au téléphone, personne n'a dit qui parle : le narrateur lit la phrase (la voix de la radio n'est que pour la radio)
    assert voix_de("Le téléphone sonne, on me dit : Ne descends pas.", malik)[-1] == ("Ne descends pas.", "homme", True)
    # une série racontée par une femme ne change pas : sa voix partout, sauf si un homme est nommé
    assert {v for _, v, _ in voix_de("Je m'appelle Claire. La lettre dit : Ne prends pas le train.", serie["lettres2043"])} == {"femme"}
    assert voix_de("Samuel répond : Moi aussi.", serie["lettres2043"])[-1][1] == "homme"
    monkeypatch.setenv("STUDIO_DIALOGUES", "0")
    assert {v for _, v, _ in voix_de("Une voix de femme annonce : Prochain arrêt.", malik)} == {"homme"}
    monkeypatch.delenv("STUDIO_DIALOGUES")

    # montage : les deux voix n'ont pas la même fréquence d'échantillonnage, la piste finale n'en a qu'une
    rng = np.random.default_rng(5)
    texte = "Je conduis la nuit. Une voix de femme annonce : Prochain arrêt. Je note tout."
    recu = {}

    def fausse_synthese(prises, dossier, journal=None, graine=0):
        recu["voix"] = [p["voix"] for p in prises]
        sons, frequences = [], []
        for p in prises:
            sr = 44100 if p["voix"] == "homme" else 24000
            sons.append((rng.standard_normal(int(1.0 * sr)) * 0.2).astype("float32"))
            frequences.append(sr)
        return sons, frequences

    monkeypatch.setattr(voix, "synthetiser", fausse_synthese)
    wav = str(tmp_path / "h.wav")
    duree = studio.dire(texte, wav, malik)
    a, sr = studio.lire_wav(wav)
    reperes = voix.lire_reperes(wav)
    assert recu["voix"] == ["homme", "homme", "femme", "homme"] and sr == 44100
    assert abs(duree - len(a) / sr) < 1e-6 and 4.0 + 0.9 < duree < 4.0 + 2.5  # 4 prises d'une seconde + les silences
    assert [r[0] for r in reperes] == [["Je", "conduis", "la", "nuit."], ["Une", "voix", "de", "femme", "annonce :"],
                                       ["Prochain", "arrêt."], ["Je", "note", "tout."]]
    assert all(0.8 < r[2] - r[1] < 1.05 for r in reperes)  # la prise à 24 kHz garde sa durée une fois rééchantillonnée
    x = voix.reechantillonner(np.sin(2 * np.pi * 440 * np.arange(24000) / 24000).astype("float32"), 24000, 44100)
    assert len(x) == 44100 and abs(float(np.abs(np.fft.rfft(x)).argmax()) - 440) <= 1  # même note, même durée
    # une voix pas encore installée est remplacée par l'autre, l'épisode sort quand même
    monkeypatch.undo()
    monkeypatch.setattr(voix, "moteurs", lambda: {"kokoro": sys.executable})
    monkeypatch.setattr(voix.subprocess, "run", lambda *a_, **k_: (_ for _ in ()).throw(OSError("pas de moteur ici")))
    prises = voix.allures(voix.attribuer(voix.decouper("Je note tout."), "homme"))
    messages = []
    assert voix.synthetiser(prises, str(tmp_path), messages.append) == (None, 0)
    assert prises[0]["voix"] == "femme" and "pas encore installée" in messages[0]
    travail = json.load(open(tmp_path / "travail.json", encoding="utf-8"))
    assert [(t["moteur"], t["voix"]) for t in travail["prises"]] == [("kokoro", "ff_siwis")]
    # la finition du narrateur met ses consonnes en avant (haut-parleur de téléphone) ; celle de la narratrice ne change pas
    sr2 = 44100
    bruit = (np.random.default_rng(5).standard_normal(sr2 * 2) * 0.1).astype("float32")

    def bande(x, f0, f1):
        f = np.fft.rfftfreq(len(x), 1.0 / sr2)
        return float(np.sqrt(np.mean(np.abs(np.fft.rfft(x))[(f >= f0) & (f < f1)] ** 2)))

    def relief(x):  # les consonnes (2 à 4,5 kHz) par rapport au bas-médium (200 à 350 Hz), en décibels
        return 20 * float(np.log10(bande(x, 2000, 4500) / bande(x, 200, 350)))

    net = voix.soigner(bruit.copy(), sr2, cible=0.195, grave=True)
    elle = voix.soigner(bruit.copy(), sr2)
    monkeypatch.setenv("STUDIO_NETTETE", "0")
    rond = voix.soigner(bruit.copy(), sr2, cible=0.195, grave=True)
    assert 3.5 < relief(net) - relief(rond) < 7.0  # plus net, sans devenir criard
    assert abs(voix._niveau(net, sr2) - voix._niveau(rond, sr2)) < 0.02 and float(np.abs(net).max()) <= 0.94  # même niveau
    assert np.allclose(elle, voix.soigner(bruit.copy(), sr2))


def test_studio_tiktok_scenes_animees(monkeypatch):
    pytest.importorskip("numpy")
    pytest.importorskip("PIL")
    monkeypatch.setenv("STUDIO_PHOTOS", "0")  # ici, les décors dessinés ; les plans photographiques ont leur test
    sys.path.insert(0, os.path.join(RACINE, "revenus", "tiktok"))
    import scenes  # noqa: E402
    import studio  # noqa: E402
    b = studio.bible()
    for s in b["series"]:
        palette = tuple(studio.hexa(c) for c in s["palette"])
        regl = scenes.reglages_serie(s)
        assert regl["decor"] in ("metro", "lettres", "immeuble")
        # toutes les scènes du décor + les deux scènes communes se dessinent en 540×960
        for nom in scenes.DECORS[regl["decor"]] + ["horloge", "nombre"]:
            info = dict(regl, heure=(2, 14), nombre=640, etiquette="EUROS", suspens=True)
            dessine = scenes.fabriquer({"scene": nom, "graine": 3, "info": info}, palette)
            for t in (0.0, 0.8, 3.5):
                im = dessine(t, t / 4.0, 0.6)
                assert im.size == (scenes.L, scenes.H) and im.mode == "RGB", nom
            assert len(dessine.foyer) == 2
        # le découpage couvre toute la vidéo sans trou, change de scène à chaque plan, finit sur le suspens
        texte, _ = studio.ecrire_episode(b, s, 1)
        mots = studio.minuter(texte, 0.4, 28.0)
        plans = scenes.decouper_plans(mots, s, 1, 32.0)
        assert plans[0]["t0"] == 0.0 and plans[-1]["t1"] == 32.0 and len(plans) >= 5
        assert all(abs(x["t1"] - y["t0"]) < 1e-9 and x["scene"] != y["scene"] for x, y in zip(plans, plans[1:]))
        assert plans[-1]["suspens"] and not plans[0]["suspens"] and plans[0]["transition"] == "aucune"
        assert all(p["scene"] in scenes.SCENES for p in plans)
    # une série ajoutée dans bible.json sans réglage reçoit le décor générique
    assert scenes.reglages_serie({"id": "nouvelle"})["decor"] == "mystere"
    assert scenes.reglages_serie({"id": "x", "animation": {"decor": "metro"}})["decor"] == "metro"
    im = scenes.finitions()(scenes.fabriquer(plans[0], palette)(1.0, 0.3, 0.5), 0, 0.4)
    assert scenes.cadrer(scenes.parasite(im, 1), 1.15, 270, 300, (1080, 1920)).size == (1080, 1920)


def test_studio_tiktok_plans_photographiques(monkeypatch, tmp_path):
    pytest.importorskip("numpy")
    Image = pytest.importorskip("PIL.Image")
    sys.path.insert(0, os.path.join(RACINE, "revenus", "tiktok"))
    import photos  # noqa: E402
    import scenes  # noqa: E402
    import studio  # noqa: E402
    monkeypatch.setenv("STUDIO_DUREE", "70")  # les plans de l'épisode 12 sont vérifiés ici sur le texte long
    monkeypatch.delenv("STUDIO_PHOTOS", raising=False)
    monkeypatch.delenv("STUDIO_MEDIAS", raising=False)
    b = studio.bible()
    s = next(x for x in b["series"] if x["id"] == "ligne13")
    palette = tuple(studio.hexa(c) for c in s["palette"])
    # la série a ses images : chacune en 9:16, avec sa carte de relief et des mots pour l'appeler
    bq = photos.banque("ligne13")
    assert bq and len(bq.noms) >= 10 and {"cabine", "visage", "tunnel"} <= set(n[len("photo:"):] for n in bq.replis())
    for nom in bq.noms:
        with Image.open(bq.chemin(nom)) as im:
            assert abs(im.width / im.height - 9 / 16) < 0.01 and im.width >= 1080, nom
        assert os.path.exists(os.path.splitext(bq.chemin(nom))[0] + "_prof.png"), nom
        assert bq.mots("photo:" + nom) and bq.fiches[nom].get("dessin") in scenes.SCENES, nom
    assert photos.banque("lettres2043") is None  # pas d'images : la série garde ses décors dessinés
    # le montage se fait avec les photos : jamais deux fois de suite la même, l'heure dite montre l'horloge
    texte, _ = studio.ecrire_episode(b, s, 1)
    mots = studio.minuter(texte, 0.4, 28.0)
    plans = scenes.decouper_plans(mots, s, 1, 32.0)
    assert plans[0]["t0"] == 0.0 and plans[-1]["t1"] == 32.0 and plans[-1]["suspens"]
    assert all(p["scene"].startswith("photo:") and p["serie"] == "ligne13" for p in plans)
    assert all((x["scene"], x["cadrage"]) != (y["scene"], y["cadrage"]) for x, y in zip(plans, plans[1:]))
    # montage nerveux : aucun plan ne traîne, et rien n'est révélé avant l'heure (la femme du quai attend l'épisode 4)
    assert max(p["t1"] - p["t0"] for p in plans[:-1]) < 5.0
    assert not {p["scene"] for p in plans} & {"photo:femme", "photo:quai", "photo:archives"}
    assert "photo:femme" not in bq.scenes(1) and "photo:femme" in bq.scenes(4) and "photo:femme" in bq.scenes()
    phrase = ("Je conduis la nuit. À 2 h 14 précises, tout change. Pas de quai. Mes mains serrent le manipulateur. La radio grésille. "
              "Une femme en uniforme attend.")
    pl = scenes.decouper_plans(studio.minuter(phrase, 0.4, 16.0), s, 1, 18.0, mini=0.5)
    par_texte = {p["texte"]: p for p in pl}
    assert next(p for p in pl if p["texte"].startswith("À 2 h 14"))["scene"] == "photo:horloge"
    assert all(p["scene"] != "photo:femme" for p in pl)
    assert any(p["scene"] == "photo:femme" for p in scenes.decouper_plans(studio.minuter(phrase, 0.4, 16.0), s, 4, 18.0, mini=0.5))
    # le second lot d'images : chaque révélation attend son épisode, et la phrase appelle la bonne image
    assert len(bq.noms) >= 21 and "photo:micro" in bq.replis()
    attendus = {"josiane": 3, "roland_jeune": 3, "mur": 4, "journal": 5, "roland": 6, "lanterne": 7, "photo": 8}
    for nom, n in attendus.items():
        assert "photo:" + nom not in bq.scenes(n - 1) and "photo:" + nom in bq.scenes(n), nom
    assert {"photo:micro", "photo:rame", "photo:depot"} <= set(bq.scenes(1))

    def montre(texte_, numero):
        pl_ = scenes.decouper_plans(studio.minuter(texte_, 0.4, 14.0), s, numero, 16.0, mini=0.5)
        return {p["texte"]: (p["scene"][len("photo:"):], p["cadrage"]) for p in pl_}
    vu = montre("Je conduis la nuit. Josiane, la doyenne, blêmit. Sa rame est arrivée au terminus. "
                "Une ouverture murée de parpaings. Je retiens mon souffle.", 4)
    assert vu["Josiane, la doyenne, blêmit."][0] == "josiane" and vu["Sa rame est arrivée au terminus."][0] == "rame"
    assert vu["Une ouverture murée de parpaings."] == ("mur", 1)  # le cadrage serré sur les parpaings
    assert montre("Je conduis la nuit. Une ouverture murée de parpaings.", 3)["Une ouverture murée de parpaings."][0] != "mur"
    vu = montre("Je conduis la nuit. Roland a 78 ans. Lucienne lui a tendu une lanterne. Josiane sort une photo de 1999. "
                "Il attend. Le panneau est allumé.", 8)
    assert vu["Roland a 78 ans."][0] == "roland" and vu["Lucienne lui a tendu une lanterne."][0] == "lanterne"
    assert vu["Josiane sort une photo de 1999."][0] == "photo"
    # le troisième lot : le banc des carnets (10), le contrôleur du terminus (11), Inès (12)
    assert len(bq.noms) >= 24
    for nom, n in {"banc": 10, "controleur": 11, "ines": 12}.items():
        assert "photo:" + nom not in bq.scenes(n - 1) and "photo:" + nom in bq.scenes(n), nom
    vu = montre("Je conduis la nuit. Sur un banc, des carnets. Des dizaines de carnets, alignés. Je me tais. "
                "Je prends un carnet vide sur le banc.", 10)
    assert vu["Sur un banc, des carnets."] == ("banc", 0) and vu["Des dizaines de carnets, alignés."] == ("banc", 1)
    assert next(v for k, v in vu.items() if "vide" in k) == ("banc", 2)  # le carnet neuf, au premier plan
    vu = montre("Je conduis la nuit. Au terminus, le contrôleur m'attend. Il regarde sa montre. "
                "Le contrôleur dit : Treize minutes de retard, Malik.", 11)
    assert vu["Au terminus, le contrôleur m'attend."] == ("controleur", 0) and vu["Il regarde sa montre."] == ("controleur", 1)
    assert all(v[0] == "controleur" for k, v in vu.items() if "Treize" in k or "dit" in k)
    assert montre("Je conduis la nuit. Au terminus, le contrôleur m'attend.", 10)["Au terminus, le contrôleur m'attend."][0] != "controleur"
    # l'épisode 12 écrit d'avance : la dernière page se lit sur le carnet, Inès n'apparaît qu'à son arrivée au dépôt
    douze = studio.texte_ecrit(s, 12)
    pl12 = scenes.decouper_plans(studio.minuter(douze, 0.4, len(douze.split()) / 2.25), s, 12, len(douze.split()) / 2.25 + 4)
    sc12 = [(p["scene"][len("photo:"):], p["texte"]) for p in pl12]
    i_ines = next(i for i, (n, _) in enumerate(sc12) if n == "ines")
    assert "nouvelle conductrice" in sc12[i_ines][1] and all(n == "carnet" for n, x in sc12 if "Prénom" in x or "prochaine" in x)
    assert any(n == "ines" and "poche" in x for n, x in sc12) and sc12[-1][0] == "radio" and pl12[-1]["suspens"]
    for nom in ("micro", "mur", "roland", "photo", "banc", "controleur", "ines"):  # les nouvelles images se rendent comme les autres
        vue = scenes.fabriquer({"scene": "photo:" + nom, "serie": "ligne13", "cadrage": 1, "graine": 2, "camera": "avant", "t0": 0.0}, palette)
        assert vue.photo and vue.plein(0.5, 0.2, 0.3, 0, 1.08).size == (1080, 1920), nom
    assert par_texte["Pas de quai."]["scene"] != "photo:quai"  # un mot nié n'appelle pas son image
    main = par_texte["Mes mains serrent le manipulateur."]
    assert main["scene"] == "photo:cabine" and main["cadrage"] == 1  # le cadrage que la phrase appelle
    # une photo se rend en pleine résolution et bouge d'une image à l'autre
    dessine = scenes.fabriquer(dict(main, camera="avant"), palette)
    assert dessine.photo and len(dessine.foyer) == 2
    a = dessine.plein(0.5, 0.1, 0.2, 0, 1.06, 0.0, (2.0, -1.0), 0.0)
    c = dessine.plein(2.5, 0.7, 0.8, 1, 1.14, 0.0, (0.0, 0.0), 0.3)
    assert a.size == c.size == (1080, 1920) and a.mode == "RGB" and a.tobytes() != c.tobytes()
    assert scenes.parasite(a, 3).size == (1080, 1920) and dessine(1.0, 0.3, 0.5).size == (scenes.L, scenes.H)
    # derrière le pare-brise, le tunnel défile même quand la caméra ne bouge pas ; STUDIO_DEFILE=0 le fige
    np = pytest.importorskip("numpy")
    monkeypatch.setenv("STUDIO_VIBRATION", "0")

    def ecart(plan_):
        f = scenes.fabriquer(plan_, palette)
        x = np.asarray(f.plein(1.0, 0.5, 0.0, 0, 1.1), dtype="int16")[300:900:6, 200:880:6]
        y = np.asarray(f.plein(1.0 + 0.4, 0.5, 0.0, 0, 1.1), dtype="int16")[300:900:6, 200:880:6]
        return float(np.abs(x - y).mean())
    tunnel = {"scene": "photo:tunnel", "serie": "ligne13", "cadrage": 0, "graine": 3, "camera": "droite", "t0": 0.0}
    assert bq.fiches["tunnel"].get("defile") and "roule" in bq.fiches["tunnel"]["effets"]
    bouge = ecart(tunnel)
    monkeypatch.setenv("STUDIO_DEFILE", "0")
    assert bouge > 2 * ecart(tunnel) and bouge > 1.5
    monkeypatch.delenv("STUDIO_DEFILE")
    monkeypatch.delenv("STUDIO_VIBRATION")
    # STUDIO_PHOTOS=0, dossier absent ou image illisible : retour aux décors dessinés, sans erreur
    monkeypatch.setenv("STUDIO_PHOTOS", "0")
    assert all(p["scene"] in scenes.SCENES for p in scenes.decouper_plans(mots, s, 1, 32.0))
    monkeypatch.delenv("STUDIO_PHOTOS")
    monkeypatch.setenv("STUDIO_MEDIAS", str(tmp_path / "rien"))
    assert all(p["scene"] in scenes.SCENES for p in scenes.decouper_plans(mots, s, 1, 32.0))
    faux = tmp_path / "medias" / "ligne13"
    faux.mkdir(parents=True)
    with open(os.path.join(bq.dossier, "plans.json"), encoding="utf-8") as f:
        (faux / "plans.json").write_text(f.read(), encoding="utf-8")
    for nom in bq.noms:
        (faux / bq.fiches[nom]["fichier"]).write_bytes(b"pas une image")
    monkeypatch.setenv("STUDIO_MEDIAS", str(tmp_path / "medias"))
    secours = scenes.fabriquer(scenes.decouper_plans(mots, s, 1, 32.0)[0], palette)
    assert not getattr(secours, "photo", False) and secours(1.0, 0.3, 0.5).size == (scenes.L, scenes.H)



def test_studio_tiktok_sous_titres_dans_la_largeur_utile():
    pytest.importorskip("PIL.Image")
    sys.path.insert(0, os.path.join(RACINE, "revenus", "tiktok"))
    import scenes  # noqa: E402
    import studio  # noqa: E402
    textes = ["Malik demande l'enregistrement de la fréquence : trente secondes de silence.",
              "Anticonstitutionnellement, l'administration désapprouverait immédiatement.",
              "Je note tout.", "Prochain arrêt, Sainte-Blaise."]
    for texte in textes:
        for g in studio.groupes(studio.minutage_mots(texte, 0.4, 8.0)):
            places = studio.mise_en_page(g, 840, 1152)
            assert [p[0] for p in places] == [m[0] for m in g]
            for m, _, _, x, y, corps, _ in places:  # aucun mot ne sort de la largeur utile (bug : « emande l'enregistreme »)
                w = scenes.police(corps).getlength(m)
                assert x - w / 2 >= (1080 - 840) / 2 - 1 and x + w / 2 <= (1080 + 840) / 2 + 1, (texte, m)
            assert len({round(p[4]) for p in places}) <= 3


def test_studio_tiktok_refaire_et_alertes(monkeypatch, tmp_path):
    sys.path.insert(0, os.path.join(RACINE, "revenus", "tiktok"))
    import studio  # noqa: E402
    import voix  # noqa: E402
    videos = tmp_path / "videos"
    monkeypatch.setattr(studio, "ETAT", str(tmp_path / "etat.json"))
    monkeypatch.setattr(studio, "SAISONS", str(tmp_path / "saisons.json"))
    monkeypatch.setattr(studio, "VIDEOS", str(videos))
    monkeypatch.setattr(studio, "JOURNAL", str(tmp_path / "studio.log"))
    monkeypatch.setenv("REVENUS_OLLAMA", "0")
    messages, dits = [], []
    monkeypatch.setattr(studio, "telegram", lambda texte, **k: messages.append(texte) or True)
    monkeypatch.setattr(studio, "telegram_video", lambda chemin, legende: messages.append("VIDEO " + chemin) or True)
    monkeypatch.setattr(studio, "dire", lambda texte, sortie, serie=None: dits.append(texte) or 30.0)
    monkeypatch.setattr(studio, "mixer", lambda voix_wav, sortie, **k: (34.0, 30.0))
    photos_vues = {"n": 0}

    def faux_rendu(texte, audio, total, debut, duree, serie, numero, sortie, **k):
        studio.BILAN.clear()
        studio.BILAN.update({"plans": 12, "photos": photos_vues["n"], "panne": False})
        with open(sortie, "wb") as f:
            f.write(b"mp4")
        return True
    monkeypatch.setattr(studio, "rendre", faux_rendu)
    # serveur à moitié à jour : la voix d'homme n'est pas installée, les images n'ont pas servi → c'est dit sur Telegram
    monkeypatch.setattr(voix, "moteurs", lambda: {"kokoro": "python"})
    assert studio.cmd_episode("ligne13") == 0
    alerte = next(m for m in messages if "à corriger avant de publier" in m)
    assert "voix d'homme n'est pas installée" in alerte and "studio.py voix" in alerte and "images réalistes" in alerte
    e = studio.etat()
    assert e["episodes"]["ligne13"] == 1 and len(e["historique"]) == 1
    # une fois le serveur réparé : « refaire » redonne le même épisode, avec le même texte, sans avancer la série
    monkeypatch.setattr(voix, "moteurs", lambda: {"kokoro": "python", "supertonic": "python"})
    photos_vues["n"] = 12
    del messages[:]
    assert studio.cmd_refaire() == 0
    e = studio.etat()
    assert e["episodes"]["ligne13"] == 1 and len(e["historique"]) == 1 and e["historique"][0]["refait"]
    assert dits[0] == dits[1] and not any("à corriger" in m for m in messages) and any(m.startswith("VIDEO ") for m in messages)
    assert studio.cmd_refaire("sept_b") == 1  # rien à refaire pour une série pas encore commencée
    # une série à voix de femme ne réclame pas la voix d'homme
    monkeypatch.setattr(voix, "moteurs", lambda: {"kokoro": "python"})
    b = studio.bible()
    assert not studio.alertes_voix(next(x for x in b["series"] if x["id"] == "lettres2043"))


def test_studio_tiktok_textes_ecrits_et_question(monkeypatch):
    sys.path.insert(0, os.path.join(RACINE, "revenus", "tiktok"))
    import re
    import studio  # noqa: E402
    import voix  # noqa: E402
    import scenes  # noqa: E402
    monkeypatch.setenv("STUDIO_DUREE", "70")  # le format long : plus d'une minute (le format court a son test)
    b = studio.bible()
    s = next(x for x in b["series"] if x["id"] == "ligne13")
    for n in range(4, 13):
        ep = s["episodes"][n - 1]
        texte, secours = studio.ecrire_episode(b, s, n)
        # le texte écrit d'avance passe avant Ollama : il ouvre sur l'accroche de la légende et tient en un peu plus d'une minute
        assert not secours and texte == studio.texte_ecrit(s, n) and texte.startswith(ep["accroche"]), n
        assert 140 <= len(texte.split()) <= 185, n
        phrases = re.split(r"(?<=[.!?]) ", texte)
        assert max(len(p.split()) for p in phrases) <= 19, n
        # celui qui tombe sur l'épisode sans avoir vu les autres comprend en dix secondes : métro, ligne 13, station fantôme
        debut = " ".join(texte.split()[:45]).lower()
        assert "ligne 13" in debut and ("fantôme" in debut or "n'existe pas" in debut), n
        # la question de fin : courte, dans la légende, et la légende reste sous la limite Telegram
        assert 8 <= len(ep["question"]) <= 36 and ep["question"].endswith("?"), n
        legende = studio.legende_tiktok(s, n, ep, False)
        assert ep["question"] in legende and ep["accroche"] in legende and len(legende) < 1000, n
        # aucune image d'un épisode à venir, et le dernier plan porte le suspens
        duree = len(texte.split()) / 2.25
        plans = scenes.decouper_plans(studio.minuter(texte, 0.4, duree), s, n, duree + 4)
        assert plans[-1]["suspens"] and len({p["scene"] for p in plans}) >= 9, n
    # la femme du quai n'apparaît qu'à la toute fin de l'épisode 4 (pas avant qu'il la voie)
    texte = studio.texte_ecrit(s, 4)
    duree = len(texte.split()) / 2.25
    plans = scenes.decouper_plans(studio.minuter(texte, 0.4, duree), s, 4, duree + 4)
    assert [p["scene"] for p in plans].index("photo:femme") >= len(plans) - 2
    # l'annonce de la radio garde sa voix de femme, Malik garde la sienne quand c'est lui qui parle
    prises = voix.attribuer(voix.decouper(texte, s["voix_personnages"]), "homme", "femme")
    assert [" ".join(p["mots"]) for p in prises if p["voix"] == "femme"] == ["Prochain arrêt, Sainte-Blaise."]
    prises = voix.attribuer(voix.decouper(studio.texte_ecrit(s, 9), s["voix_personnages"]), "homme", "femme")
    assert [" ".join(p["mots"]) for p in prises if p["voix"] == "femme"] == ["Prochain arrêt, Sainte-Blaise, portes côté gauche."]
    # l'ouverture : une phrase choc courte, lisible en une seconde, sur l'image la plus intrigante de l'épisode
    pytest.importorskip("PIL.Image")
    import photos  # noqa: E402
    monkeypatch.delenv("STUDIO_PHOTOS", raising=False)
    monkeypatch.delenv("STUDIO_MEDIAS", raising=False)
    monkeypatch.delenv("STUDIO_CHOC", raising=False)
    bq = photos.banque("ligne13")
    assert studio.phrase_choc("Une femme me fait *signe* depuis un quai *muré*.") == [
        ("Une", False), ("femme", False), ("me", False), ("fait", False), ("signe", True), ("depuis", False), ("un", False),
        ("quai", False), ("muré.", True)]
    assert [f for _, f in studio.phrase_choc("Un plan de 1972.")] == [False, False, False, True]  # sans astérisque : les chiffres
    assert studio.phrase_choc(None) == []
    f = scenes.police(104)
    for n, ep in enumerate(s["episodes"], 1):
        choc = studio.phrase_choc(ep["choc"])
        assert 4 <= len(choc) <= 10 and any(fort for _, fort in choc) and "*" not in " ".join(m for m, _ in choc), n
        corps, lignes = studio.corps_choc(choc, 840)
        assert corps >= 64 and len(lignes) <= 3 and sum(len(x) for x in lignes) == len(choc), n  # trois lignes au plus, en gros
        assert "photo:" + ep["ouverture"] in bq.scenes(n), n  # l'image d'ouverture existe et a le droit d'être montrée
        if n >= 4:
            texte = studio.texte_ecrit(s, n)
            duree = len(texte.split()) / 2.25
            assert scenes.decouper_plans(studio.minuter(texte, 0.4, duree), s, n, duree + 4)[0]["scene"] == "photo:" + ep["ouverture"], n
    ligne = studio._etiquette_mots([("quai", (255, 255, 255)), ("muré.", (240, 170, 60))], f)
    assert ligne.mode == "RGBA" and ligne.width > f.getlength("quai muré.") and ligne.getchannel("A").getextrema()[1] == 255
    # la phrase choc s'efface au premier mot de la deuxième phrase ; accroche trop longue : à la dernière virgule avant 7 s
    def dits(phrase, pas):
        return [(m, 0.4 + k * pas, 0.4 + (k + 1) * pas) for k, m in enumerate(phrase.split())]
    assert studio.fin_choc(dits("Un quai derrière un mur, une femme. Je suis conducteur.", 0.35)) == pytest.approx(0.4 + 7 * 0.35)
    assert studio.fin_choc(dits("Roland a 95 ans, il ne m'a jamais vu, et il savait pour mon carnet dans la poche. Il dit.", 0.45)) == pytest.approx(0.4 + 9 * 0.45)
    assert studio.fin_choc(dits("Non. Je", 0.3)) == 2.4 and studio.fin_choc(dits("Une phrase sans virgule " * 6 + "du tout. Puis la suite.", 0.4)) == 7.0
    # STUDIO_CHOC=0 : retour au grand titre et au premier plan choisi par les mots de la phrase
    texte = studio.texte_ecrit(s, 5)
    monkeypatch.setenv("STUDIO_CHOC", "0")
    assert scenes.decouper_plans(studio.minuter(texte, 0.4, 68.0), s, 5, 72.0)[0]["scene"] != "photo:femme"
    monkeypatch.delenv("STUDIO_CHOC")
    # sans les textes écrits (STUDIO_TEXTES=0) : retour à Ollama, donc ici au texte de secours
    monkeypatch.setenv("STUDIO_TEXTES", "0")
    texte, secours = studio.ecrire_episode(b, s, 4)
    assert secours and studio.texte_ecrit(s, 4) is None
    # les séries sans texte écrit ne changent pas
    monkeypatch.delenv("STUDIO_TEXTES")
    assert studio.texte_ecrit(b["series"][1], 1) is None and studio.texte_ecrit(s, 1) is None


def test_studio_tiktok_format_court(monkeypatch):
    """STUDIO_DUREE : 40 secondes par défaut (textes courts, cible de mots réduite), 70 = retour au format long."""
    sys.path.insert(0, os.path.join(RACINE, "revenus", "tiktok"))
    import re
    import studio  # noqa: E402
    import voix  # noqa: E402
    import scenes  # noqa: E402
    monkeypatch.delenv("STUDIO_DUREE", raising=False)
    monkeypatch.delenv("STUDIO_TEXTES", raising=False)
    monkeypatch.setenv("REVENUS_OLLAMA", "0")
    assert studio.duree_cible() == 40 and studio.format_court()
    mini, maxi, plafond = studio.mots_cibles()
    assert 75 <= mini < maxi < plafond <= 105
    b = studio.bible()
    s = next(x for x in b["series"] if x["id"] == "ligne13")
    for n in range(4, 13):
        ep = s["episodes"][n - 1]
        texte, secours = studio.ecrire_episode(b, s, n)
        # même tenue que le texte long : l'accroche de la légende d'abord, le rappel tôt, des phrases courtes
        assert not secours and texte == studio.texte_ecrit(s, n) and texte.startswith(ep["accroche"]), n
        assert 70 <= len(texte.split()) <= 100, n  # mesuré avec la vraie voix : 38 à 41 secondes, carte de fin comprise
        assert max(len(p.split()) for p in re.split(r"(?<=[.!?]) ", texte)) <= 19, n
        debut = " ".join(texte.split()[:45]).lower()
        assert "ligne 13" in debut and ("fantôme" in debut or "n'existe pas" in debut), n
        # la fin reste celle du texte long : même dernière phrase, donc même suspens et même question
        monkeypatch.setenv("STUDIO_DUREE", "70")
        long_ = studio.texte_ecrit(s, n)
        monkeypatch.delenv("STUDIO_DUREE")
        assert len(long_.split()) >= 140 and re.split(r"(?<=[.!?]) ", texte)[-1] == re.split(r"(?<=[.!?]) ", long_)[-1], n
        duree = len(texte.split()) / 2.25
        plans = scenes.decouper_plans(studio.minuter(texte, 0.4, duree), s, n, duree + 4)
        assert plans[-1]["suspens"] and len({p["scene"] for p in plans}) >= 7, n
        if "ouverture" in ep and os.path.isdir(os.path.join(RACINE, "revenus", "tiktok", "medias", "ligne13")):
            assert plans[0]["scene"] == "photo:" + ep["ouverture"], n
    if os.path.isdir(os.path.join(RACINE, "revenus", "tiktok", "medias", "ligne13")):
        # la femme du quai n'apparaît qu'à la toute fin de l'épisode 4 ; la dernière page de l'épisode 12 se lit sur le carnet
        t4 = studio.texte_ecrit(s, 4)
        pl = scenes.decouper_plans(studio.minuter(t4, 0.4, len(t4.split()) / 2.25), s, 4, len(t4.split()) / 2.25 + 4)
        assert [p["scene"] for p in pl].index("photo:femme") >= len(pl) - 2
        t12 = studio.texte_ecrit(s, 12)
        pl = scenes.decouper_plans(studio.minuter(t12, 0.4, len(t12.split()) / 2.25), s, 12, len(t12.split()) / 2.25 + 4)
        sc = [(p["scene"][len("photo:"):], p["texte"]) for p in pl]
        assert all(nom == "carnet" for nom, x in sc if "Prénom" in x or "prochaine" in x)
        assert "nouvelle conductrice" in sc[next(i for i, (nom, _) in enumerate(sc) if nom == "ines")][1]
        assert [nom for nom, _ in sc[-2:]] == ["radio", "radio"]
    prises = voix.attribuer(voix.decouper(studio.texte_ecrit(s, 4), s["voix_personnages"]), "homme", "femme")
    assert [" ".join(p["mots"]) for p in prises if p["voix"] == "femme"] == ["Prochain arrêt, Sainte-Blaise."]
    # pas de texte court pour cet épisode : le texte de secours suit la cible courte (Ollama coupé ici)
    autre = b["series"][1]
    texte, secours = studio.ecrire_episode(b, autre, 1)
    assert secours and texte.startswith(autre["episodes"][0]["accroche"]) and len(texte.split()) <= plafond
    # STUDIO_DUREE=70 : les textes longs et les réglages d'origine reviennent ; une valeur illisible retombe sur 40
    monkeypatch.setenv("STUDIO_DUREE", "70")
    assert not studio.format_court() and studio.mots_cibles() == (180, 230, 270)
    assert 140 <= len(studio.texte_ecrit(s, 4).split()) <= 185
    monkeypatch.setenv("STUDIO_DUREE", "abc")
    assert studio.duree_cible() == 40
    monkeypatch.setenv("STUDIO_DUREE", "5")
    assert studio.duree_cible() == 20
