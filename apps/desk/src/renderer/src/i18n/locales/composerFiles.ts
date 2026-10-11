// The composer's attached files (v4/Composer.tsx, lib/attachments): with many files one plain line ("104 files · 50
// videos with their .srt · 4 photos") that opens into the list. A drone's same-named .srt is its flight data, so it
// is "its .srt", never "captions". English, 简体中文, Français.

export const composerFilesEn = {
  'cf.files': '{n, plural, one {# file} other {# files}}',
  'cf.videos': '{n, plural, one {# video} other {# videos}}',
  'cf.withSubs': '{n, plural, one {# with its .srt} other {# with their .srt}}',
  'cf.photos': '{n, plural, one {# photo} other {# photos}}',
  'cf.audio': '{n, plural, one {# audio file} other {# audio files}}',
  'cf.docs': '{n, plural, one {# document} other {# documents}}',
  'cf.subs': '{n, plural, one {# subtitle file} other {# subtitle files}}',
  'cf.folders': '{n, plural, one {# folder} other {# folders}}',
  'cf.other': '{n, plural, one {# other file} other {# other files}}',
  'cf.plusSrt': '+ .srt',
  'cf.show': 'Show the list',
  'cf.hide': 'Hide the list',
  'cf.removeAll': 'Remove all',
  'cf.removeOne': 'Remove {name}',
};

export const composerFilesZh: Record<keyof typeof composerFilesEn, string> = {
  'cf.files': '{n} 个文件',
  'cf.videos': '{n} 个视频',
  'cf.withSubs': '其中 {n} 个带同名 .srt',
  'cf.photos': '{n} 张照片',
  'cf.audio': '{n} 个音频',
  'cf.docs': '{n} 份文档',
  'cf.subs': '{n} 个字幕文件',
  'cf.folders': '{n} 个文件夹',
  'cf.other': '{n} 个其他文件',
  'cf.plusSrt': '+ .srt',
  'cf.show': '展开列表',
  'cf.hide': '收起列表',
  'cf.removeAll': '全部移除',
  'cf.removeOne': '移除 {name}',
};

export const composerFilesFr: Record<keyof typeof composerFilesEn, string> = {
  'cf.files': '{n, plural, one {# fichier} other {# fichiers}}',
  'cf.videos': '{n, plural, one {# vidéo} other {# vidéos}}',
  'cf.withSubs': '{n, plural, one {# avec son .srt} other {# avec leur .srt}}',
  'cf.photos': '{n, plural, one {# photo} other {# photos}}',
  'cf.audio': '{n, plural, one {# fichier audio} other {# fichiers audio}}',
  'cf.docs': '{n, plural, one {# document} other {# documents}}',
  'cf.subs': '{n, plural, one {# fichier de sous-titres} other {# fichiers de sous-titres}}',
  'cf.folders': '{n, plural, one {# dossier} other {# dossiers}}',
  'cf.other': '{n, plural, one {# autre fichier} other {# autres fichiers}}',
  'cf.plusSrt': '+ .srt',
  'cf.show': 'Voir la liste',
  'cf.hide': 'Masquer la liste',
  'cf.removeAll': 'Tout retirer',
  'cf.removeOne': 'Retirer {name}',
};
