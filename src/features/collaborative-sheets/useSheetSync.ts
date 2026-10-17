import { computed, onBeforeUnmount, ref, watch, type Ref } from 'vue'
import { collaborativeSheetsApi as api, type CellConflict, type FillChange, type FillTaskDetail, type SheetValue, type SyncDelta, type SyncRequest } from '@/api/collaborativeSheets'
import { getAuthenticationGeneration } from '@/lib/authenticationGeneration'
import { createRandomUuid } from '@/lib/randomUuid'
import { getApiErrorMessage } from '@/lib/http'
import { coordinates, findCell } from './grid'
import { stageFillChanges } from './univerAdapter'

const key = (c: Pick<FillChange, 'sheet' | 'address'>) => `${c.sheet}:${c.address}`
export function useSheetSync(task: Ref<FillTaskDetail | undefined>, changes: Ref<FillChange[]>, factory: () => string, identity: () => string) {
  const saving = ref(false), message = ref(''), connected = ref(false), blocked = ref(false)
  const validationPaused = ref(false)
  let uncertain = false
  const conflicts = ref<CellConflict[]>([]), updated = ref<FillChange[]>([])
  let bases = new Map<string, { value: SheetValue; revision: number }>()
  const editingKeys = new Set<string>()
  let pending: SyncRequest | undefined, flight: Promise<boolean> | undefined
  let timer: ReturnType<typeof setTimeout> | undefined, polling: ReturnType<typeof setInterval> | undefined
  let stream: EventSource | undefined, epoch = 0, pulling = false, suppress = false, storageKey = ''
  let authGeneration = getAuthenticationGeneration()
  const current = (e: number) => e === epoch && authGeneration === getAuthenticationGeneration()
  const valueAt = (c: FillChange) => {
    const sheet = task.value?.workbook.sheets.find(s => s.index === c.sheet)
    return sheet ? findCell(sheet, c.address)?.value ?? null : null
  }
  const status = computed(() => blocked.value ? '同步已暂停，填写保留在本机' : validationPaused.value ? '填写未保存，请按提示修正' : conflicts.value.length ? '有同格冲突，请核对' : saving.value ? '正在保存…' : changes.value.length ? '等待自动保存…' : connected.value ? '已保存 · 实时同步中' : '已保存 · 正在连接')
  function persist() {
    if (!storageKey) return
    try {
      if (!changes.value.length && !pending) sessionStorage.removeItem(storageKey)
      else sessionStorage.setItem(storageKey, JSON.stringify({ changes: changes.value, bases: [...bases], pending, uncertain, validationPaused: validationPaused.value }))
    } catch { message.value = '浏览器无法保留恢复草稿，请勿关闭页面，等待保存成功。' }
  }
  function schedule(delay = 700) {
    clearTimeout(timer)
    if (!blocked.value && !validationPaused.value && !conflicts.value.length && (changes.value.length || pending)) timer = setTimeout(() => void flush(), delay)
  }
  watch(changes, () => {
    if (suppress || !task.value) return
    const keys = new Set(changes.value.map(key))
    for (const c of changes.value) if (!bases.has(key(c))) bases.set(key(c), { value: valueAt(c), revision: task.value.revision })
    for (const k of bases.keys()) if (!keys.has(k) && !editingKeys.has(k) && !pending?.changes.some(c => key(c) === k)) bases.delete(k)
    persist(); schedule()
  }, { flush: 'sync' })
  function stage(batch: FillChange[]) {
    if (!task.value) return []
    const result = stageFillChanges(task.value, changes.value, batch)
    validationPaused.value = false
    // Typing the old value while its previous edit is in flight is an explicit
    // undo, not an empty draft: it must be sent after the first acknowledgment.
    for (const c of batch) if (pending?.changes.some(sent => key(sent) === key(c)) && !result.some(x => key(x) === key(c))) result.push(c)
    for (const c of batch) editingKeys.delete(key(c))
    return result
  }
  function begin(c: Pick<FillChange, 'sheet' | 'address'>) {
    editingKeys.add(key(c))
    if (task.value && !bases.has(key(c))) bases.set(key(c), { value: valueAt({ ...c, value: null }), revision: task.value.revision })
  }
  function cancel(c: Pick<FillChange, 'sheet' | 'address'>) {
    editingKeys.delete(key(c))
    if (!changes.value.some(x => key(x) === key(c)) && !pending?.changes.some(x => key(x) === key(c))) bases.delete(key(c))
  }
  function apply(delta: SyncDelta) {
    if (!task.value || delta.id !== task.value.id || delta.revision < task.value.revision) return
    const updates = new Map<string, FillChange>()
    if (delta.overrides) for (const [k, value] of Object.entries(delta.overrides)) {
      const [sheet, address] = k.split(':'); updates.set(k, { sheet: Number(sheet), address: address!, value })
    }
    for (const e of delta.events) for (const c of (e.detail.changes ?? []) as { sheet: number; address: string; after: SheetValue }[]) updates.set(key(c), { sheet: c.sheet, address: c.address, value: c.after })
    const indexes = new Map(task.value.workbook.sheets.filter(s => [...updates.values()].some(c => c.sheet === s.index)).map(s => [s.index, new Map(s.cells.map(c => [c.address, c]))]))
    for (const c of updates.values()) {
      const sheet = task.value.workbook.sheets.find(s => s.index === c.sheet), position = coordinates(c.address)
      if (!sheet || !position) continue
      let cell = indexes.get(sheet.index)?.get(c.address)
      if (!cell) { cell = { address: c.address, row: position[0], column: position[1], value: null, display: '', formula: false, style: {} }; sheet.cells.push(cell); indexes.get(sheet.index)?.set(c.address, cell) }
      cell.value = c.value; cell.display = c.value === null ? '' : String(c.value)
    }
    task.value.revision = delta.revision; task.value.status = delta.status; task.value.editable_ranges = delta.editable_ranges
    task.value.grants = delta.grants
    task.value.activity = [...new Map([...delta.events.slice().reverse(), ...task.value.activity].map(e => [e.id, e])).values()].slice(0, 50)
    updated.value = [...updates.values()]
  }
  async function pull() {
    if (!task.value || pulling || saving.value || blocked.value) return false
    const e = epoch, id = task.value.id; pulling = true
    try {
      const delta = await api.changes(factory(), id, task.value.revision)
      if (current(e)) { apply(delta); connected.value = true; return true }
    } catch (error) {
      if (!current(e)) return false
      connected.value = false
      const status = (error as { response?: { status: number } }).response?.status
      if ([401, 403, 404].includes(status ?? 0)) { blocked.value = true; stream?.close(); message.value = '登录或填写权限已变化，请重新登录并打开任务。草稿保留在本机。' }
    } finally { if (current(e)) pulling = false }
    return false
  }
  async function send(): Promise<boolean> {
    if (!task.value || blocked.value || conflicts.value.length) return false
    if (!pending && !changes.value.length) return true
    const e = epoch, id = task.value.id
    pending ??= { operation_id: createRandomUuid(), expected_revision: task.value.revision, changes: changes.value.map(c => ({ ...c, base_value: bases.has(key(c)) ? bases.get(key(c))!.value : valueAt(c), base_revision: bases.get(key(c))?.revision ?? task.value!.revision })) }
    const sent = pending; persist(); saving.value = true
    try {
      const delta = await api.sync(factory(), id, sent)
      if (!current(e)) return false
      suppress = true
      changes.value = changes.value.filter(c => !sent.changes.some(s => key(s) === key(c) && s.value === c.value))
      for (const c of sent.changes) {
        if (editingKeys.has(key(c)) || changes.value.some(x => key(x) === key(c))) bases.set(key(c), { value: c.value, revision: delta.applied_revision ?? delta.revision })
        else bases.delete(key(c))
      }
      apply(delta)
      for (const c of changes.value) if (!bases.has(key(c))) bases.set(key(c), { value: valueAt(c), revision: task.value.revision })
      pending = undefined; uncertain = false; suppress = false; connected.value = true; message.value = ''; persist()
      return !changes.value.length
    } catch (error) {
      if (!current(e)) return false
      const response = (error as { response?: { status: number; data: { detail?: { code?: string; conflicts?: CellConflict[] } } } }).response
      if (response?.data.detail?.code === 'cell_conflict') {
        conflicts.value = response.data.detail.conflicts ?? []; pending = undefined; uncertain = false
        message.value = '以下单元格已被其他人修改，请逐格选择；其他填写内容仍保留。'
      } else if (response?.status === 422 && !uncertain) {
        pending = undefined; validationPaused.value = true
        message.value = `${getApiErrorMessage(error)}。请修正填写内容后重试；草稿仍保留。`
      } else if (response && response.status >= 400 && response.status < 500 && response.status !== 408 && response.status !== 429) {
        // Retain the exact retry receipt even after permission loss: an earlier
        // timed-out attempt might already have committed.
        blocked.value = true; message.value = getApiErrorMessage(error)
      } else { uncertain = true; connected.value = false; message.value = '网络暂不可用，填写已保留，将自动重试。' }
      persist(); return false
    } finally { if (current(e)) { saving.value = false; schedule(2000) } }
  }
  function flush(): Promise<boolean> {
    clearTimeout(timer)
    if (flight) return flight
    const e = epoch
    flight = send().finally(() => { if (current(e)) flight = undefined })
    return flight
  }
  async function resolve(c: CellConflict, keepMine: boolean) {
    if (!task.value) return
    if (!(await pull()) || blocked.value || task.value.revision < c.revision) { message.value = '请等待网络恢复并读取最新内容后再处理冲突。'; return }
    // Use the exact conflict version. A new intervening same-cell write must
    // conflict again, not be silently overwritten by this confirmation.
    bases.set(key(c), { value: c.value, revision: c.revision })
    if (!keepMine) changes.value = changes.value.filter(x => key(x) !== key(c))
    conflicts.value = conflicts.value.filter(x => key(x) !== key(c)); persist(); schedule()
  }
  function stop() { epoch++; clearTimeout(timer); clearInterval(polling); stream?.close(); stream = undefined; connected.value = false }
  function start() {
    stop(); blocked.value = false; validationPaused.value = false; uncertain = false; conflicts.value = []; bases = new Map(); editingKeys.clear(); pending = undefined; pulling = false; flight = undefined; saving.value = false
    authGeneration = getAuthenticationGeneration()
    storageKey = identity() && task.value ? `sheet-draft:${identity()}:${factory()}:${task.value.id}` : ''
    if (storageKey) try {
      const data = JSON.parse(sessionStorage.getItem(storageKey) ?? 'null')
      if (data) { suppress = true; bases = new Map(data.bases); pending = data.pending; uncertain = data.uncertain === true; validationPaused.value = data.validationPaused === true; changes.value = data.changes; suppress = false; message.value = validationPaused.value ? '已恢复未保存草稿，请按提示修正后再保存。' : '已恢复本页未确认保存的填写，正在与服务器核对。' }
    } catch { suppress = false; message.value = '恢复草稿失败，请保留页面并联系管理员。'; blocked.value = true }
    const e = epoch
    if (task.value && typeof EventSource !== 'undefined') {
      stream = new EventSource(api.streamUrl(factory(), task.value.id), { withCredentials: true })
      stream.addEventListener('revision', () => { if (current(e)) void pull() })
      stream.addEventListener('access_revoked', () => { if (current(e)) { blocked.value = true; connected.value = false; message.value = '权限或登录已变化，同步已暂停。'; stream?.close() } })
      stream.onerror = () => { if (current(e)) connected.value = false }
    }
    polling = setInterval(() => { if (current(e)) { void pull(); schedule() } }, 5000)
    schedule()
  }
  function sessionChanged() { persist(); stop(); blocked.value = true; message.value = '登录账号已变化，请重新打开工作台。' }
  window.addEventListener('auth-session-boundary-changed', sessionChanged)
  onBeforeUnmount(() => { persist(); stop(); window.removeEventListener('auth-session-boundary-changed', sessionChanged) })
  return { saving, message, connected, blocked, conflicts, updated, status, stage, begin, cancel, flush, pull, resolve, start, stop }
}
