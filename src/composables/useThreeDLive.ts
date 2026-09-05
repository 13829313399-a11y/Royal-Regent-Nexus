import { ref } from 'vue'
import { http, dispatchAccessFailure } from '@/lib/http'
import type { ThreeDDashboard } from '@/types/threeDPrinting'

type Snapshot = Pick<ThreeDDashboard, 'printers' | 'network_health'> & { run_version: string }

export function useThreeDLive(onSnapshot: (value: Snapshot) => void) {
  const connected = ref(false)
  let source: EventSource | undefined
  let watchdog: ReturnType<typeof setInterval> | undefined
  let lastMessage = 0
  const stop = () => {
    source?.close(); source = undefined; connected.value = false
    clearInterval(watchdog)
  }
  const start = () => {
    stop()
    if (typeof EventSource === 'undefined') return
    const url = `${http.defaults.baseURL ?? '/api'}/three-d-printing/live/events?factory_id=huakang-a`
    source = new EventSource(url, { withCredentials: true })
    lastMessage = Date.now()
    watchdog = setInterval(() => {
      if (Date.now() - lastMessage > 15000) connected.value = false
    }, 5000)
    const receive = (message: MessageEvent) => {
      try {
        const value = JSON.parse(message.data) as Snapshot
        if (!Array.isArray(value.printers) || typeof value.run_version !== 'string') return
        connected.value = true
        lastMessage = Date.now()
        onSnapshot(value)
      } catch { connected.value = false }
    }
    source.addEventListener('snapshot', receive)
    source.addEventListener('reset', receive)
    source.addEventListener('ping', () => { lastMessage = Date.now(); connected.value = true })
    source.addEventListener('access_revoked', (message: MessageEvent) => {
      stop()
      try { dispatchAccessFailure(JSON.parse(message.data).status, url) } catch { /* closed */ }
    })
    source.onerror = () => { connected.value = false } // Native reconnect retains Last-Event-ID.
  }
  return { connected, start, stop }
}
