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
      '将继承的权限',
      '这里只展示内置职位结果，不能逐项修改',
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
})
