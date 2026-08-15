import { describe, expect, it, vi } from 'vitest'
import { createRandomUuid, createRandomUuidHex } from '../randomUuid'

describe('random UUID compatibility', () => {
  it('prefers the browser native randomUUID implementation', () => {
    const randomUUID = vi.fn(() => '12345678-1234-4234-8234-123456789abc')
    const getRandomValues = vi.fn()
    const source = { randomUUID, getRandomValues } as unknown as Crypto

    expect(createRandomUuid(source)).toBe('12345678-1234-4234-8234-123456789abc')
    expect(randomUUID).toHaveBeenCalledOnce()
    expect(getRandomValues).not.toHaveBeenCalled()
  })

  it('creates an RFC 4122 version 4 UUID from getRandomValues', () => {
    const getRandomValues = vi.fn((bytes: Uint8Array) => {
      bytes.set(Array.from({ length: 16 }, (_, index) => index))
      return bytes
    })
    const source = { getRandomValues } as unknown as Crypto

    expect(createRandomUuid(source)).toBe('00010203-0405-4607-8809-0a0b0c0d0e0f')
    expect(createRandomUuidHex(source)).toBe('000102030405460788090a0b0c0d0e0f')
  })

  it('fails clearly when no secure random source exists', () => {
    expect(() => createRandomUuid(null)).toThrow(
      '当前浏览器无法生成安全随机标识，请升级浏览器或使用 HTTPS。',
    )
  })
})
