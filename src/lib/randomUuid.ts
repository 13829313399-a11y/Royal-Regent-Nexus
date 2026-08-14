const RANDOM_UUID_BYTES = 16

function browserCrypto(): Crypto | undefined {
  return typeof globalThis.crypto === 'object' ? globalThis.crypto : undefined
}

export function createRandomUuid(source: Crypto | null | undefined = browserCrypto()): string {
  if (typeof source?.randomUUID === 'function') {
    return source.randomUUID.call(source)
  }
  if (typeof source?.getRandomValues !== 'function') {
    throw new Error('当前浏览器无法生成安全随机标识，请升级浏览器或使用 HTTPS。')
  }

  const bytes = new Uint8Array(RANDOM_UUID_BYTES)
  source.getRandomValues(bytes)
  bytes[6] = (bytes[6] & 0x0f) | 0x40
  bytes[8] = (bytes[8] & 0x3f) | 0x80
  const hex = Array.from(bytes, value => value.toString(16).padStart(2, '0')).join('')
  return [
    hex.slice(0, 8),
    hex.slice(8, 12),
    hex.slice(12, 16),
    hex.slice(16, 20),
    hex.slice(20),
  ].join('-')
}

export function createRandomUuidHex(source: Crypto | null | undefined = browserCrypto()): string {
  return createRandomUuid(source).replaceAll('-', '')
}
