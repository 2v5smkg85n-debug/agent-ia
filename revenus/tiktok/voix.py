#!/usr/bin/env python3
"""Voix du studio : deux voix françaises naturelles, calculées sur le VPS, sans clé.
  - la narratrice : Kokoro, voix « ff_siwis » (24 kHz) ;
  - le narrateur  : Supertonic 3, voix « M2 » (44,1 kHz), pour les séries racontées par un homme.

Pourquoi un fichier à part : ces moteurs ont besoin d'un numpy récent, alors que le reste du serveur garde
celui d'Ubuntu. Ils vivent donc dans un petit environnement isolé (revenus/donnees/tiktok/venv_voix),
et ce fichier est lancé deux fois :
  - par studio.py (python du système) : découpe le texte, assemble, pose les silences, soigne le son ;
  - par le python de l'environnement (« --ouvrier travail.json ») : ne fait que synthétiser les phrases.

Ce que la voix gagne par rapport à Piper :
  - une phrase = une prise : le minutage de chaque phrase est exact (sous-titres calés sans deviner) ;
  - un rythme de conteur : accroche franche, silences selon la ponctuation, phrase de suspens ralentie ;
  - chaque série a la voix de son narrateur (« voix » dans bible.json : « homme » ou « femme ») ;
  - une parole rapportée change de voix quand le texte dit qui parle (« une voix de femme annonce : … ») ;
  - les paroles entendues à la radio ou au téléphone sortent d'un vrai haut-parleur (bande étroite, souffle) ;
  - un son fini : coupe-bas, chaleur, air, compression légère, niveau constant d'un épisode à l'autre.

Si aucun moteur n'est installé, studio.py retombe tout seul sur Piper.
"""
import glob
import hashlib
import json
import math
import os
import re
import shutil
import subprocess
import sys
import tempfile
import unicodedata
import urllib.request
import wave

ICI = os.path.dirname(os.path.abspath(__file__))
DOSSIER = os.path.join(os.environ.get("REVENUS_DONNEES") or os.path.join(os.path.dirname(ICI), "donnees"), "tiktok")
VOIX_DIR = os.path.join(DOSSIER, "voix")
VENV = os.path.join(DOSSIER, "venv_voix")
PAQUETS = {"kokoro_onnx": "kokoro-onnx==0.6.1", "supertonic": "supertonic==1.3.1"}  # module → paquet pip
VOIX_KOKORO = "ff_siwis"  # la narratrice : la même comédienne que la voix Piper « siwis », avec un moteur plus naturel
VOIX_HOMME = "M2"  # le narrateur : la voix d'homme la mieux comprise au banc d'essai (M5, M3 aussi graves ; M4, M1 plus aiguës)
DEPOT = "https://github.com/thewh1teagle/kokoro-onnx/releases/download/model-files-v1.0/"
FICHIERS = {  # nom → (taille en octets, sha256)
    "kokoro-v1.0.onnx": (325532387, "7d5df8ecf7d4b1878015a32686053fd0eebe2bc377234608764cc0ef3636a6c5"),
    "voices-v1.0.bin": (28214398, "bca610b8308e8d99f32e6fe4197e7ec01679264efed0cac9140fe9c29f1fbf7d"),
}
SUPERTONIC = os.path.join(VOIX_DIR, "supertonic3")
# version figée du dépôt (celle que le paquet supertonic 1.3.1 attend) : le modèle ne change pas dans notre dos
DEPOT_ST = "https://huggingface.co/Supertone/supertonic-3/resolve/724fb5abbf5502583fb520898d45929e62f02c0b/"
FICHIERS_ST = {
    "onnx/tts.json": (8253, "42078d3aef1cd43ab43021f3c54f47d2d75ceb4e75f627f118890128b06a0d09"),
    "onnx/unicode_indexer.json": (277676, "9bf7346e43883a81f8645c81224f786d43c5b57f3641f6e7671a7d6c493cb24f"),
    "onnx/duration_predictor.onnx": (3700147, "c3eb91414d5ff8a7a239b7fe9e34e7e2bf8a8140d8375ffb14718b1c639325db"),
    "onnx/text_encoder.onnx": (36416150, "c7befd5ea8c3119769e8a6c1486c4edc6a3bc8365c67621c881bbb774b9902ff"),
    "onnx/vector_estimator.onnx": (256534781, "883ac868ea0275ef0e991524dc64f16b3c0376efd7c320af6b53f5b780d7c61c"),
    "onnx/vocoder.onnx": (101424195, "085de76dd8e8d5836d6ca66826601f615939218f90e519f70ee8a36ed2a4c4ba"),
    "voice_styles/M1.json": (291748, "e35604687f5d23694b8e91593a93eec0e4eca6c0b02bb8ed69139ab2ea6b0a5b"),
    "voice_styles/M2.json": (292055, "b76cbf62bac707c710cf0ae5aba5e31eea1a6339a9734bfae33ab98499534a50"),
    "voice_styles/M3.json": (290198, "ea1ac35ccb91b0d7ecad533a2fbd0eec10c91513d8951e3b25fbba99954e159b"),
    "voice_styles/M4.json": (291522, "ca8eefad4fcd989c9379032ff3e50738adc547eeb5e221b82593a6d7b3bac303"),
    "voice_styles/M5.json": (291469, "dd22b92740314321f8ae11c5e87f8dd60d060f15dd3a632b5adf77f471f77af2"),
    "LICENSE": (15007, "0d944a9110fed9a9602d60e0423a272903e7bd21ab060490774efc77c2275e9f"),
}
FINS = (".", "!", "?", "…")
MOTS_RADIO = ("radio", "annonce", "haut-parleur", "hautparleur", "interphone", "gresill", "frequence", "repondeur",
              "telephone", "combine", "enregistrement", "micro", "messagerie", "talkie")
# qui parle ? Seulement des mots sans ambiguïté : dans le doute, c'est le narrateur qui lit la phrase.
MOTS_FEMME = {"femme", "feminine", "dame", "fille", "fillette", "mere", "maman", "soeur", "voisine", "madame",
              "mademoiselle", "mme", "gardienne", "conductrice", "infirmiere", "inconnue"}
MOTS_HOMME = {"homme", "masculine", "monsieur", "garcon", "pere", "papa", "frere", "voisin", "gardien", "conducteur",
              "regulateur", "syndic", "facteur", "inconnu"}
# « je dis : … », « je demande à Josiane : … » : c'est le narrateur qui parle, sa voix ne change pas
VERBES_DIRE = {"dis", "demande", "reponds", "murmure", "lance", "crie", "souffle", "repete", "ajoute", "chuchote", "appelle",
               "articule", "insiste", "hurle", "bredouille", "annonce", "ordonne", "supplie", "interroge", "previens", "lis", "ecris"}
CLITIQUES = {"me", "m", "te", "t", "lui", "leur", "le", "la", "l", "les", "ne", "n", "y", "en", "nous", "vous"}
ONDES = ("radio", "annonce", "haut-parleur", "hautparleur", "gresill", "frequence")  # là où parle la « voix_radio » de la série


