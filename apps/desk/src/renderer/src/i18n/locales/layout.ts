// Every split can be resized (studio-polish): the Studio's list (folds to the edge, ⌘B), the clip page's player column,
// the AI conversation's width, the editor's clip info above the chat; a page that could not open. English, 简体中文,
// Français.

export const layoutEn = {
  'lay.dragTip': 'Drag to resize · double-click to reset',
  'st.listHide': 'Hide the list',
  'st.listShow': 'Show the list',
  'st.listResize': 'Resize the list',
  'st.playerResize': 'Resize the player column',
  'st.playerCol': 'Player, cover, captions and versions',
  'st.aiResize': 'Resize the conversation',
  'st.pageFailed': 'This video did not open',
  'ce.infoResize': 'Resize the clip info',
  'keys.studioList': 'Hide or show the list of videos',
};

export const layoutZh: Record<keyof typeof layoutEn, string> = {
  'lay.dragTip': '拖动调整大小 · 双击还原',
  'st.listHide': '收起列表',
  'st.listShow': '展开列表',
  'st.listResize': '调整列表宽度',
  'st.playerResize': '调整播放器这一栏的宽度',
  'st.playerCol': '播放器、封面、字幕和版本',
  'st.aiResize': '调整对话栏宽度',
  'st.pageFailed': '这条视频没能打开',
  'ce.infoResize': '调整这条信息的高度',
  'keys.studioList': '收起或展开视频列表',
};

export const layoutFr: Record<keyof typeof layoutEn, string> = {
  'lay.dragTip': 'Glisser pour redimensionner · double-clic pour revenir',
  'st.listHide': 'Masquer la liste',
  'st.listShow': 'Afficher la liste',
  'st.listResize': 'Redimensionner la liste',
  'st.playerResize': 'Redimensionner la colonne du lecteur',
  'st.playerCol': 'Lecteur, couverture, sous-titres et versions',
  'st.aiResize': 'Redimensionner la conversation',
  'st.pageFailed': 'Cette vidéo ne s’est pas ouverte',
  'ce.infoResize': 'Redimensionner les infos du clip',
  'keys.studioList': 'Masquer ou afficher la liste des vidéos',
};
