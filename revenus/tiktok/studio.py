#!/usr/bin/env python3
"""Studio TikTok : écrit, dit, anime et monte un épisode par jour, puis l'envoie sur Telegram.

Tout tourne en local sur le VPS, sans clé ni API payante :
  - texte     : Ollama local (bible.json = séries, personnages, 12 épisodes chacune)
  - voix      : Kokoro (voix française naturelle, voix.py) ; Piper en secours si Kokoro n'est pas installé
  - image     : décors animés 1080×1920 (scenes.py, PIL + numpy), un plan par phrase, sous-titres mot à mot
  - montage   : ffmpeg (H.264 + AAC), 70-90 s, < 45 Mo
  - livraison : Telegram sendVideo + légende prête à coller dans TikTok

Commandes :
  python3 revenus/tiktok/studio.py episode [id_serie]   → épisode suivant (ou de la série donnée)
  python3 revenus/tiktok/studio.py apercu              → 20 s de rendu pour vérifier voix + image
  python3 revenus/tiktok/studio.py voix                → installe la voix Kokoro (une fois) + la voix Piper de secours
  python3 revenus/tiktok/studio.py etat                → où en est chaque série
  python3 revenus/tiktok/studio.py test                → vérifie ffmpeg / PIL / numpy / piper (sans réseau)

Pourquoi pas de publication automatique : l'API TikTok de publication n'autorise que des vidéos
privées tant que l'application n'a pas été auditée par TikTok. Le bot prépare tout, l'humain
appuie sur « Publier » depuis l'iPhone (voir README.md).
"""
import io
import json
import math
import os
import re
import shutil
import struct
import subprocess
import sys
import time
import unicodedata
import urllib.request
import uuid
import wave

ICI = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.dirname(ICI))
from commun import (DONNEES, charger_env, ecrire_json, env, horodatage, http_post_json,  # noqa: E402
                    lire_json, log, telegram)

DOSSIER = os.path.join(DONNEES, "tiktok")
VIDEOS = os.path.join(DOSSIER, "videos")
VOIX_DIR = os.path.join(DOSSIER, "voix")
ETAT = os.path.join(DOSSIER, "etat.json")
SAISONS = os.path.join(DOSSIER, "saisons.json")
JOURNAL = os.path.join(DOSSIER, "studio.log")
BIBLE = os.path.join(ICI, "bible.json")
VOIX = "fr_FR-siwis-medium"
LARGEUR, HAUTEUR, FPS = 1080, 1920, 24
POLICES = ["/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
           "/usr/share/fonts/dejavu/DejaVuSans-Bold.ttf",
           "/usr/share/fonts/truetype/liberation/LiberationSans-Bold.ttf"]


def _log(msg):
    log(msg, JOURNAL)


# ----------------------------------------------------------------------------- bible / état
def bible():
    b = lire_json(BIBLE, {"series": []})
    extra = lire_json(SAISONS, {})  # saisons générées automatiquement : {id_serie: [episodes...]}
    for s in b["series"]:
        s["episodes"] = list(s["episodes"]) + list(extra.get(s["id"], []))
    return b


def etat():
    return lire_json(ETAT, {"serie_courante": 0, "episodes": {}, "historique": []})


def choisir(b, e, force=None):
    """Retourne (serie, numero_episode 1-based). Rotation : une série jusqu'au bout, puis la suivante."""
    series = b["series"]
    if force:
        cand = [s for s in series if s["id"] == force]
        if not cand:
            raise SystemExit(f"Série inconnue : {force}. Choix : {', '.join(s['id'] for s in series)}")
        s = cand[0]
        return s, e["episodes"].get(s["id"], 0) + 1
    mode = env("STUDIO_ROTATION", "suite")
    for _ in range(len(series)):
        s = series[e["serie_courante"] % len(series)]
        fait = e["episodes"].get(s["id"], 0)
        if fait < len(s["episodes"]):
            if mode == "alternance":
                e["serie_courante"] = (e["serie_courante"] + 1) % len(series)
            return s, fait + 1
        e["serie_courante"] = (e["serie_courante"] + 1) % len(series)
    return None, 0


# ----------------------------------------------------------------------------- texte (Ollama)
def ollama_creatif(prompt, num_predict=900, timeout=240):
    if env("REVENUS_OLLAMA", "1") == "0":
        return ""
    modele = env("STUDIO_MODELE", env("OLLAMA_MODEL", "qwen2.5:3b"))
    code, corps = http_post_json(
        "http://localhost:11434/api/generate",
        {"model": modele, "prompt": prompt, "stream": False,
         "options": {"num_predict": num_predict, "temperature": 0.85, "top_p": 0.92,
                     "repeat_penalty": 1.12}},
        timeout=timeout)
    if code != 200:
        return ""
    try:
        return json.loads(corps).get("response", "").strip()
    except Exception:
        return ""


def nettoyer_texte(t):
    t = re.sub(r"[*_#>`]+", "", t)
    t = re.sub(r"^\s*(épisode|episode|titre|script)\s*\d*\s*[:.-]\s*", "", t, flags=re.I | re.M)
    t = t.replace("«", "").replace("»", "").replace('"', "")
    t = re.sub(r"\s+", " ", t).strip()
    return t


def ecrire_episode(b, s, n):
    ep = s["episodes"][n - 1]
    precedents = s["episodes"][max(0, n - 4):n - 1]
    rappel = "\n".join(f"- Épisode {n - len(precedents) + i} : {p['accroche']} Fin : {p['suspens']}"
                       for i, p in enumerate(precedents)) or "- (c'est le premier épisode)"
    prompt = f"""Tu es un auteur de mini-séries audio en français, format TikTok vertical, public adulte.
Règles : {b.get('regles', '')}

SÉRIE : {s['titre']}
Ambiance : {s['ambiance']}
Narrateur (première personne) : {s['narrateur']}
Univers : {s['univers']}

Épisodes précédents :
{rappel}

ÉPISODE {n} À ÉCRIRE
Première phrase, à reprendre mot pour mot : {ep['accroche']}
Étapes à raconter dans l'ordre : {' | '.join(ep['beats'])}
Dernière phrase, à reprendre mot pour mot : {ep['suspens']}

Contraintes : entre 180 et 230 mots, au présent, phrases courtes (12 mots max), concret, sensoriel,
un détail troublant toutes les trois phrases, aucune explication morale, aucun titre, aucune liste,
pas de guillemets, pas de didascalie. Écris uniquement le texte lu à voix haute."""
    texte = nettoyer_texte(ollama_creatif(prompt))
    secours = False
    if len(texte.split()) < 120:
        secours = True
        etapes = [nettoyer_texte(b_).rstrip(" .") for b_ in ep["beats"]]
        etapes = [x[:1].upper() + x[1:] + ("" if x.endswith(("!", "?", "…")) else ".") for x in etapes if x]
        texte = nettoyer_texte(" ".join([ep["accroche"]] + etapes + [ep["suspens"]]))
    if not texte.lower().startswith(ep["accroche"].lower()[:30]):
        texte = ep["accroche"] + " " + texte
    suspens = nettoyer_texte(ep["suspens"])  # sans guillemets, comme le reste du texte
    if suspens.lower()[-25:].rstrip(". ") not in texte.lower():
        texte = texte.rstrip(" .") + ". " + suspens
    mots = texte.split()
    if len(mots) > 270:  # coupe à la fin d'une phrase, puis remet le suspens
        coupe = " ".join(mots[:240])
        coupe = coupe[:coupe.rfind(".") + 1] if "." in coupe else coupe
        texte = coupe + " " + suspens
    return texte, secours


