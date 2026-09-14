import { computed, onScopeDispose, ref, shallowRef, watch, type Ref } from 'vue'
import { getApiErrorMessage } from '@/lib/http'
import type { UvCoverage, UvMeta } from '../contracts'

/**
 * 请求状态与请求代次。
 *
 * - 每个请求持有 AbortController，快速切换筛选或换厂时取消旧请求；
 * - 过时响应不能覆盖新页或其他厂区数据（代次比对）；
 * - `data === null && !loading && !error` 表示还没有数据，不是「0 条」；
 * - 失败保留结构化错误与可重试标记，绝不自动回落到样例数据。
 */

export interface UvRequestError {
  message: string
  code: string
  status: number | null
  fields: Record<string, string>
  retryable: boolean
}

export interface UvRequestState<T> {
  data: Ref<T | null>
  loading: Ref<boolean>
  error: Ref<UvRequestError | null>
  /** 首次读取是否已结束（无论成功或失败）。 */
  settled: Ref<boolean>
  /** 服务端返回的 meta（口径、覆盖范围、样例/正式标记、警告）。 */
  meta: Ref<UvMeta | null>
  /** 覆盖范围：完整 / 部分暂算 / 无数据。 */
  coverage: Ref<UvCoverage>
  run: () => Promise<T | null>
  cancel: () => void
  reset: () => void
}

interface UvStructuredError {
  code?: unknown
  message?: unknown
  fields?: unknown
  retryable?: unknown
  status?: unknown
  response?: { status?: unknown; data?: { detail?: unknown; code?: unknown; message?: unknown; fields?: unknown; retryable?: unknown } }
}

function normalizeError(error: unknown): UvRequestError {
  const candidate = error as UvStructuredError
  const payload = candidate?.response?.data
  const statusValue = candidate?.response?.status
  const status = typeof statusValue === 'number' ? statusValue : null
  const fieldsValue = payload?.fields ?? candidate?.fields
  const fields: Record<string, string> = {}
  if (fieldsValue && typeof fieldsValue === 'object') {
    for (const [key, value] of Object.entries(fieldsValue as Record<string, unknown>)) {
      fields[key] = String(value)
    }
  }
  const detail = payload?.detail
  if (Array.isArray(detail)) {
    detail.forEach((item, index) => {
      if (!item || typeof item !== 'object') return
      const entry = item as { loc?: unknown; msg?: unknown; type?: unknown }
      const key = Array.isArray(entry.loc) ? entry.loc.map(String).join('.') : `validation.${index}`
      fields[key] = typeof entry.msg === 'string' ? entry.msg : String(entry.type ?? '字段校验失败')
    })
  } else if (detail && typeof detail === 'object') {
    const entry = detail as { message?: unknown; msg?: unknown; code?: unknown; fields?: unknown }
    if (entry.fields && typeof entry.fields === 'object') {
      for (const [key, value] of Object.entries(entry.fields as Record<string, unknown>)) fields[key] = String(value)
    }
  }
  const message = typeof payload?.message === 'string'
    ? payload.message
    : typeof detail === 'string'
      ? detail
      : detail && typeof detail === 'object' && !Array.isArray(detail)
        ? String((detail as { message?: unknown; msg?: unknown; code?: unknown }).message
          ?? (detail as { msg?: unknown }).msg
          ?? '请求字段校验失败')
        : Array.isArray(detail)
          ? '请求字段校验失败，请检查标记字段。'
      : typeof candidate?.message === 'string'
        ? candidate.message
        : getApiErrorMessage(error)

  const code = typeof payload?.code === 'string'
    ? payload.code
    : typeof candidate?.code === 'string'
      ? candidate.code
      : status === 403
        ? 'uv_forbidden'
        : status === 401
          ? 'uv_unauthorized'
          : status === 409
            ? 'uv_conflict'
            : status === 422
              ? 'uv_invalid_field'
              : status === 503
                ? 'uv_service_unavailable'
                : 'uv_request_failed'

  return {
    message,
    code,
    status,
    fields,
    retryable: payload?.retryable === true || candidate?.retryable === true || status === null || status >= 500,
  }
}

export interface UvRequestOptions {
  /** 依赖变化时自动重跑，例如业务日期或班次。 */
  watchSource?: () => unknown
  immediate?: boolean
}

