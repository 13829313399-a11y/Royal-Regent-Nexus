import { computed, inject, onBeforeUnmount, onMounted, provide, ref, watch, type InjectionKey } from 'vue'

export type UvMotionPreference = 'system' | 'off'
const key: InjectionKey<ReturnType<typeof createUvMotionPreference>> = Symbol('uv-motion')
const storagePrefix = 'rr.uv.motion.v1.'

export function createUvMotionPreference(userId: () => string | number | null | undefined) {
  const preference = ref<UvMotionPreference>('system')
  const reduced = ref(true), hidden = ref(typeof document === 'undefined' || document.hidden)
  const session = new Map<string, UvMotionPreference>()
  let media: MediaQueryList | undefined, currentKey = ''
  const allowed = computed(() => !reduced.value && !hidden.value && preference.value === 'system')
  const attribute = computed(() => allowed.value ? 'on' : 'off')
  const valid = (value: unknown): value is UvMotionPreference => value === 'off' || value === 'system'
  watch(userId, id => {
    currentKey = id == null ? '' : storagePrefix + encodeURIComponent(String(id))
    let stored: unknown = session.get(currentKey)
    if (currentKey && !session.has(currentKey)) { try { stored = localStorage.getItem(currentKey) } catch { /* session fallback */ } }
    preference.value = valid(stored) ? stored : 'system'
  }, { immediate: true, flush: 'sync' })
  function setPreference(value: UvMotionPreference) {
    if (!valid(value)) return
    preference.value = value
    session.set(currentKey, value)
    if (currentKey) { try { localStorage.setItem(currentKey, value) } catch { /* no persistent storage available */ } }
  }
  const updateMedia = () => { reduced.value = media?.matches ?? true }
  const updateVisibility = () => { hidden.value = document.hidden }
  onMounted(() => {
    media = window.matchMedia('(prefers-reduced-motion: reduce)')
    updateMedia(); updateVisibility()
    media.addEventListener('change', updateMedia)
    document.addEventListener('visibilitychange', updateVisibility)
  })
  onBeforeUnmount(() => {
    media?.removeEventListener('change', updateMedia)
    document.removeEventListener('visibilitychange', updateVisibility)
  })
  return { preference, reduced, hidden, allowed, attribute, setPreference }
}

export function provideUvMotionPreference(userId: () => string | number | null | undefined) {
  const motion = createUvMotionPreference(userId)
  provide(key, motion)
  return motion
}

// Components mounted outside the workspace (including tests) settle synchronously.
export function useUvMotion() {
  return inject(key, null) ?? {
    preference: ref<UvMotionPreference>('off'), reduced: ref(true), hidden: ref(false),
    allowed: computed(() => false), attribute: computed(() => 'off'), setPreference: (_: UvMotionPreference) => {},
  }
}