def nouvelle_saison(b, s):
    """Quand les 12 épisodes écrits à la main sont épuisés, Ollama propose 12 nouvelles graines."""
    derniers = s["episodes"][-3:]
    prompt = f"""Tu es scénariste. Série : {s['titre']}. Univers : {s['univers']} Narrateur : {s['narrateur']}
Derniers épisodes : {json.dumps(derniers, ensure_ascii=False)}
Invente la saison suivante : 12 épisodes qui continuent l'histoire avec un nouvel arc, cohérents avec l'univers.
Réponds UNIQUEMENT avec un tableau JSON de 12 objets ayant exactement les clés
"accroche" (une phrase à la première personne, intrigante), "beats" (liste de 3 phrases courtes), "suspens" (une phrase finale)."""
    brut = ollama_creatif(prompt, num_predict=2200, timeout=420)
    m = re.search(r"\[.*\]", brut, flags=re.S)
    if not m:
        return False
    try:
        eps = json.loads(m.group(0))
    except Exception:
        return False
    eps = [e for e in eps if isinstance(e, dict) and e.get("accroche") and e.get("suspens")
           and isinstance(e.get("beats"), list)]
    if len(eps) < 6:
        return False
    sais = lire_json(SAISONS, {})
    sais.setdefault(s["id"], []).extend(eps[:12])
    ecrire_json(SAISONS, sais)
    _log(f"Nouvelle saison générée pour {s['id']} : {len(eps[:12])} épisodes")
    return True


# ----------------------------------------------------------------------------- voix (Kokoro, sinon Piper)
def piper_dispo():
    try:
        r = subprocess.run([sys.executable, "-m", "piper", "--help"], capture_output=True, timeout=60)
        return r.returncode == 0
    except Exception:
        return False


def telecharger_voix():
    os.makedirs(VOIX_DIR, exist_ok=True)
    if os.path.exists(os.path.join(VOIX_DIR, VOIX + ".onnx")):
        return True
    r = subprocess.run([sys.executable, "-m", "piper.download_voices", VOIX, "--download-dir", VOIX_DIR],
                       capture_output=True, text=True, timeout=1800)
    if r.returncode != 0:
        _log("Téléchargement voix échoué : " + (r.stderr or "")[-400:])
    return os.path.exists(os.path.join(VOIX_DIR, VOIX + ".onnx"))


def dire(texte, sortie):
    """Texte → WAV mono. Kokoro d'abord (voix naturelle + repères exacts dans « sortie.json »), sinon Piper.
    Retourne la durée (s) ou 0."""
    import voix as voix_k
    if os.path.exists(sortie + ".json"):
        os.remove(sortie + ".json")
    if env("STUDIO_MOTEUR_VOIX", "kokoro").lower() != "piper":
        d = voix_k.dire(texte, sortie, journal=_log)
        if d > 0:
            return d
        if voix_k.python_kokoro():
            _log("Kokoro n'a rien rendu : repli sur Piper.")
    modele = os.path.join(VOIX_DIR, VOIX + ".onnx")
    if not os.path.exists(modele) and not telecharger_voix():
        return 0.0
    cmd = [sys.executable, "-m", "piper", "-m", modele, "-f", sortie,
           "--length-scale", env("STUDIO_VITESSE", "1.06"), "--sentence-silence", "0.45"]
    r = subprocess.run(cmd, input=texte, capture_output=True, text=True, timeout=900)
    if r.returncode != 0 or not os.path.exists(sortie):
        _log("Piper a échoué : " + (r.stderr or "")[-400:])
        return 0.0
    with wave.open(sortie) as w:
        return w.getnframes() / float(w.getframerate())


def lire_wav(chemin):
    import numpy as np
    with wave.open(chemin) as w:
        sr, n, larg, can = w.getframerate(), w.getnframes(), w.getsampwidth(), w.getnchannels()
        brut = w.readframes(n)
    if larg == 2:
        a = np.frombuffer(brut, dtype="<i2").astype("float32") / 32768.0
    else:
        a = (np.frombuffer(brut, dtype="u1").astype("float32") - 128) / 128.0
    if can > 1:
        a = a.reshape(-1, can).mean(axis=1)
    return a, sr


def ecrire_wav(chemin, a, sr):
    import numpy as np
    a = np.clip(a, -1, 1)
    with wave.open(chemin, "w") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(sr)
        w.writeframes((a * 32767).astype("<i2").tobytes())


def nappe(duree, sr, graine=0):
    """Nappe sonore douce et libre de droits : deux bourdons graves + souffle filtré, lentement modulés."""
    import numpy as np
    rng = np.random.default_rng(graine)
    t = np.arange(int(duree * sr)) / sr
    f1, f2 = 55.0 + graine % 7, 82.4 + (graine * 3) % 11
    lfo = 0.55 + 0.45 * np.sin(2 * math.pi * 0.05 * t + graine)
    bourdon = 0.35 * np.sin(2 * math.pi * f1 * t) + 0.22 * np.sin(2 * math.pi * f2 * t + 1.3)
    bourdon += 0.12 * np.sin(2 * math.pi * f1 * 2.01 * t) * lfo
    souffle = rng.standard_normal(len(t)).astype("float32")
    noyau = np.ones(400, dtype="float32") / 400.0  # passe-bas grossier
    souffle = np.convolve(souffle, noyau, mode="same") * 2.2
    s = (bourdon * lfo + souffle * (0.5 + 0.5 * lfo)).astype("float32")
    fondu = np.minimum(1.0, np.minimum(t / 2.5, (duree - t) / 3.0))
    return s * np.clip(fondu, 0, 1)


