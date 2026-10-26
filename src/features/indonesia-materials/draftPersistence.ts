import { ref, toRaw } from 'vue'
import type { Command, Data, MaterialRecord } from '@/api/indonesiaMaterials'
import { createRandomUuid } from '@/lib/randomUuid'

export const draftKinds = {
  customer: { label: '固定客人', area: 'master' }, master: { label: '货号与物料', area: 'master' },
  options: { label: '基础选项', area: 'master' },
  planning: { label: '合同计划', area: 'board' },
  demand: { label: '合同需求', area: 'board' }, supply: { label: '采购／回料', area: 'supply' },
  shipment: { label: '出货明细', area: 'supply' }, import: { label: '统一排期导入', area: 'import' },
  warehouse: { label: '仓库实收导入', area: 'supply' },
  allocation: { label: '回料分配 PO', area: 'supply' },
} as const
export type DraftKind = keyof typeof draftKinds
export type DraftId = DraftKind | `master:product:${string}` | `${DraftKind}:new:${string}` | `${DraftKind}:record:${string}`
export function draftKind(id: string): DraftKind | undefined {
  if (Object.prototype.hasOwnProperty.call(draftKinds, id)) return id as DraftKind
  if (/^master:product:[A-Za-z0-9_-]{1,64}$/.test(id)) return 'master'
  const match = /^([a-z]+):(new|record):(.+)$/.exec(id)
  if (!match || !Object.prototype.hasOwnProperty.call(draftKinds, match[1]!)) return undefined
  if (match[2] === 'new') return /^[A-Za-z0-9_-]{1,64}$/.test(match[3]!) ? match[1] as DraftKind : undefined
  try {
    const parts = JSON.parse(decodeURIComponent(match[3]!))
    return Array.isArray(parts) && parts.length >= 2 && parts.length <= 5 && parts.every(value => typeof value === 'string' && value.length > 0 && value.length <= 500) && encodeURIComponent(JSON.stringify(parts)) === match[3] ? match[1] as DraftKind : undefined
  } catch { return undefined }
}
export const productDraftId = (id: string): DraftId => `master:product:${id}`
export const newDraftId = (kind: DraftKind): DraftId => `${kind}:new:${createRandomUuid()}`
export const recordDraftId = (kind: DraftKind, operation: string, ...keys: string[]): DraftId => `${kind}:record:${encodeURIComponent(JSON.stringify([operation, ...keys]))}`
/** Recover old singleton slots and upload drafts by their source identity, without migrating/deleting input. */
export function draftIdentity(kind: DraftKind, state: Data): DraftId | undefined {
  if (kind === 'master') return state.category === 'product' && state.editing?.id ? productDraftId(state.editing.id) : undefined
  if (kind === 'planning') return state.editing?.id ? recordDraftId(kind, 'edit', state.editing.id) : undefined
  if (kind === 'customer') return state.editing?.id ? recordDraftId(kind, 'edit', state.editing.id) : undefined
  if (kind === 'options') return state.named && state.form?.group && state.form?.value ? recordDraftId(kind, 'edit', state.form.group, state.form.value) : undefined
  if (kind === 'demand' || kind === 'allocation') {
    if (state.selection?.record?.id) return recordDraftId(kind, state.selection.mode, state.selection.record.id, ...(state.selection.demandId ? [state.selection.demandId] : []))
    return state.editing?.id ? recordDraftId(kind, 'edit', state.editing.id) : undefined
  }
  if (kind === 'supply') return state.selected?.id ? recordDraftId(kind, state.mode, state.selected.id) : state.editing?.id ? recordDraftId(kind, 'edit', state.editing.id) : undefined
  if (kind === 'shipment') return state.confirming?.id ? recordDraftId(kind, 'confirm', state.confirming.id, String(state.confirming.version)) : state.editing?.id ? recordDraftId(kind, 'edit', state.editing.id) : undefined
  if (kind === 'import' || kind === 'warehouse') return state.preview?.id ? recordDraftId(kind, 'inspect', state.preview.id) : undefined
}
export interface SavedDraft { id: DraftId; revision: string; writer: string; savedAt: string; state: Data }
export interface SavedOperation { command: Command; owner?: DraftId; draftRevision?: string; writer: string }
export interface DraftBucket { format: 1; drafts: Partial<Record<DraftId, SavedDraft>>; pending: SavedOperation | null }
export function draftLabel(draft: SavedDraft) {
  const kind = draftKind(draft.id)!, state = draft.state
  if (kind === 'master' && state.category === 'product') return `${state.form?.customer || '待选客人'} · ${state.form?.code || '新货号'} · 物料草稿`
  const detail = state.label || (kind === 'customer' ? state.form?.name || '新客人'
    : kind === 'options' ? `${state.form?.group || ''} · ${state.form?.value || '新选项'}`
      : kind === 'demand' ? [state.orderForm?.customer, state.orderForm?.contract_no || '新合同', state.orderForm?.batch].filter(Boolean).join(' · ')
        : kind === 'supply' ? [state.form?.supplier, state.form?.purchase_no || '新采购批次', state.form?.batch].filter(Boolean).join(' · ')
          : kind === 'shipment' ? [state.form?.customer || '新出货单', state.form?.recipient, state.form?.shipment_date].filter(Boolean).join(' · ')
            : kind === 'import' ? [state.customer, state.recipient, state.file?.name || '新导入'].filter(Boolean).join(' · ') : '')
  return detail ? `${draftKinds[kind].label} · ${detail}` : draftKinds[kind].label
}
export interface DraftDatabase {
  read(key: string): Promise<DraftBucket>
  update(key: string, change: (bucket: DraftBucket) => void): Promise<DraftBucket>
}
export const emptyDraftBucket = (): DraftBucket => ({ format: 1, drafts: {}, pending: null })
export function copyDraft<T>(value: T): T {
  if (value == null || typeof value !== 'object' || value instanceof Blob) return value
  const raw = toRaw(value)
  if (Array.isArray(raw)) return raw.map(copyDraft) as T
  return Object.fromEntries(Object.entries(raw).map(([key, entry]) => [key, copyDraft(entry)])) as T
}
export function checkedBucket(value: unknown): DraftBucket {
  if (value == null) return emptyDraftBucket()
  const bucket = value as DraftBucket
  if (bucket.format !== 1 || !bucket.drafts || typeof bucket.drafts !== 'object' || Array.isArray(bucket.drafts) || !(bucket.pending === null || (bucket.pending && typeof bucket.pending === 'object'))) throw new Error('本机草稿格式无法识别，原内容已保留，请联系管理员核对。')
  for (const [id, draft] of Object.entries(bucket.drafts)) {
    if (!draftKind(id) || !draft || draft.id !== id || typeof draft.revision !== 'string' || typeof draft.writer !== 'string' || typeof draft.savedAt !== 'string' || !draft.state || typeof draft.state !== 'object' || Array.isArray(draft.state)) throw new Error('本机草稿内容无法识别，原内容已保留，请联系管理员核对。')
    if (id.startsWith('master:') && (draft.state.category !== 'product' || (id.startsWith('master:product:') ? draft.state.editing?.kind !== 'product' || draft.state.editing.id !== id.slice('master:product:'.length) : !!draft.state.editing))) throw new Error('货号草稿身份无法识别，原内容已保留，请联系管理员核对。')
    const legacyConfirmation = draftKind(id) === 'shipment' && draft.state.confirming?.id && id === recordDraftId('shipment', 'confirm', draft.state.confirming.id)
    if (id.includes(':record:') && !legacyConfirmation && draftIdentity(draftKind(id)!, draft.state) !== id) throw new Error('草稿与原记录身份不一致，原内容已保留，请核对。')
  }
  return bucket
}
export const draftDatabase: DraftDatabase = {
  async read(key) { return accessDatabase(key) },
  async update(key, change) { return accessDatabase(key, change) },
}
async function accessDatabase(key: string, change?: (bucket: DraftBucket) => void): Promise<DraftBucket> {
  if (typeof indexedDB === 'undefined') throw new Error('当前浏览器不支持本机草稿存储。')
  const db = await new Promise<IDBDatabase>((resolve, reject) => {
    const request = indexedDB.open('rrn-indonesia-material-drafts', 1)
    request.onupgradeneeded = () => { request.result.createObjectStore('scopes') }
    request.onsuccess = () => resolve(request.result)
    request.onerror = () => reject(request.error)
    request.onblocked = () => reject(new Error('草稿存储被其他页面占用，请关闭旧版本页面后重试。'))
  })
  try {
    return await new Promise<DraftBucket>((resolve, reject) => {
      const transaction = db.transaction('scopes', change ? 'readwrite' : 'readonly')
      const store = transaction.objectStore('scopes')
      const request = store.get(key)
      let result: DraftBucket
      let failure: unknown
      request.onsuccess = () => {
        try { result = checkedBucket(request.result); if (change) { change(result); store.put(result, key) } }
        catch (cause) { failure = cause; transaction.abort() }
      }
      transaction.oncomplete = () => resolve(result!)
      transaction.onabort = transaction.onerror = () => reject(failure ?? transaction.error ?? request.error ?? new Error('本机草稿存储失败'))
    })
  } finally { db.close() }
}

