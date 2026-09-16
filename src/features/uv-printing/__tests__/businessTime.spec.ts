import { describe, expect, it } from 'vitest'
import { shiftMembership } from '../domain/businessTime'

describe('上海 UV 业务日期边界', () => {
  it('07:40 前仍归前一日夜班，07:40 起归当日白班', () => {
    expect(shiftMembership('2026-09-13T23:39:59.000Z')).toMatchObject({
      business_date: '2026-09-13', shift: 'night',
    })
    expect(shiftMembership('2026-09-13T23:40:00.000Z')).toMatchObject({
      business_date: '2026-09-14', shift: 'day',
    })
  })

  it('月界夜班按班次开始日归属，不被客户端 UTC 日期切到下一月', () => {
    expect(shiftMembership('2026-09-30T23:39:59.000Z')).toMatchObject({
      business_date: '2026-09-30', shift: 'night',
    })
    expect(shiftMembership('2026-09-30T23:40:00.000Z')).toMatchObject({
      business_date: '2026-10-01', shift: 'day',
    })
  })
})
