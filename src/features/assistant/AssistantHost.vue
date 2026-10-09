<script setup lang="ts">
import { computed, defineAsyncComponent, onMounted, onUnmounted, ref, watch } from 'vue'
import { useRoute } from 'vue-router'
import { useAuthStore } from '@/stores/auth'
import { useAppStore } from '@/stores/app'
import { useAssistantStore } from '@/stores/assistant'
import { eligible, identityKey, pageContext } from './context'
import AssistantCore from './AssistantCore.vue'
import { stateLabels, type PanelMode } from './types'
import { defaultPanelHeight, type PanelPosition } from './layout'
import './assistant.css'
const Panel = defineAsyncComponent(() => import('./AssistantPanel.vue'))
const auth = useAuthStore(), app = useAppStore(), assistant = useAssistantStore(), route = useRoute()
const mode = ref<PanelMode>('edge'), opened = ref(false), side = ref<'left' | 'right'>('right'), position = ref(.7), width = ref(432)
const panelPosition = ref<PanelPosition | null>(null), height = ref(defaultPanelHeight)
const focusOnOpen = ref(true)
const launcher = ref<HTMLButtonElement>(), businessModal = ref(false)
const pageHidden = ref(document.hidden)
const allowed = computed(() => eligible(auth.currentUser, route.name))
const page = computed(() => pageContext(route.name, app.activeFactoryId, route.query.factory))
const shown = computed(() => allowed.value && assistant.capabilities?.enabled)
let lastCheck = 0, observer: MutationObserver | undefined
let dragging: { x: number; y: number; moved: boolean } | null = null
let suppressClick = false
let revealTimer: ReturnType<typeof setTimeout> | undefined, hideTimer: ReturnType<typeof setTimeout> | undefined
let overLauncher = false, overPanel = false, panelFocused = false
function preferences() {
  try { localStorage.setItem('yl-assistant-layout', JSON.stringify({ side: side.value, position: position.value, width: width.value, height: height.value, panelPosition: panelPosition.value })) } catch { /* optional layout preference */ }
}
function clearHoverTimers() { clearTimeout(revealTimer); clearTimeout(hideTimer) }
function changeMode(next: PanelMode, returnFocus = true) {
  clearHoverTimers(); mode.value = next
  if (next !== 'edge') opened.value = true
  else { overPanel = false; panelFocused = false; if (returnFocus) launcher.value?.focus() }
}
function open(hover = false) {
  if (businessModal.value || !shown.value) return
  focusOnOpen.value = !hover
  panelPosition.value = { x: side.value === 'left' ? 20 : innerWidth - width.value - 20, y: innerHeight * position.value - height.value / 2 }
  changeMode('side'); void check()
}
function toggle() { if (suppressClick) { suppressClick = false; return }; mode.value === 'edge' ? open() : changeMode('edge') }
function hoverEnter(event: PointerEvent, target: 'launcher' | 'panel') {
  if (event.pointerType !== 'mouse' || innerWidth < 768) return
  if (target === 'launcher') overLauncher = true; else overPanel = true
  clearHoverTimers()
  if (target === 'launcher' && mode.value === 'edge' && !businessModal.value) revealTimer = setTimeout(() => { if (overLauncher && !dragging) open(true) }, 180)
}
function scheduleHide() {
  clearTimeout(hideTimer)
  hideTimer = setTimeout(() => {
    if (!overLauncher && !overPanel && !panelFocused && !dragging && mode.value === 'side' && innerWidth >= 768) changeMode('edge', false)
  }, 550)
}
function hoverLeave(event: PointerEvent, target: 'launcher' | 'panel') {
  if (event.pointerType !== 'mouse') return
  if (target === 'launcher') { overLauncher = false; clearTimeout(revealTimer) } else overPanel = false
  scheduleHide()
}
function focusChanged(value: boolean) { panelFocused = value; if (value) clearTimeout(hideTimer); else scheduleHide() }
async function check() {
  if (!allowed.value || Date.now()-lastCheck < 5000) return
  lastCheck = Date.now(); await assistant.refreshCapabilities()
  if (assistant.capabilities && !assistant.capabilities.enabled) {
    mode.value = 'edge'
    Object.values(assistant.runs).filter(r => ['connecting','answering','thinking','tool_running'].includes(r.state)).forEach(r => { void assistant.stop(r.sessionId) })
  }
}
watch(() => identityKey(auth.currentUser), key => { clearHoverTimers(); overLauncher = false; overPanel = false; panelFocused = false; assistant.bindIdentity(key); mode.value = 'edge'; opened.value = false; lastCheck = 0; if (key && allowed.value) void check() }, { immediate: true })
watch(allowed, value => { if (value) void check(); else mode.value = 'edge' })
watch(() => [page.value?.factory_id, auth.currentUser?.identity?.effective_context_key, auth.authorizationVersion], () => {
  for (const run of Object.values(assistant.runs)) {
    if (run.payload.page_context && ['connecting','answering','thinking','tool_running'].includes(run.state)) void assistant.stop(run.sessionId)
  }
})
function visible() { pageHidden.value = document.hidden; if (!pageHidden.value && assistant.capabilities?.enabled) void check() }
function shortcut(event: KeyboardEvent) {
  if (event.altKey && event.code === 'KeyJ' && !event.isComposing && shown.value && !businessModal.value) {
    event.preventDefault(); mode.value === 'edge' ? open() : changeMode('edge')
  }
}
function dragStart(event: PointerEvent) { if (event.button !== 0) return; clearHoverTimers(); dragging = { x: event.clientX, y: event.clientY, moved: false }; (event.currentTarget as HTMLElement).setPointerCapture(event.pointerId) }
function dragMove(event: PointerEvent) {
  if (!dragging) return
  if (Math.abs(event.clientX-dragging.x)+Math.abs(event.clientY-dragging.y) > 6) dragging.moved = true
  if (dragging.moved) { side.value = event.clientX < innerWidth/2 ? 'left' : 'right'; position.value = Math.max(.15, Math.min(.85, event.clientY/innerHeight)) }
}
function dragEnd() { suppressClick = dragging?.moved || false; if (dragging?.moved) panelPosition.value = null; dragging = null; preferences() }
onMounted(() => {
  try {
    const value = JSON.parse(localStorage.getItem('yl-assistant-layout') || '{}')
    if (['left','right'].includes(value.side)) side.value = value.side
    if (Number.isFinite(value.position)) position.value = Math.max(.15, Math.min(.85,value.position))
    if (Number.isFinite(value.width)) width.value = Math.max(360,Math.min(600,value.width))
    if (Number.isFinite(value.height)) height.value = Math.max(360, Math.min(820, value.height))
    if (Number.isFinite(value.panelPosition?.x) && Number.isFinite(value.panelPosition?.y)) panelPosition.value = { x: value.panelPosition.x, y: value.panelPosition.y }
  } catch { /* layout preferences are optional */ }
  document.addEventListener('visibilitychange', visible); window.addEventListener('keydown', shortcut)
  observer = new MutationObserver(() => {
    businessModal.value = [...document.querySelectorAll<HTMLElement>('[aria-modal="true"], dialog[open]')].some(el => !el.closest('.yl-assistant') && !!el.getClientRects().length)
    if (businessModal.value && mode.value !== 'edge') changeMode('edge')
  })
  observer.observe(document.body, { subtree: true, childList: true, attributes: true, attributeFilter: ['aria-modal','open','data-state'] })
})
onUnmounted(() => { clearHoverTimers(); document.removeEventListener('visibilitychange', visible); window.removeEventListener('keydown', shortcut); observer?.disconnect(); assistant.bindIdentity('') })
</script>
<template>
  <Teleport to="body">
    <div v-if="shown" class="yl-assistant" :class="{ 'yl-hidden-page': pageHidden }" :data-side="side">
      <button ref="launcher" v-show="mode !== 'focus'" class="yl-launcher" :class="{ 'yl-launcher-open': mode !== 'edge' }" :style="{ top: `${position*100}%` }" :disabled="businessModal" :aria-label="mode === 'edge' ? '打开曜灵 · Nexus AI' : '收起曜灵边缘面板'" aria-haspopup="dialog" :aria-expanded="mode !== 'edge'" title="移入展开，移开收起 · 点击或 Alt+J 也可打开" @click="toggle" @pointerenter="hoverEnter($event, 'launcher')" @pointerleave="hoverLeave($event, 'launcher')" @pointerdown="dragStart" @pointermove="dragMove" @pointerup="dragEnd" @pointercancel="dragEnd">
        <AssistantCore :active="assistant.anyBusy" /><span>曜灵</span><i v-if="assistant.anyBusy" aria-label="正在回答" />
      </button>
      <Panel v-if="opened" :mode="mode" :side="side" :width="width" :height="height" :position="panelPosition" :focus-on-open="focusOnOpen" :page="page" :suspended="businessModal" :page-title="String(route.meta.title || '当前页面')" @mode="changeMode" @side="side = $event" @width="width = $event" @height="height = $event" @position="panelPosition = $event" @layout-end="preferences" @pointer-enter="hoverEnter($event, 'panel')" @pointer-leave="hoverLeave($event, 'panel')" @focus-change="focusChanged" />
      <span class="yl-sr-only" role="status" aria-live="polite">{{ assistant.currentRun ? stateLabels[assistant.currentRun.state] : '' }}</span>
    </div>
  </Teleport>
</template>
