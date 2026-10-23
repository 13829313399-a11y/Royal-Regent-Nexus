import { mount } from '@vue/test-utils'
import { beforeEach, expect, it, vi } from 'vitest'

const { workspaceMock } = vi.hoisted(() => ({ workspaceMock: vi.fn() }))
vi.mock('@/api/cartonSupplierSettlement', () => ({
  supplierSettlementApi: { monthlyWorkspace: workspaceMock },
}))

import Component from '../CartonSettlementOverview.vue'

const line = (overrides: Record<string, unknown> = {}) => ({
  source_key: 'RECEIPT:1', kind: 'RECEIPT', document_no: 'DN-1', acceptance_date: '2026-10-02', date_basis: 'ACCEPTANCE',
  customer_name: 'Dickie', contract_no: 'SC-1', item_no: 'ITEM-1', packaging_type: '外箱', paper_quality: 'A33',
  specification: '30*20*15', unit: '个', quantity: '100', unit_price: '3.20', amount: '320.00', currency: 'CNY', issues: [],
  ...overrides,
})

function settlement(overrides: Record<string, unknown> = {}) {
  return {
    factory_id: 'huaxing', supplier_id: 'SUP', supplier_name: '东康', period: '2026-10', currency: 'CNY',
    source_fingerprint: 'fingerprint', status: 'OPEN', locked_at: null, locked_by: null, locked_totals: null, stale: false,
    submitted_at: null, submitted_by: null, supplier_confirmed_at: null, supplier_confirmed_by: null,
    disputed_reason: '', unlocked_reason: '', can_submit: false, can_lock: false, read_only: true,
    totals: { inbound: '1380.00', returns: '0.00', refunds: '0.00', net: '1380.00', documents: 2, receipt_lines: 3, return_lines: 0, refund_lines: 0 },
    blockers: [], lines: [line({}), line({ source_key: 'RECEIPT:2', document_no: 'DN-1', quantity: '50', amount: '160.00' }),
      line({ source_key: 'RECEIPT:3', document_no: 'DN-2', customer_name: 'BUZZ', packaging_type: '刀卡', quantity: '200', amount: '900.00' })],
    ...overrides,
  }
}

beforeEach(() => { workspaceMock.mockReset() })

it('shows a read-only month without submit, lock or unlock actions', async () => {
  workspaceMock.mockResolvedValue(settlement())
  const wrapper = mount(Component, { props: { factoryId: 'huaxing' } })
  await new Promise(resolve => setTimeout(resolve, 0)); await wrapper.vm.$nextTick()
  expect(workspaceMock).toHaveBeenCalledWith('huaxing', expect.any(String), 'CNY')
  const text = wrapper.text()
  expect(text).toContain('本月已验收送货')
  expect(text).toContain('1,380.00')
  expect(text).toContain('人民币')
  expect(text).toContain('只读')
  expect(text).toContain('不提交、不锁定，不作为付款依据')
  const labels = wrapper.findAll('button').map(button => button.text())
  expect(labels).toContain('刷新')
  expect(labels).not.toContain('提交供应商核对')
  expect(labels).not.toContain('完成月结并锁定')
  expect(labels).not.toContain('解锁重核')
  expect(wrapper.get('[aria-label="本月对账币种"]').findAll('option').map(option => option.text())).toEqual(['人民币', '港币', '美元'])
  wrapper.unmount()
})

it('lists blocking items as reference only, without submission controls', async () => {
  workspaceMock.mockResolvedValue(settlement({ blockers: ['1 行送货单缺价，不能计入应付：DN-9 ITEM-9'] }))
  const wrapper = mount(Component, { props: { factoryId: 'huaxing' } })
  await new Promise(resolve => setTimeout(resolve, 0)); await wrapper.vm.$nextTick()
  expect(wrapper.text()).toContain('1 行送货单缺价')
  expect(wrapper.text()).toContain('暂不影响旧月结流程')
  expect(wrapper.findAll('button').map(button => button.text())).not.toContain('提交供应商核对')
  wrapper.unmount()
})

it('refreshes the read-only view without calling any write endpoint', async () => {
  workspaceMock.mockResolvedValue(settlement())
  const wrapper = mount(Component, { props: { factoryId: 'huaxing' } })
  await new Promise(resolve => setTimeout(resolve, 0)); await wrapper.vm.$nextTick()
  await wrapper.findAll('button').find(button => button.text() === '刷新')!.trigger('click')
  await new Promise(resolve => setTimeout(resolve, 0)); await wrapper.vm.$nextTick()
  expect(workspaceMock).toHaveBeenCalledTimes(2)
  expect(wrapper.text()).toContain('本月应结')
  wrapper.unmount()
})
