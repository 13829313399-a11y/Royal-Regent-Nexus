import { readFileSync } from 'node:fs'
import { join } from 'node:path'
import { describe, expect, it } from 'vitest'

const source = readFileSync(join(process.cwd(), 'src/views/RegisterView.vue'), 'utf8')

describe('RegisterView source contract', () => {
  it('collects the approved basic registration fields and submits through authApi.register', () => {
    for (const requiredSource of [
      'authApi.register',
      'username',
      'displayName',
      'password',
      'confirmPassword',
      'passwordModel',
      'confirmPasswordModel',
      '密码不能包含中文，请使用英文、数字或符号',
      'phone',
      'email',
      'factoryId',
      'department',
      'position',
      '<span>职位 <b>*</b></span>',
      'autocomplete="organization-title"',
      'maxlength="128"',
      '工程部技术员',
      '管理员会在审批时核验或修正',
      '账号申请已提交',
      'router.replace',
      'register-wrap',
      'register-note',
      'radial-gradient(circle at 82% 8%',
      'grid-template-columns: 0.82fr 1fr',
      'class="control select-control"',
      '.select-control select',
      'inset: 0;',
      'padding: 0 40px;',
      'right: 12px;',
    ]) {
      expect(source).toContain(requiredSource)
    }
    expect(source).toMatch(/password\.value\s*!==\s*confirmPassword\.value/)
    expect(source).toMatch(/!phone\.value\.trim\(\)\s*&&\s*!email\.value\.trim\(\)/)
    expect(source).not.toContain('registration-position-suggestions')
    expect(source).not.toContain('<datalist')
  })
})
