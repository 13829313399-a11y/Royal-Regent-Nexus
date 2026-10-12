import { getApiErrorMessage } from './http'
import type { FieldErrors } from './authFormValidation'
const allowed = new Set(['username', 'display_name', 'phone', 'email', 'department', 'position', 'org_unit_id', 'factory_id', 'password', 'new_password', 'current_password', 'confirm_password', 'contact', 'note'])
export function authProblem(error: unknown) {
  const failure = error as { response?: { status?: number; data?: Record<string, unknown>; headers?: Record<string, unknown> } }
  const data = failure?.response?.data ?? {}
  const detail = data.detail && typeof data.detail === 'object' && !Array.isArray(data.detail) ? data.detail as Record<string, unknown> : {}
  const entries = data.field_errors ?? detail.field_errors ?? (Array.isArray(data.detail) ? data.detail : [])
  const fieldErrors: FieldErrors = {}
  if (Array.isArray(entries)) for (const entry of entries) {
    const name = entry.field ?? entry.loc?.at(-1)
    if (allowed.has(name)) fieldErrors[name] = String(entry.message ?? entry.msg ?? '请检查填写内容')
  }
  const retry = Number(data.retry_after_seconds ?? failure?.response?.headers?.['retry-after'])
  return { message: getApiErrorMessage(error), code: String(data.code ?? detail.code ?? ''), fieldErrors,
    retryAfter: Number.isFinite(retry) ? Math.max(0, retry) : 0,
    uncertain: !failure?.response || (failure.response.status ?? 0) >= 500 }
}
