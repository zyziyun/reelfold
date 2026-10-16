// Only the cover controls may be clicked. There is no arbitrary selector/click API.
export function coverAction(action: 'open' | 'upload' | 'input' | 'confirm' | 'closed'): string {
  return `(() => {
    if (location.hostname !== 'creator.xiaohongshu.com') throw new Error('Cover filling requires Xiaohongshu creator center');
    const visible = el => el.getClientRects().length > 0;
    const text = el => (el.innerText || el.textContent || '').trim();
    const exact = (root, label) => [...root.querySelectorAll('button,span,div,a,h1,h2,h3,[role="tab"]')]
      .filter(el => visible(el) && text(el) === label)
      .sort((a,b) => a.querySelectorAll('*').length - b.querySelectorAll('*').length)[0];
    const heading = exact(document, '设置封面');
    let dialog = heading;
    while (dialog && dialog !== document.body && !(exact(dialog, '上传封面') && exact(dialog, '取消'))) dialog = dialog.parentElement;
    if (dialog === document.body) dialog = null;
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
