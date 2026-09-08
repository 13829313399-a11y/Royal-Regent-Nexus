import { http } from '@/lib/http'
import { createRandomUuid } from '@/lib/randomUuid'

const storagePrefix = 'carton-inventory-pending:v1:'
const pendingIds = new Map<string, string>()
const inFlight = new Map<string, Promise<unknown>>()

function canonical(value: unknown): unknown {
  if (Array.isArray(value)) return value.map(canonical)
  if (value && typeof value === 'object') {
    return Object.fromEntries(Object.entries(value).sort(([a], [b]) => a.localeCompare(b))
      .map(([key, item]) => [key, canonical(item)]))
  }
  return value
}

// Only unresolved inventory submissions are retained in this tab's session storage.
// A retry, including after refresh, must reuse the ID; a successful new form gets a new ID.
export function postCartonInventoryRequest<T>(url: string, payload: object): Promise<T> {
  const key = storagePrefix + JSON.stringify([url, canonical(payload)])
  const current = inFlight.get(key)
  if (current) return current as Promise<T>

  let requestId = pendingIds.get(key)
  try { requestId ??= sessionStorage.getItem(key) ?? undefined } catch { /* In-memory retries still work. */ }
  requestId ??= createRandomUuid()
  pendingIds.set(key, requestId)
  try { sessionStorage.setItem(key, requestId) } catch { /* Storage may be disabled. */ }

  const request = http.post<T>(url, { ...payload, request_id: requestId })
    .then(({ data }) => {
      pendingIds.delete(key)
      try { sessionStorage.removeItem(key) } catch { /* Storage may be disabled. */ }
      return data
    })
    .finally(() => { inFlight.delete(key) })
  inFlight.set(key, request)
  return request
}
