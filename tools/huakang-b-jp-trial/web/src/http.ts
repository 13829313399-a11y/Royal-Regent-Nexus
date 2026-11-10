import axios from 'axios'

// This client is local-only: no configurable remote URL, login session or ERP hooks.
// Let Axios/the browser set multipart boundaries for the original JP FormData calls.
export const http = axios.create({ baseURL: '/api', timeout: 15_000, withCredentials: false })

function payloadMessage(value: unknown): string | undefined {
  if (typeof value === 'string') return value.trim() && !value.trim().startsWith('<') ? value : undefined
  if (!value || typeof value !== 'object') return undefined
  const record = value as { message?: unknown; detail?: unknown; msg?: unknown; loc?: unknown }
  if (typeof record.message === 'string' && record.message.trim()) return record.message
  if (typeof record.msg === 'string' && record.msg.trim()) return record.msg === 'Field required' ? '必填项未填写' : record.msg
  if (Array.isArray(record.detail)) {
    const messages = record.detail.map(payloadMessage).filter(Boolean)
    return messages.length ? messages.join('；') : undefined
  }
  return payloadMessage(record.detail)
}

export function getApiErrorMessage(error: unknown): string {
  if (axios.isAxiosError(error)) {
    const message = payloadMessage(error.response?.data)
    if (message) return message
    if (error.code === 'ECONNABORTED' || error.code === 'ETIMEDOUT') {
      return '等待本地服务超时，结果尚未确认。请先查看历史导出记录，再决定是否重试。'
    }
    if (!error.response) return '无法连接本地试用服务，请确认启动窗口仍在运行，再重新加载。'
    if (error.response.status >= 500) return `本地服务未能返回结果，请先核对历史记录（HTTP ${error.response.status}）。`
    return `操作未完成，请检查输入后重试（HTTP ${error.response.status}）。`
  }
  return error instanceof Error && error.message ? error.message : '操作未完成，请检查输入或重新加载本地页面。'
}
