# Studio TikTok — un épisode par jour, sans clé ni API payante

Le VPS écrit, dit, anime, monte et livre chaque soir un épisode de mini-série (60-90 s, vertical 1080×1920).
Toi, tu publies depuis l'iPhone en deux minutes. Rien ne sort du serveur à part la vidéo envoyée sur Telegram.

## Chaîne de fabrication

| Étape | Outil | Sur le VPS |
|---|---|---|
| Scénario (180-230 mots) | Ollama local, à partir de `bible.json` (3 séries, 12 épisodes chacune, personnages, suspens) | déjà installé |
| Voix | une narratrice (Kokoro `ff_siwis`) et un narrateur (Supertonic 3 `M2`), choisis selon la série, dans leur environnement isolé ; Piper `fr_FR-siwis-medium` en dernier secours | `python3 revenus/tiktok/studio.py voix` (une fois) |
| Image | plans photographiques réalistes mis en mouvement (`photos.py`, images dans `medias/<serie>/`) quand la série en a, sinon décors animés dessinés image par image (`scenes.py`) ; un plan par phrase, caméra qui bouge, sous-titres mot à mot calés sur la voix, titre d'ouverture, carte « La suite demain à 20 h » | `pillow numpy` |
| Nappe sonore | générée (bourdons + souffle), libre de droits | — |
| Montage | ffmpeg H.264 + AAC, 70-90 s, 20-40 Mo (débit plafonné pour rester sous la limite Telegram) | `sudo apt-get install -y ffmpeg` |
| Livraison | Telegram `sendVideo` + légende (titre, accroche, hashtags) à coller | déjà configuré |

