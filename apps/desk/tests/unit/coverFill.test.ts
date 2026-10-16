import { describe, it, expect } from 'vitest';
import { planFill } from '../../src/shared/publish/fillPlan';
import { parseAdapter } from '../../src/shared/publish/adapterSchema';
import adapter from '../../adapters/xiaohongshu.json';

describe('Xiaohongshu cover dialog', () => {
  it('plans the selected cover only when available', () => {
    const parsed = parseAdapter(adapter);
    if (!parsed.ok) throw new Error(parsed.error);
    const payload = { videoPath: '/video.mp4', copy: { title: 'Title', description: 'Text', tags: [] } };
    expect(planFill(parsed.adapter, payload).some(s => s.field === 'cover')).toBe(false);
    expect(planFill(parsed.adapter, { ...payload, coverPath: '/cover.png' }).find(s => s.field === 'cover'))
      .toMatchObject({ kind: 'files', paths: ['/cover.png'], coverFlow: 'xiaohongshu' });
  });
});
