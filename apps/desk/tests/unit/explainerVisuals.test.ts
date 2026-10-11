// Her MCP course (2026-10-11): Claude Code timed out, the scenes fell back to the rules and the autopilot shipped a
// video of plain text lines. A step that needs an AI model now says so in her words ("The visuals need an AI model —
// Claude Code didn't answer") in the Inbox and on a failed remake, and a finished explainer offers "Redo the visuals"
// on its clip page. English, 简体中文, Français.
import { afterEach, describe, expect, it } from 'vitest';
import type { AutopilotChoice, InboxAuthor } from '../../src/shared/v04';
import type { PilotFailure } from '../../src/shared/v02';
import { setLang } from '../../src/renderer/src/i18n';
import { keptNote, visualsFailure, visualsOf } from '../../src/renderer/src/v4/ClipInfo';
import { needsModelText } from '../../src/renderer/src/v4/DraftReview';
import { failureReason } from '../../src/renderer/src/v4/Failure';

afterEach(() => setLang('en'));

const a = (o: Partial<InboxAuthor>): InboxAuthor => ({ file: '/p/items/ep1/compositions', exists: false, checkpoint: 'scenes', recipe: 'explainer', ...o });

describe('a step that needs an AI model', () => {
  it('no model drew the visuals: the plain sentence, the provider by name', () => {
    const x = a({ draft_error_code: 'ai-needs-model', draft_error_params: { provider: 'claude-code', what: 'visuals' }, draft_error: 'raw' });
    expect(needsModelText(x)).toBe('The visuals need an AI model — Claude Code didn’t answer. Try again, or choose another model in Settings › AI.');
    setLang('zh-CN');
    expect(needsModelText(x)).toBe('画面需要 AI 模型来画——Claude Code 没有回应。再试一次，或在“设置 › AI”里换一个模型。');
    setLang('fr');
    expect(needsModelText(x)).toContain('Les visuels ont besoin d’un modèle d’IA — Claude Code n’a pas répondu');
  });
  it('no model connected at all, and the script step', () => {
    expect(needsModelText(a({ draft_error_code: 'ai-needs-model', draft_error_params: { provider: 'none', what: 'visuals' } }))).toBe(
      'The visuals need an AI model — none is connected. Connect one in Settings › AI, then try again.',
    );
    expect(needsModelText(a({ checkpoint: 'script', draft_error_code: 'ai-needs-model', draft_error_params: { provider: 'codex' } }))).toBe(
      'The script needs an AI model — Codex didn’t answer. Try again, or choose another model in Settings › AI.',
    );
  });
  it('a rules draft of such a step says it too; the AI’s draft or hers does not', () => {
    const rv = { kind: 'outline' as const, summary: { code: 'draft.items', params: { n: 14 } }, lines: [] };
    expect(needsModelText(a({ checkpoint: 'storyboard', needs_ai: true, draft_by: 'rules', ai_provider: 'claude-code', review: rv }))).toContain('The visuals need an AI model — Claude Code');
    expect(needsModelText(a({ needs_ai: true, draft_by: 'ai', review: rv }))).toBeNull();
    expect(needsModelText(a({ needs_ai: true, draft_by: 'her', review: rv }))).toBeNull();
    expect(needsModelText(a({ checkpoint: 'cues', draft_by: 'rules', review: rv }))).toBeNull();
  });
  it('a remake no model drew: the failure card says it', () => {
    const f: PilotFailure = { state: 'failed', code: 'ai-needs-model', provider: 'claude-code', error: 'x', at: 1, params: { what: 'visuals' } };
    expect(failureReason(f)).toBe('The visuals need an AI model — Claude Code didn’t answer. Try again, or choose another model in Settings › AI.');
  });
});

describe('Redo the visuals', () => {
  const c = (o: Partial<AutopilotChoice>): AutopilotChoice => ({ checkpoint: 'scenes', kind: 'author', item: 'mcp-course-ep1', pick: null, choice: 'rules', options: [], by: 'rules', remake_as: 'visuals', ...o });
  it('shows on a finished explainer’s clip (any of its versions)', () => {
    expect(visualsOf({ choices: [c({})] }, 'mcp-course-ep1/youtube-horizontal')).toEqual({ checkpoint: 'scenes', item: 'mcp-course-ep1', by: 'rules', kept: [], total: null, missing: false });
    expect(visualsOf({ choices: [c({})] }, 'other/youtube-horizontal')).toBeNull();
    expect(visualsOf({ choices: [c({ remake_as: undefined, kind: 'copy-pick' })] }, 'mcp-course-ep1')).toBeNull(); // a vlog's copy
    expect(visualsOf(null, 'mcp-course-ep1')).toBeNull();
  });
});

