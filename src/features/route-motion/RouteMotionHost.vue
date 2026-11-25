<script setup lang="ts">
import { ref } from 'vue'
import type { RouteGhost } from './useRouteMotionHost'
import type { SpatialDecoration } from './spatialRenderer'
import './route-motion.css'
import './local-motion.css'
defineProps<{ ghost: RouteGhost | null; spatial: SpatialDecoration | null }>()
const layer = ref<HTMLElement | null>(null)
defineExpose({ layer })
</script>
<template>
  <Teleport to="body">
    <div v-if="spatial || ghost" ref="layer" class="rr-route-motion" :data-rr-spatial-layer="spatial?.token" :data-rr-motion-chrome="spatial?.chrome || undefined"
      :style="spatial?.clip ? { clipPath: spatial.clip } : undefined" aria-hidden="true" inert>
      <template v-if="spatial">
        <div class="rr-spatial-plane" :style="{ left: spatial.surface.x + 'px', top: spatial.surface.y + 'px',
          width: spatial.surface.width + 'px', height: spatial.surface.height + 'px',
          '--rr-flight-accent': spatial.accent, '--rr-flight-soft': spatial.soft }" />
        <div v-if="spatial.badge" class="rr-spatial-icon" :style="{ left: spatial.badge.x + 'px', top: spatial.badge.y + 'px',
          width: spatial.badge.size + 'px', height: spatial.badge.size + 'px', color: spatial.accent, backgroundColor: spatial.soft }">
          <component :is="spatial.icon" aria-hidden="true" />
        </div>
      </template>
      <div v-else-if="ghost" :data-route-motion-ghost="ghost.token" class="rr-route-motion__badge" :style="{ left: `${ghost.x}px`, top: `${ghost.y}px`, color: ghost.accent, '--route-accent-soft': ghost.soft }">
        <span class="rr-route-motion__surface" />
        <component :is="ghost.icon" :size="22" />
      </div>
    </div>
  </Teleport>
</template>
