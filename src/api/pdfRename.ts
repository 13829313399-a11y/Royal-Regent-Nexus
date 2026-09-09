import axios from 'axios'
import { http } from '@/lib/http'

export const PDF_BATCH_RENAME_TIMEOUT_MS = 900_000

export class PdfRenameApiError extends Error {
  constructor(
    message: string,
    readonly code = 'DOCUMENT_TOOL_FAILED',
    readonly action = '',
    readonly retryable = false,
  ) {
    super(message)
    this.name = 'PdfRenameApiError'
  }
}

export interface PdfRenameRegionDefinition {
  key: string
  label: string
  page_number: number
  bbox: [number, number, number, number]
  required: boolean
  language: string
}

export interface PdfRenameRuleDefinition {
  id: string
  label: string
  description: string
  version: string
  status: 'active' | 'draft'
  available: boolean
  regions: PdfRenameRegionDefinition[]
  setup_checklist: string[]
  factory_ids: string[]
}

export interface PdfRenameRuleCatalog {
  rules: PdfRenameRuleDefinition[]
  limits: {
    max_files: number
    max_batch_bytes: number
    max_file_bytes: number
  }
}

export interface PdfRenamePreviewField {
  key: string
  label: string
  raw_text: string
  normalized_text: string
  route: 'NATIVE_TEXT' | 'LOCAL_OCR'
  confidence: number | null
}

export interface PdfRenamePreviewItem {
  source_file_name: string
  target_file_name: string
  interval_name: string
  status: 'READY' | 'REVIEW' | 'ERROR'
  fields: PdfRenamePreviewField[]
  issues: Array<{ code: string; message: string }>
  manual_override?: boolean
  manual_override_allowed?: boolean
}

export interface PdfRenameManualOverride {
  source_index: number
  target_file_name: string
  confirmed: boolean
}

export interface PdfRenamePreviewResult {
  rule: PdfRenameRuleDefinition
  items: PdfRenamePreviewItem[]
  preview_token: string
  summary: { total: number; ready: number; review: number; error: number }
}

export interface PdfRenameExecuteResult {
  blob: Blob
  fileName: string
  fileCount: number
}

export interface PdfRenameHttpClient {
  get?<T = unknown>(
    url: string,
    config?: unknown,
  ): Promise<{ data: T; headers?: Record<string, unknown> }>
  post<T = unknown>(
    url: string,
    data?: unknown,
    config?: unknown,
  ): Promise<{ data: T; headers?: Record<string, unknown> }>
}

function responseFileName(headers: Record<string, unknown> | undefined, fallback: string) {
  const disposition = String(headers?.['content-disposition'] ?? '')
  const encoded = disposition.match(/filename\*=UTF-8''([^;]+)/i)?.[1]
  if (!encoded) return fallback
  try {
    return decodeURIComponent(encoded)
  }
  catch {
    return fallback
  }
}

function headerCount(headers: Record<string, unknown> | undefined, name: string) {
  const value = Number(headers?.[name] ?? 0)
  return Number.isFinite(value) && value >= 0 ? value : 0
}

async function parseBlobError(error: unknown): Promise<never> {
  if (axios.isCancel(error)) {
    throw new PdfRenameApiError(
      '本次处理已取消。',
      'DOCUMENT_REQUEST_CANCELLED',
      '可调整设置后重新处理。',
    )
  }
  if (!axios.isAxiosError(error) || !(error.response?.data instanceof Blob)) {
    throw error
  }

  const raw = await error.response.data.text()
  const status = error.response.status
  try {
    const payload = JSON.parse(raw) as {
      detail?: unknown
      message?: unknown
      code?: unknown
      action?: unknown
      retryable?: unknown
    }
    const detail = payload.detail && typeof payload.detail === 'object'
      ? payload.detail as Record<string, unknown>
      : null
    const message = typeof payload.detail === 'string'
      ? payload.detail
      : typeof detail?.message === 'string'
        ? detail.message
        : typeof payload.message === 'string' ? payload.message : ''
    const code = typeof detail?.code === 'string'
      ? detail.code
      : typeof payload.code === 'string' ? payload.code : 'DOCUMENT_TOOL_FAILED'
    const action = typeof detail?.action === 'string'
      ? detail.action
      : typeof payload.action === 'string' ? payload.action : ''
    const retryable = detail?.retryable === true || payload.retryable === true
    throw new PdfRenameApiError(message || error.message, code, action, retryable)
  }
  catch (parseError) {
    if (parseError instanceof SyntaxError) {
      if (status === 504) {
        throw new Error(
          '文档处理超过网关等待时间（最长 15 分钟），结果可能仍在后台生成。请勿立即重复提交，稍后重试或联系管理员。',
        )
      }
      const contentType = String(error.response.headers?.['content-type'] ?? '')
      const looksLikeHtml = contentType.includes('text/html') || /^\s*</.test(raw)
      if (looksLikeHtml) {
        throw new Error('服务器暂时无法完成文档处理，请稍后重试。')
      }
      throw new Error(raw.trim() || error.message)
    }
    throw parseError
  }
}

