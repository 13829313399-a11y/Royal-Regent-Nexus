import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { mount, type VueWrapper } from '@vue/test-utils'
import { h, ref } from 'vue'
import { collaborativeSheetsApi as api, type FillChange, type FillTaskDetail, type SyncDelta } from '@/api/collaborativeSheets'
import { useSheetSync } from './useSheetSync'

const makeTask = (): FillTaskDetail => ({ id: 't', factory_id: 'huaxing', title: 'test', original_name: 'test.xlsx', format: 'xlsx', owner_user_id: 'a', owner_name: 'A', is_owner: true, revision: 1, status: 'open', created_at: '', updated_at: '', grants: [], submissions: [], activity: [], editable_ranges: [{ sheet: 0, range: 'A1:C3' }], workbook: { warnings: [], sheets: [{ index: 0, name: '表', rows: 3, columns: 3, merges: [], row_heights: {}, column_widths: {}, cells: [{ address: 'A1', row: 0, column: 0, value: 0, display: '0', formula: false, style: {} }] }] } })
const delta = (revision: number, value: number, applied = revision): SyncDelta => ({ id: 't', revision, applied_revision: applied, status: 'open', grants: [], editable_ranges: [{ sheet: 0, range: 'A1:C3' }], overrides: null, events: [{ id: `e${revision}`, actor_name: 'B', action: 'cells_saved', revision, created_at: '', detail: { changes: [{ sheet: 0, address: 'A1', before: 0, after: value }] } }] })
let wrapper: VueWrapper, sync: ReturnType<typeof useSheetSync>
let task = ref<FillTaskDetail>(), changes = ref<FillChange[]>([])
function start() {
  task = ref(makeTask()); changes = ref([])
  wrapper = mount({ setup() { sync = useSheetSync(task, changes, () => 'huaxing', () => 'a'); sync.start(); return () => h('div') } })
}
function edit(value: number, address = 'A1') { changes.value = sync.stage([{ sheet: 0, address, value }]) }
beforeEach(() => { vi.useFakeTimers(); sessionStorage.clear(); vi.spyOn(api, 'changes').mockResolvedValue(delta(1, 0)); vi.spyOn(api, 'sync').mockResolvedValue(delta(2, 1)) })
afterEach(() => { wrapper?.unmount(); vi.useRealTimers(); vi.restoreAllMocks(); sessionStorage.clear() })

