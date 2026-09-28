import type { RouteRecordRaw, RouteLocationNormalized } from 'vue-router'
import { CUTTING_BASE, CUTTING_WORKSPACES, isCuttingFactory } from './navigation'

export function guardCuttingFactory(to: RouteLocationNormalized) {
  return isCuttingFactory(to.query.factory) ? true : {
    path: '/modules/production',
    query: { factory: typeof to.query.factory === 'string' ? to.query.factory : 'group' },
    replace: true,
  }
}

// Authenticated informational shell only: no business reads or mutations yet.
const meta = { fullPage: true, requiresAuth: true, title: '华康 C · 裁床部' }
export const cuttingOperationsRoutes: RouteRecordRaw[] = [{
  path: CUTTING_BASE,
  component: () => import('./CuttingWorkspaceShell.vue'),
  meta,
  beforeEnter: guardCuttingFactory,
  children: [
    { path: '', redirect: to => ({ path: `${CUTTING_BASE}/planning`, query: to.query }) },
    ...CUTTING_WORKSPACES.map(workspace => ({
      path: workspace.path,
      component: () => import('./CuttingWorkspacePage.vue'),
      props: { workspace },
      meta: { ...meta, title: `裁床 · ${workspace.title}` },
    })),
  ],
}]
