export type RegistrationDepartmentId =
  | 'management'
  | 'engineering'
  | 'sales-business'
  | 'production'
  | 'pmc-warehouse'
  | 'qa'
  | 'qc'
  | 'carton'

export interface RegistrationDepartment {
  id: RegistrationDepartmentId
  name: string
  shortName: string
}

export const registrationDepartments: readonly RegistrationDepartment[] = [
  { id: 'management', name: '管理层', shortName: '管理' },
  { id: 'engineering', name: '工程部', shortName: '工程' },
  { id: 'sales-business', name: '业务部', shortName: '业务' },
  { id: 'production', name: '生产部', shortName: '生产' },
  { id: 'pmc-warehouse', name: '仓库', shortName: '仓库' },
  { id: 'qa', name: 'QA部', shortName: 'QA' },
  { id: 'qc', name: 'QC部', shortName: 'QC' },
  { id: 'carton', name: '纸箱部', shortName: '纸箱' },
]

export const registrationDepartmentMap = Object.fromEntries(
  registrationDepartments.map((department) => [department.id, department]),
) as Record<RegistrationDepartmentId, RegistrationDepartment>

export function registrationDepartmentLabel(departmentId: string) {
  return registrationDepartmentMap[departmentId as RegistrationDepartmentId]?.name ?? departmentId
}
