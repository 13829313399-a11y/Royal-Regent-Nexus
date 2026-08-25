import { ref } from 'vue'
import {
  sharedToolsApi,
  type DocumentProcessingMetadata,
  type DocumentProcessingMode,
} from '@/api/tools'
import type { DocumentToolId } from '../types'

export interface DocumentToolRunInput {
  toolId: DocumentToolId
  file: File
  processingMode: DocumentProcessingMode
  splitMode: 'each_page' | 'ranges'
  pageRanges: string
  translationDirection: 'AUTO' | 'ZH_TO_EN' | 'EN_TO_ZH'
  translationLayout: 'TRANSLATED_ONLY' | 'SIDE_BY_SIDE' | 'STACKED'
  protectedTokens: string[]
  includeEditableDocx: boolean
  wordOutputMode: 'EDITABLE' | 'LAYOUT_PRESERVING'
  glossary: Array<{ source: string; target: string }>
  translationMemory: Array<{ source: string; target: string }>
  domainPrompt: string
}

export interface DocumentToolRunResult {
  blob: Blob
  fileName: string
  summary: string[]
  processing: DocumentProcessingMetadata
}

function processingSummary(metadata: DocumentProcessingMetadata) {
  const summary: string[] = []
  if (metadata.qwenPageCount) summary.push(`${metadata.qwenPageCount} 页千问 OCR`)
  if (metadata.lowConfidenceCount) summary.push(`${metadata.lowConfidenceCount} 个低置信结果已标记`)
  if (metadata.providerModel) summary.push(metadata.providerModel)
  return summary
}

export function useDocumentToolRunner() {
  const running = ref(false)
  let controller: AbortController | null = null

  async function run(input: DocumentToolRunInput): Promise<DocumentToolRunResult> {
    controller?.abort()
    controller = new AbortController()
    running.value = true
    try {
      if (input.toolId === 'pdf-to-excel') {
        const result = await sharedToolsApi.convertPdfToExcel(
          input.file,
          input.processingMode,
          controller.signal,
        )
        return {
          blob: result.blob,
          fileName: result.fileName,
          processing: result.processing,
          summary: [
            `${result.metrics.pageCount} 页`,
            `${result.metrics.tableCount} 个表格`,
            ...processingSummary(result.processing),
          ],
        }
      }
      if (input.toolId === 'pdf-to-word') {
        const result = await sharedToolsApi.convertPdfToWord(
          input.file,
          input.processingMode,
          controller.signal,
          input.wordOutputMode,
        )
        return {
          blob: result.blob,
          fileName: result.fileName,
          processing: result.processing,
          summary: [
            `${result.metrics.pageCount} 页`,
            `${result.metrics.imageCount} 张图片`,
            ...processingSummary(result.processing),
          ],
        }
      }
      if (input.toolId === 'word-to-pdf') {
        const result = await sharedToolsApi.convertWordToPdf(input.file, controller.signal)
        return {
          blob: result.blob,
          fileName: result.fileName,
          processing: result.processing,
          summary: [
            `${result.pageCount} 页`,
            result.blankPageCount ? `${result.blankPageCount} 个空白页` : '未发现空白页',
          ],
        }
      }
      if (input.toolId === 'pdf-translation') {
        const result = await sharedToolsApi.translatePdf(input.file, {
          direction: input.translationDirection,
          layout: input.translationLayout,
          protectedTokens: input.protectedTokens,
          includeEditableDocx: input.includeEditableDocx,
          processingMode: input.processingMode,
          glossary: input.glossary,
          translationMemory: input.translationMemory,
          domainPrompt: input.domainPrompt,
        }, controller.signal)
        return {
          blob: result.blob,
          fileName: result.fileName,
          processing: result.processing,
          summary: [
            `${result.pageCount} 页`,
            `${result.translatedUnitCount} 个翻译单元`,
            ...processingSummary(result.processing),
          ],
        }
      }
      const result = await sharedToolsApi.splitPdf(input.file, {
        mode: input.splitMode,
        pageRanges: input.pageRanges,
      }, controller.signal)
      return {
        blob: result.blob,
        fileName: result.fileName,
        processing: result.processing,
        summary: [`${result.pageCount} 页`, `${result.fileCount} 个输出文件`],
      }
    }
    finally {
      controller = null
      running.value = false
    }
  }

  function cancel() {
    controller?.abort()
  }

  return { cancel, run, running }
}
