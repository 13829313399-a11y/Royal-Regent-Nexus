import type { RouteLocationNormalized } from 'vue-router'

type Guard = (to: RouteLocationNormalized, from: RouteLocationNormalized) => boolean | Promise<boolean>
const guards = new Set<Guard>()

export function registerQuoteNavigationGuard(check: Guard) {
  guards.add(check)
  return () => guards.delete(check)
}

// Identity changes discard private state, including confirmations from the old actor.
export function clearQuoteNavigationGuards() { guards.clear() }

export async function guardQuoteNavigation(to: RouteLocationNormalized, from: RouteLocationNormalized) {
  if (to.fullPath === from.fullPath || ['login', 'change-password', 'forbidden'].includes(String(to.name))) return true
  for (const guard of [...guards]) {
    if (guards.has(guard) && !await guard(to, from)) return false
  }
  return true
}
