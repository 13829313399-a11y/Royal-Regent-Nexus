import type { DocumentToolDefinition } from './types'

export const DOCUMENT_TOOLS: readonly DocumentToolDefinition[] = [
  {
    id: 'pdf-to-excel',
    label: 'PDF 转 Excel',
    description: '提取表格并生成可编辑工作簿',
    accept: '.pdf,application/pdf',
    extensionLabel: 'PDF',
  },
  {
    id: 'pdf-to-word',
    label: 'PDF 转 Word',
    description: '保留文本、图片与基础版式',
    accept: '.pdf,application/pdf',
    extensionLabel: 'PDF',
  },
  {
    id: 'word-to-pdf',
    label: 'Word 转 PDF',
    description: '生成适合分发的 PDF 文档',
    accept: '.docx,application/vnd.openxmlformats-officedocument.wordprocessingml.document',
    extensionLabel: 'DOCX',
  },
  {
    id: 'pdf-translation',
    label: 'PDF 翻译',
    description: '使用服务器本地模型翻译并生成新文件',
    accept: '.pdf,application/pdf',
    extensionLabel: 'PDF',
  },
  {
    id: 'pdf-split',
    label: 'PDF 拆分',
    description: '按页或页段输出独立文件',
    accept: '.pdf,application/pdf',
    extensionLabel: 'PDF',
  },
  {
    id: 'pdf-batch-rename',
    label: '批量改名',
    description: '按专用规则识别固定区域并生成新文件名',
    accept: '.pdf,application/pdf',
    extensionLabel: 'PDF',
    multiple: true,
  },
] as const

export function getDocumentTool(id: DocumentToolDefinition['id']) {
  return DOCUMENT_TOOLS.find(tool => tool.id === id) ?? DOCUMENT_TOOLS[0]
}
