import { describe, expect, it, vi } from 'vitest'
import { effectScope, nextTick, ref } from 'vue'
import { flushPromises } from '@vue/test-utils'
import { useCartonMovementHistory } from '../useCartonMovementHistory'
import type { CartonMovementHistoryPage, CartonMovementHistoryQuery } from '@/api/cartonMovementHistory'

const api = vi.hoisted(() => ({ list: vi.fn() }))
vi.mock('@/api/cartonMovementHistory', () => ({ cartonMovementHistoryApi: api }))

function page(factory = 'huaxing', total = 507, id = 'old-document'): CartonMovementHistoryPage {
  return { factory_id: factory, total, limit: 100, offset: 0, items: [{ id, is_reversed: true }] as CartonMovementHistoryPage['items'] }
}

function open(query: () => CartonMovementHistoryQuery | null, refreshKey?: () => unknown) {
  const scope = effectScope()
  const result = scope.run(() => useCartonMovementHistory(query, refreshKey))!
  return { ...result, stop: () => scope.stop() }
}

describe('paged carton movement history', () => {
  it('passes every server filter and offset instead of limiting browser search to 500 rows', async () => {
    api.list.mockResolvedValue(page())
    const query = ref<CartonMovementHistoryQuery>({ factory_id: 'huaxing', customer_code: 'C1', search: 'OLD', movement_type: 'OUTBOUND', date_from: '2026-09-01', date_to: '2026-09-30', limit: 100, offset: 500 })
    const history = open(() => query.value)
    await flushPromises()
    expect(api.list.mock.lastCall?.[0]).toEqual(query.value)
    expect(history.total.value).toBe(507)
    expect(history.items.value[0]?.is_reversed).toBe(true)
    query.value = { ...query.value, offset: 600 }
    await nextTick(); await flushPromises()
    expect(api.list.mock.lastCall?.[0].offset).toBe(600)
    history.stop()
  })

  it('invalidates old success and error responses when account or factory changes', async () => {
    let resolveOld!: (value: CartonMovementHistoryPage) => void
    api.list.mockImplementationOnce(() => new Promise(resolve => { resolveOld = resolve }))
    const query = ref<CartonMovementHistoryQuery | null>({ factory_id: 'huaxing' })
    const identity = ref('old-account')
    const history = open(() => query.value, () => identity.value)
    api.list.mockResolvedValueOnce(page('huakang-a', 1, 'new-document'))
    query.value = { factory_id: 'huakang-a' }; identity.value = 'new-account'
    await nextTick(); await flushPromises()
    resolveOld(page()); await flushPromises()
    expect(history.items.value[0]?.id).toBe('new-document')
    expect(history.total.value).toBe(1)
    let rejectOld!: (reason: Error) => void
    api.list.mockImplementationOnce(() => new Promise((_, reject) => { rejectOld = reject }))
    void history.reload()
    query.value = null
    await nextTick()
    rejectOld(new Error('old failure')); await flushPromises()
    expect(history.items.value).toEqual([])
    expect(history.error.value).toBe('')
    expect(history.loading.value).toBe(false)
    history.stop()
  })

  it('shows failures distinctly and keeps the current filters available for retry', async () => {
    api.list.mockRejectedValueOnce(new Error('暂时无法查询'))
    const history = open(() => ({ factory_id: 'huaxing', search: 'OLD' }))
    await flushPromises()
    expect(history.error.value).toBe('暂时无法查询')
    expect(history.items.value).toEqual([])
    api.list.mockResolvedValueOnce(page())
    await history.reload()
    expect(history.error.value).toBe('')
    expect(history.total.value).toBe(507)
    history.stop()
  })

  it('does not publish a late result after the history scope is closed', async () => {
    let finish!: (value: CartonMovementHistoryPage) => void
    api.list.mockImplementationOnce(() => new Promise(resolve => { finish = resolve }))
    const history = open(() => ({ factory_id: 'huaxing' }))
    history.stop()
    finish(page()); await flushPromises()
    expect(history.items.value).toEqual([])
  })
})
