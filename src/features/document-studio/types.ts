export const DOCUMENT_TOOL_IDS = [
  'pdf-to-excel',
  'pdf-to-word',
  'word-to-pdf',
  'pdf-translation',
  'pdf-split',
] as const

export type DocumentToolId = typeof DOCUMENT_TOOL_IDS[number]
export type DocumentWorkspaceState =
  | 'IDLE'
  | 'FILE_SELECTED'
  | 'RUNNING'
  | 'SUCCESS'
  | 'ERROR'

export interface DocumentToolDefinition {
  id: DocumentToolId
  label: string
  description: string
  accept: string
  extensionLabel: string
}

export const MAX_DOCUMENT_FILE_BYTES = 20 * 1024 * 1024

export function isDocumentToolId(value: unknown): value is DocumentToolId {
  return typeof value === 'string'
    && DOCUMENT_TOOL_IDS.includes(value as DocumentToolId)
}

export function validateDocumentFile(file: File, tool: DocumentToolDefinition): string {
  if (file.size <= 0) return '请选择非空文档。'
  if (file.size > MAX_DOCUMENT_FILE_BYTES) return '单个文档不能超过 20 MB。'

  const extension = file.name.match(/\.[^.]+$/)?.[0].toLowerCase() ?? ''
  const acceptedExtensions = tool.accept
    .split(',')
    .map(item => item.trim().toLowerCase())
    .filter(item => item.startsWith('.'))
  if (!acceptedExtensions.includes(extension)) {
    return `当前工具仅支持 ${tool.extensionLabel} 文件。`
  }
  return ''
}
