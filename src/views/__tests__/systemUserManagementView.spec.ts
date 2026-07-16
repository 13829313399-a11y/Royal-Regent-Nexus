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
      'to="/system/iam/roles"',
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
      'systemApi.listNotifications',
      'systemApi.updateUserStatus',
      'systemApi.resetUserPassword',
      'password_reset',
      '密码重置',
      '重置为临时密码',
      'UserAvatar',
      'user.avatar_url',
      '停用',
      '恢复',
      'permission-approval-page',
      'class="wrap"',
      'class="topbar"',
      'class="grid approval-workspace"',
      'class="queue"',
      'class="q-item"',
    ]) {
      expect(source).toContain(requiredSource)
    }
  })
})
