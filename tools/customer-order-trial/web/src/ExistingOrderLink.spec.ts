import { enableAutoUnmount, flushPromises, mount } from '@vue/test-utils'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import ExistingOrderLink from './ExistingOrderLink.vue'
const api = vi.hoisted(() => ({ list: vi.fn() }))
vi.mock('@/api/customerOrderLedger', () => ({ customerOrderLedgerApi: api }))
vi.mock('./api', () => ({ getApiErrorMessage: (error: Error) => error.message }))
enableAutoUnmount(afterEach)
beforeEach(() => vi.resetAllMocks())
describe('existing-order reconciliation', () => {
  it('only allows the same factory, customer and full product, and carries the selected revision', async () => {
    const line = { id: 'valid', factory_id: 'huaxing', customer_code: 'dickie', product_no: '00123-A', status: 'active', reference_no: '00001', quantity: '100', revision: 7 }
    api.list.mockResolvedValue({ total: 5, items: [line, { ...line, id: 'factory', factory_id: 'huadeng' }, { ...line, id: 'customer', customer_code: 'buzzbee' }, { ...line, id: 'short-product', product_no: '00123' }, { ...line, id: 'cancelled', status: 'cancelled' }] })
    const wrapper = mount(ExistingOrderLink, { props: { factoryId: 'huaxing', customerCode: 'dickie', productNo: '00123-A', eligible: true, disabled: false, modelValue: { enabled: false, lineId: '', expectedRevision: 0, reason: '' } } })
    await wrapper.get('input[type=checkbox]').setValue(true)
    await flushPromises()
    expect(wrapper.emitted('update:modelValue')?.at(-1)?.[0]).toMatchObject({ enabled: true })
    await wrapper.setProps({ modelValue: { enabled: true, lineId: '', expectedRevision: 0, reason: '' } })
    expect(wrapper.findAll('option').map(option => option.attributes('value'))).toEqual(['', 'valid'])
    await wrapper.get('select').setValue('valid')
    expect(wrapper.emitted('update:modelValue')?.at(-1)?.[0]).toMatchObject({ enabled: true, lineId: 'valid', expectedRevision: 7 })
    await wrapper.setProps({ eligible: false })
    expect(wrapper.emitted('update:modelValue')?.at(-1)?.[0]).toEqual({ enabled: false, lineId: '', expectedRevision: 0, reason: '' })
  })
})

describe('EDU historical product reconciliation', () => {
  async function candidates(customerCode: string, productNo: string, productNumbers: string[]) {
    api.list.mockResolvedValue({ total: productNumbers.length, items: productNumbers.map((product, index) => ({
      id: String(index), factory_id: 'huaxing', customer_code: customerCode, product_no: product,
      status: 'active', reference_no: `PO-${index}`, quantity: '100', revision: 3,
    })) })
    const wrapper = mount(ExistingOrderLink, { props: { factoryId: 'huaxing', customerCode, productNo, eligible: true, disabled: false,
      modelValue: { enabled: false, lineId: '', expectedRevision: 0, reason: '' } } })
    await wrapper.get('input[type=checkbox]').setValue(true)
    await flushPromises()
    await wrapper.setProps({ modelValue: { enabled: true, lineId: '', expectedRevision: 0, reason: '' } })
    return wrapper
  }
  it('offers the historical EDU F11 four-digit tail for a normalized formal PO without shortening unrelated shapes', async () => {
    const wrapper = await candidates('edu', ' f11-ab123-a123 ', [
      ' F11-AB123-A1234567 ', 'f11-ab123-a123', 'F11-AB123-A123456', 'F11-AB123-A12345678', 'F13-AB123-A1234567', 'F11-AB123-A1244567',
    ])
    expect(wrapper.findAll('option').map(option => option.attributes('value'))).toEqual(['', '0', '1'])
    expect(wrapper.text()).toContain('F11-AB123-A1234567')
    await wrapper.get('select').setValue('0')
    expect(wrapper.emitted('update:modelValue')?.at(-1)?.[0]).toMatchObject({ lineId: '0', expectedRevision: 3 })
  })
  it('also handles the evidenced F12 numeric base when the incoming PO retains its tail', async () => {
    const wrapper = await candidates('edu', 'F12-ZZ007-00011234', ['f12-zz007-0001', 'F12-ZZ007-00019876', 'F12-ZZ007-0002'])
    expect(wrapper.findAll('option').map(option => option.attributes('value'))).toEqual(['', '0', '1'])
    const unsupported = await candidates('edu', 'F13-AB123-A123', ['F13-AB123-A123', 'F13-AB123-A1234567'])
    expect(unsupported.findAll('option').map(option => option.attributes('value'))).toEqual(['', '0'])
  })
  it('ignores casing and outer spaces for other customers while preserving every suffix character', async () => {
    const wrapper = await candidates('dickie', ' f11-ab123-a123 ', [' F11-AB123-A123 ', 'F11-AB123-A1234567', 'F11-AB123-A12'])
    expect(wrapper.findAll('option').map(option => option.attributes('value'))).toEqual(['', '0'])
  })
})
