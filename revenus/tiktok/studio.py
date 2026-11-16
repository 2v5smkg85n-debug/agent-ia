#!/usr/bin/env python3
"""Studio TikTok : écrit, dit, anime et monte un épisode par jour, puis l'envoie sur Telegram.

Tout tourne en local sur le VPS, sans clé ni API payante :
  - texte     : Ollama local (bible.json = séries, personnages, 12 épisodes chacune)
  - voix      : Piper TTS (voix fr_FR-siwis-medium, téléchargée une fois)
  - image     : fond animé procédural 1080×1920 (PIL + numpy), sous-titres mot à mot
  - montage   : ffmpeg (H.264 + AAC), ~70 s, < 50 Mo
  - livraison : Telegram sendVideo + légende prête à coller dans TikTok

Commandes :
  python3 revenus/tiktok/studio.py episode [id_serie]   → épisode suivant (ou de la série donnée)
  python3 revenus/tiktok/studio.py apercu              → 8 s de rendu pour vérifier voix + image
  python3 revenus/tiktok/studio.py voix                → télécharge la voix Piper
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
        texte = " ".join([ep["accroche"]] + [b_.rstrip(".") + "." for b_ in ep["beats"]] + [ep["suspens"]])
        texte = nettoyer_texte(texte)
    if not texte.lower().startswith(ep["accroche"].lower()[:30]):
        texte = ep["accroche"] + " " + texte
    if ep["suspens"].lower()[-25:].rstrip(". ») ") not in texte.lower():
        texte = texte.rstrip(" .") + ". " + ep["suspens"]
    mots = texte.split()
    if len(mots) > 270:  # coupe à la fin d'une phrase, puis remet le suspens
        coupe = " ".join(mots[:240])
        coupe = coupe[:coupe.rfind(".") + 1] if "." in coupe else coupe
        texte = coupe + " " + ep["suspens"]
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


# ----------------------------------------------------------------------------- voix (Piper)
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
    """Texte → WAV mono via Piper. Retourne la durée (s) ou 0."""
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


def champ_bruit(rng, w, h, cases):
    """Bruit lisse : petite grille aléatoire agrandie en bicubique (pas de dépendance externe)."""
    from PIL import Image
    import numpy as np
    petit = (rng.random((cases, int(cases * h / w) + 1)) * 255).astype("uint8")
    im = Image.fromarray(petit.T).resize((w, h), Image.BICUBIC)
    return np.asarray(im).astype("float32") / 255.0


def minutage_mots(texte, debut, duree):
    """Répartit la durée de la voix sur les mots (poids = longueur + ponctuation)."""
    mots = texte.split()
    poids = []
    for m in mots:
        p = len(re.sub(r"[^\w]", "", m)) + 1.2
        if m.endswith((".", "!", "?", "…")):
            p += 4.5
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


def groupes(minutes, taille=3):
    """Regroupe les mots par 3-4 en coupant aux ponctuations fortes."""
    g, cour = [], []
    for m in minutes:
        cour.append(m)
        fin = m[0].endswith((".", "!", "?", "…", ",", ";", ":"))
        if len(cour) >= taille + (0 if fin else 1) or (fin and len(cour) >= 2):
            g.append(cour)
            cour = []
    if cour:
        g.append(cour)
    return g


def rendre(texte, audio_wav, duree_totale, debut_voix, duree_voix, serie, numero, sortie, suivant=True):
    """Dessine chaque image et l'envoie à ffmpeg en flux brut (pas de PNG intermédiaire)."""
    from PIL import Image, ImageDraw, ImageFilter
    import numpy as np
    fond, milieu, accent = (hexa(c) for c in serie["palette"])
    rng = np.random.default_rng(sum(ord(c) for c in serie["id"]) * 31 + numero)
    W2, H2 = LARGEUR // 2, HAUTEUR // 2
    champ_a = champ_bruit(rng, W2 * 2, H2 * 2, 7)
    champ_b = champ_bruit(rng, W2 * 2, H2 * 2, 13)
    yy, xx = np.mgrid[0:H2, 0:W2].astype("float32")
    vignette = 1.0 - 0.75 * (((xx / W2 - 0.5) ** 2) * 1.3 + ((yy / H2 - 0.5) ** 2) * 0.9)
    vignette = np.clip(vignette, 0.15, 1.0)[..., None]
    col_fond, col_mil, col_acc = (np.array(c, dtype="float32") for c in (fond, milieu, accent))
    n_part = 70
    part = np.stack([rng.random(n_part) * LARGEUR, rng.random(n_part) * HAUTEUR,
                     12 + rng.random(n_part) * 40, rng.random(n_part) * 6.28, 2 + rng.random(n_part) * 5], axis=1)
    f_sous = police(84)
    f_haut = police(38)
    f_titre = police(96)
    f_petit = police(50)
    mots = minutage_mots(texte, debut_voix, duree_voix)
    grp = groupes(mots)
    n_images = int(duree_totale * FPS)
    entete = f"{serie['titre'].upper()}  ·  ÉPISODE {numero}"
    cmd = ["ffmpeg", "-y", "-loglevel", "error", "-f", "rawvideo", "-pix_fmt", "rgb24",
           "-s", f"{LARGEUR}x{HAUTEUR}", "-r", str(FPS), "-i", "-", "-i", audio_wav,
           "-c:v", "libx264", "-preset", env("STUDIO_PRESET", "veryfast"), "-crf", env("STUDIO_CRF", "26"),
           "-pix_fmt", "yuv420p", "-c:a", "aac", "-b:a", "128k", "-shortest", "-movflags", "+faststart", sortie]
    proc = subprocess.Popen(cmd, stdin=subprocess.PIPE)
    fin_voix = debut_voix + duree_voix
    for i in range(n_images):
        t = i / FPS
        # fond : deux nappes de bruit qui dérivent + respiration lente
        dx, dy = int(60 * math.sin(t * 0.11)) + W2 // 2, int((t * 9) % H2)
        a = champ_a[dy:dy + H2, dx:dx + W2]
        b = champ_b[(H2 - dy) % H2:(H2 - dy) % H2 + H2, W2 // 2:W2 // 2 + W2]
        if a.shape != (H2, W2) or b.shape != (H2, W2):
            a = np.resize(a, (H2, W2))
            b = np.resize(b, (H2, W2))
        resp = 0.85 + 0.15 * math.sin(t * 0.5)
        img = col_fond + (col_mil - col_fond) * (a[..., None] * 0.9 * resp) + col_acc * (b[..., None] ** 4) * 0.30
        img = np.clip(img * vignette, 0, 255).astype("uint8")
        im = Image.fromarray(img).resize((LARGEUR, HAUTEUR), Image.BILINEAR)
        d = ImageDraw.Draw(im, "RGBA")
        # particules (braises / poussière) qui montent lentement
        for p in part:
            x = p[0] + 25 * math.sin(t * 0.6 + p[3])
            y = (p[1] - t * p[4] * 10) % HAUTEUR
            r = p[2] / 10
            alpha = int(90 + 80 * math.sin(t * 1.3 + p[3]))
            d.ellipse([x - r, y - r, x + r, y + r], fill=accent + (max(20, alpha),))
        # en-tête + barre de progression
        d.rectangle([0, 0, LARGEUR, 120], fill=(0, 0, 0, 90))
        d.text((LARGEUR // 2, 62), entete, font=f_haut, fill=(235, 235, 235, 255), anchor="mm")
        d.rectangle([0, HAUTEUR - 14, int(LARGEUR * t / duree_totale), HAUTEUR], fill=accent + (255,))
        if t < fin_voix + 0.3:
            # sous-titres : groupe courant, mot en cours en couleur
            cour = None
            for g in grp:
                if g[0][1] <= t < g[-1][2]:
                    cour = g
                    break
            if cour is None and t < debut_voix:
                cour = grp[0]
            if cour:
                mots_g = [m[0] for m in cour]
                largeurs = [d.textlength(m + " ", font=f_sous) for m in mots_g]
                x = (LARGEUR - sum(largeurs)) / 2
                if sum(largeurs) > LARGEUR - 80:  # trop long : deux lignes
                    moitie = len(mots_g) // 2 or 1
                    lignes = [cour[:moitie], cour[moitie:]]
                else:
                    lignes = [cour]
                y = HAUTEUR * 0.50 - 50 * (len(lignes) - 1)
                for ligne in lignes:
                    ls = [d.textlength(m[0] + " ", font=f_sous) for m in ligne]
                    x = (LARGEUR - sum(ls)) / 2
                    for (m, t0, t1), lw in zip(ligne, ls):
                        actif = t0 <= t < t1
                        coul = accent if actif else (255, 255, 255)
                        d.text((x, y), m, font=f_sous, fill=coul + (255,), stroke_width=7,
                               stroke_fill=(0, 0, 0, 230), anchor="lm")
                        x += lw
                    y += 105
        else:
            # carte de fin
            d.rectangle([80, HAUTEUR * 0.36, LARGEUR - 80, HAUTEUR * 0.64], fill=(0, 0, 0, 150))
            d.text((LARGEUR // 2, HAUTEUR * 0.44), "La suite demain", font=f_titre, fill=(255, 255, 255, 255),
                   anchor="mm", stroke_width=4, stroke_fill=(0, 0, 0, 200))
            d.text((LARGEUR // 2, HAUTEUR * 0.51), "à 20 h" if suivant else "Fin de la saison", font=f_titre,
                   fill=accent + (255,), anchor="mm", stroke_width=4, stroke_fill=(0, 0, 0, 200))
            d.text((LARGEUR // 2, HAUTEUR * 0.585), f"Épisode {numero + 1} · abonne-toi pour la suite" if suivant
                   else "Merci d'avoir suivi cette histoire", font=f_petit, fill=(230, 230, 230, 255), anchor="mm")
        if i == 0:
            im.save(sortie + ".jpg", quality=85)  # miniature
        proc.stdin.write(im.tobytes())
    proc.stdin.close()
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
        telegram(f"Studio TikTok : la voix (Piper) a échoué pour {s['titre']} ép. {n}. Voir {JOURNAL}.")
        return 1
    total, duree_voix = mixer(voix_wav, mix_wav, graine=n)
    ok = rendre(texte, mix_wav, total, 0.4, duree_voix, s, n, mp4, suivant=n < len(s["episodes"]))
    for x in (voix_wav, mix_wav):
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
    texte = s["episodes"][0]["accroche"] + " Ceci est un aperçu du studio. La voix, le fond et les sous-titres sont générés sur le serveur, sans aucune clé."
    base = os.path.join(VIDEOS, "apercu")
    d = dire(texte, base + "_voix.wav")
    if d <= 0:
        print("Piper indisponible : lance d'abord  python3 revenus/tiktok/studio.py voix")
        return 1
    total, d = mixer(base + "_voix.wav", base + "_mix.wav", apres=2.5)
    ok = rendre(texte, base + "_mix.wav", total, 0.4, d, s, 1, base + ".mp4")
    print("OK" if ok else "ÉCHEC", base + ".mp4", f"{total:.1f} s")
    if ok and telegram_video(base + ".mp4", "Aperçu du studio TikTok"):
        print("Envoyé sur Telegram.")
    return 0 if ok else 1


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
        sys.exit(0 if telecharger_voix() else 1)
    if cmd == "test":
        sys.exit(cmd_test())
    if cmd == "etat":
        sys.exit(cmd_etat())
    print(__doc__)
