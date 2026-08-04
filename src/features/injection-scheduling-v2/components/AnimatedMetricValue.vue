<script setup lang="ts">
import { onBeforeUnmount, ref, watch } from 'vue'

const props = withDefaults(defineProps<{ value: number; decimals?: number }>(), { decimals: 0 })
const displayValue = ref(props.value)
let frame = 0

function prefersReducedMotion() {
  return typeof window !== 'undefined' && typeof window.matchMedia === 'function' && window.matchMedia('(prefers-reduced-motion: reduce)').matches
}

watch(() => props.value, (next, previous) => {
  cancelAnimationFrame(frame)
  if (previous === undefined || prefersReducedMotion() || next === previous || typeof requestAnimationFrame !== 'function') {
    displayValue.value = next
    return
  }
  const start = performance.now()
  const from = typeof previous === 'number' && Number.isFinite(previous) ? previous : 0
  const duration = 320
  const tick = (now: number) => {
    const progress = Math.min(1, (now - start) / duration)
    const eased = 1 - Math.pow(1 - progress, 3)
    displayValue.value = from + (next - from) * eased
    if (progress < 1) frame = requestAnimationFrame(tick)
  }
  frame = requestAnimationFrame(tick)
}, { immediate: true })

onBeforeUnmount(() => cancelAnimationFrame(frame))
</script>

<template>{{ displayValue.toLocaleString('zh-CN', { minimumFractionDigits: decimals, maximumFractionDigits: decimals }) }}</template>
