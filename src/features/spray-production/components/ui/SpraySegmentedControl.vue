<script setup lang="ts">
import { nextTick, onBeforeUnmount, onMounted, ref, watch } from 'vue'
import type { Component } from 'vue'
import { useSprayMotionPreference } from '../../composables/useSprayMotionPreference'

/* 滑动胶囊指示器：真实选中按钮的几何决定指示器位置，接受后才变更选中态。
   - 桌面横向分段：按钮顺序与视觉顺序一致，指示器跟随宽度与滚动；
   - 未启用动效时直接落位，不播放位移；
   - 每个按钮保留 aria-pressed，因此文本与可访问名称不变。 */
const props = defineProps<{
  modelValue: string
  options: { value: string; label: string; icon?: Component }[]
  label: string
  disabled?: boolean
  /* 视觉分组用途：pill 为独立胶囊分段，bar 为页内一级分区的条形下划线。 */
  tone?: 'pill' | 'bar'
}>()
const emit = defineEmits<{ 'update:modelValue': [string] }>()
const root = ref<HTMLElement | null>(null)
const indicator = ref({ transform: 'translateX(0px)', width: '0px', opacity: 0 })
const { motionAllowed } = useSprayMotionPreference()
let observer: ResizeObserver | undefined
let frame = 0
let disposed = false

function measure() {
  const container = root.value
  const selected = container?.querySelector<HTMLElement>('button[aria-pressed="true"]')
  if (!container || !selected) {
    indicator.value = { ...indicator.value, opacity: 0 }
    return
  }
  const outer = container.getBoundingClientRect()
  const rect = selected.getBoundingClientRect()
  if (!rect.width && !rect.height) {
    /* 未布局（例如测试环境）时不展示指示器，避免出现零宽残影。 */
    indicator.value = { ...indicator.value, opacity: 0 }
    return
  }
  indicator.value = {
    transform: `translateX(${rect.left - outer.left + container.scrollLeft - container.clientLeft}px)`,
    width: `${rect.width}px`,
    opacity: 1,
  }
}

function queue() {
  if (disposed) return
  if (frame) cancelAnimationFrame(frame)
  if (!motionAllowed.value) {
    measure()
    return
  }
  frame = requestAnimationFrame(measure)
}

function keys(event: KeyboardEvent, index: number) {
  if (!['ArrowLeft', 'ArrowRight', 'Home', 'End'].includes(event.key)) return
  event.preventDefault()
  const buttons = root.value?.querySelectorAll<HTMLButtonElement>('button')
  const count = props.options.length
  const next = event.key === 'Home' ? 0
    : event.key === 'End' ? count - 1
      : (index + (event.key === 'ArrowRight' ? 1 : -1) + count) % count
  buttons?.[next]?.focus()
}

watch(() => [props.modelValue, props.options, motionAllowed.value], () => nextTick(queue), { deep: true })

onMounted(() => {
  if (typeof ResizeObserver !== 'undefined') observer = new ResizeObserver(queue)
  if (root.value) {
    observer?.observe(root.value)
    root.value.querySelectorAll('button').forEach(element => observer?.observe(element))
  }
  window.addEventListener('resize', queue)
  /* 字体载入会改变按钮宽度，补一次测量；测试环境可能没有 document.fonts。 */
  void document.fonts?.ready?.then(queue)
  measure()
})

onBeforeUnmount(() => {
  disposed = true
  observer?.disconnect()
  if (frame) cancelAnimationFrame(frame)
  window.removeEventListener('resize', queue)
})
</script>

<template>
  <div
    ref="root"
    class="spray-pill-control"
    :class="[tone === 'bar' ? 'spray-pill-control-bar' : '', { 'spray-no-motion': !motionAllowed }]"
    role="group"
    :aria-label="label"
    @scroll="queue"
  >
    <span class="spray-pill-indicator" :style="indicator" aria-hidden="true" />
    <button
      v-for="(option, index) in options"
      :key="option.value"
      type="button"
      :disabled="disabled"
      :aria-pressed="modelValue === option.value"
      @click="emit('update:modelValue', option.value)"
      @keydown="keys($event, index)"
    >
      <component :is="option.icon" v-if="option.icon" :size="14" aria-hidden="true" />
      <span>{{ option.label }}</span>
    </button>
  </div>
</template>
