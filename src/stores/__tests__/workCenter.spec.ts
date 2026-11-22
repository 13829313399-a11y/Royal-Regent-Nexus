import { createPinia, setActivePinia } from 'pinia'
import { flushPromises } from '@vue/test-utils'
import { beforeEach, afterEach, describe, expect, it, vi } from 'vitest'
import { useWorkCenterStore } from '@/stores/workCenter'
import { useAuthStore } from '@/stores/auth'
import type { AuthMeResponse } from '@/api/auth'
import type { WorkEntry, WorkSnapshot } from '@/features/work-center/types'
import { entryRoute } from '@/features/work-center/routes'
import { entry, snap } from '@/features/work-center/__tests__/fixtures'

const api = vi.hoisted(() => ({ snapshot: vi.fn(), entry: vi.fn(), patch: vi.fn(), batch: vi.fn(), preferences: vi.fn(), savePreferences: vi.fn() }))
vi.mock('@/api/workCenter', () => ({ workCenterApi: api }))
function account(id: string) { useAuthStore().$patch({ currentUser: { id, identity: { effective_context_key: id, employment_epoch: 1 } } as AuthMeResponse }) }
let center: ReturnType<typeof useWorkCenterStore>
beforeEach(() => {
  setActivePinia(createPinia()); vi.clearAllMocks(); localStorage.clear(); account('A'); center = useWorkCenterStore()
  api.snapshot.mockImplementation(async () => snap()); api.preferences.mockResolvedValue({ sound_enabled: false, toast_level: 'assigned', version: 1 })
})
afterEach(() => { center.stop(); vi.useRealTimers() })

