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
