import { flushPromises, mount } from '@vue/test-utils'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import Component from '../CartonSpecialRequests.vue'
import CartonSpecialOrderActions from '../CartonSpecialOrderActions.vue'
import type { SpecialRequest, SpecialWorkspace } from '@/api/cartonSpecialRequests'

const api = vi.hoisted(() => ({ list: vi.fn(), detail: vi.fn(), save: vi.fn(), adjust: vi.fn(), manualReceive: vi.fn(), action: vi.fn(), attach: vi.fn(), download: vi.fn(), markOptions: vi.fn() }))
vi.mock('@/api/cartonSpecialRequests', () => ({ cartonSpecialRequestsApi: api }))
function fixture(patch: Partial<SpecialRequest> = {}): SpecialRequest {
  return { id: 'REQ', request_no: 'SP-01', factory_id: 'huaxing', kind: 'SAMPLE', title: '客户确认样板', requester_name: '张同事',
    status: 'SUBMITTED', revision: 1, current_version_id: 'VERSION1', quote_version_id: '', pricing_kind: 'PENDING_QUOTE', promised_date: '',
    customer_code: '', customer_name: '', workshop_id: '', purpose: '打样', required_date: '2026-10-25',
    lines: [{ id: 'L1', packaging_type: '普通箱', paper_quality: 'A=B', specification: '10*20*30', dimension_unit: 'cm', quantity: '10', unit: '个', item_no: '', received_quantity: '0', remaining_quantity: '10' }],
    attachments: [], messages: [], shipments: [], history: [], permissions: {}, ...patch }
}
function workspace(items = [fixture()], can_create = true): SpecialWorkspace {
  return { items, total: items.length, can_create, options: { customers: [{ customer_code: 'C1', customer_name: '真实客户' }], workshops: [{ id: 'W1', name: '包装车间' }], locations: [{ id: 'BIN', label: '原料仓 / A01' }] } }
}
function deferred<T>() { let resolve!: (value: T) => void; const promise = new Promise<T>(r => { resolve = r }); return { promise, resolve } }
function setup(props: Record<string, unknown> = {}) { return mount(Component, { props: { factoryId: 'huaxing', viewerKey: 'u1', requesterName: '员工', ...props } }) }
async function button(wrapper: ReturnType<typeof setup>, text: string) { const target = wrapper.findAll('button').find(row => row.text() === text); expect(target, text).toBeDefined(); await target!.trigger('click'); await flushPromises() }
async function openDetail(wrapper: ReturnType<typeof setup>) { await flushPromises(); await wrapper.get('.special-row').trigger('click'); await flushPromises() }
async function fillForm(wrapper: ReturnType<typeof setup>) {
  await wrapper.get('[aria-label="需求日期"]').setValue('2026-10-25')
  await wrapper.get('[aria-label="申请用途"]').setValue('')
  for (const [label, value] of [['纸品1类型', '普通箱'], ['纸品1纸质', 'A=B'], ['纸品1规格', '10*20*30'], ['纸品1数量', '5']]) await wrapper.get(`[aria-label="${label}"]`).setValue(value)
}
beforeEach(() => { vi.clearAllMocks(); api.list.mockResolvedValue(workspace()); api.detail.mockResolvedValue(fixture()); api.save.mockResolvedValue(fixture()); api.action.mockResolvedValue(fixture()); api.attach.mockResolvedValue(fixture()) })

