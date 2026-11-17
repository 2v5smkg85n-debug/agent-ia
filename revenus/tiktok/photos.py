#!/usr/bin/env python3
"""Plans photographiques du studio TikTok : de vraies images, mises en mouvement.

Quand une série possède des images dans medias/<serie>/ (avec plans.json), ses épisodes sont montés
avec elles plutôt qu'avec les décors dessinés de scenes.py. Chaque image vit :

- relief : une carte de profondeur (<nom>_prof.png, calculée une fois, blanc = proche) fait bouger
  le premier plan plus que le fond quand la caméra avance ou glisse, comme une vraie prise de vue ;
- défilement : derrière les vitres, le tunnel avance vers la caméra (boucle de zoom autour du point de fuite,
  limitée aux zones lointaines de la carte de profondeur), et la cabine vibre au passage des joints de rail ;
- lumière : les néons froids vacillent, les lampes chaudes respirent ou suivent la voix,
  les lumières du tunnel passent sur la cabine, la poussière flotte dans les faisceaux ;
- pellicule : vignettage et grain refaits à chaque image.

Rien n'est téléchargé ni généré au rendu : pillow + numpy suffisent, comme pour les décors dessinés.
STUDIO_PHOTOS=0 force les décors dessinés ; STUDIO_DEFILE=0 fige le tunnel ; STUDIO_VIBRATION=0 coupe les vibrations.
"""
import json
import math
import os

import numpy as np
from PIL import Image, ImageChops, ImageFilter

ICI = os.path.dirname(os.path.abspath(__file__))
MEDIAS = os.path.join(ICI, "medias")
PREFIXE = "photo:"
LARGEUR, HAUTEUR = 1080, 1920
NX, NY = 36, 64  # maillage de la déformation de relief (cases de 30 px)
MESH = getattr(getattr(Image, "Transform", Image), "MESH")
AFFINE = getattr(getattr(Image, "Transform", Image), "AFFINE")
_BANQUES = {}
_OUTILS = {}
_LUTS = {}


def _lut(k, canaux=3):
    """Table d'atténuation (0 → 1) par pas de 1/64, pour une image en couleurs (3) ou un masque (1)."""
    n = max(0, min(64, int(round(k * 64))))
    if (n, canaux) not in _LUTS:
        _LUTS[(n, canaux)] = [int(v * n / 64) for v in range(256)] * canaux
    return _LUTS[(n, canaux)]


def _hasard(*v):
    x = math.sin(sum((i + 1) * 12.9898 * float(a) for i, a in enumerate(v))) * 43758.5453
    return x - math.floor(x)


def _doux(x):
    x = max(0.0, min(1.0, x))
    return x * x * (3 - 2 * x)


class Banque:
    """Les images d'une série : nom → fiche (fichier, mots, cadrages, effets…)."""

    def __init__(self, dossier, fiches):
        self.dossier = dossier
        self.fiches = {f["nom"]: f for f in fiches}
        self.noms = [f["nom"] for f in fiches]

    def scenes(self, numero=None):
        """Les plans utilisables ; « depuis » réserve une image aux épisodes qui ont le droit de la montrer
        (la femme du quai n'apparaît pas avant que l'histoire la révèle)."""
        return [PREFIXE + n for n in self.noms if numero is None or int(self.fiches[n].get("depuis", 1) or 1) <= int(numero)]

    def mots(self, scene):
        return str(self.fiches[scene[len(PREFIXE):]].get("mots", "")).split()

    def replis(self):
        return [PREFIXE + n for n in self.noms if self.fiches[n].get("repli")]

    def pour_heure(self, h, m):
        """Le plan qui montre cette heure à l'écran (l'horloge de la cabine affiche 02:14)."""
        for n in self.noms:
            if list(self.fiches[n].get("heure") or []) == [h, m]:
                return PREFIXE + n
        return None

    def appele(self, scene, mots_phrase):
        """Le cadrage que la phrase réclame par un mot précis (« le voyant » → la lampe de la radio), ou None."""
        for k, c in enumerate(self.fiches[scene[len(PREFIXE):]].get("cadrages") or []):
            if len(c) > 3 and set(str(c[3]).split()) & set(mots_phrase):
                return k
        return None

    def cadrage(self, scene, mots_phrase, deja_vue):
        """Le cadrage d'une apparition : celui que la phrase appelle (« mes mains » → la main sur le levier),
        sinon le suivant dans l'ordre, pour qu'une image déjà vue revienne cadrée autrement."""
        cadrages = self.fiches[scene[len(PREFIXE):]].get("cadrages") or []
        for k, c in enumerate(cadrages):
            if len(c) > 3 and set(str(c[3]).split()) & set(mots_phrase):
                return k
        return deja_vue % max(1, len(cadrages))

    def chemin(self, nom):
        return os.path.join(self.dossier, self.fiches[nom]["fichier"])


