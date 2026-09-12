// @vitest-environment jsdom
import { beforeEach, describe, expect, it, vi } from 'vitest'
import { createPinia, setActivePinia } from 'pinia'
import { injectionApi } from '@/api/injectionScheduling'
import { useInjectionStore } from '@/stores/injectionScheduling'
import {
  parseValue,
  type FieldSpec,
} from '@/features/injection-scheduling/types'

vi.mock('@/api/injectionScheduling', () => ({
  injectionApi: { get: vi.fn(), query: vi.fn(), post: vi.fn(), patch: vi.fn() },
}))
const api = vi.mocked(injectionApi)
function deferred<T>() {
  let resolve!: (value: T) => void
  const promise = new Promise<T>((r) => (resolve = r))
  return { promise, resolve }
}
const summary = (revision = 1) => ({
  revision,
  shared_revision: revision,
  total_count: 1,
})
const result = (revision = 1) => ({
  ...summary(revision),
  rows: [{ id: 'd-1', revision: 1, mold_code: '001' }],
  next_cursor: null,
  filtered_summary: summary(revision),
})
beforeEach(() => {
  vi.resetAllMocks()
  setActivePinia(createPinia())
  api.get.mockImplementation(async (path) =>
    path === '/summary'
      ? summary()
      : path === '/timeline'
        ? { ...summary(), machines: [], runs: [], events: [] }
        : path === '/field-registry'
          ? { fields: [] }
          : path === '/settings'
            ? { parameters: {} }
            : [],
  )
  api.query.mockResolvedValue(result())
})
describe('injection scheduling synchronization', () => {
  it('reports saved template assignments separately from a no-change import', async () => {
    const store = useInjectionStore()
    await store.setFactory('huaxing')
    api.post.mockResolvedValue({
      revision: 2,
      unified_import: true,
      recalculate_required: false,
      restored_assignment_count: 2,
      summary: { applied_count: 2 },
    })
    await store.mutate('/imports/template/apply', {})
    expect(store.notice).toContain('已按表记录 2 条机台安排')
    expect(store.notice).toContain('等待实际开工')
    api.post.mockResolvedValue({
      revision: 3,
      unified_import: true,
      recalculate_required: false,
      restored_assignment_count: 0,
      summary: { applied_count: 0 },
    })
    await store.mutate('/imports/template2/apply', {})
    expect(store.notice).toBe('导入完成，内容没有变化')
  })
  it('uses a refreshed clear preview revision even while the board stays frozen', async () => {
    const store = useInjectionStore()
    await store.setFactory('huaxing')
    store.dirty = true
    api.post.mockResolvedValue({ revision: 8, cleared: true })
    await store.mutate('/plan-data/clear', { expected_revision: 7 })
    expect(api.post.mock.calls.at(-1)![1]).toMatchObject({
      base_revision: 7,
      expected_revision: 7,
    })
  })
  it('resets cleared context before reload and discards an older page response', async () => {
    const store = useInjectionStore()
    await store.setFactory('huaxing')
    store.selectedId = 'd-1'
    store.drawer = true
    store.detail = { demand: { id: 'd-1' } }
    store.filter = { field: 'mold_code', op: 'eq', value: 'OLD' }
    store.search.text = 'OLD'
    store.cursor = 200
    store.nextCursor = 300
    const old = deferred<any>()
    api.query.mockReturnValueOnce(old.promise)
    const oldRequest = store.loadTable()
    api.post.mockResolvedValue({ revision: 2, cleared: true })
    api.get.mockImplementation(async (path) =>
      path === '/summary'
        ? { ...summary(2), total_count: 0 }
        : { ...summary(2), machines: [], runs: [], events: [] },
    )
    api.query.mockResolvedValue({ ...result(2), rows: [], total_count: 0 })
    api.get.mockClear()
    await store.mutate('/plan-data/clear', { expected_revision: 1 })
    old.resolve(result(1))
    await oldRequest
    expect(store.rows).toEqual([])
    expect(store.total).toBe(0)
    expect(store.selectedId).toBeNull()
    expect(store.detail).toBeNull()
    expect(store.drawer).toBe(false)
    expect(store.filter).toBeNull()
    expect(store.search.text).toBe('')
    expect(store.cursor).toBe(0)
    expect(store.nextCursor).toBeNull()
    expect(
      api.get.mock.calls.some(([path]) => path.startsWith('/demands/')),
    ).toBe(false)
    expect(store.notice).toContain('可以重新导入 Excel')
  })
  it('preserves data on an uncertain clear and retries the identical operation', async () => {
    const store = useInjectionStore()
    await store.setFactory('huaxing')
    store.selectedId = 'd-1'
    store.dirty = true
    const data = { expected_revision: 1, preview_token: 'a'.repeat(64) }
    api.post.mockRejectedValueOnce(new Error('Network Error'))
    expect(await store.mutate('/plan-data/clear', data)).toBeNull()
    expect(store.rows).toHaveLength(1)
    expect(store.selectedId).toBe('d-1')
    expect(store.dirty).toBe(true)
    const payload = api.post.mock.calls.at(-1)![1]
    store.revision = 9
    api.post.mockResolvedValue({ revision: 2, cleared: true })
    await store.mutate('/plan-data/clear', data)
    expect(api.post.mock.calls.at(-1)![1]).toEqual(payload)
  })
  it('reuses the exact operation after an uncertain network result instead of duplicating creation', async () => {
    const store = useInjectionStore()
    await store.setFactory('huaxing')
    api.post.mockRejectedValueOnce(new Error('Network Error'))
    await store.mutate('/demands', { data: { mold_code: 'RETRY-001' } })
    const first = api.post.mock.calls.at(-1)![1]
    store.revision = 9
    api.post.mockResolvedValueOnce({ revision: 2 })
    await store.mutate('/demands', { data: { mold_code: 'RETRY-001' } })
    expect(api.post.mock.calls.at(-1)![1]).toEqual(first)
  })
  it('uses the reviewed bulk-start revision and reuses the operation after a network failure', async () => {
    const store = useInjectionStore()
    await store.setFactory('huaxing')
    store.dirty = true
    const data = {
      expected_revision: 30,
      confirm_actual_start: true,
      items: [{ machine_id: 'm1', run_id: 'r1', review_token: 'a'.repeat(64) }],
    }
    api.post.mockRejectedValueOnce(new Error('Network Error'))
    await store.mutate('/execution/bulk-start', data)
    const first = api.post.mock.calls.at(-1)![1]
    expect(first).toMatchObject({ base_revision: 30 })
    store.revision = 99
    api.post.mockResolvedValueOnce({
      revision: 31,
      bulk_start: true,
      started_count: 1,
      failed_count: 0,
    })
    await store.mutate('/execution/bulk-start', data)
    expect(api.post.mock.calls.at(-1)![1]).toEqual(first)
    expect(store.notice).toBe('已开工 1 台；0 台未开工')
  })
  it('keeps the neutral factory empty without loading a fallback factory', async () => {
    const store = useInjectionStore()
    await store.setFactory(null)
    expect(store.factory).toBeNull()
    expect(api.query).not.toHaveBeenCalled()
    expect(api.get).not.toHaveBeenCalled()
  })
  it('discards a query from the previous factory after switching', async () => {
    const store = useInjectionStore()
    await store.setFactory('huaxing')
    const old = deferred<any>()
    api.query.mockReturnValueOnce(old.promise)
    const pending = store.loadTable()
    await store.setFactory('huadeng')
    old.resolve({ ...result(), rows: [{ id: 'wrong-factory', revision: 1 }] })
    await pending
    expect(store.factory).toBe('huadeng')
    expect(store.rows.some((r) => r.id === 'wrong-factory')).toBe(false)
  })
  it('preserves input when an already pending refresh completes after editing starts', async () => {
    const store = useInjectionStore()
    await store.setFactory('huaxing')
    const slow = deferred<any>()
    api.get.mockImplementationOnce(() => slow.promise)
    const pending = store.refresh()
    store.dirty = true
    slow.resolve({ ...summary(), total_count: 999 })
    await pending
    expect(store.summary.total_count).toBe(1)
    expect(store.dirty).toBe(true)
    expect(store.stale).toBe(true)
  })
  it('does not allow an older refresh to overwrite a newer revision', async () => {
    const store = useInjectionStore()
    await store.setFactory('huaxing')
    const slow = deferred<any>()
    api.get.mockImplementationOnce(() => slow.promise)
    const first = store.refresh()
    api.get.mockImplementation(async (path) =>
      path === '/summary'
        ? summary(3)
        : { ...summary(3), machines: [], runs: [], events: [] },
    )
    api.query.mockResolvedValue(result(3))
    await store.refresh()
    slow.resolve(summary(1))
    await first
    expect(store.revision).toBe(3)
  })
  it('retains dirty input and stale status on a write conflict', async () => {
    const store = useInjectionStore()
    await store.setFactory('huaxing')
    store.dirty = true
    api.patch.mockRejectedValue(new Error('版本冲突'))
    expect(
      await store.mutate(
        '/demands/d-1',
        { data: { planned_shots: 250 } },
        'patch',
      ),
    ).toBeNull()
    expect(store.dirty).toBe(true)
    expect(store.stale).toBe(true)
    expect(store.error).toContain('版本冲突')
  })
  it('does not label a scheduling preview as saved', async () => {
    const store = useInjectionStore()
    await store.setFactory('huaxing')
    api.post.mockResolvedValue({ ...summary(), unplaced: [] })
    await store.mutate('/schedule/auto', { save: false })
    expect(store.notice).toContain('尚未保存')
  })
  it('keeps leading-zero text and rejects invalid numeric/date paste values', () => {
    const field = {
      key: 'mold_code',
      label: '模号',
      value_type: 'text',
    } as FieldSpec
    expect(parseValue('001-01', field)).toBe('001-01')
    expect(() =>
      parseValue('1.5', { ...field, value_type: 'integer' }),
    ).toThrow()
    expect(() =>
      parseValue('不是日期', { ...field, value_type: 'datetime' }),
    ).toThrow()
    expect(parseValue('0', { ...field, value_type: 'integer' })).toBe(0)
    expect(parseValue('', { ...field, value_type: 'integer' })).toBeNull()
  })
})
