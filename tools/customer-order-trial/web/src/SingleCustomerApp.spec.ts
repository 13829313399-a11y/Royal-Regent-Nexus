import { flushPromises, mount } from '@vue/test-utils'
import { afterEach, beforeEach, expect, it, vi } from 'vitest'
import SingleCustomerApp from './SingleCustomerApp.vue'
import Workspace from '@/components/modules/sales/customer-order-center/CustomerOrderCenterWorkspace.vue'
import { customerOrderApi } from './singleCustomerOrderApi'
const mocks = vi.hoisted(() => ({ config: vi.fn(), post: vi.fn() }))
vi.mock('./api', () => ({ api: { config: mocks.config }, http: { post: mocks.post },
  getApiErrorMessage: (e: Error) => e.message, getApiErrorMessageAsync: async (e: Error) => e.message,
  errorMessage: async (e: Error) => e.message }))
beforeEach(() => {
  vi.clearAllMocks()
  mocks.config.mockResolvedValue({ factory_id: 'huakang-a', customers: [{ code: 'zuru' }] })
  vi.spyOn(HTMLAnchorElement.prototype, 'click').mockImplementation(() => {})
  vi.stubGlobal('URL', { createObjectURL: () => 'blob:test', revokeObjectURL: vi.fn() })
})
afterEach(() => { vi.restoreAllMocks(); vi.unstubAllGlobals() })

it.each([['huakang-a', 'zuru'], ...['casdon','jakks','goliath','simba','spin'].map(code => ['huadeng',code])])('uses the actual GitHub workspace and exports blank dates without a waiver or warehouse sync: %s %s', async (factory, customer) => {
  mocks.config.mockResolvedValue({ factory_id: factory, customers: [{code: customer}] })
  const wrapper = mount(SingleCustomerApp)
  await flushPromises()
  expect(wrapper.getComponent(Workspace).props()).toMatchObject({ localOnly: true, customerCodes: [customer] })
  expect(wrapper.find(`[data-testid=customer-choice-${customer}]`).exists()).toBe(true)
  expect(wrapper.find('[data-testid=customer-choice-green-toys]').exists()).toBe(false)
  const files = [new File(['original html'], 'ZURU.pdf'), new File(['original schedule'], 'GT.xlsx')]
  const inputs = wrapper.findAll('input[type=file]')
  for (const [i, file] of files.entries()) {
    Object.defineProperty(inputs[i]!.element, 'files', { configurable: true, value: [file] })
    await inputs[i]!.trigger('change')
  }
  mocks.post.mockResolvedValueOnce({ data: { factory_id: factory, customer_code: customer,
    customer_name: 'ZURU', preview_fingerprint: 'blank-date', po_file_count: 1, warnings: [],
    rows: [{ id: 'gt-1', status: 'warning', status_label: '有提醒', lineage: {}, product_no: 'GT-100',
      reference_no: 'TEST-1', contract_no: 'TEST', po_no: 'TEST', customer_name: 'ZURU', customer_country: 'ZURU / 美国',
      quantity: '100', units_per_carton: '10', carton_count: '10', requested_ship_date: '',
      issues: [{ code: 'missing_ship_date', field: 'requested_ship_date', severity: 'warning',
        message: '货期待补', skip_key: 'gt-1:ship', can_edit: true, can_skip: true, pending_information: true,
        edit_field: 'requested_ship_date', edit_label: '货期', edit_input_type: 'date' }] }],
    summary: { total: 1, warning: 1, valid: 0, blocked: 0 } }, headers: {} })
  await wrapper.findAll('button').find(b => b.text().includes('解析并进入预览'))!.trigger('click')
  await flushPromises()
  expect(mocks.post.mock.calls[0]![0]).toBe('/orders/preview')
  const body = mocks.post.mock.calls[0]![1] as FormData
  expect(body.get('customer_code')).toBe(customer)
  expect(body.getAll('po_files')[0]).toBe(files[0])
  expect(wrapper.find('[data-testid=warehouse-schedule-sync]').exists()).toBe(false)
  expect(wrapper.text()).toContain('不确定的字段可先留空')
  mocks.post.mockResolvedValueOnce({ data: new Blob(['xlsx']), headers: {} })
  await wrapper.get('[data-testid=preview-next-step]').findAll('button')[0]!.trigger('click')
  await flushPromises()
  const exported = mocks.post.mock.calls[1]!
  expect(exported[0]).toBe('/orders/export')
  expect(exported[1].get('manual_overrides')).toBe('[]')
  expect(exported[1].get('confirmation_reason')).toBe('')
  expect(exported[1].get('preview_fingerprint')).toBe('blank-date')
  expect(wrapper.find('[data-testid=warehouse-schedule-sync]').exists()).toBe(false)
  wrapper.unmount()
})

it('rejects another factory or customer at the local API adapter', async () => {
  const file = new File(['x'], 'source.xlsx')
  await expect(customerOrderApi.previewMappedBatch('zuru', [file], file, '2026-11-19', 'huaxing')).rejects.toThrow('仅开放')
  await expect(customerOrderApi.previewMappedBatch('headstart', [file], file, '2026-11-19', 'huakang-a')).rejects.toThrow('仅开放')
  expect(mocks.post).not.toHaveBeenCalled()
})
