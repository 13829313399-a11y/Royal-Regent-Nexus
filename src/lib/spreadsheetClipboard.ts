/** Text cells preserve leading zeros without injecting apostrophes into Kintable. */
export async function writeSpreadsheetClipboard(data: { text: string; html?: string }): Promise<'rich' | 'plain'> {
  if (data.html && navigator.clipboard?.write && typeof ClipboardItem !== 'undefined') {
    try {
      await navigator.clipboard.write([new ClipboardItem({
        'text/plain': new Blob([data.text], { type: 'text/plain' }),
        'text/html': new Blob([data.html], { type: 'text/html' }),
      })])
      return 'rich'
    } catch { /* Some browsers expose write() but reject HTML; try the legacy path. */ }
  }
  // Older Windows browsers and HTTP intranet pages can still copy both formats
  // during this user action. No source HTML is inserted into the page DOM.
  if (data.html && typeof document.execCommand === 'function') {
    let copied = false
    const listener = (event: ClipboardEvent) => {
      if (!event.clipboardData) return
      event.preventDefault()
      event.clipboardData.setData('text/plain', data.text)
      event.clipboardData.setData('text/html', data.html!)
      copied = true
    }
    document.addEventListener('copy', listener)
    try {
      if (document.execCommand('copy') && copied) return 'rich'
    } finally {
      document.removeEventListener('copy', listener)
    }
  }
  if (!navigator.clipboard?.writeText) throw new Error('clipboard unavailable')
  await navigator.clipboard.writeText(data.text)
  return 'plain'
}
