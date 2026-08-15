import type { DocumentToolDefinition } from './types'

export const DOCUMENT_TOOLS: readonly DocumentToolDefinition[] = [
  {
    id: 'pdf-to-excel',
    label: 'PDF 转 Excel',
    description: '提取表格并生成可编辑工作簿',
    accept: '.pdf,application/pdf',
    extensionLabel: 'PDF',
    available: true,
  },
  {
    id: 'pdf-to-word',
    label: 'PDF 转 Word',
    description: '保留文本、图片与基础版式',
    accept: '.pdf,application/pdf',
    extensionLabel: 'PDF',
    available: true,
  },
  {
    id: 'word-to-pdf',
    label: 'Word 转 PDF',
    description: '生成适合分发的 PDF 文档',
    accept: '.docx,application/vnd.openxmlformats-officedocument.wordprocessingml.document',
    extensionLabel: 'DOCX',
    available: true,
  },
  {
    id: 'pdf-translation',
    label: 'PDF 翻译',
    description: '翻译文档并保留可复核证据',
    accept: '.pdf,application/pdf',
    extensionLabel: 'PDF',
    available: true,
  },
  {
    id: 'pdf-split',
    label: 'PDF 拆分',
    description: '按页或页段输出独立文件',
    accept: '.pdf,application/pdf',
    extensionLabel: 'PDF',
    available: true,
  },
] as const

export function getDocumentTool(id: DocumentToolDefinition['id']) {
  return DOCUMENT_TOOLS.find(tool => tool.id === id) ?? DOCUMENT_TOOLS[0]
}
