import { describe, expect, it } from 'vitest'
import { formatShanghaiMovementTime } from '../cartonMovementTime'

describe('carton movement business time', () => {
  it('displays UTC and offset instants in the same Shanghai day as inventory filtering', () => {
    expect(formatShanghaiMovementTime('2026-09-30T16:30:00Z')).toBe('2026-10-01 00:30')
    expect(formatShanghaiMovementTime('2026-10-01T00:30:00+08:00')).toBe('2026-10-01 00:30')
    expect(formatShanghaiMovementTime('2026-09-30T12:30:00-04:00')).toBe('2026-10-01 00:30')
  })
  it('retains legacy local wall-clock time and reports malformed history without guessing', () => {
    expect(formatShanghaiMovementTime('2026-10-01T00:30:00')).toBe('2026-10-01 00:30')
    expect(formatShanghaiMovementTime('invalid')).toBe('-')
  })
})
