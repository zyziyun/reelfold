/** Runs in the platform page's isolated world. Drafts and ordinary page copy are
 * not delivery receipts. Unsupported page structures require manual confirmation. */
export function successSnapshot(): { text: string; links: string[] } {
  const editable = 'input,textarea,select,[role="textbox"],[contenteditable]:not([contenteditable="false"])';
  const statuses = Array.from(document.querySelectorAll('[role="status"],[role="alert"],[aria-live="polite"],[aria-live="assertive"]'))
    .slice(0, 200)
    .filter((node): node is HTMLElement => {
      if (!(node instanceof HTMLElement) || !node.getClientRects().length) return false;
      if (node.closest('[hidden],[aria-hidden="true"]') || node.closest(editable) || node.querySelector(editable)) return false;
      for (let current: HTMLElement | null = node; current; current = current.parentElement) {
        const style = getComputedStyle(current);
        if (style.visibility !== 'visible' || style.display === 'none' || style.opacity === '0') return false;
      }
      return true;
    });
  return {
    text: statuses.map(node => node.innerText).join('\n').slice(0, 20000),
    // An old post link elsewhere on the management page is not this upload's URL.
    links: statuses.flatMap(node => Array.from(node.querySelectorAll<HTMLAnchorElement>('a[href]')).map(a => a.href)).slice(0, 400),
  };
}
