import axios from 'axios'
import { http } from '@/lib/http'

export const PDF_TO_EXCEL_TIMEOUT_MS = 900_000
export const PDF_TO_WORD_TIMEOUT_MS = 900_000
export const WORD_TO_PDF_TIMEOUT_MS = 300_000
export const PDF_TRANSLATION_TIMEOUT_MS = 1_800_000
export const PDF_SPLIT_TIMEOUT_MS = 300_000
export const DOCUMENT_TRANSLATION_TIMEOUT_MS = 1_800_000

export type DocumentProcessingMode = 'AUTO' | 'LOCAL'

export interface DocumentToolModeCapability {
  available: boolean
  reason_code: string
  reason: string
}

export interface DocumentToolCapability {
  available: boolean
  reason_code: string
  reason: string
  modes: Record<DocumentProcessingMode, DocumentToolModeCapability>
}

export interface DocumentToolsCapabilities {
  enabled: boolean
  default_mode: DocumentProcessingMode
  tools: Record<string, DocumentToolCapability>
  providers: {
    libreoffice: { available: boolean; version: string; reason_code: string }
    local_translation: { available: boolean }
  }
  limits: { max_file_bytes: number; max_pdf_pages: number; temp_ttl_minutes: number }
}

export interface DocumentProcessingMetadata {
  mode: DocumentProcessingMode
  localPageCount: number
  lowConfidenceCount: number
  warnings: string[]
}

export class DocumentToolApiError extends Error {
  constructor(
    message: string,
    readonly code = 'DOCUMENT_TOOL_FAILED',
    readonly action = '',
    readonly retryable = false,
  ) {
    super(message)
    this.name = 'DocumentToolApiError'
  }
}

export type DocumentTranslationDirection = 'zh_to_en' | 'en_to_zh'
export interface DocumentTranslationStatus {
  available: boolean
  engine: 'offline'
  engineLabel: string
  directions: Record<DocumentTranslationDirection, boolean>
  modes?: {
    local_private: { available: boolean; label: string }
  }
}

export interface DocumentTranslationResult {
  blob: Blob
  fileName: string
  translatedUnitCount: number
  skippedUnitCount: number
  processedPartCount: number
}

export interface PdfToExcelMetrics {
  pageCount: number
  tableCount: number
  textPageCount: number
  ocrPageCount: number
}

export interface PdfToExcelResult {
  blob: Blob
  fileName: string
  metrics: PdfToExcelMetrics
  processing: DocumentProcessingMetadata
}

export interface PdfToWordMetrics extends PdfToExcelMetrics {
  imageCount: number
}

export interface PdfToWordResult {
  blob: Blob
  fileName: string
  metrics: PdfToWordMetrics
  processing: DocumentProcessingMetadata
}

export interface PdfSplitOptions {
  mode: 'each_page' | 'ranges'
  pageRanges?: string
}

export interface PdfSplitResult {
  blob: Blob
  fileName: string
  pageCount: number
  fileCount: number
  processing: DocumentProcessingMetadata
}

export interface WordToPdfResult {
  blob: Blob
  fileName: string
  pageCount: number
  blankPageCount: number
  processing: DocumentProcessingMetadata
}

export interface PdfTranslationOptions {
  direction: 'AUTO' | 'ZH_TO_EN' | 'EN_TO_ZH'
  layout: 'TRANSLATED_ONLY' | 'SIDE_BY_SIDE' | 'STACKED'
  protectedTokens?: string[]
  includeEditableDocx?: boolean
  processingMode?: DocumentProcessingMode
  glossary?: Array<{ source: string; target: string }>
  translationMemory?: Array<{ source: string; target: string }>
  domainPrompt?: string
}

export interface PdfTranslationResult {
  blob: Blob
  fileName: string
  pageCount: number
  translatedUnitCount: number
  ocrPageCount: number
  processing: DocumentProcessingMetadata
}

