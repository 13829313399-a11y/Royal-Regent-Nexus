import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { mount, flushPromises, type VueWrapper } from '@vue/test-utils'
import { createMemoryHistory, createRouter, RouterView } from 'vue-router'
import { reactive } from 'vue'
import { AxiosError } from 'axios'
import View from '../MaterialHandoverView.vue'
import type { HandoverDocument, HandoverWorkspace } from '@/api/materialHandover'

const api = vi.hoisted(() => ({ workspace: vi.fn(), list: vi.fn(), pendingDeliveries: vi.fn(), issuers: vi.fn(), detail: vi.fn(), purchaseSources: vi.fn(), post: vi.fn(), linkReceipt: vi.fn(), unlinkReceipt: vi.fn(), recordRejectionFollowup: vi.fn(), scan: vi.fn(), action: vi.fn(), save: vi.fn(), upload: vi.fn(), context: vi.fn(), file: vi.fn(), printFile: vi.fn() }))
const originalRender = vi.hoisted(() => ({ ready: true }))
vi.mock('../HandoverOriginalPrint.vue', async () => {
  const { defineComponent, onMounted } = await import('vue')
  return {
    default: defineComponent({
      name: 'OriginalPrintStub',
      props: ['file', 'token'],
      emits: ['ready', 'failed'],
      setup(props, { emit }) {
        onMounted(() => { if (originalRender.ready) emit('ready', props.token) })
        return {}
      },
      template: '<div class="handover-original-print"></div>',
    }),
  }
})
vi.mock('@/api/materialHandover', () => ({ HANDOVER_FACTORY: 'huakang-c', handoverApi: () => api }))
const auth = reactive({ currentUser: { id: 'warehouse' }, authorizationVersion: 1 })
vi.mock('@/stores/auth', () => ({ useAuthStore: () => auth }))
let wrapper: VueWrapper | undefined
const clone = <T>(value: T): T => JSON.parse(JSON.stringify(value)) as T
const fixture = (): HandoverDocument => ({ id: 'D1', factory_id: 'huakang-c', issuer_id: null, status: 'CONFIRMED', revision: 3,
  code_version: 1, code: 'MH1:D1:1', data: { kind: 'DELIVERY', supplier_id: 'SUP', source_no: 'DN-1', document_date: '2026-10-12', counterparty: '供应商',
    contract_no: '', production_no: '', product_no: '', note: '', lines: ['A','B'].map((id) => ({ id, source_line: '', item_code: id, item_name: '物料' + id, specification: '', color: '', quantity: '40', unit: '码', material_category: 'FABRIC', lot: 'LOT', roll_no: '', roll_quantities: '', contract_no: '', production_no: '', product_no: '', note: '' })) },
  warnings: [], evidence: {}, engine: 'xlsx', raw_text: '', file_name: '原件.xlsx', source_sha256: '', confirmed_at: '', created_at: '',
  progress: { A: { processed: '10', remaining: '30' }, B: { processed: '0', remaining: '40' } }, processing_status: 'PARTIAL', movements: [] })
const work = (): HandoverWorkspace => ({ factory_id: 'huakang-c', inventory: { revision: 8, locations: [{ id: 'BIN', category: 'FABRIC', warehouse: '一仓', code: 'A01', label: '一仓 A01', status: 'ACTIVE', revision: 1 }], stock: [], documents: [], permissions: { read: true, operate: true, correct: false, quality: false } }, materials: [], can_operate: true, can_manage: false })
async function open(external = false, path = '/?factory=huakang-c') {
  const router = createRouter({ history: createMemoryHistory(), routes: [{ path: '/', component: View, props: { external } }, { path: '/other', component: { template: '<div>其他页面</div>' } }, { path: '/modules/pmc-warehouse/fabric-warehouse/inventory', component: { template: '<div>台账</div>' } }] })
  await router.push(path); await router.isReady()
  wrapper = mount(RouterView, { global: { plugins: [router] } }); await flushPromises()
  return router
}
async function select() { await wrapper!.findAll('button').find(button => button.text().startsWith('DN-1'))!.trigger('click'); await flushPromises() }
async function click(text: string) { await wrapper!.findAll('button').find(button => button.text() === text)!.trigger('click'); await flushPromises() }
const quantityInput = (part = 1) => wrapper!.get<HTMLInputElement>(`[aria-label="第1项第${part}个仓位净入库量"]`)
const locationInput = (part = 1) => wrapper!.get<HTMLInputElement>(`[aria-label="第1项第${part}个入库仓位"]`)
const warehouseInput = (part = 1) => wrapper!.get<HTMLSelectElement>(`[aria-label="第1项第${part}个入库仓库"]`)
beforeEach(() => { vi.resetAllMocks(); auth.currentUser.id = 'warehouse'; auth.authorizationVersion = 1; api.workspace.mockResolvedValue(work()); api.list.mockResolvedValue({ items: [{ ...fixture(), line_count: 2 }], limit: 50, offset: 0 }); api.detail.mockResolvedValue(fixture()); api.issuers.mockResolvedValue([]); api.context.mockResolvedValue({ name: '供应商', kind: 'SUPPLIER', supplier_id: 'SUP' });api.file.mockResolvedValue(new Blob(['<svg/>'],{type:'image/svg+xml'}));vi.stubGlobal('URL',class extends URL { static createObjectURL(){return 'blob:test'};static revokeObjectURL(){} });vi.spyOn(window,'print').mockImplementation(()=>{}) })
afterEach(() => { wrapper?.unmount(); wrapper = undefined; originalRender.ready = true; vi.restoreAllMocks();vi.unstubAllGlobals() })

