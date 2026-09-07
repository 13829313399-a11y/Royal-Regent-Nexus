import { createRouter, createWebHistory, type RouteRecordRaw } from 'vue-router'
import DashboardView from '@/views/DashboardView.vue'
import {
  shouldEnforcePagePermissions,
  shouldRedirectForbiddenPageToHome,
} from '@/config/pageAccessPolicy'
import { getDepartmentModule, isModuleDepartmentId } from '@/data/enterpriseMock'
import { installBrowserBackExitGuard } from '@/lib/browserBackExitGuard'
import { resolvePostLoginRedirect } from '@/lib/postLoginRedirect'
import { useAppStore } from '@/stores/app'
import { useAuthStore } from '@/stores/auth'

const qcInspectionOperationsView = () => import('@/views/QcInspectionOperationsView.vue')
const qcInspectionFullPageMeta = {
  fullPage: true,
  requiresAuth: true,
  permissions: ['qc_inspection:read'],
  enforcePermissions: true,
  allowAuthenticatedReadOnly: true,
  permissionDepartment: 'qc',
}

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
    path: '/reset-password',
    name: 'reset-password',
    component: () => import('@/views/PasswordResetCompleteView.vue'),
    meta: {
      title: '设置新密码',
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
    path: '/people',
    name: 'people-directory',
    component: () => import('@/views/PeopleDirectoryView.vue'),
    meta: {
      title: '成员目录',
      requiresAuth: true,
    },
  },
  {
    path: '/modules',
    redirect: '/modules/engineering',
  },
  {
    path: '/tools',
    name: 'shared-tool-center',
    component: () => import('@/views/ToolCenterView.vue'),
    meta: {
      title: '公共工具栏',
      requiresAuth: true,
    },
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
      title: '注塑排产中枢',
      fullPage: true,
      requiresAuth: true,
      permissions: ['injection_scheduling:read'],
      enforcePermissions: true,
      strictPermissions: true,
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
    path: '/change-password',
    name: 'change-password',
    component: () => import('@/views/ForcePasswordChangeView.vue'),
    meta: {
      title: '设置正式密码',
      fullPage: true,
      requiresAuth: true,
    },
  },
  {
    path: '/modules/production/three-d-printing',
    name: 'three-d-printing-management',
    component: () => import('@/views/ThreeDPrintingManagementView.vue'),
    meta: {
      title: '3D打印机管理',
      fullPage: true,
      requiresAuth: true,
      permissions: ['three_d_printing:read'],
      enforcePermissions: true,
      strictPermissions: true,
      permissionFactoryId: 'huakang-a',
      permissionDepartment: 'three-d-printing',
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
      permissions: ['molding_sample:raw_material_write'],
      enforcePermissions: true,
    },
  },
  {
    path: '/modules/sales-business/customer-price-conversion',
    name: 'customer-price-conversion',
    component: () => import('@/views/CustomerPriceConversionView.vue'),
    meta: {
      title: '客价转换台',
      fullPage: true,
      requiresAuth: true,
      permissions: ['customer_price:read', 'customer_price:import_internal_quote'],
      enforcePermissions: true,
    },
  },
  {
    path: '/modules/sales-business/internal-quote-desk',
    component: () => import('@/views/InternalQuoteDeskView.vue'),
    meta: {
      title: '内部报价台',
      fullPage: true,
      requiresAuth: true,
      permissions: ['internal_quote:read'],
      enforcePermissions: true,
    },
    children: [
      {
        path: '',
        name: 'internal-quote-desk-home',
        component: () => import('@/components/modules/sales/internal-quote/InternalQuoteHome.vue'),
        meta: { title: '内部报价台', fullPage: true, requiresAuth: true },
      },
      {
        path: ':quoteId/collaboration',
        name: 'internal-quote-collaboration',
        component: () => import('@/components/modules/sales/internal-quote/InternalQuoteCollaboration.vue'),
        meta: { title: '内部报价协作', fullPage: true, requiresAuth: true },
      },
      {
        path: ':quoteId/summary',
        name: 'internal-quote-summary',
        component: () => import('@/components/modules/sales/internal-quote/InternalQuoteSummary.vue'),
        meta: { title: '内部报价汇总与放行', fullPage: true, requiresAuth: true },
      },
      {
        path: ':quoteId/export',
        name: 'internal-quote-export-summary',
        component: () => import('@/components/modules/sales/internal-quote/InternalQuoteExportSummary.vue'),
        meta: { title: '内部报价导出汇总', fullPage: true, requiresAuth: true },
      },
    ],
  },
  {
    path: '/modules/sales-business/quote-center',
    redirect: '/modules/sales-business/customer-price-conversion',
  },
  {
    path: '/modules/sales-business/quote-center/customer-price-conversion',
    redirect: '/modules/sales-business/customer-price-conversion',
  },
  {
    path: '/modules/sales-business/order-approval',
    redirect: '/modules/sales-business',
  },
  {
    path: '/modules/sales-business/po-schedule-intake',
    name: 'customer-order-center',
    component: () => import('@/views/CustomerOrderCenterView.vue'),
    meta: {
      title: '客户订单中心',
      fullPage: true,
      requiresAuth: true,
      permissions: ['customer_order:read'],
      enforcePermissions: true,
    },
  },
  {
    path: '/modules/pmc-warehouse/carton-mark-check',
    name: 'carton-mark-template',
    component: () => import('@/views/CartonMarkTemplateView.vue'),
    meta: {
      title: '箱唛资料模板',
      fullPage: true,
      requiresAuth: true,
    },
  },
  {
    path: '/modules/pmc-warehouse/carton-procurement',
    name: 'carton-procurement',
    component: () => import('@/views/CartonProcurementView.vue'),
    meta: {
      title: '纸箱采购协同',
      fullPage: true,
      requiresAuth: true,
      permissions: ['carton_procurement:read'],
      enforcePermissions: true,
      strictPermissions: true,
    },
  },
  {
    path: '/modules/qc/carton-mark-check',
    name: 'qc-carton-mark-check',
    component: () => import('@/views/CartonMarkQcVerificationView.vue'),
    meta: {
      title: 'QC 箱唛核验',
      fullPage: true,
      requiresAuth: true,
      permissions: ['carton_mark:read'],
      enforcePermissions: true,
      strictPermissions: true,
      permissionDepartment: 'qc',
    },
  },
  {
    path: '/modules/qa/carton-mark-check',
    name: 'carton-mark-check',
    component: () => import('@/views/CartonMarkVerificationView.vue'),
    meta: {
      title: '箱唛核验',
      fullPage: true,
      requiresAuth: true,
      permissions: ['carton_mark:read'],
      enforcePermissions: true,
      strictPermissions: true,
      permissionDepartment: 'qa',
    },
  },
  {
    path: '/modules/qc/inspection-operations',
    name: 'qc-inspection-schedule',
    component: qcInspectionOperationsView,
    meta: {
      ...qcInspectionFullPageMeta,
      title: 'QC 验货排期',
    },
  },
  {
    path: '/modules/qc/inspection-operations/orders/new',
    name: 'qc-inspection-order-new',
    component: qcInspectionOperationsView,
    meta: {
      ...qcInspectionFullPageMeta,
      title: 'QC 临时订单录入',
    },
  },
  {
    path: '/modules/qc/inspection-operations/orders/:orderId',
    name: 'qc-inspection-order-detail',
    component: qcInspectionOperationsView,
    meta: {
      ...qcInspectionFullPageMeta,
      title: 'QC 验货主单详情',
    },
  },
  {
    path: '/modules/qc/inspection-operations/problems',
    name: 'qc-inspection-problems',
    component: qcInspectionOperationsView,
    meta: {
      ...qcInspectionFullPageMeta,
      title: 'QC 验货问题统计',
    },
  },
  {
    path: '/modules/qc/inspection-operations/reports',
    name: 'qc-inspection-reports',
    component: qcInspectionOperationsView,
    meta: {
      ...qcInspectionFullPageMeta,
      title: 'QC 报表中心',
    },
  },
  {
    path: '/modules/qc/inspection-operations/report-renaming',
    name: 'qc-inspection-report-renaming',
    component: qcInspectionOperationsView,
    meta: {
      ...qcInspectionFullPageMeta,
      title: 'QC 验货报告批量改名',
    },
  },
  {
    path: '/modules/accounting/indonesia-invoice-reconciliation',
    name: 'indonesia-invoice-reconciliation',
    component: () => import('@/views/IndonesiaInvoiceReconciliationView.vue'),
    meta: {
      title: '印尼票据核对',
      fullPage: true,
      requiresAuth: true,
    },
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

      const module = getDepartmentModule(department, moduleId)
      if (!module || module.detailPage === false) {
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
      permissions: ['molding_sample:read', 'molding_sample:cross_factory_read'],
      enforcePermissions: true,
      allowAuthenticatedReadOnly: true,
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
      title: '调整权限职位',
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
      title: '内置职位权限',
      fullPage: true,
      requiresAuth: true,
      permissions: ['system:permission_catalog_read'],
      enforcePermissions: true,
    },
  },
  {
    path: '/system/iam/permissions',
    redirect: '/system/iam/roles',
  },
  {
    path: '/system/iam/requests',
    redirect: '/system/iam/roles',
  },
  {
    path: '/system/iam/audit',
    redirect: '/system/iam/roles',
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
    beforeEnter: () => shouldRedirectForbiddenPageToHome()
      ? { name: 'dashboard', replace: true }
      : true,
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
let latestNavigationVersion = 0
const browserBackExitGuard = installBrowserBackExitGuard(router)

type AuthorizationRefreshResult = 'refreshed' | 'password-change' | 'forbidden' | 'login' | 'unchanged'

interface AuthorizationRefreshStore {
  isAuthenticated: boolean
  currentUser?: { id?: string; profile?: { primary_factory_id?: string } | null; force_password_change?: boolean } | null
  refreshSession: () => Promise<boolean>
  canAny: (permissions: string[], factoryId?: string, department?: string) => boolean
}

interface AuthorizationRefreshRouter {
  currentRoute: {
    value: {
      name?: unknown
      fullPath?: string
      query?: Record<string, unknown>
      meta: Record<string, unknown>
    }
  }
  replace: (location: { name: string; query?: Record<string, string> }) => unknown
}

function factoryQueryForRoute(route: { name?: unknown; query?: Record<string, unknown> }) {
  const query = route.query ?? {}
  return route.name === 'login' || route.name === 'change-password'
    ? router.resolve(resolvePostLoginRedirect(router, query.redirect)).query
    : query
}

function postLoginRedirectLocation(fullPath: string) {
  // A path-only route object does not carry the query/hash parsed from a URL.
  const { path, query, hash } = router.resolve(fullPath)
  return { path, query, hash, replace: true }
}

function syncAuthenticatedFactoryContextForRoute(
  authStore: Pick<AuthorizationRefreshStore, 'currentUser'>,
  query: Record<string, unknown>,
) {
  const user = authStore.currentUser
  if (!user?.id) return
  const appStore = useAppStore()
  appStore.setRequestedFactoryContext(query.factory)
  appStore.syncAuthenticatedFactoryContext({
    userId: user.id,
    primaryFactoryId: user.profile?.primary_factory_id,
  })
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

  syncAuthenticatedFactoryContextForRoute(authStore, factoryQueryForRoute(currentRoute))

  if (isPublicRoute) return 'refreshed'

  if (authStore.currentUser?.force_password_change && currentRoute.name !== 'change-password') {
    const redirect = resolvePostLoginRedirect(router, currentRoute.fullPath)
    await activeRouter.replace({
      name: 'change-password',
      query: redirect === '/' ? {} : { redirect },
    })
    return 'password-change'
  }

  const permissions = Array.isArray(currentRoute.meta.permissions)
    ? currentRoute.meta.permissions.filter((permission): permission is string => typeof permission === 'string')
    : []
  if (
    currentRoute.name !== 'forbidden'
    && shouldEnforcePagePermissions(currentRoute.meta)
    && permissions.length
    && !authStore.canAny(
      permissions,
      typeof currentRoute.meta.permissionFactoryId === 'string'
        ? currentRoute.meta.permissionFactoryId
        : undefined,
      typeof currentRoute.meta.permissionDepartment === 'string'
        ? currentRoute.meta.permissionDepartment
        : undefined,
    )
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
  const navigationVersion = ++latestNavigationVersion
  if (routeLoadingTimer) {
    window.clearTimeout(routeLoadingTimer)
  }

  routeLoadingStartedAt = window.performance.now()
  const appStore = useAppStore()
  appStore.startRouteLoading()

  const factoryQuery = factoryQueryForRoute(to)
  appStore.setRequestedFactoryContext(factoryQuery.factory)

  const authStore = useAuthStore()
  if (to.name === 'login') {
    if (to.query.logged_out === '1') {
      return true
    }

    if (authStore.isAuthenticated || await authStore.ensureSession()) {
      if (navigationVersion !== latestNavigationVersion) return false
      syncAuthenticatedFactoryContextForRoute(authStore, factoryQuery)
      if (authStore.currentUser?.force_password_change) {
        const redirect = resolvePostLoginRedirect(router, to.query.redirect)
        return {
          name: 'change-password',
          query: redirect === '/' ? {} : { redirect },
          replace: true,
        }
      }
      return postLoginRedirectLocation(resolvePostLoginRedirect(router, to.query.redirect))
    }

    return true
  }

  const requiresAuth = to.meta.requiresAuth !== false
  if (requiresAuth) {
    const hasSession = await authStore.ensureSession()
    // An older /auth/me may finish after a newer login/navigation has already won.
    if (navigationVersion !== latestNavigationVersion) return false
    if (!hasSession) {
      return {
        name: 'login',
        query: { redirect: to.fullPath },
        replace: true,
      }
    }
  }

  syncAuthenticatedFactoryContextForRoute(authStore, factoryQuery)

  if (authStore.currentUser?.force_password_change) {
    if (to.name === 'change-password') return true
    const redirect = resolvePostLoginRedirect(router, to.fullPath)
    return {
      name: 'change-password',
      query: redirect === '/' ? {} : { redirect },
      replace: true,
    }
  }

  if (to.name === 'change-password') {
    return postLoginRedirectLocation(resolvePostLoginRedirect(router, to.query.redirect))
  }

  const permissions = Array.isArray(to.meta.permissions) ? to.meta.permissions as string[] : []
  if (
    shouldEnforcePagePermissions(to.meta)
    && permissions.length
    && !authStore.canAny(
      permissions,
      typeof to.meta.permissionFactoryId === 'string'
        ? to.meta.permissionFactoryId
        : undefined,
      typeof to.meta.permissionDepartment === 'string'
        ? to.meta.permissionDepartment
        : undefined,
    )
  ) {
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
