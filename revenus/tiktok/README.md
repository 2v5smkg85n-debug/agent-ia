# Studio TikTok — un épisode par jour, sans clé ni API payante

Le VPS écrit, dit, anime, monte et livre chaque soir un épisode de mini-série (60-90 s, vertical 1080×1920).
Toi, tu publies depuis l'iPhone en deux minutes. Rien ne sort du serveur à part la vidéo envoyée sur Telegram.

## Chaîne de fabrication

| Étape | Outil | Sur le VPS |
|---|---|---|
| Scénario (180-230 mots) | Ollama local, à partir de `bible.json` (3 séries, 12 épisodes chacune, personnages, suspens) | déjà installé |
| Voix | Piper TTS, voix `fr_FR-siwis-medium` (fichier téléchargé une fois, 63 Mo) | `pip3 install --user piper-tts` |
| Image | fond animé procédural par série (palette, brume, braises), sous-titres mot à mot, en-tête, barre de progression, carte « La suite demain à 20 h » | `pillow numpy` |
| Nappe sonore | générée (bourdons + souffle), libre de droits | — |
| Montage | ffmpeg H.264 + AAC, ~70 s, 5-15 Mo | `sudo apt-get install -y ffmpeg` |
| Livraison | Telegram `sendVideo` + légende (titre, accroche, hashtags) à coller | déjà configuré |

Timer : `revenus-tiktok.timer` à 17:30 UTC (18:30 Paris l'hiver) ; la vidéo est sur Telegram vers 18:40, à publier à 20 h.

## Commandes

```
python3 revenus/tiktok/studio.py test        # vérifie ffmpeg / pillow / numpy / piper / voix
python3 revenus/tiktok/studio.py voix        # télécharge la voix (une fois)
python3 revenus/tiktok/studio.py apercu      # 10 s de rendu envoyées sur Telegram
python3 revenus/tiktok/studio.py episode     # l'épisode suivant, tout de suite
python3 revenus/tiktok/studio.py episode sept_b   # force une série (ligne13 | lettres2043 | sept_b)
python3 revenus/tiktok/studio.py etat        # avancement des séries
```

Réglages `.env` (facultatifs) : `STUDIO_MODELE` (défaut `OLLAMA_MODEL`), `STUDIO_VITESSE` (1.06 = débit de la voix, plus grand = plus lent),
`STUDIO_NAPPE` (0.10 = volume de la nappe), `STUDIO_ROTATION=alternance` (une série différente chaque jour au lieu d'une série jusqu'au bout),
`STUDIO_GARDER` (7 vidéos conservées dans `revenus/donnees/tiktok/videos/`), `STUDIO_CRF` / `STUDIO_PRESET` (qualité ffmpeg).

## Routine iPhone (2 minutes, à 20 h)

1. Telegram → la vidéo du jour → partager → Enregistrer la vidéo.
2. TikTok → + → importer la vidéo → Suivant.
3. Coller la légende (le bot l'envoie en message séparé : appui long → Copier).
4. Activer « Contenu généré par IA » (la voix est synthétique) → Publier.
5. Répondre aux premiers commentaires dans l'heure : ça pèse dans la distribution.

## Ce que TikTok exige pour payer (France)

- Programme Récompenses Créateurs : 18 ans, compte personnel, 10 000 abonnés, 100 000 vues sur 30 jours, vidéos de plus d'une minute, contenu original.
- TikTok exclut explicitement des récompenses les vidéos « uniquement des superpositions de texte » et « une ou plusieurs photos » : d'où le fond animé, la voix et les sous-titres synchronisés, jamais un diaporama.
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
