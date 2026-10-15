import { afterEach, expect, it } from 'vitest';
import { setLang } from '../../src/renderer/src/i18n';
import { emsg } from '../../src/renderer/src/v4/msg';

afterEach(() => setLang('en'));
it('keeps the rejected parameter detail in the selected language', () => {
  const error = { code: 'bad-param', params: {}, message: 'Sticker image file is missing', message_zh: '找不到贴纸图片文件' };
  setLang('en');
  expect(emsg(error)).toBe(error.message);
  setLang('zh-CN');
  expect(emsg(error)).toBe(error.message_zh);
});
it('keeps generic parameter copy when no detail was provided', () => {
  expect(emsg({ code: 'bad-param', params: {} })).toBe('A setting is missing or out of range.');
});
