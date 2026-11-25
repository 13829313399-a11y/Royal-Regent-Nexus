import { computed, inject } from 'vue'
import { homeAppearanceKey } from '@/composables/useHomeAppearance'

/** A local surface opts in at its owner and passes the mode through any portal. */
export function useLocalMotion() {
  const appearance = inject(homeAppearanceKey, null)
  return computed(() => {
    if (import.meta.env.VITE_ROUTE_MOTION_V2_ENABLED !== 'true' || import.meta.env.VITE_ROUTE_MOTION_ENABLED === 'false') return undefined
    return appearance?.effectiveMotion.value ?? 'off'
  })
}