def mixer(voix_wav, sortie, avant=0.4, apres=3.6, graine=0):
    import numpy as np
    v, sr = lire_wav(voix_wav)
    total = avant + len(v) / sr + apres
    piste = np.zeros(int(total * sr), dtype="float32")
    d = int(avant * sr)
    piste[d:d + len(v)] = v * 0.95
    piste += nappe(total, sr, graine) * float(env("STUDIO_NAPPE", "0.10"))
    ecrire_wav(sortie, piste, sr)
    return total, len(v) / sr


# ----------------------------------------------------------------------------- image
def hexa(c):
    c = c.lstrip("#")
    return tuple(int(c[i:i + 2], 16) for i in (0, 2, 4))


def police(taille):
    from PIL import ImageFont
    for p in POLICES:
        if os.path.exists(p):
            return ImageFont.truetype(p, taille)
    return ImageFont.load_default()


def _repartir(mots, debut, duree, fin_de_bloc=False):
    """Répartit une durée sur des mots (poids = longueur + ponctuation)."""
    poids = []
    for k, m in enumerate(mots):
        p = len(re.sub(r"[^\w]", "", m)) + 1.2
        if m.endswith((".", "!", "?", "…")):
            p += 0.0 if (fin_de_bloc and k == len(mots) - 1) else 4.5
        elif m.endswith((",", ";", ":")):
            p += 2.0
        poids.append(p)
    total = sum(poids) or 1.0
    t, res = debut, []
    for m, p in zip(mots, poids):
        d = duree * p / total
        res.append((m, t, t + d))
        t += d
    return res


def minutage_mots(texte, debut, duree):
    """Répartit la durée de la voix sur les mots (poids = longueur + ponctuation)."""
    return _repartir(texte.split(), debut, duree)


def jetons(texte):
    """Mots à afficher : sans guillemets, la ponctuation isolée (« : », « ; ») recollée au mot précédent."""
    res = []
    for m in texte.replace("«", " ").replace("»", " ").replace('"', " ").split():
        if re.search(r"\w", m) or not res:
            res.append(m)
        elif m not in (".", "…") or not res[-1].endswith((".", "!", "?", "…")):
            res[-1] += ("" if m in (".", ",", "…") else " ") + m
    return res


def blancs(voix, sr, mini=0.40):
    """Silences de fin de phrase posés par Piper dans la voix : [(début, fin)] en secondes."""
    import numpy as np
    z = (np.abs(voix) < 2e-4).astype("int8")
    bords = np.flatnonzero(np.diff(np.concatenate([[0], z, [0]])))
    return [(a / sr, b / sr) for a, b in zip(bords[::2], bords[1::2]) if (b - a) / sr >= mini]


def minuter(texte, debut, duree, voix=None, sr=0, reperes=None):
    """Minutage des sous-titres. Avec les repères de Kokoro, chaque prise a son début et sa fin exacts ; avec la
    voix Piper, chaque phrase est recalée sur ses silences réels ; sinon, simple répartition sur la durée."""
    mots = jetons(texte)
    if reperes and [m for r in reperes for m in r[0]] == mots:
        res = []
        for groupe, t0, t1, poids in reperes:
            total = sum(poids) or 1.0
            t = debut + t0
            for m, p in zip(groupe, poids):
                d = max(0.0, t1 - t0) * p / total
                res.append((m, t, t + d))
                t += d
        return res
    base = _repartir(mots, debut, duree)
    if voix is None or not sr or len(mots) < 2:
        return base
    try:
        tous = blancs(voix, sr)
        fin = len(voix) / sr
        t_debut = tous[0][1] if tous and tous[0][0] < 0.01 else 0.0
        t_fin = tous[-1][0] if tous and tous[-1][1] > fin - 0.01 else fin
        sil = [x for x in tous if x[0] > t_debut + 0.2 and x[1] < t_fin - 0.2]
        cand = [i for i, m in enumerate(mots[:-1]) if m.endswith((".", "!", "?", "…"))]
        if not sil:
            return _repartir(mots, debut + t_debut, t_fin - t_debut)
        if len(cand) < len(sil):
            return base
        if len(cand) == len(sil):  # cas normal : un silence par phrase
            choix = cand
        else:
            # moins de silences que de phrases : chacun est attribué à une fin de phrase
            # (ordre respecté, écart minimal avec le minutage estimé)
            cout = [[abs(base[j][2] - debut - s0) + (0.0 if mots[j + 1][:1].isupper() or mots[j + 1][:1].isdigit() else 1.2)
                     for j in cand] for s0, _ in sil]
            inf = float("inf")
            K, M = len(sil), len(cand)
            f = [[inf] * M for _ in range(K)]
            prec = [[-1] * M for _ in range(K)]
            for k in range(K):
                meilleur, arg = inf, -1
                for j in range(M):
                    if k == 0:
                        f[k][j] = cout[k][j]
                    elif meilleur < inf:
                        f[k][j] = meilleur + cout[k][j]
                        prec[k][j] = arg
                    if k and f[k - 1][j] < meilleur:
                        meilleur, arg = f[k - 1][j], j
            j = min(range(M), key=lambda x: f[K - 1][x])
            if f[K - 1][j] / K > 2.5:
                return base
            choix = []
            for k in range(K - 1, -1, -1):
                choix.append(cand[j])
                j = prec[k][j]
            choix.reverse()
        res, i0, t0 = [], 0, t_debut
        for (s0, s1), c in zip(sil + [(t_fin, t_fin)], choix + [len(mots) - 1]):
            res += _repartir(mots[i0:c + 1], debut + t0, max(0.2, s0 - t0), fin_de_bloc=True)
            i0, t0 = c + 1, s1
        return res
    except Exception as ex:  # ne jamais bloquer un épisode pour un recalage
        _log(f"Recalage des sous-titres ignoré : {ex}")
        return base


def groupes(minutes, taille=3):
    """Regroupe les mots par 3-4 en coupant aux ponctuations ; une fin de phrase ferme toujours le groupe."""
    g, cour = [], []
    for m in minutes:
        cour.append(m)
        phrase = m[0].endswith((".", "!", "?", "…"))
        fin = phrase or m[0].endswith((",", ";", ":"))
        if phrase or len(cour) >= taille + (0 if fin else 1) or (fin and len(cour) >= 2):
            g.append(cour)
            cour = []
    if cour:
        g.append(cour)
    for a, b in zip(g, g[1:]):  # évite un mot tout seul en fin de phrase : il emprunte le dernier mot d'avant
        if len(b) == 1 and len(a) >= 3 and not a[-1][0].endswith((".", "!", "?", "…")):
            b.insert(0, a.pop())
    return g


