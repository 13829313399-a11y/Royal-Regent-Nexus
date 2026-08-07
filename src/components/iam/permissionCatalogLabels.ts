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
  dispatch: '分派生产任务',
  raw_material_write: '维护原料资料',
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
  image_upload: '上传图片',
  operate: '业务维护',
  printer_control: '远程控制打印机',
  review: '复核',
  import: '导入',
  import_internal_quote: '导入内部报价',
  export_customer_quote: '导出客户报价',
  compare: '比对',
  clone: '复制报价',
  header_edit: '编辑报价抬头',
  summary_read: '查看报价汇总',
  timeline_read: '查看报价记录',
  archive: '归档报价',
  baseline_read: '查看报价基数',
  baseline_manage: '调整报价基数',
  reference_manage: '管理报价参考数据',
  final_submit: '提交最终报价',
  final_approve: '批准最终报价',
  sales_edit: '编辑业务报价',
  sales_review: '复核业务报价',
  self_review: '审核本人报价',
  engineering_edit: '编辑工程报价',
  engineering_review: '复核工程报价',
  electronic_edit: '编辑电子报价',
  electronic_review: '复核电子报价',
  molding_edit: '编辑啤机报价',
  molding_review: '复核啤机报价',
  painting_edit: '编辑喷油报价',
  painting_review: '复核喷油报价',
  slush_edit: '编辑搪胶报价',
  slush_review: '复核搪胶报价',
  sewing_edit: '编辑车缝报价',
  sewing_review: '复核车缝报价',
  assembly_edit: '编辑装配报价',
  assembly_review: '复核装配报价',
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
  'carton_procurement:read': '查看纸箱采购台账',
  'carton_procurement:order_write': '维护纸箱订单',
  'carton_procurement:receipt_write': '登记并确认纸箱收料',
  'carton_procurement:inventory_write': '纸箱库存出库与调整',
  'carton_procurement:closing_manage': '管理纸箱库存月结',
  'carton_procurement:import': '导入纸箱送货单与排期',
  'carton_procurement:exception_manage': '处理纸箱异常',
  'carton_procurement:customer_manage': '维护纸箱客户资料',
  'customer_price:compare': '比较报价差异',
  'customer_price:export_customer_quote': '导出客户报价',
  'customer_price:import_internal_quote': '导入内部报价',
  'customer_price:read': '查看报价中心',
  'customer_order:read': '查看客户订单中心',
  'customer_order:export': '确认并导出客户排期',
  'internal_quote:self_review': '本人创建报价可自审',
  'molding_sample:audit_read': '查看啤办敏感操作审计',
  'molding_sample:create': '新建啤办申请',
  'molding_sample:cross_factory_cost_read': '跨厂查看啤办成本',
  'molding_sample:cross_factory_read': '跨厂查看啤办单据',
  'molding_sample:delete_draft': '删除啤办草稿',
  'molding_sample:dispatch': '分派啤办生产任务',
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
  'molding_sample:raw_material_write': '维护啤办原料资料',
  'molding_sample:read': '查看啤办单据',
  'molding_sample:supervisor_review': '啤办主管审核',
  'molding_sample:warehouse_requisition': '发起啤办领料',
  'three_d_printing:read': '查看3D打印机管理',
  'three_d_printing:operate': '维护3D打印业务',
  'three_d_printing:image_upload': '上传3D产品图片',
  'three_d_printing:export': '导出3D生产报表',
  'three_d_printing:printer_control': '暂停或恢复3D打印机',
  'three_d_printing:audit_read': '查看3D打印审计记录',
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

export function permissionAccessKindLabel(accessKind: string) {
  return accessKind === 'read' ? '查看' : '操作'
}

export function permissionRiskLabel(riskLevel: string) {
  return riskLevel === 'high' ? '高风险' : '普通风险'
}

export function permissionStatusLabel(status: string) {
  return status === 'inactive' ? '已停用' : '已启用'
}

export function roleScopeModeLabel(scopeMode?: string) {
  const labels: Record<string, string> = {
    own_factory: '本厂',
    cross_factory_read: '跨厂查看',
    cross_factory_operate: '跨厂操作',
  }
  return labels[scopeMode ?? 'own_factory'] ?? '本厂'
}

export function roleScopeModeDescription(scopeMode?: string) {
  const descriptions: Record<string, string> = {
    own_factory: '查看和操作均只在员工主厂区生效。',
    cross_factory_read: '查看类权限可跨厂，操作类权限仍限员工主厂区。',
    cross_factory_operate: '查看和操作类权限均可跨厂，仍需遵守业务状态与审批规则。',
  }
  return descriptions[scopeMode ?? 'own_factory'] ?? descriptions.own_factory
}

export function permissionEffectiveScopeLabel(
  permission: { scope_type?: string; access_kind?: string },
  scopeMode?: string,
) {
  if (permission.scope_type === 'global') return '全局生效'
  if (scopeMode === 'cross_factory_operate') {
    return permission.access_kind === 'read' ? '跨厂查看' : '跨厂操作'
  }
  if (scopeMode === 'cross_factory_read' && permission.access_kind === 'read') return '跨厂查看'
  return permission.access_kind === 'read' ? '本厂查看' : '本厂操作'
}