// her MCP course again (2026-10-11): scene 14 kept calling fetch(); the redo threw the other 13 away and the course
// fell into Needs you as "The first clip stopped" with a Confirm button
describe('a redo that could not draw a scene', () => {
  const c = (o: Partial<AutopilotChoice>): AutopilotChoice => ({ checkpoint: 'scenes', kind: 'author', item: 'ep1', pick: null, choice: 'ai', options: [], by: 'ai', remake_as: 'visuals', ...o });
  it('kept it as before: "13 of 14 scenes redrawn; scene 14 kept as before" + Redraw scene 14', () => {
    const v = visualsOf({ choices: [c({ options: ['missing'], kept: [{ id: 'f14-mcp-a2a', n: 14, how: 'before', why: 'network' }], total: 14 })] }, 'ep1/youtube-horizontal')!;
    expect(v.missing).toBe(true);
    expect(keptNote(v.kept, v.total)).toBe('13 of 14 scenes redrawn; scene 14 kept as before');
    expect(keptNote([{ id: 'a', n: 3, how: 'before' }, { id: 'b', n: 14, how: 'diagram' }], 14)).toBe('12 of 14 scenes redrawn; scene 3 kept as before; scene 14 drawn as a simple diagram for now');
    expect(keptNote([{ id: 'a', n: 14, how: 'before' }, { id: 'b', n: 3, how: 'before' }], 14)).toBe('12 of 14 scenes redrawn; scenes 3, 14 kept as before');
    setLang('zh-CN');
    expect(keptNote(v.kept, v.total)).toBe('已重画 13/14 段；第 14 段保留原样');
    setLang('fr');
    expect(keptNote(v.kept, v.total)).toBe('13 scènes sur 14 redessinées ; scène 14 : gardée(s) comme avant');
  });
  it('drew none: which scene and why, plainly, in three languages - the video unchanged', () => {
    const f: PilotFailure = { state: 'failed', code: 'stage-visuals-failed', provider: null, error: 'raw', at: 1, stage: 'scenes', remake: true, params: { scene: '14', total: '14', n: '1', why: 'network', id: 'f14-mcp-a2a' } };
    expect(failureReason(f)).toBe('Scene 14 of 14 couldn’t be redrawn: the AI kept loading data from the internet, which a video can’t do. Your video is unchanged — Try again redraws only the missing scenes.');
    expect(failureReason({ ...f, params: { ...f.params, n: '2', why: 'odd' } })).toBe('2 of 14 scenes couldn’t be redrawn: it didn’t pass the renderer’s check. Your video is unchanged — Try again redraws only the missing scenes.');
    setLang('zh-CN');
    expect(failureReason(f)).toBe('第 14 段（共 14 段）没能重新画出来：AI 一直想从网上加载数据，视频里做不到。你的视频没有变——点「重试」只重画没画好的那几段。');
    setLang('fr');
    expect(failureReason(f)).toContain('La scène 14 sur 14 n’a pas pu être redessinée : l’IA chargeait sans cesse des données depuis Internet');
  });
  it('is a notice on the clip only for a remake that stopped, not while it runs, not for a run that failed', () => {
    const f: PilotFailure = { state: 'failed', code: 'stage-visuals-failed', provider: null, error: '', at: 1, stage: 'scenes', remake: true };
    expect(visualsFailure({ failure: f, running: false, queued: null }, 'scenes')).toBe(f);
    expect(visualsFailure({ failure: f, running: true, queued: null }, 'scenes')).toBeNull();
    expect(visualsFailure({ failure: { ...f, remake: undefined }, running: false, queued: null }, 'scenes')).toBeNull();
    expect(visualsFailure({ failure: { ...f, code: 'unknown', stage: 'framing' }, running: false, queued: null }, 'scenes')).toBeNull();
  });
});
