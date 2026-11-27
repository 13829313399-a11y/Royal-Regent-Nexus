/** Extract the Chinese product name for one code from a schedule display name. */
export function productNameForCode(raw: unknown, code: unknown): string {
  const text = String(raw ?? '').trim()
  const key = String(code ?? '').trim()
  if (!text) return ''
  const segments = text.split(/[+＋]/).map((part) => part.trim()).filter(Boolean)
  if (segments.length > 1) {
    const segment = key ? segments.find((part) => part.includes(key)) : undefined
    if (!segment) return ''
    return segment
      .replace(new RegExp(`^\\s*\\d+\\s*[*×xX]\\s*${key.replace(/[.*+?^${}()|[\]\\]/g, '\\$&')}\\s*`), '')
      .replace(/^\s*\d+\s*[*×xX]\s*\d+\s*/, '')
      .replace(/^\s*\d+\s*/, '')
      .trim()
  }
  return text
    .replace(/^\s*\d+\s*[*×xX]\s*\d+\s*/, '')
    .replace(/^\s*\d+\s*/, '')
    .trim()
}
