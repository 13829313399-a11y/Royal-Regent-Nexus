import axios from 'axios'
import { http } from '@/lib/http'


export const PDF_TO_EXCEL_TIMEOUT_MS = 180_000
export const PDF_TO_WORD_TIMEOUT_MS = 180_000
export const PDF_SPLIT_TIMEOUT_MS = 60_000

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

export type PdfToWordMetrics = PdfToExcelMetrics

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

export interface SharedToolsHttpClient {
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
  try {
    const payload = JSON.parse(raw) as { detail?: unknown; message?: unknown }
    const message = typeof payload.detail === 'string'
      ? payload.detail
      : typeof payload.message === 'string' ? payload.message : ''
    throw new Error(message || error.message)
  }
  catch (parseError) {
    if (parseError instanceof SyntaxError) {
      throw new Error(raw.trim() || error.message)
    }
    throw parseError
  }
}

export function createSharedToolsApi(client: SharedToolsHttpClient = http) {
  return {
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
            textPageCount: headerCount(response.headers, 'x-pdf-text-page-count'),
            ocrPageCount: headerCount(response.headers, 'x-pdf-ocr-page-count'),
          },
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
