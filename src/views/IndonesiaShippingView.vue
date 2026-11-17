<script setup lang="ts">
import { computed, onBeforeUnmount, ref, watch } from 'vue'
import { useRouter } from 'vue-router'
import { ArrowLeft, Bell, Menu, RefreshCw, Ship } from '@lucide/vue'
import Button from '@/components/ui/button/Button.vue'
import SectionPanel from '@/components/common/SectionPanel.vue'
import { factoryContexts, type FactoryContextId } from '@/data/enterpriseMock'
import { http } from '@/lib/http'
import { useAppStore } from '@/stores/app'
import { useAuthStore } from '@/stores/auth'
import { registerShippingNavigationGuard } from '@/features/indonesia-shipping/navigationGuard'
import { getAuthenticationGeneration } from '@/lib/authenticationGeneration'
import { AlertDialogCancel, AlertDialogContent, AlertDialogDescription, AlertDialogOverlay, AlertDialogPortal, AlertDialogRoot, AlertDialogTitle } from 'reka-ui'

const app = useAppStore()
const auth = useAuthStore()
const router = useRouter()
const ready = ref(false)
const loading = ref(false)
const error = ref('')
const revision = ref(0)
const frame = ref<HTMLIFrameElement | null>(null)
const toolbarReady = ref(false)
const alertsEnabled = ref(false)
const alertCount = ref(0)
let toolbarId = ''
function sendToolbar(action: 'connect' | 'alerts' | 'menu') {
  if (!ready.value || !frame.value?.contentWindow) return
  frame.value.contentWindow.postMessage({ type: 'nexus-shipping-toolbar', action, id: toolbarId, factory: factory.value }, window.location.origin)
}
const authenticationGeneration = ref(getAuthenticationGeneration())
function sessionBoundary() { authenticationGeneration.value = getAuthenticationGeneration() }
window.addEventListener('auth-session-boundary-changed', sessionBoundary)
let draftState = { dirty: false, pending: false }
const leaveDialog = ref<'dirty' | 'pending' | null>(null)
let leavePromise: Promise<boolean> | null = null
let resolveLeave: ((value: boolean) => void) | null = null
function finishLeave(value: boolean) {
  leaveDialog.value = null
  resolveLeave?.(value); resolveLeave = null; leavePromise = null
}
function canLeave() {
  if (!draftState.pending && !draftState.dirty) return true
  if (leavePromise) return leavePromise
  leaveDialog.value = draftState.pending ? 'pending' : 'dirty'
  leavePromise = new Promise(resolve => { resolveLeave = resolve })
  return leavePromise
}
function receiveState(event: MessageEvent) {
  if (!event.source || event.origin !== window.location.origin || event.source !== frame.value?.contentWindow) return
  if (event.data?.type === 'nexus-shipping-navigation') {
    draftState = { dirty: event.data.dirty === true, pending: event.data.pending === true }
  } else if (ready.value && event.data?.factory === factory.value) {
    if (event.data.type === 'nexus-shipping-toolbar-ready') sendToolbar('connect')
    if (event.data.type === 'nexus-shipping-toolbar-state' && event.data.id === toolbarId) {
      toolbarReady.value = event.data.active !== false
      alertsEnabled.value = toolbarReady.value && event.data.alertsEnabled === true
      alertCount.value = alertsEnabled.value && Number.isSafeInteger(event.data.count) && event.data.count > 0 ? event.data.count : 0
    }
  }
}
window.addEventListener('message', receiveState)
const unregisterGuard = registerShippingNavigationGuard(canLeave)
onBeforeUnmount(() => { finishLeave(false); unregisterGuard(); window.removeEventListener('message', receiveState); window.removeEventListener('auth-session-boundary-changed', sessionBoundary) })
let generation = 0
const factory = computed(() => app.activeFactoryId)
const frameUrl = computed(() => `/api/indonesia-shipping/${encodeURIComponent(factory.value)}/app/shipments`)
const contextKey = computed(() => `${factory.value}:${auth.currentUser?.id ?? ''}:${auth.authorizationVersion}:${authenticationGeneration.value}:${JSON.stringify([auth.currentUser?.identity?.employment_epoch, auth.currentUser?.identity?.identity_version, auth.currentUser?.identity?.effective_context_key])}`)

