// Run before the router changes the global factory, as with the spray workspace.
let guard: (() => boolean) | null = null
export function registerInjectionNavigationGuard(value: () => boolean) {
  guard = value
  return () => { if (guard === value) guard = null }
}
export function guardInjectionNavigation(to: { fullPath: string; name?: unknown }, from: { fullPath: string }) {
  if (to.fullPath === from.fullPath || to.name === 'login' || to.name === 'change-password') return true
  return guard?.() ?? true
}
