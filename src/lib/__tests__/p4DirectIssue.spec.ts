import { describe, expect, it } from 'vitest'
import { parseP4InternalQuoteArtifact, P4_SECTION_CODES } from '@/lib/customerPriceConverters/p4Artifact'
import { createXlsxWorkbook, type XlsxCellInput } from '@/lib/customerPriceConverters/xlsxLite'

function workbook(options: { direct?: boolean; boundary?: string; status?: string; calculation?: string; dependency?: string; hash?: string; formula?: string; snapshot?: string } = {}) {
  const direct = options.direct !== false
  const rows: XlsxCellInput[][] = [[], ['结构版本', 'internal-quote-structured-data-v1'], ['记录类型', '分段代码', '分段名称', '状态', 'revision', '计算状态', '依赖状态', '计算hash', '分片序号', '分片总数', 'JSON分片', '是否参与']]
  rows.push(['reference_snapshot', 'quote', '报价参考快照', '', 1, '', '', '', 1, 1, '{}', '否'])
  for (const code of P4_SECTION_CODES) {
    const calculation = { calculation_hash: options.hash ?? 'HASH', formula_version: options.formula ?? 'F1', reference_snapshot_id: options.snapshot ?? 'R1' }
    for (const type of ['payload', 'calculation']) rows.push([type, code, code, options.status ?? (direct ? 'sealed' : 'approved'), 1, options.calculation ?? 'valid', options.dependency ?? 'current', 'HASH', 1, 1, JSON.stringify(type === 'payload' ? {} : calculation), '是'])
  }
  const bytes = createXlsxWorkbook([
    { name: '报价明细', rows: [['测试报价']] },
    { name: '审批与版本', rows: [[], ['模板版本', 'internal-quote-p4-v2', '公式版本', 'F1'], ['参考快照', 'R1'], ['导出阶段', direct ? 'P4 直接输出' : 'P4 最终业务放行'], ['边界说明', options.boundary ?? (direct ? '报价版本已冻结，可交接客价转换台' : '最终业务放行完成，可交接客价转换台')]] },
    { name: '结构化数据', rows },
  ])
  return bytes.buffer.slice(bytes.byteOffset, bytes.byteOffset + bytes.byteLength) as ArrayBuffer
}

describe('P4 direct issue boundary', () => {
  it('accepts sealed direct-issued sections and legacy approved output', () => {
    expect(parseP4InternalQuoteArtifact(workbook()).sections.sales.status).toBe('sealed')
    expect(parseP4InternalQuoteArtifact(workbook({ direct: false })).sections.sales.status).toBe('approved')
  })
  it.each([
    { direct: false, status: 'sealed' },
    { status: 'approved' },
    { status: 'draft' },
    { boundary: '最终业务放行完成，可交接客价转换台' },
    { calculation: 'pending' },
    { dependency: 'stale' },
    { hash: 'altered' },
    { formula: 'old' },
    { snapshot: 'other' },
  ])('rejects invalid state or identity %j', options => {
    expect(() => parseP4InternalQuoteArtifact(workbook(options))).toThrow()
  })
})
