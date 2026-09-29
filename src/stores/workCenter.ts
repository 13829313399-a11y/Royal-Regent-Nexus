import { computed, ref, watch } from 'vue'
import { defineStore } from 'pinia'
import { workCenterApi } from '@/api/workCenter'
import { useAuthStore } from '@/stores/auth'
import { getApiErrorMessage } from '@/lib/http'
import type { PersonalPatch, WorkEntry, WorkPreferences, WorkQuery, WorkSnapshot } from '@/features/work-center/types'

export const defaultWorkQuery = (): WorkQuery => ({ view: 'todo', factory_scope: 'authorized', module: '', q: '', due: 'all', unread_only: false, limit: 30 })
export const useWorkCenterStore = defineStore('work-center', () => {
  const auth = useAuthStore()
  const snapshot = ref<WorkSnapshot | null>(null)
  const bell = ref<WorkSnapshot | null>(null)
  const selected = ref<WorkEntry | null>(null)
  const query = ref<WorkQuery>(defaultWorkQuery())
  const loading = ref(false), error = ref(''), detailError = ref(''), syncing = ref(false), pendingRefresh = ref(false)
  const workspaceOpen = ref(false), workspaceEngaged = ref(false), panelOpen = ref(false), personalBusy = ref(false)
  const toasts = ref<WorkEntry[]>([]), toastOverflow = ref(0), information = ref<WorkEntry[]>([])
  const preferences = ref<WorkPreferences>({ sound_enabled: false, toast_level: 'assigned', version: 0, business_timezone: 'Asia/Shanghai' })
  let sequence = 0, detailSequence = 0, controller: AbortController | undefined
  let timer: ReturnType<typeof setTimeout> | undefined, running = false, failures = 0, channel: BroadcastChannel | undefined
  let known = new Set<string>(), baseline = false, stopAuthWatch: (() => void) | undefined
  const account = computed(() => `${auth.currentUser?.id ?? ''}:${auth.authorizationVersion}:${auth.authzMode}:${auth.currentUser?.identity?.effective_context_key ?? ''}:${auth.currentUser?.identity?.employment_epoch ?? ''}`)
  let infoSequence = 0
  const summary = computed(() => workspaceOpen.value ? snapshot.value?.summary : bell.value?.summary ?? snapshot.value?.summary)
  const count = computed(() => summary.value?.actionable_total ?? 0)
  const stamp = (item: WorkEntry) => `${item.id}@${item.attention_version}`

  function clear() {
    clearTimeout(timer)
    ++sequence; ++detailSequence; controller?.abort(); snapshot.value = bell.value = null; selected.value = null
    ++infoSequence; information.value = []; panelOpen.value = false; toasts.value = []; toastOverflow.value = 0; known = new Set(); baseline = false; pendingRefresh.value = false; error.value = detailError.value = ''
    query.value = defaultWorkQuery(); loading.value = syncing.value = false
    workspaceEngaged.value = false
    preferences.value = { sound_enabled: false, toast_level: 'assigned', version: 0, business_timezone: 'Asia/Shanghai' }
  }
  function schedule() {
    clearTimeout(timer)
    if (!running || document.hidden || !navigator.onLine || !auth.currentUser) return
    const boundary = snapshot.value?.context.authz_recheck_at
    const delay = boundary ? Math.max(100, Date.parse(boundary) - Date.now()) : Infinity
    timer = setTimeout(() => {
      if (delay <= 25_000) { clear(); void auth.refreshSession().then(() => refresh()) }
      else void refresh(true)
    }, Math.min(delay, Math.min(120_000, 25_000 * 2 ** failures)))
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
      const [next, bellResponse] = await Promise.all([
        workCenterApi.snapshot({ ...query.value, selected_id: selected.value?.id }, controller.signal),
        workCenterApi.snapshot({ view: 'todo', limit: 5 }, controller.signal),
      ])
      if (seq !== sequence || identity !== account.value) return
      const top = bellResponse.context.viewer_key === next.context.viewer_key ? bellResponse : { ...next, items: [], next_cursor: null }
      if (snapshot.value && snapshot.value.context.viewer_key !== next.context.viewer_key) {
        ++detailSequence; ++infoSequence; information.value = []
        selected.value = null; toasts.value = []; toastOverflow.value = 0; known.clear(); baseline = false
      }
      const ids = new Set(top.items.map(stamp))
      const candidates = top.items.filter(item => !known.has(stamp(item)) && item.attention_version > 0 && item.can_act_now
        && (!item.personal.snoozed_until || Date.parse(item.personal.snoozed_until) <= Date.parse(next.context.server_time))
        && (preferences.value.toast_level === 'all_tasks' || (preferences.value.toast_level === 'assigned' && item.viewer_relation === 'assignee')))
      toasts.value = toasts.value.filter(item => ids.has(stamp(item)))
      if (baseline && background && !workspaceOpen.value && !panelOpen.value && candidates.length) {
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
      snapshot.value = next; bell.value = top; error.value = ''; failures = 0
      if (next.selected_entry_state && 'state' in next.selected_entry_state) { selected.value = null; detailError.value = '事项已失效或不在当前可见范围' }
      else if (next.selected_entry_state) selected.value = next.selected_entry_state
    } catch (failure) {
      if (seq !== sequence || identity !== account.value) return
      const status = (failure as { response?: { status?: number } }).response?.status
      if (status === 401 || status === 403) clear()
      else if (status === 409 && query.value.cursor) { query.value.cursor = undefined; void refresh(); return }
      else if (snapshot.value) snapshot.value.health.status = 'stale'
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
      if (seq === detailSequence && identity === account.value) detailError.value = getApiErrorMessage(failure)
    }
  }
  async function patch(item: WorkEntry, payload: PersonalPatch, reload = true) {
    const identity = account.value, viewer = snapshot.value?.context.viewer_key
    personalBusy.value = true
    try {
      const result = await workCenterApi.patch(item.id, payload)
      if (identity !== account.value || viewer !== snapshot.value?.context.viewer_key) return
      if (selected.value?.id === item.id) selected.value = result
      for (const snap of [snapshot.value, bell.value]) if (snap) snap.items = snap.items.map(row => row.id === result.id ? result : row)
      broadcast(); if (reload) await refresh()
    } catch (failure) { if (identity === account.value && viewer === snapshot.value?.context.viewer_key) detailError.value = getApiErrorMessage(failure) }
    finally { if (identity === account.value) personalBusy.value = false }
  }
  async function markVisibleRead() {
    const identity = account.value
    const items = snapshot.value?.items ?? []
    personalBusy.value = true
    try {
      const result = await workCenterApi.batch(items.map(item => ({ id: item.id, observed_content_version: item.content_version })))
      if (identity !== account.value) return
      const failed = result.results.filter(item => item.status !== 'ok')
      await refresh(); broadcast()
      if (failed.length) error.value = `${failed.length} 项未能标读，请刷新后重试`
    } catch (failure) { if (identity === account.value) error.value = getApiErrorMessage(failure) }
    finally { if (identity === account.value) personalBusy.value = false }
  }
  async function loadInformation() {
    const seq = ++infoSequence, identity = account.value, viewer = snapshot.value?.context.viewer_key
    information.value = []
    try {
      const result = await workCenterApi.snapshot({ view: 'info', limit: 5 })
      if (seq === infoSequence && identity === account.value && viewer === snapshot.value?.context.viewer_key) information.value = result.items
    } catch (failure) { if (seq === infoSequence && identity === account.value && viewer === snapshot.value?.context.viewer_key) error.value = getApiErrorMessage(failure) }
  }
  async function savePreferences(values: Partial<WorkPreferences>) {
    const identity = account.value
    try {
      const result = await workCenterApi.savePreferences({ ...values, version: preferences.value.version })
      if (identity === account.value) preferences.value = result
    } catch (failure) { if (identity === account.value) error.value = getApiErrorMessage(failure) }
  }
  async function loadPreferences() {
    const identity = account.value
    try {
      const values = await workCenterApi.preferences()
      if (identity !== account.value) return
      preferences.value = values
      // Migrate an explicit browser preference once, not a new default.
      let old: string | null = null
      try { old = localStorage.getItem('rr.notification.sound.enabled') } catch { /* memory-only */ }
      if (values.version === 0 && old !== null) await savePreferences({ sound_enabled: old === 'true' })
    } catch { /* The work list remains usable if preference loading fails. */ }
  }
  function broadcast() { channel?.postMessage({ viewer: snapshot.value?.context.viewer_key, type: 'invalidate' }) }
  function wake() { if (!document.hidden && navigator.onLine) void refresh(); else clearTimeout(timer) }
  function invalidate() { if (!document.hidden) void refresh(); broadcast() }
  function start() {
    if (running) return
    running = true
    try { channel = new BroadcastChannel('rr-work-center'); channel.onmessage = event => { if (event.data?.viewer === snapshot.value?.context.viewer_key) wake() } } catch { /* polling fallback */ }
    document.addEventListener('visibilitychange', wake); window.addEventListener('online', wake); window.addEventListener('offline', wake)
    window.addEventListener('work-center-invalidated', invalidate)
    stopAuthWatch = watch(account, () => { clear(); if (auth.currentUser) { void loadPreferences(); void refresh() } }, { immediate: true })
  }
  function stop() {
    running = false; clearTimeout(timer); controller?.abort(); stopAuthWatch?.(); channel?.close()
    document.removeEventListener('visibilitychange', wake); window.removeEventListener('online', wake); window.removeEventListener('offline', wake)
    window.removeEventListener('work-center-invalidated', invalidate)
  }
  function setQuery(value: Partial<WorkQuery>) { query.value = { ...query.value, cursor: undefined, ...value }; pendingRefresh.value = false; return refresh() }
  return { snapshot, bell, selected, query, loading, error, detailError, syncing, pendingRefresh, workspaceOpen, workspaceEngaged, panelOpen,
    personalBusy, toasts, toastOverflow, information, loadInformation, preferences, summary, count, clear, refresh, selectEntry, patch, markVisibleRead, savePreferences, start, stop, setQuery }
})
