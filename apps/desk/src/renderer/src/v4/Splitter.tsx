// One divider for every split (studio-polish): a hairline that lights up on hover / focus, a wide invisible grab area,
// drag with the mouse (pointer capture, the page does not select text meanwhile), double-click to put it back, and the
// keyboard when focused (arrows, Shift for a bigger step, Home / End, Enter folds a pane that can fold).
import { useRef } from 'react';
import { FOLD_PAST, dragTo, keyTo, type PaneSpec, type PaneState } from '../lib/panes';
import './splitter.css';

export function Splitter({
  orient,
  sign,
  state,
  spec,
  room,
  onChange,
  onReset,
  label,
  tip,
  testId,
  className = '',
  perPx = 1,
  step,
  bigStep,
}: {
  /** col: a vertical line between two columns (drags left / right); row: a horizontal line between two rows */
  orient: 'col' | 'row';
  /** +1 when moving right / down makes the pane bigger, -1 when the pane is right of / below the line */
  sign: 1 | -1;
  state: PaneState;
  spec: PaneSpec;
  room?: number;
  onChange: (s: PaneState) => void;
  onReset: () => void;
  label: string;
  tip?: string;
  testId?: string;
  className?: string;
  /** the size's units per pixel (1 for px; 1 / height for a share of the height) */
  perPx?: number;
  step?: number;
  bigStep?: number;
}) {
  const drag = useRef<{ x: number; y: number; from: PaneState; moved: boolean } | null>(null);
  const grow = orient === 'col' ? (sign > 0 ? 'ArrowRight' : 'ArrowLeft') : sign > 0 ? 'ArrowDown' : 'ArrowUp';
  // aria values in px, or in % for a share (the editor's player / lower split)
  const v = (x: number) => Math.round(spec.max <= 1 ? x * 100 : x);
  const end = (el: HTMLElement) => {
    drag.current = null;
    el.classList.remove('on');
    document.body.classList.remove('resizing', 'resizing-col', 'resizing-row');
  };
  return (
    <div
      className={`splitter ${orient} ${state.collapsed ? 'folded' : ''} ${className}`}
      role="separator"
      tabIndex={0}
      aria-orientation={orient === 'col' ? 'vertical' : 'horizontal'}
      aria-label={label}
      aria-valuenow={state.collapsed ? 0 : v(state.size)}
      aria-valuemin={spec.collapsible ? 0 : v(spec.min)}
      aria-valuemax={v(Math.max(spec.min, Math.min(spec.max, room ?? Infinity)))}
      title={tip}
      data-collapsed={state.collapsed ? '1' : undefined}
      data-testid={testId}
      onPointerDown={(e) => {
        if (e.button !== 0) return;
        e.preventDefault();
        const el = e.currentTarget;
        el.setPointerCapture?.(e.pointerId);
        el.focus({ preventScroll: true });
        drag.current = { x: e.clientX, y: e.clientY, from: state, moved: false };
        el.classList.add('on');
        document.body.classList.add('resizing', `resizing-${orient}`);
      }}
      onPointerMove={(e) => {
        const d = drag.current;
        if (!d) return;
        const px = orient === 'col' ? e.clientX - d.x : e.clientY - d.y;
        if (!d.moved && Math.abs(px) < 3) return; // a click is not a drag
        d.moved = true;
        // a folded pane opens from its edge: the drag starts just past the fold line
        const start = d.from.collapsed ? spec.min - FOLD_PAST * perPx : d.from.size;
        onChange(dragTo(start, px * perPx, sign, spec, room));
      }}
      onPointerUp={(e) => end(e.currentTarget)}
      onPointerCancel={(e) => end(e.currentTarget)}
      onLostPointerCapture={(e) => drag.current && end(e.currentTarget)}
      onDoubleClick={onReset}
      onKeyDown={(e) => {
        const n = keyTo(e.key, e.shiftKey, state, spec, grow, room, step, bigStep);
        if (!n) return;
        e.preventDefault();
        e.stopPropagation(); // not the Studio's ↑ ↓ (next video) or the player's ← →
        onChange(n);
      }}
    >
      <i aria-hidden />
    </div>
  );
}
