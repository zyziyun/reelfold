/** Resolve a post's destination without silently switching accounts. Older posts
 * may use a sole account; multiple accounts always need an explicit choice. */
export function postAccount(accounts: readonly string[], selected?: string | null): string | null {
  if (selected) return accounts.includes(selected) ? selected : null;
  return accounts.length === 1 ? accounts[0] : null;
}
