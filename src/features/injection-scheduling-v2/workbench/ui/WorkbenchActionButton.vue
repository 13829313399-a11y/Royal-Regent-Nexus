<script setup lang="ts">
import { computed, ref } from 'vue'
import { LoaderCircle } from '@lucide/vue'

const props = withDefaults(defineProps<{
  variant?: 'primary' | 'secondary' | 'ghost' | 'danger'
  loading?: boolean
  loadingText?: string
  iconOnly?: boolean
  disabled?: boolean
  type?: 'button' | 'submit' | 'reset'
}>(), {
  variant: 'secondary',
  loading: false,
  loadingText: '处理中…',
  iconOnly: false,
  disabled: false,
  type: 'button',
})

const emit = defineEmits<{ click: [event: MouseEvent] }>()
const ripple = ref<{ x: number; y: number; size: number; key: number } | null>(null)
const blocked = computed(() => props.disabled || props.loading)

function createRipple(event: PointerEvent) {
  if (blocked.value || (typeof window.matchMedia === 'function' && window.matchMedia('(prefers-reduced-motion: reduce)').matches)) return
  const target = event.currentTarget as HTMLElement
  const rect = target.getBoundingClientRect()
  const size = Math.max(rect.width, rect.height) * 1.75
  ripple.value = {
    x: event.clientX - rect.left - size / 2,
    y: event.clientY - rect.top - size / 2,
    size,
    key: Date.now(),
  }
  window.setTimeout(() => { ripple.value = null }, 480)
}

function click(event: MouseEvent) {
  if (!blocked.value) emit('click', event)
}
</script>

<template>
  <button
    :type="type"
    class="wb-action"
    :class="[`wb-action--${variant}`, { 'wb-action--icon': iconOnly, 'is-loading': loading }]"
    :disabled="blocked"
    :aria-busy="loading || undefined"
    @pointerdown="createRipple"
    @click="click"
  >
    <span class="wb-action__stack">
      <span class="wb-action__content" :aria-hidden="loading">
        <span v-if="$slots.icon" class="wb-action__icon"><slot name="icon" /></span>
        <span v-if="!iconOnly" class="wb-action__label"><slot /></span>
      </span>
      <span v-if="loading" class="wb-action__content wb-action__loading" role="status">
        <LoaderCircle class="wb-spin" :size="16" aria-hidden="true" />
        <span v-if="!iconOnly">{{ loadingText }}</span>
      </span>
    </span>
    <span
      v-if="ripple"
      :key="ripple.key"
      class="wb-action__ripple"
      :style="{ left: `${ripple.x}px`, top: `${ripple.y}px`, width: `${ripple.size}px`, height: `${ripple.size}px` }"
      aria-hidden="true"
    />
  </button>
</template>
