import { getSessionGeneration, getStoredSession, saveSession, invalidateNexusSession, isNexusSessionLocked, sessionFingerprint, type AuthSession } from './permissions'

export const NEXUS_RECHECK_EVENT = 'nexus-shipping-recheck'

/** Same identity invalidation channel and 45s refresh cadence as the Nexus shell. */
export function installNexusSessionSync(load: () => Promise<AuthSession>, settled: () => void) {
  let disposed = false
  let requestVersion = 0
  let pending: Promise<boolean> | null = null
  let transition: ReturnType<typeof setTimeout> | undefined
  const channel = typeof BroadcastChannel === 'undefined' ? null : new BroadcastChannel('rr-identity-refresh')

  function schedule(session: AuthSession) {
    clearTimeout(transition)
    const delay = Date.parse(session.nextTransitionAt || '') - Date.parse(session.serverNow || '')
    if (Number.isFinite(delay)) transition = setTimeout(() => { void refresh() }, Math.min(2_147_000_000, Math.max(250, delay + 100)))
  }

  async function refresh(): Promise<boolean> {
    if (disposed || isNexusSessionLocked()) return false
    if (pending) return pending
    const version = requestVersion
    const generation = getSessionGeneration()
    pending = (async () => {
      try {
        const session = await load()
        if (disposed || version !== requestVersion || generation !== getSessionGeneration()) return false
        const changed = sessionFingerprint(getStoredSession()) !== sessionFingerprint(session)
        if (changed && getStoredSession()) { invalidateNexusSession(); return false }
        saveSession(session)
        schedule(session)
        return !changed
      } catch {
        if (!disposed && version === requestVersion && generation === getSessionGeneration()) invalidateNexusSession()
        return false
      } finally {
        if (!disposed && version === requestVersion) { pending = null; settled() }
      }
    })()
    return pending
  }

  function boundary() {
    requestVersion++
    pending = null
    clearTimeout(transition)
    invalidateNexusSession()
    settled()
    if (document.visibilityState === 'visible') void refresh()
  }
  const visible = () => { if (document.visibilityState === 'visible') void refresh() }
  const recheck = () => { void refresh() }
  if (channel) channel.onmessage = event => {
    if (event.data === 'session-boundary-changed') boundary()
    if (event.data === 'refresh') recheck()
  }
  const interval = setInterval(visible, 45_000)
  window.addEventListener('focus', visible)
  window.addEventListener('online', visible)
  window.addEventListener(NEXUS_RECHECK_EVENT, recheck)
  document.addEventListener('visibilitychange', visible)
  void refresh()
  return () => {
    disposed = true; requestVersion++; clearInterval(interval); clearTimeout(transition); channel?.close()
    window.removeEventListener('focus', visible); window.removeEventListener('online', visible)
    window.removeEventListener(NEXUS_RECHECK_EVENT, recheck); document.removeEventListener('visibilitychange', visible)
  }
}
