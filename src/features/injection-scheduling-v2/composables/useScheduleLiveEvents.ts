import { onBeforeUnmount, onMounted } from 'vue'

export function useScheduleLiveEvents(poll: () => Promise<void>, intervalMs = 12_000) {
  let timer: ReturnType<typeof window.setInterval> | undefined
  let running = false
  async function tick() {
    if (running) return
    running = true
    try {
      await poll()
    } finally {
      running = false
    }
  }
  onMounted(() => {
    timer = window.setInterval(() => void tick(), intervalMs)
  })
  onBeforeUnmount(() => {
    if (timer) window.clearInterval(timer)
  })
}
