// The host invokes this before changing the global factory context. Component
// update guards run too late: that would clear the old factory's unsaved form.
let guard: (() => boolean | Promise<boolean>) | null = null
export function registerSprayNavigationGuard(value: () => boolean | Promise<boolean>) { guard = value; return () => { if (guard === value) guard = null } }
export function guardSprayNavigation(to: { fullPath: string; name?: unknown }, from: { fullPath: string }) {
  if (to.fullPath === from.fullPath || to.name === 'login' || to.name === 'change-password') return true
  return guard?.() ?? true
}
