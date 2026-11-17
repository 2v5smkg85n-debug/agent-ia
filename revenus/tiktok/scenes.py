#!/usr/bin/env python3
"""Décors animés du studio TikTok : de vraies scènes qui bougent, dessinées image par image.

Chaque série a son décor (métro, lettres, immeuble) : cinq scènes dessinées en 540×960 avec PIL,
plus deux scènes communes (horloge, compteur) déclenchées par le texte (« 2 h 14 », « 640 euros »).
Le découpage suit les phrases : un plan par phrase (2 à 6,5 s), la scène est choisie par les mots
de la phrase, la caméra avance, recule ou glisse, et chaque coupe a sa transition.

Aucune clé, rien de téléchargé au rendu : tout est calculé sur le VPS (pillow + numpy). Les séries qui ont
leurs propres photographies (medias/<serie>/) sont montées avec elles : voir photos.py.
"""
import math
import os
import re
import unicodedata

import numpy as np
from PIL import Image, ImageChops, ImageDraw, ImageFilter, ImageFont

L, H = 540, 960  # résolution de dessin des scènes (agrandie ×2 au montage)
POLICES = ["/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
           "/usr/share/fonts/dejavu/DejaVuSans-Bold.ttf",
           "/usr/share/fonts/truetype/liberation/LiberationSans-Bold.ttf"]
_POLICES = {}
BLANC = (255, 255, 255)


# ----------------------------------------------------------------------------- outils
def police(taille):
    taille = max(6, int(taille))
    if taille not in _POLICES:
        f = None
        for p in POLICES:
            if os.path.exists(p):
                f = ImageFont.truetype(p, taille)
                break
        _POLICES[taille] = f or ImageFont.load_default()
    return _POLICES[taille]


def melange(a, b, k):
    k = max(0.0, min(1.0, k))
    return tuple(int(a[i] + (b[i] - a[i]) * k) for i in range(3))


def lum(c, k):
    return tuple(max(0, min(255, int(v * k))) for v in c)


def borne(x, a=0.0, b=1.0):
    return a if x < a else b if x > b else x


def doux(x):
    """Départ rapide, arrivée douce (0 → 1)."""
    x = borne(x)
    return 1 - (1 - x) ** 3


def lisse(x):
    x = borne(x)
    return x * x * (3 - 2 * x)


def hasard(*v):
    """Nombre pseudo-aléatoire stable dans [0, 1[ à partir de quelques valeurs."""
    s = 0.0
    for i, x in enumerate(v):
        s += float(x) * (12.9898 + 7.233 * i)
    s = math.sin(s) * 43758.5453
    return s - math.floor(s)


def clignote(t, graine, taux=0.15, cadence=11):
    """1.0 la plupart du temps, une valeur basse par à-coups (néon fatigué)."""
    return 0.25 if hasard(math.floor(t * cadence), graine) < taux else 1.0


def degrade(haut, bas):
    y = np.linspace(0, 1, H, dtype="float32")[:, None, None]
    a, b = np.array(haut, "float32"), np.array(bas, "float32")
    arr = np.repeat(a + (b - a) * y, L, axis=1)
    return Image.fromarray(arr.astype("uint8"))


def _disque(n=128):
    yy, xx = np.mgrid[0:n, 0:n].astype("float32")
    r = np.sqrt((xx - n / 2 + 0.5) ** 2 + (yy - n / 2 + 0.5) ** 2) / (n / 2)
    return Image.fromarray((np.clip(1 - r, 0, 1) ** 2 * 255).astype("uint8"))


_DISQUE = _disque()
_LUTS = {}


def _lut(force):
    k = int(borne(force) * 50)
    if k not in _LUTS:
        _LUTS[k] = [int(v * k / 50) for v in range(256)]
    return _LUTS[k]


def halo(im, x, y, r, coul, force=1.0):
    """Lueur douce (disque dégradé) posée sur l'image."""
    r = int(r)
    if r < 2 or force <= 0.02:
        return
    m = _DISQUE.resize((2 * r, 2 * r), Image.BILINEAR)
    if force < 0.99:
        m = m.point(_lut(force))
    # une image unie plutôt qu'une couleur : 50 fois plus rapide avec les anciens Pillow (Ubuntu 22.04)
    im.paste(Image.new("RGB", m.size, tuple(coul)), (int(x) - r, int(y) - r), m)


