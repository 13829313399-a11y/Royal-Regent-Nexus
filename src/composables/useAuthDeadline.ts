import { computed, onBeforeUnmount, onMounted, ref } from 'vue'
// Shared across auth route changes; deadline is never reset by a render.
const loginDeadline = ref(0)
export function useAuthDeadline() {
  const now = ref(Date.now())
  let timer: ReturnType<typeof setTimeout> | undefined
  function tick() {
    clearTimeout(timer)
    now.value = Date.now()
    if (document.visibilityState === 'visible' && loginDeadline.value > now.value) timer = setTimeout(tick, 1000)
  }
  function setRetryAfter(seconds: number) { loginDeadline.value = Date.now() + seconds * 1000; tick() }
  onMounted(() => { document.addEventListener('visibilitychange', tick); tick() })
  onBeforeUnmount(() => { clearTimeout(timer); document.removeEventListener('visibilitychange', tick) })
  return { remaining: computed(() => Math.max(0, Math.ceil((loginDeadline.value - now.value) / 1000))), setRetryAfter }
}
