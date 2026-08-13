import type { ModuleDepartmentId } from './enterpriseMock.js'

export const positionSuggestionsByDepartment: Partial<Record<ModuleDepartmentId | 'three-d-printing', readonly string[]>> = {
  engineering: [
    '工程部技术员',
    '助理工程师',
    '工程师',
    '高级工程师',
    '项目工程师',
    '模具工程师',
    '工艺工程师',
    '工程主管',
    '工程经理',
  ],
  'pmc-warehouse': [
    'PMC 计划员',
    '生产计划员',
    '物料计划员',
    '物料员',
    '仓管员',
    '仓库文员',
    '仓库主管',
    'PMC 主管',
  ],
  production: [
    '啤机操作员',
    '啤机技术员',
    '啤机文员',
    '调机技术员',
    '生产组长',
    '生产主管',
    '设备技术员',
    '生产经理',
  ],
  'three-d-printing': [
    '3D打印操作员',
    '3D打印技术员',
    '3D打印产品专员',
    '3D打印物料员',
    '3D打印计划员',
    '3D打印组长',
    '3D打印主管',
    '3D打印经理',
  ],
  qa: [
    'QA 检验员',
    'IQC 检验员',
    'IPQC 检验员',
    'OQC 检验员',
    'QA 技术员',
    '品质工程师',
    'QA 主管',
    '品质经理',
  ],
  qc: [
    'QC 检验员',
    'QC 主管',
    'QC 经理',
  ],
  'sales-business': [
    '车间业务跟客',
    '业务跟单员',
    '业务员',
    '销售专员',
    '客户经理',
    '车间业务主管',
    '业务主管',
    '销售经理',
  ],
  accounting: [
    '会计文员',
    '应收会计',
    '应付会计',
    '成本会计',
    '总账会计',
    '出纳员',
    '会计主管',
    '财务经理',
  ],
}

export function getPositionSuggestions(department: string): readonly string[] {
  return positionSuggestionsByDepartment[department as ModuleDepartmentId] ?? []
}