def enveloppe(son, sr, fps, n_images, decalage=0.0):
    """Volume de la voix image par image (0 → 1) : le décor réagit quand le narrateur parle."""
    import numpy as np
    pas = max(1, int(sr / fps))
    vol = np.zeros(n_images, dtype="float32")
    for i in range(n_images):
        a = int((i / fps - decalage) * sr)
        if a + pas <= 0 or a >= len(son):
            continue
        bout = son[max(0, a):a + pas]
        vol[i] = float(np.sqrt(np.mean(bout * bout))) if len(bout) else 0.0
    actifs = vol[vol > 1e-4]
    vol = np.clip(vol / (float(np.percentile(actifs, 92)) if len(actifs) else 1.0), 0, 1)
    for i in range(1, n_images):  # attaque franche, retombée douce
        vol[i] = max(vol[i], vol[i - 1] * 0.72)
    return vol


MOTS_FORTS = frozenset(("jamais personne disparu disparue disparait disparaissent existe seul seule mort morte peur vide "
                        "impossible interdit secret fantome efface effacer hurle noir murmure derriere").split())


def mot_fort(mot):
    """Mot mis en valeur dans les sous-titres (chiffre ou mot qui porte le frisson)."""
    net = unicodedata.normalize("NFD", mot.lower())
    net = re.sub(r"[^a-z0-9]", "", "".join(c for c in net if unicodedata.category(c) != "Mn"))
    return bool(net) and (net.isdigit() or net in MOTS_FORTS)


def _rebond(x):
    """Arrivée avec léger dépassement (0 → 1)."""
    x = min(1.0, max(0.0, x)) - 1.0
    return 1.0 + 2.70158 * x ** 3 + 1.70158 * x ** 2


def _etiquette(texte, f, couleur, contour=6, ombre=12):
    """Texte prêt à poser (RGBA) : contour noir + ombre portée floue."""
    from PIL import Image, ImageDraw, ImageFilter
    g, h, d_, b = f.getbbox(texte, stroke_width=contour)
    marge = contour + ombre * 2 + 4
    w, ht = int(d_ - g) + 2 * marge, int(b - h) + 2 * marge
    im = Image.new("RGBA", (w, ht), (0, 0, 0, 0))
    ImageDraw.Draw(im).text((w / 2, ht / 2), texte, font=f, fill=tuple(couleur) + (255,), anchor="mm",
                            stroke_width=contour, stroke_fill=(0, 0, 0, 255))
    if ombre:
        fond = Image.new("RGBA", (w, ht), (0, 0, 0, 255))
        fond.putalpha(im.getchannel("A").filter(ImageFilter.GaussianBlur(ombre)).point(lambda v: int(v * 0.75)))
        im = Image.alpha_composite(fond, im)
    return im


def _poser(base, etq, cx, cy, echelle=1.0, alpha=1.0):
    """Pose une étiquette centrée en (cx, cy), agrandie et plus ou moins transparente."""
    from PIL import Image
    if alpha <= 0.01:
        return
    if abs(echelle - 1.0) > 0.01:
        etq = etq.resize((max(1, int(etq.width * echelle)), max(1, int(etq.height * echelle))), Image.BILINEAR)
    masque = etq.getchannel("A")
    if alpha < 0.99:
        masque = masque.point(lambda v: int(v * alpha))
    base.paste(etq, (int(cx - etq.width / 2), int(cy - etq.height / 2)), masque)


def _lignes(mots, largeur_de, maxi):
    """Coupe une liste de mots en lignes de largeur ≤ maxi (au plus équilibré quand deux lignes suffisent)."""
    total = largeur_de(" ".join(mots))
    if total <= maxi or len(mots) < 2:
        return [mots]
    coupes = [(max(largeur_de(" ".join(mots[:i])), largeur_de(" ".join(mots[i:]))), i) for i in range(1, len(mots))]
    pire, i = min(coupes)
    if pire <= maxi or len(mots) < 3:
        return [mots[:i], mots[i:]]
    lignes, cour = [], []
    for m in mots:
        if cour and largeur_de(" ".join(cour + [m])) > maxi:
            lignes.append(cour)
            cour = []
        cour.append(m)
    return lignes + [cour]


