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

http.interceptors.request.use((config) => {
  if (/^\/internal-quotes(?:\/|$)/.test(config.url ?? '') && config.timeout === 15000) {
    config.timeout = 120_000
  }
  return config
})

http.interceptors.response.use(
  (response) => response,
  (error: AxiosError<ApiErrorPayload>) => {
    if (error.response?.status === 401) {
      unauthorizedHandler?.(error)
    }
    if (error.response?.status === 403) {
      forbiddenHandler?.(error)
    }

    return Promise.reject(error)
  },
)

export function getApiErrorMessage(error: unknown) {
  if (axios.isAxiosError<ApiErrorPayload>(error)) {
    const reason = extractApiErrorPayloadMessage(error.response?.data)
    if (reason) return reason
    if (error.code === 'ECONNABORTED' || error.code === 'ETIMEDOUT') {
      return '请求超时，未能确认操作结果；请先刷新台账或历史记录核对，再决定是否重试'
    }
    if (!error.response && (error.code === 'ERR_NETWORK' || error.message === 'Network Error')) {
      return '无法连接服务器，请检查网络或确认后端服务是否可用'
    }
    const status = error.response?.status
    if (status) {
      const reasons: Record<number, string> = {
        400: '提交的信息有误，请检查填写内容',
        401: '登录已失效，请重新登录后再操作',
        403: '当前账号没有此操作的权限，请核对厂区和权限',
        404: '所请求的记录或接口不存在，请刷新后重试',
        408: '服务器等待请求超时，请先核对操作结果再重试',
        409: '记录状态已变化或存在重复数据，请刷新后核对',
        413: '上传文件过大，请缩小文件后重试',
        422: '提交的数据未通过校验，请检查必填项和数据格式',
        429: '操作过于频繁，请稍后重试',
        502: '后台服务连接异常，请稍后刷新并核对操作结果',
        503: '后台服务暂时不可用，请稍后重试',
        504: '后台服务响应超时，请先核对操作结果再重试',
      }
      return `${reasons[status] ?? (status >= 500 ? '服务器处理异常，请稍后刷新并核对操作结果' : '请求未完成，请刷新后重试')}（HTTP ${status}）`
    }
    return error.message || '请求未完成，服务器没有返回具体原因'
  }

  if (error instanceof Error && error.message.trim()) {
    return error.message
  }

  if (typeof error === 'string' && error.trim()) return error
  return '操作未完成，未取得具体原因；请刷新后核对或联系管理员'
}

export async function getApiErrorMessageAsync(error: unknown) {
  if (axios.isAxiosError<ApiErrorPayload | Blob>(error) && error.response?.data instanceof Blob) {
    try {
      const rawPayload = await error.response.data.text()
      if (rawPayload) {
        const payload = JSON.parse(rawPayload) as ApiErrorPayload
        const message = extractApiErrorPayloadMessage(payload)
        if (message) return message
      }
    } catch {
      // Fall through to the ordinary Axios message when a download error body
      // is empty or is not JSON.
    }
  }

  return getApiErrorMessage(error)
}

function extractApiErrorPayloadMessage(payload: unknown) {
  if (typeof payload === 'string') return payload.trim() && !payload.trim().startsWith('<') ? payload : undefined
  if (!payload || typeof payload !== 'object') {
    return undefined
  }

  const record = payload as ApiErrorPayload
  if (typeof record.message === 'string' && record.message.trim()) {
    return record.message
  }

  return formatApiDetail(record.detail)
}

const validationFieldNames: Record<string, string> = {
  factory_id: '厂区', customer_code: '客户', contract_no: '合同号', item_no: '货号', customer_po: '客户 PO',
  file: '导入文件', reason: '原因', expected_revision: '记录版本', lines: '明细', items: '项目',
  product_order_quantity: '产品订单数量', quantity: '数量', required_quantity: '需求量', usage_quantity: '每箱个数',
  delivered_quantity: '送货数量', received_quantity: '实收数量', unit_price: '单价',
  order_date: '下单日期', due_date: '计划交期', customer_due_date: '客户交期', delivery_date: '送货日期', acceptance_date: '验收日期',
  packaging_type: '纸品类型', paper_quality: '纸质', specification: '规格', unit: '单位', location_id: '仓位',
}

function validationMessage(entry: { msg?: unknown; loc?: unknown }): string {
  if (typeof entry.msg !== 'string') return ''
  let message = entry.msg
  if (message === 'Field required') message = '必填项未填写'
  else if (message === 'Extra inputs are not permitted') message = '包含不支持的字段'
  else message = message.replace(/^Input should be greater than or equal to (.+)$/, '必须大于或等于 $1')
    .replace(/^Input should be greater than (.+)$/, '必须大于 $1')
    .replace(/^String should have at least (\d+) characters$/, '至少填写 $1 个字符')
  const location = Array.isArray(entry.loc) ? entry.loc
    .filter(part => !['body', 'query', 'path', 'header', 'cookie'].includes(String(part)))
    .map(part => typeof part === 'number' ? `第 ${part + 1} 行` : validationFieldNames[String(part)] ?? String(part))
    .join(' · ') : ''
  return location ? `${location}：${message}` : message
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
          return validationMessage(entry as { msg?: unknown; loc?: unknown })
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
