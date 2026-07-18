import { describe, expect, it } from 'vitest'
import {
  BUSINESS_TIME_ZONE,
  formatBusinessDate,
  formatBusinessDateTime,
  parseBusinessTimestamp,
} from '@/lib/dateTime'

describe('business date and time contract', () => {
  it('uses one explicit business timezone', () => {
    expect(BUSINESS_TIME_ZONE).toBe('Asia/Shanghai')
  })

  it('treats legacy timestamps without an offset as Beijing wall time', () => {
    expect(parseBusinessTimestamp('2026-07-18 08:00')).toBe(Date.parse('2026-07-18T00:00:00Z'))
    expect(parseBusinessTimestamp('2026-07-18 08:00:00.123456')).toBe(Date.parse('2026-07-18T00:00:00.123Z'))
    expect(formatBusinessDateTime('2026-07-18 08:00:59', { includeSeconds: true })).toBe('2026-07-18 08:00:59')
  })

  it('converts explicit UTC and offset timestamps to Beijing time', () => {
    expect(formatBusinessDateTime('2026-07-18T00:00:00Z')).toBe('2026-07-18 08:00')
    expect(formatBusinessDateTime('2026-07-18T08:00:00+08:00')).toBe('2026-07-18 08:00')
    expect(formatBusinessDateTime('2026-07-18T18:30:45-05:00', { includeSeconds: true })).toBe('2026-07-19 07:30:45')
    expect(parseBusinessTimestamp('2026-07-18T08:00:00+0800')).toBe(Date.parse('2026-07-18T00:00:00Z'))
  })

  it('keeps date-only values on their original calendar day', () => {
    expect(formatBusinessDate('2026-07-18')).toBe('2026-07-18')
    expect(formatBusinessDateTime('2026-07-18')).toBe('2026-07-18 00:00')
    expect(formatBusinessDate('2026-07-17T16:30:00Z')).toBe('2026-07-18')
  })

  it('uses the requested fallback for empty or invalid values', () => {
    expect(parseBusinessTimestamp('2026-02-30 08:00:00')).toBeNull()
    expect(parseBusinessTimestamp('2026-02-30T08:00:00Z')).toBeNull()
    expect(parseBusinessTimestamp('2026-07-18T24:00:00+08:00')).toBeNull()
    expect(formatBusinessDate('2026-02-30', '日期异常')).toBe('日期异常')
    expect(formatBusinessDateTime('not-a-date', { fallback: '时间异常' })).toBe('时间异常')
    expect(formatBusinessDateTime('')).toBe('-')
  })
})
