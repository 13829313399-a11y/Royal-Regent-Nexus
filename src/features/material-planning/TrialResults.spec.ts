import { mount } from '@vue/test-utils'
import { describe, expect, it } from 'vitest'
import TrialResults from './TrialResults.vue'
import type { Amount, TrialResult } from './api'

const amount = (value: string): Amount => ({ value, numerator: '0', denominator: '1', approximate: false })
const result = (): TrialResult => ({
  lines: [], totals: [{ material_id: 'glue', material_version: 2, code: '03-01-00001', name: '合成胶水', unit: '千克', attribute: '外购',
    base: amount('0.04'), loss: amount('0'), gross: amount('0.04'), processes: ['手工'], keys: ['glue'], purchase_conversion: {
      status: 'READY', purchase_unit: '支', base_unit: '千克', base_quantity: amount('0.02'), reference: '包装档案',
      exact_quantity: amount('2'), rounded_quantity: '2', surplus: amount('0') } }],
  finished_quantity: amount('2000'), finished_unit: '套', supply_status: 'PENDING_VERIFICATION', net_purchase_quantity: null,
  pending: ['库存及在途'], algorithm: 'gross-fraction-v3-purchase-reference', release_gate: { can_release: false, blockers: ['STOCK_VERIFICATION'] },
})

describe('purchase unit reference', () => {
  it('shows frozen conversion and server quantities with their units and pending supply', () => {
    const wrapper = mount(TrialResults, { props: { result: result() } })
    const text = wrapper.text()
    expect(text).toContain('1 支 = 0.02 千克')
    expect(text).toContain('2 支')
    expect(text).toContain('包装档案')
    expect(text).toContain('试算参考')
    expect(text).toContain('净采购数量：待库存和在途资料核实')
    expect(text).toContain('尚不能正式放单')
    wrapper.unmount()
  })

  it('distinguishes missing current conversions from historical uncalculated values', async () => {
    const data = result()
    data.totals[0]!.purchase_conversion = { status: 'MISSING' }
    const wrapper = mount(TrialResults, { props: { result: data } })
    expect(wrapper.text()).toContain('待维护换算关系')
    const legacy = result()
    delete legacy.totals[0]!.purchase_conversion
    await wrapper.setProps({ result: legacy })
    expect(wrapper.text()).toContain('此历史版本未计算采购换算')
    expect(wrapper.text()).not.toContain('2 支')
    wrapper.unmount()
  })
})
