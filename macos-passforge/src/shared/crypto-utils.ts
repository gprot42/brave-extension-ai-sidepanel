let clipboardClearTimer: ReturnType<typeof setTimeout> | null = null;

export async function copyToClipboard(text: string, clearAfterMs: number = 15000): Promise<void> {
  await navigator.clipboard.writeText(text);

  if (clipboardClearTimer) {
    clearTimeout(clipboardClearTimer);
  }

  if (clearAfterMs > 0) {
    clipboardClearTimer = setTimeout(async () => {
      try {
        const current = await navigator.clipboard.readText();
        if (current === text) {
          await navigator.clipboard.writeText('');
        }
      } catch {
        // Clipboard access may fail if extension is not focused
      }
      clipboardClearTimer = null;
    }, clearAfterMs);
  }
}

export function extractDomain(url: string): string {
  try {
    const parsed = new URL(url);
    return parsed.hostname.replace(/^www\./, '').toLowerCase();
  } catch {
    return '';
  }
}

/**
 * Extract the base (registrable) domain from a hostname.
 * e.g. "client.schwab.com" → "schwab.com", "login.accounts.google.com" → "google.com"
 */
function getBaseDomain(domain: string): string {
  const parts = domain.split('.');
  if (parts.length <= 2) return domain;
  // Return last two parts as base domain
  return parts.slice(-2).join('.');
}

export function domainMatches(entryUrl: string, pageUrl: string): boolean {
  const entryDomain = extractDomain(entryUrl);
  const pageDomain = extractDomain(pageUrl);
  if (!entryDomain || !pageDomain) return false;

  // Exact match
  if (pageDomain === entryDomain) return true;

  // Subdomain match in either direction
  if (pageDomain.endsWith('.' + entryDomain)) return true;
  if (entryDomain.endsWith('.' + pageDomain)) return true;

  // Base domain match (e.g. client.schwab.com ↔ www.schwab.com)
  return getBaseDomain(pageDomain) === getBaseDomain(entryDomain);
}
