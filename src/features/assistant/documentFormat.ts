import type { FileSource } from './v2'

export interface DocumentSegment {
  text: string
  document_version?: string
  locator: FileSource['locator']
  metadata?: {
    format?: 'docx' | 'xlsx' | 'ocr'; heading?: string | null; in_table?: boolean; coverage?: string
    signal_score?: number | null; uncertain?: boolean; uncertainty_reasons?: string[]; engine?: string
    formula?: string; cache_status?: 'available' | 'missing'; number_format?: string
    merged_range?: string; merged_anchor?: string; sheet_state?: string; hidden_row?: boolean
    raw_value?: string | null; cell_type?: string; cell_error?: string; formula_range?: string
  }
}

export function documentLocation(l: FileSource['locator']) {
  if (l.kind === 'document') return '文档检索范围 · 不作为正文引用'
  if (l.kind === 'ocr_region') return `第 ${l.page} 页 · 识别区域 ${l.region}`
  return l.kind === 'page' ? `第 ${l.page} 页` : l.kind === 'lines' ? `第 ${l.start}–${l.end} 行`
    : l.kind === 'paragraph' ? `第 ${l.paragraph} 段` : l.kind === 'sheet' ? `${l.sheet}!${l.cells}` : '图片'
}

export function formatDocumentSegment(part: DocumentSegment, includeCoverage = true) {
  const m = part.metadata
  const lines = [documentLocation(part.locator) + (m?.heading ? ` · ${m.heading}` : ''), part.text]
  if (m?.in_table) lines.push('位置：表格中的段落')
  if (m?.format === 'ocr') lines.push('图像识别候选 · 待核对原页',
    m.signal_score == null ? '本区域没有识别结果' : `识别评分：${m.signal_score.toFixed(3)}（不是正确率）`,
    '模糊字符和数字不能推定为确定值')
  if (m?.formula) lines.push(`公式（未执行）：${m.formula}`, m.cache_status === 'available'
    ? '缓存：文件已保存的值，未重新计算' : '缓存：未保存可用值，不能按 0 处理')
  if (m?.cell_error) lines.push(`单元格错误：${m.cell_error}`)
  if (m?.number_format && m.number_format !== 'General') lines.push(`单元格格式：${m.number_format}`)
  if (m?.merged_range) lines.push(`合并区域：${m.merged_range}；值来自 ${m.merged_anchor}`)
  if (m?.sheet_state && m.sheet_state !== 'visible') lines.push('文件中的隐藏工作表')
  if (m?.hidden_row) lines.push('文件中的隐藏行')
  if (includeCoverage && m?.coverage) lines.push(`解析范围：${m.coverage}`)
  return lines.join('\n')
}

export function formatDocument(parts: DocumentSegment[]) {
  const coverage = [...new Set(parts.map(p => p.metadata?.coverage).filter(Boolean))]
  return [...coverage.map(c => `解析范围：${c}`), ...parts.map(p => formatDocumentSegment(p, false))].join('\n\n')
}

export const documentParseMessages: Record<string, string> = {
  ocr_unavailable: '本机识别引擎或模型不可用，请联系管理员', ocr_failed: '图像识别未完成，请核对原件或拆分后上传',
  ocr_page_limit: '需要识别的页数超过 20 页，请拆分文件', ocr_preview_limit: '识别页图超过限制，请拆分文件',
  ocr_region_limit: '本页识别区域过多，请裁剪后上传', ocr_invalid_result: '识别结果无法定位，请核对原件',
  image_signature: '图片内容与格式不符，请重新导出 PNG 或 JPEG', image_pixel_limit: '图片超过 1000 万像素，请缩小后上传',
  image_frames_unsupported: '请上传单帧图片',
  pdf_encrypted: '请上传未加密的 PDF', pdf_invalid: 'PDF 无法读取，请核对文件', pdf_ocr_required: '扫描文件需要先识别成文字',
  file_page_limit: '页数超过限制，请拆分文件', file_text_limit: '文字与定位信息超过限制，请拆分文件',
  file_encoding: '请使用 UTF-8 或带 BOM 的 UTF-16 文本', csv_invalid: 'CSV 格式有误，请核对引号和分隔符', file_empty: '没有可分析的文字',
  parse_timeout: '解析超时，请拆分后重新上传', parse_interrupted: '解析已中断，请重新上传',
  parse_memory_limit: '解析超出内存限制，请拆分后重新上传', parse_resource_unavailable: '解析服务的资源保护暂不可用，请联系管理员',
  office_signature: '文件内容与 Office 格式不符，请另存为标准 DOCX 或 XLSX', office_invalid: 'Office 文件无法读取，请核对或重新导出',
  office_encrypted: '请上传未加密的 Office 文件', office_active_content: '文件含宏、嵌入对象或活动内容，请移除后重新导出',
  office_package_path: 'Office 文件内部结构不符合要求，请重新导出', office_expansion_limit: 'Office 文件展开后过大，请拆分后上传',
  office_paragraph_limit: '段落数超过限制，请拆分文档', office_sheet_limit: '工作表数量超过限制，请拆分工作簿',
  office_cell_limit: '单元格或合并区域数量超过限制，请拆分工作簿',
}

export function documentParseMessage(code?: string) {
  return documentParseMessages[code || ''] || '请核对文件后重新上传'
}