Timer : `revenus-tiktok.timer` à 17:30 UTC (18:30 Paris l'hiver) ; la vidéo est sur Telegram vers 18:40, à publier à 20 h.

## Commandes

```
python3 revenus/tiktok/studio.py test        # vérifie ffmpeg / pillow / numpy / voix
python3 revenus/tiktok/studio.py voix        # installe les deux voix (une fois, 5 à 8 minutes, 1 Go de disque)
python3 revenus/tiktok/studio.py apercu      # 25 s de rendu envoyées sur Telegram (les deux voix : Malik, puis l'annonce de la radio)
python3 revenus/tiktok/studio.py episode     # l'épisode suivant, tout de suite
python3 revenus/tiktok/studio.py episode sept_b   # force une série (ligne13 | lettres2043 | sept_b)
python3 revenus/tiktok/studio.py refaire     # refait le dernier épisode envoyé, même texte, sans avancer la série (refaire ligne13 : le dernier de cette série)
python3 revenus/tiktok/studio.py etat        # avancement des séries
```

Réglages `.env` (facultatifs) : `STUDIO_MODELE` (défaut `OLLAMA_MODEL`), `STUDIO_ALLURE` (0.90 = débit de la narratrice, plus grand = plus rapide), `STUDIO_ALLURE_HOMME` (0.86 = débit du narrateur),
`STUDIO_VOIX_HOMME` (`M2` par défaut ; `M5` et `M3` sont aussi graves, `M4` et `M1` plus aiguës), `STUDIO_DIALOGUES=0` (une seule voix par épisode),
`STUDIO_MOTEUR_VOIX=piper` (revenir à l'ancienne voix ;
`STUDIO_VITESSE` 1.06 règle alors son débit, plus grand = plus lent),
`STUDIO_NAPPE` (0.10 = volume de la nappe), `STUDIO_ROTATION=alternance` (une série différente chaque jour au lieu d'une série jusqu'au bout),
`STUDIO_GARDER` (7 vidéos conservées dans `revenus/donnees/tiktok/videos/`), `STUDIO_CRF` / `STUDIO_PRESET` / `STUDIO_DEBIT` (qualité ffmpeg),
`STUDIO_FPS` (24 images par seconde ; 20 allège le calcul sur un petit VPS), `STUDIO_FLASH=0` (coupes sans flash ni parasites),
`STUDIO_PHOTOS=0` (revenir aux décors dessinés pour toutes les séries), `STUDIO_DEFILE=0` (tunnel figé), `STUDIO_VIBRATION=0` (cabine sans vibration),
`STUDIO_PLAN_MAXI` (3.4 = durée maximale d'un plan photographique, en secondes).

## L'animation (ce qui retient le regard)

Tout est calculé sur le VPS, sans clé ni téléchargement au rendu : `scenes.py` dessine chaque image en 540×960, `studio.py` la cadre en 1080×1920.
Les séries qui ont des photographies passent par `photos.py` (voir plus bas), directement en 1080×1920.

- **Un décor par série** : métro (tunnel qui défile, radio de cabine, quai fantôme, rame qui passe, plan de la ligne), lettres (lettre qui s'écrit,
  fenêtre sous la pluie avec le chat, enveloppes qui tombent, horloges, cachet de la poste, tache d'encre), immeuble (façade, cage d'escalier,
  porte du 7B, plan d'architecte, marches comptées).
- **Un plan par phrase** (2 à 6 s) : la scène est choisie d'après les mots de la phrase (« radio » → la radio, « porte » → la porte). Une heure
  (« 2 h 14 ») déclenche l'horloge lumineuse, un nombre (« 640 euros », « 108 marches ») le compteur.
- **Caméra** : elle avance, recule ou glisse à chaque plan ; coupe avec flash doux, à-coup de zoom ou parasites ; petite secousse sur les mots forts.
- **La voix pilote l'image** : l'onde de la radio, les néons, les halos battent avec le volume réel de la voix.
- **Sous-titres** : chaque mot arrive quand il est dit, le mot en cours est surligné ; chaque phrase et chaque virgule sont calées sur la voix
  réelle (écart médian mesuré : 0,05 s).
- **Début et fin** : le titre claque dans les deux premières secondes ; sur la phrase de suspens l'image se resserre et s'assombrit, coupe au noir,
  puis carte « LA SUITE / DEMAIN À 20 H » avec le numéro du prochain épisode.
- Les textes restent dans la zone visible de TikTok (hors boutons de droite et légende du bas).

Pour une nouvelle série dans `bible.json`, ajoute si tu veux `"animation": {"decor": "metro"}` (`metro`, `lettres`, `immeuble` ; sinon un décor
« mystère » mélange les scènes) et, au choix, `panneau`, `fantome`, `stations`, `date`, `cachet`, `annees`, `porte`, `etage`, `etages`.

### Plans photographiques (personnages réalistes)

Quand `medias/<serie>/plans.json` existe, la série est montée avec de vraies images au lieu des décors dessinés. « Le Veilleur de la ligne 13 »
en a onze : Malik en cabine, son visage, le tunnel, la radio, le plan de ligne, le carnet, l'horloge à 02:14, la femme du quai, le poste de
commande, les archives, le quai Sainte-Blaise. Les deux autres séries gardent leurs décors dessinés tant qu'elles n'ont pas d'images.

- **Relief** : chaque image a une carte de profondeur (`<nom>_prof.png`, blanc = proche). Quand la caméra avance ou glisse, le premier plan
  bouge plus que le fond, comme dans une vraie prise de vue, au lieu d'un simple zoom sur une photo.
- **Le tunnel défile** : derrière le pare-brise et les vitres, le tunnel avance vers la caméra (deux copies de la zone lointaine grossissent
  en boucle autour du point de fuite et se relaient ; `defile` dans `plans.json`). La cabine, elle, reste nette et vibre légèrement, avec un
  double à-coup à chaque joint de rail (`roule`). `STUDIO_DEFILE=0` fige le tunnel, `STUDIO_VIBRATION=0` coupe les vibrations.
- **Montage nerveux** : un plan toutes les deux à trois secondes (3,4 s au plus, réglable avec `STUDIO_PLAN_MAXI`), coupé à la fin d'une
  phrase ou à une virgule, jamais au milieu d'un groupe de mots. Environ 34 plans pour un épisode de 85 s.
- **Pas de révélation avant l'heure** : `depuis` réserve une image aux épisodes qui ont le droit de la montrer (les archives à partir de
  l'épisode 2, la femme et le quai à partir de l'épisode 4).
- **Lumière vivante** : les néons vacillent, les voyants respirent, le voyant de la radio suit la voix, les lumières du tunnel passent sur la
  cabine, la poussière flotte sur le quai et aux archives. Vignettage et grain de pellicule sont refaits à chaque image.
- **Choix du plan** : par les mots de la phrase, comme pour les décors (`mots` dans `plans.json`). Une phrase sans mot-clé prend un plan
  passe-partout (`repli`), jamais un plan précis ; « Pas de quai » ne montre pas le quai ; « 2 h 14 » montre l'horloge.
- **Reprises** : une image déjà vue revient cadrée autrement (`cadrages` : visage serré, main sur le levier, voyant de la radio…), et un
  cadrage qui a ses propres mots est pris dès que la phrase les contient (« mes mains » → la main sur le manipulateur). Si la phrase désigne
  un détail de l'image déjà à l'écran, le montage reste dessus et serre.
- **Sécurité** : image absente ou illisible → le décor dessiné indiqué par `dessin` prend sa place, l'épisode sort quand même.
- **Coût en calcul** : environ 0,17 s par image de vidéo, soit 6 minutes pour un épisode de 85 s ; fichier de 20 à 25 Mo.

Ajouter une image : un JPEG 9:16 d'au moins 1080 px de large dans `medias/<serie>/`, une fiche dans `plans.json` (`nom`, `fichier`, `mots`,
`cadrages`, `effets` parmi `neons`, `voyants`, `voix`, `passage`, `poussiere`, `roule`, et `dessin` ; en option `defile` et `depuis`). La carte de profondeur est facultative : sans
elle l'image reste plane mais garde caméra, lumières et grain. Celles de la ligne 13 ont été calculées une fois, hors VPS, avec le modèle
Depth Anything V2 Small (https://huggingface.co/onnx-community/depth-anything-v2-small).

Limite à connaître : ces plans restent des photographies animées, pas des vidéos tournées. Les personnages ne clignent pas des yeux et ne
bougent pas les lèvres. L'étape suivante, si tu la veux, est de remplacer certains plans par de courts clips vidéo générés à partir des
mêmes images.

## La voix (ce qui fait rester)

`voix.py` fait parler deux voix naturelles, calculées sur le VPS, sans clé :

| Qui | Moteur | Séries |
|---|---|---|
| la narratrice | Kokoro, voix `ff_siwis` (modèle Apache 2.0, 354 Mo) | Lettres de 2043 (Claire), 7B (Nour) |
| le narrateur | Supertonic 3, voix `M2` (code MIT, modèle OpenRAIL-M, 400 Mo) | Le Veilleur de la ligne 13 (Malik) |

Le choix se fait dans `bible.json`, série par série : `"voix": "homme"` ou `"femme"`. Une nouvelle série sans cette ligne est dite par la narratrice.

- **Chacun sa voix** : quand le texte dit clairement qui parle, la parole rapportée change de voix. « Une voix de femme annonce : Prochain arrêt,
  Sainte-Blaise » : Malik dit le début, une femme dit l'annonce. Les prénoms listés dans `voix_personnages` comptent aussi (« Josiane sourit : … »).
  `voix_radio` fixe la voix des annonces radio de la série. Dans le doute, et chaque fois que le narrateur rapporte ses propres mots
  (« je lui demande : … »), la voix ne change pas.
- **Une phrase = une prise** : la voix est synthétisée phrase par phrase, puis montée. Le début et la fin de chaque phrase sont donc connus
  exactement, et les sous-titres n'ont plus rien à deviner.
- **Un rythme de conteur** : accroche plus franche, silence après l'accroche, phrases courtes posées, long silence puis diction ralentie sur la
  phrase de suspens. Les silences suivent la ponctuation (point, point d'interrogation, points de suspension) et ne sont jamais identiques.
- **Les paroles de la radio** (« Prochain arrêt, Sainte-Blaise ») sortent d'un haut-parleur de cabine : bande étroite, légère saturation, souffle,
  ouverture et relâchement de la fréquence. Vaut pour toute parole annoncée par radio, téléphone, interphone ou répondeur.
- **Ce qui est dit n'est pas ce qui est écrit** : « 2 h 14 » est prononcé « deux heures quatorze », « 20 km/h » « vingt kilomètres heure »,
  « 7B » « sept B » ; les sous-titres gardent l'écriture d'origine. Le narrateur reçoit en plus ses nombres en toutes lettres, parce que son moteur lit mal les chiffres,
  et dans une écriture « à l'oreille » : écrits comme dans le dictionnaire, 71, 78 ou 98 sortaient en deux nombres (« soixante… et onze »,
  « quatre-vingt… dix-huit »). Il reçoit donc « soissantéonze », « soissante-dizuit », « quatre-vingt-dizuit », « siz ans », « sept bé ».
  Une hésitation au milieu d'un nombre long est retirée du son (`STUDIO_RESSERRER=0` pour l'entendre telle quelle) ; les pauses des virgules restent.
  Le sous-titre d'un nombre reste affiché le temps qu'il soit dit en entier.
- **Un son fini** : coupe-bas, un peu de chaleur et d'air (réglés plus bas pour la voix d'homme), compression douce, limiteur sans écrêtage,
  niveau constant (environ −16,5 LUFS). Les deux voix sont ramenées à la même qualité (44,1 kHz) avant le montage.

