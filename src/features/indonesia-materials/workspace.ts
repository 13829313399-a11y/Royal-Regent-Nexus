import { computed, inject, onBeforeUnmount, provide, reactive, ref, watch, type InjectionKey } from 'vue'
import { useAppStore } from '@/stores/app'
import { useAuthStore } from '@/stores/auth'
import { getApiErrorMessage } from '@/lib/http'
import { getAuthenticationGeneration } from '@/lib/authenticationGeneration'
import { createRandomUuid } from '@/lib/randomUuid'
import { indonesiaMaterialsApi as api, type Action, type BoardOrder, type Command, type Data, type MaterialRecord, type RecordKind } from '@/api/indonesiaMaterials'

export function createMaterialsWorkspace() {
  const app = useAppStore()
  const auth = useAuthStore()
  const factory = computed(() => app.activeFactoryId === 'group' ? '' : app.activeFactoryId)
  const records = ref<MaterialRecord[]>([])
  const board = ref<BoardOrder[]>([])
  const permissions = ref<string[]>([])
  const loading = ref(false)
  const busy = ref(false)
  const error = ref('')
  const loadError = ref('')
  const notice = ref('')
  const pending = ref<Command | null>(null)
  const scopeEpoch = ref(0)
  const formEpoch = ref(0)
  let requestEpoch = 0
  const generation = ref(getAuthenticationGeneration())
  const boundary = () => { generation.value = getAuthenticationGeneration() }
  window.addEventListener('auth-session-boundary-changed', boundary)
  const identity = computed(() => JSON.stringify([
    auth.currentUser?.id, auth.currentUser?.identity, auth.authorizationVersion,
    auth.permissions, auth.grants, auth.effectiveAccess, generation.value,
  ]))
  const has = (permission: string) => permissions.value.includes(permission) || permissions.value.includes(`indonesia_material:${permission}`)
  const canWrite = computed(() => has('write'))
  const locked = computed(() => busy.value || !!pending.value || !factory.value)
  const kind = (type: RecordKind) => records.value.filter(record => record.kind === type)
  const record = (id: string) => records.value.find(item => item.id === id)
  const materialName = (id: string) => { const data = record(id)?.data; return data ? `${data.code} · ${data.name}` : '物料资料缺失' }
  const orderName = (id: string) => { const data = record(id)?.data; return data ? `${data.contract_no} / ${data.batch} / ${data.item_no}` : '合同资料缺失' }
  const same = (epoch: number, selected: string) => epoch === scopeEpoch.value && selected === factory.value
  function revokePrivateState() {
    // A denial on any endpoint invalidates already displayed data and all in-flight responses.
    scopeEpoch.value++; requestEpoch++; formEpoch.value++
    records.value = []; board.value = []; permissions.value = []; pending.value = null
    busy.value = false; loading.value = false; notice.value = ''
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
    records.value = []; board.value = []; permissions.value = []
    pending.value = null; error.value = ''; loadError.value = ''; notice.value = ''; busy.value = false; loading.value = false
    void reload()
  }, { immediate: true, flush: 'sync' })
  async function execute(command: Command, retry: boolean) {
    const epoch = scopeEpoch.value
    const selected = command.factory_id
    busy.value = true; error.value = ''; notice.value = ''
    try {
      await api.command(command)
      if (!same(epoch, selected)) return false
      pending.value = null
      notice.value = '已保存，数据以服务器重新核算结果为准。'
      if (retry) formEpoch.value++
      await reload()
      return same(epoch, selected)
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
        error.value = `${getApiErrorMessage(cause)}；保存结果尚未确认。请使用“重试原操作”，会复用原操作编号与原始内容。`
      } else {
        pending.value = null
        error.value = code === 409 ? `${getApiErrorMessage(cause)}。请刷新并重新打开记录核对；系统不会自动覆盖。` : getApiErrorMessage(cause)
      }
      return false
    } finally { if (same(epoch, selected)) busy.value = false }
  }
  async function run(action: Action, data: Data, target?: MaterialRecord) {
    if (locked.value || !(action === 'receipt_confirm' ? has('receipt_confirm') : canWrite.value)) return false
    const command: Command = JSON.parse(JSON.stringify({
      factory_id: factory.value, operation_id: createRandomUuid(), action,
      entity_id: target?.id ?? null, expected_version: target?.version ?? 0, data,
    }))
    return execute(command, false)
  }
  async function retry() {
    if (busy.value || !pending.value || pending.value.factory_id !== factory.value) return
    const permission = pending.value.action === 'receipt_confirm' ? 'receipt_confirm' : 'write'
    if (!has(permission)) { error.value = '当前权限不允许重试该操作。'; return }
    await execute(pending.value, true)
  }
  async function preview(customer: string, recipient: string, file: File) {
    if (locked.value || !canWrite.value) return null
    const selected = factory.value; const epoch = scopeEpoch.value
    busy.value = true; error.value = ''; notice.value = ''
    try {
      const result = await api.preview(selected, customer, recipient, file)
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
  onBeforeUnmount(() => { scopeEpoch.value++; window.removeEventListener('auth-session-boundary-changed', boundary) })
  return reactive({ factory, records, board, permissions, loading, busy, error, loadError, notice, pending, scopeEpoch, formEpoch, canWrite, locked, has, kind, record, materialName, orderName, reload, run, retry, preview, download })
}
function status(cause: unknown) { return (cause as { response?: { status?: number } })?.response?.status }
export type MaterialsWorkspace = ReturnType<typeof createMaterialsWorkspace>
const key: InjectionKey<MaterialsWorkspace> = Symbol('indonesia-materials')
export function provideMaterials(workspace: MaterialsWorkspace) { provide(key, workspace) }
export function useMaterials() { const workspace = inject(key); if (!workspace) throw new Error('Missing materials workspace'); return workspace }
