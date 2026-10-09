import { computed, inject, provide, reactive, ref, shallowRef, watch, onScopeDispose, type InjectionKey } from 'vue'
import { useRoute } from 'vue-router'
import { useAppStore } from '@/stores/app'
import { useAuthStore } from '@/stores/auth'
import { http } from '@/lib/http'
import { isAxiosError } from 'axios'
import { ContextFence } from './contextFence'
import { isSprayFactory, sprayEnabled, today, type Entity, type Envelope, type SprayFactory } from './contracts'

class StaleContext extends Error {}
export interface PendingOperation { operation_id: string; factory: SprayFactory; path: string; userId: string; authorizationVersion: number; accessKey: string; canRetry: boolean; body: Record<string, unknown>; state: 'sending' | 'uncertain' | 'confirmed'; result?: Entity }

export function createSprayWorkspace() {
  const route = useRoute(), app = useAppStore(), auth = useAuthStore()
  const factory = computed(() => isSprayFactory(route.query.factory) && route.query.factory === app.activeFactoryId ? route.query.factory : null)
  const businessDate = ref(today())
  const relatedDemand = computed(() => typeof route.query.demand === 'string' ? route.query.demand : '')
  const permissions = ref<string[]>([])
  const data = shallowRef<Record<string, Entity[]>>({})
  const totals = reactive<Record<string, number>>({})
  const activeCollections = ref<string[]>([])
  const paging = reactive<Record<string, { page: number; params: Record<string, unknown> }>>({})
  const loading = ref(false), error = ref(''), ready = ref(false), refreshing = ref(false)
  const asOf = ref(''), revision = ref(0), notification = ref('')
  const passportId = ref<string | null>(null)
  const dirty = ref(false)
  const actionQuestion = ref<{ message: string; requiresReason: boolean } | null>(null)
  let answerAction: ((answer: string | null) => void) | null = null
  function finishAction(answer: string | null) { actionQuestion.value = null; answerAction?.(answer); answerAction = null }
  function askAction(message: string, requiresReason: boolean): Promise<string | null> {
    finishAction(null)
    actionQuestion.value = { message, requiresReason }
    return new Promise(resolve => { answerAction = resolve })
  }
  const confirmDiscard = async (message: string) => (await askAction(message, false)) !== null
  const promptReason = (message: string) => askAction(message, true)
  const saveDraft = shallowRef<(() => Promise<boolean>) | null>(null)
  const pending = reactive(new Map<string, PendingOperation>())
  const fence = new ContextFence()
  const contextVersion = ref(0)
  const valid = computed(() => factory.value !== null && auth.isAuthenticated && sprayEnabled())
  const can = (action: string) => valid.value && permissions.value.includes(action)
  const accessKey = () => JSON.stringify(auth.effectiveAccess)
  const items = <T extends Entity = Entity>(key: string) => (data.value[key] ?? []) as T[]

  function explain(cause: unknown): string {
    if (isAxiosError(cause)) {
      const body = cause.response?.data as { message?: string; field_errors?: Record<string, string> } | undefined
      if (body?.field_errors && Object.keys(body.field_errors).length) return Object.values(body.field_errors).join('；')
      return body?.message ?? (cause.response ? '请求失败，请重试' : '网络连接中断，请检查连接后重试')
    }
    return cause instanceof Error ? cause.message : String(cause)
  }

  async function query<T>(path: string, params: Record<string, unknown> = {}, key = path): Promise<Envelope<T>> {
    if (!valid.value || !factory.value) throw new StaleContext('请先选择有效工厂')
    const ticket = fence.begin(key)
    try {
      const related = ['demands','demand-lines','batches','stock','tasks','reports','forecasts','deliveries','delivery-lines','returns','settlements','settlement-lines','schedule/window'].includes(path)
      const response = await http.get<Envelope<T>>('/spray-operations/' + path, { params: { ...params, factory_id: factory.value, ...(related && relatedDemand.value ? {demand_id:relatedDemand.value} : {}) }, signal: ticket.signal })
      if (!fence.current(ticket)) throw new StaleContext('请求上下文已变化')
      if (response.data.meta.factory_id !== ticket.factory || response.data.meta.data_mode !== 'live') throw new Error('服务返回的数据上下文不一致，已停止展示')
      revision.value = response.data.meta.factory_revision
      asOf.value = response.data.meta.as_of
      return response.data
    } finally { fence.finish(ticket) }
  }

  async function load(keys: string[], params: Record<string, unknown> = {}) {
    const version = contextVersion.value
    loading.value = true
    error.value = ''
    const results = await Promise.allSettled(keys.map(async key => {
      const response = await query<Entity[]>(key, { page_size: 200, ...params }, key)
      if (version !== contextVersion.value) return
      data.value = { ...data.value, [key]: response.data }
      totals[key] = response.pagination?.total ?? response.data.length
      if (params.page === undefined && params.page_size === undefined && !['activity','demands'].includes(key)) paging[key] = { page: 1, params }
    }))
    if (version !== contextVersion.value) return
    const failure = results.find(result => result.status === 'rejected' && !(result.reason instanceof StaleContext) && !(isAxiosError(result.reason) && result.reason.code === 'ERR_CANCELED'))
    if (failure?.status === 'rejected') error.value = explain(failure.reason)
    loading.value = false
  }

  async function loadMore(key: string) {
    const current = paging[key]
    if (!current || loading.value) return
    const version = contextVersion.value
    loading.value = true
    try {
      const response = await query<Entity[]>(key, { ...current.params, page_size: 200, page: current.page + 1 }, key)
      if (version !== contextVersion.value) return
      const merged = new Map([...items(key), ...response.data].map(row => [row.id, row]))
      data.value = { ...data.value, [key]: [...merged.values()] }
      current.page++
      totals[key] = response.pagination?.total ?? merged.size
    } catch (cause) { if (version === contextVersion.value) error.value = explain(cause) }
    finally { if (version === contextVersion.value) loading.value = false }
  }

  async function retryAccess() {
    error.value = ''
    try {
      const result = await query<{ permissions: string[] }>('access')
      permissions.value = result.data.permissions
      ready.value = true
    } catch (cause) { if (!(cause instanceof StaleContext)) error.value = explain(cause) }
  }

  async function command<T extends Entity = Entity>(path: string, values: Record<string, unknown>, expectedVersion = 0, operationId?: string): Promise<T> {
    if (!valid.value || !factory.value) throw new Error('工厂上下文已失效')
    const unresolved = [...pending.values()].find(op => op.path === path && op.factory === factory.value && op.userId === auth.currentUser?.id && op.state !== 'confirmed')
    if (!operationId && unresolved) {
      const normalize = (body: Record<string, unknown>) => JSON.stringify(Object.fromEntries(Object.entries(body).filter(([key]) => !['operation_id','factory_id','expected_version'].includes(key)).sort(([a],[b])=>a.localeCompare(b))))
      if (normalize(unresolved.body) !== normalize(values)) throw new Error('上一笔同类保存结果待核对，原填写内容已保留；请先查询回执再提交新内容')
      operationId = unresolved.operation_id
    }
    operationId ??= crypto.randomUUID()
    const existing = pending.get(operationId)
    if (existing?.state === 'confirmed') return existing.result as T
    if (existing && (existing.factory !== factory.value || existing.userId !== auth.currentUser?.id)) throw new Error('请回到原工厂核对该操作的回执')
    if (existing && !existing.canRetry) throw new Error('权限已变化，原内容已清除；请核对服务器回执后重新填写')
    const operation: PendingOperation = existing ?? { operation_id: operationId, factory: factory.value, userId: auth.currentUser?.id ?? '', authorizationVersion: auth.authorizationVersion, accessKey: accessKey(), canRetry: true, path, body: { ...values, factory_id: factory.value, expected_version: expectedVersion, operation_id: operationId }, state: 'sending' }
    pending.set(operationId, operation)
    fence.wrote()
    const ticket = fence.begin('command:' + operationId)
    try {
      // Do not abort a write on navigation: its outcome must be reconciled using
      // the original operation ID. Never send a second ID after a timeout.
      const response = await http.post<Envelope<T>>('/spray-operations/' + operation.path, operation.body)
      operation.state = 'confirmed'
      operation.result = operation.canRetry && operation.accessKey === accessKey() ? response.data.data : undefined
      if (fence.sameContext(ticket)) {
        fence.wrote()
        revision.value = response.data.meta.factory_revision
        notification.value = '已保存 · 操作回执 ' + operationId.slice(0, 8)
        dirty.value = false
      }
      if (!fence.sameContext(ticket)) throw new StaleContext('操作已在原工厂完成；请回到原工厂核对回执')
      return response.data.data
    } catch (cause) {
      if (isAxiosError(cause) && (!cause.response || cause.response.status >= 500)) operation.state = 'uncertain'
      else if (!(cause instanceof StaleContext)) pending.delete(operationId)
      if (fence.sameContext(ticket)) error.value = explain(cause)
      throw cause
    } finally { fence.finish(ticket) }
  }

  async function resolveOperation(operation: PendingOperation) {
    if (operation.factory !== factory.value) throw new Error('请先回到原工厂核对操作结果')
    try {
      const result = await query<Entity>('commands/' + operation.operation_id)
      operation.state = 'confirmed'; operation.result = result.data
      notification.value = '已找到成功回执，可刷新查看结果'
      dirty.value = false
    } catch (cause) {
      if (isAxiosError(cause) && cause.response?.status === 404) {
        await command(operation.path, operation.body, Number(operation.body.expected_version), operation.operation_id)
      } else throw cause
    }
  }

  async function refresh() {
    refreshing.value = true
    await load(Object.keys(data.value))
    refreshing.value = false
  }

  async function download(kind: string, extra: Record<string, unknown> = {}) {
    const context = contextVersion.value
    const artifact = await command<Entity>('exports', { kind, base_revision: revision.value, ...extra })
    const response = await http.get<Blob>(`/spray-operations/exports/${artifact.id}/download`, { params: { factory_id: artifact.factory_id }, responseType: 'blob' })
    if (context !== contextVersion.value) return
    const url = URL.createObjectURL(response.data)
    const anchor = document.createElement('a')
    anchor.href = url; anchor.download = String(artifact.name); anchor.click()
    setTimeout(() => URL.revokeObjectURL(url), 1000)
    notification.value = '导出已生成并冻结，可按原回执重复下载'
  }

  watch([factory, () => auth.currentUser?.id, () => auth.authorizationVersion, () => auth.isAuthenticated, () => JSON.stringify(auth.effectiveAccess)], async () => {
    contextVersion.value++
    finishAction(null)
    fence.switch({ userId: auth.currentUser?.id ?? '', factory: factory.value ?? '', authorizationVersion: auth.authorizationVersion })
    data.value = {}; permissions.value = []; ready.value = false; error.value = ''; asOf.value = ''; passportId.value = null
    for (const key of Object.keys(totals)) delete totals[key]
    for (const key of Object.keys(paging)) delete paging[key]
    // Revocation/logout clears values and results; no sensitive localStorage cache.
    for (const [key, operation] of pending) {
      if (operation.userId !== auth.currentUser?.id || !auth.isAuthenticated) pending.delete(key)
      else if (operation.authorizationVersion !== auth.authorizationVersion || operation.accessKey !== accessKey()) {
        operation.body = {}; operation.result = undefined; operation.canRetry = false
        if (operation.state === 'confirmed') pending.delete(key)
      }
    }
    if (!valid.value) return
    const context = contextVersion.value
    try {
      const result = await query<{ permissions: string[] }>('access')
      permissions.value = result.data.permissions
      ready.value = true
    } catch (cause) {
      if (context === contextVersion.value && !(cause instanceof StaleContext) && !(isAxiosError(cause) && cause.code === 'ERR_CANCELED')) error.value = explain(cause)
    }
  }, { immediate: true })
  onScopeDispose(() => { finishAction(null); fence.abort(); data.value = {}; pending.clear() })
  return { factory, businessDate, relatedDemand, permissions, data, totals, activeCollections, paging, loadMore, retryAccess, actionQuestion, finishAction, confirmDiscard, promptReason, loading, error, ready, asOf, revision, notification, passportId, dirty, saveDraft, pending, valid, contextVersion, can, items, query, load, command, refresh, refreshing, explain, resolveOperation, download }
}

export type SprayWorkspace = ReturnType<typeof createSprayWorkspace>
const KEY: InjectionKey<SprayWorkspace> = Symbol('spray-workspace')
export function provideSprayWorkspace() { const value = createSprayWorkspace(); provide(KEY, value); return value }
export function useSprayWorkspace() { const value = inject(KEY); if (!value) throw new Error('喷油工作区上下文缺失'); return value }