Les deux moteurs ont besoin d'un numpy récent : ils sont installés à part dans `revenus/donnees/tiktok/venv_voix`, sans toucher aux paquets
Python du serveur (le bot de trading n'est pas concerné). Les modèles sont téléchargés une fois, à une version figée, et refusés si leur
empreinte diffère. Si une voix manque, l'autre la remplace ; si aucune ne répond, le studio retombe tout seul sur Piper. Dans les deux cas,
c'est écrit dans `studio.log`. Calcul : environ 40 s pour un épisode de 85 s.

Licence de la voix d'homme (OpenRAIL-M) : usage commercial permis, à deux conditions qui rejoignent la règle de TikTok. Le contenu doit être
signalé comme généré par une machine (case « Contenu généré par IA », voir la routine ci-dessous) et la voix ne doit pas servir à se faire
passer pour une personne réelle.

## Routine iPhone (2 minutes, à 20 h)

1. Telegram → la vidéo du jour → partager → Enregistrer la vidéo.
2. TikTok → + → importer la vidéo → Suivant.
3. Coller la légende (le bot l'envoie en message séparé : appui long → Copier).
4. Activer « Contenu généré par IA » (la voix est synthétique, les images de la ligne 13 aussi) → Publier.
5. Répondre aux premiers commentaires dans l'heure : ça pèse dans la distribution.

## Ce que TikTok exige pour payer (France)

- Programme Récompenses Créateurs : 18 ans, compte personnel, 10 000 abonnés, 100 000 vues sur 30 jours, vidéos de plus d'une minute, contenu original.
- TikTok exclut explicitement des récompenses les vidéos « uniquement des superpositions de texte » et « une ou plusieurs photos » : d'où les décors animés, la voix et les sous-titres synchronisés, jamais un diaporama.
  Les plans photographiques sont en mouvement permanent (relief, caméra, lumières), mais ils partent d'images fixes : c'est le point à surveiller, et la raison pour laquelle de vrais clips vidéo restent l'étape suivante.
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
## Si un épisode sort avec la mauvaise voix ou sans les images

Le timer fabrique l'épisode avec le code présent sur le serveur à 17:30 UTC. Si le serveur n'a pas reçu la dernière version,
l'épisode sort avec les anciens décors dessinés ; si la voix d'homme n'a pas été installée (`studio.py voix`), une voix de femme la remplace.
Quand cela arrive avec une version à jour, le bot le dit dans un message Telegram « à corriger avant de publier », juste après la vidéo.

Remettre le serveur d'aplomb et refaire l'épisode, sans en sauter un :

```
cd ~/agent-ia && curl -sL https://github.com/2v5smkg85n-debug/agent-ia/archive/refs/heads/main.tar.gz | tar xz --strip-components=1 agent-ia-main/revenus/tiktok agent-ia-main/tests/test_revenus.py && python3 revenus/tiktok/studio.py voix && python3 revenus/tiktok/studio.py test && python3 revenus/tiktok/studio.py refaire
```

Sur le serveur, le studio se met à jour par cette archive et non par `git pull` : le dossier `~/agent-ia` contient le bot de trading avec des fichiers
modifiés sur place, que git refuserait de fusionner. La ligne ci-dessus ne remplace que `revenus/tiktok` et `tests/test_revenus.py` ; elle ne touche
ni au bot, ni à `revenus/donnees` (état des séries, voix installées, vidéos).

`test` doit afficher `OK voix du narrateur (Supertonic)` et `OK plans photographiques de « Le Veilleur de la ligne 13 » : 11 images`.

Si Ollama est indisponible, l'épisode du jour est un « texte de secours » court (accroche + étapes + suspens), signalé dans la légende : à republier plus tard si tu veux la version longue.