def rendre(texte, audio_wav, duree_totale, debut_voix, duree_voix, serie, numero, sortie, suivant=True, voix_wav=None):
    """Anime l'épisode : décors dessinés image par image (scenes.py), caméra, coupes calées sur les phrases,
    sous-titres mot à mot, titre d'ouverture et carte de fin. Les images partent en flux brut vers ffmpeg."""
    from PIL import Image, ImageDraw
    import numpy as np
    import scenes
    fps = max(12, min(30, int(env("STUDIO_FPS", str(FPS)))))
    eclats = env("STUDIO_FLASH", "1") != "0"
    palette = tuple(hexa(c) for c in serie["palette"])
    fond, milieu, accent = palette
    sombre = tuple(int(c * 0.6) for c in fond)
    taille = (LARGEUR, HAUTEUR)
    L2, H2 = scenes.L, scenes.H
    n_images = int(duree_totale * fps)

    # --- la voix : minutage des mots et volume image par image
    voix, sr = None, 0
    try:
        voix, sr = lire_wav(voix_wav or audio_wav)
    except Exception as ex:
        _log(f"Lecture de la voix impossible ({ex}) : animation sans réaction au son.")
    import voix as voix_k
    mots = minuter(texte, debut_voix, duree_voix, voix if voix_wav else None, sr,
                   voix_k.lire_reperes(voix_wav) if voix_wav else None)
    volume = enveloppe(voix, sr, fps, n_images, debut_voix if voix_wav else 0.0) if voix is not None else np.zeros(n_images)
    grp = groupes(mots)
    fin_voix = mots[-1][2] if mots else debut_voix + duree_voix
    plans = scenes.decouper_plans(mots, serie, numero, duree_totale)
    t_suspens = next((p["t0"] for p in plans if p.get("suspens")), fin_voix)
    chocs = []
    for m, t0, _ in mots:  # petites secousses de caméra sur les mots forts
        if mot_fort(m) and (not chocs or t0 - chocs[-1] > 1.4) and t0 > 2.4:
            chocs.append(t0)
    t_noir, t_carte = fin_voix + 0.30, fin_voix + 0.30 + 3.0 / fps
    chocs.append(t_carte + 0.20)

    # --- éléments préparés une fois
    finir = scenes.finitions()
    voile = Image.new("RGB", (L2, H2), scenes.melange(accent, (255, 255, 255), 0.35))
    noir = Image.new("RGB", taille, (0, 0, 0))
    assombri = [int(v * 0.34) for v in range(256)] * 3
    retenu = [[int(v * (0.66 + 0.34 * k / 8)) for v in range(256)] * 3 for k in range(9)]
    secours = scenes.degrade(scenes.lum(fond, 1.3), scenes.melange(fond, milieu, 0.6))
    scenes.halo(secours, L2 / 2, H2 * 0.36, 300, milieu, 0.9)
    yy = np.linspace(-1, 1, 600, dtype="float32")[:, None]
    bande = Image.fromarray(np.repeat((np.exp(-(yy * 1.9) ** 2) * 165).astype("uint8"), LARGEUR, axis=1))
    y_sous, y_bande = int(HAUTEUR * 0.60), int(HAUTEUR * 0.60) - 300
    yy = np.linspace(0, 1, 380, dtype="float32")[:, None]
    ombre_haut = Image.fromarray(np.repeat(((1 - yy) ** 1.6 * 200).astype("uint8"), LARGEUR, axis=1))
    noir_bande, noir_haut = Image.new("RGB", bande.size), Image.new("RGB", ombre_haut.size)  # image unie : rapide partout
    MAXI = 840  # largeur utile des textes : hors boutons TikTok à droite

    def largeur(f):
        return lambda s_: f.getlength(s_)

    # titre d'ouverture
    t_titre = 2.3
    f_titre = 96
    while f_titre > 56 and len(_lignes(serie["titre"].upper().split(), largeur(scenes.police(f_titre)), MAXI + 40)) > 2:
        f_titre -= 6
    l_titre = _lignes(serie["titre"].upper().split(), largeur(scenes.police(f_titre)), MAXI + 40)
    e_titre = [_etiquette(" ".join(x), scenes.police(f_titre), (255, 255, 255), 7, 14) for x in l_titre]
    f_ep = scenes.police(54)
    txt_ep = f"ÉPISODE {numero}"
    w_ep = f_ep.getlength(txt_ep) + 64
    # en-tête permanent
    f_haut = scenes.police(30)
    entete = f"{serie['titre'].upper()}  ·  ÉP. {numero}"
    if f_haut.getlength(entete) > 760:
        f_haut = scenes.police(int(30 * 760 / f_haut.getlength(entete)))
    w_haut = f_haut.getlength(entete) + 110
    # carte de fin
    l1, l2 = ("LA SUITE", "DEMAIN À 20 H") if suivant else ("FIN DE", "LA SAISON")
    e_l1 = _etiquette(l1, scenes.police(132), (255, 255, 255), 8, 16)
    e_l2 = _etiquette(l2, scenes.police(100), accent, 8, 16)
    bas = f"Épisode {numero + 1} · abonne-toi pour la suite" if suivant else "Merci d'avoir suivi cette histoire"
    f_bas = scenes.police(44)
    if f_bas.getlength(bas) > MAXI:
        f_bas = scenes.police(int(44 * MAXI / f_bas.getlength(bas)))
    f_rond, f_rond2 = scenes.police(92), scenes.police(26)

    # mise en page des sous-titres, calculée une fois par groupe
    def mise_en_page(g):
        base = 84
        while True:
            def lg(m):
                return scenes.police(int(base * (1.16 if mot_fort(m) else 1.0))).getlength(m)
            esp = base * 0.44
            if max(lg(m[0]) for m in g) <= MAXI or base <= 44:
                break
            base -= 6
        total = sum(lg(m[0]) for m in g) + esp * (len(g) - 1)
        if total > MAXI and len(g) > 1:
            coupes = []
            for i in range(1, len(g)):
                wa = sum(lg(m[0]) for m in g[:i]) + esp * (i - 1)
                wb = sum(lg(m[0]) for m in g[i:]) + esp * (len(g) - i - 1)
                coupes.append((max(wa, wb), i))
            i = min(coupes)[1]
            lignes = [g[:i], g[i:]]
        else:
            lignes = [g]
        if any(sum(lg(m[0]) for m in li) + esp * (len(li) - 1) > MAXI + 60 for li in lignes) and len(g) > 2:
            lignes = [[m] for m in g][:3] if len(g) == 3 else [g[:1], g[1:-1], g[-1:]]
        pas = base * 1.32
        places, y = [], y_sous - pas * (len(lignes) - 1) / 2
        for li in lignes:
            ws = [lg(m[0]) for m in li]
            x = (LARGEUR - sum(ws) - esp * (len(li) - 1)) / 2
            for (m, t0, t1), w_ in zip(li, ws):
                places.append((m, t0, t1, x + w_ / 2, y, int(base * (1.16 if mot_fort(m) else 1.0)), mot_fort(m)))
                x += w_ + esp
            y += pas
        return places

    pages = {}
    # débit plafonné pour rester sous la limite Telegram (49 Mo), même pour un épisode long
    debit = env("STUDIO_DEBIT", "") or f"{int(max(900, min(3200, 40 * 8000 / max(1.0, duree_totale) - 140)))}k"
    cmd = ["ffmpeg", "-y", "-loglevel", "error", "-f", "rawvideo", "-pix_fmt", "rgb24",
           "-s", f"{LARGEUR}x{HAUTEUR}", "-r", str(fps), "-i", "-", "-i", audio_wav,
           "-c:v", "libx264", "-preset", env("STUDIO_PRESET", "veryfast"), "-crf", env("STUDIO_CRF", "26"),
           "-maxrate", debit, "-bufsize", "6000k",
           "-pix_fmt", "yuv420p", "-c:a", "aac", "-b:a", "128k", "-shortest", "-movflags", "+faststart", sortie]
    proc = subprocess.Popen(cmd, stdin=subprocess.PIPE)
    k_plan, dessine, panne = -1, None, False
    i_choc, i_grp = 0, 0
    image_vignette = min(n_images - 1, int(1.1 * fps))
    for i in range(n_images):
        t = i / fps
        # --- le plan en cours (un plan par phrase)
        while k_plan < len(plans) - 1 and (k_plan < 0 or t >= plans[k_plan]["t1"]):
            k_plan += 1
            try:
                dessine = scenes.fabriquer(plans[k_plan], palette)
            except Exception as ex:
                dessine = None
                _log(f"Scène {plans[k_plan]['scene']} indisponible : {ex}")
        plan = plans[k_plan]
        tl = t - plan["t0"]
        p = min(1.0, tl / max(0.5, plan["t1"] - plan["t0"]))
        v = float(volume[i])
        im = None
        if dessine is not None:
            try:
                im = dessine(tl, p, v)
            except Exception as ex:
                if not panne:
                    _log(f"Scène {plan['scene']} en erreur : {ex}")
                panne, dessine = True, None
        if im is None:
            im = secours.copy()
        fx, fy = getattr(dessine, "foyer", (L2 / 2, H2 * 0.38))
        # --- la coupe : flash doux, à-coup de zoom ou parasites
        zoom = 0.0
        if k_plan > 0 and tl < 0.42:
            genre = plan["transition"]
            if eclats and genre == "glitch" and tl < 2.5 / fps:
                im = scenes.parasite(im, i)
            if eclats and genre == "flash" and tl < 0.28:
                im = Image.blend(im, voile, 0.36 * (1 - tl / 0.28) ** 2)
            zoom += {"zoom": 0.15, "glitch": 0.08, "flash": 0.05}.get(genre, 0.0) * (1 - scenes.doux(tl / 0.42))
        # --- le suspens : l'image se resserre et s'assombrit, le cœur bat
        noirceur, serre = 0.0, 0.0
        if t >= t_suspens:
            serre = scenes.doux((t - t_suspens) / max(1.0, fin_voix - t_suspens))
            noirceur = 0.55 * serre
            zoom += 0.10 * serre + 0.014 * max(0.0, math.sin(2 * math.pi * 1.15 * (t - t_suspens))) ** 6
        carte = t - t_carte
        if carte >= 0:
            im = im.point(assombri)
            noirceur = 0.2
        elif t < t_titre + 0.3:  # décor un peu retenu derrière le titre
            im = im.point(retenu[min(len(retenu) - 1, int(len(retenu) * max(0.0, (t - t_titre + 0.15) / 0.45)))])
        im = finir(im, i, noirceur)
        # --- la caméra
        e = scenes.doux(p)
        cx, cy = fx, fy
        if plan["camera"] == "avant":
            zoom += 1.05 + 0.11 * e
        elif plan["camera"] == "arriere":
            zoom += 1.16 - 0.10 * e
        else:
            zoom += 1.12
            cx += (52 * e - 26) * (1 if plan["camera"] == "droite" else -1)
        cx += 5 * math.sin(t * 0.7)
        cy += 4 * math.sin(t * 0.53 + 1.0)
        while i_choc < len(chocs) - 1 and t >= chocs[i_choc + 1]:
            i_choc += 1
        dc = t - chocs[i_choc] if chocs else -1
        if 0 <= dc < 0.30:
            force = (1 - dc / 0.30) ** 2
            cx += 7 * force * math.sin(dc * 95)
            cy += 6 * force * math.cos(dc * 71)
            zoom += 0.03 * force
        if t_noir <= t < t_carte:
            plein = noir.copy()
        else:
            plein = scenes.cadrer(im, zoom, cx, cy, taille)
            plein.paste(noir_haut, (0, 0), ombre_haut)  # haut assombri : le bandeau reste lisible
        d = ImageDraw.Draw(plein, "RGBA")

        # --- en-tête : apparaît quand le titre s'en va ; barres qui suivent la voix ; progression
        a_haut = min(1.0, max(0.0, (t - t_titre + 0.2) / 0.4))
        if a_haut > 0 and not (t_noir <= t < t_carte):
            x0, y0 = (LARGEUR - w_haut) / 2, 172
            d.rounded_rectangle([x0, y0, x0 + w_haut, y0 + 60], radius=30, fill=(0, 0, 0, int(135 * a_haut)))
            for b_ in range(4):
                hb = 6 + 26 * v * (0.55 + 0.45 * math.sin(t * 11 + b_ * 1.9)) if t < fin_voix else 6
                xb = x0 + 30 + b_ * 11
                d.rounded_rectangle([xb, y0 + 30 - hb / 2, xb + 6, y0 + 30 + hb / 2], radius=3,
                                    fill=accent + (int(255 * a_haut),))
            d.text((x0 + 86, y0 + 30), entete, font=f_haut, fill=(240, 240, 240, int(255 * a_haut)), anchor="lm")
            xa, xb = x0 + 30, x0 + w_haut - 30
            d.rounded_rectangle([xa, y0 + 70, xb, y0 + 76], radius=3, fill=(255, 255, 255, int(60 * a_haut)))
            d.rounded_rectangle([xa, y0 + 70, xa + max(6, (xb - xa) * t / duree_totale), y0 + 76], radius=3,
                                fill=accent + (int(255 * a_haut),))

        # --- titre d'ouverture : il claque, tient deux secondes, puis file vers le haut
        if t < t_titre + 0.3:
            sortie_t = scenes.doux((t - t_titre + 0.15) / 0.45)
            alpha = min(1.0, t / 0.12 + 0.35) * (1 - sortie_t)
            yt = HAUTEUR * 0.285 - 150 * sortie_t
            pas_t = f_titre * 1.22
            for n_l, etq in enumerate(e_titre):
                ech = 1.0 + min(0.5, (LARGEUR - 30) / etq.width - 1.0) * (1 - _rebond((t - 0.07 * n_l) / 0.38))
                _poser(plein, etq, LARGEUR / 2, yt + (n_l - (len(e_titre) - 1) / 2) * pas_t, ech, alpha if t >= 0.07 * n_l else 0)
            te = t - 0.32
            if te > 0:
                ae = min(1.0, te / 0.15) * (1 - sortie_t)
                ye = yt + len(e_titre) * pas_t / 2 + 58
                we = w_ep * (0.6 + 0.4 * _rebond(te / 0.3))
                d.rounded_rectangle([LARGEUR / 2 - we / 2, ye - 44, LARGEUR / 2 + we / 2, ye + 44], radius=44,
                                    fill=accent + (int(255 * ae),))
                d.text((LARGEUR / 2, ye), txt_ep, font=f_ep, fill=sombre + (int(255 * ae),), anchor="mm")

        if t < t_noir:
            # --- sous-titres : chaque mot arrive quand il est dit, le mot en cours est surligné
            while i_grp < len(grp) - 1 and t >= grp[i_grp + 1][0][1]:
                i_grp += 1
            g = grp[i_grp] if grp else None
            if g and g[0][1] - 0.05 <= t < g[-1][2] + 0.8:
                if i_grp not in pages:
                    pages.clear()
                    pages[i_grp] = mise_en_page(g)
                plein.paste(noir_bande, (0, y_bande), bande)
                d = ImageDraw.Draw(plein, "RGBA")
                for m, t0, t1, x, y, corps, fort in pages[i_grp]:
                    if t < t0 - 0.05:
                        continue
                    age = t - t0 + 0.05
                    # le mot « saute » à l'arrivée, sans mordre sur ses voisins quand il est long
                    saut = min(0.24, 44 / max(60.0, scenes.police(corps).getlength(m)))
                    ech = 1.0 + saut * (1 - scenes.doux(age / 0.16))
                    f = scenes.police(int(corps * ech))
                    if t < (t1 if m is g[-1][0] and t1 == g[-1][2] else t1 - 0.05):  # le mot en cours
                        wm = f.getlength(m)
                        hm = corps * ech
                        d.rounded_rectangle([x - wm / 2 - 11, y - hm * 0.62, x + wm / 2 + 11, y + hm * 0.62],
                                            radius=int(hm * 0.22), fill=accent + (255,))
                        d.text((x, y), m, font=f, fill=sombre + (255,), anchor="mm")
                    else:
                        d.text((x, y), m, font=f, fill=(accent if fort else (255, 255, 255)) + (255,), anchor="mm",
                               stroke_width=7, stroke_fill=(0, 0, 0, 235))
        elif carte >= 0:
            # --- carte de fin : « LA SUITE / DEMAIN À 20 H », puis l'épisode suivant dans un cercle qui se remplit
            yc = HAUTEUR * 0.37
            _poser(plein, e_l1, LARGEUR / 2, yc, 1.0 + min(0.9, (LARGEUR - 30) / e_l1.width - 1.0) * (1 - _rebond(carte / 0.30)),
                   min(1.0, 0.3 + carte / 0.08))
            c2 = carte - 0.26
            if c2 > 0:
                _poser(plein, e_l2, LARGEUR / 2, yc + 150, 1.0 + min(0.7, (LARGEUR - 30) / e_l2.width - 1.0) * (1 - _rebond(c2 / 0.30)),
                       min(1.0, 0.3 + c2 / 0.08))
            d = ImageDraw.Draw(plein, "RGBA")
            c3 = scenes.doux((carte - 0.55) / 0.45)
            if c3 > 0:
                d.rounded_rectangle([LARGEUR / 2 - 300 * c3, yc + 238, LARGEUR / 2 + 300 * c3, yc + 244], radius=3,
                                    fill=accent + (255,))
            c4 = min(1.0, max(0.0, (carte - 0.8) / 0.4))
            if c4 > 0:
                d.text((LARGEUR / 2, yc + 300 + 14 * (1 - c4)), bas, font=f_bas, fill=(240, 240, 240, int(255 * c4)),
                       anchor="mm", stroke_width=4, stroke_fill=(0, 0, 0, int(220 * c4)))
            c5 = carte - 1.0
            if c5 > 0 and suivant:
                r = 96 * (0.5 + 0.5 * _rebond(c5 / 0.35)) + 4 * math.sin(t * 6)
                xr, yr = LARGEUR / 2, yc + 480
                reste = max(0.0, min(1.0, c5 / max(0.4, duree_totale - t_carte - 1.15)))
                d.ellipse([xr - r, yr - r, xr + r, yr + r], fill=(0, 0, 0, 150), outline=(255, 255, 255, 70), width=8)
                d.arc([xr - r, yr - r, xr + r, yr + r], -90, -90 + 360 * reste, fill=accent + (255,), width=8)
                d.text((xr, yr - 46), "ÉPISODE", font=f_rond2, fill=(230, 230, 230, 255), anchor="mm")
                d.text((xr, yr + 14), str(numero + 1), font=f_rond, fill=accent + (255,), anchor="mm")
        if i == image_vignette:
            plein.save(sortie + ".jpg", quality=88)  # miniature : le titre sur le décor
        try:
            proc.stdin.write(plein.tobytes())
        except BrokenPipeError:
            break
    try:
        proc.stdin.close()
    except Exception:
        pass
    proc.wait(timeout=600)
    return proc.returncode == 0 and os.path.exists(sortie)


