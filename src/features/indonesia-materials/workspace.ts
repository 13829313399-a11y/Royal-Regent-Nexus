import { computed, inject, nextTick, onBeforeUnmount, provide, reactive, ref, shallowReactive, watch, type InjectionKey } from 'vue'
import { useAppStore } from '@/stores/app'
import { useAuthStore } from '@/stores/auth'
import { getApiErrorMessage } from '@/lib/http'
import { getAuthenticationGeneration } from '@/lib/authenticationGeneration'
import { createRandomUuid } from '@/lib/randomUuid'
import { registerFactoryChangeGuard } from '@/lib/factoryChangeGuard'
import { createDraftPersistence, draftKind, draftLabel, type DraftKind, type DraftId } from './draftPersistence'
import { indonesiaMaterialsApi as api, type Action, type BoardOrder, type Command, type Data, type MaterialRecord, type RecordKind } from '@/api/indonesiaMaterials'

export function createMaterialsWorkspace(sharedOptions = false) {
  const app = useAppStore()
  const auth = useAuthStore()
  const factory = computed(() => sharedOptions ? 'shared-options' : app.activeFactoryId === 'group' ? '' : app.activeFactoryId)
  const records = ref<MaterialRecord[]>([])
  const optionDefaults = ref<Data[]>([])
  const board = ref<BoardOrder[]>([])
  const permissions = ref<string[]>([])
  const loading = ref(false)
  const busy = ref(false)
  const error = ref('')
  const loadError = ref('')
  const notice = ref('')
  const pending = ref<Command | null>(null)
  const scopeEpoch = ref(0)
  const localDrafts = createDraftPersistence()
  const restoreTarget = ref<DraftId | null>(null)
  const shipmentTarget = ref<string | null>(null)
  const boardStage = ref('board'), supplyStage = ref('warehouse')
  type DraftOwner = { restore: (state: Data, revision: string, id: DraftId) => Promise<boolean>; reset: (id?: DraftId) => void; flush: () => Promise<boolean> }
  const owners = new Map<DraftKind, DraftOwner>()
  const ownerFor = (id: DraftId) => { const kind = draftKind(id); return kind ? owners.get(kind) : undefined }
  const registerDraftOwner = (id: DraftKind, owner: DraftOwner) => {
    owners.set(id, owner)
    return () => { if (owners.get(id) === owner) owners.delete(id) }
  }
  async function restoreDraft(id: DraftId) {
    if (!localDrafts.ready.value || busy.value) return
    const epoch = scopeEpoch.value, selected = factory.value
    await localDrafts.flush()
    if (!same(epoch, selected)) return
    restoreTarget.value = null
    await nextTick()
    restoreTarget.value = id
    await nextTick()
    if (!same(epoch, selected)) return
    const saved = localDrafts.bucket.value.drafts[id]
    if (!sharedOptions && saved && draftKind(id) === 'options') { notice.value = '这是旧厂区选项草稿，原内容保留。请在共用基础选项中查看并明确复制核对；不会自动改写全厂资料。'; return }
    const owner = ownerFor(id)
    if (!saved || !owner) { error.value = '草稿入口尚未就绪，请重新打开对应工作区。'; return }
    try {
      if (await owner.restore(saved.state, saved.revision, id) && same(epoch, selected)) { notice.value = `已恢复${draftLabel(saved)}；仍需核对并正式保存。`; if (!pending.value) error.value = '' }
    } catch (cause) { if (same(epoch, selected)) error.value = getApiErrorMessage(cause) }
  }
  async function deleteDraft(id: DraftId) {
    if (busy.value || pending.value || !window.confirm('删除这份本机草稿及其未提交内容？正式业务记录不受影响。')) return
    const epoch = scopeEpoch.value, selected = factory.value
    if (await localDrafts.remove(id) && same(epoch, selected)) ownerFor(id)?.reset(id)
  }
  const drafts = shallowReactive(new Set<() => boolean>())
  let pendingCompletion: (() => void) | undefined
  function registerDraft(dirty: () => boolean) {
    const epoch = scopeEpoch.value
    const scoped = () => epoch === scopeEpoch.value && dirty()
    drafts.add(scoped)
    return () => { drafts.delete(scoped) }
  }
  const hasDrafts = () => [...drafts].some(dirty => dirty())
  const hasUnstoredDrafts = computed(hasDrafts)
  function permitLeave() {
    if (busy.value) { error.value = '正在保存，请稍候再离开。'; return false }
    if (localDrafts.saving.value) { error.value = '草稿正在自动保存，请稍候再离开。'; return false }
    return !hasDrafts() || window.confirm('有尚未保存的送印尼物料填写内容，确定离开并放弃这些内容吗？')
  }
  function beforeUnload(event: BeforeUnloadEvent) {
    if (busy.value || localDrafts.saving.value || hasDrafts()) { event.preventDefault(); event.returnValue = '' }
  }
  const removeFactoryGuard = registerFactoryChangeGuard(permitLeave)
  window.addEventListener('beforeunload', beforeUnload)
  let requestEpoch = 0
  const generation = ref(getAuthenticationGeneration())
  const boundary = () => { generation.value = getAuthenticationGeneration() }
  window.addEventListener('auth-session-boundary-changed', boundary)
  const identity = computed(() => {
    // /auth/me advances its clock on every refresh; that is not a scope change.
    const { server_now: _serverNow, ...authorizationIdentity } = auth.currentUser?.identity ?? {}
    return JSON.stringify([
      auth.currentUser?.id, authorizationIdentity, auth.authorizationVersion,
      auth.permissions, auth.grants, auth.effectiveAccess, generation.value,
    ])
  })
  const has = (permission: string) => permissions.value.includes(permission) || permissions.value.includes(`indonesia_material:${permission}`)
  const canWrite = computed(() => has('write'))
  const invalidPending = ref(false)
  const locked = computed(() => busy.value || !!pending.value || invalidPending.value || !factory.value || !localDrafts.ready.value)
  const kind = (type: RecordKind) => records.value.filter(record => record.kind === type && !record.data.deleted)
  const record = (id: string) => records.value.find(item => item.id === id)
  const materialName = (id: string) => { const data = record(id)?.data; return data ? `${data.code} · ${data.name}` : '物料资料缺失' }
  const orderName = (id: string) => { const data = record(id)?.data; return data ? `PO ${data.po_no || '未填写'} · ${data.contract_no} / ${data.item_no} · ${data.delivery_date}${data.batch ? '（历史批次 ' + data.batch + '）' : ''}` : '合同资料缺失' }
  const same = (epoch: number, selected: string) => epoch === scopeEpoch.value && selected === factory.value
  function restoredPending() {
    const saved = localDrafts.bucket.value.pending
    invalidPending.value = false
    if (!saved) { if (!busy.value) { pending.value = null; pendingCompletion = undefined } return }
    const command = saved.command
    const actions: Action[] = ['option_save', 'option_delete', 'option_restore', 'customer_delete', 'customer_restore', 'product_delete', 'product_restore', 'material_restore', 'customer_save', 'material_save', 'product_save', 'order_save', 'order_recalculate', 'demand_adjust', 'supply_save', 'supply_reply', 'output_material_refresh', 'receipt_confirm', 'allocate', 'reallocate', 'shipment_save', 'shipment_confirm', 'import_confirm', 'warehouse_import_confirm']
    if (command?.factory_id !== factory.value || !actions.includes(command.action) || typeof command.operation_id !== 'string' || command.operation_id.length < 16 || !command.data || !Number.isInteger(command.expected_version) || (saved.owner !== undefined && !draftKind(saved.owner))) {
      invalidPending.value = true; localDrafts.error.value = '上次提交凭据无法识别，原内容已保留，请联系管理员核对。'; return
    }
    if (pending.value?.operation_id !== command.operation_id) pendingCompletion = undefined
    pending.value = command
    error.value = '发现上次尚未确认的提交。请重试原操作核对结果，系统会沿用原编号，不会重新建单。'
  }
  localDrafts.onExternalChange(restoredPending)
  async function reloadDrafts() {
    const epoch = scopeEpoch.value, selected = factory.value
    if (await localDrafts.load() && same(epoch, selected)) {
      restoredPending()
      if (!pending.value && !invalidPending.value) for (const owner of owners.values()) { if (!same(epoch, selected)) return; await owner.flush() }
    }
  }
  function revokePrivateState() {
    // A denial on any endpoint invalidates already displayed data and all in-flight responses.
    scopeEpoch.value++; requestEpoch++; pendingCompletion = undefined
    records.value = []; optionDefaults.value = []; board.value = []; permissions.value = []; pending.value = null; shipmentTarget.value = null; boardStage.value = 'board'; supplyStage.value = 'warehouse'
    busy.value = false; loading.value = false; notice.value = ''
    localDrafts.reset()
    invalidPending.value = false
  }
  async function reload() {
    const selected = factory.value
    if (!selected) return
    const epoch = scopeEpoch.value
    const request = ++requestEpoch
    loading.value = true
    loadError.value = ''
    try {
      const result = await api.workspace(selected)
      if (!same(epoch, selected) || request !== requestEpoch) return
      records.value = result.records
      optionDefaults.value = result.option_defaults ?? []
      board.value = result.board
      permissions.value = result.permissions
    } catch (cause) {
      if (same(epoch, selected) && request === requestEpoch) {
        loadError.value = getApiErrorMessage(cause)
        if ([401, 403].includes(status(cause) ?? 0)) revokePrivateState()
      }
    } finally { if (same(epoch, selected) && request === requestEpoch) loading.value = false }
  }
  watch([factory, identity], () => {
    scopeEpoch.value++
    records.value = []; optionDefaults.value = []; board.value = []; permissions.value = []
    pending.value = null; pendingCompletion = undefined; error.value = ''; loadError.value = ''; notice.value = ''; busy.value = false; loading.value = false
    restoreTarget.value = null; shipmentTarget.value = null; boardStage.value = 'board'; supplyStage.value = 'warehouse'; invalidPending.value = false
    const epoch = scopeEpoch.value, selected = factory.value
    const user = auth.currentUser
    const storageKey = user?.id && selected ? JSON.stringify(['v1', user.id, user.identity?.employment_epoch ?? 1, selected]) : ''
    localDrafts.reset(storageKey)
    void (async () => {
      await reload()
      if (!same(epoch, selected) || !permissions.value.length || !storageKey) return
      if (await localDrafts.load(storageKey)) restoredPending()
    })()
  }, { immediate: true, flush: 'sync' })
  async function execute(command: Command, onCommitted?: () => void, owner?: DraftId, retry = false) {
    const epoch = scopeEpoch.value
    const selected = command.factory_id
    busy.value = true; error.value = ''; notice.value = ''
    await nextTick()
    if (!same(epoch, selected)) return false
    if (!await localDrafts.begin(command, owner, retry)) {
      if (same(epoch, selected)) await localDrafts.load()
      if (same(epoch, selected)) { busy.value = false; restoredPending(); error.value ||= localDrafts.error.value || '原操作编号未能安全保存，尚未发送业务提交。' }
      return false
    }
    if (!same(epoch, selected)) return false
    try {
      await api.command(command)
      if (!same(epoch, selected)) return false
      if (!await localDrafts.finish(command.operation_id, true)) {
        if (!same(epoch, selected)) return false
        pending.value = command; pendingCompletion = onCommitted
        error.value = '业务提交已返回，但本机操作凭据未清理完成。请重试原操作核对，勿重复新建。'
        return false
      }
      if (!same(epoch, selected)) return false
      pending.value = null
      pendingCompletion = undefined
      notice.value = '已保存，数据以服务器重新核算结果为准。'
      await reload()
      if (!same(epoch, selected)) return false
      if (onCommitted) onCommitted()
      else if (owner) ownerFor(owner)?.reset(owner)
      return true
    } catch (cause) {
      if (!same(epoch, selected)) return false
      const code = status(cause)
      if (code === 401 || code === 403) {
        revokePrivateState()
        error.value = getApiErrorMessage(cause)
        return false
      }
      // An interrupted response can follow a committed transaction. Freeze the exact operation for retry.
      if (!code || code === 408 || code >= 500) {
        pending.value = command
        pendingCompletion = onCommitted
        error.value = `${getApiErrorMessage(cause)}；保存结果尚未确认。请使用“重试原操作”，会复用原操作编号与原始内容。`
      } else {
        if (!await localDrafts.finish(command.operation_id, false)) {
          if (!same(epoch, selected)) return false
          pending.value = command; pendingCompletion = onCommitted
          error.value = '本机原操作凭据尚未释放，请重试原操作后再修改。'
          return false
        }
        if (!same(epoch, selected)) return false
        pending.value = null
        pendingCompletion = undefined
        error.value = code === 409 ? `${getApiErrorMessage(cause)}。请刷新并重新打开记录核对；系统不会自动覆盖。` : getApiErrorMessage(cause)
      }
      return false
    } finally { if (same(epoch, selected)) busy.value = false }
  }
  async function run(action: Action, data: Data, target?: MaterialRecord, onCommitted?: () => void, owner?: DraftId) {
    if (locked.value || !(action === 'receipt_confirm' ? has('receipt_confirm') : canWrite.value)) return false
    const command: Command = JSON.parse(JSON.stringify({
      factory_id: factory.value, operation_id: createRandomUuid(), action,
      entity_id: target?.id ?? null, expected_version: target?.version ?? 0, data,
    }))
    return execute(command, onCommitted, owner)
  }
  async function retry() {
    if (busy.value || !pending.value || pending.value.factory_id !== factory.value) return
    const permission = pending.value.action === 'receipt_confirm' ? 'receipt_confirm' : 'write'
    if (!has(permission)) { error.value = '当前权限不允许重试该操作。'; return }
    await execute(pending.value, pendingCompletion, localDrafts.bucket.value.pending?.owner, true)
  }
  async function preview(customer: string, recipient: string, file: File, warehouse?: string) {
    if (locked.value || !canWrite.value) return null
    const selected = factory.value; const epoch = scopeEpoch.value
    busy.value = true; error.value = ''; notice.value = ''
    try {
      const result = await api.preview(selected, customer, recipient, file, ...(warehouse === undefined ? [] : [warehouse]))
      return same(epoch, selected) ? result.record : null
    } catch (cause) {
      if (same(epoch, selected)) {
        error.value = getApiErrorMessage(cause)
        if ([401, 403].includes(status(cause) ?? 0)) revokePrivateState()
      }
      return null
    }
    finally { if (same(epoch, selected)) busy.value = false }
  }
  async function download(id: string, name: string, type: 'shipment' | 'asset' = 'shipment') {
    if (busy.value || !factory.value || (type === 'shipment' && !has('export'))) return
    const selected = factory.value; const epoch = scopeEpoch.value
    busy.value = true; error.value = ''
    try {
      const blob = await api.download(selected, id, type)
      if (!same(epoch, selected)) return
      const url = URL.createObjectURL(blob)
      const link = document.createElement('a'); link.href = url; link.download = name; link.click()
      setTimeout(() => URL.revokeObjectURL(url), 1000)
    } catch (cause) {
      if (same(epoch, selected)) {
        if ([401, 403].includes(status(cause) ?? 0)) {
          error.value = getApiErrorMessage(cause)
          revokePrivateState()
          return
        }
        const blob = (cause as { response?: { data?: unknown } })?.response?.data
        if (blob instanceof Blob) {
          try { const result = JSON.parse(await blob.text()); if (same(epoch, selected)) error.value = typeof result.detail === 'string' ? result.detail : '导出校验未通过，请核对出货资料。' }
          catch { if (same(epoch, selected)) error.value = getApiErrorMessage(cause) }
        } else error.value = getApiErrorMessage(cause)
      }
    } finally { if (same(epoch, selected)) busy.value = false }
  }
  onBeforeUnmount(() => { scopeEpoch.value++; pendingCompletion = undefined; drafts.clear(); owners.clear(); localDrafts.dispose(); removeFactoryGuard(); window.removeEventListener('beforeunload', beforeUnload); window.removeEventListener('auth-session-boundary-changed', boundary) })
  return reactive({ factory, records, optionDefaults, board, permissions, loading, busy, error, loadError, notice, pending, scopeEpoch, canWrite, locked, has, kind, record, materialName, orderName, reload, run, retry, preview, download, registerDraft, permitLeave, localDrafts, restoreTarget, shipmentTarget, boardStage, supplyStage, restoreDraft, deleteDraft, registerDraftOwner, reloadDrafts, hasUnstoredDrafts })
}
function status(cause: unknown) { return (cause as { response?: { status?: number } })?.response?.status }
export type MaterialsWorkspace = ReturnType<typeof createMaterialsWorkspace>
const key: InjectionKey<MaterialsWorkspace> = Symbol('indonesia-materials')
export function provideMaterials(workspace: MaterialsWorkspace) { provide(key, workspace) }
export function useMaterials() { const workspace = inject(key); if (!workspace) throw new Error('Missing materials workspace'); return workspace }
