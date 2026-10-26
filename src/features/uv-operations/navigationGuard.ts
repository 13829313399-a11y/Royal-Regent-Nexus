import { onBeforeUnmount } from 'vue'
import type { RouteLocationNormalized } from 'vue-router'

type Guard = (to: RouteLocationNormalized, from: RouteLocationNormalized) => boolean
const guards = new Set<Guard>()
export function useUvNavigationGuard(check: Guard) {
  guards.add(check)
  onBeforeUnmount(() => guards.delete(check))
}
export function sameUvPageScope(to: RouteLocationNormalized, from: RouteLocationNormalized) {
  return to.path === from.path && to.query.factory === from.query.factory
}
export function guardUvNavigation(to: RouteLocationNormalized, from: RouteLocationNormalized) {
  if (to.fullPath === from.fullPath || ['login', 'change-password', 'forbidden'].includes(String(to.name))) return true
  for (const check of guards) if (!check(to, from)) return false
  return true
}
