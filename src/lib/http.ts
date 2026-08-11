import axios, { type AxiosError, type AxiosInstance } from 'axios'

export interface ApiErrorPayload {
  message?: string
  detail?: unknown
  code?: string
  details?: unknown
}

export interface AccessFailure {
  config?: { url?: unknown }
  response?: {
    status?: number
    data?: unknown
  }
}

export type UnauthorizedHandler = (error: AccessFailure) => void
export type ForbiddenHandler = (error: AccessFailure) => void

let unauthorizedHandler: UnauthorizedHandler | null = null
let forbiddenHandler: ForbiddenHandler | null = null

export function setUnauthorizedHandler(handler: UnauthorizedHandler | null) {
  unauthorizedHandler = handler
}

export function setForbiddenHandler(handler: ForbiddenHandler | null) {
  forbiddenHandler = handler
}

/**
 * Route fetch-based clients through the same session/authorization handlers
 * used by the shared Axios instance. Streaming POST responses cannot use the
 * Axios interceptor, but a 401/403 must still have exactly one application
 * session-expiry path.
 */
export function dispatchAccessFailure(status: number, url: string, data?: unknown) {
  const failure: AccessFailure = {
    config: { url },
    response: { status, data },
  }
  if (status === 401) {
    unauthorizedHandler?.(failure)
  }
  if (status === 403) {
    forbiddenHandler?.(failure)
  }
}

export const http: AxiosInstance = axios.create({
  baseURL: import.meta.env?.VITE_API_BASE_URL ?? '/api',
  timeout: 15000,
  withCredentials: true,
  headers: {
    'Content-Type': 'application/json',
  },
})

function isExpectedCapabilityForbidden(error: AxiosError<ApiErrorPayload>) {
  if (error.config?.skipForbiddenSessionRefresh !== true) return false
  const requestUrl = error.config.url
  if (typeof requestUrl !== 'string') return false
  const requestPath = requestUrl.split('?')[0]
  return requestPath === '/ai/capabilities' || requestPath.endsWith('/ai/capabilities')
}

http.interceptors.response.use(
  (response) => response,
  (error: AxiosError<ApiErrorPayload>) => {
    if (error.response?.status === 401) {
      unauthorizedHandler?.(error)
    }
    if (
      error.response?.status === 403
      && !isExpectedCapabilityForbidden(error)
    ) {
      forbiddenHandler?.(error)
    }

    return Promise.reject(error)
  },
)

export function getApiErrorMessage(error: unknown) {
  if (axios.isAxiosError<ApiErrorPayload>(error)) {
    return extractApiErrorPayloadMessage(error.response?.data) ?? error.message
  }

  if (error instanceof Error) {
    return error.message
  }

  return 'Unexpected request error'
}

function extractApiErrorPayloadMessage(payload: ApiErrorPayload | undefined) {
  if (!payload) {
    return undefined
  }

  if (payload.message) {
    return payload.message
  }

  return formatApiDetail(payload.detail)
}

function formatApiDetail(detail: unknown): string | undefined {
  if (typeof detail === 'string') {
    return detail
  }

  if (Array.isArray(detail)) {
    const messages = detail
      .map((entry) => {
        if (typeof entry === 'string') {
          return entry
        }
        if (entry && typeof entry === 'object' && 'msg' in entry) {
          const message = (entry as { msg?: unknown }).msg
          return typeof message === 'string' ? message : ''
        }

        return ''
      })
      .filter(Boolean)

    return messages.length ? messages.join('; ') : undefined
  }

  if (detail && typeof detail === 'object') {
    const record = detail as { message?: unknown; msg?: unknown }
    if (typeof record.message === 'string') {
      return record.message
    }
    if (typeof record.msg === 'string') {
      return record.msg
    }
  }

  return undefined
}
