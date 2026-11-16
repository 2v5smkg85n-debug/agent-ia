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


def test_studio_tiktok_scenes_animees():
    pytest.importorskip("numpy")
    pytest.importorskip("PIL")
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
