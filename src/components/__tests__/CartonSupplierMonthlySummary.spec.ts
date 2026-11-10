import { flushPromises, mount } from '@vue/test-utils'
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
  factory_id: 'huaxing', supplier_name: '东康', period: new Date().toLocaleDateString('sv-SE', { timeZone: 'Asia/Shanghai' }).slice(0, 7), currency: 'CNY', read_only: true,
  status: 'OPEN', stale: false, locked_at: null, submitted_at: null, supplier_confirmed_at: null,
  disputed_reason: '', can_confirm: false, can_dispute: false,
  totals: { inbound: '1380.00', returns: '0.00', refunds: '0.00', net: '1380.00', documents: 2, receipt_lines: 3, return_lines: 0, refund_lines: 0 },
  lines: [line({}), line({ source_key: 'RECEIPT:2', document_no: 'DN-2', item_no: 'ITEM-2', amount: '1060.00' }),
    line({ source_key: 'RETURN:1', kind: 'RETURN', document_no: 'RT-1', quantity: '20', unit_price: '3.20', amount: '64.00' })],
  ...overrides,
})

beforeEach(() => { monthlyMock.mockReset() })

it('includes verified cash refunds in the source formula without displaying a goods quantity', async () => {
  const data = summary()
  monthlyMock.mockResolvedValue({
    ...data,
    totals: { ...data.totals, returns: '64.00', refunds: '9.00', net: '1325.00', refund_lines: 1 },
    lines: [line({ source_key: 'REFUND:1', kind: 'RETURN_REFUND', document_no: 'CASH-1', quantity: '0', amount: '9.00' })],
  })
  const wrapper = mount(Component, { props: { factories: [{ factory_id: 'huaxing' }] } }); await flushPromises()
  expect(wrapper.text()).toContain('1,325.00 人民币')
  expect(wrapper.text()).toContain('本月已核实现金退款')
  expect(wrapper.text()).toContain('已核实退款 9.00')
  const refund = wrapper.get('tbody tr')
  expect(refund.text()).toContain('CASH-1')
  expect(refund.findAll('td')[5]?.text()).toBe('—')
  wrapper.unmount()
})

it('clears prior figures while the replacement viewer loads and rejects a different factory response', async () => {
  monthlyMock.mockResolvedValueOnce(summary())
  let done!: (value: ReturnType<typeof summary>) => void
  monthlyMock.mockImplementationOnce(() => new Promise(resolve => { done = resolve }))
  const wrapper = mount(Component, { props: { factories: [{ factory_id: 'huaxing' }], viewerKey: 'first' } }); await flushPromises()
  expect(wrapper.text()).toContain('1,380.00')
  await wrapper.setProps({ viewerKey: 'second' })
  expect(wrapper.text()).not.toContain('1,380.00')
  done(summary({ factory_id: 'huakang-a' })); await flushPromises()
  expect(wrapper.get('[role="alert"]').text()).toContain('与当前厂区、月份或币种不一致')
  expect(wrapper.text()).not.toContain('DN-1')
  wrapper.unmount()
})

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
