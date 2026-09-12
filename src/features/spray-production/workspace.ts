import { defineStore } from 'pinia'
import { ref, shallowRef } from 'vue'
import { sprayProductionApi as api, type SprayEntity, type SpraySummary } from '@/api/sprayProduction'
import { createRandomUuid } from '@/lib/randomUuid'

export type Entity = SprayEntity
export const str = (row: Entity | undefined, key: string) => String(row?.[key] ?? '')
export const amount = (value: unknown) => Number(value ?? 0).toLocaleString('zh-CN', { maximumFractionDigits: 6 })
export const factories = [{ id: 'huaxing', name: '华兴' }, { id: 'huakang-a', name: '华康 A' }, { id: 'huakang-b', name: '华康 B' }, { id: 'huadeng', name: '华登' }]
export const capabilities = [{ value: 'manual', label: '手喷' }, { value: 'automatic', label: '自动' }, { value: 'pad', label: '移印' }, { value: 'uv', label: 'UV' }]
export const statusName = (value: unknown) => ({ planned: '待开工', running: '进行中', paused: '已暂停', completed: '已完成', cancelled: '已取消', active: '执行中', closed: '已结案', confirmed: '已确认', corrected: '已更正', provisional: '暂算待核', unpriced: '工资未定价', verified: '工资已核', archived: '历史归档', preview: '待映射' }[String(value)] ?? String(value ?? ''))
export const localDate = () => new Intl.DateTimeFormat('en-CA', { timeZone: 'Asia/Shanghai' }).format(new Date())
export const errorText = (error: unknown) => {
  const e = error as { response?: { data?: { detail?: unknown }; status?: number }; message?: string }
  const detail = e.response?.data?.detail
  return e.response?.status === 403 ? '当前账号没有此厂区的授权数据。请联系厂区管理员。' : typeof detail === 'string' ? detail : e.message ?? '接口暂不可用，请保留草稿并重试'
}

export const useSprayWorkspace = defineStore('spray-production', () => {
  const factory = ref('')
  const summary = shallowRef<SpraySummary | null>(null)
  const data = shallowRef<Record<string, Entity[]>>({})
  const balances = shallowRef<Record<string, Record<string, string>>>({})
  const loading = ref(false), busy = ref(false), error = ref(''), notice = ref(''), selection = ref('')
  const truncated = ref(false)
  let controller: AbortController | undefined
  let generation = 0
  const pendingOperations = new Map<string, string>()
  const items = (kind: string) => data.value[kind] ?? []
  const find = (kind: string, id: unknown) => items(kind).find(v => v.id === id)
  const can = (permission: string) => summary.value?.permissions.includes(permission) ?? false
  const lineLabel = (line: Entity | undefined) => `${str(line, 'product_no')} · ${str(line, 'part_name')}`
  const batchLabel = (batch: Entity | undefined) => `${lineLabel(find('lines', batch?.line_id))} / ${str(batch, 'document_no')} #${str(batch, 'source_line')}`
  const taskLabel = (task: Entity | undefined) => `${batchLabel(find('batches', task?.batch_id))} · ${str(find('steps', task?.step_id), 'name')}`
  const stateName = (key: string) => {
    const [state, id] = key.split(':')
    const label = { ready: '待投入', reserved: '已预留', running: '执行占用', rework: '待返工', held: '待判', finished: '合格待交付', scrap: '报废', shipped: '净已送出', rejected: '拒收', 'receipt-held': '来料待检', 'return-held': '客户退回待判' }[state ?? ''] ?? state
    return `${label}${id && ['ready', 'rework', 'held'].includes(state ?? '') ? ' · ' + str(find('steps', id), 'name') : ''}`
  }
  async function load(scope = factory.value) {
    controller?.abort(); const current = ++generation; controller = new AbortController()
    const changed = factory.value !== scope
    factory.value = scope; error.value = ''; loading.value = true
    if (changed) { data.value = {}; balances.value = {}; summary.value = null; selection.value = ''; notice.value = '' }
    if (!factories.some(f => f.id === scope)) { loading.value = false; return }
    try {
      const signal = controller.signal
      const snapshot = await api.summary(scope, signal)
      const collections = ['orders', 'lines', 'steps', 'resources', 'batches', 'tasks', 'reports', 'report-lines', 'shipments', 'shipment-lines', 'returnables']
      if (snapshot.permissions.includes('cost_read')) collections.push('rates', 'purchases', 'material-events', 'settlements', 'imports')
      const [pages, stock] = await Promise.all([Promise.all(collections.map(async kind => [kind, await api.collection(scope, kind, signal)] as const)), api.balances(scope, signal)])
      if (current !== generation) return
      summary.value = snapshot; data.value = Object.fromEntries(pages.map(([kind, page]) => [kind, page.items])); balances.value = stock
      truncated.value = pages.some(([, page]) => page.total > page.items.length)
    } catch (e) { if (current === generation && !controller.signal.aborted) error.value = errorText(e) }
    finally { if (current === generation) loading.value = false }
  }
  async function command(action: string, payload: Record<string, unknown>) {
    if (busy.value) return null
    const scope = factory.value
    busy.value = true; error.value = ''; notice.value = ''
    try {
      const signature = JSON.stringify([scope, action, payload])
      const operationId = pendingOperations.get(signature) ?? createRandomUuid()
      pendingOperations.set(signature, operationId)
      const result = await api.command(scope, action, { operation_id: operationId, ...payload })
      pendingOperations.delete(signature)
      if (factory.value !== scope) return result
      notice.value = '记录已保存'; await load(scope)
      return result
    } catch (e) { if (factory.value === scope) error.value = errorText(e); return null }
    finally { busy.value = false }
  }
  function clear() { controller?.abort(); generation++; factory.value = ''; summary.value = null; data.value = {}; balances.value = {}; selection.value = ''; error.value = '' }
  return { factory, summary, data, balances, loading, busy, error, notice, selection, truncated, items, find, can, lineLabel, batchLabel, taskLabel, stateName, load, command, clear }
})
