import { computed, inject, onBeforeUnmount, provide, reactive, ref, shallowRef, watch, type InjectionKey } from 'vue'
import { useRoute } from 'vue-router'
import { useAuthStore } from '@/stores/auth'
import { useAppStore } from '@/stores/app'
import { createRandomUuid } from '@/lib/randomUuid'
import { ContextFence, UV_FACTORY, type Entity, type Envelope, type Meta, type WorkspaceSnapshot } from './contracts'

export class UvError extends Error {
  constructor(message: string, public status = 0, public code = '', public fields: Record<string, string> = {}) { super(message) }
}

export function createUvWorkspace() {
  const auth = useAuthStore(), app = useAppStore(), route = useRoute()
  const data = shallowRef<Record<string, Entity[]>>({})
  const liveData = shallowRef<Record<string, Entity[]>>({})
  const loaded = new Set<string>()
  const meta = shallowRef<Meta | null>(null)
  const permissions = ref<string[]>([]), error = ref(''), errorCode = ref(''), notification = ref('')
  const loading = ref(false), refreshing = ref(false), ready = ref(false), offline = ref(!navigator.onLine)
  const selectedTaskId = ref<string | null>(null), contextVersion = ref(0)
  const pagination = reactive<Record<string, { total: number; next_cursor: string | null; has_more: boolean }>>({})
  const fence = new ContextFence()
  const valid = computed(() => route.query.factory === UV_FACTORY && app.activeFactoryId === UV_FACTORY && auth.isAuthenticated)
  const can = (action: string) => valid.value && permissions.value.includes(action)
  const items = (name: string) => data.value[name] ?? []
  let live: EventSource | undefined, reconnect: ReturnType<typeof setTimeout> | undefined
  let streamWatch: ReturnType<typeof setInterval> | undefined
  let initializedAuthorization = -1

  function stopLive() { live?.close(); live = undefined; clearTimeout(reconnect); reconnect = undefined; clearInterval(streamWatch); streamWatch=undefined }
  function clear() {
    stopLive(); fence.clear(); data.value = {}; liveData.value = {}; loaded.clear(); meta.value = null; permissions.value = []; selectedTaskId.value = null
    ready.value = false; contextVersion.value++; initializedAuthorization = -1
    Object.keys(pagination).forEach(key => delete pagination[key])
  }
  async function request<T>(path: string, options: RequestInit = {}, params: Record<string, string> = {}): Promise<Envelope<T>> {
    if (!valid.value) throw new UvError('请明确选择华康 A 厂区', 422, 'factory_required')
    const ticket = fence.begin()
    const query = new URLSearchParams({ factory_id:UV_FACTORY, ...params })
    try {
      const response = await fetch('/api/uv-operations/'+path+'?'+query, { credentials:'same-origin', ...options, signal:ticket.controller.signal })
      const body = await response.json().catch(() => {
        if (!fence.current(ticket)) throw new DOMException('上下文已变化', 'AbortError')
        offline.value=true
        throw new UvError('服务暂时不可用，已保留最后一次快照，请稍后重试',response.status>=500?response.status:502,'service_unavailable')
      })
      if (!fence.current(ticket)) throw new DOMException('上下文已变化', 'AbortError')
      if (!response.ok) {
        if(response.status>=500) offline.value=true
        if ([401,403].includes(response.status)) {
          clear(); error.value = body.message ?? '当前授权已失效'; errorCode.value = 'permission_denied'
          void auth.refreshSession()
        }
        throw new UvError(body.message ?? '请求失败', response.status, body.code, body.field_errors ?? {})
      }
      const envelope = body as Envelope<T>
      if (envelope.meta.factory_id !== UV_FACTORY) throw new UvError('服务返回了不同厂区的数据，已停止展示')
      if (initializedAuthorization >= 0 && envelope.meta.authorization_version !== initializedAuthorization) {
        clear(); void auth.refreshSession(); throw new UvError('授权已变更，请重新载入工作区', 403)
      }
      return envelope
    } catch(cause) {
      if(!fence.current(ticket)) throw new DOMException('上下文已变化','AbortError')
      if(cause instanceof TypeError) {offline.value=true;throw new UvError('无法连接服务，请检查网络后重试',503,'connection_error')}
      throw cause
    } finally { fence.finish(ticket) }
  }
  function applySnapshot(envelope: Envelope<WorkspaceSnapshot>) {
    if (meta.value && envelope.meta.view_revision < meta.value.view_revision) return
    meta.value = envelope.meta
    for (const name of ['machines','tasks','schedule','shifts','batches','runs'] as const) {
      liveData.value = { ...liveData.value, [name]:envelope.data[name] }
      if (!loaded.has(name)) data.value = { ...data.value, [name]:envelope.data[name] }
    }
  }
  async function refresh() {
    if (!valid.value || !ready.value) return
    refreshing.value = true
    try { applySnapshot(await request<WorkspaceSnapshot>('workspace')); const reconnectNeeded=offline.value; offline.value=false; error.value = ''; errorCode.value = ''; if(reconnectNeeded)startLive() }
    catch (cause) { if (!(cause instanceof DOMException && cause.name === 'AbortError')) error.value = explain(cause) }
    finally { refreshing.value = false }
  }
  function startLive() {
    stopLive()
    if (!ready.value || !valid.value || document.hidden || !navigator.onLine) return
    const generation = fence.generation
    live = new EventSource('/api/uv-operations/live?factory_id='+UV_FACTORY, { withCredentials:true })
    let lastStreamAt=Date.now()
    streamWatch=setInterval(()=>{if(generation===fence.generation&&Date.now()-lastStreamAt>20000) offline.value=true},5000)
    const receive = (event: MessageEvent) => {
      if (generation !== fence.generation) return
      let envelope: Envelope<WorkspaceSnapshot>
      try { envelope = JSON.parse(event.data) as Envelope<WorkspaceSnapshot> } catch { offline.value=true; return }
      if (envelope.meta.authorization_version !== initializedAuthorization) { clear(); void auth.refreshSession(); return }
      lastStreamAt=Date.now(); applySnapshot(envelope); offline.value = false
    }
    live.addEventListener('reset', receive)
    live.addEventListener('snapshot', receive)
    live.addEventListener('access_revoked', () => { if(generation!==fence.generation)return; clear(); error.value='当前授权已失效'; errorCode.value='permission_denied'; void auth.refreshSession() })
    live.addEventListener('unavailable', () => { if(generation!==fence.generation)return; stopLive(); offline.value=true; reconnect=setTimeout(startLive,10000) })
    live.onerror = () => { if(generation===fence.generation) offline.value=true }
  }
  async function initialize() {
    clear(); error.value=''; errorCode.value=''
    if (!valid.value) { error.value='UV 打印仅在明确选择华康 A 时开放'; errorCode.value='factory_required'; return }
    loading.value=true
    try {
      const access = await request<{permissions:string[]}>('access')
      initializedAuthorization=access.meta.authorization_version
      permissions.value=access.data.permissions; meta.value=access.meta; ready.value=true
      await refresh(); startLive()
    } catch (cause) { if (!(cause instanceof DOMException && cause.name==='AbortError')) { error.value=explain(cause); errorCode.value=cause instanceof UvError ? cause.code : 'connection_error' } }
    finally { loading.value=false }
  }
  async function load(names: string[], append = false) {
    const generation = fence.generation
    const results = await Promise.allSettled(names.map(async name => {
      const cursor = append ? pagination[name]?.next_cursor : null
      const response = await request<Entity[]>(name, {}, cursor ? { cursor } : {})
      if (generation !== fence.generation) return
      data.value = { ...data.value, [name]:append ? [...items(name), ...response.data] : response.data }
      loaded.add(name)
      if (response.pagination) pagination[name] = response.pagination
    }))
    const failure=results.find((x):x is PromiseRejectedResult=>x.status==='rejected')
    if (failure) throw failure.reason
  }
  async function command<T = Entity>(path: string, values: Record<string, unknown>, operationId = createRandomUuid(), method = 'POST'): Promise<T> {
    const result = await request<T>(path, { method, headers:{'Content-Type':'application/json'}, body:JSON.stringify({factory_id:UV_FACTORY, operation_id:operationId, expected_version:0, ...values}) })
    notification.value='已保存，业务记录和操作回执已确认'
    await refresh()
    return result.data
  }
  function explain(cause: unknown) { return cause instanceof Error ? cause.message : '服务暂时不可用，请保留输入后重试' }
  function online() { offline.value=!navigator.onLine; if(navigator.onLine) { void refresh(); startLive() } else stopLive() }
  function visibility() { if(document.hidden) stopLive(); else { void refresh(); startLive() } }
  // Refreshing an unchanged session must not remount pages and discard a draft.
  watch(() => JSON.stringify([auth.currentUser?.id, auth.authorizationVersion, auth.effectiveAccess, route.query.factory, app.activeFactoryId]), () => { void initialize() }, { immediate:true })
  window.addEventListener('online',online); window.addEventListener('offline',online); document.addEventListener('visibilitychange',visibility)
  onBeforeUnmount(() => { clear(); window.removeEventListener('online',online); window.removeEventListener('offline',online); document.removeEventListener('visibilitychange',visibility) })
  return {data,liveData,meta,permissions,error,errorCode,notification,loading,refreshing,ready,offline,selectedTaskId,contextVersion,pagination,valid,can,items,request,refresh,initialize,load,command,explain,clear}
}
export type UvWorkspace = ReturnType<typeof createUvWorkspace>
const key: InjectionKey<UvWorkspace> = Symbol('uv-operations')
export function provideUvWorkspace() { const workspace=createUvWorkspace(); provide(key,workspace); return workspace }
export function useUvWorkspace() { const workspace=inject(key); if(!workspace) throw new Error('UV workspace provider missing'); return workspace }