async function connect() {
  const current = ++generation
  ready.value = false
  toolbarId = crypto.randomUUID()
  toolbarReady.value = false
  alertsEnabled.value = false
  alertCount.value = 0
  finishLeave(false)
  draftState = { dirty: false, pending: false }
  error.value = ''
  loading.value = false
  if (factory.value === 'group' || !auth.isAuthenticated) return
  loading.value = true
  try {
    await http.get(`/indonesia-shipping/${encodeURIComponent(factory.value)}/status`, { timeout: 20000 })
    if (current === generation) { ready.value = true; revision.value++ }
  } catch (cause: any) {
    if (current === generation) error.value = cause?.response?.data?.detail || '印尼走货工作区暂时无法连接，请稍后重试。'
  } finally {
    if (current === generation) loading.value = false
  }
}
async function chooseFactory(event: Event) {
  const value = (event.target as HTMLSelectElement).value as FactoryContextId
  await router.replace({ query: { ...router.currentRoute.value.query, factory: value } })
  ;(event.target as HTMLSelectElement).value = factory.value
}
async function reconnect() { if (await canLeave()) void connect() }
watch(contextKey, connect, { immediate: true, flush: 'sync' })
</script>

<template>
  <main class="indonesia-shipping-workspace">
    <header class="shipping-header">
      <Button v-if="ready" class="shipping-menu-toggle" variant="outline" size="sm" :disabled="!toolbarReady" @click="sendToolbar('menu')">
        <Menu class="size-4" aria-hidden="true" />菜单
      </Button>
      <Button variant="outline" size="sm" @click="router.push({ path: '/modules/sales-business', query: { factory } })">
        <ArrowLeft class="size-4" aria-hidden="true" />返回业务部
      </Button>
      <div class="shipping-heading">
        <h1><Ship class="size-5" aria-hidden="true" />印尼走货明细</h1>
        <p>当前厂区：{{ app.activeFactory?.name }} · 操作人：{{ auth.currentUser?.display_name }}</p>
      </div>
      <label class="shipping-factory">厂区
        <select :value="factory" aria-label="印尼走货厂区" @change="chooseFactory">
          <option v-for="item in factoryContexts" :key="item.id" :value="item.id">{{ item.name }}</option>
        </select>
      </label>
      <Button v-if="ready && alertsEnabled" variant="outline" size="sm" @click="sendToolbar('alerts')">
        <Bell class="size-4" aria-hidden="true" />物料提醒
        <span v-if="alertCount" class="shipping-alert-count" aria-live="polite">{{ alertCount > 99 ? '99+' : alertCount }}</span>
      </Button>
      <Button variant="outline" size="sm" :disabled="loading" @click="reconnect"><RefreshCw class="size-4" aria-hidden="true" />重新连接</Button>
    </header>
    <p class="shipping-mobile-hint">完整表格保留原工作区布局，小屏可在工作区内横向滚动；建议使用电脑处理批量导入和报关单据。</p>
    <div v-if="!ready" class="shipping-state">
      <SectionPanel :title="factory === 'group' ? '请选择厂区' : loading ? '正在连接印尼走货工作区' : '工作区暂不可用'">
        <p v-if="factory === 'group'">请在上方选择实际厂区。各厂的印尼走货资料独立保存。</p>
        <p v-else-if="loading" role="status">正在核对当前账号权限及厂区服务状态…</p>
        <p v-else role="alert">{{ error || '请登录后重新进入业务部。' }}</p>
      </SectionPanel>
    </div>
    <iframe v-else ref="frame" :key="`${contextKey}:${revision}`" :src="frameUrl" class="shipping-frame"
      title="印尼走货明细完整工作区" referrerpolicy="same-origin" @load="sendToolbar('connect')" />
    <AlertDialogRoot :open="leaveDialog !== null" @update:open="!$event && finishLeave(false)">
      <AlertDialogPortal>
        <AlertDialogOverlay class="shipping-leave-overlay" />
        <AlertDialogContent class="shipping-leave-dialog">
          <AlertDialogTitle>{{ leaveDialog === 'pending' ? '操作正在提交' : '离开当前工作区？' }}</AlertDialogTitle>
          <AlertDialogDescription>{{ leaveDialog === 'pending' ? '请等待当前操作完成后再切换厂区或页面。' : '当前有修改或编辑窗口尚未关闭。离开会放弃尚未保存的内容，已经保存的资料会保留。' }}</AlertDialogDescription>
          <footer>
            <Button v-if="leaveDialog === 'dirty'" variant="outline" @click="finishLeave(true)">不保存并离开</Button>
            <AlertDialogCancel as-child><Button @click="finishLeave(false)">继续留在工作区</Button></AlertDialogCancel>
          </footer>
        </AlertDialogContent>
      </AlertDialogPortal>
    </AlertDialogRoot>
  </main>
