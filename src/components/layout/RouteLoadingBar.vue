<script setup lang="ts">
import { useAppStore } from '@/stores/app'

const appStore = useAppStore()
</script>

<template>
  <div
    class="h-2 w-full overflow-hidden rounded-full transition-colors duration-150"
    :class="appStore.isRouteLoading ? 'bg-slate-200/80' : 'bg-transparent'"
    aria-hidden="true"
  >
    <Transition name="route-loading">
      <div
        v-if="appStore.isRouteLoading"
        class="route-loading-bar h-full w-full rounded-full bg-gradient-to-r from-teal-600 via-cyan-400 to-sky-600 shadow-[0_0_18px_rgba(8,145,178,0.55)]"
      />
    </Transition>
  </div>
</template>

<style scoped>
.route-loading-bar {
  transform-origin: left center;
  animation: route-loading-sweep 820ms cubic-bezier(0.65, 0, 0.35, 1) infinite;
}

.route-loading-enter-active,
.route-loading-leave-active {
  transition: opacity 160ms ease;
}

.route-loading-enter-from,
.route-loading-leave-to {
  opacity: 0;
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