def env(nom, defaut):
    return os.environ.get(nom, defaut)


def sans_accent(s):
    return "".join(c for c in unicodedata.normalize("NFD", s.lower()) if unicodedata.category(c) != "Mn")


# ----------------------------------------------------------------------------- texte → prises
def jetons_cites(texte):
    """Les mêmes mots que studio.jetons (ceux des sous-titres), avec pour chacun : est-il entre guillemets ?"""
    brut = texte.replace("«", " \x01 ").replace("»", " \x02 ").replace("“", " \x01 ").replace("”", " \x02 ").replace('"', " \x03 ")
    mots, cites, dedans = [], [], False
    for m in brut.split():
        if m == "\x01":
            dedans = True
        elif m == "\x02":
            dedans = False
        elif m == "\x03":
            dedans = not dedans
        elif re.search(r"\w", m) or not mots:
            mots.append(m)
            cites.append(dedans)
        elif m not in (".", "…") or not mots[-1].endswith(FINS):
            mots[-1] += ("" if m in (".", ",", "…") else " ") + m
    return mots, cites


def prononcer(texte):
    """Écrit le texte comme il doit être dit (les sous-titres, eux, gardent l'écriture d'origine)."""
    t = texte

    def heure(m):
        h, mn = int(m.group(1)), int(m.group(2) or 0)
        return f"{h} heure{'s' if h > 1 else ''}" + (f" {mn}" if mn else "")

    t = re.sub(r"\b(\d{1,2}) ?h ?(\d{2})?\b(?![\w'’])", heure, t)
    t = re.sub(r"\bkm ?/ ?h\b", "kilomètres heure", t)
    t = re.sub(r"\bn ?°\s*", "numéro ", t)
    t = re.sub(r"(\d)\s*%", r"\1 pour cent", t)
    t = re.sub(r"(\d)\s*€", r"\1 euros", t)
    t = re.sub(r"\b(\d+)([A-Z])\b", r"\1 \2", t)  # « 7B » → « 7 B »
    t = re.sub(r"\b(\d{1,3}) (\d{3})\b", r"\1\2", t)  # « 1 200 » → « 1200 »
    t = t.replace("&", " et ").replace("—", ", ").replace("–", ", ")
    t = re.sub(r"[«»“”\"]", " ", t)
    t = re.sub(r"\s+([,.;!?…])", r"\1", t)
    t = re.sub(r",\s*,", ",", t)
    return re.sub(r"\s+", " ", t).strip()


_UNITES = ["zéro", "un", "deux", "trois", "quatre", "cinq", "six", "sept", "huit", "neuf", "dix", "onze", "douze", "treize",
           "quatorze", "quinze", "seize", "dix-sept", "dix-huit", "dix-neuf"]
_DIZAINES = {2: "vingt", 3: "trente", 4: "quarante", 5: "cinquante", 6: "soixante", 8: "quatre-vingt"}
# Écriture « à l'oreille » pour Supertonic, qui lit les lettres : écrits comme dans le dictionnaire, les composés sortent
# en deux nombres (« soixante… dix-sept », « soixante… et onze ») et le « x » de dix ou de soixante s'entend parfois.
_UNITES_O = _UNITES[:17] + ["dissète", "dizuit", "dizneuf"]
_DIZAINES_O = dict(_DIZAINES)
_DIZAINES_O[6] = "soissante"


def _sous_cent(n, o=False):
    unites, dizaines = (_UNITES_O, _DIZAINES_O) if o else (_UNITES, _DIZAINES)
    if n < 20:
        return unites[n]
    d, u = divmod(n, 10)
    if d in (7, 9):  # soixante-dix, quatre-vingt-onze
        if (d, u) == (7, 1):
            return "soissantéonze" if o else "soixante et onze"
        if o and u == 0:
            return dizaines[d - 1] + "-disse"
        return dizaines[d - 1] + "-" + unites[10 + u]
    if u == 0:
        return dizaines[d] + ("s" if d == 8 else "")
    if u == 1 and d != 8:
        return (dizaines[d].rstrip("e") + "éun") if o else dizaines[d] + " et un"
    return dizaines[d] + "-" + unites[u]


def _sous_mille(n, final=True, o=False):
    c, r = divmod(n, 100)
    if c == 0:
        t = _sous_cent(r, o)
        return t if final or not t.endswith("vingts") else t[:-1]  # quatre-vingt mille
    t = "cent" if c == 1 else _UNITES[c] + " cent"
    if r == 0:
        return t + ("s" if c > 1 and final else "")
    return t + " " + _sous_cent(r, o)


def nombre_en_lettres(n, oreille=False):
    """640 → « six cent quarante », 2043 → « deux mille quarante-trois ».
    oreille : l'écriture que Supertonic dit d'une traite (77 → « soissante-dissète », 1971 → « mille neuf cent soissantéonze »)."""
    n = int(n)
    if n >= 10 ** 9:
        return " ".join(_UNITES[int(c)] for c in str(n))
    if n < 1000:
        return _sous_mille(n, o=oreille)
    m, r = divmod(n, 10 ** 6)
    k, r = divmod(r, 1000)
    p = []
    if m:
        p.append("un million" if m == 1 else _sous_mille(m, o=oreille) + " millions")
    if k:
        p.append("mille" if k == 1 else _sous_mille(k, final=False, o=oreille) + " mille")
    if r:
        p.append(_sous_mille(r, o=oreille))
    return " ".join(p)


# « six ans », « dix heures » : la liaison en « z » ne se fait que devant le nom compté
_SANS_LIAISON = {"et", "ou", "à", "au", "aux", "en", "il", "ils", "elle", "elles", "on", "un", "une", "avec", "est", "était", "étaient", "ont", "a",
                 "y", "alors", "encore", "aussi", "après", "avant", "ici", "entre", "environ", "avait", "avaient", "ou", "où", "enfin", "ensuite"}
_LETTRES = {"B": "bé", "C": "cé", "D": "dé", "F": "èf", "G": "gé", "H": "ache", "J": "ji", "K": "ka", "L": "èl", "M": "èm", "N": "èn", "P": "pé",
            "Q": "ku", "R": "èr", "S": "ès", "T": "té", "V": "vé", "X": "ix", "Z": "zèd"}
_ECRITS = None
# les mots que Supertonic dit de travers quand ils sont écrits comme dans le dictionnaire → l'écriture qu'il dit juste
# (vérifié par transcription automatique : « terminu », « parpaigne », « tende » avant, le bon mot après)
_MOTS_OREILLE = {"terminus": "terminusse", "parpaing": "parpain", "parpaings": "parpains"}
_MOTS_OREILLE_FIN = {"tend": "tan"}  # seulement devant une ponctuation : « ce qu'elle te tend, dit Roland » sortait « tende »


def _ecrits():
    """Les nombres écrits en lettres par l'auteur, de la forme du dictionnaire à la forme dite (les plus longs d'abord)."""
    global _ECRITS
    if _ECRITS is None:
        paires = {}
        for n in range(17, 100):
            a, b = _sous_cent(n), _sous_cent(n, o=True)
            if a != b:
                paires[a] = b
                if a.endswith(" et un"):
                    paires[a + "e"] = b + "e"  # vingt et une
        _ECRITS = sorted(paires.items(), key=lambda x: -len(x[0]))
    return _ECRITS


