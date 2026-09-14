import { describe, expect, it } from 'vitest'
import type { UvShiftTemplate } from '../contracts'
import { effectiveShiftTemplateFor } from '../domain/shiftTemplates'

const template = (id: string, effective_from: string, version: number): UvShiftTemplate => ({
  id, factory_id: 'huakang-a', version, created_at: '2026-01-01T00:00:00Z', updated_at: '2026-01-01T00:00:00Z',
  label: id, shift: 'day', effective_from, effective_to: null, start_local: '07:40', end_local: '21:00', break_minutes: 0, note: '',
})

describe('有效班次模板', () => {
  it('报工使用服务端当前生效版本的 ID，不写死本地模板 ID', () => {
    const selected = effectiveShiftTemplateFor([
      template('server-v1', '2026-01-01', 1),
      template('server-v2', '2026-09-01', 2),
    ], 'day', '2026-09-14')

    expect(selected?.id).toBe('server-v2')
  })
})
