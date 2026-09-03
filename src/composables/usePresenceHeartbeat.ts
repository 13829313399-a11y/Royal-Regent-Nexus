import { onBeforeUnmount, onMounted, watch } from 'vue'
import { directoryApi } from '@/api/directory'
import { useAuthStore } from '@/stores/auth'

export const HEARTBEAT_BASE_INTERVAL_MS = 60_000
export const HEARTBEAT_MAX_JITTER_MS = 10_000

export function usePresenceHeartbeat() {
  const authStore = useAuthStore()
  let timer: ReturnType<typeof setTimeout> | null = null
  let inFlight = false
  let disposed = false

  function clearTimer() {
    if (timer !== null) {
      clearTimeout(timer)
      timer = null
    }
  }

  function canSend() {
    return !disposed
      && authStore.isAuthenticated
      && !authStore.currentUser?.force_password_change
      && typeof document !== 'undefined'
      && document.visibilityState === 'visible'
      && (typeof navigator === 'undefined' || navigator.onLine !== false)
  }

  function scheduleNext() {
    clearTimer()
    if (!canSend()) return
    const jitter = Math.floor(Math.random() * (HEARTBEAT_MAX_JITTER_MS + 1))
    timer = setTimeout(() => void sendHeartbeat(), HEARTBEAT_BASE_INTERVAL_MS + jitter)
  }

  async function sendHeartbeat() {
    if (!canSend() || inFlight) return
    inFlight = true
    try {
      await directoryApi.sendHeartbeat()
    } catch {
      // Presence is non-critical and must never interrupt normal page work.
    } finally {
      inFlight = false
      scheduleNext()
    }
  }

  function resumeImmediately() {
    clearTimer()
    void sendHeartbeat()
  }

  function pause() {
    clearTimer()
  }

  function handleVisibilityChange() {
    if (document.visibilityState === 'visible') resumeImmediately()
    else pause()
  }

  onMounted(() => {
    document.addEventListener('visibilitychange', handleVisibilityChange)
    window.addEventListener('online', resumeImmediately)
    window.addEventListener('offline', pause)
    window.addEventListener('focus', resumeImmediately)
    if (authStore.isAuthenticated) resumeImmediately()
  })

  watch(
    () => authStore.sessionVersion,
    () => {
      if (authStore.isAuthenticated) resumeImmediately()
      else pause()
    },
  )

  onBeforeUnmount(() => {
    disposed = true
    clearTimer()
    document.removeEventListener('visibilitychange', handleVisibilityChange)
    window.removeEventListener('online', resumeImmediately)
    window.removeEventListener('offline', pause)
    window.removeEventListener('focus', resumeImmediately)
  })

  return { sendHeartbeat }
}