def a_l_oreille(texte):
    """Réécrit pour Supertonic les nombres déjà en lettres, marque la liaison de « six » et « dix » devant un nom,
    et corrige les quelques mots qu'il dit de travers (_MOTS_OREILLE)."""
    t = texte
    for ecrit, dit in _ecrits():
        t = re.sub(r"(?<![\w-])" + re.escape(ecrit) + r"(?![\w-])",
                   lambda m, dit=dit: dit.capitalize() if m.group(0)[0].isupper() else dit, t, flags=re.I)

    def liaison(m):
        suivant = m.group(3).lower()
        if suivant in _SANS_LIAISON or (len(suivant) < 3 and suivant not in ("an",)):
            return m.group(0)
        return m.group(1)[:2] + ("z" if m.group(1).lower().endswith("x") else "se") + m.group(2) + m.group(3)

    t = re.sub(r"\b((?:si|di)x|disse)\b( )(h?[aeiouyéèêàâîôûœ]\w*)", liaison, t, flags=re.I)

    def mot(m):
        dit = _MOTS_OREILLE.get(m.group(1).lower()) or (m.group(2) and _MOTS_OREILLE_FIN.get(m.group(1).lower()))
        if not dit:
            return m.group(0)
        return (dit.capitalize() if m.group(1)[0].isupper() else dit) + m.group(2)

    return re.sub(r"(?<![\w'’-])([A-Za-zÀ-ÿ]+)(?![\w'’-])([,.;:!?…]?)", mot, t)


def en_lettres(texte, oreille=False):
    """Écrit les nombres en toutes lettres : Supertonic lit le texte tel quel et bute sur les chiffres.
    oreille : la forme dite d'une traite (voir nombre_en_lettres), y compris pour les nombres que l'auteur a écrits en lettres."""
    def ordinal(m):
        t = nombre_en_lettres(m.group(1))
        if t.endswith("f"):
            t = t[:-1] + "v"
        elif t.endswith("q"):
            t += "u"
        elif t.endswith("e") or (t.endswith("s") and not t.endswith("trois")):
            t = t[:-1]
        return t + "ième"

    t = re.sub(r"\b1(er|re|ère)\b", lambda m: "premier" if m.group(1) == "er" else "première", texte)
    t = re.sub(r"\b(\d+)(?:e|è|ème|ième)\b", ordinal, t)
    t = re.sub(r"\b(\d+),(\d+)\b", lambda m: nombre_en_lettres(m.group(1), oreille) + " virgule " + nombre_en_lettres(m.group(2), oreille), t)
    if oreille:  # « 7 B » : la lettre dite par son nom, sinon elle se colle au mot suivant
        t = re.sub(r"\b(\d+) ([A-Z])\b", lambda m: m.group(1) + " " + _LETTRES.get(m.group(2), m.group(2)), t)
    t = re.sub(r"\d+", lambda m: nombre_en_lettres(m.group(0), oreille), t)
    return a_l_oreille(t) if oreille else t


def narrateur_parle(contexte):
    """Vrai si la phrase qui annonce la parole dit que c'est le narrateur lui-même qui parle (« je lui demande : … »)."""
    mots = re.findall(r"[a-z]+", sans_accent(contexte or ""))
    for i, m in enumerate(mots):
        if m in ("je", "j"):  # « je dis », « je lui demande », « je ne réponds » — pas « je monte le son, la radio annonce »
            j = i + 1
            while j < len(mots) and j < i + 4 and mots[j] in CLITIQUES:
                j += 1
            if j < len(mots) and mots[j] in VERBES_DIRE:
                return True
    return False


def genre_cite(contexte, noms=None):
    """« homme », « femme » ou None : la voix d'une parole rapportée, quand la phrase qui l'annonce le dit clairement.
    noms = {"homme": [prénoms], "femme": [prénoms]} : les personnages de la série (bible.json).
    Dans le doute (personne de nommé, deux personnes nommées, le narrateur qui parle) : None, le narrateur lit la phrase."""
    if narrateur_parle(contexte):
        return None
    mots = set(re.findall(r"[a-z]+", sans_accent(contexte or "")))
    noms = noms or {}
    f = mots & (MOTS_FEMME | {sans_accent(x) for x in noms.get("femme", [])})
    h = mots & (MOTS_HOMME | {sans_accent(x) for x in noms.get("homme", [])})
    if bool(f) == bool(h):
        return None
    return "femme" if f else "homme"


def decouper(texte, noms=None):
    """Découpe le texte en prises : une par phrase, les paroles rapportées à part.
    → [{"mots": [...], "texte": à dire, "radio": bool (sort d'un haut-parleur), "ondes": bool (annonce radio),
        "cite": bool, "genre": qui parle (paroles rapportées),
        "fin": bool (fin de phrase), "rang": n° de phrase}]"""
    mots, cites = jetons_cites(texte)
    phrases, debut = [], 0
    for i, m in enumerate(mots):
        if m.endswith(FINS) or i == len(mots) - 1:
            phrases.append((debut, i + 1))
            debut = i + 1
    prises, avant = [], ""
    for rang, (a, b) in enumerate(phrases):
        marques = list(cites[a:b])
        if not any(marques):
            # parole annoncée par deux-points, sans guillemets : « annonce : Prochain arrêt, Sainte-Blaise. »
            for k in range(a, b - 1):
                if mots[k].endswith(":") and mots[k + 1][:1].isupper():
                    marques = [j > k for j in range(a, b)]
                    break
        hors = sans_accent(" ".join(m for m, c in zip(mots[a:b], marques) if not c))
        contexte = hors if hors.strip() else avant
        moi = narrateur_parle(contexte)  # ses propres mots : ni changement de voix, ni haut-parleur
        radio = not moi and any(cle in contexte for cle in MOTS_RADIO)
        ondes = radio and any(cle in contexte for cle in ONDES)
        genre = genre_cite(contexte, noms)
        i = a
        while i < b:
            j = i
            while j < b and marques[j - a] == marques[i - a]:
                j += 1
            cite = marques[i - a]
            prises.append({"mots": mots[i:j], "texte": prononcer(" ".join(mots[i:j])), "cite": cite,
                           "radio": bool(cite and radio), "ondes": bool(cite and ondes), "genre": genre if cite else None,
                           "fin": j == b, "rang": rang})
            i = j
        avant = hors if hors.strip() else avant
    return prises


def attribuer(prises, narrateur="femme", radio=None):
    """Qui dit quoi. Le narrateur porte le récit ; une parole rapportée ne change de voix que si le texte dit qui parle
    (« une voix de femme annonce : … ») ou, à la radio, si la série a prévu une voix (« voix_radio » dans bible.json)."""
    narrateur = "homme" if narrateur == "homme" else "femme"
    dialogues = env("STUDIO_DIALOGUES", "1") != "0"
    for p in prises:
        v = narrateur
        if dialogues and p.get("cite"):
            if p.get("genre") in ("homme", "femme"):
                v = p["genre"]
            elif p.get("ondes") and radio in ("homme", "femme"):
                v = radio
        p["voix"] = v
    return prises


