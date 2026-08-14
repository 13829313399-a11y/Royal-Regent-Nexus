<script setup lang="ts">
import { computed, ref } from 'vue'
import { Sparkles } from '@lucide/vue'

const props = withDefaults(defineProps<{
  side?: 'left' | 'right'
  y?: number
  busy?: boolean
  badge?: number
  movable?: boolean
}>(), {
  side: 'right',
  y: 180,
  busy: false,
  badge: 0,
  movable: true,
})

const emit = defineEmits<{
  open: []
  move: [y: number]
}>()

const dragging = ref(false)
let startY = 0
let startEdgeY = 0
let moved = false

const style = computed(() => ({
  top: `${props.y}px`,
  [props.side]: '0px',
}))

function pointerDown(event: PointerEvent) {
  if (event.button !== 0 || !props.movable) return
  dragging.value = true
  moved = false
  startY = event.clientY
  startEdgeY = props.y
  event.currentTarget instanceof HTMLElement && event.currentTarget.setPointerCapture(event.pointerId)
}

function pointerMove(event: PointerEvent) {
  if (!dragging.value) return
  const delta = event.clientY - startY
  if (Math.abs(delta) > 3) moved = true
  emit('move', startEdgeY + delta)
}

function pointerUp() {
  dragging.value = false
}

function click() {
  if (!moved) emit('open')
  moved = false
}
</script>

<template>
  <button
    id="ai-assistant-trigger"
    type="button"
    class="group fixed z-[85] flex h-11 w-10 items-center overflow-hidden border border-border bg-card text-primary shadow-lg transition-[width,background-color] hover:w-28 hover:bg-accent focus-visible:w-28 focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-ring"
    :class="side === 'right' ? 'rounded-l-xl border-r-0' : 'rounded-r-xl border-l-0'"
    :style="style"
    aria-label="打开 AI 助手"
    aria-controls="ai-assistant-drawer"
    @pointerdown="pointerDown"
    @pointermove="pointerMove"
    @pointerup="pointerUp"
    @pointercancel="pointerUp"
    @click="click"
  >
    <span class="relative flex size-10 shrink-0 items-center justify-center">
      <Sparkles class="size-4" :class="busy ? 'animate-pulse' : ''" aria-hidden="true" />
      <span v-if="badge" class="absolute right-0.5 top-0.5 min-w-4 rounded-full bg-amber-500 px-1 text-[9px] font-bold leading-4 text-white">
        {{ Math.min(badge, 99) }}
      </span>
    </span>
    <span class="whitespace-nowrap pr-3 text-xs font-semibold">AI 助手</span>
  </button>
</template>
