import { describe, expect, it } from 'vitest'
import { dimensionReference, isCardPaper, paperFlute, standardPaperTypes } from '../paperCatalog'
import { masterPaperOptions, type MasterRecord } from '@/api/cartonMaster'
import { matchesSettlementLine } from '../queryFilters'
import { settlementCsv } from '../settlementExport'
import type { StatementLine, SupplierSource } from '@/api/cartonSupplierSettlement'

describe('confirmed paper catalog and dimensions', () => {
  it('provides the six standards and exact material/flute mappings without renaming historical identities', () => {
    expect(standardPaperTypes.map(row => row.name)).toEqual(['普通箱', '半翼箱', '平卡', '刀卡', '压线卡', '啤卡'])
    expect(masterPaperOptions([], 'packaging_type', { packaging_type: ['外箱', '新品A'] })).toEqual([...standardPaperTypes.map(row => row.name), '外箱', '新品A'])
    expect(paperFlute(' b3b ')).toBe('单坑'); expect(paperFlute('H3B3H')).toBe('双坑'); expect(paperFlute('UNKNOWN')).toBe('')
    expect(isCardPaper('刀卡')).toBe(true); expect(isCardPaper('隔卡')).toBe(true); expect(isCardPaper('卡通普通箱')).toBe(false)
  })
  it('keeps fixed types visible even in legacy hide lists while allowing custom types', () => {
    const rule = { kind: 'RULE', customer_code: '', data: { paper_types: ['特殊箱'], hidden_paper_types: ['普通箱', '平卡', '旧箱'] } } as MasterRecord
    expect(masterPaperOptions([rule], 'packaging_type', { packaging_type: ['旧箱'] })).toEqual([...standardPaperTypes.map(row => row.name), '特殊箱'])
  })
  it('converts reference dimensions only with an explicit unit and never guesses free text', () => {
    expect(dimensionReference('10*20*30', 'inch')).toBe('25.4 × 50.8 × 76.2 cm / 10 × 20 × 30 inch（换算参考）')
    expect(dimensionReference('25.4×50.8', 'cm')).toContain('10 × 20 inch')
    expect(dimensionReference('254*508', 'mm')).toContain('10 × 20 inch')
    expect(dimensionReference('10*20 in', 'inch')).toContain('25.4 × 50.8 cm')
    expect(dimensionReference('10*20 in', 'cm')).toContain('单位不一致')
    expect(dimensionReference('10*20', '')).toContain('明确选择')
    expect(dimensionReference('带耳10*20', 'cm')).toContain('原文保留')
  })
})
const statement = (key: string): StatementLine => ({ id: key, source_key: key, document_no: 'D-1', quantity: '12', unit_price: '1.25', amount: '15.00', approved_return_unit_price: null, credit_document_no: '', credit_date: null, note: '' })
const source = (type: string): SupplierSource => ({ source_key: type, kind: 'RECEIPT', document_no: 'D-1', acceptance_date: '2026-10-01', date_basis: 'ACCEPTANCE', customer_name: '客户A', contract_no: '000123', item_no: '=BAD()', packaging_type: type, paper_quality: 'B33', specification: '10*20', dimension_unit: 'inch', unit: '张', quantity: '12', unit_price: '1.25', amount: '15.00', currency: 'CNY', issues: [] })
it('filters card evidence separately, leaving unmatched and unrelated paper outside the card scope', () => {
  expect(matchesSettlementLine(statement('平卡'), source('平卡'), undefined, '', 'CARD')).toBe(true)
  expect(matchesSettlementLine(statement('普通箱'), source('普通箱'), undefined, '', 'CARD')).toBe(false)
  expect(matchesSettlementLine(statement('x'), undefined, undefined, '', 'CARD')).toBe(false)
  expect(matchesSettlementLine(statement('啤卡'), source('啤卡'), undefined, '不存在', 'CARD')).toBe(false)
})
it('exports only supplied filtered rows with original units, identifiers, acceptance month and safe Excel text', () => {
  const csv = settlementCsv([statement('平卡')], new Map([['平卡', source('平卡')], ['普通箱', source('普通箱')]]), '2026-10', 'CNY')
  expect(csv).toContain('英寸（inch）'); expect(csv).toContain('"\'000123"'); expect(csv).toContain('"\'=BAD()"')
  expect(csv).toContain('2026-10-01'); expect(csv).not.toContain('普通箱')
})
