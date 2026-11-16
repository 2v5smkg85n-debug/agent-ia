# Studio TikTok — un épisode par jour, sans clé ni API payante

Le VPS écrit, dit, anime, monte et livre chaque soir un épisode de mini-série (60-90 s, vertical 1080×1920).
Toi, tu publies depuis l'iPhone en deux minutes. Rien ne sort du serveur à part la vidéo envoyée sur Telegram.

## Chaîne de fabrication

| Étape | Outil | Sur le VPS |
|---|---|---|
| Scénario (180-230 mots) | Ollama local, à partir de `bible.json` (3 séries, 12 épisodes chacune, personnages, suspens) | déjà installé |
| Voix | Piper TTS, voix `fr_FR-siwis-medium` (fichier téléchargé une fois, 63 Mo) | `pip3 install --user piper-tts` |
| Image | décors animés dessinés image par image (`scenes.py`), un plan par phrase, caméra qui bouge, sous-titres mot à mot calés sur la voix, titre d'ouverture, carte « La suite demain à 20 h » | `pillow numpy` |
| Nappe sonore | générée (bourdons + souffle), libre de droits | — |
| Montage | ffmpeg H.264 + AAC, 70-90 s, 20-40 Mo (débit plafonné pour rester sous la limite Telegram) | `sudo apt-get install -y ffmpeg` |
| Livraison | Telegram `sendVideo` + légende (titre, accroche, hashtags) à coller | déjà configuré |

Timer : `revenus-tiktok.timer` à 17:30 UTC (18:30 Paris l'hiver) ; la vidéo est sur Telegram vers 18:40, à publier à 20 h.

## Commandes

```
python3 revenus/tiktok/studio.py test        # vérifie ffmpeg / pillow / numpy / piper / voix
python3 revenus/tiktok/studio.py voix        # télécharge la voix (une fois)
python3 revenus/tiktok/studio.py apercu      # 20 s de rendu envoyées sur Telegram
python3 revenus/tiktok/studio.py episode     # l'épisode suivant, tout de suite
python3 revenus/tiktok/studio.py episode sept_b   # force une série (ligne13 | lettres2043 | sept_b)
python3 revenus/tiktok/studio.py etat        # avancement des séries
```

Réglages `.env` (facultatifs) : `STUDIO_MODELE` (défaut `OLLAMA_MODEL`), `STUDIO_VITESSE` (1.06 = débit de la voix, plus grand = plus lent),
`STUDIO_NAPPE` (0.10 = volume de la nappe), `STUDIO_ROTATION=alternance` (une série différente chaque jour au lieu d'une série jusqu'au bout),
`STUDIO_GARDER` (7 vidéos conservées dans `revenus/donnees/tiktok/videos/`), `STUDIO_CRF` / `STUDIO_PRESET` / `STUDIO_DEBIT` (qualité ffmpeg),
`STUDIO_FPS` (24 images par seconde ; 20 allège le calcul sur un petit VPS), `STUDIO_FLASH=0` (coupes sans flash ni parasites).

## L'animation (ce qui retient le regard)

Tout est calculé sur le VPS, sans image externe ni clé : `scenes.py` dessine chaque image en 540×960, `studio.py` la cadre en 1080×1920.

- **Un décor par série** : métro (tunnel qui défile, radio de cabine, quai fantôme, rame qui passe, plan de la ligne), lettres (lettre qui s'écrit,
  fenêtre sous la pluie avec le chat, enveloppes qui tombent, horloges, cachet de la poste, tache d'encre), immeuble (façade, cage d'escalier,
  porte du 7B, plan d'architecte, marches comptées).
- **Un plan par phrase** (2 à 6 s) : la scène est choisie d'après les mots de la phrase (« radio » → la radio, « porte » → la porte). Une heure
  (« 2 h 14 ») déclenche l'horloge lumineuse, un nombre (« 640 euros », « 108 marches ») le compteur.
- **Caméra** : elle avance, recule ou glisse à chaque plan ; coupe avec flash doux, à-coup de zoom ou parasites ; petite secousse sur les mots forts.
- **La voix pilote l'image** : l'onde de la radio, les néons, les halos battent avec le volume réel de la voix.
- **Sous-titres** : chaque mot arrive quand il est dit, le mot en cours est surligné ; les phrases sont recalées sur les silences réels de Piper.
- **Début et fin** : le titre claque dans les deux premières secondes ; sur la phrase de suspens l'image se resserre et s'assombrit, coupe au noir,
  puis carte « LA SUITE / DEMAIN À 20 H » avec le numéro du prochain épisode.
- Les textes restent dans la zone visible de TikTok (hors boutons de droite et légende du bas).

Pour une nouvelle série dans `bible.json`, ajoute si tu veux `"animation": {"decor": "metro"}` (`metro`, `lettres`, `immeuble` ; sinon un décor
« mystère » mélange les scènes) et, au choix, `panneau`, `fantome`, `stations`, `date`, `cachet`, `annees`, `porte`, `etage`, `etages`.

## Routine iPhone (2 minutes, à 20 h)

1. Telegram → la vidéo du jour → partager → Enregistrer la vidéo.
2. TikTok → + → importer la vidéo → Suivant.
3. Coller la légende (le bot l'envoie en message séparé : appui long → Copier).
4. Activer « Contenu généré par IA » (la voix est synthétique) → Publier.
5. Répondre aux premiers commentaires dans l'heure : ça pèse dans la distribution.

## Ce que TikTok exige pour payer (France)

- Programme Récompenses Créateurs : 18 ans, compte personnel, 10 000 abonnés, 100 000 vues sur 30 jours, vidéos de plus d'une minute, contenu original.
- TikTok exclut explicitement des récompenses les vidéos « uniquement des superpositions de texte » et « une ou plusieurs photos » : d'où les décors animés, la voix et les sous-titres synchronisés, jamais un diaporama.
- Une vue compte à partir de 5 secondes ; une vidéo doit atteindre 1 000 vues « Pour toi » pour être prise en compte.
- Sources : https://support.tiktok.com/pl/business-and-creator/creator-rewards-program/creator-rewards-program ,
  https://newsroom.tiktok.com/introducing-the-new-creator-rewards-program/?lang=en

## Pourquoi le bot ne publie pas lui-même

L'API « Content Posting » de TikTok met les vidéos en **privé** tant que l'application n'est pas auditée par TikTok (et limite à 5 comptes) :
https://developers.tiktok.com/docs/en/content-sharing-guidelines/ . Il faut créer une app développeur, passer l'audit, puis autoriser le compte.
Possible plus tard si tu le veux ; d'ici là, le bouton « Publier », c'est toi.

## Ajouter ou corriger des histoires

`bible.json` : chaque série a `titre`, `palette` (3 couleurs), `ambiance`, `narrateur`, `univers`, `hashtags`, `episodes` (liste de `accroche`, `beats`, `suspens`).
Quand les 12 épisodes d'une série sont épuisés, Ollama écrit une saison suivante dans `revenus/donnees/tiktok/saisons.json` (2 épisodes avant la fin, puis à la demande).
Si Ollama est indisponible, l'épisode du jour est un « texte de secours » court (accroche + étapes + suspens), signalé dans la légende : à republier plus tard si tu veux la version longue.
