import { permissionDisplayLabel } from '@/components/iam/permissionCatalogLabels'

export const permissionName = (code: string, name = code) => permissionDisplayLabel({ code, name })

export const departmentName = (code: string) => ({ engineering: '工程部', business: '业务部', production: '生产部',
  printing_3d: '3D打印部', warehouse: 'PMC仓库', qa: 'QA部', qc: 'QC部', carton: '纸箱部', general: '总务', system: '系统', '*': '全部部门',
} as Record<string, string>)[code] || code || '未登记'