describe('special carton request work surface', () => {
  it('submits a sample without fabricated customer, contract, item or charge and preserves the request key on unchanged retry', async () => {
    const wrapper = setup(); await flushPromises(); await button(wrapper, '新建订单'); await fillForm(wrapper)
    expect(wrapper.find('[aria-label="申请客户"]').exists()).toBe(true)
    expect(wrapper.text()).not.toContain('合同号')
    api.save.mockRejectedValueOnce(new Error('网络尚未确认')).mockResolvedValueOnce(fixture())
    await wrapper.get('[aria-label="订单表单"]').trigger('submit'); await flushPromises()
    expect(wrapper.get('[role="alert"]').text()).toContain('网络尚未确认')
    const first = api.save.mock.calls[0]![0]
    expect(first).toMatchObject({ factory_id: 'huaxing', kind: 'SAMPLE', requester_name: '员工', customer_code: '', lines: [expect.objectContaining({ quantity: '5', item_no: '' })] })
    expect(first).not.toHaveProperty('title'); expect(wrapper.find('[aria-label="需求名称"]').exists()).toBe(false); expect(first).not.toHaveProperty('pricing_kind'); expect(first).not.toHaveProperty('contract_no')
    await wrapper.get('[aria-label="订单表单"]').trigger('submit'); await flushPromises()
    expect(api.save.mock.calls[1]![0].request_id).toBe(first.request_id)
    expect(wrapper.text()).toContain('订单已创建，等待负责人确认并锁单')
    wrapper.unmount()
  })
  it('requires workshop but permits an empty purpose and rejects invalid quantities before creating a workshop request', async () => {
    const wrapper = setup(); await flushPromises(); await button(wrapper, '新建订单'); await fillForm(wrapper)
    await wrapper.get('[aria-label="申请类型"]').setValue('WORKSHOP_MISC')
    await wrapper.get('[aria-label="订单表单"]').trigger('submit'); await flushPromises()
    expect(api.save).not.toHaveBeenCalled(); expect(wrapper.text()).toContain('车间杂单还须选择车间')
    await wrapper.get('[aria-label="需求车间"]').setValue('W1'); await wrapper.get('[aria-label="申请用途"]').setValue('')
    await wrapper.get('[aria-label="纸品1数量"]').setValue('0.00001')
    await wrapper.get('[aria-label="订单表单"]').trigger('submit'); await flushPromises(); expect(api.save).not.toHaveBeenCalled()
    await wrapper.get('[aria-label="纸品1数量"]').setValue('20')
    await wrapper.get('[aria-label="订单表单"]').trigger('submit'); await flushPromises()
    expect(api.save.mock.calls[0]![0]).toMatchObject({ kind: 'WORKSHOP_MISC', workshop_id: 'W1', purpose: '' }); wrapper.unmount()
  })
  it('uses server operation flags and never exposes shipment or price approval while quote is pending', async () => {
    api.list.mockResolvedValue(workspace([fixture()], false))
    const wrapper = setup(); await openDetail(wrapper)
    expect(wrapper.text()).not.toContain('新建订单'); expect(wrapper.text()).not.toContain('发送给供应商'); expect(wrapper.find('[aria-label="特殊送货表单"]').exists()).toBe(false)
    expect(wrapper.text()).not.toContain('确认收费报价并下单'); expect(api.action).not.toHaveBeenCalled(); wrapper.unmount()
  })
  it('removes manual supplier shipment entry and preserves read-only order details', async () => {
    api.detail.mockResolvedValue(fixture({ status: 'SENT', permissions: { can_ship: true } }))
    const wrapper = setup({ supplier: true }); await openDetail(wrapper)
    expect(wrapper.find('[aria-label="特殊送货表单"]').exists()).toBe(false)
    expect(wrapper.text()).not.toContain('加入统一送货单'); expect(wrapper.emitted('dispatch')).toBeUndefined()
    expect(api.action).not.toHaveBeenCalled(); wrapper.unmount()
  })
  it('saves explicit per-paper mark requirements without fabricating a confirmed file', async () => {
    const wrapper = setup(); await flushPromises(); await button(wrapper, '新建订单'); await fillForm(wrapper)
    expect(wrapper.find('[aria-label="纸品1箱唛要求"]').exists()).toBe(false)
    expect(wrapper.text()).toContain('统一在箱唛资料库维护')
    await wrapper.get('form').trigger('submit'); await flushPromises()
    expect(api.save.mock.calls[0]![0].lines[0]).toMatchObject({ mark_mode: 'PENDING' })
    expect(api.save.mock.calls[0]![0].lines[0]).not.toHaveProperty('mark_attachment_id'); wrapper.unmount()
  })
  it('binds the selected existing file revision to the correct paper and confirms only same-paper drafts', async () => {
    api.detail.mockResolvedValue(fixture({ permissions: { can_confirm_material: true }, attachments: [{ id: 'A1', line_id: 'L1', role: 'DRAFT', filename: '供应商稿.pdf' }, { id: 'A2', line_id: 'L2', role: 'DRAFT', filename: '别的纸品.pdf' }] }))
    api.markOptions.mockResolvedValue([{ id: 'ASSET', file_name: '确认稿.pdf', revision: 7, contract_number: 'C1' }])
    const wrapper = setup({ mode: 'marks' }); await openDetail(wrapper); await button(wrapper, '选择已有箱唛'); await wrapper.get('[aria-label="L1已有箱唛"]').setValue('ASSET'); await button(wrapper, '确认使用')
    expect(api.action).toHaveBeenCalledWith('REQ', 'lines/L1/mark', expect.objectContaining({ mark_mode: 'EXISTING', asset_id: 'ASSET', asset_revision: 7 }), false, expect.any(AbortSignal))
    await openDetail(wrapper); expect(wrapper.get('[aria-label="逐纸品箱唛"]').text()).not.toContain('别的纸品')
    await button(wrapper, '确认本单使用')
    expect(api.action).toHaveBeenLastCalledWith('REQ', 'lines/L1/mark', expect.objectContaining({ mark_mode: 'UPLOAD', attachment_id: 'A1' }), false, expect.any(AbortSignal)); wrapper.unmount()
  })
  it('removes supplier gift creation and hides internal confirmed attachment role', async () => {
    api.detail.mockResolvedValue(fixture({ kind: 'SUPPLIER_GIFT', permissions: { can_attach: true, can_cancel: true } }))
    const wrapper = setup({ supplier: true }); await openDetail(wrapper)
    expect(wrapper.find('[aria-label="特殊附件类别"]').exists()).toBe(false)
    expect(wrapper.text()).not.toContain('声明免费赠送'); expect(wrapper.text()).not.toContain('新建订单')
    expect(api.save).not.toHaveBeenCalled(); wrapper.unmount()
  })
  it('uses remaining-to-ship rather than the unreceived demand and preserves original shipment material and receipt differences', async () => {
    api.detail.mockResolvedValue(fixture({ status: 'READY', pricing_kind: 'CHARGEABLE', permissions: { can_ship: true },
      lines: [{ ...fixture().lines[0]!, specification: '新版规格', remaining_quantity: '10', remaining_to_ship: '3' }],
      shipments: [{ id: 'SHIP', version_id: 'OLD_VERSION', delivery_note_no: 'OLD-DN', delivery_date: '2026-10-20',
        lines: [{ id: 'SL1', request_line_id: 'L1', quantity: '7', received_quantity: '0', remaining_quantity: '7', snapshot: { packaging_type: '旧版纸箱', paper_quality: 'A=B', specification: '旧版规格', dimension_unit: 'in', unit: '个', unit_price: '1.2', pricing_kind: 'CHARGEABLE' } }],
        receipts: [{ id: 'REC', receipt_no: 'RC-1', acceptance_date: '2026-10-20', status: 'REVERSED', lines: [{ packaging_type: '旧版纸箱', received_quantity: '7', damaged_quantity: '2', rejected_quantity: '0', unusable_quantity: '0', effective_quantity: '5', unit: '个', unit_price: '1.2' }] }] }] }))
    const wrapper = setup({ supplier: true }); await openDetail(wrapper)
    expect(wrapper.find('[aria-label="特殊送货表单"]').exists()).toBe(false)
    expect(wrapper.text()).toContain('旧版规格 in'); expect(wrapper.text()).toContain('OLD_VERSION'); expect(wrapper.text()).toContain('破损 2'); expect(wrapper.text()).toContain('已冲销')
    expect(wrapper.text()).not.toContain('加入统一送货单'); expect(wrapper.emitted('dispatch')).toBeUndefined(); expect(api.action).not.toHaveBeenCalled(); wrapper.unmount()
  })
  it('uploads per-paper draft automatically and keeps reference attachments separate without a technical role choice', async () => {
    api.detail.mockResolvedValue(fixture({ permissions: { can_attach: true, can_confirm_material: true } }))
    const wrapper = setup({ mode: 'marks' }); await openDetail(wrapper)
    expect(wrapper.find('[aria-label="特殊附件类别"]').exists()).toBe(false)
    expect(wrapper.find('[aria-label="订单详情"]').exists()).toBe(true)
    expect(wrapper.findAll('h3, h4').map(row => row.text())).toEqual(['箱唛资料'])
    await button(wrapper, '上传箱唛')
    const file = new File(['draft specification'], '制作稿.pdf', { type: 'application/pdf' })
    Object.defineProperty(wrapper.get('[aria-label="L1箱唛文件"]').element, 'files', { configurable: true, value: [file] }); await wrapper.get('[aria-label="L1箱唛文件"]').trigger('change')
    await wrapper.get('[aria-label="L1箱唛上传"]').trigger('submit'); await flushPromises()
    expect(api.attach).toHaveBeenCalledWith('REQ', expect.objectContaining({ factory_id: 'huaxing', expected_revision: 1, line_id: 'L1' }), 'DRAFT', file, false, expect.any(AbortSignal))
    await wrapper.setProps({ mode: 'requests' }); await openDetail(wrapper)
    Object.defineProperty(wrapper.get('[aria-label="备注附件文件"]').element, 'files', { configurable: true, value: [file] }); await wrapper.get('[aria-label="备注附件文件"]').trigger('change')
    await wrapper.get('[aria-label="备注附件上传"]').trigger('submit'); await flushPromises()
    expect(api.attach).toHaveBeenLastCalledWith('REQ', expect.objectContaining({ line_id: 'L1' }), 'REFERENCE', file, false, expect.any(AbortSignal)); wrapper.unmount()
  })
  it('lets supplier bind a shared source as a proposal without exposing internal confirmation or no-print controls', async () => {
    api.detail.mockResolvedValue(fixture({ permissions: { can_attach: true } }))
    api.markOptions.mockResolvedValue([{ id: 'SHARED', file_name: '未绑定样板.pdf', revision: 3 }])
    const wrapper = setup({ supplier: true }); await openDetail(wrapper); await button(wrapper, '选择已有箱唛')
    expect(api.markOptions).toHaveBeenLastCalledWith('huaxing', expect.any(AbortSignal), true, 'REQ')
    await wrapper.get('[aria-label="L1已有箱唛"]').setValue('SHARED'); await button(wrapper, '绑定并提交确认')
    expect(api.action).toHaveBeenCalledWith('REQ', 'lines/L1/mark', expect.objectContaining({ mark_mode: 'EXISTING', asset_id: 'SHARED', asset_revision: 3 }), true, expect.any(AbortSignal))
    expect(wrapper.findAll('button').map(row => row.text())).not.toContain('无需印刷')
    expect(wrapper.findAll('button').map(row => row.text())).not.toContain('确认本单使用'); wrapper.unmount()
  })
  it('clears an abandoned library selection when marking a paper as unprinted', async () => {
    api.detail.mockResolvedValue(fixture({ permissions: { can_confirm_material: true } }))
    api.markOptions.mockResolvedValue([{ id: 'ASSET', file_name: '箱唛.pdf', revision: 5 }])
    const wrapper = setup({ mode: 'marks' }); await openDetail(wrapper); await button(wrapper, '选择已有箱唛')
    await wrapper.get('[aria-label="L1已有箱唛"]').setValue('ASSET'); await button(wrapper, '无需印刷')
    expect(api.action).toHaveBeenCalledWith('REQ', 'lines/L1/mark', expect.objectContaining({ mark_mode: 'NONE', asset_id: '', asset_revision: 0, attachment_id: '' }), false, expect.any(AbortSignal)); wrapper.unmount()
  })
  it('discards late previews and shared-library choices after factory context changes', async () => {
    api.detail.mockResolvedValue(fixture({ permissions: { can_confirm_material: true }, lines: [{ ...fixture().lines[0]!, mark_attachment_id: 'A1' }], attachments: [{ id: 'A1', role: 'CONFIRMED', line_id: 'L1', filename: '确认稿.pdf' }] }))
    const library = deferred<{ id: string; file_name: string; revision: number }[]>(), preview = deferred<Blob>()
    api.markOptions.mockReturnValueOnce(library.promise); api.download.mockReturnValueOnce(preview.promise)
    const wrapper = setup({ mode: 'marks' }); await openDetail(wrapper)
    await wrapper.findAll('button').find(row => row.text() === '选择已有箱唛')!.trigger('click')
    await wrapper.findAll('button').find(row => row.text() === '预览')!.trigger('click')
    api.list.mockResolvedValue(workspace([], false)); await wrapper.setProps({ factoryId: 'huakang-a' }); await flushPromises()
    library.resolve([{ id: 'PRIVATE', file_name: '旧厂私有资料.pdf', revision: 1 }]); preview.resolve(new Blob(['pdf'], { type: 'application/pdf' })); await flushPromises()
    expect(wrapper.text()).not.toContain('旧厂私有资料'); expect(wrapper.find('[aria-label="箱唛预览"]').exists()).toBe(false); wrapper.unmount()
  })
  it('hides already confirmed drafts while preserving old confirmed versions and current production file', async () => {
    api.detail.mockResolvedValue(fixture({ lines: [{ ...fixture().lines[0]!, mark_attachment_id: 'NEW', mark_ready: true, mark_mode: 'UPLOAD' }], attachments: [
      { id: 'DRAFT', role: 'DRAFT', line_id: 'L1', filename: '原制作稿.pdf', sha256: 'HASH', version: 1 },
      { id: 'OLD', role: 'CONFIRMED', line_id: 'L1', filename: '已用旧稿.pdf', sha256: 'HASH', version: 2 },
      { id: 'NEW', role: 'CONFIRMED', line_id: 'L1', filename: '当前稿.pdf', sha256: 'HASH2', version: 3 },
    ] }))
    const wrapper = setup({ mode: 'marks' }); await openDetail(wrapper)
    const marks = wrapper.get('[aria-label="逐纸品箱唛"]')
    expect(marks.text()).toContain('本单使用稿：当前稿.pdf'); expect(marks.text()).toContain('历史版本'); expect(marks.text()).toContain('已用旧稿.pdf'); expect(marks.text()).not.toContain('原制作稿.pdf'); expect(marks.text()).not.toContain('待我方确认'); wrapper.unmount()
  })

  it('opens an audited adjustment form, locks ownership and preserves edits on cancel and failure', async () => {
    const row = fixture({ status: 'SENT', permissions: { can_adjust: true } })
    api.detail.mockResolvedValue(row); api.adjust.mockRejectedValueOnce(new Error('连接未确认')).mockResolvedValueOnce(row)
    const wrapper = setup({ mode: 'detail', requestId: 'REQ', initialAction: 'adjust' }); await flushPromises()
    expect(wrapper.get('[aria-label="申请客户"]').attributes('disabled')).toBeDefined()
    await wrapper.get('[aria-label="纸品1数量"]').setValue('12')
    await wrapper.get('[aria-label="订单表单"]').trigger('submit'); await flushPromises(); expect(api.adjust).not.toHaveBeenCalled()
    await wrapper.get('[aria-label="订单调整原因"]').setValue('车间增加用量')
    await wrapper.get('[aria-label="订单表单"]').trigger('submit'); await flushPromises()
    expect(wrapper.get<HTMLInputElement>('[aria-label="纸品1数量"]').element.value).toBe('12')
    const first = api.adjust.mock.calls[0]![1]
    expect(first).toMatchObject({ expected_revision: 1, reason: '车间增加用量', lines: [expect.objectContaining({ quantity: '12' })] })
    await wrapper.get('[aria-label="订单表单"]').trigger('submit'); await flushPromises()
    expect(api.adjust.mock.calls[1]![1].request_id).toBe(first.request_id); expect(api.save).not.toHaveBeenCalled()
    wrapper.unmount()
  })
  it('requires explicit confirmation inside the lock dialog and uses only the confirm permission', async () => {
    const row = fixture({ permissions: { can_confirm: true } })
    api.detail.mockResolvedValue(row)
    const wrapper = setup({ mode: 'detail', requestId: 'REQ', initialAction: 'confirm' }); await flushPromises()
    expect(api.action).not.toHaveBeenCalled()
    const confirm = [...document.querySelectorAll('button')].find(button => button.textContent?.includes('核对无误，确认锁单'))
    expect(confirm).toBeDefined(); (confirm as HTMLButtonElement).click(); await flushPromises()
    expect(api.action).toHaveBeenCalledWith('REQ', 'confirm', expect.objectContaining({ factory_id: 'huaxing', expected_revision: 1 }), false, expect.any(AbortSignal))
    wrapper.unmount()
  })
  it('labels warehouse-entered history as warehouse evidence without inventing a supplier zero price', async () => {
    const paper = { id: 'S1', request_line_id: 'L1', quantity: '1', received_quantity: '1', remaining_quantity: '0', snapshot: { unit_price: '0', unit: '个', warehouse_unit_price: null } }
    const row = fixture({ shipments: [{ id: 'SHIP', version_id: 'V', delivery_note_no: 'MANUAL-DN', delivery_date: '2026-10-20', source_origin: 'WAREHOUSE_MANUAL', lines: [paper, { ...paper, id: 'S2', snapshot: { ...paper.snapshot, warehouse_unit_price: '0' } }], receipts: [] }] })
    api.detail.mockResolvedValue(row)
    const wrapper = setup({ mode: 'detail', requestId: 'REQ' }); await flushPromises()
    expect(wrapper.text()).toContain('仓库记录单价：未填写')
    expect(wrapper.text()).toContain('仓库记录单价：CNY 0 / 个')
    expect(wrapper.text()).not.toContain('送货单价：')
    wrapper.unmount()
  })

  it('discards old-factory list, detail, mutation and drafts when the factory or viewer changes', async () => {
    const oldList = deferred<SpecialWorkspace>(); api.list.mockReturnValueOnce(oldList.promise).mockResolvedValue(workspace([], false))
    const wrapper = setup(); await wrapper.setProps({ factoryId: 'huakang-a' }); await flushPromises()
    oldList.resolve(workspace([fixture({ title: '旧厂申请' })])); await flushPromises(); expect(wrapper.text()).not.toContain('旧厂申请')
    api.list.mockResolvedValue(workspace()); await wrapper.setProps({ factoryId: 'huaxing' }); await flushPromises()
    const oldDetail = deferred<SpecialRequest>(); api.detail.mockReturnValueOnce(oldDetail.promise)
    await wrapper.get('.special-row').trigger('click'); await wrapper.setProps({ viewerKey: 'u2' }); await flushPromises()
    oldDetail.resolve(fixture({ title: '旧账号详情' })); await flushPromises(); expect(wrapper.text()).not.toContain('旧账号详情')
    await button(wrapper, '新建订单'); await fillForm(wrapper)
    const oldSave = deferred<SpecialRequest>(); api.save.mockReturnValueOnce(oldSave.promise)
    await wrapper.get('[aria-label="订单表单"]').trigger('submit'); await wrapper.setProps({ factoryId: 'huakang-a' }); await flushPromises()
    oldSave.resolve(fixture({ title: '迟到创建结果' })); await flushPromises(); expect(wrapper.text()).not.toContain('迟到创建结果'); expect(wrapper.find('[aria-label="订单表单"]').exists()).toBe(false)
    wrapper.unmount()
  })
  it('renders an authorized ledger preview without loading another workspace and updates the hovered request', async () => {
    const wrapper = setup({ mode: 'detail', previewRequest: fixture() }); await flushPromises()
    expect(api.list).not.toHaveBeenCalled(); expect(api.detail).not.toHaveBeenCalled()
    expect(wrapper.get('[aria-label="订单资料"]').text()).toContain('SP-01')
    expect(wrapper.find('form').exists()).toBe(false)
    await wrapper.setProps({ previewRequest: fixture({ id: 'NEXT', request_no: 'SP-NEXT' }) }); await flushPromises()
    expect(wrapper.get('[aria-label="订单资料"]').text()).toContain('SP-NEXT')
    expect(wrapper.findComponent(CartonSpecialOrderActions).exists()).toBe(false)
    wrapper.unmount()
  })
  it('shows the same receipt-progress columns and unit-separated totals as regular order details', async () => {
    api.detail.mockResolvedValue(fixture({ lines: [
      { ...fixture().lines[0]!, quantity: '10', received_quantity: '4' },
      { ...fixture().lines[0]!, id: 'L2', quantity: '3', received_quantity: '1', unit: '张' },
    ] }))
    const wrapper = setup({ mode: 'detail', requestId: 'REQ' }); await flushPromises()
    expect(wrapper.findAll('th').map(row => row.text())).toEqual(['纸品类型', '纸质', '规格', '计数单位', '纸品数量', '已入库', '待入库', '入库进度'])
    expect(wrapper.get('[aria-label="订单纸品汇总"]').text()).toContain('10 个 · 3 张')
    expect(wrapper.get('[aria-label="订单纸品汇总"]').text()).toContain('6 个 · 2 张')
    expect(wrapper.find('[aria-label="样板杂单手动收料"]').exists()).toBe(false)
    expect(wrapper.find('[aria-label="逐纸品箱唛"]').exists()).toBe(false)
    expect(wrapper.findComponent(CartonSpecialOrderActions).exists()).toBe(false)
    expect(wrapper.find('form').exists()).toBe(false)
    wrapper.unmount()
  })
  it('opens deletion confirmation explicitly and preserves the request key and reason on a failed retry', async () => {
    const row = fixture({ permissions: { can_delete: true } })
    api.detail.mockResolvedValue(row)
    api.action.mockRejectedValueOnce(new Error('网络未确认')).mockResolvedValueOnce({ ...row, deleted: true, permissions: {} })
    const wrapper = setup({ mode: 'detail', requestId: 'REQ', initialAction: 'delete' }); await flushPromises()
    const text = document.querySelector<HTMLTextAreaElement>('[aria-label="样板杂单删除原因"]')!
    text.value = '重复录入订单'; text.dispatchEvent(new Event('input', { bubbles: true })); await flushPromises()
    const confirm = () => Array.from(document.querySelectorAll('button')).find(row => row.textContent === '确认删除订单')!
    confirm().click(); await flushPromises()
    const first = api.action.mock.calls[0]![2]
    expect(first).toMatchObject({ reason: '重复录入订单', expected_revision: 1 })
    expect(text.value).toBe('重复录入订单')
    confirm().click(); await flushPromises()
    expect(api.action.mock.calls[1]![2].request_id).toBe(first.request_id)
    expect(wrapper.emitted('close')).toHaveLength(1)
    wrapper.unmount()
  })
  it('shows actual read failure and can retry without claiming an empty queue', async () => {
    api.list.mockRejectedValueOnce(new Error('服务暂不可用'))
    const wrapper = setup(); await flushPromises(); expect(wrapper.get('[role="alert"]').text()).toContain('服务暂不可用'); expect(wrapper.text()).not.toContain('暂无申请；')
    await button(wrapper, '刷新'); expect(wrapper.text()).toContain(fixture().request_no); wrapper.unmount()
  })
  it('opens a newly requested notification target after an in-flight mutation settles', async () => {
    api.detail.mockImplementation(async (_factory, id) => fixture({ id, permissions: { can_confirm: true } }))
    const wrapper = setup({ requestId: 'REQ' }); await flushPromises()
    const response = deferred<SpecialRequest>(); api.action.mockReturnValueOnce(response.promise)
    await button(wrapper, '确认并锁单')
    ;([...document.querySelectorAll('button')].find(button => button.textContent?.includes('核对无误，确认锁单')) as HTMLButtonElement).click()
    await wrapper.setProps({ requestId: 'NEXT-REQ' }); await flushPromises()
    response.resolve(fixture({ id: 'REQ', status: 'SENT' })); await flushPromises()
    expect(api.detail).toHaveBeenLastCalledWith('huaxing', 'NEXT-REQ', false, expect.any(AbortSignal)); wrapper.unmount()
  })
})
