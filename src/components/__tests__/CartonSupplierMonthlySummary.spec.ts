import { mount } from '@vue/test-utils'
import { beforeEach, expect, it, vi } from 'vitest'

const { monthlyMock } = vi.hoisted(() => ({ monthlyMock: vi.fn() }))
vi.mock('@/api/cartonSupplierSettlement', () => ({ supplierSettlementApi: { supplierMonthlyWorkspace: monthlyMock } }))

import Component from '../CartonSupplierMonthlySummary.vue'

const line = (overrides: Record<string, unknown> = {}) => ({
  source_key: 'RECEIPT:1', kind: 'RECEIPT', document_no: 'DN-1', acceptance_date: '2026-10-02',
  customer_name: 'Dickie', contract_no: 'SC-1', item_no: 'ITEM-1', packaging_type: '外箱',
  unit: '个', quantity: '100', unit_price: '3.20', amount: '320.00', currency: 'CNY', issues: [],
  ...overrides,
})

const summary = (overrides: Record<string, unknown> = {}) => ({
  factory_id: 'huaxing', supplier_name: '东康', period: '2026-10', currency: 'CNY', read_only: true,
  status: 'OPEN', stale: false, locked_at: null, submitted_at: null, supplier_confirmed_at: null,
  disputed_reason: '', can_confirm: false, can_dispute: false,
  totals: { inbound: '1380.00', returns: '0.00', refunds: '0.00', net: '1380.00', documents: 2, receipt_lines: 3, return_lines: 0, refund_lines: 0 },
  lines: [line({}), line({ source_key: 'RECEIPT:2', document_no: 'DN-2', item_no: 'ITEM-2', amount: '1060.00' }),
    line({ source_key: 'RETURN:1', kind: 'RETURN', document_no: 'RT-1', quantity: '20', unit_price: '3.20', amount: '64.00' })],
  ...overrides,
})

beforeEach(() => { monthlyMock.mockReset() })

it('shows a read-only month with Chinese factory and currency labels', async () => {
  monthlyMock.mockResolvedValue(summary())
  const wrapper = mount(Component, { props: { factories: [{ factory_id: 'huaxing' }, { factory_id: 'huakang-a' }] } })
  await new Promise(resolve => setTimeout(resolve, 0)); await wrapper.vm.$nextTick()
  expect(monthlyMock).toHaveBeenCalledWith('huaxing', expect.any(String), 'CNY')
  expect(wrapper.get('[aria-label="供应商对账厂区"]').findAll('option').map(option => option.text())).toEqual(['华兴', '华康A'])
  expect(wrapper.get('[aria-label="供应商对账币种"]').findAll('option').map(option => option.text())).toEqual(['人民币', '港币', '美元'])
  const text = wrapper.text()
  expect(text).toContain('1,380.00')
  expect(text).toContain('人民币')
  expect(text).toContain('DN-1')
  expect(text).toContain('只读对账')
  const labels = wrapper.findAll('button').map(button => button.text())
  expect(labels).not.toContain('确认本月金额')
  expect(labels).not.toContain('提出异议')
  wrapper.unmount()
})

it('filters the shared lines with the page search without confirmation controls', async () => {
  monthlyMock.mockResolvedValue(summary())
  const wrapper = mount(Component, { props: { factories: [{ factory_id: 'huaxing' }] } })
  await new Promise(resolve => setTimeout(resolve, 0)); await wrapper.vm.$nextTick()
  expect(wrapper.get('[aria-label="供应商本月对账明细"]').text()).toContain('DN-2')
  await wrapper.setProps({ search: 'DN-2' }); await wrapper.vm.$nextTick()
  const table = wrapper.get('[aria-label="供应商本月对账明细"]').text()
  expect(table).toContain('DN-2')
  expect(table).not.toContain('RT-1')
  expect(wrapper.findAll('button').map(button => button.text())).not.toContain('提出异议')
  wrapper.unmount()
})
