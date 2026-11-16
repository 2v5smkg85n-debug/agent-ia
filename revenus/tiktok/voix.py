#!/usr/bin/env python3
"""Voix du studio : Kokoro (voix française naturelle, 24 kHz), calculée sur le VPS, sans clé.

Pourquoi un fichier à part : Kokoro a besoin d'un numpy récent, alors que le reste du serveur garde
celui d'Ubuntu. Il vit donc dans un petit environnement isolé (revenus/donnees/tiktok/venv_voix),
et ce fichier est lancé deux fois :
  - par studio.py (python du système) : découpe le texte, assemble, pose les silences, soigne le son ;
  - par le python de l'environnement (« --kokoro travail.json ») : ne fait que synthétiser les phrases.

Ce que la voix gagne par rapport à Piper :
  - une phrase = une prise : le minutage de chaque phrase est exact (sous-titres calés sans deviner) ;
  - un rythme de conteuse : accroche franche, silences selon la ponctuation, phrase de suspens ralentie ;
  - les paroles entendues à la radio ou au téléphone sortent d'un vrai haut-parleur (bande étroite, souffle) ;
  - un son fini : coupe-bas, chaleur, air, compression légère, niveau constant d'un épisode à l'autre.

Si Kokoro n'est pas installé, studio.py retombe tout seul sur Piper.
"""
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
PAQUET = "kokoro-onnx==0.6.1"
VOIX_KOKORO = "ff_siwis"  # la même comédienne que la voix Piper « siwis », avec un moteur plus naturel
DEPOT = "https://github.com/thewh1teagle/kokoro-onnx/releases/download/model-files-v1.0/"
FICHIERS = {  # nom → (taille en octets, sha256)
    "kokoro-v1.0.onnx": (325532387, "7d5df8ecf7d4b1878015a32686053fd0eebe2bc377234608764cc0ef3636a6c5"),
    "voices-v1.0.bin": (28214398, "bca610b8308e8d99f32e6fe4197e7ec01679264efed0cac9140fe9c29f1fbf7d"),
}
FINS = (".", "!", "?", "…")
MOTS_RADIO = ("radio", "annonce", "haut-parleur", "hautparleur", "interphone", "gresill", "frequence", "repondeur",
              "telephone", "combine", "enregistrement", "micro", "messagerie", "talkie")


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


def decouper(texte):
    """Découpe le texte en prises : une par phrase, les paroles rapportées à part.
    → [{"mots": [...], "texte": à dire, "radio": bool, "cite": bool, "fin": bool (fin de phrase), "rang": n° de phrase}]"""
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
        radio = any(cle in contexte for cle in MOTS_RADIO)
        i = a
        while i < b:
            j = i
            while j < b and marques[j - a] == marques[i - a]:
                j += 1
            cite = marques[i - a]
            prises.append({"mots": mots[i:j], "texte": prononcer(" ".join(mots[i:j])), "cite": cite,
                           "radio": bool(cite and radio), "fin": j == b, "rang": rang})
            i = j
        avant = hors if hors.strip() else avant
    return prises


def allures(prises, base=None):
    """Vitesse de diction et silence après chaque prise : le rythme d'une conteuse, pas d'un lecteur."""
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


def soigner(a, sr, cible=0.175):
    """Finition de la narration : coupe-bas, un peu de chaleur et d'air, compression douce, niveau constant."""
    import numpy as np
    if not len(a) or float(np.abs(a).max()) < 1e-4:
        return a

    def courbe(f):
        g = 1.0 / np.sqrt(1.0 + (70.0 / f) ** 8)  # coupe-bas : ronflements et « pop »
        g = g * _cloche(f, 190.0, 0.9, 1.4)  # chaleur
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


