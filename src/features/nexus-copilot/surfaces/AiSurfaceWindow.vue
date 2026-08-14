<script setup lang="ts">
import { computed, onBeforeUnmount, onMounted, ref, watch } from 'vue'
import {
  GripHorizontal,
  Minus,
  PanelLeft,
  PanelRight,
  PictureInPicture2,
  X,
} from '@lucide/vue'
import type { AISurfaceMode } from './surfaceStore'
import { clampSurfaceGeometry, type AISurfaceGeometry } from './useWindowGeometry'

const props = withDefaults(defineProps<{
  mode: AISurfaceMode
  geometry: AISurfaceGeometry
  dockWidth: number
  closeLabel: string
  adaptiveEnabled?: boolean
}>(), { adaptiveEnabled: true })

const emit = defineEmits<{
  mode: [mode: 'FLOATING' | 'DOCKED_LEFT' | 'DOCKED_RIGHT']
  geometry: [geometry: AISurfaceGeometry, save?: boolean]
  dockWidth: [width: number, save?: boolean]
  minimize: []
  close: []
}>()

const root = ref<HTMLElement | null>(null)
const draft = ref<AISurfaceGeometry>(props.geometry)
const draftDockWidth = ref(props.dockWidth)
const viewportWidth = ref(window.innerWidth)
let frame = 0
let interaction: null | {
  type: 'move' | 'resize' | 'dock-resize'
  pointerId: number
  startX: number
  startY: number
  geometry: AISurfaceGeometry
  dockWidth: number
} = null
let pending: PointerEvent | null = null

watch(() => props.geometry, (value) => { if (!interaction) draft.value = value }, { deep: true })
watch(() => props.dockWidth, (value) => { if (!interaction) draftDockWidth.value = value })

const floating = computed(() => props.mode === 'FLOATING')
const mobile = computed(() => props.mode === 'FULLSCREEN_MOBILE')
const dockMaximum = computed(() => Math.round(Math.min(720, viewportWidth.value * 0.72)))
const style = computed(() => {
  if (mobile.value) return {}
  if (props.mode === 'DOCKED_LEFT') return { left: '0px', width: `${props.dockWidth}px` }
  if (props.mode === 'DOCKED_RIGHT') return { right: '0px', width: `${props.dockWidth}px` }
  return {
    width: `${draft.value.width}px`,
    height: `${draft.value.height}px`,
    transform: `translate3d(${draft.value.x}px, ${draft.value.y}px, 0)`,
  }
})

function begin(event: PointerEvent, type: NonNullable<typeof interaction>['type']) {
  if (event.button !== 0 || mobile.value || !props.adaptiveEnabled) return
  if (type === 'move' && !floating.value) return
  interaction = {
    type,
    pointerId: event.pointerId,
    startX: event.clientX,
    startY: event.clientY,
    geometry: { ...draft.value },
    dockWidth: props.dockWidth,
  }
  event.currentTarget instanceof HTMLElement && event.currentTarget.setPointerCapture(event.pointerId)
  event.preventDefault()
}

function applyPending() {
  frame = 0
  if (!interaction || !pending) return
  const event = pending
  pending = null
  const dx = event.clientX - interaction.startX
  const dy = event.clientY - interaction.startY
  if (interaction.type === 'move') {
    draft.value = clampSurfaceGeometry({ ...interaction.geometry, x: interaction.geometry.x + dx, y: interaction.geometry.y + dy })
    emit('geometry', draft.value, false)
  } else if (interaction.type === 'resize') {
    draft.value = clampSurfaceGeometry({ ...interaction.geometry, width: interaction.geometry.width + dx, height: interaction.geometry.height + dy })
    emit('geometry', draft.value, false)
  } else {
    const width = interaction.dockWidth + (props.mode === 'DOCKED_LEFT' ? dx : -dx)
    draftDockWidth.value = width
    emit('dockWidth', draftDockWidth.value, false)
  }
}

function pointerMove(event: PointerEvent) {
  if (!interaction || interaction.pointerId !== event.pointerId) return
  pending = event
  frame ||= requestAnimationFrame(applyPending)
}

function pointerUp(event: PointerEvent) {
  if (!interaction || interaction.pointerId !== event.pointerId) return
  if (frame) cancelAnimationFrame(frame)
  applyPending()
  if (interaction.type === 'dock-resize') emit('dockWidth', draftDockWidth.value, true)
  else emit('geometry', draft.value, true)
  interaction = null
}

function keyboardMove(event: KeyboardEvent) {
  if (!event.altKey || !floating.value || !['ArrowUp', 'ArrowDown', 'ArrowLeft', 'ArrowRight'].includes(event.key)) return
  event.preventDefault()
  const amount = 12
  const next = { ...draft.value }
  const resize = event.shiftKey
  if (event.key === 'ArrowLeft') resize ? next.width -= amount : next.x -= amount
  if (event.key === 'ArrowRight') resize ? next.width += amount : next.x += amount
  if (event.key === 'ArrowUp') resize ? next.height -= amount : next.y -= amount
  if (event.key === 'ArrowDown') resize ? next.height += amount : next.y += amount
  draft.value = clampSurfaceGeometry(next)
  emit('geometry', draft.value, true)
}

