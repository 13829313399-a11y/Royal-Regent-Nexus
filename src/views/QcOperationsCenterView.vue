<script setup lang="ts">
import { computed, onBeforeUnmount, ref, watch } from 'vue'
import { RouterLink, useRoute, useRouter } from 'vue-router'
import { Button } from '@/components/ui/button'
import { factoryContexts, isFactoryContextId, productionFactoryContextIds, type FactoryContextId } from '@/data/enterpriseMock'
import { http, getApiErrorMessage } from '@/lib/http'
import { registerFactoryChangeGuard } from '@/lib/factoryChangeGuard'
import { useAppStore } from '@/stores/app'
import { useAuthStore } from '@/stores/auth'

type FactoryOption = { id: string; label: string }
interface QcFrame extends Window {
  __QC_CONFIRM_FACTORY_LEAVE?: () => boolean
  __QC_CURRENT_PAGE?: () => string
  __QC_SET_FACTORY_BRIDGE?: (bridge: {
    factory: string; options: FactoryOption[]; page: string
    select: (factory: string) => Promise<void>
  }) => void
}
const route = useRoute()
const router = useRouter()
const app = useAppStore()
const auth = useAuthStore()
const contextId = computed(() => {
  const candidate = route.query.factory ?? app.activeFactoryId
  return typeof candidate === 'string' && isFactoryContextId(candidate) ? candidate : 'group'
})
const factoryId = computed(() => productionFactoryContextIds.includes(contextId.value as never) ? contextId.value : '')
const factoryName = computed(() => factoryContexts.find(item => item.id === contextId.value)?.shortName ?? '')
const options = computed<FactoryOption[]>(() => [
  { id: 'group', label: '集团' },
  ...factoryContexts.filter(item => productionFactoryContextIds.includes(item.id as never)
    && auth.can('qc_inspection:read', item.id, 'qc')).map(item => ({ id: item.id, label: item.shortName })),
])
const frame = ref<HTMLIFrameElement | null>(null)
const frameUrl = ref('')
const loading = ref(false)
const ready = ref(false)
const error = ref('')
const switching = ref(false)
const frameVersion = ref(0)
let page = 'dashboard'
let sequence = 0
function child() { return frame.value?.contentWindow as QcFrame | null }
function permitLeave() {
  try { return child()?.__QC_CONFIRM_FACTORY_LEAVE?.() ?? true }
  catch { window.alert('无法确认 QC 保存状态，请先核对当前记录。'); return false }
}
const unregister = registerFactoryChangeGuard(permitLeave)
onBeforeUnmount(() => { unregister(); sequence++ })
async function selectFactory(value: string) {
  if (switching.value || value === contextId.value) return
  if (!options.value.some(option => option.id === value)) return
  switching.value = true
  try {
    // The router asks the registered draft guard before updating the shared store.
    await router.replace({ path: route.path, query: { ...route.query, factory: value as FactoryContextId }, hash: route.hash })
  } catch (reason) { error.value = getApiErrorMessage(reason) }
  finally { switching.value = false }
}
async function onSelect(event: Event) {
  const select = event.target as HTMLSelectElement
  const value = select.value
  select.value = contextId.value
  await selectFactory(value)
  select.value = contextId.value
}
function connectFrame(restorePage = true) {
  const target = child()
  if (!target || !ready.value) return
  const identity = `${contextId.value}:${auth.currentUser?.id}:${auth.authorizationVersion}`
  target.__QC_SET_FACTORY_BRIDGE?.({ factory: contextId.value, options: options.value, page: restorePage ? page : (target.__QC_CURRENT_PAGE?.() || page),
    select: async value => {
      if (target !== child() || identity !== `${contextId.value}:${auth.currentUser?.id}:${auth.authorizationVersion}`) return
      await selectFactory(value)
    },
  })
}
async function refresh() {
  const current = ++sequence
  try { page = child()?.__QC_CURRENT_PAGE?.() || page } catch { /* A replaced frame has no reusable view. */ }
  ready.value = false
  frameUrl.value = ''
  error.value = ''
  if (!factoryId.value) { loading.value = false; return }
  loading.value = true
  try {
    const response = await http.get<{ frame_url: string }>(`/qc-department/${encodeURIComponent(factoryId.value)}/api/health`)
    if (current !== sequence) return
    frameUrl.value = response.data.frame_url
    frameVersion.value++
    ready.value = true
  } catch (reason) {
    if (current === sequence) error.value = getApiErrorMessage(reason)
  } finally {
    if (current === sequence) loading.value = false
  }
}
function reload() { if (permitLeave()) void refresh() }
watch([factoryId, () => auth.currentUser?.id, () => auth.authorizationVersion], refresh, { immediate: true })
watch(options, () => connectFrame(false))
</script>

<template>
  <main class="qc-department-host">
    <header class="flex flex-wrap items-center justify-between gap-2 border-b bg-white px-4 py-2 text-slate-900">
      <RouterLink :to="{ path: '/modules/qc', query: { factory: contextId } }" class="text-sm font-semibold text-teal-700">返回 QC 模块中心</RouterLink>
      <h1 class="text-sm font-semibold">{{ factoryName }} · QC 验货工作台</h1>
      <div class="flex flex-wrap items-center gap-2">
        <label class="qc-host-factory">Nexus 厂区
          <select aria-label="Nexus 厂区" :value="contextId" :disabled="switching" @change="onSelect">
            <option v-if="!options.some(option => option.id === contextId)" :value="contextId" disabled>{{ factoryName }}（无 QC 权限）</option>
            <option v-for="option in options" :key="option.id" :value="option.id">{{ option.label }}</option>
          </select>
        </label>
        <Button variant="outline" size="sm" :disabled="loading || !factoryId" @click="reload">重新加载</Button>
      </div>
    </header>
    <section v-if="!factoryId" class="m-6 rounded-xl border bg-white p-6" role="status">请选择具体厂区，再进入 QC 验货工作台。集团不加载各厂业务数据。</section>
    <section v-else-if="loading" class="p-6" role="status">正在连接 QC 工作台…</section>
    <section v-else-if="error" class="m-6 rounded-xl border bg-white p-6" role="alert">{{ error }}</section>
    <iframe v-else-if="ready" ref="frame" :key="`${factoryId}:${frameVersion}`" :src="frameUrl" @load="connectFrame()" title="QC_department 验货工作台" class="h-full min-h-0 w-full border-0 bg-white" />
  </main>
</template>

<style scoped>
.qc-department-host { display: grid; grid-template-rows: auto minmax(0, 1fr); height: 100dvh; min-width: 320px; background: var(--background, #f8fafc); }
.qc-host-factory { display: inline-flex; align-items: center; gap: 8px; font-size: 13px; }
.qc-host-factory select { min-height: 36px; max-width: 180px; border: 1px solid var(--input); border-radius: 10px; padding: 4px 10px; background: var(--card, white); font: inherit; }
</style>
