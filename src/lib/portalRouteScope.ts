import type { RouteLocationNormalizedLoaded } from 'vue-router'
import { isModuleDepartmentId } from '@/data/enterpriseMock'

/**
 * 门户外观作用域判定。
 *
 * 这个函数只决定“当前路由是否启用门户外观”，它不替代鉴权、路由守卫、厂区选择或
 * fullPage 判断，也不改变任何路由注册。
 *
 * 尤其不要改成 `route.path.startsWith('/modules')`、`!route.meta.fullPage` 或按
 * 路径段数量判断：`/modules/:department/:module` 是模块详情页，必须保持默认外观。
 */

export type PortalScope =
  | 'dashboard'
  | 'department'
  | 'workbench'
  | 'people'
  | 'tools-entry'
  | 'users-entry'
  | 'roles-entry'
  | null

type RouteIdentity = Pick<RouteLocationNormalizedLoaded, 'name' | 'params'>

export function getPortalScope(route: RouteIdentity): PortalScope {
  if (route.name === 'modules-department') {
    const department = route.params.department
    return typeof department === 'string' && isModuleDepartmentId(department)
      ? 'department'
      : null
  }

  switch (route.name) {
    case 'dashboard':
      return 'dashboard'
    case 'workbench':
      return 'workbench'
    case 'people-directory':
      return 'people'
    case 'shared-tool-center':
      return 'tools-entry'
    case 'system-users':
      return 'users-entry'
    case 'iam-role-templates':
      return 'roles-entry'
    default:
      return null
  }
}

/** 普通应用壳（顶栏 + 侧栏）里允许做导航表面换肤的路由。 */
export function usesPortalShell(scope: PortalScope): boolean {
  return scope === 'dashboard'
    || scope === 'department'
    || scope === 'workbench'
    || scope === 'people'
    || scope === 'tools-entry'
}

/** 使用独立完整壳、只做局部页头换肤的入口。 */
export function usesPortalRegion(scope: PortalScope, region: 'tools-header' | 'users-header' | 'users-stats' | 'roles-header'): boolean {
  if (region === 'tools-header') return scope === 'tools-entry'
  if (region === 'roles-header') return scope === 'roles-entry'
  return scope === 'users-entry'
}

export function resolvePortalShellAttribute(scope: PortalScope): 'jade-v3' | undefined {
  return usesPortalShell(scope) ? 'jade-v3' : undefined
}

/** V4 is a presentation-only opt-in for the eight exact home routes. */
export function getHomeExperienceScope(route: RouteIdentity): 'dashboard' | 'department' | null {
  const scope = getPortalScope(route)
  return scope === 'dashboard' || scope === 'department' ? scope : null
}
