import { computed, inject, onBeforeUnmount, onMounted, provide, ref, watch, type InjectionKey, type Ref } from 'vue'
import { useAuthStore } from '@/stores/auth'

export type HomeMotion = 'expressive' | 'calm' | 'off'
export type HomeDensity = 'comfortable' | 'compact'
export const HOME_PREFERENCE_VERSION = 1
const motionOptions = ['expressive', 'calm', 'off']
const densityOptions = ['comfortable', 'compact']

export function createHomeAppearance(enabled: Ref<boolean> = ref(true)) {
  const auth = useAuthStore()
  const motion = ref<HomeMotion>('expressive')
  const density = ref<HomeDensity>('comfortable')
  const reduced = ref(false)
  const hidden = ref(false)
  const effectiveMotion = computed(() => reduced.value || hidden.value ? 'off' : motion.value)
  let media: MediaQueryList | undefined
  let loading = false
  let guest = { motion: 'expressive' as HomeMotion, density: 'comfortable' as HomeDensity }
  const key = computed(() => auth.currentUser?.id ? `rrn:home-prism:v1:${encodeURIComponent(auth.currentUser.id)}` : null)
  watch(key, () => {
    loading = true
    let value: { motion?: unknown; density?: unknown; version?: unknown } = key.value ? {} : guest
    try {
      if (key.value) {
        const stored = JSON.parse(localStorage.getItem(key.value) ?? 'null')
        if (stored?.version === HOME_PREFERENCE_VERSION) value = stored
      }
    } catch { /* Preferences never block navigation when storage is unavailable. */ }
    motion.value = motionOptions.includes(String(value.motion)) ? value.motion as HomeMotion : 'expressive'
    density.value = densityOptions.includes(String(value.density)) ? value.density as HomeDensity : 'comfortable'
    loading = false
  }, { immediate: true, flush: 'sync' })
  watch([motion, density], () => {
    if (loading) return
    if (!key.value) { guest = { motion: motion.value, density: density.value }; return }
    try {
      localStorage.setItem(key.value, JSON.stringify({ version: HOME_PREFERENCE_VERSION, motion: motion.value, density: density.value }))
    } catch { /* Keep the current in-memory choice. */ }
  }, { flush: 'sync' })
  function updateMotion() { reduced.value = media?.matches ?? false }
  function updateVisibility() { hidden.value = document.visibilityState === 'hidden' }
  function disconnect() {
    media?.removeEventListener('change', updateMotion)
    document.removeEventListener('visibilitychange', updateVisibility)
    media = undefined
  }
  function connect() {
    disconnect()
    if (!enabled.value) return
    media = window.matchMedia?.('(prefers-reduced-motion: reduce)')
    media?.addEventListener('change', updateMotion)
    document.addEventListener('visibilitychange', updateVisibility)
    updateMotion(); updateVisibility()
  }
  onMounted(connect)
  watch(enabled, connect)
  onBeforeUnmount(disconnect)
  return { motion, density, reduced, effectiveMotion }
}
export type HomeAppearance = ReturnType<typeof createHomeAppearance>
export const homeAppearanceKey: InjectionKey<HomeAppearance> = Symbol('home-appearance')
export const homeSearchKey: InjectionKey<Ref<number>> = Symbol('home-search')
export function useHomeAppearance() {
  const inherited = inject(homeAppearanceKey, null)
  if (inherited) return inherited
  const appearance = createHomeAppearance()
  provide(homeAppearanceKey, appearance)
  return appearance
}
