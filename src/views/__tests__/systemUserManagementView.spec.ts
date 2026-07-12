import { readFileSync } from 'node:fs'
import { join } from 'node:path'
import { describe, expect, it } from 'vitest'

const source = readFileSync(join(process.cwd(), 'src/views/SystemUserManagementView.vue'), 'utf8')

describe('SystemUserManagementView source contract', () => {
  it('loads pending requests, users, roles, and submits approval assignments', () => {
    for (const requiredSource of [
      'systemApi.listRegistrationRequests',
      'systemApi.listUsers',
      'systemApi.listRoles',
      'systemApi.listNotifications',
      'systemApi.approveRegistrationRequest',
      'systemApi.rejectRegistrationRequest',
      'systemApi.updateUserStatus',
      'systemApi.resetUserPassword',
      'password_reset',
      '密码重置',
      '重置为临时密码',
      'notification_id',
      'role_assignments',
      'recommended_role_ids',
      '待审批',
      '用户列表',
      '联系方式',
      'user.phone',
      'user.email',
      'UserAvatar',
      'user.avatar_url',
      'resolveUserAvatarUrl',
      'shape="rounded"',
      '6 厂区',
      'permission-approval-page',
      'class="wrap"',
      'class="topbar"',
      'class="topbar-left"',
      'class="home-exit-link"',
      'ArrowLeft',
      'position: sticky;',
      'backdrop-filter: blur(14px);',
      'class="brand"',
      'class="admin"',
      'class="stats"',
      'class="stat"',
      'class="grid approval-workspace"',
      'class="panel-head"',
      'class="queue"',
      'class="q-item"',
      'class="applicant"',
      'class="section"',
      'class="sec-title"',
      'class="roles"',
      'class="actions"',
      'class="note-in"',
      'btn-approve',
      '权限清单',
      'permissionGroupsForSelectedRole',
      'perm-groups',
      'perm-group',
      'perm locked',
      'admin.manage',
      'sales_customer_supervisor',
      'factoryScopesForSelectedRequest',
      'departmentScopesForSelectedRequest',
      'allFactoryScopeLabel',
      'molding_sample:create',
      '跨厂查看啤办单据',
      'molding_sample:cross_factory_read',
      '跨厂查看啤办成本',
      'molding_sample:cross_factory_cost_read',
      'group_molding_readonly',
      'selectedRequest',
      'route.query.request_id',
      '停用',
      '恢复',
      "userStatusFilter = ref<'all' | 'active' | 'suspended' | 'retired'>('all')",
      "retired: { label: '已离职', toneClass: 'pill-slate' }",
      "userStatusPresentation(user.status).label",
      "userStatusPresentation(user.status).toneClass",
      "label: '未知状态'",
      'aria-label="搜索用户"',
      '配置权限',
      '/system/users/${encodeURIComponent(user.id)}/access',
      '高级权限管理',
      '/system/iam/permissions',
    ]) {
      expect(source).toContain(requiredSource)
    }

    const readonlyPreset = source.match(/group_molding_readonly:\s*\[([\s\S]*?)\],/)
    expect(readonlyPreset?.[1]).toContain("'molding_sample:cross_factory_read'")
    expect(readonlyPreset?.[1]).not.toContain('molding_sample:create')
    expect(readonlyPreset?.[1]).not.toContain('molding_sample:cross_factory_cost_read')
  })
})
