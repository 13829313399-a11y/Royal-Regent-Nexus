import { factoryContexts } from '@/data/enterpriseMock'
import { registrationDepartments } from '@/data/registrationDepartments'

const additionalDepartmentLabels: Record<string, string> = {
  assembly: '装配部',
  electronic: '电子部',
  hair: '植发部',
  management: '总务',
  molding: '啤机部',
  painting: '喷油部',
  sewing: '车缝部',
  slush: '搪胶部',
  system: '系统管理',
  warehouse: '仓管部',
}

const factoryLabels = new Map<string, string>(
  factoryContexts.map((factory) => [factory.id, factory.shortName]),
)

const departmentLabels = new Map<string, string>([
  ...registrationDepartments.map((department) => [department.id, department.name] as const),
  ...Object.entries(additionalDepartmentLabels),
])

export const directoryFactoryOptions = factoryContexts
  .filter((factory) => factory.id !== 'group')
  .map((factory) => ({ value: factory.id, label: factory.shortName }))

export const directoryDepartmentOptions = Array.from(departmentLabels, ([value, label]) => ({
  value,
  label,
}))

function containsLatinCode(value: string) {
  return /[a-z]/i.test(value)
}

export function directoryFactoryLabel(factoryId?: string) {
  const normalized = factoryId?.trim() ?? ''
  if (!normalized) return '未确认厂区'
  return factoryLabels.get(normalized)
    ?? (containsLatinCode(normalized) ? '其他厂区' : normalized)
}

export function directoryDepartmentLabel(departmentId?: string) {
  const normalized = departmentId?.trim() ?? ''
  if (!normalized) return '未确认部门'
  return departmentLabels.get(normalized)
    ?? (containsLatinCode(normalized) ? '其他部门' : normalized)
}
