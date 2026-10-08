import type { RouteLocationGeneric, RouteLocationNormalized, RouteRecordRaw } from 'vue-router'
import { WAREHOUSES, WAREHOUSE_HOME, isWarehouseFactory, warehousePath } from './navigation'

export function guardWarehouseFactory(to: RouteLocationNormalized) {
  return isWarehouseFactory(to.query.factory) ? true : {
    path: WAREHOUSE_HOME,
    query: { factory: typeof to.query.factory === 'string' ? to.query.factory : 'group' },
    replace: true,
  }
}

// Fabric sources and receipts use backend authorization; other warehouse actions remain informational.
export const warehouseOperationsRoutes: RouteRecordRaw[] = WAREHOUSES.map(warehouse => ({
  path: `${WAREHOUSE_HOME}/${warehouse.id}`,
  component: () => import('./WarehouseShell.vue'),
  props: { warehouse },
  beforeEnter: guardWarehouseFactory,
  meta: { requiresAuth: true, fullPage: true, title: warehouse.title },
  children: [
    { path: '', redirect: to => ({ path: warehousePath(warehouse), query: to.query }) },
    ...(warehouse.id === 'fabric-warehouse' ? [{
      path: 'orders',
      redirect: (to: RouteLocationGeneric) => ({
        path: warehousePath(warehouse, 'receipts'),
        query: {
          ...to.query,
          view: to.query.view === 'purchases' || to.query.view === 'purchase-history' ? 'import-review' : 'pending',
          source: to.query.view === 'purchases' ? 'all' : to.query.view === 'purchase-history' ? 'returned' : undefined,
        },
      }),
    }] : []),
    ...warehouse.sections.map(section => ({
      path: section.path,
      component: () => import('./WarehousePage.vue'),
      props: { warehouse, section },
      meta: { requiresAuth: true, fullPage: true, title: `${warehouse.title} · ${section.title}` },
    })),
  ],
}))
