import type { ModuleDepartmentId } from '@/data/enterpriseMock'

/**
 * 门户展示配置（Jade Atlas · jade-v3）。
 *
 * 这里只放颜色、纹样标识和短文案等纯展示信息，不包含模块清单、权限、业务数据、
 * API 或厂区规则。部门业务内容仍然来自 `departmentModuleRegistry`。
 */

export type PortalMotifKind = 'blueprint' | 'storage' | 'rail' | 'ring' | 'grid' | 'document' | 'ledger' | 'flow'

export interface DepartmentPresentation {
  /** 非状态类图标的强调色，不用于表达告警等业务状态。 */
  accent: string
  /** 强调色对应的浅色承载面。 */
  accentSoft: string
  /** 页头右侧低对比刻线纹样。 */
  motif: PortalMotifKind
  /** 权限矩阵目录示意说明。 */
  permissionNote: string
  /** 待办队列空态文案。 */
  todoEmptyText: string
}

const sharedPermissionNote = '目录权限示意，实际操作以账号授权为准'
const sharedTodoEmptyText = '当前暂无可展示的本厂待办'

export const departmentPresentation: Record<ModuleDepartmentId, DepartmentPresentation> = {
  engineering: {
    accent: '#2D6470',
    accentSoft: '#EBF3F5',
    motif: 'blueprint',
    permissionNote: sharedPermissionNote,
    todoEmptyText: sharedTodoEmptyText,
  },
  'pmc-warehouse': {
    accent: '#4D7164',
    accentSoft: '#EEF4ED',
    motif: 'storage',
    permissionNote: sharedPermissionNote,
    todoEmptyText: sharedTodoEmptyText,
  },
  production: {
    accent: '#197765',
    accentSoft: '#E8F3EF',
    motif: 'rail',
    permissionNote: sharedPermissionNote,
    todoEmptyText: sharedTodoEmptyText,
  },
  qa: {
    accent: '#526F61',
    accentSoft: '#EDF3EE',
    motif: 'ring',
    permissionNote: sharedPermissionNote,
    todoEmptyText: sharedTodoEmptyText,
  },
  qc: {
    accent: '#326B73',
    accentSoft: '#EBF4F4',
    motif: 'grid',
    permissionNote: sharedPermissionNote,
    todoEmptyText: sharedTodoEmptyText,
  },
  'sales-business': {
    accent: '#32665E',
    accentSoft: '#EDF3F0',
    motif: 'document',
    permissionNote: sharedPermissionNote,
    todoEmptyText: sharedTodoEmptyText,
  },
  accounting: {
    accent: '#52695B',
    accentSoft: '#F1F3EC',
    motif: 'ledger',
    permissionNote: sharedPermissionNote,
    todoEmptyText: sharedTodoEmptyText,
  },
}

export function getDepartmentPresentation(departmentId: ModuleDepartmentId): DepartmentPresentation {
  return departmentPresentation[departmentId]
}