describe('cell reconciliation', () => {
  it('allows correcting a definitive validation rejection with a new command', async () => {
    vi.mocked(api.sync).mockRejectedValueOnce({ response: { status: 422, data: { detail: 'XLS 行块过大' } } })
    start(); edit(7); await sync.flush()
    const rejectedId = vi.mocked(api.sync).mock.calls[0]![2].operation_id
    expect(sync.blocked.value).toBe(false)
    await vi.advanceTimersByTimeAsync(6000); expect(api.sync).toHaveBeenCalledTimes(1)
    edit(1); await sync.flush()
    expect(vi.mocked(api.sync).mock.calls[1]![2].operation_id).not.toBe(rejectedId)
    expect(changes.value).toHaveLength(0)
  })
  it('captures the edit-start value even if another author saves while the editor is open', async () => {
    start(); sync.begin({ sheet: 0, address: 'A1' })
    vi.mocked(api.changes).mockResolvedValue(delta(2, 5)); await sync.pull()
    edit(7); await sync.flush()
    expect(vi.mocked(api.sync).mock.calls[0]![2].changes[0]).toMatchObject({ base_value: 0, base_revision: 1, value: 7 })
  })
  it('retains newer typing and explicit undo while an acknowledgment is in flight', async () => {
    let acknowledge!: (d: SyncDelta) => void
    vi.mocked(api.sync).mockReturnValueOnce(new Promise(resolve => { acknowledge = resolve }))
    start(); edit(1); const first = sync.flush(); edit(0)
    acknowledge(delta(2, 1)); await first
    expect(changes.value).toEqual([{ sheet: 0, address: 'A1', value: 0 }])
    await sync.flush()
    expect(vi.mocked(api.sync).mock.calls[1]![2].changes[0]).toMatchObject({ base_value: 1, base_revision: 2, value: 0 })
  })
  it('retries identical commands after a lost response and does not rebase newer typing over another author', async () => {
    vi.mocked(api.sync).mockRejectedValueOnce(new Error('lost ack')).mockResolvedValueOnce(delta(3, 3, 2))
    start(); edit(1); await sync.flush(); edit(2); await sync.flush()
    expect(vi.mocked(api.sync).mock.calls[1]![2]).toEqual(vi.mocked(api.sync).mock.calls[0]![2])
    await sync.flush()
    expect(vi.mocked(api.sync).mock.calls[2]![2].changes[0]).toMatchObject({ base_value: 1, base_revision: 2, value: 2 })
  })
  it('retains a new active edit baseline when an older staged edit is acknowledged', async () => {
    let acknowledge!: (d: SyncDelta) => void
    vi.mocked(api.sync).mockReturnValueOnce(new Promise(resolve => { acknowledge = resolve }))
    start(); edit(1); const first = sync.flush(); sync.begin({ sheet: 0, address: 'A1' })
    acknowledge(delta(2, 1)); await first
    vi.mocked(api.changes).mockResolvedValue(delta(3, 3)); await sync.pull()
    edit(2); await sync.flush()
    expect(vi.mocked(api.sync).mock.calls[1]![2].changes[0]).toMatchObject({ base_value: 1, base_revision: 2, value: 2 })
  })
  it('keeps conflicts pending when latest data cannot be read', async () => {
    vi.mocked(api.sync).mockRejectedValueOnce({ response: { status: 409, data: { detail: { code: 'cell_conflict', conflicts: [{ sheet: 0, address: 'A1', value: 5, actor_name: 'B', revision: 2 }] } } } })
    start(); edit(7); await sync.flush()
    vi.mocked(api.changes).mockRejectedValue(new Error('offline'))
    await sync.resolve(sync.conflicts.value[0]!, true)
    expect(sync.conflicts.value).toHaveLength(1)
    expect(sync.blocked.value).toBe(false)
    await sync.flush(); expect(api.sync).toHaveBeenCalledTimes(1)
  })
  it('debounces edits, sends only the changed cells and restores an uncertain retry on remount', async () => {
    vi.mocked(api.sync).mockRejectedValue(new Error('offline'))
    start(); edit(1); edit(2)
    await vi.advanceTimersByTimeAsync(700)
    expect(api.sync).toHaveBeenCalledTimes(1)
    const request = vi.mocked(api.sync).mock.calls[0]![2]
    wrapper.unmount(); start(); await sync.flush()
    expect(vi.mocked(api.sync).mock.calls[1]![2]).toEqual(request)
    expect(changes.value[0]?.value).toBe(2)
  })
  it('preserves null baselines after remote updates and does not silently replace them', async () => {
    start(); edit(4, 'B2')
    vi.mocked(api.changes).mockResolvedValue({ ...delta(2, 0), overrides: { '0:B2': 9 } }); await sync.pull()
    await sync.flush()
    expect(vi.mocked(api.sync).mock.calls[0]![2].changes[0]).toMatchObject({ address: 'B2', base_value: null, base_revision: 1 })
  })
  it('requires an explicit same-cell decision and keeps the server conflict revision', async () => {
    vi.mocked(api.sync).mockRejectedValueOnce({ response: { status: 409, data: { detail: { code: 'cell_conflict', conflicts: [{ sheet: 0, address: 'A1', value: 5, actor_name: 'B', revision: 2 }] } } } })
    start(); edit(7); await sync.flush()
    await vi.advanceTimersByTimeAsync(5000)
    expect(api.sync).toHaveBeenCalledTimes(1)
    vi.mocked(api.changes).mockResolvedValue(delta(3, 6))
    await sync.resolve(sync.conflicts.value[0]!, true); await sync.flush()
    expect(vi.mocked(api.sync).mock.calls[1]![2].changes[0]).toMatchObject({ base_value: 5, base_revision: 2, value: 7 })
  })
  it('ignores late success after a task/session boundary', async () => {
    let acknowledge!: (d: SyncDelta) => void
    vi.mocked(api.sync).mockReturnValueOnce(new Promise(resolve => { acknowledge = resolve }))
    start(); edit(1); const saving = sync.flush()
    window.dispatchEvent(new Event('auth-session-boundary-changed'))
    acknowledge(delta(2, 1)); await saving
    expect(task.value!.revision).toBe(1); expect(changes.value).toHaveLength(1); expect(sync.blocked.value).toBe(true)
  })
})