# ----------------------------------------------------------------------------- livraison
def telegram_video(chemin, legende):
    token, chat = env("TELEGRAM_BOT_TOKEN", ""), env("TELEGRAM_CHAT_ID", "")
    if not token or not chat or env("REVENUS_TELEGRAM", "1") == "0":
        return False
    if os.path.getsize(chemin) > 49 * 1024 * 1024:
        _log("Vidéo > 49 Mo, envoi Telegram impossible : " + chemin)
        return False
    limite = "----agentia" + uuid.uuid4().hex
    corps = io.BytesIO()

    def champ(nom, val):
        corps.write(f"--{limite}\r\nContent-Disposition: form-data; name=\"{nom}\"\r\n\r\n{val}\r\n".encode())
    champ("chat_id", chat)
    champ("caption", legende[:1000])
    champ("supports_streaming", "true")
    champ("width", str(LARGEUR))
    champ("height", str(HAUTEUR))
    corps.write(f"--{limite}\r\nContent-Disposition: form-data; name=\"video\"; filename=\"{os.path.basename(chemin)}\"\r\n"
                f"Content-Type: video/mp4\r\n\r\n".encode())
    with open(chemin, "rb") as f:
        corps.write(f.read())
    corps.write(f"\r\n--{limite}--\r\n".encode())
    req = urllib.request.Request(f"https://api.telegram.org/bot{token}/sendVideo", data=corps.getvalue(),
                                 headers={"Content-Type": f"multipart/form-data; boundary={limite}"}, method="POST")
    try:
        with urllib.request.urlopen(req, timeout=180) as r:
            return r.status == 200
    except Exception as e:
        _log(f"sendVideo : {e}")
        return False


