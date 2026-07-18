import { readFileSync } from 'node:fs'
import { join } from 'node:path'
import { describe, expect, it } from 'vitest'

const source = readFileSync(join(process.cwd(), 'src/views/UserAccessManagementView.vue'), 'utf8')

describe('UserAccessManagementView contract', () => {
  it('changes one system position through preview and atomic commit', () => {
    for (const required of [
      'IamIdentitySummary',
      'iamApi.getUserAccess',
      'iamApi.listSystemPositions',
      'iamApi.listPermissions',
      "iamApi.listPermissions('all')",
      'iamApi.getRoleAccess',
      'iamApi.previewUserSystemPosition',
      'iamApi.commitUserSystemPosition',
      'system_position_role_id',
      'assignableSystemPositions',
      'base_revision',
      'preview_token',
      'confirmedHighRisk',
      'authStore.refreshSession',
      '内置权限职位',
      '选择新的内置权限职位',
      '显示全部内置职位，并按权限部门分组',
      'previewAfterPositionLabel',
      '尚未确认主组织资料',
      'missing-primary-department',
      '将继承的完整权限',
      '权限和数据范围由代码固定，管理员只能查看，不能逐项修改',
      '实际职位用于人员资料',
      '权限职位',
      '推荐仅用于提示，不会自动选中或授权',
      'selected-position-fixed-metadata',
      'permissionStatusLabel(permission.status)',
      'permissionRiskLabel(permission.risk_level)',
      '检测到历史授权',
      'legacy_role_count',
      'active_override_count',
      'cleanup_role_count',
      'cleanup_override_count',
      'hasSystemPositionAction',
      '预览历史授权清理',
      'removed_role_count',
      'removed_override_count',
      'data-testid="system-position-action-panel"',
    ]) {
      expect(source).toContain(required)
    }
    expect(source).not.toContain('position.position_department === userDepartment.value')
    expect(source).not.toContain('isBuiltInPositionPermissionVisible')
    expect(source).not.toContain("iamApi.listPermissions('active')")
  })

  it('does not render scope, multi-role, granular override, or expiry controls', () => {
    for (const removed of [
      'IamScopeSelector',
      'IamRoleBindings',
      'IamPermissionMatrix',
      'PermissionDraftEffect',
      'RoleBindingDraft',
      'updatePermissionState',
      'addRoleBinding',
      'revokeRoleBinding',
      'validUntil',
      '有效期至',
      '用户级调整',
      '调整原因',
      '例如：员工岗位职责调整为工程主管',
      'reason = ref',
      'reason.trim()',
    ]) {
      expect(source).not.toContain(removed)
    }
    expect(source).toContain('overflow-x-clip')
    expect(source).toContain('w-full min-w-0')
    expect(source).toContain('aria-label="选择新的内置权限职位"')
    expect(source).toContain('role="dialog"')
  })

  it('uses a protected read-only fallback and rechecks every local change handler', () => {
    expect(source).toContain("const canManageAccess = computed(() => authStore.can('system:access_manage'))")
    expect(source).toContain('data-testid="user-access-protected-notice"')
    expect(source).toContain('页面可访问 · 权限资料受保护')
    expect(source).toMatch(/async function loadData\(\) \{\s+if \(!canManageAccess\.value\) \{[\s\S]*?return\s+\}/)
    expect(source.match(/if \(!ensureAccessManagementPermission\(\)\) return/g)).toHaveLength(4)
    expect(source).toContain(':disabled="!canManageAccess || isPreviewing || isCommitting"')
    expect(source).toContain('v-if="canManageAccess && preview"')
  })
})
