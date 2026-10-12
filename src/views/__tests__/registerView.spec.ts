import { describe, expect, it } from 'vitest'
import { newPasswordErrors, passwordError } from '@/lib/authFormValidation'
describe('registration password policy', () => {
  it('reports Chinese input without changing or trimming the supplied value', () => {
    const value = ' 中文Password '
    expect(passwordError(value)).toContain('不能包含中文')
    expect(value).toBe(' 中文Password ')
    expect(passwordError(' secret ')).toBe('')
  })
  it('limits new passwords while retaining historical long login passwords', () => {
    expect(passwordError('x'.repeat(256))).toBe('')
    expect(passwordError('x'.repeat(257))).toContain('256')
    expect(passwordError('x'.repeat(300), false)).toBe('')
    expect(newPasswordErrors('123456', '123457').confirm_password).toContain('不一致')
  })
})
