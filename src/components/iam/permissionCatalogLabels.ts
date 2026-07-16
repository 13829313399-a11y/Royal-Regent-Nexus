const ACTION_LABELS: Record<string, string> = {
  read: '查看',
  create: '新建',
  update: '修改',
  delete: '删除',
  approve: '审批',
  export: '导出',
  manage: '管理',
  edit_draft: '编辑草稿',
  delete_draft: '删除草稿',
  supervisor_review: '主管审核',
  manager_review: '经理终审',
  warehouse_requisition: '仓库领料',
  inventory_issue: '库存发料',
  production_read: '查看生产任务',
  production_start: '开始生产',
  production_fillback: '生产回填',
  production_complete: '完成生产',
  price_update: '维护价格',
  audit_read: '查看审计记录',
  notification_read: '查看通知',
  template_upload: '上传模板',
  photo_upload: '上传实拍',
  review: '复核',
  import: '导入',
  import_internal_quote: '导入内部报价',
  export_customer_quote: '导出客户报价',
  compare: '比对',
  user_manage: '管理用户',
  role_manage: '管理角色',
  access_manage: '管理用户授权',
  access_request: '提交权限申请',
  access_approve: '审批权限申请',
  permission_catalog_read: '查看内置职位权限',
  cross_factory_read: '跨厂查看',
  cross_factory_cost_read: '跨厂查看成本',
}

const PERMISSION_LABELS: Record<string, string> = {
  'carton_mark:photo_upload': '上传箱唛实拍',
  'carton_mark:read': '查看箱唛',
  'carton_mark:review': '复核箱唛',
  'carton_mark:template_upload': '维护箱唛模板',
  'customer_price:compare': '比较报价差异',
  'customer_price:export_customer_quote': '导出客户报价',
  'customer_price:import_internal_quote': '导入内部报价',
  'customer_price:read': '查看报价中心',
  'injection_schedule:import': '导入啤机排产',
  'injection_schedule:read': '查看啤机排产',
  'molding_sample:audit_read': '查看啤办敏感操作审计',
  'molding_sample:create': '新建啤办申请',
  'molding_sample:cross_factory_cost_read': '跨厂查看啤办成本',
  'molding_sample:cross_factory_read': '跨厂查看啤办单据',
  'molding_sample:delete_draft': '删除啤办草稿',
  'molding_sample:edit_draft': '编辑啤办草稿',
  'molding_sample:export': '导出啤办单',
  'molding_sample:inventory_issue': '啤办库存发料',
  'molding_sample:manager_review': '啤办经理终审',
  'molding_sample:notification_read': '接收啤办通知',
  'molding_sample:price_update': '维护啤办价格',
  'molding_sample:production_complete': '完成啤办生产',
  'molding_sample:production_fillback': '回填啤办生产数据',
  'molding_sample:production_read': '查看啤办生产任务',
  'molding_sample:production_start': '开始啤办生产',
  'molding_sample:read': '查看啤办单据',
  'molding_sample:supervisor_review': '啤办主管审核',
  'molding_sample:warehouse_requisition': '发起啤办领料',
  'system:access_approve': '审批权限申请',
  'system:access_manage': '管理用户授权',
  'system:access_request': '提交权限申请',
  'system:audit_read': '查看权限操作记录',
  'system:permission_catalog_read': '查看内置职位权限',
  'system:role_manage': '管理角色模板',
  'system:user_manage': '管理用户账号',
}

const SCOPE_LABELS: Record<string, string> = {
  global: '全集团',
  factory: '指定厂区',
  department: '指定部门',
  factory_department: '指定厂区与部门',
  business_object: '指定业务对象',
}

const LEGACY_IAM_PAGE_PERMISSION_CODES = new Set([
  'system:access_approve',
  'system:access_request',
  'system:audit_read',
  'system:permission_catalog_read',
  'system:role_manage',
])

export function permissionActionLabel(action: string) {
  return ACTION_LABELS[action] ?? '自定义操作'
}

export interface PermissionLabelSource {
  code: string
  name?: string
  module_name?: string
  action?: string
}

export function permissionDisplayLabel(permission: PermissionLabelSource) {
  const configuredName = permission.name?.trim()
  const isTechnicalName = !configuredName
    || configuredName === permission.code
    || /^[a-z0-9_]+:[a-z0-9_]+$/i.test(configuredName)

  if (!isTechnicalName) return configuredName
  if (PERMISSION_LABELS[permission.code]) return PERMISSION_LABELS[permission.code]

  const action = permission.action || permission.code.split(':').at(-1) || ''
  const actionLabel = permissionActionLabel(action)
  return permission.module_name ? `${permission.module_name} · ${actionLabel}` : actionLabel
}

export function permissionScopeLabel(scopeType: string) {
  return SCOPE_LABELS[scopeType] ?? '自定义范围'
}

export function isBuiltInPositionPermissionVisible(permissionCode: string) {
  return !LEGACY_IAM_PAGE_PERMISSION_CODES.has(permissionCode)
}
