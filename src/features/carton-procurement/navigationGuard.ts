let guard: (() => boolean) | null = null
export function registerCartonNavigationGuard(check: () => boolean) {
  guard = check
  return () => { if (guard === check) guard = null }
}
export function guardCartonNavigation(to: { fullPath: string; name?: unknown }, from: { fullPath: string }) {
  if (to.fullPath === from.fullPath || to.name === 'login' || to.name === 'change-password') return true
  return guard?.() ?? true
}
