import type { RouteRecordRaw, RouteLocationNormalized } from 'vue-router'
import { CUTTING_BASE, CUTTING_WORKSPACES, isCuttingFactory } from './navigation'

export function guardCuttingFactory(to: RouteLocationNormalized) {
  return isCuttingFactory(to.query.factory) ? true : {
    path: '/modules/production',
    query: { factory: typeof to.query.factory === 'string' ? to.query.factory : 'group' },
    replace: true,
  }
}

// Authenticated shell; master-data reads and mutations are authorized by the API.
const meta = { fullPage: true, requiresAuth: true, title: '华康 C · 裁床部' }
export const cuttingOperationsRoutes: RouteRecordRaw[] = [{
  path: CUTTING_BASE,
  component: () => import('./CuttingWorkspaceShell.vue'),
  meta,
  beforeEnter: guardCuttingFactory,
  children: [
    { path: '', redirect: to => ({ path: `${CUTTING_BASE}/dashboard`, query: to.query }) },
    ...CUTTING_WORKSPACES.map((workspace):RouteRecordRaw => workspace.path === 'costs' ? {
      path:workspace.path,
      redirect:to=>({path:`${CUTTING_BASE}/closing`,query:{...to.query,view:'costs'}}),
      meta:{...meta,title:'裁床 · 月结物料费用'},
    } : ({
      path: workspace.path,
      component: workspace.path === 'dashboard'
        ? () => import('./CuttingDashboardPage.vue')
        : workspace.path === 'activity'
        ? () => import('./CuttingActivityPage.vue')
        : workspace.path === 'master'
        ? () => import('./CuttingMasterPage.vue')
        : workspace.path === 'reporting'
        ? () => import('./CuttingReportingPage.vue')
        : workspace.path === 'closing'
        ? () => import('./CuttingClosingPage.vue')
        : workspace.path === 'planning' || workspace.path === 'materials'
        ? () => import('./CuttingOrdersPage.vue')
        : () => import('./CuttingWorkspacePage.vue'),
      props: { workspace },
      meta: { ...meta, title: `裁床 · ${workspace.title}` },
    })),
  ],
}]
