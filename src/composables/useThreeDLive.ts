import { ref } from 'vue'
import { http, dispatchAccessFailure } from '@/lib/http'
import type { ThreeDDashboard } from '@/types/threeDPrinting'

type Snapshot = Pick<ThreeDDashboard, 'printers' | 'network_health'> & { run_version: string }

export function useThreeDLive(onSnapshot: (value: Snapshot) => void) {
  const connected = ref(false)
  let source: EventSource | undefined
  let watchdog: ReturnType<typeof setInterval> | undefined
  let lastMessage = 0
  let running = false
  const resume = () => {
    if (running && document.visibilityState !== 'hidden' &&
        (!connected.value || Date.now() - lastMessage > 10000)) open()
  }
  const stop = () => {
    running = false
    source?.close(); source = undefined; connected.value = false
    clearInterval(watchdog)
    window.removeEventListener('online', resume)
    window.removeEventListener('focus', resume)
    document.removeEventListener('visibilitychange', resume)
  }
  const open = () => {
    source?.close()
    connected.value = false
    const url = `${http.defaults.baseURL ?? '/api'}/three-d-printing/live/events?factory_id=huakang-a`
    const stream = new EventSource(url, { withCredentials: true })
    source = stream
    let hasSnapshot = false
    const current = () => running && source === stream
    lastMessage = Date.now()
    const receive = (message: MessageEvent) => {
      if (!current()) return
      try {
        const value = JSON.parse(message.data) as Snapshot
        if (!Array.isArray(value.printers) || typeof value.run_version !== 'string') return
        hasSnapshot = true
        connected.value = true
        lastMessage = Date.now()
        onSnapshot(value)
      } catch { connected.value = false }
    }
    stream.addEventListener('snapshot', receive)
    stream.addEventListener('reset', receive)
    stream.addEventListener('ping', () => {
      if (!current() || !hasSnapshot) return
      lastMessage = Date.now(); connected.value = true
    })
    stream.addEventListener('access_revoked', (message: MessageEvent) => {
      if (!current()) return
      stop()
      try { dispatchAccessFailure(JSON.parse(message.data).status, url) } catch { /* closed */ }
    })
    stream.onerror = () => { if (current()) connected.value = false } // Native reconnect retains Last-Event-ID.
  }
  const start = () => {
    stop()
    if (typeof EventSource === 'undefined') return
    running = true
    open()
    watchdog = setInterval(() => {
      // A half-open stream may never raise onerror. Reopen for a fresh DB snapshot.
      if (Date.now() - lastMessage >= 15000) open()
    }, 5000)
    window.addEventListener('online', resume)
    window.addEventListener('focus', resume)
    document.addEventListener('visibilitychange', resume)
  }
  return { connected, start, stop }
}