def poids_mots(mots, phonemes=None):
    """Part de chaque mot dans la durée d'une prise. Avec les phonèmes de Kokoro (un groupe par mot), le poids suit
    ce qui est réellement prononcé (« aux horaires » ne compte pas ses lettres muettes)."""
    sons = phonemes.split() if phonemes else []
    sons = [s for s in sons if re.sub(r"[\W_]", "", s)]
    res = []
    for k, m in enumerate(mots):
        if len(sons) == len(mots):
            p = len(re.sub(r"[ˈˌː\W_]", "", sons[k])) + 0.6
        else:
            p = (len(re.sub(r"[^\w]", "", m)) + 1.2) * 0.8
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
    narration = []
    for k, (p, a) in enumerate(zip(prises, sons)):
        a = rogner(a, sr) if a is not None else np.zeros(0, dtype="float32")
        if not len(a):  # prise muette (ponctuation seule) : un court silence garde le compte des mots
            a = np.zeros(int(0.25 * sr), dtype="float32")
        if p["radio"]:
            a = effet_radio(a, sr, graine + k)
        else:
            narration.append(len(morceaux))
        morceaux.append(a)
        if p["radio"]:  # 0,09 s de garde de chaque côté (ouverture et relâchement de la fréquence)
            reperes.append((list(p["mots"]), t / sr + 0.09, (t + len(a)) / sr - 0.09, poids_mots(p["mots"], p.get("phonemes"))))
        else:
            poids = poids_mots(p["mots"], p.get("phonemes"))
            for i0, i1, s0, s1 in respirations(p["mots"], a, sr, poids):
                reperes.append((list(p["mots"][i0:i1]), (t + s0) / sr, (t + s1) / sr, poids[i0:i1]))
        t += len(a)
        blanc = np.zeros(int(p.get("pause", 0.4) * sr), dtype="float32")
        morceaux.append(blanc)
        t += len(blanc)
    # la narration est soignée d'un seul tenant (même niveau partout), les passages radio restent tels quels
    if narration:
        pos, tout = [], []
        for i in narration:
            pos.append((i, len(morceaux[i])))
            tout.append(morceaux[i])
            tout.append(np.zeros(int(0.12 * sr), dtype="float32"))
        fini = soigner(np.concatenate(tout), sr)
        x = 0
        for i, n in pos:
            morceaux[i] = fini[x:x + n]
            x += n + int(0.12 * sr)
    piste = np.concatenate(morceaux) if morceaux else np.zeros(0, dtype="float32")
    return piste, reperes


# ----------------------------------------------------------------------------- Kokoro
def python_kokoro():
    """Le python qui sait faire tourner Kokoro : celui de l'environnement isolé, sinon le python courant."""
    if not all(os.path.exists(os.path.join(VOIX_DIR, f)) for f in FICHIERS):
        return None
    for cand in (env("STUDIO_PYTHON_VOIX", ""), os.path.join(VENV, "bin", "python")):
        if cand and os.path.exists(cand):
            return cand
    try:
        import importlib.util
        if importlib.util.find_spec("kokoro_onnx"):
            return sys.executable
    except Exception:
        pass
    return None


def synthetiser(prises, dossier, journal=None):
    """Lance Kokoro sur toutes les prises (un seul chargement du modèle). → liste de sons (ou None si échec)."""
    py = python_kokoro()
    if not py:
        return None, 0
    travail = os.path.join(dossier, "travail.json")
    with open(travail, "w", encoding="utf-8") as f:
        json.dump({"modele": os.path.join(VOIX_DIR, "kokoro-v1.0.onnx"), "voix_bin": os.path.join(VOIX_DIR, "voices-v1.0.bin"),
                   "voix": env("STUDIO_VOIX_KOKORO", VOIX_KOKORO), "dossier": dossier,
                   "prises": [{"texte": p["texte"], "vitesse": p.get("vitesse", 0.9)} for p in prises]}, f, ensure_ascii=False)
    try:
        r = subprocess.run([py, os.path.abspath(__file__), "--kokoro", travail], capture_output=True, text=True, timeout=1500)
    except Exception as ex:
        if journal:
            journal(f"Kokoro n'a pas pu démarrer : {ex}")
        return None, 0
    try:
        res = json.loads([x for x in r.stdout.splitlines() if x.startswith("{")][-1])
    except Exception:
        res = None
    if r.returncode != 0 or not res:
        if journal:
            journal("Kokoro a échoué : " + (r.stderr or r.stdout or "")[-400:])
        return None, 0
    sons = []
    for k, p in enumerate(prises):
        chemin = os.path.join(dossier, f"prise_{k:03d}.wav")
        sons.append(lire_wav(chemin)[0] if os.path.exists(chemin) else None)
        if k < len(res.get("phonemes", [])):
            p["phonemes"] = res["phonemes"][k]
    if all(s is None or not len(s) for s in sons):
        return None, 0
    return sons, int(res.get("sr", 24000))