function keyboardDockResize(event: KeyboardEvent) {
  if (mobile.value || floating.value || !props.adaptiveEnabled || !['ArrowLeft', 'ArrowRight'].includes(event.key)) return
  event.preventDefault()
  const physicalDelta = event.key === 'ArrowLeft' ? -16 : 16
  const widthDelta = props.mode === 'DOCKED_LEFT' ? physicalDelta : -physicalDelta
  emit('dockWidth', props.dockWidth + widthDelta, true)
}

function viewportChanged() {
  viewportWidth.value = window.innerWidth
  if (floating.value) emit('geometry', clampSurfaceGeometry(draft.value), true)
}

onMounted(() => window.addEventListener('resize', viewportChanged))
onBeforeUnmount(() => {
  window.removeEventListener('resize', viewportChanged)
  if (frame) cancelAnimationFrame(frame)
})

defineExpose({ root })
</script>

<template>
  <aside
    id="ai-assistant-drawer"
    ref="root"
    class="fixed z-[90] flex min-h-0 flex-col overflow-hidden border border-border bg-card shadow-2xl outline-none"
    :class="mobile
      ? 'inset-0 rounded-none'
      : floating
        ? 'left-0 top-0 rounded-2xl'
        : 'inset-y-0 rounded-none'"
    :style="style"
    :role="mobile ? 'dialog' : 'complementary'"
    :aria-modal="mobile ? 'true' : undefined"
    aria-labelledby="ai-assistant-title"
    aria-describedby="ai-assistant-description"
    tabindex="-1"
  >
    <header
      class="flex shrink-0 items-center gap-2 border-b border-border bg-card px-3 py-2.5"
      :class="floating ? 'cursor-move' : ''"
      tabindex="0"
      aria-label="AI 助手窗口标题栏；Alt 加方向键移动，Alt 加 Shift 加方向键缩放"
      @pointerdown="begin($event, 'move')"
      @pointermove="pointerMove"
      @pointerup="pointerUp"
      @pointercancel="pointerUp"
      @keydown="keyboardMove"
    >
      <GripHorizontal v-if="floating" class="size-4 shrink-0 text-muted-foreground" aria-hidden="true" />
      <div class="min-w-0 flex-1 cursor-default" @pointerdown.stop>
        <slot name="identity" />
      </div>
      <div class="flex items-center gap-0.5" data-surface-control @pointerdown.stop>
        <button v-if="adaptiveEnabled" type="button" class="ai-surface-control" aria-label="停靠到左侧" @click="emit('mode', 'DOCKED_LEFT')">
          <PanelLeft class="size-3.5" aria-hidden="true" />
        </button>
        <button v-if="adaptiveEnabled" type="button" class="ai-surface-control" aria-label="切换为浮动窗口" @click="emit('mode', 'FLOATING')">
          <PictureInPicture2 class="size-3.5" aria-hidden="true" />
        </button>
        <button v-if="adaptiveEnabled" type="button" class="ai-surface-control" aria-label="停靠到右侧" @click="emit('mode', 'DOCKED_RIGHT')">
          <PanelRight class="size-3.5" aria-hidden="true" />
        </button>
        <button type="button" class="ai-surface-control" aria-label="最小化 AI 助手到页面边缘" @click="emit('minimize')">
          <Minus class="size-3.5" aria-hidden="true" />
        </button>
        <button type="button" class="ai-surface-control" :aria-label="closeLabel" @click="emit('close')">
          <X class="size-3.5" aria-hidden="true" />
        </button>
      </div>
    </header>

    <slot />

    <button
      v-if="floating && adaptiveEnabled"
      type="button"
      class="absolute bottom-0 right-0 size-6 cursor-nwse-resize rounded-tl-lg text-transparent focus-visible:text-primary focus-visible:outline focus-visible:outline-2 focus-visible:outline-inset focus-visible:outline-ring"
      aria-label="调整 AI 助手窗口大小"
      @pointerdown="begin($event, 'resize')"
      @pointermove="pointerMove"
      @pointerup="pointerUp"
      @pointercancel="pointerUp"
    >
      调整
    </button>
    <div
      v-else-if="!mobile && adaptiveEnabled"
      class="absolute inset-y-0 w-2 cursor-ew-resize text-transparent focus-visible:bg-primary/20 focus-visible:outline-none"
      :class="mode === 'DOCKED_LEFT' ? 'right-0' : 'left-0'"
      role="separator"
      aria-orientation="vertical"
      aria-label="调整停靠面板宽度"
      :aria-valuenow="Math.round(dockWidth)"
      aria-valuemin="360"
      :aria-valuemax="dockMaximum"
      tabindex="0"
      @pointerdown="begin($event, 'dock-resize')"
      @pointermove="pointerMove"
      @pointerup="pointerUp"
      @pointercancel="pointerUp"
      @keydown="keyboardDockResize"
    >
      调整
    </div>
  </aside>
</template>

<style scoped>
.ai-surface-control {
  display: flex;
  width: 2rem;
  height: 2rem;
  align-items: center;
  justify-content: center;
  border-radius: 0.55rem;
  color: var(--muted-foreground);
}
.ai-surface-control:hover { background: var(--accent); color: var(--foreground); }
.ai-surface-control:focus-visible { outline: 2px solid var(--ring); outline-offset: 2px; }
@media (prefers-reduced-motion: reduce) { * { scroll-behavior: auto !important; } }
</style>
