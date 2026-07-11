import { readFileSync } from 'node:fs'
import { join } from 'node:path'
import { describe, expect, it } from 'vitest'
import {
  permissionActionLabel,
  permissionDisplayLabel,
  permissionScopeLabel,
} from '../../components/iam/permissionCatalogLabels'

function readView(name: string) {
  return readFileSync(join(process.cwd(), `src/views/${name}.vue`), 'utf8')
}

describe('IAM management view semantics and accessibility', () => {
  it('separates protected-role template records from automatic superadmin access', () => {
    const source = readView('IamRoleTemplatesView')

    for (const required of [
      'activePermissionCount',
      'templatePermissionCount',
      '模板记录',
      '自动拥有全部',
      '超级管理员按系统规则自动拥有全部启用权限',
      '系统自动拥有',
      'aria-pressed',
      '关闭角色模板影响预览',
      'overflow-x-hidden',
    ]) {
      expect(source).toContain(required)
    }
    expect(source).not.toContain('sticky bottom-4')
  })

  it('renders business labels while retaining action and scope codes', () => {
    expect(permissionActionLabel('read')).toBe('查看')
    expect(permissionActionLabel('manager_review')).toBe('经理终审')
    expect(permissionActionLabel('unknown_action')).toBe('自定义操作')
    expect(permissionScopeLabel('factory_department')).toBe('指定厂区与部门')
    expect(permissionScopeLabel('global')).toBe('全集团')
    expect(permissionScopeLabel('factory')).toBe('指定厂区')
    expect(permissionScopeLabel('department')).toBe('指定部门')
    expect(permissionScopeLabel('unknown_scope')).toBe('自定义范围')
    expect(permissionDisplayLabel({
      code: 'carton_mark:photo_upload',
      name: 'carton_mark:photo_upload',
      module_name: '箱唛管理',
      action: 'photo_upload',
    })).toBe('上传箱唛实拍')
    expect(permissionDisplayLabel({
      code: 'maintenance:update',
      name: '修改维修记录',
      module_name: '设备维修',
      action: 'update',
    })).toBe('修改维修记录')
    expect(permissionDisplayLabel({
      code: 'new_module:read',
      name: 'new_module:read',
      module_name: '新模块',
      action: 'read',
    })).toBe('新模块 · 查看')

    const registeredPermissionLabels = {
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
      'molding_sample:audit_read': '查看啤办审计记录',
      'molding_sample:create': '新建啤办申请',
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
      'system:permission_catalog_read': '查看权限目录',
      'system:role_manage': '管理角色模板',
      'system:user_manage': '管理用户账号',
    }
    expect(Object.keys(registeredPermissionLabels)).toHaveLength(33)
    for (const [code, label] of Object.entries(registeredPermissionLabels)) {
      expect(permissionDisplayLabel({ code, name: code })).toBe(label)
    }

    const source = readView('IamPermissionCatalogView')
    for (const required of [
      'permissionActionLabel(permission.action)',
      'permissionDisplayLabel(permission)',
      'permissionScopeLabel(permission.scope_type)',
      '{{ permission.action }}',
      '{{ permission.scope_type }}',
      '搜索权限',
      '按模块筛选权限',
      '按风险级别筛选权限',
      'overflow-x-auto',
      'overscroll-x-contain',
    ]) {
      expect(source).toContain(required)
    }

    const roleSource = readView('IamRoleTemplatesView')
    expect(roleSource).toContain('permissionDisplayLabel(permission)')
    expect(roleSource).toContain('permissionLabels.get(diff.permission_code)')
  })

  it('labels request status, review reason, and audit filters without page overflow', () => {
    const requestSource = readView('IamAccessRequestsView')
    for (const required of [
      '申请状态',
      '按申请状态筛选',
      '复核意见（必填）',
      '说明批准或拒绝的依据',
      'effectLabel(change.effect)',
      'permissionLabel(change.permission_code)',
      'overflow-x-hidden',
    ]) {
      expect(requestSource).toContain(required)
    }

    const auditSource = readView('IamAuditView')
    for (const required of [
      '筛选权限操作记录',
      '按目标用户 ID 筛选',
      '按模块代码筛选',
      '按厂区代码筛选',
      '筛选开始日期',
      '筛选结束日期',
      'minmax(0,1fr)',
      'permissionLabel(event.permission_code)',
      'overflow-x-hidden',
    ]) {
      expect(auditSource).toContain(required)
    }
  })
})
