// Per-task AI (the AI chip of the composer, the run page, the project page, the clip chat, a goal's group): English,
// 简体中文, français.

export const taskAiEn = {
  'tai.chipTip': 'The AI for this',
  'tai.composerTip': 'The AI for this request',
  'tai.runTip': 'The AI this request plans with',
  'tai.projectTip': 'This project’s AI (from its next AI step)',
  'tai.groupTip': 'The AI of every video in this group',
  'tai.videoTip': 'This video’s AI',
  'tai.tagTip': 'Runs on {name}',
  'tai.useDefault': 'Use my default ({name})',
  'tai.switched': 'Now using {name}, from the next AI step.',
  'tai.switchedDefault': 'Back to your default ({name}), from the next AI step.',
  'tai.groupSwitched': 'The group now uses {name}: the videos not made yet switch, running ones from their next AI step.',
  'tai.chatSwitched': 'This project now uses {name}, from its next AI step. Your default stays {def}.',
  'tai.makeDefault': 'Make this my default',
  'tai.madeDefault': '{name} is now your default for new requests.',
};

export const taskAiZh: Record<keyof typeof taskAiEn, string> = {
  'tai.chipTip': '这里用的 AI',
  'tai.composerTip': '这次请求用的 AI',
  'tai.runTip': '这次请求规划用的 AI',
  'tai.projectTip': '这个项目的 AI（从下一个 AI 步骤起）',
  'tai.groupTip': '这组所有视频用的 AI',
  'tai.videoTip': '这个视频用的 AI',
  'tai.tagTip': '用 {name}',
  'tai.useDefault': '用我的默认（{name}）',
  'tai.switched': '已换成 {name}，从下一个 AI 步骤起生效。',
  'tai.switchedDefault': '已换回默认（{name}），从下一个 AI 步骤起生效。',
  'tai.groupSwitched': '这组已换成 {name}：还没做好的视频都换，正在做的从下一个 AI 步骤起。',
  'tai.chatSwitched': '这个项目已换成 {name}，从下一个 AI 步骤起生效。你的默认还是 {def}。',
  'tai.makeDefault': '设为我的默认',
  'tai.madeDefault': '{name} 已设为新请求的默认 AI。',
};

export const taskAiFr: Record<keyof typeof taskAiEn, string> = {
  'tai.chipTip': 'L’IA utilisée ici',
  'tai.composerTip': 'L’IA de cette demande',
  'tai.runTip': 'L’IA qui planifie cette demande',
  'tai.projectTip': 'L’IA de ce projet (dès sa prochaine étape IA)',
  'tai.groupTip': 'L’IA de toutes les vidéos de ce groupe',
  'tai.videoTip': 'L’IA de cette vidéo',
  'tai.tagTip': 'Tourne sur {name}',
  'tai.useDefault': 'Utiliser mon IA par défaut ({name})',
  'tai.switched': 'C’est maintenant {name}, dès la prochaine étape IA.',
  'tai.switchedDefault': 'Retour à votre IA par défaut ({name}), dès la prochaine étape IA.',
  'tai.groupSwitched': 'Le groupe utilise maintenant {name} : les vidéos pas encore faites changent, celles en cours dès leur prochaine étape IA.',
  'tai.chatSwitched': 'Ce projet utilise maintenant {name}, dès sa prochaine étape IA. Votre IA par défaut reste {def}.',
  'tai.makeDefault': 'En faire mon IA par défaut',
  'tai.madeDefault': '{name} est maintenant votre IA par défaut pour les nouvelles demandes.',
};