function isUvResponse(value: unknown): value is { meta: UvMeta; data: unknown } {
  return Boolean(
    value
    && typeof value === 'object'
    && 'meta' in (value as Record<string, unknown>)
    && 'data' in (value as Record<string, unknown>)
    && (value as { meta?: { factory_id?: unknown } }).meta?.factory_id !== undefined,
  )
}

export function useUvRequest<T>(
  loader: (signal: AbortSignal) => Promise<T | { meta: UvMeta; data: T }>,
  options: UvRequestOptions = {},
): UvRequestState<T> {
  const data = shallowRef<T | null>(null)
  const loading = ref(false)
  const error = ref<UvRequestError | null>(null)
  const settled = ref(false)
  const meta = shallowRef<UvMeta | null>(null)
  let generation = 0
  let controller: AbortController | null = null

  function cancel() {
    generation += 1
    controller?.abort()
    controller = null
    loading.value = false
  }

  async function run(): Promise<T | null> {
    const current = ++generation
    controller?.abort()
    controller = new AbortController()
    loading.value = true
    error.value = null
    try {
      const response = await loader(controller.signal)
      if (current !== generation) return null
      if (isUvResponse(response)) {
        meta.value = response.meta
        data.value = response.data as T
        settled.value = true
        return response.data as T
      }
      data.value = response as T
      settled.value = true
      return response as T
    } catch (caught) {
      if (current !== generation) return null
      if ((caught as { name?: string })?.name === 'CanceledError' || (caught as { name?: string })?.name === 'AbortError') {
        return null
      }
      error.value = normalizeError(caught)
      settled.value = true
      return null
    } finally {
      if (current === generation) loading.value = false
    }
  }

  function reset() {
    cancel()
    data.value = null
    error.value = null
    settled.value = false
    meta.value = null
  }

  const coverage = computed<UvCoverage>(() => meta.value?.coverage ?? 'no_data')

  if (options.watchSource) {
    watch(options.watchSource, () => { void run() }, { immediate: options.immediate ?? true })
  } else if (options.immediate) {
    void run()
  }

  onScopeDispose(() => {
    generation += 1
    controller?.abort()
    controller = null
  })

  return { data, loading, error, settled, meta, coverage, run, cancel, reset }
}

/** 命令类调用的状态（保存中 / 失败保留表单 / 幂等重试）。 */
export interface UvCommandState<T> {
  pending: Ref<boolean>
  error: Ref<UvRequestError | null>
  result: Ref<T | null>
  lastOperationId: Ref<string | null>
  execute: (operationId: string, run: () => Promise<T>) => Promise<T | null>
  clearError: () => void
}

export function useUvCommand<T>(): UvCommandState<T> {
  const pending = ref(false)
  const error = ref<UvRequestError | null>(null)
  const result = shallowRef<T | null>(null)
  const lastOperationId = ref<string | null>(null)
  let generation = 0

  async function execute(operationId: string, run: () => Promise<T>): Promise<T | null> {
    const current = ++generation
    pending.value = true
    error.value = null
    lastOperationId.value = operationId
    try {
      const value = await run()
      if (current !== generation) return null
      result.value = value
      return value
    } catch (caught) {
      if (current !== generation) return null
      error.value = normalizeError(caught)
      return null
    } finally {
      if (current === generation) pending.value = false
    }
  }

  return {
    pending,
    error,
    result,
    lastOperationId,
    execute,
    clearError: () => { error.value = null },
  }
}

export function newOperationId(): string {
  const globalCrypto = globalThis.crypto as Crypto | undefined
  if (globalCrypto?.randomUUID) return globalCrypto.randomUUID()
  if (globalCrypto?.getRandomValues) {
    const bytes = globalCrypto.getRandomValues(new Uint8Array(16))
    return [...bytes].map((byte) => byte.toString(16).padStart(2, '0')).join('')
  }
  return `uv-${Date.now()}-${Math.random().toString(16).slice(2)}`
}

/**
 * Keep an idempotency key while a command body is unchanged.  A timeout has
 * unknown server state, so retrying it must reuse the same key; any actual
 * form change gets a distinct key.
 */
export function operationForPayload(
  pending: { fingerprint: string; id: string } | null,
  fingerprint: string,
  create = newOperationId,
): { fingerprint: string; id: string } {
  return pending?.fingerprint === fingerprint ? pending : { fingerprint, id: create() }
}
