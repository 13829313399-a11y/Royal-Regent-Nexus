<script setup lang="ts">
import { computed, onBeforeUnmount, onMounted, ref, watch } from 'vue'
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
    navigate?: (page: string) => void
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
const frameLoaded = ref(false)
const error = ref('')
const switching = ref(false)
const frameVersion = ref(0)
const viewportStyle = ref<Record<string, string>>({})
const headerBounds = ref<HTMLDivElement | null>(null)
const headerStrip = ref<HTMLDivElement | null>(null)
let viewport: VisualViewport | null = null
let viewportFrame = 0
let scrollFrame = 0
let frameResize: ResizeObserver | undefined
let frameChanges: MutationObserver | undefined
let layoutDocument: Document | undefined
let headerSheet: HTMLElement | null = null
let headerSignature = ''
function syncHeaderScroll() {
  if (headerStrip.value && headerSheet) headerStrip.value.scrollLeft = headerSheet.scrollLeft
}
function clearHeader() {
  headerSheet?.removeEventListener('scroll', syncHeaderScroll)
  headerSheet = null
  headerSignature = ''
  if (headerBounds.value) headerBounds.value.hidden = true
  headerStrip.value?.replaceChildren()
}
function measureHeader(doc: Document, element: HTMLIFrameElement) {
  const bounds = headerBounds.value, strip = headerStrip.value
  const sheet = doc.querySelector<HTMLElement>('#page-records.active .qis-wrap,#page-review.active .qis-wrap')
  const table = sheet?.querySelector<HTMLTableElement>('.qis-table')
  if (!bounds || !strip || !sheet || !table?.tHead || !table.tBodies[0]?.rows.length) { clearHeader(); return }
  if (headerSheet !== sheet) {
    clearHeader()
    headerSheet = sheet
    sheet.addEventListener('scroll', syncHeaderScroll, { passive: true })
  }
  const headBox = table.tHead.getBoundingClientRect(), sheetBox = sheet.getBoundingClientRect()
  // This box is anchored to the table in document coordinates. Native sticky
  // handles vertical motion on the compositor, without scroll-event transforms.
  Object.assign(bounds.style, {
    top: `${element.offsetTop + headBox.top}px`,
    left: `${element.offsetLeft + sheetBox.left + sheet.clientLeft}px`,
    width: `${sheet.clientWidth}px`,
    height: `${Math.max(0, table.getBoundingClientRect().bottom - headBox.top)}px`,
  })
  const cells = Array.from(table.tHead.querySelectorAll('th')).map(th => {
    const style = doc.defaultView!.getComputedStyle(th)
    const box = th.getBoundingClientRect()
    const frozen = th.dataset.column === 'customer' || th.dataset.column === 'poNo'
    return { text: th.textContent || '', column: th.dataset.column || '', style: {
      width: `${box.width}px`, height: `${box.height}px`,
      font: style.font, letterSpacing: style.letterSpacing, textAlign: style.textAlign,
      padding: style.padding, color: style.color, background: style.backgroundColor,
      borderRight: style.borderRight, borderBottom: style.borderBottom,
      position: frozen ? 'sticky' : 'relative', left: frozen ? style.left : 'auto',
      zIndex: frozen ? '2' : '1',
    } }
  })
  const signature = JSON.stringify(cells)
  if (signature !== headerSignature) {
    // Presentational labels only: do not duplicate inputs, IDs or accessibility headers.
    strip.replaceChildren(...cells.map(cell => {
      const label = document.createElement('span')
      label.textContent = cell.text
      label.dataset.column = cell.column
      Object.assign(label.style, cell.style)
      return label
    }))
    headerSignature = signature
  }
  const overlayOpen = doc.body.classList.contains('qc-sidebar-open') || !!doc.querySelector('dialog[open]')
    || Array.from(doc.querySelectorAll<HTMLElement>('.modal-overlay,.import-confirm-overlay,.backup-confirm-overlay,#rptExportOverlay'))
      .some(overlay => overlay.getClientRects().length && doc.defaultView!.getComputedStyle(overlay).visibility !== 'hidden')
  bounds.hidden = overlayOpen
  syncHeaderScroll()
}
function disconnectLayout() {
  frameResize?.disconnect()
  frameChanges?.disconnect()
  layoutDocument = undefined
  clearHeader()
}
function measureVisibleArea() {
  const element = frame.value, root = child()?.document?.documentElement
  if (!element || !root?.classList.contains('qc-page-scroll')) return
  const bounds = element.getBoundingClientRect(), top = viewport?.offsetTop || 0
  const height = viewport?.height || window.innerHeight
  const visibleTop = Math.max(top, bounds.top)
  root.style.setProperty('--qc-visible-top', `${Math.max(0, visibleTop - bounds.top)}px`)
  root.style.setProperty('--qc-visible-height', `${Math.max(1, Math.min(top + height, bounds.bottom) - visibleTop)}px`)
}
function scheduleScroll() {
  cancelAnimationFrame(scrollFrame)
  scrollFrame = requestAnimationFrame(measureVisibleArea)
}
function measureFrame(height: number) {
  const element = frame.value
  const doc = child()?.document
  const root = doc?.documentElement
  const main = doc?.querySelector<HTMLElement>('.main-wrap')
  const phone = !!root?.classList.contains('qc-mobile')
  const flowing = !!(phone && main && doc?.querySelector('#page-records.active,#page-review.active'))
  document.documentElement.classList.toggle('qc-document-scroll', flowing)
  document.documentElement.classList.toggle('qc-viewport-locked', !flowing)
  root?.classList.toggle('qc-page-scroll', flowing)
  root?.classList.toggle('qc-short-viewport', phone && window.innerWidth > 640 && height <= 500)
  if (!element || !root || !main) return
  if (flowing) {
    // Measure natural content, not body.scrollHeight (which also includes the iframe viewport).
    // This lets filtering shrink the frame again without recreating editors or losing drafts.
    const contentHeight = Math.ceil(main.getBoundingClientRect().height)
    // The workbench is hidden during bootstrap. Keep room for its loading status.
    if (contentHeight > 0) element.style.height = `${contentHeight}px`
    measureVisibleArea()
    measureHeader(doc, element)
  } else {
    clearHeader()
    element.style.removeProperty('height')
    root.style.removeProperty('--qc-visible-top')
    root.style.removeProperty('--qc-visible-height')
  }
}
function connectLayout() {
  const doc = child()?.document
  if (doc && doc !== layoutDocument) {
    disconnectLayout()
    layoutDocument = doc
    const main = doc.querySelector('.main-wrap')
    if (main && typeof ResizeObserver !== 'undefined') {
      frameResize = new ResizeObserver(scheduleViewport)
      frameResize.observe(main)
    }
    // Page/device classes change independently of the current table's content size.
    frameChanges = new MutationObserver(scheduleViewport)
    frameChanges.observe(doc.documentElement, { attributes: true, attributeFilter: ['class'] })
    // Also catch same-height row/header replacements, review tab changes and overlays.
    frameChanges.observe(doc.body, { childList: true, subtree: true, attributes: true, attributeFilter: ['class', 'style', 'open', 'hidden'] })
  }
  scheduleViewport()
}
function measureViewport() {
  // Do not resize the layout while the user deliberately pinch-zooms.
  if (viewport && Math.abs(viewport.scale - 1) > 0.01) return
  const height = viewport?.height || window.innerHeight
  if (height > 0) viewportStyle.value = {
    '--qc-viewport-height': `${height}px`,
    '--qc-viewport-top': `${viewport?.offsetTop || 0}px`,
  }
  measureFrame(height)
}
function scheduleViewport() {
  cancelAnimationFrame(viewportFrame)
  viewportFrame = requestAnimationFrame(measureViewport)
}
onMounted(() => {
  document.documentElement.classList.add('qc-viewport-locked')
  viewport = window.visualViewport
  window.addEventListener('resize', scheduleViewport)
  window.addEventListener('orientationchange', scheduleViewport)
  window.addEventListener('scroll', scheduleScroll, { passive: true })
  viewport?.addEventListener('resize', scheduleViewport)
  viewport?.addEventListener('scroll', scheduleScroll)
  measureViewport()
})
let page = typeof route.query.qcPage === 'string' ? route.query.qcPage : 'dashboard'
let sequence = 0
function child() { return frame.value?.contentWindow as QcFrame | null }
function permitLeave() {
  try { return child()?.__QC_CONFIRM_FACTORY_LEAVE?.() ?? true }
  catch { window.alert('无法确认 QC 保存状态，请先核对当前记录。'); return false }
}
const unregister = registerFactoryChangeGuard(permitLeave)
onBeforeUnmount(() => {
  unregister(); sequence++
  disconnectLayout()
  cancelAnimationFrame(viewportFrame)
  cancelAnimationFrame(scrollFrame)
  window.removeEventListener('resize', scheduleViewport)
  window.removeEventListener('orientationchange', scheduleViewport)
  window.removeEventListener('scroll', scheduleScroll)
  viewport?.removeEventListener('resize', scheduleViewport)
  viewport?.removeEventListener('scroll', scheduleScroll)
  document.documentElement.classList.remove('qc-viewport-locked', 'qc-document-scroll')
})
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
    navigate: value => {
      if (target !== child() || identity !== `${contextId.value}:${auth.currentUser?.id}:${auth.authorizationVersion}`) return
      page = value
      if (route.query.qcPage !== value) void router.replace({ path: route.path, query: { ...route.query, qcPage: value }, hash: route.hash })
    },
    select: async value => {
      if (target !== child() || identity !== `${contextId.value}:${auth.currentUser?.id}:${auth.authorizationVersion}`) return
      await selectFactory(value)
    },
  })
  connectLayout()
}
function onFrameLoad(event: Event) {
  if (event.currentTarget !== frame.value || !ready.value) return
  frameLoaded.value = true
  connectFrame()
}
async function refresh() {
  const current = ++sequence
  disconnectLayout()
  try { page = child()?.__QC_CURRENT_PAGE?.() || page } catch { /* A replaced frame has no reusable view. */ }
  ready.value = false
  frameLoaded.value = false
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
watch(frame, scheduleViewport, { flush: 'post' })
</script>

<template>
  <main class="qc-department-host" :style="viewportStyle">
    <header class="qc-host-header flex flex-wrap items-center justify-between gap-2 border-b bg-white px-4 py-2 text-slate-900">
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
    <section v-else-if="error" class="m-6 rounded-xl border bg-white p-6" role="alert">{{ error }}</section>
    <template v-else>
      <section v-if="loading || (ready && !frameLoaded)" class="qc-host-loading p-6" role="status">正在连接 QC 工作台…</section>
      <iframe v-if="ready" ref="frame" :key="`${factoryId}:${frameVersion}`" :src="frameUrl" :class="{ invisible: !frameLoaded }" @load="onFrameLoad" title="QC_department 验货工作台" class="h-full min-h-0 w-full border-0 bg-white" />
    </template>
    <div ref="headerBounds" class="qc-table-header-bounds" hidden aria-hidden="true" inert>
      <div class="qc-table-header-sticky"><div ref="headerStrip" class="qc-table-header-strip" /></div>
    </div>
  </main>
</template>

<style scoped>
:global(html.qc-viewport-locked), :global(html.qc-viewport-locked body) { height:100%; min-height:0; overflow:hidden; overscroll-behavior:none; }
:global(html.qc-document-scroll), :global(html.qc-document-scroll body) { height:auto; min-height:0; overflow:visible; overscroll-behavior:auto; }
.qc-department-host { position:fixed; top:var(--qc-viewport-top,0px); left:0; right:0; display:grid; grid-template-rows:auto minmax(0,1fr); height:var(--qc-viewport-height,100dvh); min-width:0; overflow:hidden; background:var(--background,#f8fafc); }
:global(html.qc-document-scroll .qc-department-host) { position:relative; top:auto; display:block; height:auto; min-height:var(--qc-viewport-height,100dvh); overflow:visible; }
.qc-host-loading, .qc-department-host iframe { grid-area:2 / 1; }
.qc-department-host iframe { display:block; }
.qc-table-header-bounds { position:absolute; pointer-events:none; z-index:5; }
.qc-table-header-sticky { position:sticky; top:0; }
.qc-table-header-strip { display:flex; overflow:hidden; }
.qc-table-header-strip :deep(span) { display:block; flex:none; box-sizing:border-box; white-space:nowrap; }
.qc-host-factory { display: inline-flex; align-items: center; gap: 8px; font-size: 13px; }
.qc-host-factory select { min-height: 36px; max-width: 180px; border: 1px solid var(--input); border-radius: 10px; padding: 4px 10px; background: var(--card, white); font: inherit; }
/* Scoped QC frame chrome; Nexus theme and authorization/factory bridge are unchanged. */
.qc-department-host { background: #fbfaf7; }
.qc-host-header { background: #f8f9f5; border-color: #e3e6df; color: #25302b; padding: 8px 18px; min-height: 46px; font-family: -apple-system,BlinkMacSystemFont,'PingFang SC','Microsoft YaHei',sans-serif; }
.qc-host-header a { color: #365d49; text-decoration: none; }
.qc-host-header h1 { font-family: inherit; font-weight: 600; letter-spacing: .2px; }
.qc-host-factory { color: #54615a; font-size: 12px; }
.qc-host-factory select { min-height: 32px; background: rgba(255,255,255,.8); color:#25302b; border-color:#cbd4ca; border-radius:8px; }
.qc-host-header :deep(button) { border-radius:8px; border-color:#cbd4ca; background:rgba(255,255,255,.85); }
@media (max-width:640px) {
  .qc-department-host { min-width:0; overflow:hidden; }
  .qc-host-header { padding:4px 10px; gap:2px 8px; display:grid; grid-template-columns:1fr auto; }
  .qc-host-header h1 { font-size:12px; text-align:right; }
  .qc-host-header>a { display:flex; align-items:center; min-height:32px; font-size:12px; }
  .qc-host-header>div { grid-column:1 / -1; justify-content:space-between; min-width:0; flex-wrap:nowrap; }
  .qc-host-factory { min-width:0; }
  .qc-host-factory select { min-height:44px; font-size:16px; max-width:150px; }
  .qc-host-header :deep(button) { min-height:44px; }
}
@media (prefers-reduced-motion:reduce) { .qc-host-header * { transition:none!important; } }
</style>