function parseJsonApiError(error: unknown): never {
  if (axios.isCancel(error)) {
    throw new PdfRenameApiError(
      '本次处理已取消。',
      'DOCUMENT_REQUEST_CANCELLED',
      '可调整文件或规则后重新处理。',
    )
  }
  if (axios.isAxiosError(error)) {
    const payload = error.response?.data as { detail?: unknown } | undefined
    const detail = payload?.detail && typeof payload.detail === 'object'
      ? payload.detail as Record<string, unknown>
      : null
    if (detail) {
      throw new PdfRenameApiError(
        typeof detail.message === 'string' ? detail.message : error.message,
        typeof detail.code === 'string' ? detail.code : 'DOCUMENT_TOOL_FAILED',
        typeof detail.action === 'string' ? detail.action : '',
        detail.retryable === true,
      )
    }
  }
  throw error
}

export function createPdfRenameApi(client: PdfRenameHttpClient = http) {
  return {
    async getPdfRenameRules(factoryId: string, signal?: AbortSignal): Promise<PdfRenameRuleCatalog> {
      if (!client.get) throw new Error('当前 HTTP 客户端不支持读取批量改名规则。')
      try {
        const response = await client.get<PdfRenameRuleCatalog>(
          '/tools/pdf-rename/rules', { params: { factory_id: factoryId }, signal },
        )
        return response.data
      } catch (error) { return parseJsonApiError(error) }
    },

    async previewPdfRename(
      pdfFiles: File[],
      ruleId: string,
      factoryId: string,
      signal?: AbortSignal,
      manualOverrides: PdfRenameManualOverride[] = [],
    ): Promise<PdfRenamePreviewResult> {
      const payload = new FormData()
      pdfFiles.forEach(file => payload.append('pdf_files', file))
      payload.append('rule_id', ruleId)
      payload.append('factory_id', factoryId)
      payload.append('manual_overrides', JSON.stringify(manualOverrides))
      try {
        const response = await client.post<PdfRenamePreviewResult>('/tools/pdf-rename/preview', payload, {
          headers: { 'Content-Type': 'multipart/form-data' },
          timeout: PDF_BATCH_RENAME_TIMEOUT_MS,
          signal,
        })
        return response.data
      }
      catch (error) {
        return parseJsonApiError(error)
      }
    },

    async executePdfRename(
      pdfFiles: File[],
      ruleId: string,
      previewToken: string,
      ocrReviewConfirmed: boolean,
      factoryId: string,
      signal?: AbortSignal,
      manualOverrides: PdfRenameManualOverride[] = [],
    ): Promise<PdfRenameExecuteResult> {
      const payload = new FormData()
      pdfFiles.forEach(file => payload.append('pdf_files', file))
      payload.append('rule_id', ruleId)
      payload.append('preview_token', previewToken)
      payload.append('ocr_review_confirmed', String(ocrReviewConfirmed))
      payload.append('factory_id', factoryId)
      payload.append('manual_overrides', JSON.stringify(manualOverrides))
      try {
        const response = await client.post<Blob>('/tools/pdf-rename/execute', payload, {
          headers: { 'Content-Type': 'multipart/form-data' },
          responseType: 'blob',
          timeout: PDF_BATCH_RENAME_TIMEOUT_MS,
          signal,
        })
        return {
          blob: response.data,
          fileName: responseFileName(response.headers, 'PDF批量改名结果.zip'),
          fileCount: headerCount(response.headers, 'x-pdf-rename-file-count'),
        }
      }
      catch (error) {
        return parseBlobError(error)
      }
    },

  }
}

export const pdfRenameApi = createPdfRenameApi()
