import { watch } from 'vue'
import type { Pinia } from 'pinia'
import type { Router } from 'vue-router'
import { useAuthStore } from '@/stores/auth'
import { refreshAndRevalidateAuthorization } from '@/router'

/** Broadcast only an invalidation signal, never identity data or credentials. */
export function installIdentitySync(router: Router, pinia: Pinia) {
  const auth = useAuthStore(pinia)
  let boundary: ReturnType<typeof setTimeout> | undefined
  let running = false
  let nextAllowedRefresh = 0
  let snapshotReceivedAt = Date.now()
  const channel = typeof BroadcastChannel !== 'undefined' ? new BroadcastChannel('rr-identity-refresh') : null
  const eligible = () => auth.isAuthenticated && navigator.onLine && document.visibilityState === 'visible'
  const refresh = async () => {
    if (!eligible() || running || Date.now() < nextAllowedRefresh) return
    running = true
    nextAllowedRefresh = Date.now() + 5_000
    try { await refreshAndRevalidateAuthorization(auth, router) } finally { running = false; scheduleBoundary() }
  }
  function scheduleBoundary() {
    clearTimeout(boundary)
    const identity = auth.currentUser?.identity
    if (!eligible() || !identity?.next_transition_at) return
    const delay = Date.parse(identity.next_transition_at) - Date.parse(identity.server_now) - (Date.now() - snapshotReceivedAt)
    if (Number.isFinite(delay)) boundary = setTimeout(() => { void refresh() }, Math.min(2_147_000_000, Math.max(250, nextAllowedRefresh - Date.now() + 100, delay + 100)))
  }
  const changed = () => { channel?.postMessage('refresh'); void refresh() }
  const visible = () => { if (eligible()) void refresh(); else clearTimeout(boundary) }
  const stop = watch(() => [auth.currentUser?.identity?.effective_context_key, auth.currentUser?.identity?.server_now, auth.isAuthenticated, auth.currentUser?.id], (values, previous) => {
    if (previous?.[0] && values[0] && values[3] === previous[3] && values[0] !== previous[0]) window.dispatchEvent(new Event('authorization-context-changed'))
    snapshotReceivedAt = Date.now()
    scheduleBoundary()
  }, { immediate: true })
  const interval = setInterval(() => { void refresh() }, 45_000)
  if (channel) channel.onmessage = e => { if (e.data === 'refresh') void refresh() }
  window.addEventListener('iam-identity-changed', changed)
  window.addEventListener('online', visible)
  document.addEventListener('visibilitychange', visible)
  return () => { clearTimeout(boundary); clearInterval(interval); channel?.close(); stop(); window.removeEventListener('iam-identity-changed', changed); window.removeEventListener('online', visible); document.removeEventListener('visibilitychange', visible) }
}
