import { readFileSync } from 'node:fs'
import { join } from 'node:path'
import { describe, expect, it } from 'vitest'

const viewSource = readFileSync(join(process.cwd(), 'src/views/ForcePasswordChangeView.vue'), 'utf8')
const routerSource = readFileSync(join(process.cwd(), 'src/router/index.ts'), 'utf8')
const notificationSource = readFileSync(join(process.cwd(), 'src/composables/useNotificationCenter.ts'), 'utf8')

describe('forced password change workflow source contract', () => {
  it('collects and validates all password fields before calling the Pinia action', () => {
    for (const expected of [
      '当前密码',
      '新密码',
      '确认新密码',
      '密码不能包含中文',
      '新密码不能与当前密码相同',
      'authStore.changePassword',
      'resolvePostLoginRedirect',
      'showCurrentPassword',
      'showNewPassword',
      'showConfirmPassword',
    ]) {
      expect(viewSource).toContain(expected)
    }
  })

  it('clears plaintext fields after success and when leaving the page', () => {
    expect(viewSource).toContain('onBeforeUnmount')
    expect(viewSource.match(/currentPassword\.value = ''/g)?.length).toBeGreaterThanOrEqual(2)
    expect(viewSource.match(/newPassword\.value = ''/g)?.length).toBeGreaterThanOrEqual(2)
    expect(viewSource).not.toContain('localStorage')
    expect(viewSource).not.toContain('sessionStorage')
  })

  it('forces flagged sessions onto the dedicated route and keeps redirects internal', () => {
    expect(routerSource).toContain("path: '/change-password'")
    expect(routerSource).toContain('authStore.currentUser?.force_password_change')
    expect(routerSource).toContain("if (to.name === 'change-password') return true")
    expect(routerSource).toContain('resolvePostLoginRedirect(router, to.fullPath)')
  })

  it('routes password reset notifications by formal request id', () => {
    expect(notificationSource).toContain('notification.payload.password_reset_request_id')
    expect(notificationSource).toContain('/system/users?tab=password-reset&request_id=')
    expect(notificationSource).not.toContain('tab=password-reset&notification_id=')
  })
})
