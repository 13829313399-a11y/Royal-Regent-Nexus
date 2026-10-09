import { mount } from '@vue/test-utils'
import { describe, expect, it } from 'vitest'
import type { ApiInternalQuote, ApiInternalQuoteVersionComparison } from '@/api/internalQuote'
import { pairComparisonItems } from '@/lib/internalQuoteDetailComparison'
import InternalQuoteComparison from '../InternalQuoteComparison.vue'

function fixture() {
  const hardware = [
    { item: '螺丝', category: 'hardware', specification: '2×6 mm', quantity: 6, unit_price_rmb: 0.027 },
    { item: '车轴', category: 'hardware', specification: '2×65 mm', quantity: 2, unit_price_hkd: 0.182 },
  ]
  const base = { sections: [{ department: 'engineering', is_required: true, payload: { materials: hardware } }] } as ApiInternalQuote
  const target = { sections: [{ department: 'engineering', is_required: true, payload: { materials: [hardware[1], { ...hardware[0], specification: '2×8 mm', unit_price_rmb: 0.03 }, { item: '垫片', category: 'hardware', quantity: 1, unit_price_rmb: 0 }] } }] } as ApiInternalQuote
  const comparison = { total_before_hkd: '1', total_after_hkd: '2', total_delta_hkd: '1', header_changes: [{ path: 'shipping_pricing.pricing_entries', before: [{ internal_secret: 'should-not-render' }], after: [] }, { path: 'reference_snapshot_id', before: 'IQREF-hidden', after: 'IQREF-other' }], sections: [{ section_code: 'engineering', section_name: '工程部', before_total_hkd: '1', after_total_hkd: '2', delta_hkd: '1', payload_changes: [{ path: 'materials', before: hardware, after: [] }] }] } as unknown as ApiInternalQuoteVersionComparison
  return { base, target, comparison, baseLabel: '普通盒 · A-V1', targetLabel: '开窗盒 · B-V1' }
}
describe('business quotation comparison', () => {
  it('shows hardware side by side with original specifications and unit prices, without internal objects', async () => {
    const wrapper = mount(InternalQuoteComparison, { props: fixture() })
    const text = wrapper.text()
    expect(text).toContain('工程部'); expect(text).toContain('五金')
    expect(text).toContain('2×6 mm'); expect(text).toContain('2×8 mm')
    expect(text).toContain('0.027'); expect(text).toContain('0.03'); expect(text).toContain('单价 RMB')
    expect(text).not.toMatch(/shipping_pricing|pricing_entries|IQREF|internal_secret|should-not-render/)
    const screw = wrapper.findAll('tbody tr').find(row => row.text().includes('螺丝'))!
    expect(screw.findAll('.highlight').map(cell => cell.text())).toContain('规格2×8 mm')
    expect(wrapper.text()).not.toContain('车轴')
    await wrapper.get('.same-toggle').trigger('click')
    const axle = wrapper.findAll('tbody tr').find(row => row.text().includes('车轴'))!
    expect(axle.text()).toContain('相同')
    await wrapper.get('.same-toggle').trigger('click')
    expect(wrapper.text()).not.toContain('车轴')
    expect(wrapper.text()).toContain('垫片'); expect(wrapper.text()).toContain('此版无此项')
    wrapper.unmount()
  })
  it('matches reordered duplicate names before pairing edits, and keeps additions and deletions distinct', () => {
    const a = { name: '螺丝', fields: { 规格: '短', '单价 RMB': '0' } }
    const b = { name: '螺丝', fields: { 规格: '长', '单价 RMB': '0.05' } }
    expect(pairComparisonItems([a, b], [b, a]).every(row => !row.changed)).toBe(true)
    const rows = pairComparisonItems([a, b], [b, { name: '车轴', fields: { 用量: '0' } }])
    expect(rows.map(row => row.status)).toEqual(['已删除', '相同', '新增'])
    expect(rows[2]!.after!.fields.用量).toBe('0')
  })
  it('collapses unchanged departments by default and expands them on request', async () => {
    const props = fixture()
    props.target = props.base
    props.comparison.sections[0]!.payload_changes = []
    const wrapper = mount(InternalQuoteComparison, { props })
    expect(wrapper.get('.department').attributes('open')).toBeUndefined()
    expect(wrapper.get('.department > summary').text()).toContain('明细相同 · 点击查看')
    await wrapper.get('input[type=checkbox]').setValue(true)
    expect(wrapper.get('.department').attributes('open')).toBeDefined()
    wrapper.unmount()
  })
  it('shows the entered price currency instead of a derived or empty alternate price', () => {
    const props = fixture()
    props.base.sections[0]!.payload = { materials: [{ item: '螺丝', category: 'hardware', unit_price_source_currency: 'RMB', unit_price_rmb: 0.027, unit_price_hkd: 0 }] }
    props.target.sections[0]!.payload = { materials: [{ item: '螺丝', category: 'hardware', unit_price_source_currency: 'RMB', unit_price_rmb: 0.03, unit_price_hkd: 0.0353 }] }
    const wrapper = mount(InternalQuoteComparison, { props })
    expect(wrapper.text()).toContain('单价 RMB')
    expect(wrapper.text()).not.toContain('单价 HKD')
    wrapper.unmount()
  })
  it('does not mix packaging rows across departments or silently label hidden supplemental changes as unchanged', () => {
    const props = fixture()
    props.base.sections.push({ department: 'sales', is_required: true, payload: { packaging_materials: [{ item: '彩盒', quantity: 1, unit_price_rmb: 1 }] } } as never)
    props.target.sections.push({ department: 'sales', is_required: true, payload: { packaging_materials: [{ item: '彩盒', quantity: 1, unit_price_rmb: 1 }], customer_quote_fields: { note: 'new' } } } as never)
    props.comparison.sections.push({ section_code: 'sales', section_name: '业务部', before_total_hkd: '1', after_total_hkd: '1', delta_hkd: '0', payload_changes: [{ path: 'customer_quote_fields.note', before: '', after: 'new' }] } as never)
    const wrapper = mount(InternalQuoteComparison, { props })
    expect(wrapper.findAll('.department')).toHaveLength(2)
    expect(wrapper.findAll('.department')[1]!.text()).toContain('包装材料')
    expect(wrapper.text()).toContain('另有附加资料或排列变化')
    wrapper.unmount()
  })
})
