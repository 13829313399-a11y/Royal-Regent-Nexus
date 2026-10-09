import { flushPromises, mount } from '@vue/test-utils'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import CustomerRecognition from '../modules/qa/CartonMarkCustomerRecognition.vue'
import type { CartonMarkCustomer, CartonMarkCustomerRecognition } from '@/api/cartonMark'

const api = vi.hoisted(() => ({ recognizeCustomer: vi.fn(), customerInitializationCandidates: vi.fn(), initializeCustomers: vi.fn() }))
vi.mock('@/api/cartonMark', () => ({ cartonMarkApi: api }))
const buzz = { id: 'BUZZ', name: 'BUZZ' } as CartonMarkCustomer
const matched: CartonMarkCustomerRecognition = { status: 'MATCHED', customer_name: 'BUZZ', managed_customer_id: 'BUZZ', message: '已识别客名',
  orders: [{ id: 'O1', order_no: 'CT-1', customer_name: 'BUZZ', customer_code: 'BUZZ', contract_no: '4500222793', item_no: '12313232131' }] }
const wrappers: ReturnType<typeof mount>[] = []
function create(props: Partial<InstanceType<typeof CustomerRecognition>['$props']> = {}) {
  const wrapper = mount(CustomerRecognition, { props: { factoryId: 'huaxing', factoryName: '华兴', contractNumber: '4500222793', item: '12313232131',
    excelAssetId: 'EXCEL', pdfAssetId: 'PDF', selectedCustomer: '', customers: [buzz], allowed: true, canManage: true, ...props }, global: { stubs: { Teleport: true } } })
  wrappers.push(wrapper)
  return wrapper
}
async function settleRecognition() { await vi.advanceTimersByTimeAsync(250); await flushPromises() }
function button(wrapper: ReturnType<typeof create>, text: string) { return wrapper.findAll('button').find(item => item.text() === text)! }
beforeEach(() => {
  vi.useFakeTimers(); vi.clearAllMocks()
  api.recognizeCustomer.mockResolvedValue(structuredClone(matched))
  api.customerInitializationCandidates.mockResolvedValue([{ name: 'BUZZ', order_count: 2, customer_codes: ['BUZZ'], existing_customer_id: null, warning: '' }])
  api.initializeCustomers.mockResolvedValue({ created_names: ['BUZZ'], existing_names: [] })
})
afterEach(() => { wrappers.splice(0).forEach(wrapper => wrapper.unmount()); vi.useRealTimers() })

