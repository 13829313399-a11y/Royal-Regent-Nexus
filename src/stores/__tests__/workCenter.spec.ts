import { createPinia, setActivePinia } from 'pinia'
import { flushPromises } from '@vue/test-utils'
import { beforeEach, afterEach, describe, expect, it, vi } from 'vitest'
import { useWorkCenterStore } from '@/stores/workCenter'
import { useAuthStore } from '@/stores/auth'
import type { AuthMeResponse } from '@/api/auth'
import type { WorkEntry, WorkSnapshot } from '@/features/work-center/types'
import { entryRoute } from '@/features/work-center/routes'

const api = vi.hoisted(() => ({ snapshot: vi.fn(), entry: vi.fn(), patch: vi.fn(), batch: vi.fn(), preferences: vi.fn(), savePreferences: vi.fn() }))
vi.mock('@/api/workCenter', () => ({ workCenterApi: api }))
const entry = (id = 'first'): WorkEntry => ({ id, kind: 'task', module: 'molding', title: '审核啤办单', summary: '测试', reference_label: id,
  lifecycle: 'open', viewer_relation: 'assignee', source_factory: { id: 'huakang-c', label: '华康C' }, execution_factory: { id: 'huakang-a', label: '华康A' },
  department_label: '工程', stage_label: '审核', responsible_label: '本人', why_me: '当前责任人', priority: 'normal', priority_reasons: [], due_at: null,
  due_source: null, opened_at: '2026-09-28T02:00:00Z', can_act_now: true, unavailable_reason: null, verification_state: 'verified', resolution_reason: null,
  content_version: 1, attention_version: 1, personal: { read_state: 'unread', snoozed_until: null, archived_at: null, pinned: false, state_version: 0 },
  actions: [{ key: 'open', label: '审核', mode: 'navigate', enabled: true, disabled_reason: null, target: { route_key: 'molding_production', params: { id }, query: { factory: 'huakang-a' } } }] })
const snap = (items: WorkEntry[] = [entry()]): WorkSnapshot => ({
  context: { viewer_key: 'A', scope_key: 'authorized', server_time: '2026-09-28T02:00:00Z', business_timezone: 'Asia/Shanghai', authz_recheck_at: null },
  summary: { actionable_total: items.length, assigned_total: items.length, team_queue_total: 0, focus_total: items.length, snoozed_total: 0, overdue_total: 0, info_unread_total: 0, waiting_total: 0, verification_required_total: 0 },
  query: { filtered_total: items.length, cursor: null }, items, next_cursor: null, selected_entry_state: null,
  health: { status: 'fresh', as_of: '2026-09-28T02:00:00Z', unavailable_sources: [], coverage: [] },
})
function account(id: string) { useAuthStore().$patch({ currentUser: { id, identity: { effective_context_key: id, employment_epoch: 1 } } as AuthMeResponse }) }
let center: ReturnType<typeof useWorkCenterStore>
beforeEach(() => {
  setActivePinia(createPinia()); vi.clearAllMocks(); localStorage.clear(); account('A'); center = useWorkCenterStore()
  api.snapshot.mockImplementation(async () => snap()); api.preferences.mockResolvedValue({ sound_enabled: false, toast_level: 'assigned', version: 1 })
})
afterEach(() => { center.stop(); vi.useRealTimers() })

