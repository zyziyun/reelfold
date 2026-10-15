<p align="center">
  <a href="README.md">English</a> · <a href="README.zh-CN.md">简体中文</a> · <b>Français</b> · <a href="README.es.md">Español</a>
</p>

<p align="center">
  <picture>
    <source media="(prefers-color-scheme: dark)" srcset="docs/brand/wordmark-on-dark.svg">
    <img alt="Reelfold" src="docs/brand/wordmark-on-light.svg" width="340">
  </picture>
</p>

<p align="center"><b>L’atelier open source des créateurs.</b><br>
Une phrase transforme vos rushes en une série de vidéos prêtes à publier pour chaque plateforme, en anglais et en
chinois. Open source, gratuit, et tout sur votre Mac.</p>

<p align="center">
  <a href="https://reelfold.com/fr/demo/">Voir la démo</a> ·
  <a href="https://reelfold.com/docs/fr/">Documentation</a> ·
  <a href="https://github.com/zyziyun/reelfold/releases/latest">Télécharger pour macOS</a> ·
  <a href="https://reelfold.com/fr/">reelfold.com</a> ·
  <a href="docs/PRESS_KIT.md">Kit média</a> ·
  <a href="LICENSE">MIT</a>
</p>

- **Toute une série en une phrase.** Indiquez un dossier ou une carte SD et demandez « une douzaine de vidéos, chacune
  avec son thème ». Il regroupe les rushes en histoires, prévoit la série demandée (de 10 à 20 vidéos, par exemple)
  et la réalise en pilote automatique. Des centaines de montages d’un coup ; chaque décision est notée avec sa raison.
- **À chaque plateforme son montage et sa langue.** YouTube, TikTok, Instagram, X et LinkedIn d’abord, puis
  Xiaohongshu, Douyin, Bilibili et WeChat Channels : 20 plateformes, chacune avec sa taille, sa durée (une version
  longue avec chapitres pour YouTube, des versions courtes pour Shorts et TikTok), ses sous-titres, son volume, sa
  couverture et son texte. L’anglais pour YouTube et TikTok, le chinois pour Xiaohongshu et Bilibili.
- **Vos vrais rushes, montés avec soin.** Un modèle par type de vidéo, des coupes sur le temps (Beat This!), la
  détection des plans, un étalonnage plan par plan, des jump cuts lissés et des ralentis nets (RIFE), un recadrage
  vertical qui suit le sujet, et une bibliothèque intégrée de 52 musiques CC0. La génération IA ne comble que les
  manques, après votre accord sur le prix.
- **Couvertures et contrôles.** Les couvertures choisissent une image nette, détourent le sujet, l’agrandissent et
  gardent le titre loin des visages et des boutons, avec trois options A/B pour YouTube. Chaque fichier est vérifié
  (scintillement, cadrage, volume, langue des sous-titres, texte à l’écran) ; vous ne regardez que ce qui est signalé.
- **Reprendre, d’où qu’elle vienne.** Importez une vidéo finie pour la retravailler, gardez vos retouches quand l’IA
  refait le rendu, enregistrez-vous avec le prompteur, ajoutez votre filigrane, et envoyez un clip vers Premiere Pro,
  DaVinci Resolve, CapCut ou OpenTimelineIO.
- **Publier depuis un calendrier.** YouTube est mis en ligne et programmé par son API officielle (Data API) ; pour les
  autres plateformes, Reelfold remplit la page de mise en ligne et c’est vous qui publiez.
- **Local, privé, gratuit, votre IA.** Le rendu, la transcription et les voix gratuites (Kokoro en anglais, Qwen3-TTS
  en chinois) tournent sur votre Mac. Claude Code, Codex, des agents de code ACP (Gemini CLI, Qwen Code, Kimi CLI…),
  des clés d’API, y compris de fournisseurs disponibles en Chine continentale, ou un modèle local ; l’IA et le modèle
  se choisissent par demande, ou avec `/model` dans la discussion. Licence MIT.

![Face caméra · extraits de cours · récit photo · vlog rythmé · podcast masqué · vidéo explicative](docs/demos/strip.jpg)

## Installation

**Application Mac** (Apple Silicon, gratuite) : signée et notarisée, sur
[Releases](https://github.com/zyziyun/reelfold/releases/latest), ou
[compilée depuis les sources](https://reelfold.com/docs/fr/start/install-mac/). En pilote automatique, une phrase
suffit pour aller jusqu’aux clips finis, chaque choix étant noté ; Windows est en préversion.

**Skill Claude Code** (le même moteur, toujours nommé `video-studio`) :

```bash
git clone https://github.com/zyziyun/reelfold ~/.claude/skills/video-studio
~/.claude/skills/video-studio/install.sh
cp ~/.claude/skills/video-studio/persona.example.yaml ~/.claude/skills/video-studio/persona.local.yaml
```

L'IA tourne avec ce que vous avez déjà : votre connexion Claude Code ou Codex, un autre agent de code ACP, votre propre
clé d'API, ou un modèle local.

**Documentation → [reelfold.com/docs/fr](https://reelfold.com/docs/fr/)**

## Dites-le comme ça

| Vous voulez | Dites par exemple |
|---|---|
| Plusieurs vidéos d’une carte | « Fais plusieurs vidéos avec ma carte DJI, chacune avec son thème, pour YouTube et Instagram » |
| Reprendre une vidéo finie | « Voici la vidéo de la semaine dernière : resserre le début, nouvelle couverture, et une version verticale pour TikTok » |
| Un face caméra bien serré | « Retire les pauses, les tics de langage et les répétitions, accélère à 1,1×, ajoute des sous-titres et une barre de progression, exporte pour TikTok et Shorts » |
| Un cours en extraits verticaux | « Découpe ce cours de 70 minutes en 3 épisodes verticaux, une idée par épisode, zoome sur le code, avec couvertures et textes de publication » |
| Un extrait de podcast | « Trouve la meilleure minute de ce podcast Zoom, masque le visage et le nom de l'invité, en vertical » |
| Un vlog de voyage rythmé | « Fais un vlog rapide, calé sur le rythme, avec ces photos et vidéos de Disneyland : jours, lieux, effets sonores, 9:16 » |
| Une vidéo, plusieurs plateformes | « Exporte-la pour Instagram Reels, TikTok et YouTube Shorts, chacune avec ses zones de sécurité et son volume » |

Plus d'exemples : [exemples de demandes](https://reelfold.com/docs/fr/examples/).

## En savoir plus

[Premiers pas](https://reelfold.com/docs/fr/start/what-is-reelfold/) ·
[Guides](https://reelfold.com/docs/fr/guides/talking-head/) ·
[Concepts](https://reelfold.com/docs/fr/concepts/projects/) ·
[Référence](https://reelfold.com/docs/fr/reference/) ·
[Dépannage](https://reelfold.com/docs/fr/help/troubleshooting/) ·
[Contribuer](https://reelfold.com/docs/fr/contributing/)

## Licence

MIT, y compris l'application (`apps/desk`), le site (`apps/site`) et la documentation (`apps/docs`). Les polices et les
modèles sont téléchargés à l'installation sous leurs propres licences (SIL OFL 1.1, Apache-2.0). Les workflows
HTML-vers-vidéo reposent sur [HyperFrames](https://hyperframes.heygen.com).

Anciennement **video-studio** (le skill et le moteur) et **Daycut** (l'application). Les installations existantes dans
`~/.claude/skills/video-studio` continuent de fonctionner ; pointez-les vers la nouvelle adresse avec
`git -C ~/.claude/skills/video-studio remote set-url origin https://github.com/zyziyun/reelfold`.
