import { defineComponent, reactive } from 'vue'
import { flushPromises, mount } from '@vue/test-utils'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import { useScheduleMarks } from '../useScheduleMarks'
import type { ScheduleMarksWorkspace } from '@/api/cartonScheduleMarks'

const api = vi.hoisted(() => ({ get: vi.fn() }))
vi.mock('@/api/cartonScheduleMarks', () => ({ cartonScheduleMarksApi: api }))
const response = (factory_id = 'huaxing', batch_id = 'B1'): ScheduleMarksWorkspace => ({ factory_id, batch_id,
  rows: [{ source_sheet: 'ITEM', source_row: 4, status: 'UPLOADED', asset_ids: ['FILE'] }],
  assets: [{ id: 'FILE', file_name: '原箱唛.pdf', usage_status: 'READY' }] })
beforeEach(() => vi.resetAllMocks())

describe('live schedule mark hints', () => {
  it('clears old data and ignores late success/errors across factory, batch and viewer changes', async () => {
    const scope = reactive({ factory: 'huaxing', batch: 'B1', viewer: 'A', enabled: true })
    let first!: (value: ScheduleMarksWorkspace) => void, second!: (reason: Error) => void
    api.get.mockImplementationOnce(() => new Promise(resolve => { first = resolve }))
      .mockImplementationOnce(() => new Promise((_resolve, reject) => { second = reject }))
      .mockResolvedValue(response('huakang-a', 'B2'))
    let state!: ReturnType<typeof useScheduleMarks>
    const wrapper = mount(defineComponent({ setup() { state = useScheduleMarks(() => ({ ...scope })); return () => null } }))
    scope.factory = 'huakang-a'; scope.batch = 'B2'; scope.viewer = 'B'; await flushPromises()
    first(response()); second(new Error('old failure')); await flushPromises()
    expect(state.data.value).toMatchObject({ factory_id: 'huakang-a', batch_id: 'B2' })
    expect(state.error.value).toBe('')
    scope.enabled = false; await flushPromises()
    expect(state.data.value).toBeNull(); expect(state.loading.value).toBe(false)
    wrapper.unmount()
  })
  it('does not treat read failures as missing files and refreshes after focus', async () => {
    api.get.mockRejectedValueOnce(new Error('read failed')).mockResolvedValue(response())
    let state!: ReturnType<typeof useScheduleMarks>
    const wrapper = mount(defineComponent({ setup() { state = useScheduleMarks(() => ({ factory: 'huaxing', batch: 'B1', viewer: 'A', enabled: true })); return () => null } }))
    await flushPromises(); expect(state.error.value).toContain('read failed'); expect(state.find({ sourceSheet: 'ITEM', sourceRow: 4 })).toBeUndefined()
    window.dispatchEvent(new Event('focus')); await flushPromises()
    expect(state.find({ sourceSheet: 'ITEM', sourceRow: 4 })).toMatchObject({ status: 'UPLOADED' })
    wrapper.unmount()
  })
  it('rejects mismatched response scopes and never requests without read permission', async () => {
    const scope = reactive({ factory: 'huaxing', batch: 'B1', viewer: 'A', enabled: false })
    api.get.mockResolvedValue(response('huakang-a'))
    let state!: ReturnType<typeof useScheduleMarks>
    const wrapper = mount(defineComponent({ setup() { state = useScheduleMarks(() => ({ ...scope })); return () => null } }))
    expect(api.get).not.toHaveBeenCalled()
    scope.enabled = true; await flushPromises()
    expect(state.data.value).toBeNull(); expect(state.error.value).toContain('范围')
    wrapper.unmount()
  })
})
