// Check before the global router changes the selected factory and destroys its iframe.
let guard: (() => boolean | Promise<boolean>) | null = null
export function registerShippingNavigationGuard(value: () => boolean | Promise<boolean>) {
  guard = value
  return () => { if (guard === value) guard = null }
}
export function guardShippingNavigation(to: { fullPath: string; name?: unknown; meta?: Record<string, unknown> }, from: { fullPath: string }) {
  if (to.fullPath === from.fullPath || to.meta?.requiresAuth === false || ['login', 'change-password', 'forbidden'].includes(String(to.name))) return true
  return guard?.() ?? true
}
