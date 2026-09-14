import { describe, expect, it } from 'vitest'
import { workspaceFreshnessLabel } from '../domain/workspaceFreshness'

describe('工作区数据截止时间', () => {
  it('正式模式只显示当前 summary 的服务端时间，未读取时不回落样例时钟', () => {
    expect(workspaceFreshnessLabel(false, '2026-09-13T06:20:00.000Z', null)).toBe('尚未读取')
    expect(workspaceFreshnessLabel(false, '2026-09-13T06:20:00.000Z', '2026-09-14T01:02:00.000Z')).toContain('2026-09-14 09:02')
    expect(workspaceFreshnessLabel(true, '2026-09-13T06:20:00.000Z', '2026-09-14T01:02:00.000Z')).toContain('2026-09-13 14:20')
  })
})