describe('shared work center', () => {
  it('is silent at baseline, replaces finished entries and preserves stale data on network failure', async () => {
    await center.refresh(); expect(center.toasts).toEqual([])
    api.snapshot.mockResolvedValue(snap([])); await center.refresh(true)
    expect(center.count).toBe(0); expect(center.snapshot?.items).toEqual([])
    api.snapshot.mockRejectedValue(new Error('offline')); await center.refresh(true)
    expect(center.snapshot?.health.status).toBe('stale'); expect(center.error).toBeTruthy()
  })
  it('discards a late list and information response from the prior account', async () => {
    let resolve!: (value: WorkSnapshot) => void
    api.snapshot.mockImplementation(() => new Promise<WorkSnapshot>(done => { resolve = done }))
    const info = center.loadInformation(); account('B'); resolve(snap()); await info
    expect(center.information).toEqual([])
    account('A'); let resolvers: ((value: WorkSnapshot) => void)[] = []
    api.snapshot.mockImplementation(() => new Promise<WorkSnapshot>(done => resolvers.push(done)))
    const request = center.refresh(); account('B'); resolvers.forEach(done => done(snap())); await request
    expect(center.snapshot).toBeNull()
  })
  it('clears sensitive detail, toasts and info immediately on forbidden refresh', async () => {
    await center.refresh(); center.selected = entry(); center.toasts = [entry()]; center.information = [entry()]
    api.snapshot.mockRejectedValue({ response: { status: 403 } }); await center.refresh()
    expect(center.selected).toBeNull(); expect(center.snapshot).toBeNull(); expect(center.toasts).toEqual([]); expect(center.information).toEqual([])
  })
  it('invalidates late detail and info when the server revokes scope for the same account', async () => {
    await center.refresh()
    let resolveDetail!: (item: WorkEntry) => void, resolveInfo!: (value: WorkSnapshot) => void
    api.entry.mockImplementation(() => new Promise<WorkEntry>(done => { resolveDetail = done }))
    api.snapshot.mockImplementation(() => new Promise<WorkSnapshot>(done => { resolveInfo = done }))
    const detail = center.selectEntry('first'), info = center.loadInformation()
    const revised = snap([]); revised.context.viewer_key = 'revoked'
    api.snapshot.mockResolvedValue(revised); await center.refresh()
    resolveDetail(entry()); resolveInfo(snap()); await Promise.all([detail, info])
    expect(center.selected).toBeNull(); expect(center.information).toEqual([]); expect(api.patch).not.toHaveBeenCalled()
  })
  it('uses the workspace snapshot summary with its rows even when the separate bell changes', async () => {
    center.workspaceOpen = true
    api.snapshot.mockResolvedValueOnce(snap([])).mockResolvedValueOnce(snap())
    await center.refresh(); expect(center.count).toBe(0); expect(center.snapshot?.query.filtered_total).toBe(0)
  })
  it('only acknowledges the version opened by the viewer', async () => {
    api.entry.mockResolvedValue(entry()); api.patch.mockResolvedValue(entry())
    await center.selectEntry('first')
    expect(api.patch).toHaveBeenCalledWith('first', { observed_content_version: 1 })
  })
  it('keeps the current row position during typing or deep reading until explicit refresh', async () => {
    center.workspaceOpen = true; center.workspaceEngaged = true
    await center.refresh()
    api.snapshot.mockImplementation(async () => snap([entry('new'), entry()]))
    await center.refresh(true)
    expect(center.snapshot?.items.map(x => x.id)).toEqual(['first'])
    expect(center.pendingRefresh).toBe(true)
    await center.refresh()
    expect(center.snapshot?.items.map(x => x.id)).toEqual(['new', 'first'])
  })
  it('claims new attention once across shared storage while ordinary refresh is silent', async () => {
    await center.refresh(); api.snapshot.mockResolvedValue(snap([entry('new')]))
    await center.refresh(true); expect(center.toasts.map(x => x.id)).toEqual(['new'])
    await center.refresh(true); expect(center.toasts).toHaveLength(1)
    center.clear(); await center.refresh(true); expect(center.toasts).toEqual([])
  })
  it('keeps one scheduler for repeated host starts and stops cleanly', async () => {
    vi.useFakeTimers(); Object.defineProperty(document, 'hidden', { configurable: true, value: false })
    center.start(); center.start(); await flushPromises()
    expect(api.snapshot).toHaveBeenCalledTimes(2)
    await vi.advanceTimersByTimeAsync(25_000); expect(api.snapshot).toHaveBeenCalledTimes(4)
    center.stop(); await vi.advanceTimersByTimeAsync(100_000); expect(api.snapshot).toHaveBeenCalledTimes(4)
  })
  it('replaces stale work after more than five minutes of failed polling', async () => {
    vi.useFakeTimers(); Object.defineProperty(document, 'hidden', { configurable: true, value: false })
    center.start(); await flushPromises(); expect(center.count).toBe(1)
    api.snapshot.mockRejectedValue(new Error('temporary server failure'))
    await vi.advanceTimersByTimeAsync(360_000)
    expect(center.snapshot?.health.status).toBe('stale'); expect(center.count).toBe(1)
    api.snapshot.mockImplementation(async () => snap([]))
    window.dispatchEvent(new Event('online')); await flushPromises()
    expect(center.snapshot?.health.status).toBe('fresh'); expect(center.count).toBe(0)
    expect(center.snapshot?.items).toEqual([]); expect(center.toasts).toEqual([])
  })
  it('batch reading sends only observed entries while a new message arrives', async () => {
    await center.refresh()
    let finish!: (value: { results: unknown[] }) => void
    api.batch.mockImplementation(() => new Promise(done => { finish = done }))
    const reading = center.markVisibleRead()
    api.snapshot.mockImplementation(async () => snap([entry(), entry('arrived-later')]))
    finish({ results: [] }); await reading
    expect(api.batch).toHaveBeenCalledWith([{ id: 'first', observed_content_version: 1 }])
    expect(center.snapshot?.items.find(x => x.id === 'arrived-later')?.personal.read_state).toBe('unread')
  })
  it('routes only allowlisted actions and includes the real source id', () => {
    expect(entryRoute(entry())).toMatchObject({ query: { order_id: 'first', factory: 'huakang-a' } })
    const bad = entry(); bad.actions[0]!.target!.route_key = 'https://outside.test'; expect(entryRoute(bad)).toBeNull()
  })
})