def banque(serie_id):
    """La banque d'images de la série, ou None (pas d'images, fichier illisible, STUDIO_PHOTOS=0)."""
    if os.environ.get("STUDIO_PHOTOS", "1") == "0" or not serie_id:
        return None
    dossier = os.path.join(os.environ.get("STUDIO_MEDIAS", MEDIAS), str(serie_id))
    if dossier not in _BANQUES:
        res = None
        try:
            with open(os.path.join(dossier, "plans.json"), encoding="utf-8") as f:
                fiches = [x for x in json.load(f).get("plans", [])
                          if x.get("nom") and x.get("fichier") and os.path.exists(os.path.join(dossier, x["fichier"]))]
            if len(fiches) >= 3:  # en dessous, le montage tournerait en rond : on garde les décors dessinés
                res = Banque(dossier, fiches)
        except (OSError, ValueError, AttributeError):
            res = None
        _BANQUES[dossier] = res
    return _BANQUES[dossier]


def _outils():
    """Vignettage, grain, bande de lumière et grille du maillage : préparés une fois."""
    if _OUTILS:
        return _OUTILS
    yy, xx = np.mgrid[0:HAUTEUR // 4, 0:LARGEUR // 4].astype("float32")
    r = ((xx / (LARGEUR // 4) - 0.5) ** 2) * 1.3 + ((yy / (HAUTEUR // 4) - 0.5) ** 2) * 0.9
    vign = Image.fromarray((np.clip(1.0 - 0.62 * r, 0.3, 1.0) * 255).astype("uint8"))
    _OUTILS["vign"] = vign.resize((LARGEUR, HAUTEUR), Image.BILINEAR).convert("RGB")
    _OUTILS["serre"] = Image.fromarray((np.clip(r * 2.3, 0, 1) * 255).astype("uint8")).resize((LARGEUR, HAUTEUR), Image.BILINEAR)
    _OUTILS["noir"] = Image.new("RGB", (LARGEUR, HAUTEUR))
    rng = np.random.default_rng(11)
    grains = []
    for _ in range(4):  # grain de pellicule : même valeur sur les trois couleurs
        g = np.clip(rng.normal(9, 4.2, (HAUTEUR, LARGEUR, 1)), 0, 30).astype("uint8")
        grains.append(Image.fromarray(np.repeat(g, 3, axis=2)))
    _OUTILS["grains"] = grains
    lb = 760
    x = np.linspace(-1, 1, lb, dtype="float32")[None, :]
    y = np.linspace(0, 1, HAUTEUR // 4, dtype="float32")[:, None]
    bande = np.exp(-(x * 2.4) ** 2) * (0.55 + 0.45 * np.exp(-((y - 0.35) * 2.2) ** 2))
    _OUTILS["bande"] = Image.fromarray((bande * 255).astype("uint8")).resize((lb, HAUTEUR), Image.BILINEAR)
    _OUTILS["bande_coul"] = Image.new("RGB", (lb, HAUTEUR), (196, 218, 255))
    gu, gv = np.meshgrid(np.linspace(0, 1, NX + 1, dtype="float32"), np.linspace(0, 1, NY + 1, dtype="float32"))
    _OUTILS["gu"], _OUTILS["gv"] = gu, gv
    cw, ch = LARGEUR // NX, HAUTEUR // NY
    _OUTILS["cases"] = [(i * cw, j * ch, (i + 1) * cw, (j + 1) * ch) for j in range(NY) for i in range(NX)]
    return _OUTILS


def _relief(prof, x, y):
    """Profondeur (0 loin → 1 proche) aux points (x, y) donnés en fraction de l'image, interpolée."""
    ph, pw = prof.shape
    fx = np.clip(x, 0, 1) * (pw - 1)
    fy = np.clip(y, 0, 1) * (ph - 1)
    x0 = np.minimum(fx.astype("int32"), pw - 2)
    y0 = np.minimum(fy.astype("int32"), ph - 2)
    ax, ay = fx - x0, fy - y0
    haut = prof[y0, x0] * (1 - ax) + prof[y0, x0 + 1] * ax
    bas = prof[y0 + 1, x0] * (1 - ax) + prof[y0 + 1, x0 + 1] * ax
    return haut * (1 - ay) + bas * ay


def _preparer_defile(im, prof, df):
    """Prépare le tunnel qui défile : zone lointaine (carte de profondeur) + point de fuite. None si rien à animer."""
    ws, hs = im.size
    ph, pw = prof.shape
    seuil = float(df.get("seuil", 0.18))
    m = np.clip((seuil - prof) / max(0.02, seuil * 0.4), 0, 1)
    zx0, zy0, zx1, zy1 = (list(df.get("zone") or []) + [0, 0, 1, 1])[:4] if df.get("zone") else (0, 0, 1, 1)
    yy, xx = np.mgrid[0:ph, 0:pw]
    m = m * (((xx + 0.5) / pw >= zx0) & ((xx + 0.5) / pw <= zx1) & ((yy + 0.5) / ph >= zy0) & ((yy + 0.5) / ph <= zy1))
    if pw >= 24:  # la zone est rentrée d'un cran : le défilement ne doit pas mordre sur les montants des vitres
        m = np.asarray(Image.fromarray((m * 255).astype("uint8")).filter(ImageFilter.MinFilter(3)), dtype="float32") / 255.0
    if m.max() < 0.5:
        return None
    ys, xs = np.where(m > 0.04)
    x0, x1 = int(xs.min() / pw * ws) // 4 * 4, min(ws, -(-int((xs.max() + 1) / pw * ws) // 4) * 4)
    y0, y1 = int(ys.min() / ph * hs) // 4 * 4, min(hs, -(-int((ys.max() + 1) / ph * hs) // 4) * 4)
    if x1 - x0 < 64 or y1 - y0 < 64:
        return None
    masque = Image.fromarray((m * 255).astype("uint8")).resize((ws, hs), Image.BICUBIC).crop((x0, y0, x1, y1))
    r = 2  # le tunnel en mouvement est calculé à demi-résolution : plus rapide, et le flou de vitesse est naturel
    petit = im.crop((x0, y0, x1, y1)).resize(((x1 - x0) // r, (y1 - y0) // r), Image.BILINEAR)
    px, py = (list(df.get("point") or [0.5, 0.4]) + [0.4])[:2]
    return {"boite": (x0, y0, x1, y1), "masque": masque, "petit": petit, "masque_petit": masque.resize(petit.size, Image.BILINEAR),
            "vx": (px * ws - x0) / r, "vy": (py * hs - y0) / r,
            "ampleur": max(1.2, float(df.get("ampleur", 1.8))), "periode": max(0.4, float(df.get("periode", 1.5)))}


def fabriquer(plan):
    """Construit le plan photographique : un objet appelable, avec .plein(...) → image 1080×1920 finie."""
    b = banque(plan.get("serie"))
    nom = plan["scene"][len(PREFIXE):]
    fiche = b.fiches[nom]
    im = Image.open(b.chemin(nom)).convert("RGB")
    if abs(im.width / im.height - LARGEUR / HAUTEUR) > 0.01:  # image d'un autre format : on recadre au centre en 9:16
        w = min(im.width, int(im.height * LARGEUR / HAUTEUR))
        h = min(im.height, int(w * HAUTEUR / LARGEUR))
        x0, y0 = (im.width - w) // 2, (im.height - h) // 2
        im = im.crop((x0, y0, x0 + w, y0 + h))
    ws, hs = im.size
    o = _outils()
    effets = set(fiche.get("effets") or [])
    cadrages = fiche.get("cadrages") or [[0.5, 0.4, 1.0]]
    fx, fy, serrage = (list(cadrages[int(plan.get("cadrage", 0)) % len(cadrages)][:3]) + [1.0])[:3]
    fxs, fys = fx * ws, fy * hs
    # --- le relief : carte de profondeur, 0.5 partout si elle manque (l'image reste plane mais vivante)
    try:
        chemin_prof = os.path.splitext(b.chemin(nom))[0] + "_prof.png"
        prof = np.asarray(Image.open(chemin_prof).convert("L"), dtype="float32") / 255.0
    except (OSError, ValueError):
        prof = np.full((16, 9), 0.5, dtype="float32")
    d0 = float(_relief(prof, np.array([fx]), np.array([fy]))[0])  # le sujet reste fixe, le reste bouge autour
    # --- les lumières : halos des zones claires, froides (néons, écrans) et chaudes (voyants, lampes)
    petit = im.resize((ws // 4, hs // 4), Image.BILINEAR)
    a = np.asarray(petit, dtype="float32")
    clair = np.clip((a.max(axis=2) - 150) / 80, 0, 1)[..., None]
    chaud = (a[..., 0] > a[..., 2] * 1.15)[..., None]
    halo_c = Image.fromarray((a * clair * ~chaud * 0.55).astype("uint8")).filter(ImageFilter.GaussianBlur(7))
    halo_w = Image.fromarray((a * clair * chaud * 0.75).astype("uint8")).filter(ImageFilter.GaussianBlur(7))
    # --- le défilement : le tunnel avance derrière les vitres ; la cabine vibre quand la rame roule
    defile = None
    if fiche.get("defile") and os.environ.get("STUDIO_DEFILE", "1") != "0":
        try:
            defile = _preparer_defile(im, prof, fiche["defile"])
        except Exception:
            defile = None
    roule = "roule" in effets and os.environ.get("STUDIO_VIBRATION", "1") != "0"
    t0_plan = float(plan.get("t0", 0.0))
    graine = float(plan.get("graine", 0)) % 977
    phase = _hasard(graine, 3) * 6.28
    cote = 1 if _hasard(graine, 5) > 0.5 else -1
    camera = plan.get("camera", "avant")
    # --- la poussière : des grains lents, visibles surtout dans la lumière
    grains_p = [(_hasard(graine, k, 1), _hasard(graine, k, 2), 0.004 + 0.012 * _hasard(graine, k, 3),
                 1.0 + 2.2 * _hasard(graine, k, 4), _hasard(graine, k, 6) * 6.28) for k in range(34)] if "poussiere" in effets else []
    couleur_p = Image.new("RGB", (LARGEUR, HAUTEUR), (255, 232, 190))

    def plein(tl, p, v, i, zoom, glisse=0.0, tremble=(0.0, 0.0), noirceur=0.0):
        """L'image du plan à l'instant tl (s) : caméra + relief + lumières + pellicule, en 1080×1920."""
        e = _doux(p)
        z = max(1.0, zoom * serrage)
        w, h = ws / z, hs / z
        # caméra : le sujet vise le tiers haut de l'écran ; le glissement reste dans l'image
        pan = min(0.042 * ws, (ws - w) / 2) if camera in ("droite", "gauche") else 0.0
        tt = t0_plan + tl  # temps de l'épisode : vibrations et défilement continuent d'un plan à l'autre
        bx, by = tremble
        if roule:  # la rame roule : vibration fine + double à-coup à chaque joint de rail
            bx += 0.7 * math.sin(tt * 38.0 + phase) + 0.5 * math.sin(tt * 61.0)
            by += 0.9 * math.sin(tt * 44.0) + 0.6 * math.sin(tt * 71.0 + 1.0)
            c = tt % 1.24
            for retard in (0.0, 0.17):
                dj = c - retard
                if 0.0 <= dj < 0.2:
                    by += 4.0 * (1 - dj / 0.2) ** 2 * math.cos(dj * 55)
        mx, my = min(14.0, (ws - w) / 2), min(14.0, (hs - h) / 2)  # un peu de marge pour que l'image puisse vibrer
        cx = min(max(fxs, w / 2 + pan + mx), ws - w / 2 - pan - mx) + glisse * pan
        cy = min(max(fys + 0.09 * h, h / 2 + my), hs - h / 2 - my)
        x0 = min(max(cx - w / 2 + bx * ws / 540, 0.0), ws - w)
        y0 = min(max(cy - h / 2 + by * hs / 960, 0.0), hs - h)
        sx = x0 + o["gu"] * w
        sy = y0 + o["gv"] * h
        # relief : chaque point se décale selon sa profondeur (le proche bouge plus que le lointain)
        dp = _relief(prof, sx / ws, sy / hs) - d0
        if camera in ("droite", "gauche"):
            lat, fuite = glisse * 20.0, 0.012
        else:
            lat = 13.0 * math.sin(tl * 0.85 + phase) * cote
            fuite = 0.052 * (e if camera == "avant" else 1 - e)
        haut = 6.0 * math.sin(tl * 0.6 + phase * 1.7) + 2.0 * math.sin(tl * 1.4)
        qx = np.clip(sx - dp * (lat + (sx - fxs) * fuite), 0, ws - 1)
        qy = np.clip(sy - dp * (haut + (sy - fys) * fuite), 0, hs - 1)
        quads = np.stack([qx[:-1, :-1], qy[:-1, :-1], qx[1:, :-1], qy[1:, :-1],
                          qx[1:, 1:], qy[1:, 1:], qx[:-1, 1:], qy[:-1, 1:]], axis=-1).reshape(-1, 8).tolist()
        source = im
        if defile:  # deux copies du tunnel grossissent en boucle autour du point de fuite et se relaient
            q0 = (tt / defile["periode"] + phase / 6.28) % 1.0
            couches = []
            for q in (q0, (q0 + 0.5) % 1.0):
                k = 1.0 / defile["ampleur"] ** q
                mat = (k, 0, defile["vx"] * (1 - k), 0, k, defile["vy"] * (1 - k))
                couche = defile["petit"].transform(defile["petit"].size, AFFINE, mat, Image.BILINEAR)
                # là où la copie agrandie viendrait d'un objet proche (une tête, un bras), on garde le tunnel d'origine
                couches.append(Image.composite(couche, defile["petit"],
                                               defile["masque_petit"].transform(defile["petit"].size, AFFINE, mat, Image.BILINEAR)))
            melange = Image.blend(couches[0], couches[1], math.sin(math.pi * ((q0 + 0.5) % 1.0)) ** 2)
            bx0, by0, bx1, by1 = defile["boite"]
            source = im.copy()
            source.paste(melange.resize((bx1 - bx0, by1 - by0), Image.BILINEAR), (bx0, by0), defile["masque"])
        vue = source.transform((LARGEUR, HAUTEUR), MESH, list(zip(o["cases"], quads)), Image.BILINEAR)
        # lumières : les néons vacillent (avec de rares creux), les lampes chaudes respirent ou suivent la voix
        kc = kw = 0.0
        if "neons" in effets:
            kc = 0.30 + 0.16 * math.sin(tl * 2.3 + phase) + 0.10 * math.sin(tl * 7.1)
            if _hasard(graine, math.floor(tl * 9)) < 0.04:
                kc = -0.55
        if "voix" in effets:
            kw = 0.12 + 0.88 * min(1.0, v * 1.5)
        elif "voyants" in effets:
            kw = 0.34 + 0.22 * math.sin(tl * 1.1 + phase) + 0.25 * v
        if kc > 0.03 or kw > 0.03:
            g = ImageChops.add(halo_c.point(_lut(max(0.0, kc))), halo_w.point(_lut(max(0.0, kw))))
            vue = ImageChops.add(vue, g.resize((LARGEUR, HAUTEUR), Image.BILINEAR, box=(x0 / 4, y0 / 4, (x0 + w) / 4, (y0 + h) / 4)))
        if kc < -0.03:
            g = halo_c.point(_lut(-kc))
            vue = ImageChops.subtract(vue, g.resize((LARGEUR, HAUTEUR), Image.BILINEAR, box=(x0 / 4, y0 / 4, (x0 + w) / 4, (y0 + h) / 4)))
        # les lumières du tunnel passent sur la cabine
        if "passage" in effets:
            cycle = 1.24
            n = math.floor((tt + phase) / cycle)
            q = ((tt + phase) % cycle) / 0.5
            force = 0.35 + 0.65 * _hasard(graine, n, 9)
            if q < 1.0 and force > 0.42:
                lb = o["bande"].width
                xb = int((LARGEUR + lb) * (1 - q) - lb) if cote > 0 else int((LARGEUR + lb) * q - lb)
                vue.paste(o["bande_coul"], (xb, 0), o["bande"].point(_lut(0.20 * force, 1)))
        if grains_p:
            calque = np.zeros((HAUTEUR // 4, LARGEUR // 4), dtype="float32")
            for gx, gy, vit, taille_g, ph_g in grains_p:
                px = (gx + 0.02 * math.sin(tl * 0.5 + ph_g) + tl * vit * 0.6) % 1.0
                py = (gy * 0.72 - tl * vit) % 0.72
                ix, iy = int(px * (LARGEUR // 4 - 3)), int(py * (HAUTEUR // 4 - 3))
                calque[iy:iy + 2, ix:ix + 2] += (0.25 + 0.75 * (0.5 + 0.5 * math.sin(tl * 1.3 + ph_g))) * taille_g * 44
            masque = Image.fromarray(np.clip(calque, 0, 255).astype("uint8")).filter(ImageFilter.GaussianBlur(0.9))
            vue.paste(couleur_p, (0, 0), masque.resize((LARGEUR, HAUTEUR), Image.BILINEAR))
        # pellicule
        vue = ImageChops.multiply(vue, o["vign"])
        if noirceur > 0.02:
            vue.paste(o["noir"], (0, 0), o["serre"].point(_lut(noirceur, 1)))
        return ImageChops.add(vue, o["grains"][i % 4], 1, -9)

    def dessine(t, p, v):
        """Aperçu au format des décors dessinés (540×960), pour les outils qui n'attendent que cela."""
        return plein(t, p, v, 0, 1.08).resize((540, 960), Image.BILINEAR)

    dessine.photo = True
    dessine.plein = plein
    dessine.foyer = (fx * 540, fy * 960)
    dessine.nom = nom
    return dessine
