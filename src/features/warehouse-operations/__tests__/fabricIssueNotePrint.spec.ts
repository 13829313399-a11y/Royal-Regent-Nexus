// @vitest-environment node
import { describe, expect, it } from 'vitest'
import type { WarehouseDocument, WarehouseDocumentInput } from '@/api/warehouseOperations'
import { fabricIssueNoteHtml } from '../fabricIssueNotePrint'

const issue = (data: Partial<WarehouseDocumentInput> = {}, overrides: Partial<WarehouseDocument> = {}): WarehouseDocument => ({
  id: 'ISSUE-001', kind: 'ISSUE', sequence: 1, business_date: '2026-10-23', actor_name: '仓管甲', occurred_at: '',
  data: {
    factory_id: 'huakang-c', request_id: 'request-1', expected_revision: 0, kind: 'ISSUE', business_date: '2026-10-23',
    source_system: 'MANUAL', source_no: '', source_line: '', source_version: '', item_code: '00012', item_name: '白布 / 150cm',
    unit: '码', process_state: '', material_category: 'FABRIC', location: '一仓／A01', lot: '0008', roll_no: 'R01',
    quantity: '12.345678', consumed_quantity: '', counterparty: '裁床一组', production_no: 'FC-001', purpose: '裁剪', due_date: null,
    batch_id: 'B1', original_id: '', task_id: '', quality_status: 'PENDING_INSPECTION', responsible_person: '', reason: '核对缸号', allocations: [],
    ...data,
  },
  batch_snapshot: {
    id: 'B1', item_code: 'SNAP-001', item_name: '历史白布', unit: '米', process_state: '', material_category: 'FABRIC',
    location: '旧仓／B02', lot: 'LOT-OLD', roll_no: 'ROLL-OLD', quantity: '98765', available_quantity: '87654',
    quality_status: 'PENDING_INSPECTION', source_no: '', source_document: '', received_on: '', counterparty: '原供应商', production_no: '旧放产单',
  },
  ...overrides,
})

describe('fabric issue note printing', () => {
  it('renders A4 portrait with recorded issue facts and blank signatures', () => {
    const html = fabricIssueNoteHtml(issue(), {})
    expect(html).toContain('@page { size: A4 portrait;')
    expect(html).toContain('<h1>发料单</h1>')
    expect(html).toContain('华康塑胶制品（东源）有限公司')
    for (const value of ['ISSUE-001', '2026-10-23', '裁床一组', 'FC-001', '裁剪', '仓管甲', '00012', '白布 / 150cm', '码', '核对缸号']) expect(html).toContain(value)
    expect(html).toContain('<div>领料人：</div><div>日期：</div>')
    expect(html).toContain('本单为仓库发料凭证，实际领用以签收为准')
    expect(html).not.toContain('放产单分配')
  })

  it('escapes all dynamic fields, including context, snapshots and allocations', () => {
    const unsafe = `<>&"'`
    const escaped = '&lt;&gt;&amp;&quot;&#39;'
    const row = issue({ item_code: unsafe, item_name: unsafe, lot: unsafe, roll_no: unsafe, location: unsafe, unit: unsafe,
      quantity: unsafe, counterparty: unsafe, production_no: unsafe, purpose: unsafe, reason: unsafe,
      allocations: [{ production_no: unsafe, quantity: unsafe }] }, { id: unsafe, business_date: unsafe, actor_name: unsafe })
    row.batch_snapshot!.material_detail = unsafe
    const html = fabricIssueNoteHtml(row, { factoryName: unsafe })
    expect(html).not.toContain(unsafe)
    expect(html.split(escaped)).toHaveLength(21)
    expect(html).not.toContain('<script')
  })

  it('keeps missing production and other fields unknown instead of borrowing batch production', () => {
    const html = fabricIssueNoteHtml(issue({ production_no: '', counterparty: '', purpose: '', reason: '' }), {})
    expect(html).toContain('<span>放产单号：</span>—')
    expect(html).toContain('<span>领用方：</span>—')
    expect(html).toContain('<span>用途：</span>—')
    expect(html).not.toContain('旧放产单')
    expect(html).not.toContain('原供应商')
  })

  it('uses recorded lot, roll and location, then the historical snapshot when absent', () => {
    const html = fabricIssueNoteHtml(issue(), {})
    expect(html).toContain('<td>0008 / R01</td>')
    expect(html).toContain('<td>一仓／A01</td>')
    const fallback = fabricIssueNoteHtml(issue({ lot: '', roll_no: '', location: '', item_code: '', item_name: '', unit: '' }), {})
    for (const value of ['LOT-OLD / ROLL-OLD', '旧仓／B02', 'SNAP-001', '历史白布', '<td>米</td>']) expect(fallback).toContain(value)
    const missing = fabricIssueNoteHtml(issue({ lot: '', roll_no: '', location: '' }, { batch_snapshot: undefined }), {})
    expect(missing).toContain('<td>— / —</td>\n      <td>—</td>')
  })

  it('renders allocations separately without duplicating physical quantity or printing stock balances', () => {
    const html = fabricIssueNoteHtml(issue({ allocations: [{ production_no: 'FC-A', quantity: '4' }, { production_no: 'FC-B', quantity: '8.345678' }] }), {})
    expect(html).toContain('放产单分配')
    expect(html).toContain('分配仅供核对，总数量以本次实发为准')
    expect(html).toContain('<td>FC-A</td><td class="number">4</td>')
    expect(html).toContain('<td>FC-B</td><td class="number">8.345678</td>')
    expect(html.match(/>12\.345678</g)).toHaveLength(1)
    for (const value of ['24.691356', '98765', '87654', '当前库存', '结余']) expect(html).not.toContain(value)
  })

  it('marks reversed originals in red while retaining the original issue quantity', () => {
    const html = fabricIssueNoteHtml(issue({}, { reversed: true }), {})
    expect(html).toContain('<div class="reversed">已冲销，仅供存档</div>')
    expect(html).toMatch(/\.reversed\s*\{[^}]*color: #b91c1c/)
    expect(html).toContain('>12.345678</td>')
    expect(fabricIssueNoteHtml(issue(), {})).not.toContain('已冲销，仅供存档')
  })

  it('is deterministic without window or document and does not mutate the input', () => {
    expect(typeof window).toBe('undefined')
    expect(typeof document).toBe('undefined')
    const row = issue({ quantity: '0' })
    const before = structuredClone(row)
    const html = fabricIssueNoteHtml(row, { factoryName: '自定义公司' })
    expect(html).toContain('自定义公司')
    expect(html).toContain('>0</td>')
    expect(fabricIssueNoteHtml(row, { factoryName: '自定义公司' })).toBe(html)
    expect(row).toEqual(before)
  })
})
