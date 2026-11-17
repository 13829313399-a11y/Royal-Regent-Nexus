import type { ModuleKey } from '../auth/permissions'

const groups = [
  { key: 'basic-data', name: '基础资料', children: [
    { path: '/customers', name: '客户管理', module: 'customers' },
    { path: '/products', name: '货号库', module: 'products' },
    { path: '/tool-materials', name: '工具及非生产物料', module: 'products' },
    { path: '/supplier-summary', name: '供应商汇总', module: 'products' },
    { path: '/quotes', name: '供应商报价', module: 'quotes' },
    { path: '/dictionaries', name: 'HS/翻译字典', module: 'products' },
  ] },
  { key: 'orders-shipping', name: '订单与走货', children: [
    { path: '/schedules', name: '排期', module: 'schedules' },
    { path: '/purchase', name: '采购订单', module: 'purchase' },
    { path: '/molding-pos', name: '生产单', module: 'molding' },
    { path: '/material-alerts', name: '物料追踪', module: 'purchase' },
    { path: '/outbound', name: '出库', module: 'outbound' },
    { path: '/shipments', name: '走货明细', module: 'shipments' },
  ] },
] satisfies { key: string; name: string; children: { path: string; name: string; module: ModuleKey }[] }[]

// Grouping changes navigation only; each leaf retains its existing module grant.
export function workspaceMenu(canAccess: (module: ModuleKey) => boolean) {
  return groups.map(group => ({
    key: group.key,
    name: group.name,
    children: group.children.filter(item => canAccess(item.module)).map(({ path, name }) => ({ key: path, path, name })),
  })).filter(group => group.children.length > 0)
}
