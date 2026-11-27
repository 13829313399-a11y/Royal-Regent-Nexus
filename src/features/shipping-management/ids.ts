/** Stable UUID helper for browsers that do not expose crypto.randomUUID (HTTP/LAN). */
export function newId(): string {
  const cryptoObject = typeof globalThis !== 'undefined' ? globalThis.crypto : undefined
  if (cryptoObject && typeof cryptoObject.randomUUID === 'function') {
    return cryptoObject.randomUUID()
  }
  if (cryptoObject && typeof cryptoObject.getRandomValues === 'function') {
    const bytes = cryptoObject.getRandomValues(new Uint8Array(16))
    bytes[6] = (bytes[6] & 0x0f) | 0x40
    bytes[8] = (bytes[8] & 0x3f) | 0x80
    const hex = [...bytes].map((value) => value.toString(16).padStart(2, '0')).join('')
    return `${hex.slice(0, 8)}-${hex.slice(8, 12)}-${hex.slice(12, 16)}-${hex.slice(16, 20)}-${hex.slice(20)}`
  }
  return `id-${Date.now().toString(36)}-${Math.random().toString(36).slice(2, 10)}`
}