def dire(texte, sortie, journal=None, graine=0):
    """Texte → WAV (Kokoro) + fichier de repères « sortie.json ». → durée en secondes, 0 si Kokoro est absent ou en panne."""
    prises = allures(decouper(texte))
    if not prises:
        return 0.0
    dossier = tempfile.mkdtemp(prefix="voix_")
    try:
        sons, sr = synthetiser(prises, dossier, journal)
        if sons is None:
            return 0.0
        piste, reperes = assembler(prises, sons, sr, graine)
        ecrire_wav(sortie, piste, sr)
        with open(sortie + ".json", "w", encoding="utf-8") as f:
            json.dump({"moteur": "kokoro", "reperes": reperes}, f, ensure_ascii=False)
        return len(piste) / float(sr)
    except Exception as ex:
        if journal:
            journal(f"Voix Kokoro abandonnée : {ex}")
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


def telecharger_modele(affiche=print):
    os.makedirs(VOIX_DIR, exist_ok=True)
    for nom, (taille, empreinte) in FICHIERS.items():
        but = os.path.join(VOIX_DIR, nom)
        if os.path.exists(but) and os.path.getsize(but) == taille:
            continue
        affiche(f"Téléchargement de {nom} ({taille / 1e6:.0f} Mo)…")
        tmp = but + ".part"
        try:
            with urllib.request.urlopen(urllib.request.Request(DEPOT + nom, headers={"User-Agent": "studio-tiktok"}), timeout=120) as r, \
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


def installer(affiche=print):
    """Installe Kokoro dans son environnement isolé + télécharge le modèle (354 Mo, une seule fois)."""
    py = os.path.join(VENV, "bin", "python")
    if not os.path.exists(py):
        os.makedirs(DOSSIER, exist_ok=True)
        affiche("Création de l'environnement de la voix…")
        r = subprocess.run([sys.executable, "-m", "venv", VENV], capture_output=True, text=True)
        if r.returncode != 0 or not os.path.exists(py):
            shutil.rmtree(VENV, ignore_errors=True)
            affiche("Impossible de créer l'environnement. Lance d'abord :  sudo apt-get install -y python3-venv")
            return False
    r = subprocess.run([py, "-c", "import kokoro_onnx"], capture_output=True, text=True)
    if r.returncode != 0:
        affiche("Installation de Kokoro (2 à 3 minutes)…")
        subprocess.run([py, "-m", "pip", "install", "--quiet", "--upgrade", "pip"], capture_output=True, text=True)
        r = subprocess.run([py, "-m", "pip", "install", "--quiet", PAQUET], capture_output=True, text=True)
        if r.returncode != 0:
            affiche("pip a échoué : " + (r.stderr or "")[-600:])
            return False
    if not telecharger_modele(affiche):
        return False
    with tempfile.TemporaryDirectory() as d:
        ok = dire("Bonsoir. La voix du studio est prête.", os.path.join(d, "essai.wav"), journal=affiche) > 0.5
    affiche("Voix Kokoro prête." if ok else "Kokoro est installé mais l'essai a échoué.")
    return ok


# ----------------------------------------------------------------------------- ouvrier (python de l'environnement)
def _ouvrier(travail):
    import numpy as np
    from kokoro_onnx import Kokoro
    with open(travail, encoding="utf-8") as f:
        w = json.load(f)
    k = Kokoro(w["modele"], w["voix_bin"])
    phonemes = []
    for i, p in enumerate(w["prises"]):
        ph = ""
        try:
            ph = k.tokenizer.phonemize(p["texte"], "fr-fr")
            a, sr = k.create(ph, voice=w["voix"], speed=float(p["vitesse"]), lang="fr-fr", is_phonemes=True, trim=True)
            a = np.asarray(a, dtype="float32")
            with wave.open(os.path.join(w["dossier"], f"prise_{i:03d}.wav"), "w") as f:
                f.setnchannels(1)
                f.setsampwidth(2)
                f.setframerate(sr)
                f.writeframes((np.clip(a, -1, 1) * 32767).astype("<i2").tobytes())
        except Exception as ex:  # une prise ratée ne bloque pas l'épisode
            print(f"prise {i} ignorée : {ex}", file=sys.stderr)
        phonemes.append(ph)
    print(json.dumps({"sr": 24000, "phonemes": phonemes}, ensure_ascii=False))


if __name__ == "__main__":
    if len(sys.argv) == 3 and sys.argv[1] == "--kokoro":
        _ouvrier(sys.argv[2])
    elif len(sys.argv) == 2 and sys.argv[1] == "installer":
        sys.exit(0 if installer() else 1)
    else:
        print(__doc__)
