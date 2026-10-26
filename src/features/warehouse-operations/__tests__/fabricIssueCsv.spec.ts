// @vitest-environment node
import { describe, expect, it } from 'vitest'
import type { WarehouseDocument, WarehouseDocumentInput } from '@/api/warehouseOperations'
import { fabricIssueCsv } from '../fabricIssueCsv'

const issue = (data: Partial<WarehouseDocumentInput> = {}, overrides: Partial<WarehouseDocument> = {}): WarehouseDocument => ({
  id: 'ISSUE-CSV-1', kind: 'ISSUE', sequence: 1, business_date: '2026-10-23', actor_name: '仓管甲', occurred_at: '',
  data: { production_no: 'FC-1', counterparty: '裁床一组', item_code: '00012', item_name: '白布 / 150cm', lot: '0008', roll_no: 'R01',
    location: '一仓／A01', unit: '码', quantity: '12.345678', purpose: '裁剪', reason: '核对缸号', ...data } as WarehouseDocumentInput,
  ...overrides,
})
const header = '业务日期,单据编号,放产单号,领用方,物料编码,物料名称/规格,缸号,卷号,仓位,单位,数量,用途/备注,经办人,状态'

describe('fabric issue CSV', () => {
  it('outputs only issues with the requested column order, CRLF and no BOM', () => {
    const csv = fabricIssueCsv([issue({}, { kind: 'RECEIPT', id: 'RECEIPT-1' }), issue(), issue({}, { kind: 'RETURN', id: 'RETURN-1' })])
    expect(csv).toBe(`${header}\r\n2026-10-23,ISSUE-CSV-1,FC-1,裁床一组,00012,白布 / 150cm,0008,R01,一仓／A01,码,12.345678,裁剪 / 核对缸号,仓管甲,已登记`)
    expect(csv.startsWith('\ufeff')).toBe(false)
    expect(fabricIssueCsv([])).toBe(header)
    expect(fabricIssueCsv([issue({}, { kind: 'REQUEST' })])).toBe(header)
  })

  it('quotes commas, doubles quotes and preserves multiline field content', () => {
    const csv = fabricIssueCsv([issue({ item_name: '白布,"宽幅"', purpose: '第一行\n第二行', reason: '备注\r\n续行', counterparty: '裁床\r一组' })])
    expect(csv).toContain(',"裁床\r一组",')
    expect(csv).toContain(',"白布,""宽幅""",')
    expect(csv).toContain(',"第一行\n第二行 / 备注\r\n续行",')
  })

  it('falls back to the batch snapshot when data fields are absent and retains data precedence', () => {
    const row = issue({ production_no: '', counterparty: '', item_code: '', item_name: '', lot: '', roll_no: '', location: '', unit: '', quantity: '', purpose: '', reason: '' })
    row.batch_snapshot = { id: 'B1', item_code: 'OLD-CODE', item_name: '历史白布', unit: '米', quantity: '45.670000',
      lot: 'LOT-OLD', roll_no: 'ROLL-OLD', location: '旧仓／B02', counterparty: '历史领用方', production_no: 'FC-OLD',
      process_state: '', material_category: 'FABRIC', available_quantity: '33', quality_status: 'PENDING_INSPECTION', source_no: '', source_document: '', received_on: '' }
    expect(fabricIssueCsv([row]).split('\r\n')[1]).toBe('2026-10-23,ISSUE-CSV-1,,,OLD-CODE,历史白布,LOT-OLD,ROLL-OLD,旧仓／B02,米,,,仓管甲,已登记')
    expect(fabricIssueCsv([issue({}, { batch_snapshot: row.batch_snapshot })])).toBe(fabricIssueCsv([issue()]))
    expect(fabricIssueCsv([issue({ quantity: '0' }, { batch_snapshot: row.batch_snapshot })])).toContain(',0,裁剪 / 核对缸号,')
  })

  it('never exports receipt production, supplier or batch balance as issue facts', () => {
    const row = issue({ production_no: '', counterparty: '', quantity: '' })
    row.batch_snapshot = { production_no: 'RECEIPT-PRODUCTION', counterparty: '原供应商', quantity: '98765' } as NonNullable<WarehouseDocument['batch_snapshot']>
    const csv = fabricIssueCsv([row])
    for (const value of ['RECEIPT-PRODUCTION', '原供应商', '98765']) expect(csv).not.toContain(value)
    const columns = csv.split('\r\n')[1]!.split(',')
    expect([columns[2], columns[3], columns[10]]).toEqual(['', '', ''])
  })

  it('leaves unknown fields empty and retains remarks when there is no purpose', () => {
    const row = issue({}, { business_date: '', id: '', actor_name: '', data: {} as WarehouseDocumentInput })
    expect(fabricIssueCsv([row]).split('\r\n')[1]?.split(',')).toEqual([...Array<string>(13).fill(''), '已登记'])
    expect(fabricIssueCsv([issue({ purpose: '', reason: '仅备注' })])).toContain(',仅备注,仓管甲,')
  })

  it('marks reversals without negating quantities or expanding allocations', () => {
    const csv = fabricIssueCsv([issue({ allocations: [{ production_no: 'FC-A', quantity: '4' }, { production_no: 'FC-B', quantity: '8.345678' }] }, { reversed: true })])
    expect(csv.split('\r\n')).toHaveLength(2)
    expect(csv).toContain(',12.345678,')
    expect(csv).toContain(',已冲销')
    expect(csv).not.toContain('FC-A')
  })

  it('preserves input order and values without depending on browser globals', () => {
    expect(typeof window).toBe('undefined')
    expect(typeof document).toBe('undefined')
    const rows = [issue({}, { id: 'FIRST', business_date: '2026-10-01' }), issue({}, { id: 'SECOND', business_date: '2026-10-23' })]
    const before = structuredClone(rows)
    const csv = fabricIssueCsv(rows)
    expect(csv.indexOf('FIRST')).toBeLessThan(csv.indexOf('SECOND'))
    expect(fabricIssueCsv(rows)).toBe(csv)
    expect(rows).toEqual(before)
  })
})