describe('shared work center', () => {
  it('reuses the first unfiltered page for the bell and normalizes an untrusted factory query', async () => {
    center.workspaceOpen = true
    api.snapshot.mockResolvedValue(snap(Array.from({length:12}, (_,i)=>entry(String(i)))))
    await center.setQuery({factory_scope:'group'})
    expect(api.snapshot).toHaveBeenCalledTimes(1)
    expect(api.snapshot.mock.calls[0]![0].factory_scope).toBe('authorized')
    expect(center.snapshot?.items).toHaveLength(12)
    expect(center.bell?.items).toHaveLength(8)
    await center.setQuery({factory_scope:'huaxing'})
    expect(api.snapshot).toHaveBeenCalledTimes(3)
  })
  it('rejects mixed live-task archives and snoozes only eligible observed versions', async () => {
    await center.refresh()
    const task=entry(), info={...entry('notice'),kind:'info' as const,can_act_now:false}
    await center.batchPatch([task,info],'archive')
    expect(api.batch).not.toHaveBeenCalled()
    api.batch.mockResolvedValue({results:[{id:task.id,status:'error',message:'版本已变化'}]})
    const until='2030-01-01T12:00:00Z'
    expect(await center.batchPatch([task,info],'snooze',until)).toEqual([task.id])
    expect(api.batch).toHaveBeenCalledWith([{id:task.id,state_version:0,snoozed_until:until}])
    expect(center.feedback).toContain('1 项未成功 · 版本已变化')
    api.batch.mockResolvedValue({results:[{id:info.id,status:'ok'}]})
    await center.batchPatch([info],'archive')
    expect(api.batch).toHaveBeenLastCalledWith([{id:info.id,state_version:0,archived:true}])
  })
  it('clears cached information when a personal write loses access', async () => {
    await center.refresh()
    center.selected=entry();center.information=[entry()]
    api.patch.mockRejectedValueOnce({response:{status:403}})
    await center.patch(entry(),{pinned:true,state_version:0})
    expect(center.bell).toBeNull();expect(center.snapshot).toBeNull();expect(center.selected).toBeNull()
    expect(center.information).toEqual([]);expect(center.personalBusy).toBe(false)
  })
  it('is silent at baseline, replaces finished entries and preserves stale data on network failure', async () => {
    await center.refresh(); expect(center.toasts).toEqual([])
    api.snapshot.mockResolvedValue(snap([])); await center.refresh(true)
    expect(center.count).toBe(0); expect(center.snapshot?.items).toEqual([])
    api.snapshot.mockRejectedValue(new Error('offline')); await center.refresh(true)
    expect(center.snapshot?.health.status).toBe('stale'); expect(center.bell?.health.status).toBe('stale'); expect(center.error).toBeTruthy()
  })
  it.each([401, 403])('clears denied data and recovers automatically after a %i write', async (status) => {
    vi.useFakeTimers()
    Object.defineProperty(document, 'hidden', { configurable: true, value: false })
    center.start()
    await flushPromises()
    api.patch.mockRejectedValueOnce({ response: { status } })
    await center.patch(entry(), { pinned: true, state_version: 0 })
    expect(center.bell).toBeNull()
    api.snapshot.mockRejectedValueOnce({ response: { status } })
    await vi.advanceTimersByTimeAsync(49_999)
    expect(api.snapshot).toHaveBeenCalledTimes(1)
    await vi.advanceTimersByTimeAsync(1)
    expect(center.bell).toBeNull()
    api.snapshot.mockResolvedValue(snap([entry('restored')]))
    await vi.advanceTimersByTimeAsync(100_000)
    expect(center.bell?.items.map(item => item.id)).toEqual(['restored'])
    expect(center.toasts).toEqual([])
    expect(center.error).toBe('')
  })
  it.each(['batch', 'refresh'])('drops a late %s response when the host stops and restarts', async (phase) => {
    const channels: { postMessage: ReturnType<typeof vi.fn>; close: ReturnType<typeof vi.fn> }[] = []
    vi.stubGlobal('BroadcastChannel', class {
      postMessage = vi.fn()
      close = vi.fn()
      constructor() { channels.push(this) }
    })
    try {
      center.start()
      await flushPromises()
      let finish!: () => void
      const pending = new Promise<void>(resolve => { finish = resolve })
      api.batch.mockImplementationOnce(async () => {
        if (phase === 'batch') await pending
        return { results: [] }
      })
      if (phase === 'refresh') api.snapshot.mockImplementationOnce(async () => { await pending; return snap() })
      const writing = center.markVisibleRead()
      await flushPromises()
      center.stop()
      center.start()
      await flushPromises()
      const calls = api.snapshot.mock.calls.length
      finish()
      expect(await writing).toBeUndefined()
      expect(api.snapshot).toHaveBeenCalledTimes(calls)
      expect(channels[0]!.close).toHaveBeenCalledOnce()
      for (const channel of channels) expect(channel.postMessage).not.toHaveBeenCalled()
      expect(center.personalBusy).toBe(false)
      expect(center.feedback).toBe('')
    } finally { center.stop(); vi.unstubAllGlobals() }
  })
  it('restores saved preferences after denial before allowing new background toasts', async () => {
    const muted = { sound_enabled: true, toast_level: 'none', version: 4, business_timezone: 'Asia/Shanghai' }
    api.preferences.mockResolvedValue(muted)
    center.start()
    await flushPromises()
    expect(center.preferences).toEqual(muted)
    api.patch.mockRejectedValueOnce({ response: { status: 403 } })
    await center.patch(entry(), { pinned: true, state_version: 0 })
    expect(center.preferences.sound_enabled).toBe(false)
    expect(api.preferences).toHaveBeenCalledTimes(1)
    api.preferences.mockRejectedValueOnce(new Error('offline'))
    await center.refresh(true)
    await flushPromises()
    expect(center.bell).not.toBeNull()
    let restore!: (value: typeof muted) => void
    api.preferences.mockImplementationOnce(() => new Promise(done => { restore = done }))
    api.snapshot.mockResolvedValue(snap([entry('during-recovery')]))
    await center.refresh(true)
    api.snapshot.mockResolvedValue(snap([entry('still-recovering')]))
    await center.refresh(true)
    expect(api.preferences).toHaveBeenCalledTimes(3)
    expect(center.toasts).toEqual([])
    restore(muted)
    await flushPromises()
    expect(center.preferences).toEqual(muted)
    api.snapshot.mockResolvedValue(snap([entry('after-recovery')]))
    await center.refresh(true)
    expect(center.toasts).toEqual([])
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
    center.query.module = 'position_reviews'
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
    expect(api.snapshot).toHaveBeenCalledTimes(1)
    expect(api.snapshot.mock.calls[0]![0]).toEqual({view:'todo',limit:8})
    await vi.advanceTimersByTimeAsync(25_000); expect(api.snapshot).toHaveBeenCalledTimes(2)
    center.stop(); await vi.advanceTimersByTimeAsync(100_000); expect(api.snapshot).toHaveBeenCalledTimes(2)
  })
  it('preserves initial workspace URL filters when the host starts later, then resets them for another account', async () => {
    center.workspaceOpen = true
    await center.setQuery({ view: 'verification', module: 'internal_quote' })
    center.start(); await flushPromises()
    expect(center.query.view).toBe('verification'); expect(center.query.module).toBe('internal_quote')
    account('B'); await flushPromises()
    expect(center.query.view).toBe('todo'); expect(center.query.module).toBe('')
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
  it('refreshes the visible info tab and isolates its loading and failure from tasks', async () => {
    await center.refresh(); center.panelOpen = true; center.panelTab = 'info'
    let finish!: (value: WorkSnapshot) => void
    api.snapshot.mockImplementation(query => query.view === 'info' ? new Promise<WorkSnapshot>(done => { finish = done }) : Promise.resolve(snap()))
    const pending = center.refresh(); await flushPromises()
    expect(center.informationLoading).toBe(true); expect(center.informationLoaded).toBe(false)
    finish(snap([entry('info-new')])); await pending
    expect(center.information.map(x => x.id)).toEqual(['info-new'])
    expect(center.informationLoading).toBe(false); expect(center.informationLoaded).toBe(true)
    api.snapshot.mockImplementation(query => query.view === 'info' ? Promise.reject(new Error('info offline')) : Promise.resolve(snap()))
    await center.refresh()
    expect(center.error).toBe(''); expect(center.informationError).toBeTruthy()
    expect(center.information.map(x => x.id)).toEqual(['info-new'])
    api.snapshot.mockResolvedValue(snap([])); await center.refresh()
    expect(center.informationError).toBe(''); expect(center.information).toEqual([])
  })
  it('does not let an older info result replace a newer request or clear its loading state', async () => {
    await center.refresh()
    const done: ((value: WorkSnapshot) => void)[] = []
    api.snapshot.mockImplementation(() => new Promise<WorkSnapshot>(resolve => done.push(resolve)))
    const first = center.loadInformation(), second = center.loadInformation()
    done[0]!(snap([entry('old')])); await first
    expect(center.informationLoading).toBe(true); expect(center.information).toEqual([])
    done[1]!(snap([entry('latest')])); await second
    expect(center.informationLoading).toBe(false); expect(center.information[0]?.id).toBe('latest')
  })
  it('clears info and personal details when info refresh is forbidden', async () => {
    await center.refresh(); center.information = [entry()]; center.selected = entry()
    api.snapshot.mockRejectedValue({ response: { status: 403 } }); await center.loadInformation()
    expect(center.information).toEqual([]); expect(center.selected).toBeNull()
    expect(center.informationLoading).toBe(false); expect(center.informationLoaded).toBe(false)
  })
})
