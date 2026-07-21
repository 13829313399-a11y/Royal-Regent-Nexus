import { mount } from '@vue/test-utils'
import { describe, expect, it } from 'vitest'
import MoldingSampleEngineeringPrintDocument from '../MoldingSampleEngineeringPrintDocument.vue'
import MoldingSampleProductionPrintDocument from '../MoldingSampleProductionPrintDocument.vue'
import { getMoldingSampleRecord } from '@/data/moldingSampleWorkflowMock'
import type { MoldingSampleWorkflowRecord } from '@/types/moldingSample'

function createRecord(itemCount: number): MoldingSampleWorkflowRecord {
  const source = getMoldingSampleRecord('huaxing')
  const record = structuredClone(source)
  const sourceItem = record.items[0]

  record.order.id = `BP-PRINT-${String(itemCount).padStart(2, '0')}`
  record.order.product_name = `${itemCount}套模具产品`
  record.items = Array.from({ length: itemCount }, (_, index) => ({
    ...structuredClone(sourceItem),
    id: `${record.order.id}-${String(index + 1).padStart(3, '0')}`,
    order_id: record.order.id,
    sort_order: index + 1,
    mold_id: `MOLD-${index + 1}`,
    mold_name: `打印模具${index + 1}`,
  }))

  return record
}

describe('shared molding-sample print documents', () => {
  it.each([1, 4, 8, 12])('renders %i engineering mold rows without hiding cost fields', (itemCount) => {
    const wrapper = mount(MoldingSampleEngineeringPrintDocument, {
      props: {
        records: [createRecord(itemCount)],
        materialPrices: [],
      },
    })

    expect(wrapper.findAll('[data-testid="molding-sample-engineering-print-row"]')).toHaveLength(itemCount)
    expect(wrapper.text()).toContain('预计料费(HKD)')
    expect(wrapper.text()).toContain('实际料费(HKD)')
    expect(wrapper.text()).not.toContain('签核栏')
    expect(wrapper.text()).not.toContain('来源厂 → 承接生产厂')
  })

  it.each([1, 4, 8, 12])('renders %i production mold rows with engineering handoff fields only', (itemCount) => {
    const wrapper = mount(MoldingSampleProductionPrintDocument, {
      props: {
        records: [createRecord(itemCount)],
      },
    })

    expect(wrapper.findAll('[data-testid="molding-sample-production-print-row"]')).toHaveLength(itemCount)
    expect(wrapper.text()).toContain('啤机部生产任务单')
    expect(wrapper.text()).toContain('注意事项 / 开单事由')
    expect(wrapper.text()).toContain('工程模具明细')
    expect(wrapper.text()).not.toContain('回模')
    expect(wrapper.text()).not.toContain('派厂时间')
    expect(wrapper.text()).not.toContain('实际料费(HKD)')
  })
})