export interface SharedToolsHttpClient {
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

function processingMetadata(
  headers: Record<string, unknown> | undefined,
  fallbackMode: DocumentProcessingMode,
): DocumentProcessingMetadata {
  let warnings: string[] = []
  const encoded = String(headers?.['x-document-warnings'] ?? '')
  if (encoded) {
    try {
      const parsed = JSON.parse(decodeURIComponent(encoded))
      if (Array.isArray(parsed)) warnings = parsed.filter(item => typeof item === 'string')
    }
    catch {
      warnings = []
    }
  }
  const headerMode = String(headers?.['x-processing-mode'] ?? fallbackMode).toUpperCase()
  const mode: DocumentProcessingMode = ['AUTO', 'LOCAL'].includes(headerMode)
    ? headerMode as DocumentProcessingMode
    : fallbackMode
  return {
    mode,
    localPageCount: headerCount(headers, 'x-local-page-count'),
    lowConfidenceCount: headerCount(headers, 'x-low-confidence-count'),
    warnings,
  }
}

async function parseBlobError(error: unknown): Promise<never> {
  if (axios.isCancel(error)) {
    throw new DocumentToolApiError(
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
    throw new DocumentToolApiError(message || error.message, code, action, retryable)
  }
  catch (parseError) {
    if (parseError instanceof SyntaxError) {
      if (status === 504) {
        throw new Error(
          '文档处理超过网关等待时间（最长 30 分钟），结果可能仍在后台生成。请勿立即重复提交，稍后重试或联系管理员。',
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

export function createSharedToolsApi(
  client: SharedToolsHttpClient = http,
) {
  return {
    async getCapabilities(signal?: AbortSignal): Promise<DocumentToolsCapabilities> {
      if (!client.get) throw new Error('当前 HTTP 客户端不支持读取工具能力。')
      const response = await client.get<DocumentToolsCapabilities>(
        '/tools/capabilities',
        signal ? { signal } : undefined,
      )
      return response.data
    },

    async getDocumentTranslationStatus(): Promise<DocumentTranslationStatus> {
      if (!client.get) throw new Error('当前 HTTP 客户端不支持读取翻译服务状态。')
      const response = await client.get<DocumentTranslationStatus>('/tools/document-translation/status')
      return response.data
    },

    async translateDocument(
      documentFile: File,
      direction: DocumentTranslationDirection,
      selectedSheetNames?: string[],
    ): Promise<DocumentTranslationResult> {
      const payload = new FormData()
      payload.append('document_file', documentFile)
      payload.append('direction', direction)
      payload.append('mode', 'local_private')
      if (selectedSheetNames) payload.append('sheet_names', JSON.stringify(selectedSheetNames))
      const extension = documentFile.name.match(/\.(xlsx|xlsm|docx)$/i)?.[0].toLowerCase() ?? '.docx'
      const stem = documentFile.name.replace(/\.(xlsx|xlsm|docx)$/i, '') || '文档'
      const directionLabel = direction === 'zh_to_en' ? '中译英' : '英译中'
      const fallbackFileName = `${stem}_${directionLabel}${extension}`

      try {
        const response = await client.post<Blob>('/tools/document-translation', payload, {
          headers: { 'Content-Type': 'multipart/form-data' },
          responseType: 'blob',
          timeout: DOCUMENT_TRANSLATION_TIMEOUT_MS,
        })
        return {
          blob: response.data,
          fileName: responseFileName(response.headers, fallbackFileName),
          translatedUnitCount: headerCount(response.headers, 'x-translation-unit-count'),
          skippedUnitCount: headerCount(response.headers, 'x-translation-skipped-count'),
          processedPartCount: headerCount(response.headers, 'x-translation-part-count'),
        }
      }
      catch (error) {
        return parseBlobError(error)
      }
    },

    async convertPdfToExcel(
      pdfFile: File,
      processingMode: DocumentProcessingMode = 'AUTO',
      signal?: AbortSignal,
    ): Promise<PdfToExcelResult> {
      const payload = new FormData()
      payload.append('pdf_file', pdfFile)
      payload.append('processing_mode', processingMode)
      const fallbackFileName = `${pdfFile.name.replace(/\.pdf$/i, '') || 'PDF文件'}_转换结果.xlsx`

      try {
        const response = await client.post<Blob>('/tools/pdf-to-excel', payload, {
          headers: { 'Content-Type': 'multipart/form-data' },
          responseType: 'blob',
          timeout: PDF_TO_EXCEL_TIMEOUT_MS,
          signal,
        })
        return {
          blob: response.data,
          fileName: responseFileName(response.headers, fallbackFileName),
          metrics: {
            pageCount: headerCount(response.headers, 'x-pdf-page-count'),
            tableCount: headerCount(response.headers, 'x-pdf-table-count'),
            textPageCount: headerCount(response.headers, 'x-pdf-text-page-count'),
            ocrPageCount: headerCount(response.headers, 'x-pdf-ocr-page-count'),
          },
          processing: processingMetadata(response.headers, processingMode),
        }
      }
      catch (error) {
        return parseBlobError(error)
      }
    },

    async convertPdfToWord(
      pdfFile: File,
      processingMode: DocumentProcessingMode = 'AUTO',
      signal?: AbortSignal,
      outputMode: 'EDITABLE' | 'LAYOUT_PRESERVING' = 'EDITABLE',
    ): Promise<PdfToWordResult> {
      const payload = new FormData()
      payload.append('pdf_file', pdfFile)
      payload.append('processing_mode', processingMode)
      payload.append('output_mode', outputMode)
      const fallbackFileName = `${pdfFile.name.replace(/\.pdf$/i, '') || 'PDF文件'}_转换结果.docx`

      try {
        const response = await client.post<Blob>('/tools/pdf-to-word', payload, {
          headers: { 'Content-Type': 'multipart/form-data' },
          responseType: 'blob',
          timeout: PDF_TO_WORD_TIMEOUT_MS,
          signal,
        })
        return {
          blob: response.data,
          fileName: responseFileName(response.headers, fallbackFileName),
          metrics: {
            pageCount: headerCount(response.headers, 'x-pdf-page-count'),
            tableCount: headerCount(response.headers, 'x-pdf-table-count'),
            imageCount: headerCount(response.headers, 'x-pdf-image-count'),
            textPageCount: headerCount(response.headers, 'x-pdf-text-page-count'),
            ocrPageCount: headerCount(response.headers, 'x-pdf-ocr-page-count'),
          },
          processing: processingMetadata(response.headers, processingMode),
        }
      }
      catch (error) {
        return parseBlobError(error)
      }
    },

    async convertWordToPdf(documentFile: File, signal?: AbortSignal): Promise<WordToPdfResult> {
      const payload = new FormData()
      payload.append('document_file', documentFile)
      payload.append('processing_mode', 'AUTO')
      const fallbackFileName = `${documentFile.name.replace(/\.docx$/i, '') || 'Word文档'}_转换结果.pdf`

      try {
        const response = await client.post<Blob>('/tools/word-to-pdf', payload, {
          headers: { 'Content-Type': 'multipart/form-data' },
          responseType: 'blob',
          timeout: WORD_TO_PDF_TIMEOUT_MS,
          signal,
        })
        return {
          blob: response.data,
          fileName: responseFileName(response.headers, fallbackFileName),
          pageCount: headerCount(response.headers, 'x-word-page-count'),
          blankPageCount: headerCount(response.headers, 'x-word-blank-page-count'),
          processing: processingMetadata(response.headers, 'AUTO'),
        }
      }
      catch (error) {
        return parseBlobError(error)
      }
    },

    async translatePdf(
      pdfFile: File,
      options: PdfTranslationOptions,
      signal?: AbortSignal,
    ): Promise<PdfTranslationResult> {
      const payload = new FormData()
      payload.append('pdf_file', pdfFile)
      payload.append('direction', options.direction)
      payload.append('layout', options.layout)
      payload.append('protected_tokens', JSON.stringify(options.protectedTokens ?? []))
      payload.append('include_editable_docx', String(options.includeEditableDocx ?? false))
      const processingMode = options.processingMode ?? 'AUTO'
      payload.append('processing_mode', processingMode)
      payload.append('glossary_json', JSON.stringify(options.glossary ?? []))
      payload.append('translation_memory_json', JSON.stringify(options.translationMemory ?? []))
      payload.append('domain_prompt', options.domainPrompt?.trim() ?? '')
      const suffix = options.includeEditableDocx ? '.zip' : '.pdf'
      const fallbackFileName = `${pdfFile.name.replace(/\.pdf$/i, '') || 'PDF文件'}_translated${suffix}`

      try {
        const response = await client.post<Blob>('/tools/pdf-translation', payload, {
          headers: { 'Content-Type': 'multipart/form-data' },
          responseType: 'blob',
          timeout: PDF_TRANSLATION_TIMEOUT_MS,
          signal,
        })
        return {
          blob: response.data,
          fileName: responseFileName(response.headers, fallbackFileName),
          pageCount: headerCount(response.headers, 'x-pdf-page-count'),
          translatedUnitCount: headerCount(response.headers, 'x-translation-unit-count'),
          ocrPageCount: headerCount(response.headers, 'x-pdf-ocr-page-count'),
          processing: processingMetadata(response.headers, processingMode),
        }
      }
      catch (error) {
        return parseBlobError(error)
      }
    },

    async splitPdf(
      pdfFile: File,
      options: PdfSplitOptions,
      signal?: AbortSignal,
    ): Promise<PdfSplitResult> {
      const payload = new FormData()
      payload.append('pdf_file', pdfFile)
      payload.append('split_mode', options.mode)
      payload.append('page_ranges', options.pageRanges?.trim() ?? '')
      payload.append('processing_mode', 'AUTO')
      const fallbackFileName = `${pdfFile.name.replace(/\.pdf$/i, '') || 'PDF文件'}_拆分结果.zip`

      try {
        const response = await client.post<Blob>('/tools/pdf-split', payload, {
          headers: { 'Content-Type': 'multipart/form-data' },
          responseType: 'blob',
          timeout: PDF_SPLIT_TIMEOUT_MS,
          signal,
        })
        return {
          blob: response.data,
          fileName: responseFileName(response.headers, fallbackFileName),
          pageCount: headerCount(response.headers, 'x-pdf-page-count'),
          fileCount: headerCount(response.headers, 'x-pdf-split-file-count'),
          processing: processingMetadata(response.headers, 'AUTO'),
        }
      }
      catch (error) {
        return parseBlobError(error)
      }
    },
  }
}

export const sharedToolsApi = createSharedToolsApi()
