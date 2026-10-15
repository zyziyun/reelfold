---
title: FAQ
description: Réponses sur le prix et la licence de Reelfold, Windows, ce qui quitte votre Mac, l’IA nécessaire, les langues, les polices, la publication et l’usage pro.
---

## Reelfold est-il gratuit ?

Oui. Reelfold est open source sous licence MIT : le moteur, le skill Claude Code, l’app Mac et le site web. Vous ne payez que votre fournisseur d’IA, si vous utilisez une API payante. Avec un modèle local, ou avec votre Claude Code ou Codex CLI déjà connecté, il n’y a aucune facture d’API. Lors d’un test interne, 96 fichiers tirés d’un cours de 72 minutes ont coûté 0,73 $ en appels d’API.

## Existe-t-il une version à télécharger pour Mac ? Et pour Windows ?

Oui. L’app Mac (Apple Silicon) est sur [GitHub Releases](https://github.com/zyziyun/reelfold/releases/latest), signée et notarisée : voir [Installer l’app Mac](/docs/fr/start/install-mac/). Une édition Mac App Store (Reelfold Lite) utilise des clés d’API ou des modèles locaux pour l’IA. Windows 10 / 11 (x64) est en préversion : chaque version inclut aussi un installateur Windows non signé (SmartScreen affiche un avertissement), ou compilez depuis les sources ; voir [Install on Windows](/docs/start/install-windows/). Les différences : [Éditions](/docs/fr/help/editions/). Le moteur y utilise faster-whisper et l’encodeur `h264_mf` ; l’essentiel des tests se fait encore sur Mac.

## Est-ce qu’il publie à ma place ?

Seulement si vous le lui demandez. YouTube passe par son API officielle (Data API) : vous vous connectez avec Google dans votre propre navigateur, et Publier ou Programmer met en ligne la vidéo, la couverture et le texte (une publication programmée part en privé et YouTube la publie à l’heure prévue). Pour les autres plateformes, la publication est assistée : l’app ouvre la page de mise en ligne dans son navigateur intégré, y place la vidéo et saisit le titre, le texte et les hashtags ; vous vérifiez, puis vous cliquez vous-même sur publier. Les vidéos programmées ne partent seules que si vous activez « Publier automatiquement les vidéos programmées ». Voir [Publication](/docs/fr/concepts/publishing/).

## Qu’est-ce qui quitte mon Mac ?

Votre vidéo et votre audio restent sur votre Mac : la transcription et le rendu tournent en local. Seul ce dont une étape d’IA a besoin part chez le fournisseur que vous avez choisi : du texte, comme la transcription, les sous-titres et les titres, et pour certaines étapes des planches d’images fixes. La transcription hébergée reçoit l’audio et la narration hébergée reçoit le script. Pour un traitement IA local, utilisez des modèles locaux pour toutes les tâches et leurs secours, la transcription et les voix locales, sans génération hébergée. Les téléchargements, mises à jour et publications sont des opérations réseau distinctes. Voir [Confidentialité](/docs/fr/concepts/privacy/).

## De quelle IA ai-je besoin ?

De l’une de celles-ci, tâche par tâche :

- Votre **Claude Code** ou **Codex** CLI déjà connecté (sans clé d’API).
- Un autre **agent de code** installé et connecté, piloté via ACP : Gemini CLI, Cursor CLI, GitHub Copilot CLI, OpenCode, Qwen Code, Kimi CLI, CodeBuddy, iFlow CLI.
- Une **clé d’API** : Anthropic, OpenAI, DeepSeek, Qwen, Kimi, GLM, Doubao, OpenRouter, Gemini, ElevenLabs. Les clés Qwen, Kimi, GLM et Doubao utilisent leur point d’accès Chine continentale ou international.
- Un **modèle local** : Ollama, LM Studio, vLLM, llama.cpp, whisper en local.

Sans aucune IA, la planification des segments se rabat sur un planificateur à base de règles. Voir [Fournisseurs d’IA](/docs/fr/concepts/ai-providers/).

## Ai-je besoin de Claude Code ?

Pas pour l’app Mac : n’importe quel fournisseur ci-dessus convient. La version skill de Reelfold tourne dans Claude Code, donc pour celle-là, oui. Les recettes de vidéos explicatives et de cours ont besoin d’un modèle d’IA pour dessiner leurs scènes animées : Claude Code, Codex, une clé d’API ou un modèle local conviennent.

## Qu’est-ce qui le distingue d’Opus Clip, Descript ou CapCut ?

Ce sont de bons outils, avec une autre vocation. Opus Clip est un service en ligne qui repère des extraits dans les vidéos longues, Descript est un éditeur basé sur la transcription, et CapCut est un éditeur à timeline avec des modèles. Reelfold est conçu pour celles et ceux qui montent en série :

- **Local d’abord.** Vos rushes sont traités sur votre propre Mac.
- **Lancer le lot, puis relire les exceptions.** Plusieurs clips tournent en parallèle, chaque fichier est contrôlé automatiquement, et vous ne regardez que ce qui a été signalé.
- **Un enregistrement, toutes les plateformes.** Format, sous-titres, volume sonore, couverture et texte adaptés à chacune des 20 plateformes.
- **Votre propre IA**, ou aucune.
- **Open source** (MIT) : vous pouvez lire le code, le modifier et l’étendre.
- **L’anglais et le chinois depuis une même source.** Les versions YouTube et TikTok en anglais, Xiaohongshu et Bilibili en chinois.
- **Compatible avec votre logiciel de montage.** Chaque clip s’exporte vers Premiere Pro, DaVinci Resolve, CapCut ou OpenTimelineIO.
- **Une publication que vous gardez en main :** YouTube par son API officielle, les pages de mise en ligne remplies pour les autres, rien ne part sans votre clic sur Publier ou Programmer.

## Quelles langues sont prises en charge ?

L’app est disponible en anglais, en chinois simplifié et en français. Pour le contenu, le chinois et l’anglais sont les plus aboutis : détection des hésitations, règles de sous-titrage, sous-titres bilingues et textes de publication dans les deux langues. Whisper transcrit de nombreuses autres langues, dont le français, mais ces parcours sont moins testés.

## Puis-je utiliser mes propres polices et couleurs de marque ?

Oui. Dans `persona.local.yaml`, faites pointer n’importe quel rôle de police (`cjk`, `cjk-bold`, `serif`, `mono`…) vers votre propre fichier, et définissez vos couleurs de marque, le thème des panneaux, vos hashtags par défaut et vos règles de titres. Les studios peuvent garder une identité distincte par client. Voir [Thèmes](/docs/fr/concepts/themes/) et la [référence persona](/docs/fr/reference/persona/).

## Puis-je l’utiliser pour un usage commercial ?

La licence MIT autorise l’usage commercial, y compris pour des clients. Deux points à vérifier vous-même : les conditions de votre fournisseur d’IA (les CLI par abonnement comme Claude Code et Codex sont destinées à un usage personnel ; utilisez une clé d’API ou un modèle local quand les conditions l’exigent), et les licences des polices, musiques et images que vous utilisez. Le moteur de détourage RVM, optionnel pour les couvertures, est sous GPL-3.0 et n’est téléchargé que si vous le choisissez.

## Dois-je signaler les contenus générés par IA ?

Respectez les règles de chaque plateforme. Les plateformes chinoises exigent une déclaration pour les contenus générés par IA (règles en vigueur depuis le 1er septembre 2025), et YouTube, TikTok et Meta ont leurs propres mentions IA. Reelfold ne coche jamais ces cases pour vous ; la checklist de publication et les notes de livraison client vous le rappellent. Le workflow de vidéo IA prévoit une mention par plateforme. Voir la [référence sur la publication](/docs/fr/reference/engine/publishing/).

## Que sont devenus video-studio et Daycut ?

Reelfold est le nouveau nom. Le skill et le moteur open source étaient publiés sous le nom **video-studio**, et l’app de bureau s’appelait **Daycut** (日剪). Le skill s’appelle toujours `video-studio`, le paquet Python reste `vstudio`, et les installations existantes dans `~/.claude/skills/video-studio` continuent de fonctionner. Seul le dépôt a déménagé, vers [github.com/zyziyun/reelfold](https://github.com/zyziyun/reelfold).

## Voir aussi

- [Qu’est-ce que Reelfold](/docs/fr/start/what-is-reelfold/)
- [Dépannage](/docs/fr/help/troubleshooting/)
- [Contribuer](/docs/fr/contributing/)
