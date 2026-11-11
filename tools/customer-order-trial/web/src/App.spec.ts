import { enableAutoUnmount, flushPromises, mount } from '@vue/test-utils'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import App from './App.vue'
import ExistingOrderLink from './ExistingOrderLink.vue'
const mock = vi.hoisted(() => ({ config: vi.fn(), preview: vi.fn(), export: vi.fn(), save: vi.fn(), list: vi.fn() }))
vi.mock('./api', () => ({ api: mock, errorMessage: async (error: Error) => error.message }))
vi.mock('@/api/customerOrderLedger', () => ({ customerOrderLedgerApi: { importConfirmed: mock.save, list: mock.list } }))
vi.mock('@/components/modules/sales/customer-order-center/CustomerOrderLedger.vue', () => ({ default: { name: 'CustomerOrderLedger', props: ['factoryId', 'factoryName', 'historyImportEnabled', 'localOnly'], template: '<div>本机订单台账</div>' } }))
vi.mock('@/components/modules/sales/customer-order-center/CustomerOrderSchedule.vue', () => ({ default: { template: '<div>各客排期</div>' } }))
vi.mock('./LocalInbox.vue', () => ({ default: { template: '<div>本机部门收件</div>' } }))
vi.mock('./ExportHistory.vue', () => ({ default: { template: '<div>历史</div>' } }))
enableAutoUnmount(afterEach)
const configuration = { factory_id: 'huaxing', factory_name: '华兴', customers: [{ code: 'dickie', name: 'Dickie', po_extensions: ['.pdf'], schedule_extensions: ['.xlsx'] }], capabilities: { history_import: true, ledger_schedule: true, workbook_tools: true }, limits: { po_files: 30, po_bytes: 999999, batch_po_bytes: 9999999, schedule_bytes: 999999 } }
const issue = { severity: 'blocked', code: 'missing_price', field: '单价', message: '单价需要人工核对', can_skip: false, skip_key: 'price-1', skip_label: '', can_edit: true, edit_field: 'po_unit_prices', edit_label: '各 PO 单价' }
function result(blocked = false) { return { factory_id: 'huaxing', customer_code: 'dickie', preview_fingerprint: 'fingerprint-1', po_file_count: 1, output_file_name: 'Dickie.xlsx', warnings: [], summary: { valid: blocked ? 0 : 1, warning: 0, blocked: blocked ? 1 : 0 }, rows: [{ id: 'row-1', status: blocked ? 'blocked' : 'valid', status_label: blocked ? '阻断' : '有效', po_no: '00001', product_no: '00123', quantity: '0100', unit_price_hkd: '', issues: blocked ? [issue] : [], lineage: {} }] } }
beforeEach(() => { vi.resetAllMocks(); mock.config.mockResolvedValue(configuration); mock.preview.mockResolvedValue(result()); vi.stubGlobal('URL', { createObjectURL: vi.fn(() => 'blob:trial'), revokeObjectURL: vi.fn() }); vi.spyOn(HTMLAnchorElement.prototype, 'click').mockImplementation(() => {}) })
afterEach(() => { vi.unstubAllGlobals(); vi.restoreAllMocks() })
async function prepare() {
  const wrapper = mount(App)
  await flushPromises()
  await wrapper.get('[data-testid=customer]').setValue('dickie')
  const po = wrapper.get('[data-testid=po-files]')
  Object.defineProperty(po.element, 'files', { value: [new File(['po'], '0001.pdf')], configurable: true })
  await po.trigger('change')
  const schedule = wrapper.get('[data-testid=schedule-file]')
  Object.defineProperty(schedule.element, 'files', { value: [new File(['sheet'], '排期.xlsx')], configurable: true })
  await schedule.trigger('change')
  await wrapper.findAll('button').find(button => button.text() === '解析并进入预览')!.trigger('click')
  await flushPromises()
  return wrapper
}
describe('factory trial operations', () => {
  it.each([false, true])('only reconciles quantity when the selected target matches (other blocker: %s)', async (otherBlocker) => {
    const data = result(true)
    mock.preview.mockResolvedValue({ ...data, rows: [{ ...data.rows[0], reference_no: 'REF-001', issues: [
      { ...issue, code: 'existing_quantity_conflict', field: 'quantity', can_edit: false, message: '相同订单数量不同' },
      ...(otherBlocker ? [{ ...issue, code: 'order_type_unresolved', field: 'order_type', can_edit: false, message: '订单类型无法确认' }] : []),
    ] }] })
    const line = { id: 'matching', factory_id: 'huaxing', customer_code: 'dickie', reference_no: 'REF-001', product_no: '00123', quantity: '50', status: 'active', revision: 7 }
    mock.list.mockResolvedValue({ items: [line, { ...line, id: 'other-reference', reference_no: 'OTHER-REF' }], total: 2 })
    mock.save.mockResolvedValue({ items: [], created_count: 0, existing_count: 0, reconciled_count: 1 })
    const wrapper = await prepare()
    const save = wrapper.get('[data-testid=save]')
    const generate = wrapper.get('[data-testid=export]')
    expect(save.attributes('disabled')).toBeDefined()
    const link = wrapper.getComponent(ExistingOrderLink)
    await link.get('input[type=checkbox]').setValue(true)
    await flushPromises()
    await link.get('textarea').setValue('核对原订单数量修订')
    expect(save.attributes('disabled')).toBeDefined()
    await link.get('select').setValue('other-reference')
    expect(save.attributes('disabled')).toBeDefined()
    await link.get('select').setValue('matching')
    expect(generate.attributes('disabled')).toBeDefined()
    if (otherBlocker) {
      expect(save.attributes('disabled')).toBeDefined()
      await save.trigger('click')
      expect(mock.save).not.toHaveBeenCalled()
    } else {
      expect(save.attributes('disabled')).toBeUndefined()
      await save.trigger('click')
      await flushPromises()
      const body = mock.save.mock.calls[0]![1] as FormData
      expect(body.get('reconcile_line_id')).toBe('matching')
      expect(body.get('expected_revision')).toBe('7')
      expect(body.get('skipped_issue_keys')).toBe('[]')
    }
    expect(mock.export).not.toHaveBeenCalled()
  })

  it('keeps pending fields blank without confirmation and requires a reason only after editing', async () => {
    const pending = { ...issue, severity: 'warning', code: 'missing_ship_date', field: 'requested_ship_date', message: '客户交期待补', pending_information: true, can_skip: true, edit_field: 'requested_ship_date', edit_label: '客户交期', edit_input_type: 'date' }
    const data = result()
    mock.preview.mockResolvedValue({ ...data, rows: [{ ...data.rows[0], status: 'warning', status_label: '待补', requested_ship_date: '', issues: [pending] }] })
    mock.save.mockResolvedValue({ items: [], created_count: 1, existing_count: 0, reconciled_count: 0 })
    const wrapper = await prepare()
    expect(wrapper.get('[data-testid=pending-information]').text()).toContain('客户交期待补')
    expect(wrapper.find('.issue input[type=checkbox]').exists()).toBe(false)
    expect(wrapper.find('.reason').exists()).toBe(false)
    expect(wrapper.get('[data-testid=save]').attributes('disabled')).toBeUndefined()
    expect(wrapper.get('[data-testid=export]').attributes('disabled')).toBeUndefined()
    await wrapper.get('[data-testid=save]').trigger('click')
    await flushPromises()
    const body = mock.save.mock.calls[0]![1] as FormData
    expect(body.get('manual_overrides')).toBe('[]')
    expect(body.get('skipped_issue_keys')).toBe('[]')
    expect((wrapper.get('.issue input[type=date]').element as HTMLInputElement).value).toBe('')
    await wrapper.get('.issue input[type=date]').setValue('2027-01-01')
    expect(wrapper.find('[data-testid=pending-information]').exists()).toBe(false)
    expect(wrapper.get('[data-testid=save]').attributes('disabled')).toBeDefined()
    await wrapper.get('.reason textarea').setValue('客户已确认交期')
    expect(wrapper.get('[data-testid=save]').attributes('disabled')).toBeUndefined()
  })

  it('does not classify other warnings or hard blockers as pending information', async () => {
    const data = result(true)
    mock.preview.mockResolvedValue({ ...data, rows: [{ ...data.rows[0], issues: [{ ...issue, pending_information: true }, { ...issue, severity: 'warning', pending_information: false, code: 'ocr_review', message: '请核对OCR' }] }] })
    const wrapper = await prepare()
    expect(wrapper.find('[data-testid=pending-information]').exists()).toBe(false)
    expect(wrapper.get('[data-testid=save]').attributes('disabled')).toBeDefined()
    expect(wrapper.get('[data-testid=export]').attributes('disabled')).toBeDefined()
  })
  it('requires the original blocking controls and reason; rejected save preserves all inputs', async () => {
    mock.preview.mockResolvedValue(result(true))
    mock.save.mockRejectedValue(new Error('保存未完成，请核对本机台账'))
    const wrapper = await prepare()
    expect(wrapper.get('[data-testid=save]').attributes('disabled')).toBeDefined()
    expect(wrapper.find('.issue input[type=checkbox]').exists()).toBe(false)
    await wrapper.get('.issue textarea').setValue('00001=007.15000')
    expect(wrapper.get('[data-testid=save]').attributes('disabled')).toBeDefined()
    await wrapper.get('.reason textarea').setValue('按客户原件核对')
    await wrapper.get('[data-testid=save]').trigger('click')
    await flushPromises()
    const body = mock.save.mock.calls[0]![1] as FormData
    expect(body.get('factory_id')).toBe('huaxing')
    expect(body.get('source_kind')).toBe('formal')
    expect(body.get('preview_fingerprint')).toBe('fingerprint-1')
    expect(JSON.parse(String(body.get('manual_overrides')))).toEqual([{ row_id: 'row-1', issue_key: 'price-1', field: 'po_unit_prices', value: '00001=007.15000' }])
    expect((wrapper.get('.issue textarea').element as HTMLTextAreaElement).value).toBe('00001=007.15000')
    expect(wrapper.text()).toContain('保存未完成，请核对本机台账')
    expect(wrapper.text()).not.toContain('本机订单保存完成')
    expect(mock.export).not.toHaveBeenCalled()
  })
  it('matches existing orders using the effective manually corrected product number', async () => {
    const data = result(true)
    data.rows[0]!.product_no = ''
    data.rows[0]!.issues = [{ ...issue, code: 'missing_product', field: '货号', message: '请补录完整货号', skip_key: 'product-1', edit_field: 'product_no', edit_label: '完整货号' }]
    mock.preview.mockResolvedValue(data)
    const wrapper = await prepare()
    expect(wrapper.getComponent(ExistingOrderLink).props('productNo')).toBe('')
    await wrapper.get('.issue input').setValue(' F11-AB123-A123 ')
    expect(wrapper.getComponent(ExistingOrderLink).props('productNo')).toBe('F11-AB123-A123')
    await wrapper.get('.issue input').setValue('')
    expect(wrapper.getComponent(ExistingOrderLink).props('productNo')).toBe('')
  })

  it('counts actual detail rows for reconciliation and applies the detail manual product', async () => {
    const data = result(true)
    const detail = { ...data.rows[0]!, id: 'detail-1', product_no: 'DETAIL-001', row_role: 'detail', issues: [{ ...issue, field: '货号', message: '请核对完整货号', edit_field: 'product_no', edit_label: '完整货号' }] }
    mock.preview.mockResolvedValue({ ...data, rows: [{ ...detail, id: 'parent', product_no: 'PARENT-001', row_role: 'parent', issues: [] }, detail] })
    const wrapper = await prepare()
    expect(wrapper.getComponent(ExistingOrderLink).props()).toMatchObject({ eligible: true, productNo: 'DETAIL-001' })
    await wrapper.get('.issue input').setValue('DETAIL-002')
    expect(wrapper.getComponent(ExistingOrderLink).props('productNo')).toBe('DETAIL-002')
    mock.preview.mockResolvedValue({ ...data, rows: [{ ...detail, id: 'parent', row_role: 'parent', issues: [] }, detail, { ...detail, id: 'detail-2' }] })
    await wrapper.findAll('button').find(button => button.text() === '解析并进入预览')!.trigger('click')
    await flushPromises()
    expect(wrapper.getComponent(ExistingOrderLink).props('eligible')).toBe(false)
  })

  it('keeps save and export separate and only reports persisted counts after success', async () => {
    mock.save.mockResolvedValue({ items: [], created_count: 1, existing_count: 0, reconciled_count: 0 })
    const wrapper = await prepare()
    await wrapper.get('[data-testid=save]').trigger('click')
    await flushPromises()
    expect(wrapper.text()).toContain('新增 1 条，已有 0 条')
    expect(mock.export).not.toHaveBeenCalled()
    await wrapper.findAll('button').find(button => button.text() === '订单台账与走货')!.trigger('click')
    expect(wrapper.findComponent({ name: 'CustomerOrderLedger' }).props()).toMatchObject({ factoryId: 'huaxing', historyImportEnabled: true, localOnly: true })
    expect(wrapper.text()).toContain('不会通知线上员工')
  })
  it('rejects a different factory preview and cannot confirm it', async () => {
    mock.preview.mockResolvedValue({ ...result(), factory_id: 'huadeng' })
    const wrapper = await prepare()
    expect(wrapper.text()).toContain('返回的预览与当前厂区或客户不一致')
    expect(wrapper.find('[data-testid=save]').exists()).toBe(false)
  })
  it('prevents duplicate export clicks and offers a persistent download link', async () => {
    let finish: (value: unknown) => void = () => {}
    mock.export.mockImplementation(() => new Promise(resolve => { finish = resolve }))
    const wrapper = await prepare()
    await wrapper.get('[data-testid=export]').trigger('click')
    await wrapper.get('[data-testid=export]').trigger('click')
    expect(mock.export).toHaveBeenCalledTimes(1)
    expect(mock.save).not.toHaveBeenCalled()
    finish({ blob: new Blob(['xlsx']), fileName: 'Dickie排期.xlsx', passwordRequired: false })
    await flushPromises()
    expect(wrapper.get('a[download]').attributes('download')).toBe('Dickie排期.xlsx')
    expect(wrapper.text()).toContain('不代表订单已入台账')
  })
})
