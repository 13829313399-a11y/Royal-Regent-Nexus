import { describe, expect, it } from 'vitest'
import {
  prepareP4CustomerConversion,
} from '@/lib/customerPriceConverters/p4CustomerAdapter'
import {
  P4_ARTIFACT_TEMPLATE_VERSION,
  P4_SECTION_CODES,
  P4_STRUCTURED_DATA_SCHEMA_VERSION,
  parseP4InternalQuoteArtifact,
} from '@/lib/customerPriceConverters/p4Artifact'
import {
  createBuzzBeeCustomerQuoteWorkbook,
} from '@/lib/customerPriceConverters/buzzbee'
import {
  createXlsxWorkbook,
  parseXlsxWorkbook,
  type XlsxCellInput,
} from '@/lib/customerPriceConverters/xlsxLite'

function asArrayBuffer(bytes: Uint8Array) {
  return bytes.buffer.slice(bytes.byteOffset, bytes.byteOffset + bytes.byteLength) as ArrayBuffer
}

function p4Workbook(templateVersion = P4_ARTIFACT_TEMPLATE_VERSION) {
  const summary: XlsxCellInput[][] = Array.from({ length: 6 }, () => [])
  summary[1] = ['报价编号', 'IQ-P4-BB-001', '版本', 'V1', '客户', 'BuzzBee', '数量', 3000]
  summary[2] = ['产品', '火堆套装', '厂区/车间', 'huaxing/华兴', '公式版本', 'rr2-2026-v1', '参考快照', 'IQREF-1']

  const approval: XlsxCellInput[][] = Array.from({ length: 8 }, () => [])
  approval[1] = ['模板版本', templateVersion]
  approval[3] = ['导出阶段', 'P4 最终业务放行']
  approval[4] = ['边界说明', '最终业务放行完成，可交接客价转换台']

  const structured: XlsxCellInput[][] = Array.from({ length: 4 }, () => [])
  structured[1] = ['结构版本', P4_STRUCTURED_DATA_SCHEMA_VERSION]
  structured[2] = ['记录类型', '分段代码', '分段名称', '状态', 'revision', '计算状态', '依赖状态', '计算hash', '分片序号', '分片总数', 'JSON分片']
  const addRecord = (type: string, code: string, name: string, value: Record<string, unknown>) => {
    structured.push([type, code, name, 'approved', 2, 'valid', 'current', `${code}-hash`, 1, 1, JSON.stringify(value)])
  }
  addRecord('reference_snapshot', 'quote', '报价参考快照', {})
  P4_SECTION_CODES.forEach((code) => {
    const payload = code === 'molding'
      ? {
          injection_lines: [{
            item: '大身面壳', material: 'ABS', grade: '750SW', net_weight_g: 135,
            loss_rate_percent: 3, machine_code: '18A', sets: 1, target_output: 2800, quantity: 1,
          }],
          blow_lines: [],
        }
      : code === 'engineering'
        ? { materials: [], molds: [], amortization_qty: 0, customer_mold_subsidy_usd: 0, cartons: [] }
        : {}
    const calculation = code === 'molding'
      ? {
          line_breakdown: [{ kind: 'injection', item: '大身面壳', material_cost_hkd: '2.1400', molding_cost_hkd: '0.6750', amount_hkd: '2.8150' }],
          totals: { injection_hkd: '2.8150', blow_hkd: '0.0000', total_hkd: '2.8150' },
        }
      : { line_breakdown: [], totals: { total_hkd: '0.0000' } }
    Object.assign(calculation, {
      calculation_hash: `${code}-hash`,
      formula_version: 'rr2-2026-v1',
      reference_snapshot_id: 'IQREF-1',
    })
    addRecord('payload', code, code, payload)
    addRecord('calculation', code, code, calculation)
  })

  return asArrayBuffer(createXlsxWorkbook([
    { name: '报价明细', rows: summary },
    { name: '审批与版本', rows: approval },
    { name: '结构化数据', rows: structured },
  ]))
}

describe('P4 customer price adapter', () => {
  it('validates P4 v2 structured data and drives the BuzzBee converter', () => {
    const source = p4Workbook()
    const artifact = parseP4InternalQuoteArtifact(source)
    expect(artifact.quoteNo).toBe('IQ-P4-BB-001')
    expect(artifact.sections.molding.payload.injection_lines).toHaveLength(1)

    const prepared = prepareP4CustomerConversion(source, 'IQ-P4-BB-001.xlsx', 'buzzbee')
    expect(prepared.customerId).toBe('buzzbee')
    expect(prepared.result.sheets[0].name).toBe('火堆套装')
    expect(prepared.result.sheets[0].totalCustomerHkd).toBeGreaterThan(0)

    const exported = createBuzzBeeCustomerQuoteWorkbook(prepared.result)
    expect(parseXlsxWorkbook(asArrayBuffer(exported)).sheets[0].rows[0][0]).toBe('COST BREAKDOWN SHEET (ROYAL REGENT)')
  })

  it('rejects legacy P4 v1 before one-time consumption', () => {
    expect(() => parseP4InternalQuoteArtifact(p4Workbook('internal-quote-p4-v1')))
      .toThrow('旧 P4 v1 没有完整原始参数')
  })

  it('keeps customer-specific incomplete mappings explicit', () => {
    const disneySource = p4Workbook()
    const workbook = parseXlsxWorkbook(disneySource)
    workbook.sheets[0].rows[1][5] = '迪士尼'
    const rebuilt = asArrayBuffer(createXlsxWorkbook(workbook.sheets))
    expect(() => prepareP4CustomerConversion(rebuilt, 'disney-p4.xlsx', 'disney'))
      .toThrow('Item Number')
  })
})
