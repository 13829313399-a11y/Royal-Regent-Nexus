import { readFileSync } from 'node:fs'
import { join } from 'node:path'
import { describe, expect, it } from 'vitest'

const source = readFileSync(join(process.cwd(), 'src/views/SystemUserManagementView.vue'), 'utf8')
const template = source.slice(source.indexOf('<template>'), source.indexOf('<style scoped>'))

describe('SystemUserManagementView source contract', () => {
  it('edits registration profile data and assigns one system position from the full catalog', () => {
    for (const requiredSource of [
      'systemApi.listRegistrationRequests',
      'systemApi.listUsers',
      'systemApi.listSystemPositions',
      'systemApi.approveRegistrationRequest',
      'systemApi.rejectRegistrationRequest',
      'approvalProfiles',
      'RegistrationProfileRequest',
      'system_position_role_id',
      'profile,',
      'registrationDepartments',
      'allSystemPositions',
      'groupedSystemPositions',
      'aria-label="选择内置权限职位"',
      '<optgroup',
      'selected-system-position-summary',
      'aria-live="polite"',
      'aria-atomic="true"',
      'aria-label="确认姓名"',
      'aria-label="确认电话"',
      'aria-label="确认邮箱"',
      'aria-label="确认厂区"',
      'aria-label="确认部门"',
      'aria-label="确认职位"',
      '注册资料核验',
      '内置权限职位',
      '真实职位只用于个人资料展示',
      '个人职位',
      '权限职位',
      '调整权限职位',
      '/system/users/${encodeURIComponent(user.id)}/access',
    ]) {
      expect(source).toContain(requiredSource)
    }

    expect(source).not.toContain('buildApprovalRoleAssignments')
    expect(source).not.toContain('positionsForDepartment')
    expect(source).not.toContain('permissionGroupsForSelectedRole')
    expect(source).not.toContain('inferPermissionCodesForRole')
    expect(template).not.toContain('role="radiogroup"')
    expect(template).not.toContain('role="radio"')
    expect(template).not.toContain('权限清单')
    expect(template).not.toContain('数据范围')
    expect(template).not.toContain('工程师默认组合授权')
    expect(template).not.toContain('高级权限管理')
  })

  it('retains account operations and the reference approval shell', () => {
    for (const requiredSource of [
      'systemApi.listPasswordResetRequests',
      'systemApi.updateUserStatus',
      'systemApi.approvePasswordResetRequest',
      'systemApi.rejectPasswordResetRequest',
      'systemApi.reissuePasswordResetRequest',
      'PasswordResetRequestDetail',
      '密码重置',
      '批准并开放自助改密',
      '重新开放 4 小时',
      '系统不会生成或显示临时密码',
      'UserAvatar',
      'user.avatar_url',
      '停用',
      '恢复',
      'permission-approval-page',
      'class="wrap"',
      'TabsList',
      '账号办理',
      'class="approval-workspace"',
      'class="queue"',
      'class="q-item"',
    ]) {
      expect(source).toContain(requiredSource)
    }
  })

  it('keeps username typography from overriding the shared avatar layout', () => {
    expect(template).toContain('class="user-identity"')
    expect(readFileSync(join(process.cwd(), 'src/views/iam-account.css'), 'utf8')).toContain(
      '.user-identity span {',
    )
    expect(source).not.toContain('.user-cell span {')
  })

  it('degrades to a protected read-only page without relying on backend 403 responses', () => {
    expect(source).toContain(
      "const canManageUsers = computed(() => authStore.can('system:user_manage'))",
    )
    expect(source).toContain('data-testid="system-users-protected-notice"')
    expect(source).toContain('页面可访问 · 敏感账号资料受保护')
    expect(source).toContain('if (!canManageUsers.value) return')
    expect(source).not.toContain('v-if="authStore.can(\'system:permission_catalog_read\')"')
    expect(source.match(/if \(!ensureUserManagementPermission\(\)\) return/g)).toHaveLength(3)
    expect(source).toMatch(
      /async function loadData\(\) \{[\s\S]*?if \(!canManageUsers\.value\) \{[\s\S]*?return\s+\}/,
    )
  })

  it('never receives, displays, copies, or persists a temporary password', () => {
    expect(source).not.toContain('oneTimeTemporaryPassword')
    expect(source).not.toContain('temporary_password')
    expect(source).not.toContain('navigator.clipboard.writeText')
    expect(source).not.toContain('一次性临时密码')
    expect(source).not.toContain('localStorage.setItem')
    expect(source).not.toContain('sessionStorage.setItem')
  })
})
