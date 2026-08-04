import { onBeforeUnmount, onMounted } from 'vue'

export function useSchedulePolling(refresh: () => Promise<void>, intervalMs = 30_000) {
  let timer: ReturnType<typeof window.setInterval> | undefined
  onMounted(() => {
    timer = window.setInterval(() => void refresh(), intervalMs)
  })
  onBeforeUnmount(() => {
    if (timer) window.clearInterval(timer)
  })
}
