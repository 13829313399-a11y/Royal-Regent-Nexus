import { expect, it, vi } from 'vitest'
const get = vi.hoisted(() => vi.fn().mockResolvedValue({ data: [] }))
vi.mock('@/lib/http', () => ({ http: { get } }))
import { auditParams, getAuditEvents } from '../iam-audit'
it('sends only supported filters and preserves the server wall-time string boundaries', async () => {
  const filters = {
    actor_user_id: 'actor',
    target_user_id: 'person',
    module_code: 'system',
    factory_id: 'f',
    department: 'd',
    from: '2026-09-28T00:00',
    to: '2026-09-28T23:59',
    limit: 200,
  }
  expect(auditParams(filters)).toEqual({
    ...filters,
    from: '2026-09-28 00:00:00',
    to: '2026-09-28 23:59:00',
  })
  await getAuditEvents(filters)
  expect(get).toHaveBeenCalledWith('/iam/audit-events', { params: auditParams(filters) })
})
it('omits empty date boundaries rather than sending invalid timestamps', () => {
  expect(
    auditParams({
      actor_user_id: '',
      target_user_id: '',
      module_code: '',
      factory_id: '',
      department: '',
      from: '',
      to: '',
      limit: 100,
    }),
  ).not.toHaveProperty('from')
})

it('includes same-day stored events using the existing lexical comparison contract', () => {
  const params = auditParams({
    actor_user_id: '',
    target_user_id: '',
    module_code: '',
    factory_id: '',
    department: '',
    from: '2026-09-28T08:00',
    to: '2026-09-28T18:00',
    limit: 100,
  })
  expect('2026-09-28 12:30:00' >= params.from! && '2026-09-28 12:30:00' <= params.to!).toBe(true)
})
