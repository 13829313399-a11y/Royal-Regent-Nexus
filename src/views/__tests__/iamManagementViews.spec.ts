import { readFileSync } from 'node:fs'
import { join } from 'node:path'
import { describe, expect, it } from 'vitest'
import {
  permissionAccessKindLabel,
  permissionActionLabel,
  permissionDisplayLabel,
  permissionEffectiveScopeLabel,
  permissionRiskLabel,
  permissionScopeLabel,
  permissionStatusLabel,
  roleScopeModeLabel,
} from '../../components/iam/permissionCatalogLabels'

function readView(name: string) {
  return readFileSync(join(process.cwd(), `src/views/${name}.vue`), 'utf8')
}

describe('IAM management view semantics and accessibility', () => {
  it('renders fixed system positions as a searchable read-only catalog', () => {
    const source = readView('IamRoleTemplatesView')

    for (const required of [
      'iamApi.listSystemPositions()',
      "iamApi.listPermissions('all')",
      'groupedSystemPositions',
      'position_department',
      'position_department_name',
      'position_sort_order',
      '内置职位权限',
      '内置职位目录',
      '内置职位由系统代码固定维护；管理员可以查看，但不能在线修改。',
      '权限来源',
      '代码固定 · 只读',
      '数据范围',
      '修改方式',
      '定义版本',
      '定义哈希',
      '提交明确需求，通过代码变更、测试和发布流程生效',
      '跨厂操作 · 全业务部门',
      '不包含账号与权限管理',
      '已包含',
      'permissionStatusLabel(permission.status)',
      'permissionRiskLabel(permission.risk_level)',
      'data-testid="role-templates-sticky-navigation"',
      'data-testid="role-catalog-protected-notice"',
      'data-testid="role-viewer-workspace"',
      'data-testid="role-directory-scroll-region"',
      'data-testid="role-summary-panel"',
      'data-testid="permission-filter-toolbar"',
      'data-testid="definition-details-trigger"',
      'data-testid="definition-details-panel"',
      'data-testid="role-permission-scroll-region"',
      '搜索职位',
      '搜索权限',
    ]) {
      expect(source).toContain(required)
    }

    for (const removed of [
      'previewRoleAccess',
      'commitRoleAccess',
      'getManageableScopes',
      'type="checkbox"',
      'type="radio"',
      '变更原因',
      '撤销修改',
      '预览职位影响',
      '确认提交',
      '有变更',
      '未保存的权限修改',
      'isBuiltInPositionPermissionVisible',
    ]) {
      expect(source).not.toContain(removed)
    }

    expect(source).not.toContain('xl:h-dvh')
    expect(source).not.toContain('xl:overflow-hidden')
    expect(source).not.toContain('xl:overflow-y-auto')
    expect(source).toContain("const canReadPermissionCatalog = computed(() => authStore.can('system:permission_catalog_read'))")
    expect(source).toMatch(/async function loadData\(\) \{\s+if \(!canReadPermissionCatalog\.value\) \{[\s\S]*?return\s+\}/)
    expect(source).toContain('@media (min-width: 1280px) and (min-height: 820px)')
    expect(source).toContain('@media (max-width: 1279px), (max-height: 819px)')
  })

  it('provides complete business labels, status, risk, and fixed-scope presentation', () => {
    expect(permissionActionLabel('read')).toBe('查看')
    expect(permissionActionLabel('raw_material_write')).toBe('维护原料资料')
    expect(permissionScopeLabel('factory_department')).toBe('指定厂区与部门')
    expect(permissionAccessKindLabel('read')).toBe('查看')
    expect(permissionAccessKindLabel('operate')).toBe('操作')
    expect(permissionRiskLabel('normal')).toBe('普通风险')
    expect(permissionRiskLabel('high')).toBe('高风险')
    expect(permissionStatusLabel('active')).toBe('已启用')
    expect(permissionStatusLabel('inactive')).toBe('已停用')
    expect(roleScopeModeLabel('cross_factory_operate')).toBe('跨厂操作')
    expect(permissionEffectiveScopeLabel({ scope_type: 'factory_department', access_kind: 'read' }, 'cross_factory_read')).toBe('跨厂查看')
    expect(permissionEffectiveScopeLabel({ scope_type: 'factory_department', access_kind: 'operate' }, 'cross_factory_read')).toBe('本厂操作')
    expect(permissionDisplayLabel({
      code: 'molding_sample:raw_material_write',
      name: 'molding_sample:raw_material_write',
      module_name: '啤办管理',
      action: 'raw_material_write',
    })).toBe('维护啤办原料资料')
    expect(permissionDisplayLabel({
      code: 'system:access_approve',
      name: 'system:access_approve',
      module_name: '系统管理',
      action: 'access_approve',
    })).toBe('审批权限申请')

    const labelSource = readFileSync(join(process.cwd(), 'src/components/iam/permissionCatalogLabels.ts'), 'utf8')
    expect(labelSource).not.toContain('LEGACY_IAM_PAGE_PERMISSION_CODES')
    expect(labelSource).not.toContain('isBuiltInPositionPermissionVisible')
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