describe('carton order customer recognition', () => {
  it('autofills a managed customer with order evidence without writing business data', async () => {
    const wrapper = create(); await settleRecognition()
    expect(api.recognizeCustomer).toHaveBeenCalledWith('huaxing', {
      contract_number: '4500222793', item: '12313232131', excel_asset_id: 'EXCEL', pdf_asset_id: 'PDF', order_id: undefined,
    }, expect.any(AbortSignal))
    expect(wrapper.emitted('select')?.at(-1)).toEqual(['BUZZ'])
    expect(wrapper.text()).toContain('来源订单：CT-1')
    expect(api.initializeCustomers).not.toHaveBeenCalled()
  })

  it('preserves a manual choice and requires confirmation of a conflict', async () => {
    const wrapper = create({ selectedCustomer: 'Manual', customers: [buzz, { ...buzz, id: 'manual', name: 'Manual' }] })
    await settleRecognition()
    expect(wrapper.emitted('select')).toBeUndefined()
    expect(wrapper.emitted('busy')?.at(-1)).toEqual([true])
    await button(wrapper, '确认使用手选客名').trigger('click')
    expect(wrapper.emitted('busy')?.at(-1)).toEqual([false])
    await wrapper.setProps({ selectedCustomer: 'Another' })
    expect(wrapper.emitted('busy')?.at(-1)).toEqual([true])
  })

  it('requires explicit order selection for ambiguous evidence', async () => {
    api.recognizeCustomer.mockResolvedValueOnce({ ...matched, status: 'AMBIGUOUS', customer_name: '', managed_customer_id: null })
    const wrapper = create(); await settleRecognition()
    expect(wrapper.emitted('select')).toBeUndefined()
    expect(wrapper.emitted('busy')?.at(-1)).toEqual([true])
    await wrapper.get('[aria-label="选择识别客名的订单"]').setValue('O1'); await flushPromises()
    expect(api.recognizeCustomer).toHaveBeenLastCalledWith('huaxing', expect.objectContaining({ order_id: 'O1' }), expect.any(AbortSignal))
    expect(wrapper.emitted('select')?.at(-1)).toEqual(['BUZZ'])
  })

  it('keeps an identified new customer as a candidate until explicitly added and refreshed', async () => {
    api.recognizeCustomer.mockResolvedValue({ ...matched, managed_customer_id: null })
    const wrapper = create({ customers: [] }); await settleRecognition()
    expect(wrapper.emitted('select')).toBeUndefined()
    expect(api.initializeCustomers).not.toHaveBeenCalled()
    await button(wrapper, '将 BUZZ 加入客户库').trigger('click'); await flushPromises()
    expect(api.initializeCustomers).toHaveBeenCalledWith('huaxing', ['BUZZ'])
    expect(wrapper.emitted('customersChanged')).toHaveLength(1)
    expect(wrapper.emitted('select')).toBeUndefined()
    await wrapper.setProps({ customers: [buzz] })
    expect(wrapper.emitted('select')?.at(-1)).toEqual(['BUZZ'])
  })

  it('offers warehouse readers recognition while keeping initialization unavailable', async () => {
    const wrapper = create({ customers: [], canManage: false }); await settleRecognition()
    expect(wrapper.text()).toContain('请主管或管理员')
    expect(wrapper.text()).not.toContain('从本厂订单初始化客名')
    expect(api.initializeCustomers).not.toHaveBeenCalled()
    await wrapper.setProps({ allowed: false })
    expect(wrapper.find('[aria-label="订单客名识别"]').exists()).toBe(false)
  })

  it('previews without writing and imports only explicitly checked eligible names', async () => {
    api.customerInitializationCandidates.mockResolvedValue([
      { name: 'BUZZ', order_count: 2, customer_codes: ['BUZZ'], existing_customer_id: null, warning: '' },
      { name: 'ZURU', order_count: 1, customer_codes: ['ZURU'], existing_customer_id: 'ZURU', warning: '' },
      { name: 'Duplicate', order_count: 2, customer_codes: ['A', 'B'], existing_customer_id: null, warning: '客户身份有歧义' },
    ])
    const wrapper = create(); await settleRecognition()
    await button(wrapper, '从本厂订单初始化客名').trigger('click'); await flushPromises()
    expect(api.initializeCustomers).not.toHaveBeenCalled()
    const checkboxes = wrapper.findAll('input[type=checkbox]')
    expect(checkboxes[1]!.attributes('disabled')).toBeDefined()
    expect(checkboxes[2]!.attributes('disabled')).toBeDefined()
    await checkboxes[0]!.setValue(true)
    await button(wrapper, '确认加入 1 个客名').trigger('click'); await flushPromises()
    expect(api.initializeCustomers).toHaveBeenCalledWith('huaxing', ['BUZZ'])
    expect(wrapper.emitted('customersChanged')).toHaveLength(1)
  })

  it('ignores late recognition after a factory change or permission revocation', async () => {
    let finish: (value: CartonMarkCustomerRecognition) => void = () => {}
    api.recognizeCustomer.mockImplementationOnce(() => new Promise(resolve => { finish = resolve }))
    const wrapper = create(); await settleRecognition()
    await wrapper.setProps({ factoryId: 'huakang-a', allowed: false, canManage: false })
    finish(matched); await flushPromises()
    expect(wrapper.emitted('select')).toBeUndefined()
    expect(wrapper.find('[aria-label="订单客名识别"]').exists()).toBe(false)
  })

  it('discards a late initialization preview after a factory switch', async () => {
    let finish: (value: unknown) => void = () => {}
    api.customerInitializationCandidates.mockImplementationOnce(() => new Promise(resolve => { finish = resolve }))
    const wrapper = create(); await settleRecognition()
    await button(wrapper, '从本厂订单初始化客名').trigger('click'); await flushPromises()
    await wrapper.setProps({ factoryId: 'huakang-a' })
    finish([{ name: 'Foreign', order_count: 1, customer_codes: ['Foreign'], warning: '' }]); await flushPromises()
    expect(wrapper.find('[role=dialog]').exists()).toBe(false)
    expect(wrapper.text()).not.toContain('Foreign')
  })

  it('clears a prior automatic choice after fresh evidence no longer matches', async () => {
    const wrapper = create(); await settleRecognition()
    await wrapper.setProps({ selectedCustomer: 'BUZZ' })
    api.recognizeCustomer.mockResolvedValue({ ...matched, status: 'NO_MATCH', customer_name: '', orders: [] })
    await button(wrapper, '重新识别客名').trigger('click'); await flushPromises()
    expect(wrapper.emitted('select')?.at(-1)).toEqual([''])
  })
})