def allures(prises, base=None):
    """Vitesse de diction et silence après chaque prise : le rythme d'un conteur, pas d'un lecteur."""
    base = float(base if base is not None else env("STUDIO_ALLURE", "0.90"))
    dernier = prises[-1]["rang"] if prises else 0
    longueur = {}
    for p in prises:
        longueur[p["rang"]] = longueur.get(p["rang"], 0) + len(p["mots"])
    for k, p in enumerate(prises):
        fin = p["mots"][-1] if p["mots"] else "."
        n = longueur[p["rang"]]  # la phrase entière : ses morceaux gardent la même allure
        v = base
        if p["rang"] == 0:
            v = base * 1.04  # l'accroche : franche
        elif p["rang"] == dernier and dernier > 0:
            v = base * 0.93  # le suspens : on retient
        elif n <= 4:
            v = base * 0.96  # les phrases courtes pèsent
        if p["radio"]:
            v = min(v, base * 0.95)
        if not p["fin"]:
            pause = 0.30 if fin.endswith(":") else 0.20
        elif fin.endswith("…"):
            pause = 0.70
        elif fin.endswith(("?", "!")):
            pause = 0.52
        else:
            pause = 0.44 + (0.06 if n <= 4 else 0.0)
        if p["rang"] == 0 and p["fin"]:
            pause += 0.14  # laisser l'accroche résonner
        if p["fin"] and p["rang"] == dernier - 1:
            pause += 0.40  # le silence avant la dernière phrase
        pause += 0.05 * math.sin(k * 2.4)  # jamais deux silences identiques
        if k == len(prises) - 1:
            pause = 0.0
        p["vitesse"], p["pause"] = round(max(0.6, min(1.3, v)), 3), round(max(0.0, pause), 3)
        p["rel"] = round(v / base, 3)  # l'allure relative, la même quel que soit le moteur
    return prises


# ----------------------------------------------------------------------------- son
def lire_wav(chemin):
    import numpy as np
    with wave.open(chemin) as w:
        sr, n, can = w.getframerate(), w.getnframes(), w.getnchannels()
        a = np.frombuffer(w.readframes(n), dtype="<i2").astype("float32") / 32768.0
    if can > 1:
        a = a.reshape(-1, can).mean(axis=1)
    return a, sr


def ecrire_wav(chemin, a, sr):
    import numpy as np
    with wave.open(chemin, "w") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(sr)
        w.writeframes((np.clip(a, -1, 1) * 32767).astype("<i2").tobytes())


