import { createRouter, createWebHistory, type RouteRecordRaw } from 'vue-router'
import DashboardView from '@/views/DashboardView.vue'
import { useAppStore } from '@/stores/app'

const routes: RouteRecordRaw[] = [
  {
    path: '/',
    name: 'dashboard',
    component: DashboardView,
    meta: {
      title: '集团运营总览',
    },
  },
  {
    path: '/modules',
    name: 'modules',
    component: () => import('@/views/ModuleCenterView.vue'),
    meta: {
      title: '部门模块中心',
    },
  },
  {
    path: '/modules/molding-sample',
    name: 'molding-sample',
    component: () => import('@/views/MoldingSampleView.vue'),
    meta: {
      title: '啤办进度追踪',
      fullPage: true,
    },
  },
  {
    path: '/workbench',
    name: 'workbench',
    component: () => import('@/views/ApprovalWorkbenchView.vue'),
    meta: {
      title: '业务审批工作台',
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

router.beforeEach(() => {
  if (routeLoadingTimer) {
    window.clearTimeout(routeLoadingTimer)
  }

  routeLoadingStartedAt = window.performance.now()
  useAppStore().startRouteLoading()
})

router.afterEach((to) => {
  const title = typeof to.meta.title === 'string' ? to.meta.title : 'Workspace'

  document.title = `${title} | Royal Regent Nexus`
  finishRouteLoading()
})

router.onError(() => {
  finishRouteLoading()
})
