// The editor brain's two-language reasons (the engine writes English and Chinese; French reads the English).
import type { BrainText } from '../../../shared/v04';
import { getLang } from '../i18n';

export const said = (x: BrainText | null | undefined): string => (!x ? '' : getLang() === 'zh-CN' ? x.zh || x.en : x.en || x.zh);