def reechantillonner(a, sr, sr2):
    """Change la fréquence d'échantillonnage d'une prise (par le spectre : propre, sans dépendance)."""
    import numpy as np
    if sr == sr2 or len(a) < 16:
        return a
    n = len(a)
    m = int(round(n * float(sr2) / sr))
    spectre = np.fft.rfft(a)
    neuf = np.zeros(m // 2 + 1, dtype=spectre.dtype)
    k = min(len(spectre), len(neuf))
    neuf[:k] = spectre[:k]
    return (np.fft.irfft(neuf, n=m) * (m / float(n))).astype("float32")


def rogner(a, sr, seuil=0.006, marge=0.025):
    """Retire le silence de début et de fin d'une prise, avec un fondu de 6 ms (pas de clic)."""
    import numpy as np
    fort = np.flatnonzero(np.abs(a) > seuil)
    if not len(fort):
        return a[:0]
    i0, i1 = max(0, fort[0] - int(marge * sr)), min(len(a), fort[-1] + int(marge * 2 * sr))
    a = a[i0:i1].copy()
    n = min(int(0.006 * sr), len(a) // 2)
    if n > 1:
        rampe = np.linspace(0, 1, n, dtype="float32")
        a[:n] *= rampe
        a[-n:] *= rampe[::-1]
    return a


def _filtrer(a, sr, courbe):
    """Égalisation sans déphasage : on multiplie le spectre par une courbe de gain f(Hz) → gain."""
    import numpy as np
    if len(a) < 64:
        return a
    spectre = np.fft.rfft(a)
    f = np.maximum(np.fft.rfftfreq(len(a), 1.0 / sr), 1.0)
    return np.fft.irfft(spectre * courbe(f), n=len(a)).astype("float32")


def _cloche(f, centre, octaves, db):
    import numpy as np
    return 10 ** (db * np.exp(-(np.log2(f / centre) / octaves) ** 2) / 20)


def _niveau(a, sr):
    """Niveau moyen des passages parlés (les silences ne comptent pas)."""
    import numpy as np
    if not len(a):
        return 0.0
    pas = max(1, int(0.05 * sr))
    n = len(a) // pas
    if n < 1:
        return float(np.sqrt(np.mean(a ** 2)))
    e = np.sqrt(np.mean(a[:n * pas].reshape(n, pas) ** 2, axis=1))
    parle = e[e > max(1e-4, e.max() * 0.08)]
    return float(np.sqrt(np.mean(parle ** 2))) if len(parle) else 0.0


def _lisser(x, n):
    import numpy as np
    if n < 2 or len(x) < n:
        return x
    c = np.cumsum(np.concatenate([[0.0], x.astype("float64")]))
    m = (c[n:] - c[:-n]) / n
    return np.concatenate([np.full(n // 2, m[0]), m, np.full(len(x) - len(m) - n // 2, m[-1])]).astype("float32")


def limiter(a, sr, plafond=0.93):
    """Limiteur à anticipation : le gain baisse en douceur 4 ms avant chaque crête, sans écrêter ni déformer le timbre."""
    import numpy as np
    pas = max(1, int(0.002 * sr))
    n = -(-len(a) // pas)
    if n < 8 or float(np.abs(a).max()) <= plafond:
        return a.astype("float32")
    blocs = np.zeros(n * pas, dtype="float32")
    blocs[:len(a)] = np.abs(a)
    crete = blocs.reshape(n, pas).max(axis=1)
    large = crete.copy()
    for d in (1, 2, 3):  # la crête « déborde » sur ses voisins : le gain est déjà bas quand elle arrive
        large[d:] = np.maximum(large[d:], crete[:-d])
        large[:-d] = np.maximum(large[:-d], crete[d:])
    gain = np.minimum(1.0, plafond / np.maximum(large, 1e-6))
    gain = _lisser(gain, 3)
    g = np.interp(np.arange(len(a)), np.arange(n) * pas + pas / 2.0, gain)
    return np.clip(a * g, -0.985, 0.985).astype("float32")


def soigner(a, sr, cible=0.175, grave=False):
    """Finition de la narration : coupe-bas, un peu de chaleur et d'air, compression douce, niveau constant.
    grave=True : voix d'homme. Son timbre grave se perd sur le haut-parleur d'un téléphone (rien sous 300 à 400 Hz) et
    ses consonnes s'y noient : moins de coffre, un creux dans le bas-médium, de la présence autour de 3 kHz, là où
    s'entendent les consonnes. Au banc d'essai (haut-parleur de téléphone + bruit de fond, transcription automatique),
    un quart à un tiers de mots mal compris en moins. STUDIO_NETTETE=0 revient à l'ancienne finition, plus ronde."""
    import numpy as np
    if not len(a) or float(np.abs(a).max()) < 1e-4:
        return a
    net = grave and env("STUDIO_NETTETE", "1") != "0"

    def courbe(f):
        if net:
            g = 1.0 / np.sqrt(1.0 + (60.0 / f) ** 8)  # coupe-bas
            g = g * _cloche(f, 130.0, 0.9, 0.5)  # un reste de chaleur
            g = g * _cloche(f, 270.0, 0.9, -2.0)  # le bas-médium, qui empâte la diction
            g = g * _cloche(f, 3100.0, 1.0, 3.3)  # la présence : les consonnes
            return g * 10 ** (2.0 / (1.0 + (6500.0 / f) ** 4) / 20)  # air
        g = 1.0 / np.sqrt(1.0 + ((52.0 if grave else 70.0) / f) ** 8)  # coupe-bas : ronflements et « pop »
        g = g * _cloche(f, 130.0 if grave else 190.0, 0.9, 1.4)  # chaleur
        g = g * _cloche(f, 3400.0, 0.5, -1.0)  # un peu moins de dureté
        return g * 10 ** (1.6 / (1.0 + (6500.0 / f) ** 4) / 20)  # air

    a = _filtrer(a, sr, courbe)
    # compression 2:1 au-dessus du niveau moyen : les fins de phrases ne tombent plus, les éclats ne dépassent plus
    env_ = np.sqrt(_lisser(a * a, int(0.020 * sr)) + 1e-12)
    ref = max(_niveau(a, sr), 1e-4)
    trop = np.maximum(0.0, 20 * np.log10(env_ / ref) + 1.0)
    gain = 10 ** (-_lisser(trop * 0.5, int(0.070 * sr)) / 20)
    a = a * gain
    a = a * (cible / max(_niveau(a, sr), 1e-4))
    return limiter(a, sr)


def effet_radio(a, sr, graine=0, cible=0.155):
    """La même voix, entendue dans un haut-parleur de cabine : bande étroite, saturation, souffle, « clac » d'émission."""
    import numpy as np
    if not len(a):
        return a
    rng = np.random.default_rng(1000 + graine)

    def bande(f):
        g = 1.0 / np.sqrt(1.0 + (360.0 / f) ** 8) / np.sqrt(1.0 + (f / 3300.0) ** 8)
        return g * _cloche(f, 1800.0, 0.7, 3.5)

    garde = int(0.09 * sr)
    v = np.concatenate([np.zeros(garde, dtype="float32"), a, np.zeros(garde, dtype="float32")])
    v = _filtrer(v, sr, bande)
    v = v / max(float(np.abs(v).max()), 1e-4)
    v = np.tanh(v * 1.7) / math.tanh(1.7)  # saturation légère du petit haut-parleur : les mots restent nets
    souffle = _filtrer(rng.standard_normal(len(v)).astype("float32"), sr, bande)
    souffle = souffle / max(float(np.abs(souffle).max()), 1e-4)
    porte = np.ones(len(v), dtype="float32") * 0.022
    porte[:garde] = np.linspace(0.22, 0.03, garde)  # ouverture de la fréquence
    porte[-garde:] = np.linspace(0.03, 0.20, garde)  # relâchement
    v = v + souffle * porte
    v = _filtrer(v, sr, bande)
    v = v * (cible / max(_niveau(v, sr), 1e-4))
    n = int(0.004 * sr)
    v[:n] *= np.linspace(0, 1, n)
    v[-n:] *= np.linspace(1, 0, n)
    return limiter(v, sr)


def _dit(mot):
    """Le mot tel qu'il est prononcé : les chiffres en lettres, « h » pour « heures »."""
    if re.fullmatch(r"\W*h\W*", mot):
        return "heures"
    return en_lettres(prononcer(mot)) if re.search(r"\d", mot) else mot


_MOTS_NOMBRES = set(_UNITES[2:]) | set(_DIZAINES.values()) | {"cent", "cents", "mille", "vingts", "quatre-vingt", "quatre-vingts"}


def est_nombre(mot):
    """Vrai pour « 1972 », « 7B », « soixante-dix-sept », « onze »."""
    m = re.sub(r"[^\w-]", "", mot.lower())
    return bool(re.search(r"\d", m)) or (bool(m) and all(x in _MOTS_NOMBRES for x in m.split("-")))


def resserrer(a, sr, mots, poids, garde=0.045, mini=0.11):
    """Retire les hésitations que Supertonic glisse au milieu d'un nombre long (« mille neuf cent… quatre-vingt-cinq ») :
    un silence qui tombe pendant un nombre est ramené à 45 ms. Les pauses des virgules et des fins de groupe ne bougent pas."""
    import numpy as np
    total = float(sum(poids)) or 1.0
    if not len(a) or len(poids) != len(mots):
        return a
    # où tombent les nombres : deux estimations (le poids des sous-titres, et le compte brut des lettres, plus large :
    # un nombre dit avec une hésitation dure plus longtemps), on garde l'enveloppe des deux. On n'élargit que vers l'avant.
    def reperer(pds):
        tout, res, x, k = float(sum(pds)) or 1.0, [], 0.0, 0
        while k < len(mots):
            if not est_nombre(mots[k]):
                x += pds[k]
                k += 1
                continue
            x0 = x
            while k < len(mots) and (est_nombre(mots[k]) or (mots[k] in ("et", "h") and k + 1 < len(mots) and est_nombre(mots[k + 1]))):
                x += pds[k]
                k += 1
                if mots[k - 1].endswith((",", ";", ":", ".", "!", "?", "…")):
                    break
            fin = mots[k - 1].endswith((",", ";", ":", ".", "!", "?", "…"))
            res.append((x0 / tout * len(a), x / tout * len(a), x - x0, fin))
        return res

    zones = []
    for (d1, f1, w, fin), (d2, f2, _, _) in zip(reperer(poids), reperer(poids_mots(mots, large=True))):
        if w >= 0.09 * total or w >= 9:  # « six » ou « onze » se disent d'une traite : rien à resserrer
            zones.append((min(d1, d2) - 0.15 * sr, max(f1, f2) - (0.30 if fin else 0.12) * sr))
    if not zones:
        return a
    pas = int(0.005 * sr)
    n = len(a) // pas
    if n < 40:
        return a
    e = np.sqrt(np.mean(a[:n * pas].reshape(n, pas) ** 2, axis=1))
    calme = (e < max(0.004, float(e.max()) * 0.035)).astype("int8")
    bords = np.flatnonzero(np.diff(np.concatenate([[0], calme, [0]])))
    # les silences des virgules (ceux que les sous-titres suivent) sont gardés, même au ras d'un nombre : « 1972, et… »
    morceaux = respirations(mots, a, sr, poids)
    gardes = [(x[3], y[2]) for x, y in zip(morceaux, morceaux[1:])]
    coupes = []
    for d, f in zip(bords[::2], bords[1::2]):
        d, f = d * pas, f * pas
        if (f - d) / sr < mini or d < 0.08 * sr or f > len(a) - 0.08 * sr:
            continue
        if any(d < g1 and f > g0 for g0, g1 in gardes):
            continue
        if any(z0 < (d + f) / 2 < z1 for z0, z1 in zones):
            coupes.append((d + int(garde / 2 * sr), f - int(garde / 2 * sr)))
    if not coupes:
        return a
    morceaux, x, fondu = [], 0, max(2, int(0.004 * sr))
    for d, f in coupes:
        m = a[x:d].copy()
        m[-fondu:] *= np.linspace(1, 0, fondu, dtype="float32")
        morceaux.append(m)
        x = f
    morceaux.append(a[x:].copy())
    for m in morceaux[1:]:
        m[:fondu] *= np.linspace(0, 1, fondu, dtype="float32")
    return np.concatenate(morceaux)


def poids_mots(mots, phonemes=None, large=False):
    """Part de chaque mot dans la durée d'une prise. Avec les phonèmes de Kokoro (un groupe par mot), le poids suit
    ce qui est réellement prononcé (« aux horaires » ne compte pas ses lettres muettes)."""
    sons = phonemes.split() if phonemes else []
    sons = [s for s in sons if re.sub(r"[\W_]", "", s)]
    res = []
    for k, m in enumerate(mots):
        if len(sons) == len(mots):
            p = len(re.sub(r"[ˈˌː\W_]", "", sons[k])) + 0.6
        else:  # « 1972 » dure le temps de « mille neuf cent soixante-douze », pas celui de quatre lettres
            n = len(re.sub(r"[^\w]", "", _dit(m)))
            if n > 8 and re.search(r"\d", m) and not large:
                n = 8 + 0.5 * (n - 8)  # beaucoup de lettres muettes dans les grands nombres (mesuré sur la voix d'homme)
            p = (n + 1.2) * 0.8
        if m.endswith((",", ";", ":", ".", "!", "?", "…")):
            p += 1.8  # la dernière syllabe avant une pause s'allonge
        res.append(p)
    return res


def respirations(mots, a, sr, poids=None, mini=0.045):
    """Découpe une prise à ses virgules quand Kokoro y a marqué un silence : les sous-titres collent à la diction.
    Chaque virgule prend le silence le plus proche de l'endroit où on l'attend (et le plus long à distance égale) ;
    les micro-silences des consonnes (« t », « p », « k ») sont ainsi écartés.
    → [(i0, i1, s0, s1)] : mots[i0:i1] sont dits entre les échantillons s0 et s1."""
    import numpy as np
    entier = [(0, len(mots), 0, len(a))]
    virgules = [k for k, m in enumerate(mots[:-1]) if m.endswith((",", ";", ":"))]
    pas = int(0.005 * sr)
    n = len(a) // pas
    if not virgules or n < 40:
        return entier
    poids = list(poids) if poids and len(poids) == len(mots) else [len(m) + 1.0 for m in mots]
    e = np.sqrt(np.mean(a[:n * pas].reshape(n, pas) ** 2, axis=1))
    calme = (e < max(0.004, float(e.max()) * 0.035)).astype("int8")
    bords = np.flatnonzero(np.diff(np.concatenate([[0], calme, [0]])))
    trous = [(x * pas, y * pas) for x, y in zip(bords[::2], bords[1::2])
             if (y - x) * pas / sr >= mini and x * pas > 0.08 * sr and y * pas < len(a) - 0.08 * sr]
    res, i0, s0 = [], 0, 0
    for k in virgules:
        reste = sum(poids[i0:]) or 1.0
        attendu = s0 + (len(a) - s0) * sum(poids[i0:k + 1]) / reste
        tolerance = max(0.22 * sr, 0.16 * (len(a) - s0))
        cand = [(abs((x + y) / 2 - attendu) - 0.8 * (y - x), x, y) for x, y in trous
                if x > s0 + 0.05 * sr and abs((x + y) / 2 - attendu) < tolerance]
        if not cand:
            continue  # pas de silence à cette virgule : elle reste dans le morceau en cours
        _, x, y = min(cand)
        res.append((i0, k + 1, s0, x))
        i0, s0 = k + 1, y
    res.append((i0, len(mots), s0, len(a)))
    return res


def assembler(prises, sons, sr, graine=0):
    """Monte les prises bout à bout avec leurs silences. → (piste, repères)
    repères = [(mots, début, fin, poids)] en secondes depuis le début de la voix : le minutage exact des sous-titres."""
    import numpy as np
    morceaux, reperes, t = [], [], 0
    narrations = {}  # voix → rangs des morceaux
    for k, (p, a) in enumerate(zip(prises, sons)):
        a = rogner(a, sr) if a is not None else np.zeros(0, dtype="float32")
        if not len(a):  # prise muette (ponctuation seule) : un court silence garde le compte des mots
            a = np.zeros(int(0.25 * sr), dtype="float32")
        if p["radio"]:
            a = effet_radio(a, sr, graine + k)
        else:
            narrations.setdefault(p.get("voix", "femme"), []).append(len(morceaux))
        morceaux.append(a)
        if p["radio"]:  # 0,09 s de garde de chaque côté (ouverture et relâchement de la fréquence)
            reperes.append((list(p["mots"]), t / sr + 0.09, (t + len(a)) / sr - 0.09, poids_mots(p["mots"], p.get("phonemes"))))
        else:
            poids = poids_mots(p["mots"], p.get("phonemes"))
            if profil(p.get("voix", "femme"))[0] == "supertonic" and env("STUDIO_RESSERRER", "1") != "0":
                a = resserrer(a, sr, p["mots"], poids)
                morceaux[-1] = a
            for i0, i1, s0, s1 in respirations(p["mots"], a, sr, poids):
                reperes.append((list(p["mots"][i0:i1]), (t + s0) / sr, (t + s1) / sr, poids[i0:i1]))
        t += len(a)
        blanc = np.zeros(int(p.get("pause", 0.4) * sr), dtype="float32")
        morceaux.append(blanc)
        t += len(blanc)
    # chaque voix est soignée d'un seul tenant (même niveau partout), les passages radio restent tels quels
    for genre, narration in narrations.items():
        pos, tout = [], []
        for i in narration:
            pos.append((i, len(morceaux[i])))
            tout.append(morceaux[i])
            tout.append(np.zeros(int(0.12 * sr), dtype="float32"))
        homme = genre == "homme"  # une voix grave sonne moins fort à niveau égal : un décibel de plus
        fini = soigner(np.concatenate(tout), sr, cible=0.195 if homme else 0.175, grave=homme)
        x = 0
        for i, n in pos:
            morceaux[i] = fini[x:x + n]
            x += n + int(0.12 * sr)
    piste = np.concatenate(morceaux) if morceaux else np.zeros(0, dtype="float32")
    return piste, reperes


# ----------------------------------------------------------------------------- moteurs
def python_voix():
    """Le python qui fait tourner les voix : celui de l'environnement isolé, sinon le python courant."""
    for cand in (env("STUDIO_PYTHON_VOIX", ""), os.path.join(VENV, "bin", "python")):
        if cand and os.path.exists(cand):
            return cand
    return sys.executable


def _module_dispo(py, module):
    if os.path.abspath(py) == os.path.abspath(sys.executable):
        try:
            import importlib.util
            return importlib.util.find_spec(module) is not None
        except Exception:
            return False
    racine = os.path.dirname(os.path.dirname(os.path.abspath(py)))
    return bool(glob.glob(os.path.join(racine, "lib", "python*", "site-packages", module)))


def moteurs():
    """Les moteurs prêts à servir (paquet installé et modèle téléchargé) : {"kokoro": python, "supertonic": python}."""
    py, res = python_voix(), {}
    if all(os.path.exists(os.path.join(VOIX_DIR, f)) for f in FICHIERS) and _module_dispo(py, "kokoro_onnx"):
        res["kokoro"] = py
    if all(os.path.exists(os.path.join(SUPERTONIC, f)) for f in FICHIERS_ST) and _module_dispo(py, "supertonic"):
        res["supertonic"] = py
    return res


def python_kokoro():
    return moteurs().get("kokoro")


def profil(genre):
    """« homme » / « femme » → (moteur, nom de la voix)."""
    if genre == "homme":
        return "supertonic", env("STUDIO_VOIX_HOMME", VOIX_HOMME)
    return "kokoro", env("STUDIO_VOIX_KOKORO", VOIX_KOKORO)


def synthetiser(prises, dossier, journal=None, graine=0):
    """Synthétise toutes les prises (un seul chargement de chaque modèle).
    → (sons, fréquences d'échantillonnage) prise par prise, ou (None, 0) si aucun moteur n'a répondu."""
    dispo = moteurs()
    if not dispo:
        return None, 0
    base_h = float(env("STUDIO_ALLURE_HOMME", "0.86"))
    taches, manque = [], set()
    for k, p in enumerate(prises):
        genre = p.get("voix", "femme")
        moteur, nom = profil(genre)
        if moteur not in dispo:  # voix pas installée : l'autre la remplace plutôt que de perdre l'épisode
            manque.add(genre)
            genre = "femme" if genre == "homme" else "homme"
            moteur, nom = profil(genre)
            p["voix"] = genre
        if moteur == "kokoro":
            texte, vitesse = p["texte"], p.get("vitesse", 0.9)
        else:
            texte, vitesse = en_lettres(p["texte"], oreille=True), max(0.75, min(1.4, base_h * p.get("rel", 1.0)))
        taches.append({"texte": texte, "phon": p["texte"], "moteur": moteur, "voix": nom, "vitesse": round(vitesse, 3),
                       "graine": graine * 1000 + k})
    if manque and journal:
        journal("Voix « " + " / ".join(sorted(manque)) + " » pas encore installée (python3 revenus/tiktok/studio.py voix) : "
                "l'autre voix la remplace.")
    travail = os.path.join(dossier, "travail.json")
    with open(travail, "w", encoding="utf-8") as f:
        json.dump({"kokoro": {"modele": os.path.join(VOIX_DIR, "kokoro-v1.0.onnx"), "voix_bin": os.path.join(VOIX_DIR, "voices-v1.0.bin")},
                   "supertonic": SUPERTONIC, "pas": int(env("STUDIO_PAS_HOMME", "8")), "dossier": dossier, "prises": taches},
                  f, ensure_ascii=False)
    py = list(dispo.values())[0]
    try:
        r = subprocess.run([py, os.path.abspath(__file__), "--ouvrier", travail], capture_output=True, text=True, timeout=1500)
    except Exception as ex:
        if journal:
            journal(f"La voix n'a pas pu démarrer : {ex}")
        return None, 0
    try:
        res = json.loads([x for x in r.stdout.splitlines() if x.startswith("{")][-1])
    except Exception:
        res = None
    if r.returncode != 0 or not res:
        if journal:
            journal("La voix a échoué : " + (r.stderr or r.stdout or "")[-400:])
        return None, 0
    sons, frequences = [], []
    for k, p in enumerate(prises):
        chemin = os.path.join(dossier, f"prise_{k:03d}.wav")
        a, sr = lire_wav(chemin) if os.path.exists(chemin) else (None, 0)
        sons.append(a)
        frequences.append(sr)
        if k < len(res.get("phonemes", [])):
            p["phonemes"] = res["phonemes"][k]
    if all(a is None or not len(a) for a in sons):
        return None, 0
    return sons, frequences


def dire(texte, sortie, journal=None, graine=0, narrateur="femme", radio=None, noms=None):
    """Texte → WAV + fichier de repères « sortie.json ». → durée en secondes, 0 si aucune voix n'est installée ou en panne.
    narrateur : « homme » ou « femme » (la voix de la série) ; radio : la voix des annonces radio, si elle diffère ;
    noms : {"homme": [...], "femme": [...]}, les personnages dont on rapporte les paroles."""
    prises = allures(attribuer(decouper(texte, noms), narrateur, radio))
    if not prises:
        return 0.0
    dossier = tempfile.mkdtemp(prefix="voix_")
    try:
        sons, frequences = synthetiser(prises, dossier, journal, graine)
        if sons is None:
            return 0.0
        if isinstance(frequences, int):  # un seul moteur, une seule fréquence
            frequences = [frequences] * len(sons)
        sr = max([f for a, f in zip(sons, frequences) if a is not None and f] or [24000])
        sons = [a if a is None or not f or f == sr else reechantillonner(a, f, sr) for a, f in zip(sons, frequences)]
        piste, reperes = assembler(prises, sons, sr, graine)
        ecrire_wav(sortie, piste, sr)
        with open(sortie + ".json", "w", encoding="utf-8") as f:
            json.dump({"moteur": "+".join(sorted({profil(p["voix"])[0] for p in prises})), "narrateur": narrateur,
                       "voix": [p["voix"] for p in prises], "reperes": reperes}, f, ensure_ascii=False)
        return len(piste) / float(sr)
    except Exception as ex:
        if journal:
            journal(f"Voix abandonnée : {ex}")
        return 0.0
    finally:
        shutil.rmtree(dossier, ignore_errors=True)


def lire_reperes(wav):
    """Repères écrits par dire() à côté du WAV, ou None (voix Piper)."""
    try:
        with open(wav + ".json", encoding="utf-8") as f:
            return [(list(m), float(a), float(b), list(p)) for m, a, b, p in json.load(f)["reperes"]]
    except Exception:
        return None


# ----------------------------------------------------------------------------- installation
def _sha256(chemin):
    h = hashlib.sha256()
    with open(chemin, "rb") as f:
        for bloc in iter(lambda: f.read(1 << 20), b""):
            h.update(bloc)
    return h.hexdigest()


def _telecharger(depot, fichiers, dossier, affiche=print):
    """Télécharge les fichiers manquants d'un modèle ; chaque fichier est refusé si sa taille ou son empreinte diffère."""
    for nom, (taille, empreinte) in fichiers.items():
        but = os.path.join(dossier, nom)
        if os.path.exists(but) and os.path.getsize(but) == taille:
            continue
        os.makedirs(os.path.dirname(but), exist_ok=True)
        if taille > 5e6:
            affiche(f"Téléchargement de {os.path.basename(nom)} ({taille / 1e6:.0f} Mo)…")
        tmp = but + ".part"
        try:
            with urllib.request.urlopen(urllib.request.Request(depot + nom, headers={"User-Agent": "studio-tiktok"}), timeout=120) as r, \
                    open(tmp, "wb") as f:
                shutil.copyfileobj(r, f, 1 << 20)
        except Exception as ex:
            affiche(f"Téléchargement de {nom} impossible : {ex}")
            return False
        if os.path.getsize(tmp) != taille or _sha256(tmp) != empreinte:
            affiche(f"{nom} : fichier incomplet ou modifié, téléchargement refusé.")
            os.remove(tmp)
            return False
        os.replace(tmp, but)
    return True


def telecharger_modele(affiche=print):
    """Le modèle de la narratrice (Kokoro, 354 Mo)."""
    return _telecharger(DEPOT, FICHIERS, VOIX_DIR, affiche)


def telecharger_modele_homme(affiche=print):
    """Le modèle du narrateur (Supertonic 3, 400 Mo)."""
    return _telecharger(DEPOT_ST, FICHIERS_ST, SUPERTONIC, affiche)


def installer(affiche=print):
    """Installe les deux voix dans leur environnement isolé + télécharge les modèles (750 Mo, une seule fois).
    → {"femme": bool, "homme": bool}. Relancer la commande complète ce qui manque sans rien refaire."""
    etat = {"femme": False, "homme": False}
    py = os.path.join(VENV, "bin", "python")
    if not os.path.exists(py):
        os.makedirs(DOSSIER, exist_ok=True)
        affiche("Création de l'environnement des voix…")
        r = subprocess.run([sys.executable, "-m", "venv", VENV], capture_output=True, text=True)
        if r.returncode != 0 or not os.path.exists(py):
            shutil.rmtree(VENV, ignore_errors=True)
            affiche("Impossible de créer l'environnement. Lance d'abord :  sudo apt-get install -y python3-venv")
            return etat
    manquants = [paquet for module, paquet in PAQUETS.items()
                 if subprocess.run([py, "-c", "import " + module], capture_output=True, text=True).returncode != 0]
    if manquants:
        affiche("Installation de " + ", ".join(m.split("==")[0] for m in manquants) + " (2 à 3 minutes)…")
        subprocess.run([py, "-m", "pip", "install", "--quiet", "--upgrade", "pip"], capture_output=True, text=True)
        for paquet in manquants:  # un par un : si l'un échoue, l'autre voix reste utilisable
            r = subprocess.run([py, "-m", "pip", "install", "--quiet", paquet], capture_output=True, text=True)
            if r.returncode != 0:
                affiche(f"pip a échoué pour {paquet} : " + (r.stderr or "")[-500:])
    telecharger_modele(affiche)
    telecharger_modele_homme(affiche)
    prets = moteurs()
    essais = (("femme", "kokoro", "Bonsoir. La voix du studio est prête."), ("homme", "supertonic", "Bonsoir. Le narrateur est prêt, lui aussi."))
    for genre, moteur, phrase in essais:
        if moteur not in prets:
            affiche(f"Voix « {genre} » : pas installée.")
            continue
        with tempfile.TemporaryDirectory() as d:
            wav = os.path.join(d, "essai.wav")
            ok = dire(phrase, wav, journal=affiche, narrateur=genre) > 0.5
            try:
                with open(wav + ".json", encoding="utf-8") as f:
                    ok = ok and set(json.load(f).get("voix") or []) == {genre}  # dite par la bonne voix, pas par l'autre
            except Exception:
                ok = False
        etat[genre] = bool(ok)
        affiche(f"Voix « {genre} » ({moteur}) : " + ("prête." if ok else "installée, mais l'essai a échoué."))
    return etat


# ----------------------------------------------------------------------------- ouvrier (python de l'environnement)
def _ouvrier(travail):
    import numpy as np
    with open(travail, encoding="utf-8") as f:
        w = json.load(f)
    besoin = {p.get("moteur", "kokoro") for p in w["prises"]}
    kokoro = supertonic = jeton = None
    styles = {}
    if "kokoro" in besoin:
        from kokoro_onnx import Kokoro
        kokoro = Kokoro(w["kokoro"]["modele"], w["kokoro"]["voix_bin"])
        jeton = kokoro.tokenizer
    else:  # les phonèmes servent aussi à caler les sous-titres de l'autre voix
        try:
            from kokoro_onnx.tokenizer import Tokenizer
            jeton = Tokenizer()
        except Exception:
            jeton = None
    if "supertonic" in besoin:
        from supertonic import TTS
        supertonic = TTS(model="supertonic-3", model_dir=w["supertonic"], auto_download=False)
    phonemes = []
    for i, p in enumerate(w["prises"]):
        ph = ""
        try:
            if jeton is not None:
                ph = jeton.phonemize(p.get("phon") or p["texte"], "fr-fr")
            if p.get("moteur") == "supertonic":
                if p["voix"] not in styles:
                    styles[p["voix"]] = supertonic.get_voice_style(voice_name=p["voix"])
                np.random.seed(int(p.get("graine", i)) % (2 ** 31))  # même texte → même prise, d'un jour à l'autre
                a, _ = supertonic.synthesize(p["texte"], voice_style=styles[p["voix"]], lang="fr", speed=float(p["vitesse"]),
                                             total_steps=int(w.get("pas", 8)))
                sr = int(getattr(supertonic, "sample_rate", 44100))
            else:
                a, sr = kokoro.create(ph, voice=p["voix"], speed=float(p["vitesse"]), lang="fr-fr", is_phonemes=True, trim=True)
            a = np.asarray(a, dtype="float32").reshape(-1)
            with wave.open(os.path.join(w["dossier"], f"prise_{i:03d}.wav"), "w") as f:
                f.setnchannels(1)
                f.setsampwidth(2)
                f.setframerate(int(sr))
                f.writeframes((np.clip(a, -1, 1) * 32767).astype("<i2").tobytes())
        except Exception as ex:  # une prise ratée ne bloque pas l'épisode
            print(f"prise {i} ignorée : {ex}", file=sys.stderr)
        phonemes.append(ph)
    print(json.dumps({"phonemes": phonemes}, ensure_ascii=False))


if __name__ == "__main__":
    if len(sys.argv) == 3 and sys.argv[1] in ("--ouvrier", "--kokoro"):
        _ouvrier(sys.argv[2])
    elif len(sys.argv) == 2 and sys.argv[1] == "installer":
        sys.exit(0 if any(installer().values()) else 1)
    else:
        print(__doc__)
