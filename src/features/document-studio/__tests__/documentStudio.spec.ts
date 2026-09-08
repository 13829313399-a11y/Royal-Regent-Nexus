import { describe, expect, it } from 'vitest'
import { DOCUMENT_TOOLS, getDocumentTool } from '../constants'
import {
  DOCUMENT_TOOL_IDS,
  isDocumentToolId,
  MAX_DOCUMENT_FILE_BYTES,
  validateDocumentFile,
} from '../types'

describe('document studio closed frontend contracts', () => {
  it('exposes the documented primary tools including batch PDF rename', () => {
    expect(DOCUMENT_TOOLS.map(tool => tool.id)).toEqual(DOCUMENT_TOOL_IDS)
    expect(getDocumentTool('pdf-batch-rename')).toMatchObject({ multiple: true })
  })

  it('accepts only closed tool query values', () => {
    expect(isDocumentToolId('pdf-translation')).toBe(true)
    expect(isDocumentToolId('pdf-batch-rename')).toBe(true)
    expect(isDocumentToolId('document-translation')).toBe(false)
    expect(isDocumentToolId(['pdf-to-excel'])).toBe(false)
  })

  it('validates extension, non-empty content and the 20 MB limit', () => {
    const tool = getDocumentTool('pdf-to-excel')
    expect(validateDocumentFile(new File(['pdf'], '订单.PDF'), tool)).toBe('')
    expect(validateDocumentFile(new File(['word'], '订单.docx'), tool)).toContain('仅支持 PDF')
    expect(validateDocumentFile(new File([], '空白.pdf'), tool)).toContain('非空')
    expect(validateDocumentFile({
      name: '超大.pdf',
      size: MAX_DOCUMENT_FILE_BYTES + 1,
    } as File, tool)).toContain('20 MB')
  })
})
