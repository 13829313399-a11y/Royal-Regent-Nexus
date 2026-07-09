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
      '账号申请已提交',
      'router.replace',
      'register-wrap',
      'register-note',
      'radial-gradient(circle at 82% 8%',
      'grid-template-columns: 0.82fr 1fr',
    ]) {
      expect(source).toContain(requiredSource)
    }
    expect(source).toMatch(/password\.value\s*!==\s*confirmPassword\.value/)
    expect(source).toMatch(/!phone\.value\.trim\(\)\s*&&\s*!email\.value\.trim\(\)/)
  })
})
