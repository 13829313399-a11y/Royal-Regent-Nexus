<script setup lang="ts">
import type { RouteGhost } from './useRouteMotionHost'
import './route-motion.css'
defineProps<{ ghost: RouteGhost | null }>()
</script>
<template>
  <Teleport to="body">
    <div v-if="ghost" class="rr-route-motion" aria-hidden="true" inert>
      <div :data-route-motion-ghost="ghost.token" class="rr-route-motion__badge" :style="{ left: `${ghost.x}px`, top: `${ghost.y}px`, color: ghost.accent, '--route-accent-soft': ghost.soft }">
        <span class="rr-route-motion__surface" />
        <component :is="ghost.icon" :size="22" />
      </div>
    </div>
  </Teleport>
</template>
