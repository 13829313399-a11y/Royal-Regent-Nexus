import { createRouter, createWebHistory, type RouteRecordRaw } from 'vue-router'
import DashboardView from '@/views/DashboardView.vue'
import { getDepartmentModule, isModuleDepartmentId } from '@/data/enterpriseMock'
import { installBrowserBackExitGuard } from '@/lib/browserBackExitGuard'
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
    },
  },
  {
    path: '/modules/sales-business/quote-center/customer-price-conversion',
    name: 'customer-price-conversion',
    component: () => import('@/views/CustomerPriceConversionView.vue'),
    meta: {
      title: '客价转换台',
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
      requiresAuth: true,
      permissions: ['system:user_manage'],
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
const browserBackExitGuard = installBrowserBackExitGuard(router)

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
      const redirect = typeof to.query.redirect === 'string' ? to.query.redirect : '/'
      return { path: redirect, replace: true }
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
  if (permissions.length && !authStore.hasAnyPermission(permissions)) {
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