</template>

<style scoped>
.indonesia-shipping-workspace { height: 100dvh; display: flex; flex-direction: column; background: var(--background); color: var(--foreground); overflow: hidden; }
.shipping-header { display: flex; align-items: center; flex-wrap: wrap; gap: 12px; padding: 12px 18px; border-bottom: 1px solid var(--border); background: var(--card); }
.shipping-heading { flex: 1; min-width: 200px; }
.shipping-heading h1 { display: flex; align-items: center; gap: 8px; font-size: 18px; font-weight: 650; }
.shipping-heading p { margin-top: 4px; font-size: 12px; color: var(--muted-foreground); }
.shipping-factory { display: flex; align-items: center; gap: 8px; font-size: 13px; }
.shipping-factory select { max-width: 180px; padding: 7px 10px; border: 1px solid var(--border); border-radius: 6px; background: var(--card); }
.shipping-factory select:focus-visible { outline: 2px solid var(--primary); outline-offset: 2px; }
.shipping-state { margin: 24px; }
.shipping-frame { display: block; flex: 1; width: 100%; min-height: 0; border: 0; background: white; }
.shipping-mobile-hint { display: none; padding: 8px 16px; font-size: 12px; color: var(--muted-foreground); }
.shipping-menu-toggle { display: none; }
.shipping-alert-count { border-radius: 999px; padding: 0 6px; background: var(--destructive); color: white; font-size: 11px; }
@media (max-width: 767px) { .shipping-menu-toggle { display: inline-flex; } }
.shipping-leave-overlay { position: fixed; inset: 0; z-index: 1100; background: rgb(15 23 42 / .46); }
.shipping-leave-dialog { position: fixed; z-index: 1101; left: 50%; top: 50%; transform: translate(-50%, -50%); width: min(480px, calc(100vw - 32px)); padding: 24px; border: 1px solid var(--border); border-radius: 12px; background: var(--card); color: var(--foreground); box-shadow: 0 24px 64px rgb(15 23 42 / .25); }
.shipping-leave-dialog h2 { font-size: 18px; font-weight: 650; }
.shipping-leave-dialog p { margin: 12px 0 24px; font-size: 14px; line-height: 1.6; color: var(--muted-foreground); }
.shipping-leave-dialog footer { display: flex; justify-content: flex-end; gap: 12px; flex-wrap: wrap; }
@media (max-width: 767px) { .shipping-header { padding: 10px 12px; gap: 10px; } .shipping-heading { order: -1; flex-basis: 100%; } .shipping-mobile-hint { display: block; } .shipping-state { margin: 12px; } }
</style>
