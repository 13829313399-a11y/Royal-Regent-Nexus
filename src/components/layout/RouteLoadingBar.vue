<script setup lang="ts">
import { computed, onBeforeUnmount, ref, watch } from 'vue'
import { useAppStore } from '@/stores/app'
import { Progress } from '@/components/ui/progress'

const appStore = useAppStore()
const progressValue = ref(0)
const isVisible = ref(false)
const progressTimers: ReturnType<typeof setTimeout>[] = []

function clearProgressTimers() {
  progressTimers.splice(0).forEach((timer) => clearTimeout(timer))
}

function scheduleProgress(value: number, delay: number) {
  progressTimers.push(setTimeout(() => {
    progressValue.value = value
  }, delay))
}

watch(() => appStore.isRouteLoading, (isLoading) => {
  clearProgressTimers()

  if (isLoading) {
    isVisible.value = true
    progressValue.value = 14
    scheduleProgress(46, 90)
    scheduleProgress(72, 320)
    scheduleProgress(88, 760)
    return
  }

  if (!isVisible.value) {
    progressValue.value = 0
    return
  }

  progressValue.value = 100
  progressTimers.push(setTimeout(() => {
    isVisible.value = false
    progressValue.value = 0
  }, 220))
}, { immediate: true })

onBeforeUnmount(clearProgressTimers)

const trackClass = computed(() => [
  'h-[3px] rounded-none transition-colors duration-150',
  isVisible.value ? 'bg-teal-950/[0.04]' : 'bg-transparent',
])

const indicatorClass = computed(() => [
  'rounded-r-full bg-gradient-to-r from-teal-800 via-teal-500 to-cyan-400 shadow-[0_0_8px_rgba(13,148,136,0.28)] transition-[transform,opacity] duration-300 ease-out',
  isVisible.value ? 'opacity-100' : 'opacity-0',
])
</script>

<template>
  <Progress
    :model-value="progressValue"
    :class="trackClass"
    :indicator-class="indicatorClass"
    aria-hidden="true"
  />
</template>
