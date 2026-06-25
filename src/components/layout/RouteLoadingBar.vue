<script setup lang="ts">
import { computed } from 'vue'
import { useAppStore } from '@/stores/app'
import { Progress } from '@/components/ui/progress'

const appStore = useAppStore()

const progressValue = computed(() => appStore.isRouteLoading ? null : 0)

const trackClass = computed(() => [
  'h-1.5 transition-colors duration-150',
  appStore.isRouteLoading ? 'bg-emerald-100/80' : 'bg-transparent',
])

const indicatorClass = computed(() => [
  'rounded-full bg-gradient-to-r from-emerald-600 via-green-400 to-lime-500 shadow-[0_0_18px_rgba(22,163,74,0.55)]',
  appStore.isRouteLoading ? 'route-loading-bar opacity-100' : 'opacity-0',
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

<style scoped>
.route-loading-bar {
  transform-origin: left center;
  animation: route-loading-sweep 820ms cubic-bezier(0.65, 0, 0.35, 1) infinite;
}

@keyframes route-loading-sweep {
  0% {
    transform: translateX(-70%) scaleX(0.28);
  }

  46% {
    transform: translateX(-12%) scaleX(0.72);
  }

  100% {
    transform: translateX(42%) scaleX(0.9);
  }
}

@media (prefers-reduced-motion: reduce) {
  .route-loading-bar {
    animation: none;
    transform: scaleX(1);
  }
}
</style>
