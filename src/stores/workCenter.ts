import { computed, ref, watch } from 'vue'
import { defineStore } from 'pinia'
import { workCenterApi } from '@/api/workCenter'
import { useAuthStore } from '@/stores/auth'
import { getApiErrorMessage } from '@/lib/http'
import { parseBusinessTimestamp } from '@/lib/dateTime'
import { canArchive, normalizeFactory } from '@/features/work-center/metadata'
import type { PersonalPatch, WorkEntry, WorkPreferences, WorkQuery, WorkSnapshot } from '@/features/work-center/types'

export const defaultWorkQuery = (): WorkQuery => ({ view: 'todo', factory_scope: 'authorized', module: '', q: '', due: 'all', unread_only: false, limit: 30 })
const defaultPreferences = (): WorkPreferences => ({ sound_enabled: false, toast_level: 'assigned', version: 0, business_timezone: 'Asia/Shanghai' })
export const useWorkCenterStore = defineStore('work-center', () => {
  const auth = useAuthStore()
  const snapshot = ref<WorkSnapshot | null>(null)
  const bell = ref<WorkSnapshot | null>(null)
  const selected = ref<WorkEntry | null>(null)
  const query = ref<WorkQuery>(defaultWorkQuery())
  const loading = ref(false), error = ref(''), detailError = ref(''), syncing = ref(false), pendingRefresh = ref(false)
  const workspaceOpen = ref(false), workspaceEngaged = ref(false), panelOpen = ref(false), personalBusy = ref(false)
  const toasts = ref<WorkEntry[]>([]), toastOverflow = ref(0), information = ref<WorkEntry[]>([])
  const panelTab = ref<'todo' | 'info'>('todo'), informationLoading = ref(false), informationError = ref(''), informationLoaded = ref(false)
  const preferences = ref(defaultPreferences())
  let sequence = 0, detailSequence = 0, controller: AbortController | undefined
  let timer: ReturnType<typeof setTimeout> | undefined, running = false, failures = 0, channel: BroadcastChannel | undefined
  let known = new Set<string>(), baseline = false, stopAuthWatch: (() => void) | undefined
  const account = computed(() => `${auth.currentUser?.id ?? ''}:${auth.authorizationVersion}:${auth.authzMode}:${auth.currentUser?.identity?.effective_context_key ?? ''}:${auth.currentUser?.identity?.employment_epoch ?? ''}`)
  let infoSequence = 0, accessGeneration = 0, activeWrites = 0
  let snapshotReceivedAt = 0
  let preferencesLoaded = false, preferenceRequest: Promise<void> | undefined
  const feedback = ref('')
  const summary = computed(() => workspaceOpen.value ? snapshot.value?.summary : bell.value?.summary ?? snapshot.value?.summary)
  const count = computed(() => summary.value?.actionable_total ?? 0)
  const stamp = (item: WorkEntry) => `${item.id}@${item.attention_version}`

  function serverNow() {
    const at = parseBusinessTimestamp(snapshot.value?.context.server_time)
    return at === null ? undefined : new Date(at + performance.now() - snapshotReceivedAt).toISOString()
  }
  function resetPreferences() {
    preferencesLoaded = false; preferenceRequest = undefined
    preferences.value = defaultPreferences()
  }
  function clear() {
    ++accessGeneration; activeWrites = 0; personalBusy.value = false; feedback.value = ''
    resetPreferences()
    clearTimeout(timer)
    ++sequence; ++detailSequence; controller?.abort(); snapshot.value = bell.value = null; selected.value = null
    ++infoSequence; information.value = []; panelOpen.value = false; toasts.value = []; toastOverflow.value = 0; known = new Set(); baseline = false; pendingRefresh.value = false; error.value = detailError.value = ''
    informationLoading.value = informationLoaded.value = false; informationError.value = ''; panelTab.value = 'todo'
    query.value = defaultWorkQuery(); loading.value = syncing.value = false
    workspaceEngaged.value = false
  }
  function accessDenied(failure: unknown) {
    const status = (failure as { response?: { status?: number } })?.response?.status
    if (status !== 401 && status !== 403) return false
    clear()
    error.value = '当前账号无法查看事项，请重新核验登录和权限。'
    failures++
    schedule()
    return true
  }
  function clearSelection() { ++detailSequence; selected.value = null; detailError.value = '' }
  function beginWrite() { activeWrites++; personalBusy.value = true }
  function endWrite(generation: number) {
    if (generation === accessGeneration) personalBusy.value = --activeWrites > 0
  }
  function schedule() {
    clearTimeout(timer)
    if (!running || document.hidden || !navigator.onLine || !auth.currentUser) return
    const boundary = snapshot.value?.context.authz_recheck_at
    const delay = boundary ? Math.max(100, Date.parse(boundary) - Date.now()) : Infinity
    const pollDelay = Math.min(120_000, 25_000 * 2 ** failures)
    timer = setTimeout(() => {
      if (delay > pollDelay) { void refresh(true); return }
      clear()
      const generation = accessGeneration
      void auth.refreshSession().then(() => {
        if (running && generation === accessGeneration) return refresh()
      })
    }, Math.min(delay, pollDelay))
  }
  async function claim(items: WorkEntry[], viewer: string): Promise<WorkEntry[]> {
    const operation = () => {
      try {
        const storageKey = `rr.work-center.claims.${viewer}`
        const old = JSON.parse(localStorage.getItem(storageKey) ?? '[]') as string[]
        const accepted = items.filter(item => !old.includes(stamp(item)))
        localStorage.setItem(storageKey, JSON.stringify([...old, ...accepted.map(stamp)].slice(-300)))
        return accepted
      } catch { return items }
    }
    return navigator.locks ? navigator.locks.request(`rr-work-center-${viewer}`, operation) : operation()
  }
  async function refresh(background = false) {
    if (!auth.currentUser) { clear(); return }
    const seq = ++sequence, identity = account.value
    controller?.abort(); controller = new AbortController()
    syncing.value = true; loading.value = !snapshot.value
    try {
      const current = query.value
      const bellQuery = { view: 'todo' as const, limit: 8 }
      const shared = current.view === 'todo' && current.factory_scope === 'authorized' && !current.module &&
        !current.q && current.due === 'all' && !current.unread_only && !current.cursor && current.limit >= 8
      const [{ snapshot: next, receivedAt }, separate] = await Promise.all([
        workCenterApi.snapshot(workspaceOpen.value ? { ...current, selected_id: selected.value?.id } : bellQuery, controller.signal)
          .then(snapshot => ({ snapshot, receivedAt: performance.now() })),
        workspaceOpen.value && !shared ? workCenterApi.snapshot(bellQuery, controller.signal) : undefined,
      ])
      if (seq !== sequence || identity !== account.value) return
      if (separate && separate.context.viewer_key !== next.context.viewer_key) {
        clear(); error.value = '授权范围已变化，请重新同步。'; schedule(); return
      }
      const top = separate ?? { ...next, items: next.items.slice(0, 8), next_cursor: null }
      if (snapshot.value && snapshot.value.context.viewer_key !== next.context.viewer_key) {
        ++accessGeneration; activeWrites = 0; personalBusy.value = false; feedback.value = ''; pendingRefresh.value = false
        resetPreferences()
        ++detailSequence; ++infoSequence; information.value = []
        informationLoaded.value = informationLoading.value = false; informationError.value = ''
        selected.value = null; toasts.value = []; toastOverflow.value = 0; known.clear(); baseline = false
      }
      const ids = new Set(top.items.map(stamp))
      const candidates = top.items.filter(item => !known.has(stamp(item)) && item.attention_version > 0 && item.can_act_now
        && (!item.personal.snoozed_until || Date.parse(item.personal.snoozed_until) <= Date.parse(next.context.server_time))
        && (preferences.value.toast_level === 'all_tasks' || (preferences.value.toast_level === 'assigned' && item.viewer_relation === 'assignee')))
      toasts.value = toasts.value.filter(item => ids.has(stamp(item)))
      if (baseline && background && preferencesLoaded && !workspaceOpen.value && !panelOpen.value && candidates.length) {
        const accepted = await claim(candidates, next.context.viewer_key)
        if (seq !== sequence || identity !== account.value) return
        const all = [...toasts.value, ...accepted]
        toasts.value = all.slice(0, 3); toastOverflow.value += Math.max(0, all.length - 3)
      }
      const newVisible = baseline && next.items.some(item => !snapshot.value?.items.some(previous => previous.id === item.id))
      known = new Set([...known, ...ids].slice(-500)); baseline = true
      if (background && workspaceOpen.value && (selected.value || query.value.cursor || workspaceEngaged.value) && newVisible) {
        pendingRefresh.value = true
        // Preserve position, but remove revoked/finished rows immediately.
        const current = new Map(next.items.map(item => [item.id, item]))
        next.items = (snapshot.value?.items ?? []).flatMap(item => current.has(item.id) ? [current.get(item.id)!] : [])
      }
      snapshotReceivedAt = receivedAt
      snapshot.value = next; bell.value = top; error.value = ''; failures = 0
      if (!preferencesLoaded && !preferenceRequest) {
        const generation = accessGeneration
        preferenceRequest = loadPreferences().finally(() => {
          if (generation === accessGeneration) preferenceRequest = undefined
        })
      }
      if (!background) pendingRefresh.value = false
      if (next.selected_entry_state && selected.value?.id === next.selected_entry_state.id) {
        if ('state' in next.selected_entry_state) { clearSelection(); detailError.value = '事项已失效或不在当前可见范围' }
        else selected.value = next.selected_entry_state
      }
      if (panelOpen.value && panelTab.value === 'info') await loadInformation()
    } catch (failure) {
      if (seq !== sequence || identity !== account.value) return
      const status = (failure as { response?: { status?: number } }).response?.status
      if (accessDenied(failure)) return
      else if (status === 409 && query.value.cursor) { query.value.cursor = undefined; void refresh(); return }
      else {
        if (snapshot.value) snapshot.value.health.status = 'stale'
        if (bell.value) bell.value.health.status = 'stale'
      }
      error.value = getApiErrorMessage(failure); failures++
    } finally {
      if (seq === sequence) { loading.value = syncing.value = false; schedule() }
    }
  }
  async function selectEntry(id: string) {
    const seq = ++detailSequence, identity = account.value
    detailError.value = ''; selected.value = null
    try {
      const item = await workCenterApi.entry(id)
      if (seq !== detailSequence || identity !== account.value) return
      selected.value = item
      await patch(item, { observed_content_version: item.content_version }, false)
    } catch (failure) {
      if (seq === detailSequence && identity === account.value && !accessDenied(failure)) detailError.value = getApiErrorMessage(failure)
    }
  }
  async function patch(item: WorkEntry, payload: PersonalPatch, reload = true) {
    const identity = account.value, viewer = snapshot.value?.context.viewer_key
    const generation = accessGeneration
    beginWrite()
    try {
      const result = await workCenterApi.patch(item.id, payload)
      if (generation !== accessGeneration || identity !== account.value || viewer !== snapshot.value?.context.viewer_key) return
      if (selected.value?.id === item.id) selected.value = result
      for (const snap of [snapshot.value, bell.value]) if (snap) snap.items = snap.items.map(row => row.id === result.id ? result : row)
      information.value = information.value.map(row => row.id === result.id ? result : row)
      broadcast(); if (reload) await refresh()
      if (generation !== accessGeneration || identity !== account.value || viewer !== snapshot.value?.context.viewer_key) return
      return result
    } catch (failure) {
      if (generation === accessGeneration && identity === account.value && !accessDenied(failure)) {
        detailError.value = feedback.value = getApiErrorMessage(failure)
      }
    } finally { endWrite(generation) }
  }
  async function batchPatch(entries: WorkEntry[], action: 'read' | 'snooze' | 'archive', until?: string) {
    const identity = account.value, generation = accessGeneration
    if (!entries.length || (action === 'archive' && !entries.every(canArchive))) return
    const eligible = action === 'snooze' ? entries.filter(item => item.can_act_now) : entries
    if (!eligible.length || (action === 'snooze' && !until)) return
    const items = eligible.map(item => ({
      id: item.id, ...(action === 'read' ? { observed_content_version: item.content_version }
        : { state_version: item.personal.state_version, ...(action === 'archive' ? { archived: true } : { snoozed_until: until }) }),
    }))
    beginWrite(); feedback.value = ''
    try {
      const result = await workCenterApi.batch(items)
      if (generation !== accessGeneration || identity !== account.value) return
      const failed = result.results.filter(item => item.status !== 'ok')
      await refresh()
      if (generation !== accessGeneration || identity !== account.value) return
      broadcast()
      const reasons = [...new Set(failed.map(item => item.message || '事项状态已变化'))]
      feedback.value = failed.length ? `${failed.length} 项未成功 · ${reasons.join('、')}` : `已处理 ${eligible.length} 项`
      return failed.map(item => item.id)
    } catch (failure) {
      if (generation === accessGeneration && identity === account.value && !accessDenied(failure)) feedback.value = getApiErrorMessage(failure)
    } finally { endWrite(generation) }
  }
  function markVisibleRead(entries = snapshot.value?.items ?? []) { return batchPatch(entries, 'read') }
  async function loadInformation() {
    if (!auth.currentUser) { clear(); return }
    const seq = ++infoSequence, identity = account.value, viewer = snapshot.value?.context.viewer_key
    informationLoading.value = true; informationError.value = ''
    try {
      const result = await workCenterApi.snapshot({ view: 'info', limit: 8 })
      if (seq !== infoSequence || identity !== account.value || viewer !== snapshot.value?.context.viewer_key) return
      if (viewer && result.context.viewer_key !== viewer) { clear(); void refresh(); return }
      information.value = result.items; informationLoaded.value = true
    } catch (failure) {
      if (seq !== infoSequence || identity !== account.value || viewer !== snapshot.value?.context.viewer_key) return
      if (accessDenied(failure)) return
      informationError.value = getApiErrorMessage(failure)
    } finally { if (seq === infoSequence) informationLoading.value = false }
  }
  async function savePreferences(values: Partial<WorkPreferences>) {
    const identity = account.value, generation = accessGeneration
    try {
      const result = await workCenterApi.savePreferences({ ...values, version: preferences.value.version })
      if (identity === account.value && generation === accessGeneration) {
        preferences.value = result
        preferencesLoaded = true
      }
    } catch (failure) { if (identity === account.value && generation === accessGeneration && !accessDenied(failure)) error.value = getApiErrorMessage(failure) }
  }
  async function loadPreferences() {
    const identity = account.value, generation = accessGeneration
    try {
      const values = await workCenterApi.preferences()
      if (identity !== account.value || generation !== accessGeneration) return
      if (values.version < preferences.value.version) return
      preferences.value = values
      preferencesLoaded = true
      // Migrate an explicit browser preference once, not a new default.
      let old: string | null = null
      try { old = localStorage.getItem('rr.notification.sound.enabled') } catch { /* memory-only */ }
      if (values.version === 0 && old !== null) await savePreferences({ sound_enabled: old === 'true' })
    } catch (failure) { if (identity === account.value && generation === accessGeneration) accessDenied(failure) }
  }
  function broadcast() { channel?.postMessage({ viewer: snapshot.value?.context.viewer_key, type: 'invalidate' }) }
  function wake() { if (!document.hidden && navigator.onLine) void refresh(); else clearTimeout(timer) }
  function invalidate() { if (!document.hidden) void refresh(); broadcast() }
  function start() {
    if (running) return
    running = true
    // The routed workspace can mount before the application host. Preserve
    // its initial URL filters, but still clear them on real account changes.
    const initialQuery = workspaceOpen.value ? { ...query.value } : undefined
    try { channel = new BroadcastChannel('rr-work-center'); channel.onmessage = event => { if (event.data?.viewer === snapshot.value?.context.viewer_key) wake() } } catch { /* polling fallback */ }
    document.addEventListener('visibilitychange', wake); window.addEventListener('online', wake); window.addEventListener('offline', wake)
    window.addEventListener('work-center-invalidated', invalidate)
    stopAuthWatch = watch(account, (_, previous) => {
      clear()
      failures = 0
      if (previous === undefined && initialQuery) query.value = initialQuery
      if (auth.currentUser) void refresh()
    }, { immediate: true, flush: 'sync' })
  }
  function stop() {
    running = false; stopAuthWatch?.(); clear()
    channel?.close(); channel = undefined
    document.removeEventListener('visibilitychange', wake); window.removeEventListener('online', wake); window.removeEventListener('offline', wake)
    window.removeEventListener('work-center-invalidated', invalidate)
  }
  function setQuery(value: Partial<WorkQuery>) {
    query.value = { ...query.value, cursor: undefined, ...value, factory_scope: normalizeFactory(value.factory_scope ?? query.value.factory_scope) }
    pendingRefresh.value = false
    return refresh()
  }
  return { snapshot, bell, selected, query, loading, error, detailError, syncing, pendingRefresh, workspaceOpen, workspaceEngaged, panelOpen,
    personalBusy, toasts, toastOverflow, information, informationLoading, informationError, informationLoaded, panelTab, loadInformation, preferences, summary, count, serverNow, clear, clearSelection, accessDenied, refresh, selectEntry, patch, markVisibleRead, batchPatch, feedback, savePreferences, start, stop, setQuery }
})
