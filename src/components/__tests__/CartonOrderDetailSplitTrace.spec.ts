import { mount } from '@vue/test-utils'
import { describe, expect, it } from 'vitest'
import CartonOrderDetailContent from '../CartonOrderDetailContent.vue'
import type { CartonOrderResponse } from '@/api/cartonProcurement'
import type { SplitRecord } from '@/api/cartonOrderSplits'

const record = (status: SplitRecord['status'], contract: string): SplitRecord => ({
  id: contract, factory_id: 'huadeng', order_id: 'one', order_no: 'CT1', item_no: 'ITEM', customer_code: 'C1',
  status, revision: 1, reason: 'test', created_at: '', created_by_name: '',
  targets: [{ contract_no: contract, customer_po: 'PO-' + contract, product_quantity: 300, lines: [] }],
})
const order = {
  id: 'one', factory_id: 'huadeng', contract_no: 'B', customer_code: 'C1', item_no: 'ITEM',
  schedule_split_source: { source_contract_no: 'A', current_contract_no: 'B', batch_id: 'batch', source_sheet: 'ITEM', source_row: 7 },
  split_records: [record('ACTIVE', 'C'), record('PENDING_WAREHOUSE', 'D'), record('CANCELLED', 'E')],
} as CartonOrderResponse
const render = (value?: CartonOrderResponse) => mount(CartonOrderDetailContent, {
  props: { fields: [], rows: [], order: value },
})

describe('shared order split provenance', () => {
  it('distinguishes schedule origin, live allocations and cancelled history without claiming new purchases', () => {
    const wrapper = render(order)
    const section = wrapper.get('[aria-label="拆单来源与去向"]')
    expect(section.text()).toContain('A → B')
    expect(section.text()).toContain('B → C')
    expect(section.text()).toContain('PO-C')
    expect(section.text()).toContain('产品数量：300')
    expect(section.text()).toContain('待仓库确认')
    expect(section.text()).toContain('历史拆出去向（已取消）')
    expect(section.text()).toContain('不另建重复采购单')
  })
  it('does not show another factory/customer/order allocation or stale source', () => {
    const wrapper = render({ ...order, contract_no: 'OTHER', split_records: [
      { ...record('ACTIVE', 'FOREIGN'), factory_id: 'huaxing' },
      { ...record('ACTIVE', 'FOREIGN-CUSTOMER'), customer_code: 'C2' },
      { ...record('ACTIVE', 'FOREIGN-ORDER'), order_id: 'two' },
    ] })
    expect(wrapper.find('[aria-label="拆单来源与去向"]').exists()).toBe(false)
  })
  it('keeps existing unrelated order details free of an empty provenance block', () => {
    expect(render().find('[aria-label="拆单来源与去向"]').exists()).toBe(false)
  })
})