/** Each write compares the editor's revision, not a newer revision received from another tab. */
export function createDraftPersistence(database: DraftDatabase = draftDatabase) {
  const bucket = ref<DraftBucket>(emptyDraftBucket())
  const ready = ref(false), saving = ref(0), error = ref('')
  const writer = createRandomUuid()
  let scope = '', generation = 0, queue = Promise.resolve()
  const leases = new Map<DraftId, string | undefined>()
  let channel: BroadcastChannel | undefined
  const listeners = new Set<() => void>()
  function reset(key = '') { generation++; scope = key; ready.value = false; saving.value = 0; error.value = ''; bucket.value = emptyDraftBucket(); leases.clear(); queue = Promise.resolve() }
  async function load(key = scope) {
    const epoch = generation
    try {
      const result = await database.read(key)
      if (scope !== key || epoch !== generation) return false
      bucket.value = result; ready.value = true; error.value = ''
      return true
    } catch (cause) { if (epoch === generation) error.value = message(cause); return false }
  }
  function publish() {
    channel?.postMessage(scope)
    // A small invalidation signal also covers browsers without BroadcastChannel.
    try { localStorage.setItem('rrn-indonesia-draft-signal', JSON.stringify([scope, createRandomUuid()])) } catch { /* IndexedDB remains authoritative. */ }
  }
  async function refresh() { if (scope && await load()) listeners.forEach(listener => listener()) }
  const storageChanged = (event: StorageEvent) => { if (event.key === 'rrn-indonesia-draft-signal') void refresh() }
  if (typeof BroadcastChannel !== 'undefined') {
    channel = new BroadcastChannel('rrn-indonesia-draft-changes')
    channel.onmessage = event => { if (event.data === scope) void refresh() }
  }
  window.addEventListener('storage', storageChanged)
  function transact(change: (current: DraftBucket) => void) {
    const key = scope, epoch = generation
    saving.value++
    const job = queue.then(async () => {
      if (epoch !== generation || !ready.value) return false
      try {
        const result = await database.update(key, current => {
          if (epoch !== generation) throw new Error('身份或厂区已变化，本次旧草稿写入已取消。')
          change(current)
        })
        if (epoch !== generation) return false
        bucket.value = result; error.value = ''; publish(); return true
      } catch (cause) { if (epoch === generation) error.value = message(cause); return false }
    }).finally(() => { if (epoch === generation) saving.value-- })
    queue = job.then(() => undefined)
    return job
  }
  function adopt(id: DraftId, revision = bucket.value.drafts[id]?.revision) { leases.set(id, revision) }
  async function save(id: DraftId, state: Data) {
    // Only explicit open/restore may adopt an existing revision. An untouched slot expects absence.
    if (!leases.has(id)) leases.set(id, undefined)
    const snapshot = copyDraft(state)
    const revision = createRandomUuid()
    const success = await transact(current => {
      if (current.pending) throw new Error('上次提交结果尚未确认，请先核对或重试原操作。')
      if (current.drafts[id]?.revision !== leases.get(id)) throw new Error('此草稿已在其他页面更新或删除，本页不会覆盖。请先保留当前输入，再核对草稿。')
      current.drafts[id] = { id, state: snapshot, revision, writer, savedAt: new Date().toISOString() }
    })
    if (success) leases.set(id, revision)
    return success
  }
  async function remove(id: DraftId, revision = bucket.value.drafts[id]?.revision) {
    const success = await transact(current => {
      if (current.pending?.owner === id) throw new Error('该草稿有尚未确认的提交，不能删除；请先重试原操作。')
      if (current.drafts[id]?.revision !== revision) throw new Error('此草稿已在其他页面更新，请重新核对后删除。')
      delete current.drafts[id]
    })
    if (success) leases.set(id, undefined)
    return success
  }
  async function begin(command: Command, owner?: DraftId, retry = false) {
    await queue
    if (!ready.value || error.value) return false
    const saved = copyDraft(command)
    const revision = owner ? leases.get(owner) : undefined
    return transact(current => {
      if (current.pending) {
        if (JSON.stringify(current.pending.command) !== JSON.stringify(saved) || current.pending.owner !== owner) throw new Error('其他页面有未确认的提交，请先核对原操作。')
        return
      }
      if (retry) throw new Error('原操作已在其他页面完成核对，请重新读取草稿；本页不会重新提交。')
      if (owner && current.drafts[owner]?.revision !== revision) throw new Error('待提交草稿已在其他页面更新，请先核对；本次尚未发送。')
      current.pending = { command: saved, owner, draftRevision: revision, writer }
    })
  }
  async function finish(operationId: string, committed: boolean) {
    let cleared: DraftId | undefined
    const success = await transact(current => {
      const operation = current.pending
      if (!operation) return // Another tab already finalized this same replay. Never touch a newer draft.
      if (operation.command.operation_id !== operationId) throw new Error('原操作凭据已变化，请重新读取草稿核对。')
      if (committed && operation.owner && current.drafts[operation.owner]?.revision === operation.draftRevision) {
        delete current.drafts[operation.owner]; cleared = operation.owner
      }
      current.pending = null
    })
    if (success && cleared) leases.set(cleared, undefined)
    return success
  }
  return { bucket, ready, saving, error, reset, load, save, adopt, remove, begin, finish,
    flush: () => queue, onExternalChange: (listener: () => void) => { listeners.add(listener); return () => { listeners.delete(listener) } },
    dispose: () => { generation++; channel?.close(); window.removeEventListener('storage', storageChanged); listeners.clear() } }
}
function message(cause: unknown) { return `${cause instanceof Error ? cause.message : '存储空间不足或浏览器禁止写入'}；草稿尚未安全保存，请保留当前页面。` }
export function recordRef(row?: MaterialRecord | null) { return row ? { id: row.id, kind: row.kind, version: row.version } : null }
export function restoreRecord(records: MaterialRecord[], reference: Data | null | undefined, kind: MaterialRecord['kind']) {
  if (!reference) return undefined
  const row = records.find(item => item.id === reference.id && item.kind === kind)
  if (!row || row.data.deleted || reference.kind !== kind || !Number.isInteger(reference.version) || reference.version < 1) throw new Error('草稿引用的原记录已不可用，草稿仍保留，请核对资料。')
  // Keep the version that was edited. A stale draft must not overwrite a newer record silently.
  return { ...row, version: reference.version }
}
