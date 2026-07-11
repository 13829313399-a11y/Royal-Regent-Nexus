import { createRouter, createWebHistory, type RouteRecordRaw } from 'vue-router'
import DashboardView from '@/views/DashboardView.vue'
import { getDepartmentModule, isModuleDepartmentId } from '@/data/enterpriseMock'
import { installBrowserBackExitGuard } from '@/lib/browserBackExitGuard'
import { resolvePostLoginRedirect } from '@/lib/postLoginRedirect'
import { useAppStore } from '@/stores/app'
import { useAuthStore } from '@/stores/auth'

const routes: RouteRecordRaw[] = [
  {
    path: '/login',
    name: 'login',
    component: () => import('@/views/LoginView.vue'),
    meta: {
      title: '账号登录',
      fullPage: true,
      requiresAuth: false,
    },
  },
  {
    path: '/register',
    name: 'register',
    component: () => import('@/views/RegisterView.vue'),
    meta: {
      title: '账号申请',
      fullPage: true,
      requiresAuth: false,
    },
  },
  {
    path: '/',
    name: 'dashboard',
    component: DashboardView,
    meta: {
      title: '集团运营总览',
      requiresAuth: true,
    },
  },
  {
    path: '/modules',
    redirect: '/modules/engineering',
  },
  {
    path: '/modules/:department',
    name: 'modules-department',
    component: () => import('@/views/ModuleCenterView.vue'),
    meta: {
      title: '部门模块中心',
      requiresAuth: true,
    },
    beforeEnter: (to) => {
      const department = String(to.params.department ?? '')
      if (!isModuleDepartmentId(department)) {
        return { path: '/modules/engineering', replace: true }
      }

      return true
    },
  },
  {
    path: '/modules/production/injection-scheduling',
    name: 'injection-scheduling',
    component: () => import('@/views/InjectionSchedulingView.vue'),
    meta: {
      title: '注塑生产中枢',
      fullPage: true,
      requiresAuth: true,
      permissions: ['injection_schedule:read'],
      enforcePermissions: true,
    },
  },
  {
    path: '/modules/production/molding-sample-tasks',
    name: 'molding-sample-production-tasks',
    component: () => import('@/views/MoldingSampleProductionTaskView.vue'),
    meta: {
      title: '啤办生产任务单',
      fullPage: true,
      requiresAuth: true,
      permissions: ['molding_sample:production_read'],
      enforcePermissions: true,
    },
  },
  {
    path: '/modules/pmc-warehouse/raw-material-management',
    name: 'raw-material-management',
    component: () => import('@/views/RawMaterialManagementView.vue'),
    meta: {
      title: '原料管理模块',
      fullPage: true,
      requiresAuth: true,
      permissions: ['molding_sample:warehouse_requisition'],
      enforcePermissions: true,
    },
  },
  {
    path: '/modules/sales-business/quote-center',
    name: 'quote-center',
    component: () => import('@/views/CustomerPriceConversionView.vue'),
    meta: {
      title: '报价与成本中心',
      fullPage: true,
      requiresAuth: true,
      permissions: ['customer_price:read'],
      enforcePermissions: true,
    },
  },
  {
    path: '/modules/sales-business/quote-center/customer-price-conversion',
    redirect: '/modules/sales-business/quote-center',
  },
  {
    path: '/modules/:department/:module',
    name: 'module-detail',
    component: () => import('@/views/ModuleDetailView.vue'),
    meta: {
      title: '模块详情',
      requiresAuth: true,
    },
    beforeEnter: (to) => {
      const department = String(to.params.department ?? '')
      const moduleId = String(to.params.module ?? '')

      if (!isModuleDepartmentId(department)) {
        return { path: '/modules/engineering', replace: true }
      }

      if (!getDepartmentModule(department, moduleId)) {
        return { path: `/modules/${department}`, replace: true }
      }

      return true
    },
  },
  {
    path: '/modules/molding-sample',
    name: 'molding-sample',
    component: () => import('@/views/MoldingSampleView.vue'),
    meta: {
      title: '啤办进度追踪',
      fullPage: true,
      requiresAuth: true,
      permissions: ['molding_sample:read'],
      enforcePermissions: true,
    },
  },
  {
    path: '/workbench',
    name: 'workbench',
    component: () => import('@/views/ApprovalWorkbenchView.vue'),
    meta: {
      title: '业务审批工作台',
      requiresAuth: true,
    },
  },
  {
    path: '/system/users',
    name: 'system-users',
    component: () => import('@/views/SystemUserManagementView.vue'),
    meta: {
      title: '账号与权限管理',
      fullPage: true,
      requiresAuth: true,
      permissions: ['system:user_manage'],
      enforcePermissions: true,
    },
  },
  {
    path: '/system/users/:userId/access',
    name: 'system-user-access',
    component: () => import('@/views/UserAccessManagementView.vue'),
    meta: {
      title: '用户权限配置',
      fullPage: true,
      requiresAuth: true,
      permissions: ['system:access_manage'],
      enforcePermissions: true,
    },
  },
  {
    path: '/system/iam/roles',
    name: 'iam-role-templates',
    component: () => import('@/views/IamRoleTemplatesView.vue'),
    meta: {
      title: '角色模板',
      fullPage: true,
      requiresAuth: true,
      permissions: ['system:permission_catalog_read'],
      enforcePermissions: true,
    },
  },
  {
    path: '/system/iam/permissions',
    name: 'iam-permission-catalog',
    component: () => import('@/views/IamPermissionCatalogView.vue'),
    meta: {
      title: '权限目录',
      fullPage: true,
      requiresAuth: true,
      permissions: ['system:permission_catalog_read'],
      enforcePermissions: true,
    },
  },
  {
    path: '/system/iam/requests',
    name: 'iam-access-requests',
    component: () => import('@/views/IamAccessRequestsView.vue'),
    meta: {
      title: '权限申请',
      fullPage: true,
      requiresAuth: true,
      permissions: ['system:access_request', 'system:access_approve'],
      enforcePermissions: true,
    },
  },
  {
    path: '/system/iam/audit',
    name: 'iam-audit-events',
    component: () => import('@/views/IamAuditView.vue'),
    meta: {
      title: '权限操作记录',
      fullPage: true,
      requiresAuth: true,
      permissions: ['system:audit_read'],
      enforcePermissions: true,
    },
  },
  {
    path: '/forbidden',
    name: 'forbidden',
    component: () => import('@/views/ForbiddenView.vue'),
    meta: {
      title: '无权限访问',
      fullPage: true,
      requiresAuth: true,
    },
  },
  {
    path: '/:pathMatch(.*)*',
    redirect: '/',
  },
]

