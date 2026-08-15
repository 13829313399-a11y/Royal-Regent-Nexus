import axios from 'axios'
import { http } from '@/lib/http'
import {
  isArtifactWorkflowUnavailable,
  uploadAIArtifact,
} from '@/api/aiArtifacts'


export const PDF_TO_EXCEL_TIMEOUT_MS = 900_000
export const PDF_TO_WORD_TIMEOUT_MS = 900_000
export const WORD_TO_PDF_TIMEOUT_MS = 300_000
export const PDF_TRANSLATION_TIMEOUT_MS = 1_800_000
export const PDF_SPLIT_TIMEOUT_MS = 300_000
export const DOCUMENT_TRANSLATION_TIMEOUT_MS = 1_800_000

export type DocumentTranslationDirection = 'zh_to_en' | 'en_to_zh'
export type DocumentTranslationMode = 'local_private' | 'ai_smart_cloud'

export interface DocumentTranslationStatus {
  available: boolean
  engine: 'offline'
  engineLabel: string
  directions: Record<DocumentTranslationDirection, boolean>
  cloudAvailable?: boolean
  artifactWorkflowsEnabled?: boolean
  modes?: {
    local_private: { available: boolean; label: string }
    ai_smart_cloud: { available: boolean; label: string; provider: string; model: string }
  }
}

export interface DocumentTranslationResult {
  blob: Blob
  fileName: string
  translatedUnitCount: number
  skippedUnitCount: number
  processedPartCount: number
  sourceArtifactId?: string
  derivedArtifactId?: string
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
}

export interface PdfToWordMetrics extends PdfToExcelMetrics {
  imageCount: number
}

export interface PdfToWordResult {
  blob: Blob
  fileName: string
  metrics: PdfToWordMetrics
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
}

export interface WordToPdfResult {
  blob: Blob
  fileName: string
  pageCount: number
  blankPageCount: number
}

export interface PdfTranslationOptions {
  direction: 'AUTO' | 'ZH_TO_EN' | 'EN_TO_ZH'
  layout: 'TRANSLATED_ONLY' | 'SIDE_BY_SIDE' | 'STACKED'
  protectedTokens?: string[]
  includeEditableDocx?: boolean
}

