/**
 * 样例角色定义（轻量模块）。
 *
 * 这里刻意**不导入** `memoryStore.ts` 或 `fixtures.ts`：工作区壳需要在生产构建里
 * 显示「样例预览」标签与角色选择器的文案，如果它静态依赖样例数据模块，整套合成
 * 记录就会被拖进生产包。因此类型与文案放在这个只有几十行的模块里，
 * 真正的内存事实源仍由 `preview/memoryStore.ts` 提供，并且只在
 * `isUvPreviewEnabled()` 为真时动态加载。
 */

export type UvSampleRole =
  | 'operator'
  | 'supervisor'
  | 'warehouse'
  | 'cost'
  | 'manager'
  | 'readonly'

export const SAMPLE_ROLE_IDS: UvSampleRole[] = [
  'operator',
  'supervisor',
  'warehouse',
  'cost',
  'manager',
  'readonly',
]

export const SAMPLE_ROLE_LABELS: Record<UvSampleRole, string> = {
  operator: '现场操作员',
  supervisor: '生产主管',
  warehouse: '仓管',
  cost: '成本人员',
  manager: '部门主管（全权限）',
  readonly: '只读查看',
}

export const SAMPLE_ROLE_DESCRIPTIONS: Record<UvSampleRole, string> = {
  operator: '可报工、可补质量，看不到价格与工资',
  supervisor: '报工、核对、排班、质量与工资预览',
  warehouse: '墨水收发与盘点，不含成本定价',
  cost: '价格、费用、定价测算与经营报表',
  manager: '全部 UV 权限，可确认工资与导出',
  readonly: '只能读取，所有写操作显式不可用',
}

const READ = 'uv_printing:read'

/** 样例角色档案（供预览页展示角色说明，不用于真实授权）。 */
export interface UvSampleRoleProfile {
  id: UvSampleRole
  label: string
  description: string
  permissions: string[]
}

export function sampleRoleProfiles(): UvSampleRoleProfile[] {
  return SAMPLE_ROLE_IDS.map((id) => ({
    id,
    label: SAMPLE_ROLE_LABELS[id],
    description: SAMPLE_ROLE_DESCRIPTIONS[id],
    permissions: SAMPLE_ROLE_PERMISSIONS[id],
  }))
}

export const SAMPLE_ROLE_PERMISSIONS: Record<UvSampleRole, string[]> = {
  operator: [READ, 'uv_printing:report', 'uv_printing:quality'],
  supervisor: [READ, 'uv_printing:report', 'uv_printing:quality', 'uv_printing:shift_write', 'uv_printing:payroll_read'],
  warehouse: [READ, 'uv_printing:ink_write'],
  cost: [READ, 'uv_printing:cost_read', 'uv_printing:cost_write', 'uv_printing:master_write'],
  manager: [
    READ,
    'uv_printing:report',
    'uv_printing:quality',
    'uv_printing:master_write',
    'uv_printing:shift_write',
    'uv_printing:ink_write',
    'uv_printing:cost_read',
    'uv_printing:cost_write',
    'uv_printing:payroll_read',
    'uv_printing:payroll_write',
    'uv_printing:export',
  ],
  readonly: [READ],
}