def legende_tiktok(serie, numero, ep, secours):
    accro = ep["accroche"]
    l = f"{serie['titre']} — Épisode {numero}\n\n{accro}\n\n{serie['hashtags']}\n#voixsynthetique #fiction"
    if secours:
        l += "\n\n(Texte de secours : Ollama indisponible, épisode court.)"
    return l


def menage(garder=7):
    try:
        fichiers = sorted((os.path.join(VIDEOS, f) for f in os.listdir(VIDEOS) if f.endswith(".mp4")),
                          key=os.path.getmtime)
        for f in fichiers[:-garder]:
            for x in (f, f + ".jpg", f.replace(".mp4", ".txt")):
                if os.path.exists(x):
                    os.remove(x)
    except Exception:
        pass


# ----------------------------------------------------------------------------- commandes
def cmd_episode(force=None):
    os.makedirs(VIDEOS, exist_ok=True)
    b, e = bible(), etat()
    s, n = choisir(b, e, force)
    if s is None:
        # tout est épuisé : on tente une nouvelle saison sur la première série
        s0 = b["series"][0]
        if nouvelle_saison(b, s0):
            b = bible()
            s, n = choisir(b, e, force)
        if s is None:
            telegram("Studio TikTok : toutes les séries sont terminées et Ollama n'a pas pu écrire de nouvelle saison. "
                     "Ajoute des épisodes dans revenus/tiktok/bible.json.")
            return 1
    ep = s["episodes"][n - 1]
    debut = time.time()
    texte, secours = ecrire_episode(b, s, n)
    base = os.path.join(VIDEOS, f"{s['id']}_ep{n:02d}_{time.strftime('%Y%m%d')}")
    voix_wav, mix_wav, mp4 = base + "_voix.wav", base + "_mix.wav", base + ".mp4"
    duree_voix = dire(texte, voix_wav)
    if duree_voix <= 0:
        telegram(f"Studio TikTok : la voix a échoué pour {s['titre']} ép. {n}. Voir {JOURNAL}.")
        return 1
    total, duree_voix = mixer(voix_wav, mix_wav, graine=n)
    ok = rendre(texte, mix_wav, total, 0.4, duree_voix, s, n, mp4, suivant=n < len(s["episodes"]), voix_wav=voix_wav)
    for x in (voix_wav, voix_wav + ".json", mix_wav):
        if os.path.exists(x):
            os.remove(x)
    if not ok:
        telegram(f"Studio TikTok : le montage ffmpeg a échoué pour {s['titre']} ép. {n}. Voir {JOURNAL}.")
        return 1
    with open(base + ".txt", "w", encoding="utf-8") as f:
        f.write(legende_tiktok(s, n, ep, secours) + "\n\n---\n" + texte + "\n")
    taille = os.path.getsize(mp4) / 1e6
    e["episodes"][s["id"]] = n
    e["historique"].append({"date": horodatage(), "serie": s["id"], "episode": n, "mots": len(texte.split()),
                            "duree": round(total, 1), "mo": round(taille, 1), "secours": secours, "fichier": mp4})
    e["historique"] = e["historique"][-100:]
    ecrire_json(ETAT, e)
    legende = legende_tiktok(s, n, ep, secours)
    envoye = telegram_video(mp4, legende)
    if not envoye:
        telegram(f"Studio TikTok : vidéo prête mais non envoyée ({taille:.0f} Mo) : {mp4}\n\n{legende}")
    telegram("Légende à coller dans TikTok (appui long → copier) :\n\n" + legende, silencieux=True)
    if n == len(s["episodes"]) - 2:  # anticipe : écrit la saison suivante pendant qu'il reste 2 épisodes
        nouvelle_saison(b, s)
    menage(int(env("STUDIO_GARDER", "7")))
    _log(f"{s['id']} ép.{n} : {len(texte.split())} mots, {total:.0f} s, {taille:.1f} Mo, {time.time() - debut:.0f} s de calcul, secours={secours}")
    print(f"OK {mp4} ({total:.0f} s, {taille:.1f} Mo)")
    return 0


