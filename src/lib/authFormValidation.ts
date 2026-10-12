export type FieldErrors = Record<string, string>
export const passwordChineseMessage = '密码不能包含中文，请使用英文、数字或符号'
const chinese = /[\u3400-\u4dbf\u4e00-\u9fff\uf900-\ufaff]/u
export function passwordError(value: string, isNew = true) {
  if (!value) return '请输入密码'
  if (chinese.test(value)) return passwordChineseMessage
  if (isNew && value.length < 6) return '密码至少需要 6 位'
  if (isNew && value.length > 256) return '密码不能超过 256 个字符'
  return ''
}
export function newPasswordErrors(password: string, confirmation: string): FieldErrors {
  const errors: FieldErrors = {}
  const error = passwordError(password)
  const confirmError = passwordError(confirmation)
  if (error) errors.new_password = error
  if (confirmError) errors.confirm_password = confirmError
  else if (password !== confirmation) errors.confirm_password = '两次输入的密码不一致'
  return errors
}
export function focusFirstError(errors: FieldErrors) {
  for (const name of Object.keys(errors)) {
    const input = document.querySelector<HTMLElement>(`[name="${name}"]`)
    if (input) { input.focus(); return }
  }
}
