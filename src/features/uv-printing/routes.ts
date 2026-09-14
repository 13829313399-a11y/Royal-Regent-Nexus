import type { Component } from 'vue'
import type { RouteRecordRaw } from 'vue-router'
import { useAppStore } from '@/stores/app'
import { useAuthStore } from '@/stores/auth'
import type { UvFactoryId } from './contracts'
import { UV_PERMISSIONS } from './contracts'
import { isUvModuleEnabled } from './transport/provider'

/**
 * UV 打印管理子路由。
 *
 * 正式路由严格华康A/production 作用域：
 * `permissionFactoryId` 只是权限作用域，不能代替「当前有效厂区」一致性检查，
 * 后者由工作区 composable 在模块内执行（换厂立即取消请求、清空缓存、退出工作区）。
 */

export const UV_FACTORY: UvFactoryId = 'huakang-a'

export const UV_WORKSPACE_BASE = '/modules/production/uv-printing'
export const UV_PREVIEW_BASE = '/__preview/uv-printing'

const workspaceMeta = {
  fullPage: true,
  requiresAuth: true,
  permissions: [UV_PERMISSIONS.read],
  enforcePermissions: true,
  strictPermissions: true,
  permissionFactoryId: UV_FACTORY,
  permissionDepartment: 'production',
} as const

interface UvChildSpec {
  path: string
  name: string
  title: string
  component: () => Promise<Component>
}

const childSpecs: UvChildSpec[] = [
  { path: 'overview', name: 'uv-printing-overview', title: 'UV打印·生产驾驶舱', component: () => import('./pages/OverviewPage.vue') },
  { path: 'production', name: 'uv-printing-production', title: 'UV打印·生产记录', component: () => import('./pages/ProductionPage.vue') },
  { path: 'machines/:id?', name: 'uv-printing-machines', title: 'UV打印·机台', component: () => import('./pages/MachinesPage.vue') },
  { path: 'ink', name: 'uv-printing-ink', title: 'UV打印·墨水', component: () => import('./pages/InkPage.vue') },
  { path: 'workforce', name: 'uv-printing-workforce', title: 'UV打印·人员班次', component: () => import('./pages/WorkforcePage.vue') },
  { path: 'catalog', name: 'uv-printing-catalog', title: 'UV打印·产品定价', component: () => import('./pages/CatalogPage.vue') },
  { path: 'reports', name: 'uv-printing-reports', title: 'UV打印·经营报表', component: () => import('./pages/ReportsPage.vue') },
]

export const uvPrintingChildRoutes = [
  {
    path: '',
    redirect: (to: { query: Record<string, unknown> }) => ({ path: `${UV_WORKSPACE_BASE}/overview`, query: to.query }),
  },
  ...childSpecs.map((spec) => ({
    path: spec.path,
    name: spec.name,
    component: spec.component,
    meta: { ...workspaceMeta, title: spec.title },
  })),
] as RouteRecordRaw[]

export const uvPrintingRoutes: RouteRecordRaw[] = [
  {
    path: UV_WORKSPACE_BASE,
    component: () => import('./UvWorkspaceShell.vue'),
    meta: { ...workspaceMeta, title: '华康A · UV打印管理' },
    /**
     * 有效厂区一致性检查。
     *
     * `permissionFactoryId` 只是权限作用域，不能代替「当前有效厂区」检查；
     * 直接输入 URL 或 query 里写别的厂区时，这里在进入工作区前就停下，
     * 不查询、不显示华康A数据，也不静默切厂。工作区内再校验一次以覆盖
     * 已经进入页面后切换厂区的情况。
     */
    beforeEnter: (to) => {
      if (!isUvModuleEnabled()) {
        return { path: '/modules/production', query: { factory: UV_FACTORY }, replace: true }
      }
      const requested = Array.isArray(to.query.factory) ? to.query.factory[0] : to.query.factory
      if (typeof requested === 'string' && requested !== UV_FACTORY) {
        return { path: '/modules/production', query: { factory: UV_FACTORY }, replace: true }
      }
      const appStore = useAppStore()
      const authStore = useAuthStore()
      // 刷新会话后仍是别的厂区：不发请求，回到生产部并保留合法厂区上下文。
      if (authStore.isAuthenticated && appStore.activeFactoryId !== UV_FACTORY) {
        return { path: '/modules/production', query: { factory: UV_FACTORY }, replace: true }
      }
      return true
    },
    children: uvPrintingChildRoutes,
  },
]

/**
 * DEV 专属样例预览。
 *
 * 只在 `import.meta.env.DEV` 且显式开启 `VITE_UV_PREVIEW=true` 时注册；
 * 沿用宿主登录状态要求，但不要求尚未注册的 UV 业务权限——
 * 因为它只读写内存样例、不能访问真实 UV 接口。
 * 这个路由不是给正式路由加授权后门，生产构建不可达。
 */
export function uvPreviewRoutes(previewEnabled: boolean): RouteRecordRaw[] {
  if (!previewEnabled) return []
  return [
    {
      path: UV_PREVIEW_BASE,
      component: () => import('./UvWorkspaceShell.vue'),
      meta: {
        title: 'UV打印 · 样例预览',
        fullPage: true,
        requiresAuth: true,
        /** 明确不继承正式权限：预览只读内存样例。 */
        enforcePermissions: false,
        allowAuthenticatedReadOnly: true,
        previewOnly: true,
      },
      children: [
        {
          path: '',
          name: 'uv-printing-preview',
          redirect: (to: { query: Record<string, unknown> }) => ({ path: `${UV_PREVIEW_BASE}/overview`, query: to.query }),
        },
        // 其余子路由不命名：避免与正式路由重名，导航按路径进行。
        ...childSpecs.map((spec) => ({
          path: spec.path,
          component: spec.component,
          meta: {
            title: `样例预览 · ${spec.title}`,
            fullPage: true,
            requiresAuth: true,
            enforcePermissions: false,
            allowAuthenticatedReadOnly: true,
            previewOnly: true,
          },
        })),
      ] as RouteRecordRaw[],
    },
  ]
}
