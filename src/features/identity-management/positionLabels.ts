import { permissionDisplayLabel } from '@/components/iam/permissionCatalogLabels'
import { departments } from '@/data/enterpriseMock'
import { formatBusinessDateTime } from '@/lib/dateTime'

export const permissionName = (code: string, name = code) => permissionDisplayLabel({ code, name })

export function lastLoginLabel(value: string | null | undefined, includeSeconds = false) {
  if (value == null) return '暂无记录'
  if (!value.trim()) return '从未登录'
  return formatBusinessDateTime(value, { includeSeconds, fallback: '暂无记录' })
}

export const departmentName = (code: string) => ({ engineering: '工程部', business: '业务部', production: '生产部',
  printing_3d: '3D打印部', warehouse: 'PMC仓库', qa: 'QA部', qc: 'QC部', carton: '纸箱部', general: '总务', management: '总务', 'three-d-printing': '3D打印部', system: '系统', '*': '全部部门',
} as Record<string, string>)[code] || departments.find(d => d.id === code)?.name || code || '未登记'

export function requestedPackageLabel(id: string, packages?: ReadonlyArray<{ role_id: string; name: string; department: string }>) {
  const role = packages?.find(item => item.role_id === id)
  return role ? `${departmentName(role.department)} · ${role.name}` : id
}