def cmd_apercu():
    os.makedirs(VIDEOS, exist_ok=True)
    b = bible()
    s = b["series"][0]
    texte = s["episodes"][0]["accroche"] + " À 2 h 14, la radio grésille. Ceci est un aperçu du studio : la voix, les décors animés et les sous-titres sont fabriqués sur le serveur, sans aucune clé."
    base = os.path.join(VIDEOS, "apercu")
    d = dire(texte, base + "_voix.wav")
    if d <= 0:
        print("Voix indisponible : lance d'abord  python3 revenus/tiktok/studio.py voix")
        return 1
    total, d = mixer(base + "_voix.wav", base + "_mix.wav", apres=2.5)
    ok = rendre(texte, base + "_mix.wav", total, 0.4, d, s, 1, base + ".mp4", voix_wav=base + "_voix.wav")
    print("OK" if ok else "ÉCHEC", base + ".mp4", f"{total:.1f} s")
    if ok and telegram_video(base + ".mp4", "Aperçu du studio TikTok"):
        print("Envoyé sur Telegram.")
    return 0 if ok else 1


def cmd_voix():
    """Installe Kokoro (voix naturelle) ; garde ou télécharge Piper comme secours."""
    import voix as voix_k
    ok = voix_k.installer()
    if not ok:
        print("Kokoro non installé : le studio continue avec la voix Piper.")
    secours = piper_dispo() and telecharger_voix()
    print("Voix de secours Piper : " + ("prête." if secours else "absente (facultatif si Kokoro est prêt)."))
    return 0 if (ok or secours) else 1


def cmd_test():
    import importlib
    rapport = []
    rapport.append(("ffmpeg", bool(shutil.which("ffmpeg"))))
    for mod in ("PIL", "numpy"):
        try:
            importlib.import_module(mod)
            rapport.append((mod, True))
        except Exception:
            rapport.append((mod, False))
    import voix as voix_k
    kokoro = bool(voix_k.python_kokoro())
    print(("OK   " if kokoro else "ABSENT ") + "voix Kokoro (naturelle)" + ("" if kokoro else " → python3 revenus/tiktok/studio.py voix"))
    if not kokoro:  # Piper n'est indispensable que si Kokoro manque
        rapport.append(("piper", piper_dispo()))
        rapport.append(("voix " + VOIX, os.path.exists(os.path.join(VOIX_DIR, VOIX + ".onnx"))))
    rapport.append(("police", any(os.path.exists(p) for p in POLICES)))
    b = bible()
    rapport.append((f"bible : {len(b['series'])} séries, {sum(len(s['episodes']) for s in b['series'])} épisodes", True))
    for nom, ok in rapport:
        print(("OK   " if ok else "MANQUE ") + nom)
    manque = [n for n, ok in rapport if not ok]
    if manque:
        print("\nÀ installer : sudo apt-get install -y ffmpeg fonts-dejavu-core && pip3 install --user piper-tts pillow numpy "
              "&& python3 revenus/tiktok/studio.py voix")
    return 0 if not manque else 1


def cmd_etat():
    b, e = bible(), etat()
    for s in b["series"]:
        n = e["episodes"].get(s["id"], 0)
        print(f"{s['id']:12s} {s['titre']:32s} {n}/{len(s['episodes'])} épisodes faits")
    for h in e["historique"][-5:]:
        print(f"  {h['date']}  {h['serie']} ép.{h['episode']}  {h['duree']} s  {h['mo']} Mo  {'(secours)' if h.get('secours') else ''}")
    return 0


if __name__ == "__main__":
    charger_env()
    os.makedirs(DOSSIER, exist_ok=True)
    args = [re.sub(r"[\s\u00a0]+$", "", a) for a in sys.argv[1:]]  # espace insécable iPhone
    cmd = (args[0] if args else "episode").lower()
    if cmd == "episode":
        sys.exit(cmd_episode(args[1] if len(args) > 1 else None))
    if cmd == "apercu":
        sys.exit(cmd_apercu())
    if cmd == "voix":
        sys.exit(cmd_voix())
    if cmd == "test":
        sys.exit(cmd_test())
    if cmd == "etat":
        sys.exit(cmd_etat())
    print(__doc__)
