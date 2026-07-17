import { readFileSync } from 'node:fs'
import { join } from 'node:path'
import { describe, expect, it } from 'vitest'
import {
  isBuiltInPositionPermissionVisible,
  permissionActionLabel,
  permissionDisplayLabel,
  permissionScopeLabel,
} from '../../components/iam/permissionCatalogLabels'

function readView(name: string) {
  return readFileSync(join(process.cwd(), `src/views/${name}.vue`), 'utf8')
}

describe('IAM management view semantics and accessibility', () => {
  it('groups fixed system positions by department for template maintenance', () => {
    const source = readView('IamRoleTemplatesView')

    for (const required of [
      'iamApi.listSystemPositions()',
      'groupedSystemPositions',
      'position_department',
      'position_department_name',
      'position_sort_order',
      '内置职位权限',
      '内置职位目录',
      '按部门维护固定职位权限',
      'roles.value = await iamApi.listSystemPositions()',
      '关闭内置职位影响预览',
      'overflow-x-clip',
      'data-testid="role-templates-sticky-navigation"',
      'sticky top-0 z-30',
      'data-testid="role-editor-workspace"',
      'xl:h-dvh',
      'xl:min-h-0',
      'data-testid="role-directory-scroll-region"',
      'data-testid="role-permission-scroll-region"',
      'overflow-y-auto',
      'data-testid="role-editor-action-bar"',
      '搜索职位',
      '搜索权限',
      '有变更',
      '当前职位还有未保存的权限修改',
    ]) {
      expect(source).toContain(required)
    }
    expect(source).not.toContain('iamApi.listRoles()')
    expect(source).not.toContain('overflow-x-hidden')
    expect(source).not.toContain('sticky bottom-4')
  })

  it('renders business labels while retaining action and scope codes', () => {
    expect(permissionActionLabel('read')).toBe('查看')
    expect(permissionActionLabel('cross_factory_read')).toBe('跨厂查看')
    expect(permissionActionLabel('cross_factory_cost_read')).toBe('跨厂查看成本')
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
    expect(Object.keys(registeredPermissionLabels)).toHaveLength(35)
    for (const [code, label] of Object.entries(registeredPermissionLabels)) {
      expect(permissionDisplayLabel({ code, name: code })).toBe(label)
    }
    expect(isBuiltInPositionPermissionVisible('system:access_request')).toBe(false)
    expect(isBuiltInPositionPermissionVisible('system:access_approve')).toBe(false)
    expect(isBuiltInPositionPermissionVisible('system:role_manage')).toBe(false)
    expect(isBuiltInPositionPermissionVisible('system:audit_read')).toBe(false)
    expect(isBuiltInPositionPermissionVisible('system:permission_catalog_read')).toBe(false)

    const roleSource = readView('IamRoleTemplatesView')
    expect(roleSource).toContain('permissionDisplayLabel(permission)')
    expect(roleSource).toContain('permissionLabels.get(diff.permission_code)')
  })

  it('keeps IAM navigation focused on users and built-in positions', () => {
    const source = readFileSync(join(process.cwd(), 'src/components/iam/IamNavigation.vue'), 'utf8')
    expect(source).toContain("to: '/system/users', label: '用户与授权'")
    expect(source).toContain("to: '/system/iam/roles', label: '内置职位权限'")
    expect(source).not.toContain("label: '权限目录'")
    expect(source).not.toContain("label: '权限申请'")
    expect(source).not.toContain("label: '操作记录'")
  })
})
