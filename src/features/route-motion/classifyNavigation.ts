import type { RouteLocationNormalized } from 'vue-router'
import { getHomeExperienceScope } from '@/lib/portalRouteScope'

export type MotionRoute = Pick<RouteLocationNormalized, 'params' | 'query' | 'meta' | 'matched' | 'path' | 'fullPath'> & { name?: string | symbol | null }
export type MotionKind = 'home-to-department' | 'home-to-module' | 'module-to-home' | 'module-to-module' | 'none'

// These sibling records share one workspace. Nested features use their actual
// matched parent record, including unnamed cutting/warehouse children.
const qcFamily = new Set(['qc-inspection-schedule', 'qc-inspection-schedule-details', 'qc-inspection-order-records', 'qc-inspection-order-detail', 'qc-inspection-problems', 'qc-inspection-reports'])
const authRoutes = new Set(['login', 'register', 'reset-password', 'change-password'])

export function routeVisualIdentity(route: MotionRoute) {
  const name = String(route.name ?? '')
  const home = getHomeExperienceScope({ name: route.name ?? undefined, params: route.params })
  if (home) return { id: home === 'dashboard' ? 'home:dashboard' : `home:${String(route.params.department)}`, home: true, eligible: true }
  if (!route.matched.length || authRoutes.has(name) || name === 'forbidden' || route.meta.requiresAuth === false) {
    return { id: `excluded:${name}`, home: false, eligible: false }
  }
  const root = route.matched[0]!
  const canonical = root.aliasOf ?? root
  const id = name === 'module-detail'
    ? `module:${String(route.params.department)}:${String(route.params.module)}`
    : qcFamily.has(name) ? 'workspace:qc-inspection'
      : `workspace:${String(canonical.name ?? canonical.path)}`
  return { id, home: false, eligible: true }
}

export function factoryQueryChanged(to: MotionRoute, from: MotionRoute) {
  // Some registered destinations (supplier workspaces, dashboard) inherit the
  // active factory rather than repeating it in the URL. Actual store boundaries
  // are also observed by the host. Adding/removing that query on a different
  // family is not itself a factory switch.
  if (routeVisualIdentity(to).id !== routeVisualIdentity(from).id && (to.query.factory == null || from.query.factory == null)) return false
  return JSON.stringify(to.query.factory ?? null) !== JSON.stringify(from.query.factory ?? null)
}

export function classifyNavigation(to: MotionRoute, from: MotionRoute): MotionKind {
  const target = routeVisualIdentity(to), source = routeVisualIdentity(from)
  if (!target.eligible || !source.eligible || factoryQueryChanged(to, from) || target.id === source.id) return 'none'
  if (target.home) return source.home ? 'home-to-department' : 'module-to-home'
  return source.home ? 'home-to-module' : 'module-to-module'
}