describe('material handover workflow', () => {
  it.each([false, true])('uses the receiving unit for a price without a second unit input (external=%s)', async (external) => {
    const row = fixture(); row.status = 'DRAFT'; row.data.lines[1]!.unit_price = '0'; row.data.lines[1]!.price_unit = '码'
    api.detail.mockResolvedValue(row)
    api.save.mockImplementation((_id, body) => Promise.resolve({ ...row, revision: 4, data: body.data }))
    await open(external, external ? '/#key=public-test-key' : '/?factory=huakang-c'); await select()
    expect(wrapper!.find('input[placeholder="计价单位"]').exists()).toBe(false)
    await wrapper!.get('[aria-label="第1行参考单价"]').setValue('8')
    await wrapper!.get('[aria-label="第1行单位"]').setValue('米')
    await wrapper!.get('[aria-label="第2行单位"]').setValue('Pcs')
    expect(wrapper!.findAll('.price-unit-hint').map(node => node.text())).toEqual(['单价按米计价', '单价按Pcs计价'])
    await click(external ? '保存草稿' : '保存核对内容')
    expect(api.save.mock.calls[0]![1].data.lines).toEqual([
      expect.objectContaining({ unit: '米', unit_price: '8', price_unit: '米' }),
      expect.objectContaining({ unit: 'Pcs', unit_price: '0', price_unit: 'Pcs' }),
    ])
  })
  it('preserves a different original pricing unit and shows it as reference', async () => {
    const row = fixture(); row.status = 'DRAFT'; row.data.lines[0]!.unit_price = '8'; row.data.lines[0]!.price_unit = '米'
    api.detail.mockResolvedValue(row)
    api.save.mockImplementation((_id, body) => Promise.resolve({ ...row, revision: 4, data: body.data }))
    await open(); await select()
    expect(wrapper!.get('.price-unit-hint').text()).toBe('原单按米计价')
    await wrapper!.get('[aria-label="第1行单位"]').setValue('卷')
    await click('保存核对内容')
    expect(api.save.mock.calls[0]![1].data.lines[0]).toMatchObject({ unit: '卷', unit_price: '8', price_unit: '米' })
  })
  it.each([false, true])('defaults delivery entry to CNY and saves staff currency choices (external=%s)', async (external) => {
    const row = fixture(); row.status = 'DRAFT'; row.data.lines[0]!.currency = ''; row.data.lines[1]!.currency = 'HKD'
    api.detail.mockResolvedValue(row)
    api.save.mockImplementation((_id, body) => Promise.resolve({ ...row, revision: 4, data: body.data }))
    const router = await open(external, external ? '/#key=public-test-key' : '/?factory=huakang-c'); await select()
    expect(wrapper!.get<HTMLSelectElement>('[aria-label="第1行币种"]').element.value).toBe('CNY')
    expect(wrapper!.get<HTMLSelectElement>('[aria-label="第2行币种"]').element.value).toBe('HKD')
    await click('添加明细')
    expect(wrapper!.get<HTMLSelectElement>('[aria-label="第3行币种"]').element.value).toBe('CNY')
    await wrapper!.get('[aria-label="第2行币种"]').setValue('USD')
    await click(external ? '保存草稿' : '保存核对内容')
    const lines = api.save.mock.calls[0]![1].data.lines
    expect(lines.map((line: { currency: string }) => line.currency)).toEqual(['CNY', 'USD', 'CNY'])
    expect(lines[0].unit_price).toBeUndefined(); expect(lines[0].price_unit).toBeUndefined()
    await router.push('/other'); expect(router.currentRoute.value.path).toBe('/other')
  })
  it('does not dirty a draft just by displaying its default or rewrite historical unknown currency', async () => {
    const row = fixture(); row.status = 'DRAFT'; api.detail.mockResolvedValue(row)
    const router = await open(); await select()
    expect(wrapper!.get<HTMLSelectElement>('[aria-label="第1行币种"]').element.value).toBe('CNY')
    await router.push('/other'); expect(router.currentRoute.value.path).toBe('/other')
    wrapper!.unmount(); wrapper = undefined
    api.detail.mockResolvedValue(fixture()); await open(); await select()
    expect(wrapper!.get<HTMLSelectElement>('[aria-label="第1行币种"]').element.value).toBe('')
    expect(api.save).not.toHaveBeenCalled(); expect(api.action).not.toHaveBeenCalled()
  })
  it('preserves edited drafts and navigation guards on a same-account session refresh', async () => {
    const row = fixture(); row.status = 'DRAFT'; api.detail.mockResolvedValue(row)
    const router = await open(); await select()
    expect(wrapper!.text()).toContain('确认单据后，在「本次实际收料入库」选择仓库和仓位')
    expect(wrapper!.find('.receipt-allocations').exists()).toBe(false)
    await wrapper!.get('[aria-label="第1行单据数量"]').setValue('19')
    api.workspace.mockClear(); api.list.mockClear()
    auth.currentUser = { id: 'warehouse' }; await flushPromises()
    expect(wrapper!.get<HTMLInputElement>('[aria-label="第1行单据数量"]').element.value).toBe('19')
    expect(api.workspace).not.toHaveBeenCalled(); expect(api.list).not.toHaveBeenCalled()
    await router.push('/other'); expect(router.currentRoute.value.path).toBe('/')
  })
  it('preserves receiving inputs and an uncertain submission on a same-account session refresh', async () => {
    api.post.mockRejectedValueOnce(new AxiosError('网络断开')).mockResolvedValueOnce(fixture())
    await open(); await select()
    await wrapper!.get('.posting-row input[type=checkbox]').setValue(true)
    await quantityInput().setValue('7.5')
    await locationInput().setValue('一仓 A01')
    auth.currentUser = { id: 'warehouse' }; await flushPromises()
    expect(quantityInput().element.value).toBe('7.5')
    expect(locationInput().element.value).toBe('一仓 A01')
    expect(wrapper!.get<HTMLInputElement>('.posting-row input[type=checkbox]').element.checked).toBe(true)
    await click('确认本次实物收发'); const frozen = clone(api.post.mock.calls[0]![1])
    auth.currentUser = { id: 'warehouse' }; await flushPromises()
    expect(wrapper!.get('.posting-card fieldset').attributes('disabled')).toBeDefined()
    await click('重试原提交'); expect(api.post.mock.calls[1]![1]).toEqual(frozen)
  })
  it('still clears private selection when the account actually changes', async () => {
    await open(); await select(); expect(wrapper!.find('.posting-card').exists()).toBe(true)
    api.list.mockResolvedValue({ items: [], limit: 50, offset: 0 })
    auth.currentUser = { id: 'another-user' }; await flushPromises()
    expect(wrapper!.find('.posting-card').exists()).toBe(false)
    expect(wrapper!.text()).not.toContain('物料A')
  })
  it('suggests a new delivery line from its unit and submits the staff correction', async () => {
    const row = fixture(); row.status = 'DRAFT'; api.detail.mockResolvedValue(row)
    api.save.mockImplementation((_id, body) => Promise.resolve({ ...row, revision: 4, data: body.data }))
    await open(); await select(); await click('添加明细')
    const category = () => wrapper!.get<HTMLSelectElement>('[aria-label="第3行物料分类"]').element.value
    expect(category()).toBe('')
    await wrapper!.get('[aria-label="第3行单位"]').setValue(' PＣＳ ')
    expect(category()).toBe('ACCESSORY')
    await wrapper!.get('[aria-label="第3行单位"]').setValue('码')
    expect(category()).toBe('FABRIC')
    await wrapper!.get('[aria-label="第3行物料分类"]').setValue('THREAD')
    await wrapper!.get('[aria-label="第3行单位"]').setValue('卷')
    expect(category()).toBe('THREAD')
    await click('保存核对内容')
    expect(api.save.mock.calls[0]![1].data.lines[2]).toMatchObject({ unit: '卷', material_category: 'THREAD' })
    expect(api.action).not.toHaveBeenCalled(); expect(api.post).not.toHaveBeenCalled()
  })
  it('keeps an existing category and requires a category before confirming an ambiguous unit', async () => {
    const row = fixture(); row.status = 'DRAFT'
    row.data.lines[0]!.material_category = 'ACCESSORY'
    row.data.lines[1]!.unit = '公斤'; row.data.lines[1]!.material_category = ''
    api.detail.mockResolvedValue(row)
    await open(); await select()
    await wrapper!.get('[aria-label="第1行单位"]').setValue('米')
    expect(wrapper!.get<HTMLSelectElement>('[aria-label="第1行物料分类"]').element.value).toBe('ACCESSORY')
    expect(wrapper!.get('[aria-label="第2行物料分类"]').attributes('aria-invalid')).toBe('true')
    expect(wrapper!.get('.draft-review').text()).toContain('缺少物料分类')
    expect(wrapper!.findAll('button').find(b => b.text() === '确认并打印原单')!.attributes('disabled')).toBeDefined()
    await wrapper!.get('[aria-label="第2行物料分类"]').setValue('FABRIC')
    expect(wrapper!.get('.draft-review').text()).not.toContain('缺少物料分类')
  })
  it('lists exact missing fields and saves incomplete supplier edits as a private draft', async () => {
    const row = fixture(); row.status = 'DRAFT'; row.code = ''; row.code_version = 0; row.issuer_id = 'ISSUER-A'
    row.data.lines[0]!.item_code = ''; row.data.lines[0]!.quantity = ''; row.data.lines[1]!.unit = ''
    row.warnings = ['请核对印刷文字与手写内容']
    api.detail.mockResolvedValue(row)
    api.save.mockRejectedValueOnce(new AxiosError('连接断开')).mockResolvedValueOnce({ ...row, revision: 4 })
    await open(true, '/#key=public-test-key'); await select()
    expect(wrapper!.get('.draft-review').text()).toContain('第 1 行（物料A）：缺少物料编码；缺少数量')
    expect(wrapper!.get('.draft-review').text()).toContain('第 2 行（物料B）：缺少单位')
    expect(wrapper!.get('[aria-label="第1行物料编码"]').attributes('aria-invalid')).toBe('true')
    expect(wrapper!.findAll('button').find(b => b.text() === '确认送货单')!.attributes('disabled')).toBeDefined()
    expect(wrapper!.get('.recognition-notes').attributes('open')).toBeUndefined()
    expect(wrapper!.text()).not.toContain('交仓库补全')
    await wrapper!.get('[aria-label="原单号"]').setValue('DN-1-DRAFT')
    await click('保存草稿')
    const frozen = clone(api.save.mock.calls[0]![1])
    await click('重试原提交')
    expect(api.save.mock.calls[1]![1]).toEqual(frozen)
    expect(frozen.data.lines[0].item_code).toBe('')
    expect(wrapper!.text()).toContain('草稿已保存，仅本供应商可见')
    expect(api.action).not.toHaveBeenCalled(); expect(api.printFile).not.toHaveBeenCalled(); expect(api.post).not.toHaveBeenCalled()
  })
  it('updates confirmation readiness as missing fields are filled and retains optional supplier data', async () => {
    const row = fixture(); row.status = 'DRAFT'; row.data.lines[0]!.quantity = '0'; row.data.lines[0]!.unit_price = '0'
    row.warnings = ['请核对印刷文字与手写内容']
    api.detail.mockResolvedValue(row)
    api.action.mockImplementation((_id, _kind, body) => Promise.resolve({ ...fixture(), data: body.data }))
    api.printFile.mockResolvedValue(new Blob(['pdf'], { type: 'application/pdf' }))
    await open(true, '/#key=public-test-key'); await select()
    expect(wrapper!.get('.draft-review').text()).toContain('数量须大于 0')
    expect(wrapper!.get('.lines').classes()).toContain('compact')
    await click('展开选填信息'); expect(wrapper!.get('.lines').classes()).not.toContain('compact')
    await click('收起选填信息')
    await wrapper!.get('[aria-label="第1行单据数量"]').setValue('0.000001')
    expect(wrapper!.get('.draft-review').text()).toContain('资料已齐全')
    expect(wrapper!.find('.document-confirmation input[type="checkbox"]').exists()).toBe(false)
    await click('确认送货单')
    expect(api.action.mock.calls[0]![2]).toMatchObject({ acknowledge_warnings: true, data: { lines: [expect.objectContaining({ quantity: '0.000001', unit_price: '0', lot: 'LOT' }), expect.anything()] } })
    expect(api.post).not.toHaveBeenCalled()
  })
  it('saves a cleared document date as an incomplete draft instead of an invalid date string', async () => {
    const row = fixture(); row.status = 'DRAFT'; api.detail.mockResolvedValue(row)
    api.save.mockImplementation((_id, body) => Promise.resolve({ ...row, revision: 4, data: body.data }))
    await open(true, '/#key=public-test-key'); await select()
    await wrapper!.get('[aria-label="单据日期"]').setValue('')
    await click('保存草稿')
    expect(api.save.mock.calls[0]![1].data.document_date).toBeNull()
    expect(wrapper!.get('.draft-review').text()).toContain('缺少单据日期')
  })
  it.each([false, true])('opens receiving with the confirmed supplier details collapsed (scan=%s)', async (scan) => {
    const row = fixture(); row.issuer_id = 'ISSUER-A'
    row.data.lines[0]!.quantity = '40.000000'
    row.progress.A!.remaining = '30.000000'
    api.detail.mockResolvedValue(row); api.scan.mockResolvedValue(row)
    await open(false, scan ? '/?factory=huakang-c&tab=scan' : '/?factory=huakang-c')
    if (scan) {
      await wrapper!.get('[aria-label="扫描单据二维码"]').setValue(row.code)
      await wrapper!.get('.scan-card form').trigger('submit'); await flushPromises()
    } else await select()
    const details = wrapper!.get<HTMLElement>('.supplier-document-details')
    const disclosure = wrapper!.get('[aria-controls="handover-supplier-document-details"]')
    expect(disclosure.attributes('aria-expanded')).toBe('false')
    expect(details.element.style.display).toBe('none')
    expect(wrapper!.get('.detail-heading h2').text()).toBe(row.data.source_no)
    expect(wrapper!.get('.supplier-document-meta').text()).toContain(row.data.counterparty)
    expect(wrapper!.get('.supplier-document-meta time').text()).toBe(row.data.document_date)
    expect(details.get('.document-fields').attributes('disabled')).toBeDefined()
    expect(details.get('[aria-label="第1行物料编码"]').attributes('disabled')).toBeDefined()
    expect(wrapper!.find('.document-confirmation').exists()).toBe(false)
    expect(wrapper!.find('.code-card').exists()).toBe(false)
    expect(wrapper!.text()).not.toContain('作废未执行单据')
    expect(details.text()).toContain('原单有误请联系供应商更正重开')
    const receiving = wrapper!.get('.posting-card')
    expect(details.element.contains(receiving.element)).toBe(false)
    expect(receiving.text()).toContain('本次实际收料入库')
    expect(receiving.text()).toContain('增加仓位')
    expect(receiving.get('.receipt-metrics').findAll('dd').map(value => value.text())).toEqual(['40 码', '30 码', '30 码'])
    await quantityInput().setValue('19.25')
    await disclosure.trigger('click')
    expect(disclosure.attributes('aria-expanded')).toBe('true')
    expect(details.element.style.display).not.toBe('none')
    await disclosure.trigger('click')
    expect(details.element.style.display).toBe('none')
    expect(quantityInput().element.value).toBe('19.25')
    await click('查看原件')
    expect(api.file).toHaveBeenCalledWith(row.id, 'source')
    expect(api.post).not.toHaveBeenCalled()
  })
  it('opens the exact confirmed delivery from the dashboard without posting or scanning', async () => {
    api.pendingDeliveries.mockResolvedValue({ total: 1, items: [{ ...fixture(), line_count: 2 }], offset: 0, limit: 50 })
    await open(false, '/?factory=huakang-c&deliveries=pending&document=D1')
    expect(api.pendingDeliveries).toHaveBeenCalledWith(0)
    expect(api.list).not.toHaveBeenCalled()
    expect(api.detail).toHaveBeenCalledWith('D1')
    expect(wrapper!.text()).toContain('待入库送货单')
    expect(wrapper!.find('.posting-card').exists()).toBe(true)
    expect(api.post).not.toHaveBeenCalled()
  })
  it('shows receipt progress below confirmation and labels void history', async () => {
    const delivery = fixture()
    const statuses = ['PENDING', 'PARTIAL', 'COMPLETE'] as const
    api.list.mockResolvedValue({ items: [
      ...statuses.map(processing_status => ({ ...delivery, id: processing_status, processing_status, line_count: 2 })),
      { ...delivery, id: 'VOID', status: 'VOID', line_count: 2 },
      { ...delivery, id: 'DRAFT', status: 'DRAFT', line_count: 2 },
      { ...delivery, id: 'ISSUE', data: { ...delivery.data, kind: 'ISSUE' }, line_count: 2 },
    ], total: 6, limit: 50, offset: 0 })
    await open(false, '/?factory=huakang-c&tab=scan')

    const labels = wrapper!.findAll('.document-statuses').map(group => (
      Array.from(group.element.children, label => label.textContent?.trim())
    ))
    expect(labels).toEqual([
      ['已确认', '待收货'], ['已确认', '部分收货'], ['已确认', '收货完成'],
      ['已作废'], ['待核对'], ['已确认'],
    ])
  })
  beforeEach(() => { api.purchaseSources.mockResolvedValue({ document_revision: 3, lines: {} }) })
  const purchase = (id: string, revision = 4, count = 2) => ({ id, revision, receipt_count: count, remaining: '30', received: '70',
    order_no: 'PO-' + id, production_no: 'P001', plan_no: 'PLAN-001', contract_no: 'MA-001', supplier: '供应商',
    item_code: 'A', item_name: '物料A', unit: '码', can_receive: true, suggested: true, primary_match: true,
    purchase_price: { unit_price: '8.5', price_unit: '码', currency: 'CNY' as const } })
  it('links actual delivery quantity and freezes purchase progress versions on an unknown result', async () => {
    api.purchaseSources.mockResolvedValue({ document_revision: 3, match_status: { A: 'MATCHED' }, lines: { A: [purchase('P1')] } })
    api.post.mockRejectedValueOnce(new AxiosError('网络断开')).mockResolvedValueOnce(fixture())
    await open(); await select()
    expect(wrapper!.get<HTMLSelectElement>('[aria-label="A采购待收明细"]').element.value).toBe('P1')
    expect(wrapper!.get('.posting-card').text()).toContain('采购尚欠 30 码')
    const details = wrapper!.get('.purchase-details').text()
    for (const text of ['PO-P1', 'P001', 'PLAN-001', 'MA-001', '8.5 元／码']) expect(details).toContain(text)
    await wrapper!.get('.posting-row input[type=checkbox]').setValue(true)
    await quantityInput().setValue('7.5')
    await locationInput().setValue('一仓 A01')
    await click('确认本次实物收发')
    const frozen = clone(api.post.mock.calls[0]![1])
    expect(frozen.lines[0]).toMatchObject({ purchase_source_id: 'P1', expected_source_revision: 4, expected_receipt_count: 2, quantity: '7.5' })
    expect(frozen.lines[0]).not.toHaveProperty('unit_price')
    expect(wrapper!.get('.posting-card fieldset').attributes('disabled')).toBeDefined()
    await click('重试原提交')
    expect(api.post.mock.calls[1]![1]).toEqual(frozen)
  })
  it('requires a warehouse choice when multiple purchase lines match the same material', async () => {
    const second = purchase('P2', 5, 3)
    api.purchaseSources.mockResolvedValue({ document_revision: 3, match_status: { A: 'MATCHED' }, lines: { A: [
      { ...second, suggested: false, ordered_quantity: '5768', ordered_quantity_matches: true, purchase_price: { ...second.purchase_price, unit_price: null } },
      { ...purchase('P1'), suggested: false, ordered_quantity: '2152' },
    ] } })
    api.post.mockResolvedValue(fixture())
    await open(); await select(); await wrapper!.get('.posting-row input[type=checkbox]').setValue(true)
    expect(wrapper!.find('.purchase-details').exists()).toBe(false)
    const choices = wrapper!.get<HTMLSelectElement>('[aria-label="A采购待收明细"]').element
    expect(choices.value).toBe('')
    expect(Array.from(choices.options, option => option.value)).toEqual(['', 'P2', 'P1'])
    expect(choices.options[1]!.text).toContain('5768 码（下单量相符）')
    expect(wrapper!.get('.purchase-match-message').text()).toContain('单号对应多条采购明细')
    await click('确认本次实物收发')
    expect(api.post).not.toHaveBeenCalled()
    expect(wrapper!.text()).toContain('请为本次实收选择对应采购待收明细')
    await wrapper!.get('[aria-label="A采购待收明细"]').setValue('P2')
    expect(wrapper!.get('.purchase-details').text()).toContain('待补价')
    await locationInput().setValue('一仓 A01')
    await click('确认本次实物收发')
    expect(api.post.mock.calls[0]![1].lines[0]).toMatchObject({ purchase_source_id: 'P2', expected_source_revision: 5, expected_receipt_count: 3 })
  })
  it.each(['NO_REFERENCE', 'NOT_FOUND', 'CONFLICT', undefined])('leaves a lone %s fallback for warehouse selection', async matchStatus => {
    api.purchaseSources.mockResolvedValue({ document_revision: 3, match_status: { A: matchStatus },
      lines: { A: [{ ...purchase('P1'), primary_match: false, suggested: false }] } })
    await open(); await select()
    expect(wrapper!.get<HTMLSelectElement>('[aria-label="A采购待收明细"]').element.value).toBe('')
    expect(wrapper!.get('.purchase-match-message').text()).toContain('候补')
    expect(api.post).not.toHaveBeenCalled()
  })
  it.each([
    ['7', 'CNY', '码', '原送货单与采购单价有差异'],
    ['8.5', 'HKD', '码', '原送货单与采购的币种或计价单位不同'],
    ['8.5', 'CNY', '米', '原送货单与采购的币种或计价单位不同'],
    ['8.500', 'CNY', '码', ''],
  ] as const)('compares original delivery price %s %s per %s without conversion', async (unit_price, currency, price_unit, note) => {
    const document = fixture()
    Object.assign(document.data.lines[0]!, { unit_price, currency, price_unit })
    api.detail.mockResolvedValue(document)
    api.purchaseSources.mockResolvedValue({ document_revision: 3, match_status: { A: 'MATCHED' }, lines: { A: [purchase('P1')] } })
    await open(); await select()
    const details = wrapper!.get('.purchase-details')
    expect(details.text()).toContain(`${unit_price} ${currency}／${price_unit}`)
    expect(details.text()).toContain('8.5 元／码')
    if (note) expect(details.get('.purchase-price-note').text()).toContain(note)
    else expect(details.find('.purchase-price-note').exists()).toBe(false)
  })
  it('hides the current tracking price on a fully received delivery line', async () => {
    const document = fixture()
    document.progress.A = { processed: '40', remaining: '0' }
    api.detail.mockResolvedValue(document)
    api.purchaseSources.mockResolvedValue({ document_revision: 3, match_status: { A: 'MATCHED' }, lines: { A: [purchase('P1')] } })
    await open(); await select()
    expect(wrapper!.find('.purchase-details').exists()).toBe(false)
  })
  it('blocks posting until purchase progress is read and ignores a late response after authorization changes', async () => {
    let resolve!: (value: { document_revision: number; lines: { A: ReturnType<typeof purchase>[] } }) => void
    api.purchaseSources.mockReturnValue(new Promise(done => { resolve = done }))
    await open(); await select()
    expect(wrapper!.findAll('button').find(button => button.text() === '确认本次实物收发')!.attributes('disabled')).toBeDefined()
    auth.authorizationVersion++; await flushPromises()
    resolve({ document_revision: 3, lines: { A: [purchase('private')] } }); await flushPromises()
    expect(wrapper!.find('.posting-card').exists()).toBe(false)
    expect(wrapper!.text()).not.toContain('PO-private')
    expect(api.post).not.toHaveBeenCalled()
  })
  it('keeps actual receiving disabled after a purchase read failure until explicitly refreshed', async () => {
    api.purchaseSources.mockRejectedValueOnce(new AxiosError('网络断开')).mockResolvedValueOnce({ document_revision: 3, match_status: { A: 'MATCHED' }, lines: { A: [purchase('P1')] } })
    await open(); await select()
    expect(wrapper!.findAll('button').find(button => button.text() === '确认本次实物收发')!.attributes('disabled')).toBeDefined()
    await wrapper!.get('.posting-row input[type=checkbox]').setValue(true)
    await quantityInput().setValue('12')
    await locationInput().setValue('一仓 A01')
    api.workspace.mockResolvedValue({ ...work(), inventory: { ...work().inventory, revision: 12 } })
    await wrapper!.get('[aria-label="刷新采购与库存进度"]').trigger('click'); await flushPromises()
    expect(wrapper!.findAll('button').find(button => button.text() === '确认本次实物收发')!.attributes('disabled')).toBeUndefined()
    expect(wrapper!.get<HTMLSelectElement>('[aria-label="A采购待收明细"]').element.value).toBe('P1')
    api.post.mockResolvedValue(fixture())
    await click('确认本次实物收发')
    expect(api.post).toHaveBeenCalledWith('D1', expect.objectContaining({
      expected_inventory_revision: 12,
      lines: [expect.objectContaining({ line_id: 'A', quantity: '12', location_id: 'BIN' })],
    }))
  })
  it('keeps the current split receipt on refresh and submits the latest versions', async () => {
    const workspace = work()
    workspace.inventory.locations!.push({
      id: 'BIN2', category: 'FABRIC', warehouse: '二仓', code: 'B01', label: '二仓 B01', status: 'ACTIVE', revision: 1,
    })
    api.workspace.mockResolvedValue(workspace)
    api.purchaseSources.mockResolvedValue({ document_revision: 3, match_status: { A: 'MATCHED' }, lines: { A: [purchase('P1'), purchase('P2')] } })
    await open(); await select()
    await wrapper!.get('.receipt-date input').setValue('2026-10-13')
    await wrapper!.get('.posting-row input[type=checkbox]').setValue(true)
    await warehouseInput().setValue('一仓')
    await locationInput().setValue('一仓 A01')
    await quantityInput().setValue('12')
    await click('增加仓位')
    await warehouseInput(2).setValue('二仓')
    await locationInput(2).setValue('二仓 B01')
    await quantityInput(2).setValue('6')
    const secondAllocation = wrapper!.get('.posting-row').findAll('.receipt-allocation')[1]!
    const [lot, roll] = secondAllocation.findAll('input[maxlength="128"]')
    await lot!.setValue('LOT-2')
    await roll!.setValue('ROLL-2')
    await click('实点与差异')
    await wrapper!.get('[aria-label="第1项第1个仓位破损数量"]').setValue('2')
    await wrapper!.get('[aria-label="A采购待收明细"]').setValue('P2')

    const updated = fixture()
    updated.revision = 4
    updated.progress.A = { processed: '20', remaining: '20' }
    updated.progress.B = { processed: '5', remaining: '35' }
    api.detail.mockResolvedValue(updated)
    api.workspace.mockResolvedValue({ ...workspace, inventory: { ...workspace.inventory, revision: 12 } })
    api.purchaseSources.mockResolvedValue({
      document_revision: 4, match_status: { A: 'MATCHED' }, lines: { A: [purchase('P1'), purchase('P2', 5, 3)] },
    })
    api.post.mockResolvedValue(updated)
    await click('刷新进度')

    expect(api.post).not.toHaveBeenCalled()
    expect(wrapper!.get<HTMLInputElement>('.posting-row input[type=checkbox]').element.checked).toBe(true)
    expect(wrapper!.get('.posting-row').text()).toContain('单据尚余由 30 码更新为 20 码')
    expect(quantityInput().element.value).toBe('10')
    expect(quantityInput(2).element.value).toBe('6')
    expect(wrapper!.get<HTMLInputElement>('[aria-label="第2项第1个仓位净入库量"]').element.value).toBe('35')
    expect(wrapper!.get<HTMLSelectElement>('[aria-label="A采购待收明细"]').element.value).toBe('P2')
    await click('确认本次实物收发')
    expect(api.post).toHaveBeenCalledWith('D1', expect.objectContaining({
      expected_revision: 4, expected_inventory_revision: 12, business_date: '2026-10-13',
      lines: [
        expect.objectContaining({
          line_id: 'A', quantity: '10', location_id: 'BIN', purchase_source_id: 'P2',
          expected_source_revision: 5, expected_receipt_count: 3,
          receipt_counts: expect.objectContaining({ counted_quantity: '12', damaged_quantity: '2' }),
        }),
        expect.objectContaining({
          line_id: 'A', quantity: '6', location_id: 'BIN2', lot: 'LOT-2', roll_no: 'ROLL-2',
          purchase_source_id: 'P2', expected_source_revision: 5, expected_receipt_count: 3,
        }),
      ],
    }))
  })
  it.each([
    ['8', '分仓净入库合计超过单据尚余'],
    ['0', '该物料已收货完成，请取消勾选'],
  ])('checks retained inputs against a refreshed remainder of %s', async (remaining, message) => {
    await open(); await select()
    const checkbox = wrapper!.get<HTMLInputElement>('.posting-row input[type=checkbox]')
    await checkbox.setValue(true)
    await locationInput().setValue('一仓 A01')
    await quantityInput().setValue('12')

    const updated = fixture()
    updated.revision = 4
    updated.progress.A = { processed: remaining === '0' ? '40' : '32', remaining }
    api.detail.mockResolvedValue(updated)
    api.purchaseSources.mockResolvedValue({ document_revision: 4, lines: {} })
    await click('刷新进度')
    expect(quantityInput().element.value).toBe('12')
    expect(wrapper!.get('.posting-row [role="alert"]').text()).toContain(message)
    await click('确认本次实物收发')
    expect(api.post).not.toHaveBeenCalled()
    if (remaining === '0') {
      expect(checkbox.element.disabled).toBe(false)
      await checkbox.setValue(false)
      expect(checkbox.element.disabled).toBe(true)
      expect(wrapper!.get('.posting-row').find('[role="alert"]').exists()).toBe(false)
    }
  })
  it('requires a new choice when a refreshed purchase source or warehouse location is unavailable', async () => {
    api.purchaseSources.mockResolvedValue({ document_revision: 3, match_status: { A: 'MATCHED' }, lines: { A: [purchase('P1')] } })
    await open(); await select()
    await wrapper!.get('.posting-row input[type=checkbox]').setValue(true)
    await quantityInput().setValue('12')
    await locationInput().setValue('一仓 A01')

    const workspace = work()
    workspace.inventory.locations = [{ ...workspace.inventory.locations![0]!, id: 'NEW-BIN', code: 'A02', label: '一仓 A02' }]
    api.workspace.mockResolvedValue(workspace)
    api.purchaseSources.mockResolvedValue({ document_revision: 3, match_status: { A: 'MATCHED' }, lines: { A: [purchase('P2')] } })
    await click('刷新进度')
    await click('刷新进度')
    expect(quantityInput().element.value).toBe('12')
    const purchaseSelect = wrapper!.get<HTMLSelectElement>('[aria-label="A采购待收明细"]')
    expect(purchaseSelect.element.value).toBe('')
    expect(wrapper!.get('.purchase-match-message').text()).toContain('请重新选择')
    await click('确认本次实物收发')
    expect(api.post).not.toHaveBeenCalled()
    await purchaseSelect.setValue('P2')
    await click('确认本次实物收发')
    expect(wrapper!.get('.handover-message.error').text()).toContain('选择仓库和仓位')
    expect(api.post).not.toHaveBeenCalled()
  })
  it('keeps a boxed return on the left and removes duplicate warehouse navigation', async () => {
    await open()
    expect(wrapper!.findAll('.handover-tabs button').map(button => button.text())).toEqual(['单据管理', '扫码收发'])
    expect(wrapper!.find('.handover-tabs a').exists()).toBe(false)
    expect(wrapper!.get('.handover-header > :first-child').classes()).toContain('handover-back')
    expect(wrapper!.get('.handover-back').attributes('href')).toBe('/modules/pmc-warehouse/fabric-warehouse/receipts?factory=huakang-c&view=pending')
    expect(wrapper!.text()).not.toContain('查看库存台账')
  })
  it('queries all matching documents and keeps the applied filters when loading more and refreshing', async () => {
    api.workspace.mockResolvedValue({ ...work(), suppliers: [{ id: 'SUP', kind: 'SUPPLIER', code: 'S1', name: '供应商', status: 'ACTIVE', revision: 1, data: {}, updated_at: '' }] })
    await open(); await select()
    await quantityInput().setValue('7')
    await wrapper!.get('[aria-label="搜索交接单据"]').setValue('  布A  ')
    api.list.mockResolvedValue({ items: [{ ...fixture(), line_count: 2 }], total: 2, limit: 1, offset: 0 })
    await wrapper!.get('[aria-label="筛选供应商"]').setValue('SUP'); await flushPromises()
    await wrapper!.get('[aria-label="筛选单据状态"]').setValue('CONFIRMED'); await flushPromises()
    expect(api.list).toHaveBeenLastCalledWith(0, { search: '布A', supplier_id: 'SUP', kind: 'ALL', status: 'CONFIRMED' })
    expect(quantityInput().element.value).toBe('7')
    api.list.mockResolvedValue({ items: [{ ...fixture(), id: 'D2', line_count: 2 }], total: 2, limit: 1, offset: 1 })
    await click('加载更早单据')
    expect(api.list).toHaveBeenLastCalledWith(1, { search: '布A', supplier_id: 'SUP', kind: 'ALL', status: 'CONFIRMED' })
    expect(wrapper!.findAll('.document-item')).toHaveLength(2)
    await click('刷新')
    expect(api.list).toHaveBeenLastCalledWith(0, expect.objectContaining({ supplier_id: 'SUP', status: 'CONFIRMED' }))
    await click('重置')
    expect(api.list).toHaveBeenLastCalledWith(0, { search: '', supplier_id: '', kind: 'ALL', status: 'ALL' })
  })
  it('clears the supplier filter for issue documents and gives a useful empty result', async () => {
    await open()
    api.list.mockResolvedValue({ items: [], total: 0, limit: 50, offset: 0 })
    await wrapper!.get('[aria-label="筛选单据用途"]').setValue('ISSUE'); await flushPromises()
    expect(api.list).toHaveBeenLastCalledWith(0, expect.objectContaining({ supplier_id: '', kind: 'ISSUE' }))
    expect(wrapper!.get('[aria-label="筛选供应商"]').attributes('disabled')).toBeDefined()
    expect(wrapper!.text()).toContain('没有符合条件的单据')
  })
  it('opens a scanned document on submit without posting stock', async () => {
    api.scan.mockResolvedValue(fixture())
    api.purchaseSources.mockResolvedValue({ document_revision: 3, match_status: { A: 'MATCHED' }, lines: { A: [purchase('P1')] } })
    await open(false, '/?factory=huakang-c&tab=scan')
    await wrapper!.get('[aria-label="扫描单据二维码"]').setValue(' MH1:D1:1 ')
    await wrapper!.get('.scan-card form').trigger('submit'); await flushPromises()
    expect(api.scan).toHaveBeenCalledWith('MH1:D1:1')
    expect(api.purchaseSources).toHaveBeenCalledWith('D1')
    expect(wrapper!.get<HTMLSelectElement>('[aria-label="A采购待收明细"]').element.value).toBe('P1')
    expect(wrapper!.get('.receipt-metrics').findAll('dd').slice(0, 2).map(value => value.text())).toEqual(['40 码', '30 码'])
    expect(quantityInput().element.value).toBe('30')
    expect(warehouseInput().element.value).toBe('一仓')
    expect(wrapper!.get('.posting-row').text()).toContain('增加仓位')
    expect(api.post).not.toHaveBeenCalled()
  })
  it('posts only explicitly selected lines with the actual quantity and revisions', async () => {
    api.post.mockResolvedValue(fixture()); await open(); await select()
    expect(api.post).not.toHaveBeenCalled()
    await wrapper!.get('.posting-row input[type=checkbox]').setValue(true)
    await quantityInput().setValue('7.5')
    expect(wrapper!.get('.receipt-metrics').findAll('dd').slice(0, 2).map(value => value.text())).toEqual(['40 码', '30 码'])
    await locationInput().setValue('一仓 A01')
    await click('确认本次实物收发')
    const body = api.post.mock.calls[0]![1]
    expect(body.expected_revision).toBe(3); expect(body.expected_inventory_revision).toBe(8)
    expect(body.lines).toEqual([{ line_id: 'A', quantity: '7.5', batch_id: '', location_id: 'BIN', lot: 'LOT', roll_no: '' }])
  })
  it.each([true, false])('requires reviewing an existing manual receipt before posting (same number: %s)', async (exact) => {
    const row = fixture()
    row.prior_receipts = { A: { review_token: 'a'.repeat(64), items: [{
      id: 'ORIGINAL', reference: exact ? 'DN-1' : 'DN-01', date: '2026-10-12', quantity: '12',
      production_no: 'PROD-1', contract_no: 'C-1', order_no: '',
      parts: [{ lot: 'LOT', roll_no: 'R1', location: '一仓 A01' }],
      exact_reference: exact, blocks_posting: exact, can_link: true, reason: '',
    }] } }
    api.detail.mockResolvedValue(row)
    api.purchaseSources.mockResolvedValue({ document_revision: 3, lines: {} })
    api.post.mockResolvedValue(fixture())
    await open(); await select()
    expect(wrapper!.get('.prior-receipts').text()).toContain('生产单 PROD-1')
    await wrapper!.get('.receipt-material input[type=checkbox]').setValue(true)
    await quantityInput().setValue('7.5')
    await locationInput().setValue('一仓 A01')
    await click('确认本次实物收发')
    expect(api.post).not.toHaveBeenCalled()
    if (exact) {
      const linked = { ...fixture(), revision: 4, progress: { ...row.progress, A: { processed: '22', remaining: '18' } } }
      api.linkReceipt.mockResolvedValue(linked)
      api.purchaseSources.mockResolvedValue({ document_revision: 4, lines: {} })
      await click('关联这笔入库')
      expect(api.linkReceipt).not.toHaveBeenCalled()
      await click('确认补关联')
      expect(api.linkReceipt).toHaveBeenCalledWith('D1', expect.objectContaining({
        expected_revision: 3, line_id: 'A', receipt_id: 'ORIGINAL',
      }))
      expect(quantityInput().element.value).toBe('7.5')
      expect(locationInput().element.value).toBe('一仓 A01')
      expect(wrapper!.get('.receipt-metrics').text()).toContain('18 码')
      await click('确认本次实物收发')
      expect(api.post).toHaveBeenCalledWith('D1', expect.objectContaining({ expected_revision: 4 }))
    } else {
      await wrapper!.get('.prior-receipts input[type=checkbox]').setValue(true)
      await click('确认本次实物收发')
      expect(api.post).toHaveBeenCalledWith('D1', expect.objectContaining({
        manual_receipt_reviews: { A: 'a'.repeat(64) },
      }))
    }
  })
  it('lets a receipt with conflicting purchase candidates record a reason and enter purchase review', async () => {
    api.purchaseSources.mockResolvedValue({ document_revision: 3, match_status: { A: 'NOT_FOUND' }, lines: { A: [purchase('P1')] } })
    api.post.mockResolvedValue(fixture())
    await open(); await select()
    await wrapper!.get('.receipt-material input[type=checkbox]').setValue(true)
    await quantityInput().setValue('20')
    await locationInput().setValue('一仓 A01')
    await wrapper!.get('[aria-label="A采购待核对"]').setValue(true)
    await click('确认本次实物收发')
    expect(api.post).not.toHaveBeenCalled()
    expect(wrapper!.text()).toContain('请填写采购待核对原因')
    await wrapper!.get('[aria-label="A采购待核对原因"]').setValue('原合同与候选不同')
    await click('确认本次实物收发')
    const part = api.post.mock.calls[0]![1].lines[0]
    expect(part).toMatchObject({ line_id: 'A', quantity: '20', procurement_pending_reason: '原合同与候选不同' })
    expect(part).not.toHaveProperty('purchase_source_id')
    expect(wrapper!.text()).toContain('收料入库 → 入库记录')
  })
  it('previews revoking a manual receipt link, requires a reason, and shows the audit entry', async () => {
    const row = fixture()
    row.progress.A = { processed: '30', remaining: '10' }
    row.movements = [{
      operation_id: 'LINK-1', line_id: 'A', quantity: '20', business_date: '2026-10-12',
      reversed: false, manual_reference: 'OLD-1',
    }, { operation_id: 'RC-1', line_id: 'A', quantity: '10', business_date: '2026-10-13', reversed: false }]
    api.detail.mockResolvedValue(row)
    api.purchaseSources.mockResolvedValue({ document_revision: 3, lines: {} })
    api.unlinkReceipt.mockResolvedValue({ ...row, revision: 4, progress: { ...row.progress, A: { processed: '10', remaining: '30' } },
      movements: [row.movements[1]], revoked_receipt_links: [{
        link_id: 'LINK-1', line_id: 'A', reference: 'OLD-1', quantity: '20', business_date: '2026-10-12',
        revoked_at: '2026-10-14T09:00:00+08:00', revoked_by: '仓管甲', reason: '旧记录归属另一张单',
      }],
    })
    await open(); await select()
    await click('撤回关联')
    const form = wrapper!.get('.receipt-unlink-form')
    expect(form.text()).toContain('已收 30 → 10 码 · 待收 10 → 30 码')
    expect(form.get('button[type="submit"]').attributes('disabled')).toBeDefined()
    await form.get('input').setValue('旧记录归属另一张单')
    api.purchaseSources.mockResolvedValue({ document_revision: 4, lines: {} })
    await form.trigger('submit'); await flushPromises()
    expect(api.unlinkReceipt).toHaveBeenCalledWith('D1', expect.objectContaining({
      link_id: 'LINK-1', expected_revision: 3, expected_processed: '30', reason: '旧记录归属另一张单',
    }))
    expect(wrapper!.text()).toContain('已撤回关联 · OLD-1')
    expect(wrapper!.text()).toContain('旧记录归属另一张单')
  })
  it('carries the current quantity into the count fields and posts the calculated net', async () => {
    api.post.mockResolvedValue(fixture())
    await open(); await select()
    await click('实点与差异')
    expect(quantityInput().attributes('readonly')).toBeDefined()
    expect(quantityInput().element.closest('.receipt-count-fields')).not.toBeNull()
    expect(wrapper!.get<HTMLInputElement>('[aria-label="第1项第1个仓位实点数量"]').element.value).toBe('30')
    expect(wrapper!.find('[aria-label="第1项本批送货数量"]').exists()).toBe(false)
    await click('实点与差异')
    expect(quantityInput().element.value).toBe('30')
    expect(quantityInput().attributes('readonly')).toBeUndefined()
    await quantityInput().setValue('18.25')
    await click('实点与差异')
    expect(wrapper!.get<HTMLInputElement>('[aria-label="第1项第1个仓位实点数量"]').element.value).toBe('18.25')
    await click('增加仓位')
    expect(wrapper!.get<HTMLInputElement>('[aria-label="第1项第2个仓位实点数量"]').element.value).toBe('')
    await wrapper!.get('[aria-label="移除第1项的第2个仓位"]').trigger('click')
    await wrapper!.get('[aria-label="第1项第1个仓位实点数量"]').setValue('12.5')
    await wrapper!.get('[aria-label="第1项第1个仓位破损数量"]').setValue('1')
    await wrapper!.get('[aria-label="第1项第1个仓位拒收数量"]').setValue('0.5')
    await wrapper!.get('[aria-label="第1项第1个仓位其他不可用"]').setValue('0.25')
    expect(quantityInput().element.value).toBe('10.75')
    await click('实点与差异')
    expect(quantityInput().element.value).toBe('10.75')
    expect(quantityInput().element.closest('.receipt-count-fields')).toBeNull()
    await wrapper!.get('.posting-row input[type=checkbox]').setValue(true)
    await locationInput().setValue('一仓 A01')
    await click('确认本次实物收发')
    const body = api.post.mock.calls[0]![1]
    expect(body.delivery_quantities).toBeUndefined()
    expect(body).toMatchObject({
      lines: [{ line_id: 'A', quantity: '10.75', location_id: 'BIN', receipt_counts: {
        counted_quantity: '12.5', damaged_quantity: '1', rejected_quantity: '0.5', other_unusable_quantity: '0.25',
      } }],
    })
  })
  it('can save an all-rejected split without a stock location or purchase selection', async () => {
    api.purchaseSources.mockResolvedValue({ document_revision: 3, lines: { A: [purchase('P1')] } })
    api.post.mockResolvedValue(fixture())
    await open(); await select()
    await click('实点与差异')
    await wrapper!.get('.posting-row input[type=checkbox]').setValue(true)
    await wrapper!.get('[aria-label="第1项第1个仓位实点数量"]').setValue('0')
    await click('确认本次实物收发')
    expect(api.post).not.toHaveBeenCalled()
    expect(wrapper!.text()).toContain('实点数量须大于零')
    await wrapper!.get('[aria-label="第1项第1个仓位实点数量"]').setValue('5')
    await wrapper!.get('[aria-label="第1项第1个仓位拒收数量"]').setValue('5')
    expect(quantityInput().element.value).toBe('0')
    expect(warehouseInput().attributes('disabled')).toBeDefined()
    await click('确认本次实物收发')
    const line = api.post.mock.calls[0]![1].lines[0]
    expect(line).toMatchObject({ quantity: '0', location_id: '', receipt_counts: { rejected_quantity: '5' } })
    expect(line.purchase_source_id).toBeUndefined()
    expect(wrapper!.text()).toContain('本次收料差异已保存，净入库量为零')
  })
  it('warns about the two duplicate splits and preserves deliberately blank rolls in the submission', async () => {
    const row = fixture()
    row.data.lines[0]!.roll_no = 'R1'
    api.detail.mockResolvedValue(row)
    api.post.mockResolvedValue(row)
    await open(); await select()
    await wrapper!.get('.posting-row input[type=checkbox]').setValue(true)
    await locationInput().setValue('一仓 A01')
    await quantityInput().setValue('5')
    await click('增加仓位')
    await locationInput(2).setValue('一仓 A01')
    await quantityInput(2).setValue('5')
    expect(wrapper!.get('.receipt-allocations [role="alert"]').text()).toContain('第 1 项和第 2 项')
    await click('确认本次实物收发')
    expect(api.post).not.toHaveBeenCalled()
    for (const part of wrapper!.get('.posting-row').findAll('.receipt-allocation')) {
      await part.findAll('input[maxlength="128"]')[1]!.setValue('')
    }
    await click('确认本次实物收发')
    expect(api.post.mock.calls[0]![1].lines).toEqual([
      expect.objectContaining({ location_id: 'BIN', roll_no: '', roll_no_is_blank: true }),
      expect.objectContaining({ location_id: 'BIN', roll_no: '', roll_no_is_blank: true }),
    ])
  })
  it('shows a full rejection on the list and saves an audited follow-up with a frozen retry', async () => {
    const row = fixture()
    row.issuer_id = 'SUPPLIER-1'
    row.processing_status = 'PENDING'
    row.progress.A = { processed: '0', remaining: '40' }
    row.receipt_rejection = { rejected_quantity: '40', unit: '码', status: null }
    row.receipt_observations = [{ request_id: 'OBS-1', business_date: '2026-10-13', actor_name: '记录人', lines: [{
      line_id: 'A', item_name: '物料A', item_code: 'A', unit: '码',
      full_rejection: { rejected_quantity: '40', followup: null },
      parts: [{ counted_quantity: '40', rejected_quantity: '40', damaged_quantity: '0', other_unusable_quantity: '0', accepted_quantity: '0', lot: 'LOT', roll_no: '' }],
    }] }]
    const saved = clone(row)
    saved.revision = 4
    saved.receipt_rejection!.status = 'PENDING_REDELIVERY'
    saved.receipt_observations![0]!.lines[0]!.full_rejection!.followup = {
      status: 'PENDING_REDELIVERY', reason: '请补送同款', actor_name: '仓管甲', recorded_at: '2026-10-13T16:30:00+08:00',
    }
    api.detail.mockResolvedValue(row)
    api.list.mockResolvedValue({ items: [{ ...row, line_count: 2 }], limit: 50, offset: 0 })
    api.recordRejectionFollowup.mockRejectedValueOnce(new AxiosError('网络断开')).mockResolvedValueOnce(saved)
    await open(); await select()
    const list = wrapper!.get('.document-list')
    expect(list.text()).toContain('全拒收')
    expect(list.text()).toContain('拒收 40 码 · 本项实收 0 码')
    expect(list.text()).not.toContain('待收货')
    await quantityInput().setValue('4')
    await click('查看收料差异')
    await click('处理拒收')
    const form = wrapper!.get('.rejection-followup-form')
    await form.get('select').setValue('PENDING_REDELIVERY')
    expect(form.get('button[type="submit"]').attributes('disabled')).toBeDefined()
    await form.get('textarea').setValue('请补送同款')
    await form.trigger('submit'); await flushPromises()
    expect(api.recordRejectionFollowup).toHaveBeenCalledWith('D1', expect.objectContaining({
      expected_revision: 3, observation_request_id: 'OBS-1', line_id: 'A', status: 'PENDING_REDELIVERY', reason: '请补送同款',
    }))
    api.list.mockResolvedValue({ items: [{ ...saved, line_count: 2 }], limit: 50, offset: 0 })
    await click('重试原提交')
    expect(api.recordRejectionFollowup.mock.calls[1]).toEqual(api.recordRejectionFollowup.mock.calls[0])
    expect(list.text()).toContain('待补送')
    expect(wrapper!.get('.rejection-evidence').text()).toContain('请补送同款 · 仓管甲')
    expect(quantityInput().element.value).toBe('4')
    expect(api.post).not.toHaveBeenCalled()
  })
  it('splits one receipt line across eligible warehouses with an exact quantity cap and frozen retry', async () => {
    const row = fixture()
    row.progress.A = { processed: '39.7', remaining: '0.3' }
    api.detail.mockResolvedValue(row)
    api.purchaseSources.mockResolvedValue({ document_revision: 3, match_status: { A: 'MATCHED' }, lines: { A: [{ ...purchase('P1'), remaining: '0.3' }] } })
    const ws = work()
    ws.inventory.locations!.push(
      { id: 'BIN2', category: 'FABRIC', warehouse: '二仓', code: 'B01', label: '二仓 B01', status: 'ACTIVE', revision: 1 },
      { id: 'WRONG', category: 'THREAD', warehouse: '线仓', code: 'T01', label: '线仓 T01', status: 'ACTIVE', revision: 1 },
      { id: 'STOP', category: 'FABRIC', warehouse: '旧仓', code: 'Z01', label: '旧仓 Z01', status: 'INACTIVE', revision: 1 },
    )
    api.workspace.mockResolvedValue(ws)
    api.post.mockRejectedValueOnce(new AxiosError('网络断开')).mockResolvedValueOnce(row)
    await open(); await select()
    await wrapper!.get('.posting-row input[type=checkbox]').setValue(true)
    expect(Array.from(warehouseInput().element.options, option => option.value)).toEqual(['', '一仓', '二仓'])
    await warehouseInput().setValue('一仓')
    await locationInput().setValue('一仓 A01')
    await quantityInput().setValue('0.1')
    await click('增加仓位')
    await warehouseInput(2).setValue('一仓')
    await locationInput(2).setValue('一仓 A01')
    await warehouseInput(2).setValue('二仓')
    expect(locationInput(2).element.value).toBe('')
    await quantityInput(2).setValue('0.21')
    expect(wrapper!.get('.receipt-metric-total dd').text()).toBe('0.31 码')
    await click('确认本次实物收发')
    expect(wrapper!.text()).toContain('分仓净入库合计超过单据尚余')
    expect(api.post).not.toHaveBeenCalled()
    await quantityInput(2).setValue('0.2')
    expect(wrapper!.get('.receipt-metric-total dd').text()).toBe('0.3 码')
    expect(wrapper!.find('[aria-label="A超收说明"]').exists()).toBe(false)
    await click('确认本次实物收发')
    expect(wrapper!.text()).toContain('请为每个入库仓位填写净入库量')
    expect(api.post).not.toHaveBeenCalled()
    await locationInput(2).setValue('二仓 B01')
    await click('确认本次实物收发')
    const frozen = clone(api.post.mock.calls[0]![1])
    expect(frozen.lines).toEqual([
      expect.objectContaining({ line_id: 'A', quantity: '0.1', location_id: 'BIN', purchase_source_id: 'P1', expected_source_revision: 4, expected_receipt_count: 2 }),
      expect.objectContaining({ line_id: 'A', quantity: '0.2', location_id: 'BIN2', purchase_source_id: 'P1', expected_source_revision: 4, expected_receipt_count: 2 }),
    ])
    await click('重试原提交')
    expect(api.post.mock.calls[1]![1]).toEqual(frozen)
  })
  it('freezes an unknown write outcome and retries exactly the same request', async () => {
    api.post.mockRejectedValueOnce(new AxiosError('网络断开')); api.post.mockResolvedValueOnce(fixture())
    await open(); await select(); await wrapper!.get('.posting-row input[type=checkbox]').setValue(true)
    await locationInput().setValue('一仓 A01')
    await click('确认本次实物收发'); const first = clone(api.post.mock.calls[0]![1])
    expect(quantityInput().attributes('disabled')).toBeUndefined() // parent fieldset enforces locking
    expect(wrapper!.get('.posting-card fieldset').attributes('disabled')).toBeDefined()
    await click('重试原提交'); expect(api.post.mock.calls[1]![1]).toEqual(first)
  })
  it('saves reactive draft edits and guards unsaved navigation', async () => {
    const row = fixture(); row.status = 'DRAFT'; api.detail.mockResolvedValue(row)
    api.save.mockImplementation((_id, body) => Promise.resolve({ ...row, revision: 4, data: body.data }))
    const router = await open(); await select(); await wrapper!.get('[aria-label="第1行单据数量"]').setValue('19')
    expect(wrapper!.findAll('button').find(b => b.text() === '确认并打印原单')!.attributes('disabled')).toBeUndefined()
    await router.push('/other'); expect(router.currentRoute.value.path).toBe('/')
    await click('保存核对内容'); expect(api.save.mock.calls[0]![1].data.lines[0].quantity).toBe('19')
    await router.push('/other'); expect(router.currentRoute.value.path).toBe('/other')
  })
  it('clears private documents on authorization changes and ignores late responses', async () => {
    let resolve: (row: HandoverDocument) => void = () => {}
    api.detail.mockReturnValue(new Promise<HandoverDocument>(r => { resolve = r }))
    await open(); await wrapper!.findAll('button').find(button => button.text().startsWith('DN-1'))!.trigger('click')
    api.list.mockResolvedValue({ items: [], limit: 50, offset: 0 }); auth.authorizationVersion++; await flushPromises()
    resolve(fixture()); await flushPromises(); expect(wrapper!.find('.posting-card').exists()).toBe(false)
  })
  it.each(['SUPPLIER', 'REQUESTOR'])('public %s preparation keeps stock private and offers the delivery template only to suppliers', async (kind) => {
    api.context.mockResolvedValue({ name: '制单方', kind, supplier_id: kind === 'SUPPLIER' ? 'SUP' : '' })
    await open(true, '/#key=public-test-key'); await select()
    expect(api.workspace).not.toHaveBeenCalled(); expect(wrapper!.find('.posting-card').exists()).toBe(false)
    expect(api.purchaseSources).not.toHaveBeenCalled()
    expect(wrapper!.text()).not.toContain('制单方与链接')
    expect(wrapper!.find('[aria-label="筛选供应商"]').exists()).toBe(false)
    expect(wrapper!.find('.handover-back').exists()).toBe(false)
    const download = wrapper!.find('.upload-actions a[download]')
    expect(download.exists()).toBe(kind === 'SUPPLIER')
    if (kind === 'SUPPLIER') {
      expect(download.text()).toBe('下载统一模板')
      expect(download.attributes('href')).toBe('/templates/material-handover/supplier-delivery-v1.xlsx')
      expect(download.attributes('download')).toBe('供应商统一送货单模板.xlsx')
      expect(wrapper!.get('.upload-actions button').text()).toBe('选择文件并识别')
    }
  })
  it('confirms a reviewed supplier upload without opening print until the supplier chooses it',async()=>{
    const row=fixture();row.status='DRAFT';row.issuer_id='ISSUER-A';api.upload.mockResolvedValue(row)
    api.action.mockImplementation((_id,_kind,body)=>Promise.resolve({...fixture(),issuer_id:row.issuer_id,data:body.data}))
    await open(true,'/#key=public-test-key')
    const file = new File(['filled template'], '供应商统一送货单模板.xlsx', { type: 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet' })
    const input = wrapper!.get('input[type="file"]')
    Object.defineProperty(input.element, 'files', { value: [file] })
    await input.trigger('change'); await flushPromises()
    expect(api.upload).toHaveBeenCalledWith(file, expect.any(String))
    expect(api.action).not.toHaveBeenCalled(); expect(window.print).not.toHaveBeenCalled()
    await wrapper!.get('[aria-label="第1行单据数量"]').setValue('9')
    api.printFile.mockResolvedValue(new Blob(['pdf'],{type:'application/pdf'}))
    await wrapper!.get('[aria-label="第1行参考单价"]').setValue('2.3');await click('确认送货单')
    expect(api.save).not.toHaveBeenCalled();expect(api.action.mock.calls[0]![2].data.lines[0].quantity).toBe('9')
    expect(api.action.mock.calls[0]![2].data.lines[0].unit_price).toBe('2.3')
    expect(api.action.mock.calls[0]![2].data.lines[0].price_unit).toBe('码')
    expect(wrapper!.text()).toContain('送货单已确认，已生成交接二维码')
    expect(api.printFile).not.toHaveBeenCalled();expect(window.print).not.toHaveBeenCalled()
    await click('原单加码打印')
    expect(api.printFile).toHaveBeenCalledWith('D1',3,'right')
    expect(window.print).toHaveBeenCalledOnce()
    expect(wrapper!.find('.original-print-preview').exists()).toBe(false)
    expect(wrapper!.find('main > .handover-original-print').exists()).toBe(true)
    expect(api.post).not.toHaveBeenCalled()
  })
  it('prepares the chosen corner and clears print copies when authorization changes',async()=>{
    api.printFile.mockResolvedValue(new Blob(['pdf'],{type:'application/pdf'}))
    await open();await select();await wrapper!.get('[aria-label="原单二维码位置"]').setValue('left')
    await click('原单加码打印');expect(api.printFile).toHaveBeenCalledWith('D1',3,'left')
    expect(wrapper!.find('main > .handover-original-print').exists()).toBe(true)
    auth.authorizationVersion++;await flushPromises()
    expect(wrapper!.find('.handover-original-print').exists()).toBe(false)
    expect(wrapper!.text()).not.toContain('下载加码原单 PDF')
  })
  it('prints the company name and keeps sign-off with the final confirmed material row', async () => {
    const row = { ...fixture(), issuer_id: 'ISSUER-A' }
    row.data.counterparty = '锦禾纺织有限公司'
    row.data.lines[0]!.unit_price = '0'
    api.detail.mockResolvedValue(row)
    await open(true, '/#key=public-test-key')
    await select()
    await click('打印统一明细（备用）')

    const sheet = wrapper!.get('main > .handover-summary-print')
    expect(sheet.get('.summary-heading .print-qr').attributes('src')).toBe('blob:test')
    expect(sheet.get('h2').text()).toBe('锦禾纺织有限公司')
    expect(sheet.get('.summary-kicker').text()).toBe('送货交接单 · 已确认')
    expect(sheet.get('.summary-heading').text()).not.toContain('供应商')
    expect(sheet.get('.summary-number').text()).toBe('DN-1')
    expect(sheet.get('tbody .summary-material').text()).toBe('物料A')
    expect(sheet.get('tbody .summary-quantity').text()).toBe('40 码')
    expect(sheet.get('tbody tr > td:nth-child(5)').text()).toBe('0')
    const ending = sheet.get('tbody.summary-ending')
    expect(ending.findAll('.summary-material').map(item => item.text())).toEqual(['物料B'])
    expect(ending.get('.summary-signoff').text()).toContain('送货人签字收货人签字签收日期签收备注')
    expect(window.print).toHaveBeenCalledOnce()
    expect(api.post).not.toHaveBeenCalled()
  })
  it('does not print a cached QR when a fresh request says the supplier document was voided', async () => {
    const row = { ...fixture(), issuer_id: 'ISSUER-A' }
    api.detail.mockResolvedValue(row)
    await open(true, '/#key=public-test-key'); await select(); await click('显示二维码')
    expect(wrapper!.find('.qr-image').exists()).toBe(true)
    api.file.mockRejectedValueOnce(Object.assign(new AxiosError('单据已作废'), { response: { status: 409 } }))
    await click('打印统一明细（备用）')
    expect(wrapper!.find('.qr-image').exists()).toBe(false)
    expect(wrapper!.text()).toContain('旧二维码和加码副本不可再用')
    expect(window.print).not.toHaveBeenCalled()
  })
  it('discards a late QR response after another request reports that the supplier document was voided', async () => {
    let finish!: (file: Blob) => void
    api.detail.mockResolvedValue({ ...fixture(), issuer_id: 'ISSUER-A' })
    api.file.mockReturnValueOnce(new Promise<Blob>(resolve => { finish = resolve }))
      .mockRejectedValueOnce(Object.assign(new AxiosError('单据已作废'), { response: { status: 409 } }))
    await open(true, '/#key=public-test-key'); await select()
    await click('打印统一明细（备用）'); await click('显示二维码')
    finish(new Blob(['<svg/>'], { type: 'image/svg+xml' })); await flushPromises()
    expect(wrapper!.find('.qr-image').exists()).toBe(false)
    expect(window.print).not.toHaveBeenCalled()
  })
  it.each(['原单加码打印', '下载加码原单 PDF'])('rechecks a prepared copy before %s', async (operation) => {
    const row = { ...fixture(), issuer_id: 'ISSUER-A' }
    api.detail.mockResolvedValue(row)
    api.printFile.mockResolvedValue(new Blob(['pdf'], { type: 'application/pdf' }))
    const download = vi.spyOn(HTMLAnchorElement.prototype, 'click').mockImplementation(() => {})
    await open(true, '/#key=public-test-key'); await select(); await click('原单加码打印')
    expect(window.print).toHaveBeenCalledOnce()
    api.detail.mockResolvedValueOnce({ ...row, status: 'VOID', code: '', revision: row.revision + 1 })
    await click(operation)
    expect(wrapper!.find('.handover-original-print').exists()).toBe(false)
    expect(wrapper!.find('.code-card').exists()).toBe(false)
    expect(wrapper!.text()).toContain('旧二维码和加码副本不可再用')
    expect(window.print).toHaveBeenCalledOnce()
    expect(download).not.toHaveBeenCalled()
  })
  it('cancels pending automatic printing as soon as another supplier document is opened', async () => {
    const row = { ...fixture(), issuer_id: 'ISSUER-A' }
    const other = { ...row, id: 'D2', code: 'MH1:D2:1', data: { ...row.data, source_no: 'DN-2' } }
    api.list.mockResolvedValue({ items: [{ ...row, line_count: 2 }, { ...other, line_count: 2 }], limit: 50, offset: 0 })
    api.detail.mockResolvedValueOnce(row)
    api.printFile.mockResolvedValue(new Blob(['pdf'], { type: 'application/pdf' }))
    let finishPrint!: (document: HandoverDocument) => void
    let finishOpen!: (document: HandoverDocument) => void
    api.detail.mockReturnValueOnce(new Promise<HandoverDocument>(resolve => { finishPrint = resolve }))
      .mockReturnValueOnce(new Promise<HandoverDocument>(resolve => { finishOpen = resolve }))
    await open(true, '/#key=public-test-key'); await select(); await click('原单加码打印')
    expect(api.detail.mock.calls.map(([id]) => id)).toEqual(['D1', 'D1'])
    await wrapper!.findAll('button').find(button => button.text().startsWith('DN-2'))!.trigger('click')
    finishPrint(row); await flushPromises()
    expect(window.print).not.toHaveBeenCalled()
    expect(wrapper!.find('.handover-original-print').exists()).toBe(false)
    finishOpen(other); await flushPromises()
    expect(wrapper!.get('.detail-heading h2').text()).toBe('DN-2')
  })
  it('cancels preparation without printing its late response and can print the same document again', async () => {
    let finishFirst!: (file: Blob) => void
    const pdf = new Blob(['pdf'], { type: 'application/pdf' })
    api.printFile.mockReturnValueOnce(new Promise<Blob>(resolve => { finishFirst = resolve })).mockResolvedValue(pdf)
    await open(); await select(); await click('原单加码打印')
    expect(wrapper!.get('.print-preparing').text()).toBe('正在准备加码原单…')
    expect(wrapper!.find('.original-print-preview').exists()).toBe(false)

    await click('取消准备')
    finishFirst(pdf); await flushPromises()
    expect(window.print).not.toHaveBeenCalled()
    expect(wrapper!.find('.handover-original-print').exists()).toBe(false)

    await click('原单加码打印')
    expect(api.printFile).toHaveBeenLastCalledWith('D1', 3, 'right')
    expect(window.print).toHaveBeenCalledOnce()
  })
  it('does not print a late PDF for a cleared account context',async()=>{
    let resolve!:(file:Blob)=>void
    api.printFile.mockReturnValue(new Promise<Blob>(done=>{resolve=done}))
    await open();await select();await wrapper!.findAll('button').find(b=>b.text()==='原单加码打印')!.trigger('click')
    auth.authorizationVersion++;await flushPromises();resolve(new Blob(['pdf'],{type:'application/pdf'}));await flushPromises()
    expect(window.print).not.toHaveBeenCalled();expect(wrapper!.find('.handover-original-print').exists()).toBe(false)
  })
  it('reuses a prepared original after the browser dialog closes and can switch to summary printing', async () => {
    api.printFile.mockResolvedValue(new Blob(['pdf'], { type: 'application/pdf' }))
    await open(true, '/#key=public-test-key')
    await select()
    await click('原单加码打印')
    expect(wrapper!.get('main').classes()).toContain('original-print-active')

    window.dispatchEvent(new Event('afterprint'))
    await flushPromises()
    expect(wrapper!.get('main').classes()).not.toContain('original-print-active')
    await click('原单加码打印')
    expect(api.printFile).toHaveBeenCalledOnce()
    expect(window.print).toHaveBeenCalledTimes(2)

    window.dispatchEvent(new Event('afterprint'))
    await click('打印统一明细（备用）')
    expect(window.print).toHaveBeenCalledTimes(3)
    expect(wrapper!.get('main').classes()).not.toContain('original-print-active')
    expect(wrapper!.find('.handover-original-print').exists()).toBe(false)
  })
  it('cancels a summary request before its QR response arrives', async () => {
    let finish!: (file: Blob) => void
    api.file.mockReturnValueOnce(new Promise<Blob>(resolve => { finish = resolve }))
    await open(true, '/#key=public-test-key')
    await select()
    await click('打印统一明细（备用）')
    await click('取消准备')
    finish(new Blob(['<svg/>'], { type: 'image/svg+xml' }))
    await flushPromises()
    expect(window.print).not.toHaveBeenCalled()
    expect(wrapper!.find('.qr-image').exists()).toBe(false)
  })
  it('shows the server lock message and can retry printing the saved document', async () => {
    api.printFile.mockRejectedValueOnce(Object.assign(new AxiosError('busy'), {
      response: { status: 503, data: new Blob([JSON.stringify({ detail: '数据库忙，请稍后重试原单加码打印' })], { type: 'application/json' }) },
    })).mockResolvedValue(new Blob(['pdf'], { type: 'application/pdf' }))
    await open(true, '/#key=public-test-key')
    await select()
    await click('原单加码打印')
    expect(wrapper!.get('[role="alert"]').text()).toContain('数据库忙，请稍后重试原单加码打印')
    expect(wrapper!.find('.handover-original-print').exists()).toBe(false)
    await click('原单加码打印')
    expect(window.print).toHaveBeenCalledOnce()
    expect(api.action).not.toHaveBeenCalled()
    expect(api.save).not.toHaveBeenCalled()
  })
  it('keeps PDF download available when browser page rendering fails', async () => {
    originalRender.ready = false
    api.printFile.mockResolvedValue(new Blob(['pdf'], { type: 'application/pdf' }))
    const download = vi.spyOn(HTMLAnchorElement.prototype, 'click').mockImplementation(() => {})
    await open(true, '/#key=public-test-key')
    await select()
    await click('原单加码打印')
    const renderer = wrapper!.getComponent({ name: 'OriginalPrintStub' })
    renderer.vm.$emit('failed', renderer.props('token'), '无法绘制')
    await flushPromises()
    expect(window.print).not.toHaveBeenCalled()
    expect(wrapper!.find('.handover-original-print').exists()).toBe(false)
    expect(wrapper!.get('[role="alert"]').text()).toContain('可下载加码 PDF 打印')
    await click('下载加码原单 PDF')
    expect(download).toHaveBeenCalledOnce()
  })
})