def brume(rng, w=540, h=320):
    """Texture de brume (bruit lissé, raccordable) qu'on fait défiler horizontalement : image 2w × h."""
    petit = (rng.random((7, 12)) * 255).astype("uint8")
    im = Image.fromarray(petit).resize((w, h), Image.BICUBIC).filter(ImageFilter.GaussianBlur(30))
    yy = np.linspace(0, 1, h, dtype="float32")[:, None]
    xx = np.linspace(0, 1, w, dtype="float32")[None, :]
    arr = np.asarray(im).astype("float32")
    arr = arr * (1 - xx) + np.roll(arr, w // 2, axis=1) * xx  # fondu pour que la droite rejoigne la gauche
    arr *= np.clip(np.minimum(yy, 1 - yy) * 3.5, 0, 1)
    return Image.fromarray(np.concatenate([arr, arr], axis=1).astype("uint8"))


def gribouillis(rng, x0, x1, y, pas=5):
    """Ligne d'écriture manuscrite : suites de boucles séparées par des blancs (les mots)."""
    mots, x = [], x0
    while x < x1 - 20:
        long_mot = int(rng.integers(4, 11)) * pas * 2
        pts = []
        ph = rng.random() * 6.28
        for xx in range(int(x), int(min(x + long_mot, x1)), pas):
            pts.append((xx, y + 6.5 * math.sin(ph + xx * 0.55) + 2.5 * math.sin(xx * 1.7 + ph)))
        if len(pts) > 2:
            mots.append(pts)
        x += long_mot + 16
    return mots


def sans_accent(s):
    return "".join(c for c in unicodedata.normalize("NFD", s.lower()) if unicodedata.category(c) != "Mn")


def tourne(pts, cx, cy, a):
    ca, sa = math.cos(a), math.sin(a)
    return [(cx + (x - cx) * ca - (y - cy) * sa, cy + (x - cx) * sa + (y - cy) * ca) for x, y in pts]


def silhouette(d, x, y, h, coul, bras=True):
    """Personnage debout (pieds en x, y). Retourne la position de la main."""
    w = h * 0.30
    d.polygon([(x - w * 0.45, y), (x - w * 0.08, y), (x - w * 0.04, y - h * 0.42), (x - w * 0.5, y - h * 0.42)], fill=coul)
    d.polygon([(x + w * 0.08, y), (x + w * 0.45, y), (x + w * 0.5, y - h * 0.42), (x + w * 0.04, y - h * 0.42)], fill=coul)
    d.polygon([(x - w * 0.66, y - h * 0.34), (x + w * 0.66, y - h * 0.34), (x + w * 0.44, y - h * 0.81),
               (x - w * 0.44, y - h * 0.81)], fill=coul)
    r = h * 0.085
    d.ellipse([x - r, y - h * 0.985, x + r, y - h * 0.985 + 2 * r], fill=coul)
    d.rectangle([x - r * 1.3, y - h * 0.99, x + r * 1.3, y - h * 0.99 + r * 0.55], fill=coul)
    ep = max(2, int(h * 0.075))
    if bras:
        main = (x + w * 1.05, y - h * 1.0)
        d.line([(x + w * 0.38, y - h * 0.76), main], fill=coul, width=ep)
    else:
        main = (x + w * 0.75, y - h * 0.40)
        d.line([(x + w * 0.42, y - h * 0.78), main], fill=coul, width=ep)
    return main


_SEG = {"0": "abcdef", "1": "bc", "2": "abged", "3": "abgcd", "4": "fgbc", "5": "afgcd", "6": "afgedc",
        "7": "abc", "8": "abcdefg", "9": "abcdfg"}


def sept_segments(d, x, y, w, h, chiffre, coul, eteint, e):
    """Chiffre d'afficheur à sept segments (segments hexagonaux), coin haut-gauche en (x, y)."""
    m, c, j = h / 2, e / 2, 3

    def horiz(xa, xb, yy):
        return [(xa, yy), (xa + c, yy - c), (xb - c, yy - c), (xb, yy), (xb - c, yy + c), (xa + c, yy + c)]

    def vert(xx, ya, yb):
        return [(xx, ya), (xx + c, ya + c), (xx + c, yb - c), (xx, yb), (xx - c, yb - c), (xx - c, ya + c)]

    seg = {"a": horiz(x + j, x + w - j, y), "g": horiz(x + j, x + w - j, y + m), "d": horiz(x + j, x + w - j, y + h),
           "f": vert(x, y + j, y + m - j), "e": vert(x, y + m + j, y + h - j),
           "b": vert(x + w, y + j, y + m - j), "c": vert(x + w, y + m + j, y + h - j)}
    for nom, pts in seg.items():
        d.polygon(pts, fill=coul if nom in _SEG.get(chiffre, "") else eteint)


# ----------------------------------------------------------------------------- décor « métro »
def sc_tunnel(pal, rng, info):
    """Vue de la cabine : le tunnel fonce vers nous, lampes et traverses défilent."""
    fond, mil, acc = pal
    base = degrade(lum(fond, 0.5), lum(fond, 0.9))
    vit = 0.34 + 0.16 * rng.random()
    n = 13
    vx0, vy0 = 270, 350
    graine = float(rng.random() * 100)

    def dessine(t, p, v):
        im = base.copy()
        d = ImageDraw.Draw(im, "RGBA")
        vx, vy = vx0 + 14 * math.sin(t * 0.5 + graine), vy0 + 6 * math.sin(t * 0.8 + 1)
        halo(im, vx, vy, 260, lum(mil, 1.3), 0.9)
        halo(im, vx, vy, 70 + 30 * v, acc, 0.55 + 0.35 * v)
        ph = (t * vit) % 1.0
        # traverses (deux par anneau)
        for k in range(2 * n):
            q = (k + 2 * ph) / (2 * n)
            s = 0.02 + q ** 2.6 * 2.3
            y = vy + 285 * s
            if y > H + 20:
                continue
            d.line([(vx - 150 * s, y), (vx + 150 * s, y)], fill=melange(fond, mil, 0.5) + (int(230 * min(1, q * 2.5)),),
                   width=max(1, int(1 + 15 * q * q)))
        # rails et câbles
        for cote in (-1, 1):
            d.line([(vx + cote * 2, vy + 3), (vx + cote * 225, H + 10)], fill=melange(mil, acc, 0.45) + (220,), width=4)
            d.line([(vx + cote * 3, vy - 4), (vx + cote * 470, -30)], fill=lum(mil, 0.8) + (140,), width=2)
        # anneaux du tunnel, du plus lointain au plus proche
        for k in range(n):
            q = (k + ph) / n
            s = 0.02 + q ** 2.6 * 2.3
            w, h = 300 * s, 380 * s
            a = int(255 * min(1, q * 3.5))
            ep = max(1, int(2 + 20 * q * q))
            d.rounded_rectangle([vx - w, vy - h * 0.9, vx + w, vy + h * 0.75], radius=min(w, h) * 0.75,
                                outline=melange(fond, lum(mil, 1.5), 0.35 + 0.65 * q) + (a,), width=ep)
            # lampes latérales : un trait dans le sens de la fuite
            q2 = max(0.0, q - 0.045)
            s2 = 0.02 + q2 ** 2.6 * 2.3
            allume = clignote(t, k + graine, 0.08)
            for cote in (-1, 1):
                x1, y1 = vx + cote * 300 * s * 0.93, vy - 380 * s * 0.38
                x0, y0 = vx + cote * 300 * s2 * 0.93, vy - 380 * s2 * 0.38
                d.line([(x0, y0), (x1, y1)], fill=acc + (int(a * allume),), width=max(1, int(1 + 9 * q)))
                if q > 0.45 and allume == 1.0 and -40 < x1 < L + 40:
                    halo(im, x1, y1, 26 + 60 * q, acc, 0.55)
        # montants du pare-brise et pupitre
        d.polygon([(0, 0), (30, 0), (16, H), (0, H)], fill=lum(fond, 0.35))
        d.polygon([(L, 0), (L - 30, 0), (L - 16, H), (L, H)], fill=lum(fond, 0.35))
        d.polygon([(0, H), (0, 850), (120, 818), (420, 818), (L, 850), (L, H)], fill=lum(fond, 0.4))
        d.line([(0, 850), (120, 818), (420, 818), (L, 850)], fill=mil + (255,), width=3)
        for i in range(4):
            c = acc if hasard(i, math.floor(t * 2)) > 0.4 else lum(mil, 1.3)
            d.ellipse([150 + i * 26, 842, 162 + i * 26, 854], fill=c)
        d.arc([330, 836, 410, 916], 200, 340, fill=mil + (255,), width=3)
        ang = math.radians(215 + 95 * (0.5 + 0.5 * math.sin(t * 0.7)))
        d.line([(370, 876), (370 + 34 * math.cos(ang), 876 + 34 * math.sin(ang))], fill=acc, width=3)
        return im

    dessine.foyer = (vx0, vy0)
    return dessine


def sc_radio(pal, rng, info):
    """Radio de cabine : l'onde suit la voix, l'aiguille cherche la fréquence."""
    fond, mil, acc = pal
    base = degrade(lum(fond, 1.0), lum(fond, 0.5))
    d0 = ImageDraw.Draw(base, "RGBA")
    d0.rounded_rectangle([34, 140, 506, 470], radius=26, fill=lum(mil, 0.45), outline=lum(mil, 1.2), width=3)
    d0.rounded_rectangle([56, 162, 484, 392], radius=14, fill=lum(fond, 0.35))
    for x in range(56, 485, 43):
        d0.line([(x, 162), (x, 392)], fill=mil + (70,), width=1)
    for y in range(162, 393, 46):
        d0.line([(56, y), (484, y)], fill=mil + (70,), width=1)
    d0.rounded_rectangle([56, 408, 484, 452], radius=8, fill=lum(fond, 0.5))
    for cx in (60, 480):
        d0.ellipse([cx - 9, 480, cx + 9, 498], fill=lum(mil, 0.9))
    heure = info.get("heure") or info.get("heure_defaut") or (2, 14)
    graine = float(rng.random() * 100)

    def dessine(t, p, v):
        im = base.copy()
        d = ImageDraw.Draw(im, "RGBA")
        halo(im, 270, 277, 230, acc, 0.10 + 0.22 * v)
        amp = 10 + 96 * v
        for decal, alpha, ep in ((0.35, 70, 2), (0.0, 255, 4)):
            pts = []
            for x in range(60, 481, 6):
                e = math.sin(math.pi * (x - 60) / 420)
                y = 277 + amp * e * (0.6 * math.sin(x * 0.047 + (t - decal) * 9) + 0.3 * math.sin(x * 0.113 - (t - decal) * 15)
                                     + 0.25 * (hasard(x, math.floor((t - decal) * 24)) - 0.5))
                pts.append((x, y))
            d.line(pts, fill=acc + (alpha,), width=ep, joint="curve")
        if v < 0.12:  # parasites entre les phrases
            for i in range(14):
                x, y = 60 + hasard(i, t) * 400, 170 + hasard(t, i) * 214
                d.line([(x, y), (x + 8 + 30 * hasard(i, t, 2), y)], fill=lum(acc, 0.9) + (150,), width=2)
        # cadran des fréquences
        for i in range(16):
            x = 60 + ((i * 28 - t * 26) % 420)
            d.line([(x, 416 if i % 4 else 410), (x, 444)], fill=lum(mil, 1.6) + (220,), width=2)
        xa = 270 + 120 * math.sin(t * 0.9 + graine) * math.sin(t * 0.37)
        d.line([(xa, 404), (xa, 456)], fill=acc, width=5)
        # horloge de bord
        deux = ":" if (t * 2) % 2 < 1.2 else " "
        d.text((72, 174), f"{heure[0]:02d}{deux}{heure[1]:02d}", font=police(34), fill=melange(acc, BLANC, 0.2), anchor="lt")
        # haut-parleur : anneaux de points qui battent avec la voix
        for j, r in enumerate((26, 52, 78, 104, 130)):
            nb = int(r * 0.32)
            rr = 2.5 + 4.5 * v * (0.6 + 0.4 * math.sin(t * 10 - j))
            c = melange(lum(mil, 1.3), acc, v * (1 - j * 0.12))
            for i in range(nb):
                a = 2 * math.pi * i / nb + j * 0.3
                x, y = 270 + r * math.cos(a), 705 + r * math.sin(a)
                d.ellipse([x - rr, y - rr, x + rr, y + rr], fill=c)
        d.ellipse([264, 699, 276, 711], fill=acc)
        return im

    dessine.foyer = (270, 290)
    return dessine


def sc_quai(pal, rng, info):
    """Le quai fantôme : panneau qui grésille, silhouette à la lanterne, brume au sol."""
    fond, mil, acc = pal
    vx, vy = 300, 352
    base = degrade(lum(fond, 0.45), lum(fond, 0.8))
    d0 = ImageDraw.Draw(base, "RGBA")
    d0.polygon([(L, 40), (L, 790), (vx, vy + 16), (vx, vy - 34)], fill=melange(fond, mil, 0.55))
    d0.polygon([(0, 130), (0, 650), (vx, vy + 10), (vx, vy - 30)], fill=melange(fond, mil, 0.28))
    d0.polygon([(120, H), (L, H), (L, 790), (vx, vy + 16)], fill=melange(fond, mil, 0.8))
    d0.polygon([(0, H), (120, H), (vx, vy + 16), (0, 650)], fill=lum(fond, 0.4))
    d0.polygon([(120, H), (158, H), (vx + 2, vy + 16), (vx, vy + 16)], fill=melange(mil, acc, 0.6) + (210,))
    for k in range(1, 10):
        d0.line([(L, 40 + 750 * k / 10), (vx, vy - 34 + 50 * k / 10)], fill=lum(fond, 0.6) + (120,), width=1)
    for q in (0.05, 0.085, 0.13, 0.19, 0.27, 0.38, 0.53, 0.74):
        x = vx + (L - vx) * q
        d0.line([(x, vy - 34 + (40 - (vy - 34)) * q), (x, vy + 16 + (790 - (vy + 16)) * q)],
                fill=lum(fond, 0.6) + (120,), width=1 + int(q * 3))
    d0.line([(8, H), (vx - 16, vy + 13)], fill=lum(mil, 1.5) + (160,), width=3)
    d0.line([(78, H), (vx - 7, vy + 15)], fill=lum(mil, 1.5) + (160,), width=3)
    voile = brume(rng)
    panneau = (info.get("panneau") or "TERMINUS").upper()
    graine = float(rng.random() * 100)
    f_pan = police(30 if len(panneau) < 14 else 24)

    def dessine(t, p, v):
        im = base.copy()
        d = ImageDraw.Draw(im, "RGBA")
        # plafonniers en enfilade
        for k, q in enumerate((0.10, 0.17, 0.27, 0.42, 0.64, 0.95)):
            x, y = vx + (440 - vx) * q, vy - 34 + (30 - (vy - 34)) * q
            on = clignote(t, k * 7 + graine, 0.22 if k == 3 else 0.04)
            halo(im, x, y + 20 * q, 150 * q + 20, acc, 0.32 * on)
            d.rounded_rectangle([x - 46 * q, y - 6 * q, x + 46 * q, y + 6 * q], radius=3, fill=melange(mil, acc, on) + (255,))
        # panneau suspendu
        on = clignote(t, graine, 0.2, 9)
        d.line([(170, 150), (170, 226)], fill=lum(mil, 1.4), width=2)
        d.line([(388, 150), (388, 226)], fill=lum(mil, 1.4), width=2)
        halo(im, 279, 256, 170, acc, 0.22 * on)
        d.rounded_rectangle([128, 226, 430, 286], radius=8, fill=lum(mil, 0.75), outline=melange(mil, acc, on), width=3)
        d.text((279, 256), panneau, font=f_pan, fill=melange(lum(mil, 1.2), BLANC, on), anchor="mm")
        # silhouette qui lève sa lanterne
        hs = 78 * (1 + 0.35 * p)
        sx, sy = vx + 44, vy + 50 + 46 * p
        main = silhouette(d, sx, sy, hs, lum(fond, 0.25) + (255,), bras=True)
        puls = 0.75 + 0.25 * math.sin(t * 3.1) + 0.3 * v
        halo(im, main[0], main[1] + 8, 62 * puls, acc, 0.8)
        d.ellipse([main[0] - 5, main[1] + 2, main[0] + 5, main[1] + 14], fill=BLANC)
        halo(im, sx, sy + 4, 60, acc, 0.25)
        # brume qui glisse sur le quai
        dx = int(t * 26) % L
        im.paste(Image.new("RGB", (L, 320), melange(mil, BLANC, 0.5)), (0, 610), voile.crop((dx, 0, dx + L, 320)).point(_lut(0.62)))
        return im

    dessine.foyer = (vx + 30, vy + 10)
    return dessine


def sc_rame(pal, rng, info):
    """La rame passe à toute vitesse : fenêtres éclairées, étincelles, reflets sur le quai."""
    fond, mil, acc = pal
    base = degrade(lum(fond, 0.5), lum(fond, 0.85))
    d0 = ImageDraw.Draw(base, "RGBA")
    d0.rectangle([0, 600, L, H], fill=melange(fond, mil, 0.55))
    for k in range(7):
        d0.line([(270 + (k - 3) * 30, 600), (270 + (k - 3) * 260, H)], fill=lum(fond, 0.7) + (150,), width=2)
    d0.rectangle([0, 600, L, 612], fill=melange(mil, acc, 0.55))
    sens = -1 if rng.random() < 0.5 else 1
    vit = 1050 + 400 * rng.random()
    traits = [(float(rng.random() * L), float(120 + rng.random() * 430), float(40 + rng.random() * 140),
               float(900 + rng.random() * 900)) for _ in range(16)]

    def dessine(t, p, v):
        im = base.copy()
        d = ImageDraw.Draw(im, "RGBA")
        sy = 3 * math.sin(t * 31)
        # caisse de la rame
        d.rectangle([0, 215 + sy, L, 560 + sy], fill=melange(fond, mil, 0.9))
        d.rectangle([0, 215 + sy, L, 228 + sy], fill=lum(mil, 1.5))
        d.rectangle([0, 492 + sy, L, 502 + sy], fill=melange(mil, acc, 0.5))
        d.rectangle([0, 560 + sy, L, 600], fill=lum(fond, 0.3))
        pas = 150
        dec = (t * vit * sens) % (pas * 5)
        for k in range(-6, 10):
            x = k * pas + dec - pas * 5 if sens > 0 else k * pas + dec
            porte = (k % 5 == 0)
            for j, a in ((3, 45), (2, 80), (1, 130), (0, 255)):  # traînée de vitesse
                xx = x - sens * j * 26
                if porte:
                    d.rectangle([xx + 30, 262 + sy, xx + 62, 478 + sy], fill=lum(acc, 0.8) + (a,))
                    d.rectangle([xx + 70, 262 + sy, xx + 102, 478 + sy], fill=lum(acc, 0.8) + (a,))
                else:
                    d.rounded_rectangle([xx + 14, 268 + sy, xx + 122, 410 + sy], radius=12, fill=acc + (a,))
            if not porte and -140 < x < L:
                d.rounded_rectangle([x + 14, 640, x + 122, 760], radius=10, fill=acc + (45,))  # reflet au sol
                if hasard(k, 3) > 0.55:  # un voyageur
                    d.ellipse([x + 52, 300 + sy, x + 84, 334 + sy], fill=lum(fond, 0.5) + (230,))
                    d.rounded_rectangle([x + 40, 332 + sy, x + 96, 410 + sy], radius=10, fill=lum(fond, 0.5) + (230,))
        halo(im, 270, 340, 330, acc, 0.16 + 0.1 * math.sin(t * 20))
        for x0, y, lg, vt in traits:  # filets d'air
            x = (x0 + sens * t * vt) % (L + 200) - 100
            d.line([(x, y), (x + lg, y)], fill=BLANC + (38,), width=2)
        for i in range(12):  # étincelles au rail
            if hasard(i, math.floor(t * 18)) > 0.55:
                x, y = hasard(i, t) * L, 566 + hasard(t, i) * 30
                d.line([(x, y), (x - sens * (10 + 30 * hasard(i, 7, t)), y + 6)], fill=melange(acc, BLANC, 0.6), width=2)
        return im

    dessine.foyer = (270, 350)
    return dessine


def sc_plan_ligne(pal, rng, info):
    """Le plan de la ligne se trace ; entre deux stations, un point qui ne devrait pas exister."""
    fond, mil, acc = pal
    base = degrade(melange(fond, mil, 0.35), melange(fond, mil, 0.15))
    d0 = ImageDraw.Draw(base, "RGBA")
    for x in range(0, L, 36):
        d0.line([(x, 0), (x, H)], fill=mil + (60,), width=1)
    for y in range(0, H, 36):
        d0.line([(0, y), (L, y)], fill=mil + (60,), width=1)
    pts = [(96, 880), (120, 760), (170, 660), (250, 560), (290, 440), (300, 345), (352, 268), (418, 200), (446, 128)]
    stations = info.get("stations") or ["Station A", "Station B", "Station C", "Station D", "Station E"]
    idx = [1, 3, 5, 6, 7][:len(stations)]
    fant = info.get("fantome") or "?"
    gx, gy = pts[4]
    longs = [math.dist(pts[i], pts[i + 1]) for i in range(len(pts) - 1)]
    total = sum(longs)

    def dessine(t, p, v):
        im = base.copy()
        d = ImageDraw.Draw(im, "RGBA")
        reste = total * doux(t / 1.3)
        trace, fait = [pts[0]], 0.0
        for i, lg in enumerate(longs):
            if reste >= lg:
                trace.append(pts[i + 1])
                reste -= lg
                fait += 1
            else:
                k = reste / lg
                trace.append((pts[i][0] + (pts[i + 1][0] - pts[i][0]) * k, pts[i][1] + (pts[i + 1][1] - pts[i][1]) * k))
                break
        if len(trace) > 1:
            d.line(trace, fill=lum(mil, 0.5) + (255,), width=18, joint="curve")
            d.line(trace, fill=acc + (255,), width=10, joint="curve")
        for nom, i in zip(stations, idx):
            if fait >= i:
                x, y = pts[i]
                d.ellipse([x - 13, y - 13, x + 13, y + 13], fill=BLANC, outline=lum(fond, 0.5), width=4)
                gauche = x >= 290
                d.text((x - 24 if gauche else x + 24, y), nom, font=police(21), fill=BLANC + (235,),
                       anchor="rm" if gauche else "lm")
        if t > 1.2:  # la station fantôme
            k = t - 1.2
            for j in range(3):
                q = ((k * 0.7 + j / 3) % 1)
                r = 14 + 96 * q
                d.ellipse([gx - r, gy - r, gx + r, gy + r], outline=BLANC + (int(210 * (1 - q)),), width=3)
            halo(im, gx, gy, 70 + 30 * v, BLANC, 0.45 + 0.3 * v)
            for a in range(0, 360, 30):
                d.arc([gx - 17, gy - 17, gx + 17, gy + 17], a + t * 60, a + 16 + t * 60, fill=BLANC, width=4)
            on = clignote(t, 3, 0.25, 8)
            d.text((gx - 36, gy), fant, font=police(26), fill=melange(mil, BLANC, on), anchor="rm")
            # cercle au stylo autour du point
            e = lisse((k - 0.3) / 0.7)
            if e > 0:
                d.arc([gx - 240, gy - 50, gx + 56, gy + 50], -200, -200 + 380 * e, fill=melange(acc, BLANC, 0.3), width=4)
        return im

    dessine.foyer = (gx - 30, gy + 20)
    return dessine


# ----------------------------------------------------------------------------- décor « lettres »
def sc_fenetre(pal, rng, info):
    """Pluie sur la vitre, lumières de la ville en flou, le chat sur le rebord."""
    fond, mil, acc = pal
    base = degrade(melange(fond, mil, 0.55), lum(fond, 1.2))
    ville = Image.new("RGB", (760, H), (0, 0, 0))
    for _ in range(46):
        c = [acc, lum(mil, 2.2), melange(acc, BLANC, 0.4), melange(mil, acc, 0.5)][int(rng.integers(0, 4))]
        halo(ville, rng.random() * 760, 240 + rng.random() * 520, 18 + rng.random() * 50, c, 0.35 + 0.45 * rng.random())
    ville = ville.filter(ImageFilter.GaussianBlur(4))
    gouttes = [(float(rng.random() * L), float(170 + rng.random() * 420), float(14 + rng.random() * 40), float(rng.random()))
               for _ in range(80)]
    perles = [(float(rng.random() * L), float(rng.random() * H), float(2 + rng.random() * 4)) for _ in range(34)]
    eclair = 0.25 + rng.random() * 1.2 if rng.random() < 0.6 else -1
    chat = info.get("chat", False)

    def dessine(t, p, v):
        dx = int(110 + 60 * math.sin(t * 0.12))
        im = ImageChops.screen(base, ville.crop((dx, 0, dx + L, H)))
        d = ImageDraw.Draw(im, "RGBA")
        if eclair > 0 and eclair < t < eclair + 0.5:
            k = t - eclair
            f = (1 - k / 0.5) * (1.0 if k < 0.08 or 0.16 < k < 0.24 else 0.35)
            d.rectangle([0, 0, L, H], fill=melange(acc, BLANC, 0.7) + (int(150 * f),))
        for x, vt, lg, ph in gouttes:
            y = (ph * (H + 80) + t * vt) % (H + 80) - 40
            d.line([(x, y - lg), (x, y - lg * 0.4)], fill=BLANC + (34,), width=1)
            d.line([(x, y - lg * 0.4), (x, y)], fill=BLANC + (110,), width=2)
        for i, (x, y, r) in enumerate(perles):
            yy = (y + 22 * max(0.0, math.sin(t * 0.5 + i)) ** 6 * t) % H
            d.ellipse([x - r, yy - r, x + r, yy + r], fill=BLANC + (45,), outline=BLANC + (120,))
        # croisée de la fenêtre et rebord
        sombre = lum(fond, 0.35)
        d.rectangle([0, 0, L, 26], fill=sombre)
        d.rectangle([0, 0, 24, H], fill=sombre)
        d.rectangle([L - 24, 0, L, H], fill=sombre)
        d.rectangle([262, 0, 278, H], fill=sombre)
        d.rectangle([0, 318, L, 332], fill=sombre)
        d.rectangle([0, 790, L, H], fill=sombre)
        d.rectangle([0, 790, L, 796], fill=lum(mil, 1.1))
        if chat:  # Virgule regarde dehors
            cx, cy = 400, 790
            d.ellipse([cx - 46, cy - 92, cx + 46, cy + 6], fill=sombre)
            d.ellipse([cx - 26, cy - 140, cx + 26, cy - 88], fill=sombre)
            d.polygon([(cx - 24, cy - 126), (cx - 18, cy - 160), (cx - 2, cy - 136)], fill=sombre)
            d.polygon([(cx + 24, cy - 126), (cx + 18, cy - 160), (cx + 2, cy - 136)], fill=sombre)
            q = [(cx + 40 + i * 5, cy - 8 - 26 * math.sin(i * 0.33 + math.sin(t * 1.6) * 0.9) * i / 12) for i in range(13)]
            d.line(q, fill=sombre, width=11, joint="curve")
        return im

    dessine.foyer = (270, 330)
    return dessine


def sc_lettre(pal, rng, info):
    """La lettre s'écrit toute seule, la plume avance, le cachet de l'année brille."""
    fond, mil, acc = pal
    papier = melange(acc, fond, 0.42)
    base = degrade(lum(fond, 1.3), lum(fond, 0.7))
    halo(base, 90, 110, 380, melange(acc, mil, 0.5), 0.35)
    ang = (rng.random() - 0.5) * 0.09
    feuille = tourne([(64, 120), (476, 120), (476, 990), (64, 990)], 270, 480, ang)
    d0 = ImageDraw.Draw(base, "RGBA")
    d0.polygon([(x + 10, y + 12) for x, y in feuille], fill=(0, 0, 0, 120))
    d0.polygon(feuille, fill=papier)
    lignes = []
    for j in range(13):
        for mot in gribouillis(rng, 104 if j else 200, 440 if j % 4 != 3 else 300, 262 + j * 50):
            lignes.append(tourne(mot, 270, 480, ang))
    nb_pts = sum(len(m) for m in lignes)
    date = info.get("date") or ""
    encre = lum(fond, 0.9)
    pd = tourne([(436, 186)], 270, 480, ang)[0]
    pc = tourne([(140, 262)], 270, 480, ang)[0]

    def dessine(t, p, v):
        im = base.copy()
        d = ImageDraw.Draw(im, "RGBA")
        if date:
            d.text(pd, date, font=police(22), fill=encre, anchor="rm")
        reste = int(nb_pts * borne(0.10 + p * 1.0))
        bout = None
        for mot in lignes:
            if reste <= 1:
                break
            seg = mot[:reste]
            if len(seg) > 1:
                d.line(seg, fill=encre + (235,), width=3, joint="curve")
                bout = seg[-1]
            reste -= len(mot)
        if bout:  # la plume
            halo(im, bout[0], bout[1], 34 + 14 * v, acc, 0.9)
            d.line([bout, (bout[0] + 42, bout[1] - 74)], fill=lum(fond, 0.5), width=6)
            d.line([bout, (bout[0] + 8, bout[1] - 14)], fill=BLANC, width=3)
        # cachet rond en haut de la feuille
        if date:
            puls = 0.6 + 0.4 * math.sin(t * 2.4)
            c = melange(mil, acc, 0.25) + (int(150 + 80 * puls),)
            d.ellipse([pc[0] - 40, pc[1] - 110, pc[0] + 40, pc[1] - 30], outline=c, width=4)
            d.text((pc[0], pc[1] - 70), date[-4:], font=police(24), fill=c, anchor="mm")
        return im

    dessine.foyer = (270, 380)
    return dessine


def sc_horloges(pal, rng, info):
    """Des horloges qui s'emballent, certaines à l'envers, et les années qui défilent."""
    fond, mil, acc = pal
    base = degrade(lum(fond, 0.9), melange(fond, mil, 0.5))
    cadrans = [(270, 268, 128, 1.0), (84, 150, 50, -2.3), (462, 160, 56, 3.1), (86, 770, 76, -1.4), (446, 800, 92, 2.0),
               (486, 520, 46, -3.4), (58, 470, 40, 4.2)]
    annees = info.get("annees")
    graine = float(rng.random() * 10)

    def dessine(t, p, v):
        im = base.copy()
        d = ImageDraw.Draw(im, "RGBA")
        halo(im, 270, 268, 300, mil, 0.8)
        for i, (cx, cy, r, vit) in enumerate(cadrans):
            c = acc if i == 0 else melange(mil, acc, 0.45)
            ep = 6 if i == 0 else 3
            d.ellipse([cx - r, cy - r, cx + r, cy + r], outline=c, width=ep, fill=lum(fond, 0.7) + (200,))
            for k in range(12):
                a = k * math.pi / 6
                r0 = r * (0.80 if k % 3 == 0 else 0.88)
                d.line([(cx + r0 * math.sin(a), cy - r0 * math.cos(a)), (cx + r * 0.95 * math.sin(a), cy - r * 0.95 * math.cos(a))],
                       fill=c, width=max(2, ep - 2))
            am = (t * (1.2 + t * 0.35) * vit + graine + i) % (2 * math.pi) if i == 0 else t * 1.6 * vit + i
            ah = am / 12 + i
            d.line([(cx, cy), (cx + r * 0.52 * math.sin(ah), cy - r * 0.52 * math.cos(ah))], fill=BLANC, width=ep + 2)
            d.line([(cx, cy), (cx + r * 0.80 * math.sin(am), cy - r * 0.80 * math.cos(am))], fill=BLANC, width=ep)
            d.ellipse([cx - ep, cy - ep, cx + ep, cy + ep], fill=acc)
        if annees:  # le compteur d'années
            a0, a1 = annees
            an = int(a0 + (a1 - a0) * doux(p * 1.25))
            d.rounded_rectangle([176, 408, 364, 462], radius=12, fill=lum(fond, 0.5) + (235,), outline=acc, width=3)
            d.text((270, 435), str(an), font=police(40), fill=BLANC if an < a1 else acc, anchor="mm")
        return im

    dessine.foyer = (270, 290)
    return dessine


def sc_enveloppes(pal, rng, info):
    """Une pluie d'enveloppes qui tombent en tournant, sur trois profondeurs."""
    fond, mil, acc = pal
    base = degrade(melange(fond, mil, 0.6), lum(fond, 0.9))
    halo(base, 270, 60, 520, melange(mil, acc, 0.4), 0.5)
    objets = sorted(((float(26 + rng.random() ** 1.6 * 110), float(rng.random() * L), float(rng.random()),
                      float(rng.random() * 6.28), float(0.5 + rng.random() * 1.3)) for _ in range(20)))

    def dessine(t, p, v):
        im = base.copy()
        d = ImageDraw.Draw(im, "RGBA")
        for w, x0, ph, a0, vr in objets:
            prof = (w - 26) / 110
            y = (ph * (H + 300) + t * (60 + 170 * prof)) % (H + 300) - 150
            x = x0 + 34 * math.sin(t * vr * 0.8 + a0)
            a = 0.5 * math.sin(t * vr + a0) + (a0 - 3.14) * 0.12
            h = w * 0.64
            rect = tourne([(x - w, y - h), (x + w, y - h), (x + w, y + h), (x - w, y + h)], x, y, a)
            teinte = melange(lum(mil, 1.1), acc, 0.25 + 0.75 * prof)
            d.polygon([(px + 6 * prof, py + 9 * prof) for px, py in rect], fill=(0, 0, 0, 70))
            d.polygon(rect, fill=teinte, outline=lum(fond, 0.8))
            c = tourne([(x, y + h * 0.18)], x, y, a)[0]
            d.line([rect[0], c, rect[1]], fill=lum(teinte, 0.6), width=max(1, int(1 + 3 * prof)))
            if w > 60:
                tb = tourne([(x + w * 0.56, y - h * 0.76), (x + w * 0.86, y - h * 0.76), (x + w * 0.86, y - h * 0.30),
                             (x + w * 0.56, y - h * 0.30)], x, y, a)
                d.polygon(tb, fill=melange(mil, acc, 0.3), outline=lum(fond, 0.8))
                for j in range(3):
                    l0 = tourne([(x - w * 0.6, y + h * (0.42 + j * 0.16)), (x + w * (0.25 - j * 0.15), y + h * (0.42 + j * 0.16))], x, y, a)
                    d.line(l0, fill=lum(teinte, 0.55), width=3)
        return im

    dessine.foyer = (270, 380)
    return dessine


def sc_cachet(pal, rng, info):
    """L'enveloppe glisse sur la table, le cachet de la poste s'abat dessus."""
    fond, mil, acc = pal
    base = degrade(lum(fond, 1.3), lum(fond, 0.7))
    halo(base, 430, 120, 420, melange(acc, mil, 0.5), 0.3)
    papier = melange(acc, fond, 0.30)
    ang = -0.07 + (rng.random() - 0.5) * 0.05
    ville = (info.get("cachet") or "POSTE").upper()
    annee = (info.get("date") or "")[-4:]
    eclats = [(float(rng.random() * 6.28), float(30 + rng.random() * 120)) for _ in range(18)]
    t_choc = 0.55

    def dessine(t, p, v):
        im = base.copy()
        d = ImageDraw.Draw(im, "RGBA")
        gl = (1 - doux(t / 0.4)) * 560
        sec = 0.0
        if t_choc < t < t_choc + 0.3:
            sec = (1 - (t - t_choc) / 0.3) * 9
        ox, oy = sec * math.sin(t * 90), gl + sec * math.cos(t * 70)
        cx, cy = 270 + ox, 370 + oy
        env = tourne([(cx - 220, cy - 150), (cx + 220, cy - 150), (cx + 220, cy + 150), (cx - 220, cy + 150)], cx, cy, ang)
        d.polygon([(x + 12, y + 16) for x, y in env], fill=(0, 0, 0, 130))
        d.polygon(env, fill=papier, outline=lum(papier, 0.6))
        for j, lg in enumerate((230, 190, 150)):
            d.line(tourne([(cx - 180, cy + 10 + j * 38), (cx - 180 + lg, cy + 10 + j * 38)], cx, cy, ang), fill=lum(fond, 0.9) + (220,), width=5)
        tb = tourne([(cx + 120, cy - 128), (cx + 196, cy - 128), (cx + 196, cy - 34), (cx + 120, cy - 34)], cx, cy, ang)
        d.polygon(tb, fill=melange(mil, acc, 0.35), outline=lum(fond, 0.7))
        d.polygon(tourne([(cx + 132, cy - 116), (cx + 184, cy - 116), (cx + 184, cy - 46), (cx + 132, cy - 46)], cx, cy, ang),
                  outline=lum(fond, 0.7))
        if t > t_choc - 0.12:  # le tampon
            k = borne((t - (t_choc - 0.12)) / 0.12)
            e = 1 + 1.6 * (1 - k)
            px, py = tourne([(cx + 86, cy - 76)], cx, cy, ang)[0]
            c = melange(mil, fond, 0.35) + (int(235 * k),)
            r = 78 * e
            d.ellipse([px - r, py - r, px + r, py + r], outline=c, width=int(6 * e))
            d.ellipse([px - r * 0.74, py - r * 0.74, px + r * 0.74, py + r * 0.74], outline=c, width=int(3 * e))
            d.text((px, py - r * 0.16), ville, font=police(22 * e), fill=c, anchor="mm")
            d.text((px, py + r * 0.24), annee, font=police(30 * e), fill=c, anchor="mm")
            for j in range(4):
                o = [(px - r - 150 + i * 12, py - 30 + j * 20 + 5 * math.sin(i * 0.9)) for i in range(13)]
                d.line(o, fill=c, width=int(3 * e), joint="curve")
            if t > t_choc:
                kk = (t - t_choc) / 0.5
                if kk < 1:
                    for a, dist in eclats:
                        x, y = px + math.cos(a) * dist * doux(kk) * 1.6, py + math.sin(a) * dist * doux(kk) * 1.6
                        d.ellipse([x - 3, y - 3, x + 3, y + 3], fill=c[:3] + (int(220 * (1 - kk)),))
                    rr = 80 + 260 * doux(kk)
                    d.ellipse([px - rr, py - rr, px + rr, py + rr], outline=acc + (int(160 * (1 - kk)),), width=5)
        return im

    dessine.foyer = (330, 310)
    return dessine


def sc_encre(pal, rng, info):
    """La tache s'étale sur la page, et dessous, une phrase cachée se met à briller."""
    fond, mil, acc = pal
    papier = melange(acc, fond, 0.40)
    base = Image.new("RGB", (L, H), papier)
    cache = Image.new("RGB", (L, H), melange(fond, mil, 0.55))
    d0, d1 = ImageDraw.Draw(base, "RGBA"), ImageDraw.Draw(cache, "RGBA")
    for j in range(17):
        for mot in gribouillis(rng, 44, 500, 90 + j * 52):
            d0.line(mot, fill=lum(fond, 0.9) + (190,), width=3, joint="curve")
            d1.line(mot, fill=melange(acc, BLANC, 0.5), width=4, joint="curve")
    lueur = cache.filter(ImageFilter.GaussianBlur(5))
    cache = ImageChops.screen(cache, lueur)
    cx, cy = 250 + rng.random() * 60, 300 + rng.random() * 60
    ph = [float(rng.random() * 6.28) for _ in range(3)]
    sat = [(float(rng.random() * 6.28), float(1.15 + rng.random() * 0.5), float(8 + rng.random() * 22)) for _ in range(9)]

    def contour(r):
        pts = []
        for i in range(120):
            a = i * 2 * math.pi / 120
            rr = r * (1 + 0.13 * math.sin(3 * a + ph[0]) + 0.06 * math.sin(5 * a + ph[1]) + 0.025 * math.sin(9 * a + ph[2]))
            pts.append((cx + rr * math.cos(a), cy + rr * math.sin(a) * 1.15))
        return pts

    def dessine(t, p, v):
        im = base.copy()
        r = 14 + 150 * doux(t / 3.5) + 14 * t
        masque = Image.new("L", (L, H), 0)
        dm = ImageDraw.Draw(masque)
        dm.polygon(contour(r), fill=255)
        for a, k, rs in sat:
            if r * k > 40:
                x, y = cx + r * k * math.cos(a), cy + r * k * math.sin(a) * 1.15
                dm.ellipse([x - rs, y - rs, x + rs, y + rs], fill=255)
        im.paste(cache, (0, 0), masque)
        d = ImageDraw.Draw(im, "RGBA")
        d.line(contour(r) + contour(r)[:1], fill=lum(fond, 0.6) + (220,), width=5, joint="curve")
        d.line(contour(r * 0.93) + contour(r * 0.93)[:1], fill=acc + (60,), width=2)
        halo(im, cx, cy, 120 + 60 * v, acc, 0.25 + 0.3 * v)
        return im

    dessine.foyer = (int(cx), int(cy))
    return dessine


# ----------------------------------------------------------------------------- décor « immeuble »
def sc_escalier(pal, rng, info):
    """La cage d'escalier vue d'en haut : une spirale sans fond qui tourne et nous aspire."""
    fond, mil, acc = pal
    base = Image.new("RGB", (L, H), lum(fond, 0.6))
    sens = 1 if rng.random() < 0.5 else -1
    cx, cy = 270, 350
    n = 15
    graine = float(rng.random() * 50)

    def carre(q, t):
        s = 9 * 1.36 ** q
        a = sens * (q * 0.21 + t * 0.07)
        return tourne([(cx - s, cy - s), (cx + s, cy - s), (cx + s, cy + s), (cx - s, cy + s)], cx, cy, a)

    def dessine(t, p, v):
        im = base.copy()
        d = ImageDraw.Draw(im, "RGBA")
        ph = (t * 0.42) % 1.0
        on = clignote(t, graine, 0.10)
        anneaux = [carre(k + ph, t) for k in range(n, -2, -1)]
        for i in range(len(anneaux) - 1):
            ext, inte = anneaux[i], anneaux[i + 1]
            q = (n - i + ph) / n
            ton = melange(lum(fond, 0.7), mil, (0.25 + 0.6 * (1 - q)) * (0.55 + 0.45 * on))
            d.polygon(ext, fill=ton if (n - i) % 2 else lum(ton, 0.78))
            for c in range(4):  # les marches entre deux volées
                a0, a1 = ext[c], ext[(c + 1) % 4]
                b0, b1 = inte[c], inte[(c + 1) % 4]
                for m in range(1, 7):
                    k = m / 7
                    d.line([(a0[0] + (a1[0] - a0[0]) * k, a0[1] + (a1[1] - a0[1]) * k),
                            (b0[0] + (b1[0] - b0[0]) * k, b0[1] + (b1[1] - b0[1]) * k)],
                           fill=lum(fond, 0.5) + (170,), width=max(1, int(3 * q)))
            d.line(inte + inte[:1], fill=melange(mil, acc, 0.55 * on) + (255,), width=max(2, int(1 + 7 * q)), joint="curve")
        d.polygon(anneaux[-1], fill=(0, 0, 0))
        halo(im, cx, cy, 70 + 50 * v, acc, (0.35 + 0.4 * v) * on)
        d.ellipse([cx - 4, cy - 4, cx + 4, cy + 4], fill=melange(acc, BLANC, 0.5))
        return im

    dessine.foyer = (cx, cy)
    return dessine


def sc_facade(pal, rng, info):
    """L'immeuble la nuit : les fenêtres s'allument, et au-dessus du toit, un étage de trop."""
    fond, mil, acc = pal
    base = degrade(melange(fond, mil, 0.75), lum(fond, 1.0))
    halo(base, 440, 96, 150, melange(acc, BLANC, 0.3), 0.5)
    d0 = ImageDraw.Draw(base, "RGBA")
    d0.ellipse([412, 68, 468, 124], fill=melange(acc, BLANC, 0.5))
    for _ in range(40):
        x, y = rng.random() * L, rng.random() * 220
        d0.point((x, y), fill=BLANC + (int(80 + rng.random() * 150),))
    x0, x1, y0, et = 70, 470, 300, 100
    mur = melange(fond, mil, 0.5)
    d0.polygon([(x0 - 6, y0), (x0 + 22, y0 - 46), (x1 - 22, y0 - 46), (x1 + 6, y0)], fill=lum(mur, 0.7))
    for cx in (130, 300, 410):
        d0.rectangle([cx, y0 - 76, cx + 22, y0 - 40], fill=lum(mur, 0.6))
    d0.rectangle([x0, y0, x1, H], fill=mur)
    fen = []
    for e in range(7):
        y = y0 + 14 + e * et
        d0.line([(x0, y - 14), (x1, y - 14)], fill=lum(mur, 1.35), width=3)
        for c in range(4):
            x = x0 + 34 + c * 96
            fen.append((x, y, e, c))
            d0.rounded_rectangle([x - 5, y - 5, x + 49, y + 75], radius=6, fill=lum(mur, 1.3))
        if e in (1, 4):
            d0.line([(x0 + 14, y + 74), (x1 - 14, y + 74)], fill=lum(fond, 0.5), width=4)
            for bx in range(x0 + 16, x1 - 14, 10):
                d0.line([(bx, y + 58), (bx, y + 74)], fill=lum(fond, 0.5), width=1)
    graine = float(rng.random() * 30)

    def dessine(t, p, v):
        im = base.copy()
        d = ImageDraw.Draw(im, "RGBA")
        for x, y, e, c in fen:
            allume = hasard(e, c, math.floor(t / 1.9 + hasard(e, c) * 3), graine) > 0.56
            if allume:
                d.rectangle([x, y, x + 44, y + 70], fill=melange(acc, BLANC, 0.15))
                d.rectangle([x, y, x + 12, y + 70], fill=lum(acc, 0.72))
                d.rectangle([x + 32, y, x + 44, y + 70], fill=lum(acc, 0.72))
                if hasard(e, c, 9) > 0.6:  # quelqu'un passe devant
                    px = x + 10 + 24 * (0.5 + 0.5 * math.sin(t * 0.9 + e + c))
                    d.ellipse([px - 6, y + 26, px + 6, y + 38], fill=lum(fond, 0.6))
                    d.rectangle([px - 8, y + 38, px + 8, y + 70], fill=lum(fond, 0.6))
            else:
                d.rectangle([x, y, x + 44, y + 70], fill=lum(fond, 0.75))
            d.line([(x + 22, y), (x + 22, y + 70)], fill=lum(fond, 0.5), width=2)
            d.line([(x, y + 24), (x + 44, y + 24)], fill=lum(fond, 0.5), width=2)
        # l'étage qui n'existe pas
        on = clignote(t, graine, 0.3, 7)
        a = int((70 + 110 * lisse(p * 1.6)) * (0.5 + 0.5 * on))
        yf = y0 - 46 - et + 4
        d.rectangle([x0 + 22, yf, x1 - 22, y0 - 46], fill=melange(mil, acc, 0.3) + (a // 2,))
        for xx in range(x0 + 22, x1 - 22, 22):
            d.line([(xx, yf), (xx + 12, yf)], fill=acc + (a + 60,), width=3)
        for yy in range(int(yf), y0 - 46, 22):
            d.line([(x0 + 22, yy), (x0 + 22, yy + 12)], fill=acc + (a + 60,), width=3)
            d.line([(x1 - 22, yy), (x1 - 22, yy + 12)], fill=acc + (a + 60,), width=3)
        fx = x0 + 34 + 2 * 96
        halo(im, fx + 22, yf + 50, 90 + 40 * v, acc, 0.5 + 0.4 * v)
        d.rectangle([fx, yf + 16, fx + 44, yf + 84], fill=melange(acc, BLANC, 0.55) + (min(255, a + 110),))
        d.line([(fx + 22, yf + 16), (fx + 22, yf + 84)], fill=lum(fond, 0.5) + (200,), width=2)
        d.text((x0 + 60, yf + 50), info.get("etage") or "7", font=police(40), fill=acc + (min(255, a + 80),), anchor="mm")
        return im

    dessine.foyer = (290, 280)
    return dessine


def sc_porte(pal, rng, info):
    """Au bout du couloir, la porte : la lumière passe dessous, l'ampoule clignote, elle s'entrouvre."""
    fond, mil, acc = pal
    base = degrade(lum(fond, 0.7), lum(fond, 1.1))
    d0 = ImageDraw.Draw(base, "RGBA")
    px0, py0, px1, py1 = 205, 232, 335, 470
    d0.polygon([(0, 0), (L, 0), (px1 + 22, py0 - 30), (px0 - 22, py0 - 30)], fill=lum(fond, 0.8))
    d0.polygon([(0, 0), (px0 - 22, py0 - 30), (px0 - 22, py1), (0, H)], fill=melange(fond, mil, 0.5))
    d0.polygon([(L, 0), (px1 + 22, py0 - 30), (px1 + 22, py1), (L, H)], fill=melange(fond, mil, 0.4))
    d0.polygon([(0, H), (px0 - 22, py1), (px1 + 22, py1), (L, H)], fill=melange(fond, mil, 0.7))
    d0.rectangle([px0 - 22, py0 - 30, px1 + 22, py1], fill=melange(fond, mil, 0.3))
    for k in range(1, 6):  # lames du parquet et plinthes
        xx = (px0 - 22) + (px1 - px0 + 44) * k / 6
        d0.line([(xx, py1), ((k / 6) * L * 1.6 - L * 0.3, H)], fill=lum(fond, 0.6) + (150,), width=2)
    for q in (0.08, 0.2, 0.38, 0.62, 0.92):
        y = py1 + (H - py1) * q
        xa = (px0 - 22) * (1 - q)
        xb = (px1 + 22) + (L - px1 - 22) * q
        d0.line([(xa, y), (xb, y)], fill=lum(fond, 0.6) + (120,), width=1 + int(q * 3))
    for cote, xb in ((0, px0 - 22), (L, px1 + 22)):  # portes latérales
        for q0, q1 in ((0.18, 0.40), (0.55, 0.86)):
            def pt(q, haut):
                x = xb + (cote - xb) * q
                y = (py0 - 30) * (1 - q) + (-60) * q if haut else py1 + (H - py1) * q
                return (x, y + (py1 - py0) * 0.16 * (1 + q * 2) if haut else y)
            d0.polygon([pt(q0, True), pt(q1, True), pt(q1, False), pt(q0, False)], fill=lum(fond, 0.75), outline=lum(mil, 0.9))
    nom = info.get("porte") or "7B"
    ouvre = info.get("suspens", False)
    graine = float(rng.random() * 40)

    def dessine(t, p, v):
        im = base.copy()
        d = ImageDraw.Draw(im, "RGBA")
        on = clignote(t, graine, 0.22, 10)
        # ampoule et cône de lumière
        d.line([(270, 0), (270, 96)], fill=lum(fond, 0.4), width=3)
        d.polygon([(270, 100), (90, 760), (450, 760)], fill=acc + (int(26 * on),))
        halo(im, 270, 106, 120, acc, 0.75 * on)
        d.ellipse([260, 94, 280, 118], fill=melange(acc, BLANC, 0.6 * on))
        # la porte
        d.rectangle([px0, py0, px1, py1], fill=melange(fond, mil, 0.85), outline=lum(mil, 1.5), width=3)
        d.rectangle([px0 + 16, py0 + 70, px1 - 16, py0 + 140], outline=lum(mil, 0.7), width=3)
        d.rectangle([px0 + 16, py0 + 156, px1 - 16, py1 - 16], outline=lum(mil, 0.7), width=3)
        d.text(((px0 + px1) / 2, py0 + 36), nom, font=police(40), fill=melange(acc, BLANC, 0.25 + 0.4 * v), anchor="mm")
        d.ellipse([px1 - 26, py0 + 140, px1 - 12, py0 + 154], fill=acc)
        if ouvre:  # elle s'entrouvre sur le noir
            g = 4 + 34 * lisse(p)
            d.polygon([(px1 - g, py0 + 2), (px1 - 2, py0 + 2), (px1 - 2, py1 - 2), (px1 - g, py1 - 2)], fill=(0, 0, 0))
            d.line([(px1 - g, py0 + 2), (px1 - g, py1 - 2)], fill=melange(acc, BLANC, 0.4), width=2)
        # rai de lumière sous la porte
        f = 0.55 + 0.45 * v + 0.15 * math.sin(t * 5)
        halo(im, 270, py1 + 6, 150 * f + 40, acc, borne(0.5 + 0.4 * f))
        d.rectangle([px0 + 4, py1 - 3, px1 - 4, py1 + 3], fill=melange(acc, BLANC, 0.7))
        d.polygon([(px0 + 4, py1 + 3), (px1 - 4, py1 + 3), (px1 + 150, H), (px0 - 150, H)], fill=acc + (int(34 * f),))
        if on < 1:
            d.rectangle([0, 0, L, H], fill=(0, 0, 0, 90))
        return im

    dessine.foyer = (270, 370)
    return dessine


def sc_plan_archi(pal, rng, info):
    """Le plan d'architecte se trace trait par trait, puis une pièce en trop se met à battre."""
    fond, mil, acc = pal
    base = degrade(melange(fond, mil, 0.9), melange(fond, mil, 0.55))
    d0 = ImageDraw.Draw(base, "RGBA")
    for x in range(0, L, 30):
        d0.line([(x, 0), (x, H)], fill=acc + (22 if x % 150 else 50,), width=1)
    for y in range(0, H, 30):
        d0.line([(0, y), (L, y)], fill=acc + (22 if y % 150 else 50,), width=1)
    murs = [((70, 170), (470, 170)), ((470, 170), (470, 520)), ((470, 520), (70, 520)), ((70, 520), (70, 170)),
            ((70, 330), (240, 330)), ((240, 170), (240, 290)), ((240, 330), (240, 440)), ((240, 480), (240, 520)),
            ((300, 330), (470, 330)), ((300, 170), (300, 330)), ((240, 420), (380, 420)), ((380, 420), (380, 520)),
            ((50, 140), (50, 550)), ((40, 170), (60, 170)), ((40, 520), (60, 520)),
            ((70, 560), (470, 560)), ((70, 550), (70, 570)), ((470, 550), (470, 570))]
    nom = info.get("porte") or "7B"
    etages = int(info.get("etages") or 6)

    def dessine(t, p, v):
        im = base.copy()
        d = ImageDraw.Draw(im, "RGBA")
        av = borne(t / 2.2) * len(murs)
        for i, (a, b) in enumerate(murs):
            k = borne(av - i)
            if k <= 0:
                break
            fin = (a[0] + (b[0] - a[0]) * k, a[1] + (b[1] - a[1]) * k)
            d.line([a, fin], fill=BLANC + (235,), width=5 if i < 12 else 2)
            if 0 < k < 1:
                halo(im, fin[0], fin[1], 26, BLANC, 0.9)
        if av > 6:
            d.arc([240 - 40, 290, 240 + 40, 370], 270, 360, fill=BLANC + (160,), width=2)
            d.arc([240 - 40, 440, 240 + 40, 520], 0, 90, fill=BLANC + (160,), width=2)
        if t > 1.6:  # la pièce en trop
            k = lisse((t - 1.6) / 0.6)
            puls = 0.5 + 0.5 * math.sin(t * 4.2)
            d.rectangle([304, 174, 466, 326], fill=acc + (int(k * (50 + 80 * puls + 60 * v)),))
            for xx in range(304, 466, 20):
                d.line([(xx, 174), (xx + 11, 174)], fill=acc, width=4)
                d.line([(xx, 326), (xx + 11, 326)], fill=acc, width=4)
            for yy in range(174, 326, 20):
                d.line([(304, yy), (304, yy + 11)], fill=acc, width=4)
                d.line([(466, yy), (466, yy + 11)], fill=acc, width=4)
            halo(im, 385, 250, 110, acc, 0.35 * k)
            d.text((385, 250), nom, font=police(int(52 * (0.7 + 0.3 * k))), fill=BLANC, anchor="mm")
        # coupe de l'immeuble : les étages numérotés, et celui du dessus en pointillés
        for e in range(etages):
            y = 880 - e * 34
            if t > 0.25 * e:
                d.rectangle([150, y - 30, 390, y], outline=BLANC + (200,), width=2)
                d.text((128, y - 15), str(e + 1), font=police(20), fill=BLANC + (200,), anchor="mm")
        if t > 0.25 * etages + 0.3:
            y = 880 - etages * 34
            on = clignote(t, 5, 0.3, 8)
            for xx in range(150, 390, 18):
                d.line([(xx, y - 30), (xx + 9, y - 30)], fill=acc + (int(255 * on),), width=3)
            d.text((128, y - 15), str(etages + 1), font=police(22), fill=acc + (int(255 * on),), anchor="mm")
            d.rectangle([150, y - 30, 390, y], fill=acc + (int(60 * on),))
        return im

    dessine.foyer = (385, 250)
    return dessine


def sc_marches(pal, rng, info):
    """On monte l'escalier, les marches défilent et le compteur tourne."""
    fond, mil, acc = pal
    base = degrade(melange(fond, mil, 0.5), lum(fond, 0.8))
    pw, ph_ = 84, 58
    cible = info.get("nombre")
    cadence = 2.4

    def dessine(t, p, v):
        im = base.copy()
        d = ImageDraw.Draw(im, "RGBA")
        f = (t * cadence) % 1.0
        ox, oy = -f * pw, f * ph_
        # lampe murale qui passe
        lx = (360 - t * cadence * pw) % 1100 - 280
        ly = 250 + (360 - lx) * ph_ / pw * 0.0
        on = clignote(t, 2, 0.12)
        halo(im, lx, ly, 210, acc, 0.5 * on)
        d.ellipse([lx - 12, ly - 12, lx + 12, ly + 12], fill=melange(acc, BLANC, 0.5 * on))
        pts = []
        for k in range(-2, 11):
            x, y = k * pw + ox - 40, 800 - k * ph_ + oy
            pts += [(x, y), (x + pw, y)]
        corps = [(pts[0][0], H + 80)] + pts + [(pts[-1][0], H + 80)]
        d.polygon(corps, fill=melange(fond, mil, 0.85))
        for k in range(-2, 11):
            x, y = k * pw + ox - 40, 800 - k * ph_ + oy
            d.rectangle([x, y, x + pw, y + 7], fill=melange(mil, acc, 0.55))
            d.rectangle([x + pw - 5, y - ph_ + 7, x + pw, y], fill=lum(mil, 0.75))
            d.line([(x + pw * 0.5, y), (x + pw * 0.5, y - 210)], fill=lum(fond, 0.5), width=4)  # barreau
        d.line([(-40 + ox - 2 * pw + pw * 0.5, 800 + 2 * ph_ + oy - 210 + ph_ * 0.5 - ph_ * 0.5),
                (-40 + ox + 10 * pw + pw * 0.5, 800 - 10 * ph_ + oy - 210)], fill=lum(mil, 1.6), width=10)
        # le compteur
        if not cible:
            return im
        reste = max(0, int((1 - p) * min(cible - 1, 14)))
        nb = cible - reste
        fini = nb >= cible
        d.rounded_rectangle([150, 162, 390, 342], radius=22, fill=lum(fond, 0.5) + (215,), outline=acc if fini else lum(mil, 1.6), width=4)
        d.text((270, 238), str(nb), font=police(104), fill=acc if fini else BLANC, anchor="mm")
        d.text((270, 312), "MARCHES", font=police(24), fill=lum(mil, 2.4), anchor="mm")
        return im

    dessine.foyer = (270, 300)
    return dessine


# ----------------------------------------------------------------------------- scènes communes
def sc_horloge(pal, rng, info):
    """Une heure précise, en grands chiffres lumineux : la minute bascule sous nos yeux."""
    fond, mil, acc = pal
    base = degrade(lum(fond, 0.7), lum(fond, 0.4))
    hh, mm = info.get("heure") or (2, 14)
    avant = (hh * 60 + mm - 1) % 1440

    def dessine(t, p, v):
        im = base.copy()
        d = ImageDraw.Draw(im, "RGBA")
        bascule = 0.7
        h, m = (hh, mm) if t >= bascule else (avant // 60, avant % 60)
        txt = f"{h:02d}{m:02d}"
        halo(im, 270, 330, 300, acc, 0.22 + 0.12 * v + (0.35 * max(0.0, 1 - (t - bascule) / 0.4) if t >= bascule else 0))
        w, hd, e = 64, 132, 13
        xs = [98, 180, 296, 378]
        eteint = lum(mil, 0.55) + (130,)
        for ch, x in zip(txt, xs):
            dy = 0
            if bascule <= t < bascule + 0.25:
                dy = -18 * (1 - (t - bascule) / 0.25)
            sept_segments(d, x, 264 + dy, w, hd, ch, melange(acc, BLANC, 0.2), eteint, e)
        if (t * 2) % 2 < 1.3:
            for y in (306, 354):
                d.ellipse([263, y - 7, 277, y + 7], fill=acc)
        # la trotteuse : soixante traits qui se remplissent
        sec = int((t * 6) % 60)
        for i in range(60):
            a = i * math.pi / 30
            c = acc if i <= sec else lum(mil, 0.8)
            d.line([(270 + 190 * math.sin(a), 330 - 190 * math.cos(a)), (270 + 204 * math.sin(a), 330 - 204 * math.cos(a))],
                   fill=c, width=4)
        for y in range(int((t * 40) % 6), H, 6):  # lignes de balayage
            d.line([(0, y), (L, y)], fill=(0, 0, 0, 46), width=1)
        return im

    dessine.foyer = (270, 330)
    return dessine


def sc_nombre(pal, rng, info):
    """Un nombre de l'histoire qui s'affiche en grand : il monte, puis claque."""
    fond, mil, acc = pal
    base = degrade(melange(fond, mil, 0.7), lum(fond, 0.7))
    cible = int(info.get("nombre") or 0)
    etiq = info.get("etiquette") or ""
    depart = cible - 40 if 1800 <= cible <= 2200 else 0
    duree = 1.15
    f_n = police(190 if cible < 1000 else 150)

    def dessine(t, p, v):
        im = base.copy()
        d = ImageDraw.Draw(im, "RGBA")
        cx, cy = 270, 312
        for i in range(12):  # rayons qui tournent
            a = i * math.pi / 6 + t * 0.25
            d.polygon([(cx, cy), (cx + 900 * math.cos(a), cy + 900 * math.sin(a)),
                       (cx + 900 * math.cos(a + 0.26), cy + 900 * math.sin(a + 0.26))], fill=mil + (70,))
        halo(im, cx, cy, 300, lum(fond, 0.6), 0.9)
        k = borne(t / duree)
        val = int(depart + (cible - depart) * doux(k))
        arrive = k >= 1
        dx = dy = 0
        if arrive and t - duree < 0.35:
            amp = 12 * (1 - (t - duree) / 0.35)
            dx, dy = amp * math.sin(t * 80), amp * math.cos(t * 67)
            q = (t - duree) / 0.35
            r = 120 + 420 * doux(q)
            d.ellipse([cx - r, cy - r, cx + r, cy + r], outline=acc + (int(220 * (1 - q)),), width=8)
        if arrive:
            halo(im, cx, cy, 250 + 40 * v, acc, 0.28 + 0.2 * v)
        for r in (196, 210):
            d.arc([cx - r, cy - r, cx + r, cy + r], t * 50 * (1 if r == 196 else -1), t * 50 * (1 if r == 196 else -1) + 250,
                  fill=melange(mil, acc, 0.6) + (200,), width=4)
        d.text((cx + dx, cy + dy), str(val), font=f_n, fill=acc if arrive else BLANC, anchor="mm",
               stroke_width=6, stroke_fill=lum(fond, 0.4))
        if etiq:
            d.text((cx, cy + 122), etiq, font=police(32), fill=BLANC + (235,), anchor="mm")
        return im

    dessine.foyer = (270, 312)
    return dessine


# ----------------------------------------------------------------------------- choix des scènes
SCENES = {
    "tunnel": (sc_tunnel, "tunnel rame conduis conduit roule ralenti ralentir vitesse rails ligne metro cabine frein nuit"),
    "radio": (sc_radio, "radio annonce voix frequence gresille controle entend entendu micro parle prochain arret muette"),
    "quai": (sc_quai, "quai station femme uniforme silhouette attend lanterne panneau mur portes descend descendez elle"),
    "rame": (sc_rame, "train passe wagon voiture terminus deraille retard collegue passagers"),
    "plan_ligne": (sc_plan_ligne, "plan carte carnet note archives matricule photo existe projet abandonne"),
    "fenetre": (sc_fenetre, "pluie fenetre vitre dehors matin soir chat virgule seule regarde nuit"),
    "lettre": (sc_lettre, "lettre ecrite ecrit ecriture main manuscrit lire phrase mots stylo ecris"),
    "horloges": (sc_horloges, "temps futur ans heure semaine demain date annee tot tard avant apres mois"),
    "enveloppes": (sc_enveloppes, "enveloppe enveloppes courrier poste boite recu lettres arrive"),
    "cachet": (sc_cachet, "timbre timbrees cachet oblitere bureau datee datees poste"),
    "encre": (sc_encre, "cafe tache encre invisible apparait efface effacer renverse faute"),
    "escalier": (sc_escalier, "escalier cage monte descend palier tourne vide"),
    "facade": (sc_facade, "immeuble etages etage toit appartement septieme loyer fenetre gardienne haussmannien locataire"),
    "porte": (sc_porte, "porte laiton couloir frappe entrouverte cle loge entre entrez derriere sous ouvre"),
    "plan_archi": (sc_plan_archi, "plan plans architecte dessine cadastre syndic construit piece"),
    "marches": (sc_marches, "marches marche compte comptais compter volee"),
    "horloge": (sc_horloge, ""),
    "nombre": (sc_nombre, ""),
}
DECORS = {
    "metro": ["tunnel", "radio", "quai", "plan_ligne", "rame"],
    "lettres": ["lettre", "fenetre", "enveloppes", "horloges", "cachet", "encre"],
    "immeuble": ["facade", "escalier", "porte", "plan_archi", "marches"],
    "mystere": ["tunnel", "fenetre", "escalier", "horloges", "porte", "enveloppes"],
}
PAR_SERIE = {
    "ligne13": {"decor": "metro", "panneau": "Sainte-Blaise", "fantome": "Sainte-Blaise", "heure_defaut": (2, 14),
                "stations": ["La Fourche", "Guy-Môquet", "Pte de St-Ouen", "Garibaldi", "Saint-Denis"]},
    "lettres2043": {"decor": "lettres", "date": "12 mars 2043", "cachet": "Lyon", "annees": (2026, 2043), "chat": True},
    "sept_b": {"decor": "immeuble", "porte": "7B", "etage": "7", "etages": 6},
}
ETIQUETTES = (("euro", "EUROS"), ("marche", "MARCHES"), ("etage", "ÉTAGES"), ("minute", "MINUTES"), ("lettre", "LETTRES"),
              ("an", "ANS"), ("nuit", "NUITS"), ("jour", "JOURS"), ("metre", "MÈTRES"), ("heure", "HEURES"))
RE_HEURE = re.compile(r"\b(\d{1,2}) ?h ?(\d{2})\b")
RE_NOMBRE = re.compile(r"\b(\d{2,4})\b")


def reglages_serie(serie):
    r = dict(PAR_SERIE.get(serie.get("id"), {}))
    r.update(serie.get("animation") or {})  # bible.json peut préciser {"animation": {"decor": "metro", ...}}
    if r.get("decor") not in DECORS:
        r["decor"] = "mystere"
    return r


def phrases(mots):
    """Regroupe les mots minutés [(mot, t0, t1)] en phrases."""
    res, cour = [], []
    for m in mots:
        cour.append(m)
        if m[0].rstrip("»\") ").endswith((".", "!", "?", "…")):
            res.append(cour)
            cour = []
    if cour:
        res.append(cour)
    return res


def decouper_plans(mots, serie, numero, duree_totale, mini=1.9, maxi=5.8):
    """Un plan par phrase : les phrases trop courtes sont regroupées, les trop longues coupées à la virgule.
    Retourne [{t0, t1, scene, info, graine, camera, transition, suspens}] couvrant 0 → duree_totale."""
    if not mots:
        return [{"t0": 0.0, "t1": duree_totale, "scene": DECORS[reglages_serie(serie)["decor"]][0], "info": reglages_serie(serie),
                 "graine": numero, "camera": "avant", "transition": "aucune", "suspens": False}]
    banque = None
    try:  # la série a ses propres images (medias/<serie>/) : le montage se fait avec elles
        import photos
        banque = photos.banque(serie.get("id"))
    except Exception:
        banque = None
    if banque:  # de vraies images : montage plus nerveux, un plan toutes les deux à trois secondes
        mini, maxi = min(mini, 1.5), min(maxi, float(os.environ.get("STUDIO_PLAN_MAXI", "3.4")))
    ph = phrases(mots)
    debut_suspens = ph[-1][0][1]
    blocs = []
    for p in ph:
        if blocs and (blocs[-1][-1][2] - blocs[-1][0][1]) < mini and p is not ph[-1]:
            blocs[-1] = blocs[-1] + p
        else:
            blocs.append(list(p))
    if len(blocs) > 1 and (blocs[-1][-1][2] - blocs[-1][0][1]) < mini and len(ph) > 1 and blocs[-1][0][1] > debut_suspens:
        blocs[-2] = blocs[-2] + blocs.pop()
    coupes = []
    for b in blocs:
        pile = [b]
        while pile:
            x = pile.pop(0)
            if x[-1][2] - x[0][1] <= (4.2 if x[0] is mots[0] else maxi) or len(x) < 6:  # l'accroche : plans courts
                coupes.append(x)
                continue
            milieu = (x[0][1] + x[-1][2]) / 2
            cand = [i for i in range(2, len(x) - 2) if x[i][0].endswith((",", ";", ":"))] or list(range(2, len(x) - 2))
            if banque:  # montage nerveux : on coupe d'abord à la fin d'une phrase, jamais au milieu d'un groupe de mots
                tient = [j for j in range(len(x) - 1) if x[j][2] - x[0][1] >= 0.9 and x[-1][2] - x[j + 1][1] >= 0.9]
                cand = ([j for j in tient if x[j][0].endswith((".", "!", "?", "…", "»"))]
                        or [j for j in tient if x[j][0].endswith((",", ";", ":"))] or cand)
            i = min(cand, key=lambda j: abs(x[j][2] - milieu))
            pile = [x[:i + 1], x[i + 1:]] + pile
    regl = reglages_serie(serie)
    dispo = DECORS[regl["decor"]]
    mots_cles = {n: SCENES[n][1].split() for n in dispo}
    if banque:
        dispo = banque.scenes(numero)
        mots_cles = {n: banque.mots(n) for n in dispo}

    def scores(net, exclues=()):
        """Nombre de mots de la phrase qui évoquent chaque scène (« lettres » compte pour « lettre »)."""
        suite = re.findall(r"[a-z0-9]+", net)
        nies = {suite[k + 2] for k in range(len(suite) - 2) if suite[k] == "pas" and suite[k + 1] in ("de", "d")}
        nies |= {suite[k + 1] for k in range(len(suite) - 1) if suite[k] in ("aucun", "aucune", "ni")}
        mots_p = set(suite) - nies  # « Pas de quai » ne doit pas montrer le quai
        return {n: sum(1 for w in mots_p if any(w == c or (len(c) >= 5 and w.startswith(c)) for c in mots_cles[n]))
                for n in dispo if n not in exclues}

    # la scène du suspens est choisie d'abord (la mieux assortie) : le plan juste avant ne doit pas la prendre
    i_final = next((i for i, b in enumerate(coupes) if b[0][1] >= debut_suspens - 1e-6), len(coupes))
    scene_finale = None
    if 0 < i_final < len(coupes):
        sf = scores(sans_accent(" ".join(m[0] for m in coupes[i_final])))
        if sf and max(sf.values()) > 0:
            scene_finale = max(sf, key=lambda n: (sf[n], -dispo.index(n)))
    dernier = {n: -10 - i for i, n in enumerate(dispo)}  # ordre de la liste = ordre de repli
    base = sum(ord(c) for c in serie.get("id", "x")) * 31 + numero * 7
    cameras = ["avant", "arriere", "droite", "avant", "gauche"]
    transitions = ["flash", "zoom", "glitch", "zoom"]
    plans, precedente, dernier_nombre, vues = [], None, -5, {}
    for i, b in enumerate(coupes):
        texte = " ".join(m[0] for m in b)
        net = sans_accent(texte)
        info = dict(regl)
        info["suspens"] = b[0][1] >= debut_suspens - 1e-6
        scene = None
        if i > 0 and banque:  # avec des photos : l'heure dite appelle le plan qui la montre, pas d'écran dessiné
            mh = RE_HEURE.search(net)
            montre = banque.pour_heure(int(mh.group(1)), int(mh.group(2))) if mh else None
            if montre and montre != precedente:
                scene = montre
        elif i > 0:
            mh = RE_HEURE.search(net)
            if mh and precedente != "horloge" and int(mh.group(1)) < 24 and int(mh.group(2)) < 60:
                scene, info["heure"] = "horloge", (int(mh.group(1)), int(mh.group(2)))
            else:
                nums = [int(x) for x in RE_NOMBRE.findall(RE_HEURE.sub(" ", net))]
                if nums and i - dernier_nombre >= 2:
                    nb = max(nums)
                    info["nombre"] = nb
                    if "marche" in net and "marches" in dispo:
                        scene = "marches"
                    else:
                        scene = "nombre"
                        apres = net.split(str(nb), 1)[1].split()[:3]
                        if net.startswith(str(nb)) and plans:  # « Je compte les marches. 96. » : l'unité est juste avant
                            apres = apres[:1] + sans_accent(plans[-1]["texte"]).split()[-5:]
                        info["etiquette"] = "ANNÉE" if 1800 <= nb <= 2200 else next(
                            (e for cle, e in ETIQUETTES if any(a.startswith(cle) for a in apres)), "")
                    dernier_nombre = i
        if scene is None and i == i_final and scene_finale and scene_finale != precedente:
            scene = scene_finale
        if scene is None and banque and plans and str(precedente).startswith("photo:"):
            # la phrase désigne un détail de l'image en cours : on reste dessus et on serre (« le voyant est éteint »)
            detail = banque.appele(precedente, re.findall(r"[a-z0-9]+", net))
            if detail is not None and detail != plans[-1]["cadrage"]:
                scene = precedente
        if scene is None:
            exclues = {precedente} | ({scene_finale} if i == i_final - 1 else set())
            if i + 1 < len(coupes) and "marches" in dispo:
                suite = sans_accent(" ".join(m[0] for m in coupes[i + 1]))
                if "marche" in suite and RE_NOMBRE.search(suite):
                    exclues.add("marches")
            sc = scores(net, exclues)
            meilleur = max(sc.values()) if sc else 0
            cand = [n for n, v_ in sc.items() if v_ == meilleur] if meilleur > 0 else list(sc)
            if banque and meilleur == 0:  # phrase sans mot-clé : un plan passe-partout plutôt qu'un plan précis
                cand = [n for n in banque.replis() if n in sc] or cand
            scene = min(cand or dispo, key=lambda n: dernier[n])
        if scene == "horloges" and not scores(net).get("horloges"):
            info.pop("annees", None)  # les années ne défilent que si la phrase parle du temps
        if scene in dernier:
            dernier[scene] = i
        precedente = scene
        vues[scene] = vues.get(scene, 0) + 1
        plans.append({"t0": b[0][1], "t1": b[-1][2], "scene": scene, "info": info, "graine": base + i * 13,
                      "serie": serie.get("id"),
                      "cadrage": banque.cadrage(scene, re.findall(r"[a-z0-9]+", net), vues[scene] - 1) if banque else 0,
                      "camera": cameras[(i + numero) % len(cameras)],
                      "transition": "aucune" if i == 0 else transitions[(i + numero) % len(transitions)],
                      "suspens": info["suspens"], "texte": texte})
    plans[0]["t0"] = 0.0
    for a, b in zip(plans, plans[1:]):
        a["t1"] = b["t0"]
    plans[-1]["t1"] = duree_totale
    return plans


def fabriquer(plan, palette):
    """Construit la fonction de dessin d'un plan : dessine(t, p, v) → Image 540×960."""
    rng = np.random.default_rng(int(plan["graine"]))
    if str(plan["scene"]).startswith("photo:"):
        import photos
        try:
            return photos.fabriquer(plan)
        except Exception:  # image absente ou illisible : le décor dessiné qui lui correspond
            b = photos.banque(plan.get("serie"))
            fiche = b.fiches.get(plan["scene"][len("photo:"):], {}) if b else {}
            dessin = fiche.get("dessin")
            if dessin not in SCENES:
                dessin = DECORS[plan["info"].get("decor", "mystere")][0]
            return SCENES[dessin][0](palette, rng, plan["info"])
    return SCENES[plan["scene"]][0](palette, rng, plan["info"])


# ----------------------------------------------------------------------------- finitions d'image
_SEUIL = [0 if v < 96 else min(255, int((v - 96) * 1.35)) for v in range(256)] * 3


def finitions():
    """Prépare le vignettage et le grain ; retourne finir(im, t, noirceur) appliqué à chaque image."""
    yy, xx = np.mgrid[0:H, 0:L].astype("float32")
    v = 1.0 - 0.95 * (((xx / L - 0.5) ** 2) * 1.5 + ((yy / H - 0.5) ** 2) * 1.0)
    vign = Image.fromarray((np.clip(v, 0.2, 1.0) * 255).astype("uint8")).convert("RGB")
    serre = Image.fromarray((np.clip(1.2 - v, 0, 1) * 255).astype("uint8"))
    rng = np.random.default_rng(7)
    noir = Image.new("RGB", (L, H))
    grains = [Image.fromarray((rng.random((H // 2, L // 2, 3)) * 22).astype("uint8")).resize((L, H), Image.NEAREST)
              for _ in range(4)]

    def finir(im, i, noirceur=0.0):
        lueur = im.resize((L // 4, H // 4), Image.BILINEAR).point(_SEUIL).filter(ImageFilter.GaussianBlur(4))
        im = ImageChops.screen(im, lueur.resize((L, H), Image.BILINEAR))
        im = ImageChops.multiply(im, vign)
        if noirceur > 0.02:
            im.paste(noir, (0, 0), serre.point(_lut(noirceur)))
        return ImageChops.add(im, grains[i % 4], 1, -10)

    return finir


def parasite(im, graine):
    """Coupe « glitch » : bandes décalées et couleurs dédoublées, pour une ou deux images."""
    a = np.asarray(im)
    out = a.copy()
    rng = np.random.default_rng(graine)
    k = max(1, round(im.height / H))  # même effet sur une image pleine résolution (plans photographiques)
    for _ in range(7):
        y0 = int(rng.integers(0, H - 60)) * k
        h = int(rng.integers(12, 90)) * k
        out[y0:y0 + h] = np.roll(a[y0:y0 + h], int(rng.integers(-70, 70)) * k, axis=1)
    out[..., 0] = np.roll(out[..., 0], 9 * k, axis=1)
    out[..., 2] = np.roll(out[..., 2], -9 * k, axis=1)
    return Image.fromarray(out)


def cadrer(im, zoom, cx, cy, taille):
    """Caméra : recadre autour de (cx, cy) avec le zoom donné puis agrandit à la taille finale."""
    zoom = max(1.0, zoom)
    w, h = L / zoom, H / zoom
    x0 = borne(cx - w / 2, 0, L - w)
    y0 = borne(cy - h / 2, 0, H - h)
    return im.resize(taille, Image.BILINEAR, box=(x0, y0, x0 + w, y0 + h))