export const router = createRouter({
  history: createWebHistory(import.meta.env.BASE_URL),
  routes,
})

let routeLoadingStartedAt = 0
let routeLoadingTimer: ReturnType<typeof window.setTimeout> | undefined
let lastAuthorizationRefreshAt = 0
const browserBackExitGuard = installBrowserBackExitGuard(router)

type AuthorizationRefreshResult = 'refreshed' | 'forbidden' | 'login' | 'unchanged'

interface AuthorizationRefreshStore {
  isAuthenticated: boolean
  refreshSession: () => Promise<boolean>
  canAny: (permissions: string[]) => boolean
}

interface AuthorizationRefreshRouter {
  currentRoute: {
    value: {
      name?: unknown
      fullPath?: string
      meta: Record<string, unknown>
    }
  }
  replace: (location: { name: string; query?: Record<string, string> }) => unknown
}

export async function refreshAndRevalidateAuthorization(
  authStore: AuthorizationRefreshStore,
  activeRouter: AuthorizationRefreshRouter,
): Promise<AuthorizationRefreshResult> {
  const refreshSucceeded = await authStore.refreshSession()
  const currentRoute = activeRouter.currentRoute.value
  const isPublicRoute = currentRoute.name === 'login' || currentRoute.meta.requiresAuth === false

  if (!refreshSucceeded) {
    if (!authStore.isAuthenticated && !isPublicRoute) {
      const redirect = currentRoute.fullPath && currentRoute.fullPath !== '/login'
        ? currentRoute.fullPath
        : '/'
      await activeRouter.replace({ name: 'login', query: { redirect } })
      return 'login'
    }
    return 'unchanged'
  }

  if (isPublicRoute) return 'refreshed'

  const permissions = Array.isArray(currentRoute.meta.permissions)
    ? currentRoute.meta.permissions.filter((permission): permission is string => typeof permission === 'string')
    : []
  const shouldEnforcePermissions = currentRoute.meta.enforcePermissions === true
  if (
    currentRoute.name !== 'forbidden'
    && shouldEnforcePermissions
    && permissions.length
    && !authStore.canAny(permissions)
  ) {
    await activeRouter.replace({ name: 'forbidden' })
    return 'forbidden'
  }

  return 'refreshed'
}

const refreshAuthorizationSnapshot = () => {
  const authStore = useAuthStore()
  const now = Date.now()
  if (!authStore.isAuthenticated || now - lastAuthorizationRefreshAt < 15_000) return
  lastAuthorizationRefreshAt = now
  void refreshAndRevalidateAuthorization(authStore, router)
}

window.addEventListener('focus', refreshAuthorizationSnapshot)

const finishRouteLoading = () => {
  if (routeLoadingTimer) {
    window.clearTimeout(routeLoadingTimer)
  }

  const elapsed = window.performance.now() - routeLoadingStartedAt
  const remainingTime = Math.max(180 - elapsed, 0)

  routeLoadingTimer = window.setTimeout(() => {
    useAppStore().finishRouteLoading()
  }, remainingTime)
}

router.beforeEach(async (to) => {
  if (routeLoadingTimer) {
    window.clearTimeout(routeLoadingTimer)
  }

  routeLoadingStartedAt = window.performance.now()
  useAppStore().startRouteLoading()

  const authStore = useAuthStore()
  if (to.name === 'login') {
    if (to.query.logged_out === '1') {
      return true
    }

    if (authStore.isAuthenticated || await authStore.ensureSession()) {
      return { path: resolvePostLoginRedirect(router, to.query.redirect), replace: true }
    }

    return true
  }

  const requiresAuth = to.meta.requiresAuth !== false
  if (requiresAuth && !await authStore.ensureSession()) {
    return {
      name: 'login',
      query: { redirect: to.fullPath },
      replace: true,
    }
  }

  const permissions = Array.isArray(to.meta.permissions) ? to.meta.permissions as string[] : []
  const shouldEnforcePermissions = to.meta.enforcePermissions === true
  if (shouldEnforcePermissions && permissions.length && !authStore.canAny(permissions)) {
    return {
      name: 'forbidden',
      replace: true,
    }
  }

  return true
})

router.afterEach((to) => {
  if (to.meta.requiresAuth === false) {
    browserBackExitGuard.unlock()
  } else {
    browserBackExitGuard.lock(to.fullPath)
    refreshAuthorizationSnapshot()
  }

  const routeTitle = typeof to.meta.title === 'string' ? to.meta.title : 'Workspace'
  const department = String(to.params.department ?? '')
  const moduleId = String(to.params.module ?? '')

  const title = isModuleDepartmentId(department) && moduleId
    ? getDepartmentModule(department, moduleId)?.title ?? routeTitle
    : routeTitle

  document.title = `${title} | Royal Regent Nexus`
  finishRouteLoading()
})

router.onError(() => {
  finishRouteLoading()
})
