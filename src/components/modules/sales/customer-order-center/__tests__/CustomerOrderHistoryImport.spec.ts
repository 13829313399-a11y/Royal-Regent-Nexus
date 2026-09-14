import { flushPromises, mount } from '@vue/test-utils'
import { describe, expect, it, vi } from 'vitest'
import CustomerOrderHistoryImport from '../CustomerOrderHistoryImport.vue'

const historyApi = vi.hoisted(() => ({ customers: vi.fn(), preview: vi.fn(), confirm: vi.fn() }))
const ledgerApi = vi.hoisted(() => ({ capabilities: vi.fn() }))
vi.mock('@/api/customerOrderHistory', () => ({ customerOrderHistoryApi: historyApi }))
vi.mock('@/api/customerOrderLedger', () => ({ customerOrderLedgerApi: ledgerApi }))

const preview = {
  factory_id: 'huaxing', customer_code: 'buzzbee', customer_name: 'BuzzBee', file_name: 'history.xlsx', fingerprint: 'history-fp', warnings: ['请核对源表'],
  summary: { total: 2, blocked: 0, existing: 0 },
  rows: [
    { id: 'row-1', sheet: '未走货', row: 8, section: 'unshipped' as const, reference_no: 'PO-001', product_no: '00123', quantity: '10.25', requested_ship_date: '2026-10-01', customer_name: 'BuzzBee', issues: [], blocked: false, existing: false, data: { history_fields: [{ column: 'A', header: '客户 P/O', value: 'PO-001' }] } },
    { id: 'row-2', sheet: '已走货', row: 9, section: 'shipped' as const, reference_no: 'PO-002', product_no: '00124', quantity: '5', requested_ship_date: '', customer_name: 'BuzzBee', issues: [], blocked: false, existing: false, data: {} },
  ],
}

function setup() {
  historyApi.customers.mockResolvedValue({ items: [{ code: 'buzzbee', name: 'BuzzBee' }] })
  ledgerApi.capabilities.mockResolvedValue({ read: true, write: true, dispatch: false, shipment_confirm: true, inbox_read: false, inbox_receive: false })
  return mount(CustomerOrderHistoryImport, { props: { factoryId: 'huaxing' } })
}

async function previewFile(wrapper: ReturnType<typeof setup>) {
  await flushPromises()
  await wrapper.get('select').setValue('buzzbee')
  const file = new File(['schedule'], 'history.xlsx')
  const fileInput = wrapper.get('[data-testid="history-file"]')
  Object.defineProperty(fileInput.element, 'files', { value: [file] })
  await fileInput.trigger('change')
  historyApi.preview.mockResolvedValue(preview)
  await wrapper.get('button.history-import__button--primary').trigger('click')
  await flushPromises()
  return file
}

describe('CustomerOrderHistoryImport', () => {
  it('keeps every selected row baseline blank until an explicit user action and requires acknowledgement before confirm', async () => {
    const wrapper = setup()
    const file = await previewFile(wrapper)
    expect(historyApi.preview).toHaveBeenCalledWith('huaxing', 'buzzbee', file)
    const rowCheckbox = wrapper.findAll('tbody input[type="checkbox"]')[0]!
    await rowCheckbox.setValue(true)
    const opening = wrapper.get('input[placeholder="明确填写 0 至数量"]')
    expect((opening.element as HTMLInputElement).value).toBe('')
    expect((wrapper.get('tbody select[aria-label="迁入状态"]').element as HTMLSelectElement).value).toBe('')
    await wrapper.findAll('button').find((button) => button.text() === '确认迁入已选记录')!.trigger('click')
    await flushPromises()
    expect(historyApi.confirm).not.toHaveBeenCalled()
    expect(wrapper.text()).toContain('明确选择')

    await wrapper.findAll('button').find((button) => button.text() === '所选未走货订单期初走货设为 0')!.trigger('click')
    await wrapper.get('tbody select[aria-label="迁入状态"]').setValue('cancelled')
    expect(wrapper.text()).toContain('后续可走货 0')
    await wrapper.get('input[type="date"]').setValue('2026-09-30')
    await wrapper.get('textarea').setValue('迁入历史排期')
    await wrapper.get('.history-import__acknowledge input').setValue(true)
    historyApi.confirm.mockResolvedValue({ created_count: 1, existing_count: 0, items: [] })
    await wrapper.findAll('button').find((button) => button.text() === '确认迁入已选记录')!.trigger('click')
    await flushPromises()
    expect(historyApi.confirm).toHaveBeenCalledWith('huaxing', 'buzzbee', file, expect.objectContaining({
      cutoff_date: '2026-09-30', reason: '迁入历史排期', fingerprint: 'history-fp',
      selections: [{ id: 'row-1', status: 'cancelled', opening_shipped_quantity: '0' }],
    }))
    expect(wrapper.emitted('saved')).toHaveLength(1)
  })

  it('drops a stale preview when the factory changes', async () => {
    const wrapper = setup()
    await flushPromises()
    await wrapper.get('select').setValue('buzzbee')
    const file = new File(['schedule'], 'history.xlsx')
    const fileInput = wrapper.get('[data-testid="history-file"]')
    Object.defineProperty(fileInput.element, 'files', { value: [file] })
    await fileInput.trigger('change')
    let resolvePreview: ((value: typeof preview) => void) | undefined
    historyApi.preview.mockImplementationOnce(() => new Promise((resolve) => { resolvePreview = resolve }))
    await wrapper.get('button.history-import__button--primary').trigger('click')
    await wrapper.setProps({ factoryId: 'huakang-a' })
    resolvePreview?.(preview)
    await flushPromises()
    expect(wrapper.text()).not.toContain('PO-001')
    expect(historyApi.customers).toHaveBeenLastCalledWith('huakang-a')
  })

  it('does not display a preview returned for another factory or customer scope', async () => {
    const wrapper = setup()
    await flushPromises()
    await wrapper.get('select').setValue('buzzbee')
    const file = new File(['schedule'], 'history.xlsx')
    const fileInput = wrapper.get('[data-testid="history-file"]')
    Object.defineProperty(fileInput.element, 'files', { value: [file] })
    await fileInput.trigger('change')
    historyApi.preview.mockResolvedValue({ ...preview, factory_id: 'huakang-a' })
    await wrapper.get('button.history-import__button--primary').trigger('click')
    await flushPromises()
    expect(wrapper.text()).toContain('范围不匹配')
    expect(wrapper.find('.history-import__table-wrap').exists()).toBe(false)
  })
})
