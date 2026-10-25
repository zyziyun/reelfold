// Only the cover controls may be clicked. There is no arbitrary selector/click API.
export function coverAction(action: 'open' | 'upload' | 'input' | 'confirm' | 'closed'): string {
  return `(() => {
    if (location.hostname !== 'creator.xiaohongshu.com') throw new Error('Cover filling requires Xiaohongshu creator center');
    const visible = el => el.getClientRects().length > 0;
    const text = el => (el.innerText || el.textContent || '').trim();
    const matches = (root, label) => [...root.querySelectorAll('button,span,div,a,h1,h2,h3,[role="tab"]')]
      .filter(el => visible(el) && text(el) === label)
      .sort((a,b) => a.querySelectorAll('*').length - b.querySelectorAll('*').length);
    const exact = (root, label) => matches(root, label)[0];
    const headings = matches(document, '设置封面');
    // The page's opener can remain visible behind the modal. Find the smallest
    // enclosing cover dialog, rather than assuming the first label is its title.
    const dialogs = headings.map(heading => {
      let candidate = heading;
      while (candidate && candidate !== document.body) {
        if (exact(candidate, '上传封面') && exact(candidate, '取消')) return candidate;
        candidate = candidate.parentElement;
      }
      return null;
    }).filter(Boolean);
    const dialog = dialogs.sort((a,b) => a.querySelectorAll('*').length - b.querySelectorAll('*').length)[0];
    const heading = headings[0];
    const action = ${JSON.stringify(action)};
    if (action === 'closed') return !dialog;
    if (action === 'open') {
      if (dialog) return true;
      if (!heading) return false;
      heading.click(); return true;
    }
    if (!dialog) return false;
    if (action === 'upload') { const tab = exact(dialog, '上传封面'); if (!tab) return false; tab.click(); return true; }
    if (action === 'input') return [...dialog.querySelectorAll('input[type="file"]')].find(el => /image|png|jpe?g/i.test(el.accept)) || null;
    if (action === 'confirm') {
      const button = exact(dialog, '确定');
      if (!button || button.disabled || button.getAttribute('aria-disabled') === 'true' || button.closest('[disabled], [aria-disabled="true"]')) return false;
      button.click(); return true;
    }
    return false;
  })()`;
}
