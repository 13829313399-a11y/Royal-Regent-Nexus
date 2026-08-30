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

  it('prints the original engineering submitter as the order creator', () => {
    const record = createRecord(1)
    const sourceAudit = record.audit_logs[0]

    record.order.eng_name = '杨敬作'
    record.audit_logs = [
      {
        ...sourceAudit,
        id: `${record.order.id}-audit-resubmit`,
        action: '工程提交主管审核',
        actor_name: '重新提交账号',
        created_at: '2026-07-06 17:20',
      },
      {
        ...sourceAudit,
        id: `${record.order.id}-audit-opening`,
        action: '工程提交主管审核',
        actor_name: '华兴工程师',
        created_at: '2026-07-06 16:55',
      },
    ]

    const wrapper = mount(MoldingSampleProductionPrintDocument, {
      props: {
        records: [record],
      },
    })

    expect(wrapper.get('[data-testid="molding-sample-production-print-creator"]').text()).toBe('华兴工程师')
    expect(wrapper.get('[data-testid="molding-sample-production-print-created-at"]').text()).toBe('2026-07-06 16:55')
    expect(wrapper.text()).toContain('下单人')
    expect(wrapper.text()).toContain('开单时间')
    expect(wrapper.text()).not.toContain('杨敬作')
  })

  it('falls back to the engineering name when legacy records have no opening audit', () => {
    const record = createRecord(1)

    record.order.eng_name = '杨敬作'
    record.audit_logs = []

    const wrapper = mount(MoldingSampleProductionPrintDocument, {
      props: {
        records: [record],
      },
    })

    expect(wrapper.get('[data-testid="molding-sample-production-print-creator"]').text()).toBe('杨敬作')
  })
})
