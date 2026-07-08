import { describe, expect, it } from 'vitest'
import { createSystemApi } from '../system'

describe('systemApi', () => {
  it('uses the system namespace for notifications, registration approvals, users, and roles', async () => {
    const calls: Array<{ method: string; url: string; data?: unknown }> = []
    const client = {
      async get<T = unknown>(url: string): Promise<{ data: T }> {
        calls.push({ method: 'get', url })
        return { data: { url } as T }
      },
      async post<T = unknown>(url: string, data?: unknown): Promise<{ data: T }> {
        calls.push({ method: 'post', url, data })
        return { data: { url, data } as T }
      },
      async patch<T = unknown>(url: string, data?: unknown): Promise<{ data: T }> {
        calls.push({ method: 'patch', url, data })
        return { data: { url, data } as T }
      },
    }
    const api = createSystemApi(client)

    await api.listNotifications()
    await api.updateNotification('notice-1', { status: 'handled' })
    await api.listRegistrationRequests('pending')
    await api.approveRegistrationRequest('registration-1', {
      role_assignments: [{ role_id: 'engineer', factory_id: 'huaxing', department: 'engineering' }],
      review_comment: '资料完整',
    })
    await api.rejectRegistrationRequest('registration-2', { review_comment: '资料不完整' })
    await api.listUsers('active')
    await api.updateUserStatus('user-1', { status: 'suspended' })
    await api.listRoles()

    expect(calls.map((call) => `${call.method} ${call.url}`)).toEqual([
      'get /system/notifications',
      'patch /system/notifications/notice-1',
      'get /system/registration-requests?status=pending',
      'post /system/registration-requests/registration-1/approve',
      'post /system/registration-requests/registration-2/reject',
      'get /system/users?status=active',
      'patch /system/users/user-1/status',
      'get /system/roles',
    ])
    expect(calls[3].data).toEqual({
      role_assignments: [{ role_id: 'engineer', factory_id: 'huaxing', department: 'engineering' }],
      review_comment: '资料完整',
    })
  })
})
