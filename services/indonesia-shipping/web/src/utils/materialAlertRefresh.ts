export const MATERIAL_ALERT_REFRESH = 'material-alerts-refresh'

export function refreshMaterialAlerts() {
  window.dispatchEvent(new Event(MATERIAL_ALERT_REFRESH))
}

/** Discard old responses after a newer refresh or after the workspace closes. */
export function watchMaterialAlerts<T>(load: () => Promise<T>, publish: (value: T) => void,
  failed: (error: unknown) => void, target: EventTarget = window) {
  let sequence = 0
  let stopped = false
  const refresh = async () => {
    const current = ++sequence
    try {
      const value = await load()
      if (!stopped && current === sequence) publish(value)
    } catch (error) {
      if (!stopped && current === sequence) failed(error)
    }
  }
  target.addEventListener(MATERIAL_ALERT_REFRESH, refresh)
  target.addEventListener('focus', refresh)
  const timer = setInterval(refresh, 5 * 60 * 1000)
  void refresh()
  return () => {
    stopped = true
    clearInterval(timer)
    target.removeEventListener(MATERIAL_ALERT_REFRESH, refresh)
    target.removeEventListener('focus', refresh)
  }
}
