/**
 * Safely copies text to the system clipboard across both secure (HTTPS, localhost)
 * and non-secure (e.g. LAN IP over HTTP like http://192.168.0.196:3000) contexts.
 *
 * In non-secure contexts, `navigator.clipboard` is undefined in Chromium/Firefox,
 * so this utility falls back to `document.execCommand('copy')` with a temporary textarea.
 *
 * @param {string} text - The text string to copy.
 * @returns {Promise<boolean>} Resolves to true if successfully copied, false otherwise.
 */
export async function copyToClipboard(text) {
  if (text == null) return false;
  const str = typeof text === 'string' ? text : String(text);
  if (!str) return false;

  // 1. Try modern navigator.clipboard API if available
  if (typeof navigator !== 'undefined' && navigator.clipboard && typeof navigator.clipboard.writeText === 'function') {
    try {
      await navigator.clipboard.writeText(str);
      return true;
    } catch (err) {
      console.warn('navigator.clipboard.writeText failed, attempting execCommand fallback:', err);
    }
  }

  // 2. Fallback: document.execCommand('copy') using an off-screen textarea
  try {
    const textArea = document.createElement('textarea');
    textArea.value = str;

    // Avoid scrolling or viewport displacement
    textArea.style.position = 'fixed';
    textArea.style.top = '0';
    textArea.style.left = '-9999px';
    textArea.style.width = '2em';
    textArea.style.height = '2em';
    textArea.style.padding = '0';
    textArea.style.border = 'none';
    textArea.style.outline = 'none';
    textArea.style.boxShadow = 'none';
    textArea.style.background = 'transparent';
    textArea.style.opacity = '0';
    textArea.setAttribute('readonly', '');

    document.body.appendChild(textArea);
    textArea.focus({ preventScroll: true });
    textArea.select();
    textArea.setSelectionRange(0, str.length);

    const successful = document.execCommand('copy');
    document.body.removeChild(textArea);

    if (successful) {
      return true;
    }
  } catch (err) {
    console.error('execCommand copy fallback failed:', err);
  }

  return false;
}
