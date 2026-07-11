import { describe, expect, it } from 'vitest'
import { createIamApi } from '@/api/iam'

describe('iamApi', () => {
  it('uses the IAM contracts for user access, role templates, requests, and audit', async () => {
    const calls: Array<{ method: string; url: string; data?: unknown }> = []
    const client = {
      async get<T = unknown>(url: string): Promise<{ data: T }> {
        calls.push({ method: 'get', url })
        return { data: [] as T }
      },
      async post<T = unknown>(url: string, data?: unknown): Promise<{ data: T }> {
        calls.push({ method: 'post', url, data })
        return { data: { preview_token: 'preview-1' } as T }
      },
    }
    const api = createIamApi(client)

    await api.listPermissions()
    await api.getManageableScopes()
    await api.searchUsers('张三', 'active')
    await api.getUserAccess('user/1')
    await api.previewUserAccess('user/1', {
      base_revision: 3,
      reason: '开放设备维修模块',
      overrides: [{
        permission_code: 'maintenance:update',
        effect: 'allow',
        factory_id: 'huaxing',
        department: 'engineering',
        valid_until: null,
      }],
    })
    await api.commitUserAccess('user/1', 'preview-1', true)
    await api.listRoles()
    await api.getRoleAccess('engineer')
    await api.previewRoleAccess('engineer', {
      base_version: 2,
      reason: '角色补充查看权限',
      permission_codes: ['maintenance:read'],
    })
    await api.commitRoleAccess('engineer', 'role-preview', false)
    await api.listAccessRequests('pending')
    await api.approveAccessRequest('request/1', '范围和风险已复核')
    await api.rejectAccessRequest('request/2', '范围不符合要求')
    await api.listAuditEvents({ target_user_id: 'user-1', module_code: 'maintenance' })

    expect(calls.map((call) => `${call.method} ${call.url}`)).toEqual([
      'get /iam/permissions?status=active',
      'get /iam/manageable-scopes',
      'get /iam/users/search?query=%E5%BC%A0%E4%B8%89&status=active',
      'get /iam/users/user%2F1/access',
      'post /iam/users/user%2F1/access/preview',
      'post /iam/users/user%2F1/access/commit',
      'get /iam/roles',
      'get /iam/roles/engineer/access',
      'post /iam/roles/engineer/access/preview',
      'post /iam/roles/engineer/access/commit',
      'get /iam/access-requests?status=pending',
      'post /iam/access-requests/request%2F1/approve',
      'post /iam/access-requests/request%2F2/reject',
      'get /iam/audit-events?target_user_id=user-1&module_code=maintenance',
    ])
    expect(calls[4].data).toEqual({
      base_revision: 3,
      reason: '开放设备维修模块',
      overrides: [{
        permission_code: 'maintenance:update',
        effect: 'allow',
        factory_id: 'huaxing',
        department: 'engineering',
        valid_until: null,
      }],
    })
    expect(calls[5].data).toEqual({ preview_token: 'preview-1', confirm_high_risk: true })
  })
})