export interface PdfTranslationResult {
  blob: Blob
  fileName: string
  pageCount: number
  translatedUnitCount: number
  ocrPageCount: number
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

async function parseBlobError(error: unknown): Promise<never> {
  if (!axios.isAxiosError(error) || !(error.response?.data instanceof Blob)) {
    throw error
  }

  const raw = await error.response.data.text()
  const status = error.response.status
  try {
    const payload = JSON.parse(raw) as { detail?: unknown; message?: unknown }
    const message = typeof payload.detail === 'string'
      ? payload.detail
      : typeof payload.message === 'string' ? payload.message : ''
    throw new Error(message || error.message)
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
  artifactUploader = uploadAIArtifact,
) {
  return {
    async getDocumentTranslationStatus(): Promise<DocumentTranslationStatus> {
      if (!client.get) throw new Error('当前 HTTP 客户端不支持读取翻译服务状态。')
      const response = await client.get<DocumentTranslationStatus>('/tools/document-translation/status')
      return response.data
    },

    async translateDocument(
      documentFile: File,
      direction: DocumentTranslationDirection,
      selectedSheetNames?: string[],
      mode: DocumentTranslationMode = 'local_private',
      cloudConsent = false,
      factoryId = '',
      artifactWorkflowEnabled = false,
    ): Promise<DocumentTranslationResult> {
      const payload = new FormData()
      payload.append('document_file', documentFile)
      payload.append('direction', direction)
      payload.append('mode', mode)
      if (mode === 'ai_smart_cloud') payload.append('cloud_consent', String(cloudConsent))
      if (selectedSheetNames) payload.append('sheet_names', JSON.stringify(selectedSheetNames))
      const extension = documentFile.name.match(/\.(xlsx|xlsm|docx)$/i)?.[0].toLowerCase() ?? '.docx'
      const stem = documentFile.name.replace(/\.(xlsx|xlsm|docx)$/i, '') || '文档'
      const directionLabel = direction === 'zh_to_en' ? '中译英' : '英译中'
      const fallbackFileName = `${stem}_${directionLabel}${extension}`

      try {
        if (
          artifactWorkflowEnabled
          && factoryId
          && /\.(xlsx|docx)$/i.test(documentFile.name)
        ) {
          try {
            const source = await artifactUploader(
              documentFile,
              factoryId,
              'CONFIDENTIAL_BUSINESS',
            )
            const artifactPayload = new FormData()
            artifactPayload.append('artifact_id', source.id)
            artifactPayload.append('direction', direction)
            artifactPayload.append('mode', mode)
            if (selectedSheetNames) {
              artifactPayload.append('sheet_names', JSON.stringify(selectedSheetNames))
            }
            if (mode === 'ai_smart_cloud') {
              artifactPayload.append('cloud_consent_json', JSON.stringify({
                accepted: true,
                notice_version: source.content_class === 'WORKBOOK'
                  ? 'aliyun-cn-beijing-workbook-v1'
                  : 'aliyun-cn-beijing-document-v1',
                provider: 'qwen',
                region: 'cn-beijing',
                classification: source.classification,
                content_class: source.content_class,
                artifact_ids: [source.id],
              }))
            }
            const artifactResponse = await client.post<Blob>(
              '/tools/document-translation/artifact',
              artifactPayload,
              {
                headers: { 'Content-Type': 'multipart/form-data' },
                responseType: 'blob',
                timeout: DOCUMENT_TRANSLATION_TIMEOUT_MS,
              },
            )
            return {
              blob: artifactResponse.data,
              fileName: responseFileName(artifactResponse.headers, fallbackFileName),
              translatedUnitCount: headerCount(artifactResponse.headers, 'x-translation-unit-count'),
              skippedUnitCount: headerCount(artifactResponse.headers, 'x-translation-skipped-count'),
              processedPartCount: headerCount(artifactResponse.headers, 'x-translation-part-count'),
              sourceArtifactId: String(artifactResponse.headers?.['x-source-artifact-id'] ?? ''),
              derivedArtifactId: String(artifactResponse.headers?.['x-derived-artifact-id'] ?? ''),
            }
          }
          catch (error) {
            if (!isArtifactWorkflowUnavailable(error)) throw error
          }
        }
        if (factoryId) payload.append('factory_id', factoryId)
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

    async convertPdfToExcel(pdfFile: File): Promise<PdfToExcelResult> {
      const payload = new FormData()
      payload.append('pdf_file', pdfFile)
      const fallbackFileName = `${pdfFile.name.replace(/\.pdf$/i, '') || 'PDF文件'}_转换结果.xlsx`

      try {
        const response = await client.post<Blob>('/tools/pdf-to-excel', payload, {
          headers: { 'Content-Type': 'multipart/form-data' },
          responseType: 'blob',
          timeout: PDF_TO_EXCEL_TIMEOUT_MS,
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
        }
      }
      catch (error) {
        return parseBlobError(error)
      }
    },

    async convertPdfToWord(pdfFile: File): Promise<PdfToWordResult> {
      const payload = new FormData()
      payload.append('pdf_file', pdfFile)
      const fallbackFileName = `${pdfFile.name.replace(/\.pdf$/i, '') || 'PDF文件'}_转换结果.docx`

      try {
        const response = await client.post<Blob>('/tools/pdf-to-word', payload, {
          headers: { 'Content-Type': 'multipart/form-data' },
          responseType: 'blob',
          timeout: PDF_TO_WORD_TIMEOUT_MS,
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
        }
      }
      catch (error) {
        return parseBlobError(error)
      }
    },

    async convertWordToPdf(documentFile: File): Promise<WordToPdfResult> {
      const payload = new FormData()
      payload.append('document_file', documentFile)
      const fallbackFileName = `${documentFile.name.replace(/\.docx$/i, '') || 'Word文档'}_转换结果.pdf`

      try {
        const response = await client.post<Blob>('/tools/word-to-pdf', payload, {
          headers: { 'Content-Type': 'multipart/form-data' },
          responseType: 'blob',
          timeout: WORD_TO_PDF_TIMEOUT_MS,
        })
        return {
          blob: response.data,
          fileName: responseFileName(response.headers, fallbackFileName),
          pageCount: headerCount(response.headers, 'x-word-page-count'),
          blankPageCount: headerCount(response.headers, 'x-word-blank-page-count'),
        }
      }
      catch (error) {
        return parseBlobError(error)
      }
    },

    async translatePdf(
      pdfFile: File,
      options: PdfTranslationOptions,
    ): Promise<PdfTranslationResult> {
      const payload = new FormData()
      payload.append('pdf_file', pdfFile)
      payload.append('direction', options.direction)
      payload.append('layout', options.layout)
      payload.append('protected_tokens', JSON.stringify(options.protectedTokens ?? []))
      payload.append('include_editable_docx', String(options.includeEditableDocx ?? false))
      const suffix = options.includeEditableDocx ? '.zip' : '.pdf'
      const fallbackFileName = `${pdfFile.name.replace(/\.pdf$/i, '') || 'PDF文件'}_translated${suffix}`

      try {
        const response = await client.post<Blob>('/tools/pdf-translation', payload, {
          headers: { 'Content-Type': 'multipart/form-data' },
          responseType: 'blob',
          timeout: PDF_TRANSLATION_TIMEOUT_MS,
        })
        return {
          blob: response.data,
          fileName: responseFileName(response.headers, fallbackFileName),
          pageCount: headerCount(response.headers, 'x-pdf-page-count'),
          translatedUnitCount: headerCount(response.headers, 'x-translation-unit-count'),
          ocrPageCount: headerCount(response.headers, 'x-pdf-ocr-page-count'),
        }
      }
      catch (error) {
        return parseBlobError(error)
      }
    },

    async splitPdf(pdfFile: File, options: PdfSplitOptions): Promise<PdfSplitResult> {
      const payload = new FormData()
      payload.append('pdf_file', pdfFile)
      payload.append('split_mode', options.mode)
      payload.append('page_ranges', options.pageRanges?.trim() ?? '')
      const fallbackFileName = `${pdfFile.name.replace(/\.pdf$/i, '') || 'PDF文件'}_拆分结果.zip`

      try {
        const response = await client.post<Blob>('/tools/pdf-split', payload, {
          headers: { 'Content-Type': 'multipart/form-data' },
          responseType: 'blob',
          timeout: PDF_SPLIT_TIMEOUT_MS,
        })
        return {
          blob: response.data,
          fileName: responseFileName(response.headers, fallbackFileName),
          pageCount: headerCount(response.headers, 'x-pdf-page-count'),
          fileCount: headerCount(response.headers, 'x-pdf-split-file-count'),
        }
      }
      catch (error) {
        return parseBlobError(error)
      }
    },
  }
}

export const sharedToolsApi = createSharedToolsApi()
