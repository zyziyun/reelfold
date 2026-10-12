// Slash commands in Home's composer (both versions of Home): `/model` shows / switches the AI model for every job,
// `/help` lists the commands, the clip tools (/trim ...) say they work in a video's chat. A command is never sent as
// a request. The menu appears while she types "/" (no files attached).
import type { KeyboardEvent, ReactNode, RefObject } from 'react';
import type { ProviderId } from '../../../shared/aiRoutes';
import { t } from '../i18n';
import { loadModels, pickModel } from '../lib/ai';
import { isCardSlash, slashCommand, slashMatches, SLASH, type SlashId } from '../lib/chatEdit';
import { currentLine, switchByWords } from '../lib/modelCmd';
import { modelItems } from './AiChip';
import { useUi } from './ui';

export function useComposerSlash(prompt: string, setPrompt: (s: string) => void, ta: RefObject<HTMLTextAreaElement | null>, hasFiles: boolean) {
  const ui = useUi();
  const where = () => {
    const r = ta.current?.getBoundingClientRect();
    return r ? { clientX: r.left + 12, clientY: r.bottom } : null;
  };
  const run = async (raw: string) => {
    const sc = slashCommand(raw);
    if (!sc) return false;
    setPrompt('');
    if (sc.id === 'model' && sc.arg) {
      const r = await switchByWords(sc.arg, 'default');
      ui.toast(r.text, { error: !r.ok });
    } else if (sc.id === 'model') {
      await loadModels();
      const now = currentLine('default');
      const at = where();
      if (!now || now.provider === 'none' || !at) ui.toast(now ? t('mdl.cur', { name: now.name }) : t('mdl.noRoutes'));
      else
        ui.menu(
          at,
          modelItems(now.provider, now.model).map((m) => ({
            label: m.label,
            testId: `composer-model-${m.id ?? 'default'}`,
            run: () => void pickModel('default', now.provider as ProviderId, m.id).then(() => ui.toast(t('mdl.switched', { name: currentLine('default')?.name ?? '' }))),
          })),
        );
    } else if (sc.id === 'help' || sc.id === 'unknown') {
      if (sc.id === 'unknown') ui.toast(t('mdl.unknownCmd', { cmd: sc.name }), { error: true });
      const at = where();
      if (at) ui.menu(at, SLASH.map((c) => ({ label: `/${c.en} · ${t(`ce.slash.${c.id}` as never)}`, run: () => pick(c.id), testId: `composer-help-${c.id}` })));
    } else ui.toast(t('mdl.clipOnly', { cmd: SLASH.find((c) => c.id === sc.id)?.en ?? sc.id }));
    return true;
  };
  const pick = (k: SlashId) => (isCardSlash(k) ? ui.toast(t('mdl.clipOnly', { cmd: k })) : void run(`/${k}`));
  const isSlash = prompt.trim().startsWith('/') && !prompt.includes('\n') && !hasFiles;
  const matches = isSlash ? slashMatches(prompt) : [];
  /** Enter on a "/..." line: the highlighted command (a partial word) or the command as typed. true = handled. */
  const onKey = (e: KeyboardEvent<HTMLTextAreaElement>): boolean => {
    if (!isSlash || e.key !== 'Enter' || e.shiftKey || e.nativeEvent.isComposing) return false;
    e.preventDefault();
    const exact = slashCommand(prompt);
    if ((!exact || exact.id === 'unknown') && matches.length) pick(matches[0]);
    else void run(prompt.trim());
    return true;
  };
  const menu: ReactNode = matches.length ? (
    <div className="ux-slash" role="listbox" data-testid="composer-slash">
      {matches.map((k) => (
        <button key={k} role="option" onClick={() => pick(k)} data-testid={`composer-slash-${k}`}>
          <span className="mono">/{SLASH.find((c) => c.id === k)!.en}</span>
          <small>{t(`ce.slash.${k}` as never)}</small>
        </button>
      ))}
    </div>
  ) : null;
  /** ⌘↵ / Make it on a "/..." line: the command, never a request. true = handled. */
  const submit = () => (isSlash ? (void run(prompt.trim()), true) : false);
  return { menu, onKey, submit };
}
