import { mount } from '@vue/test-utils'
import { describe, expect, it } from 'vitest'
import WarehousePackingReview from '../WarehousePackingReview.vue'

const group = { id: 'box', label: 'M01', output_label: 'M01', warehouse: '胶件仓', receipt_no: 'WH01', row_count: 2, issues: [] as string[] }
const rows = [{ index: 0, packing_group: group }, { index: 1, packing_group: group }]
describe('warehouse carton review', () => {
  it('reflects all, partial and restored selections without changing receipt rows', async () => {
    const wrapper = mount(WarehousePackingReview, { props: { rows, selected: rows } })
    expect(wrapper.text()).toContain('合为 1 个混箱包装组')
    expect(wrapper.findAll('tbody tr')).toHaveLength(1)
    await wrapper.setProps({ selected: rows.slice(0, 1) })
    expect(wrapper.text()).toContain('同箱物料未全部选中')
    expect(wrapper.text()).not.toContain('合为 1 个混箱包装组')
    await wrapper.setProps({ selected: rows })
    expect(wrapper.text()).toContain('合为 1 个混箱包装组')
    expect(rows[0]!.packing_group.issues).toEqual([])
  })
  it('shows source conflicts and missing labels while keeping warehouses separate', () => {
    const others = [...rows.map(row => ({ ...row, packing_group: { ...group, issues: ['同箱箱数不一致'] } })),
      { index: 2, packing_group: { ...group, id: 'other-warehouse', warehouse: '半成品仓', row_count: 1 } }, { index: 3 }]
    const wrapper = mount(WarehousePackingReview, { props: { rows: others, selected: others } })
    expect(wrapper.findAll('tbody tr')).toHaveLength(2)
    expect(wrapper.text()).toContain('同箱箱数不一致')
    expect(wrapper.text()).toContain('带入 1 个包装组')
    expect(wrapper.text()).toContain('1 行未填箱号')
  })
})
