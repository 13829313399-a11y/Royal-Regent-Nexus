import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { mount, flushPromises, DOMWrapper, type VueWrapper } from '@vue/test-utils'
import { createMemoryHistory, createRouter } from 'vue-router'
import Workspace from '../WarehouseOperationsWorkspace.vue'
import { documentProgress, remaining, sumQuantities } from '../operations'
import type { WarehouseDocument, WarehouseDocumentInput, WarehouseDomain, WarehouseOperationsWorkspace } from '@/api/warehouseOperations'

const api = vi.hoisted(() => ({ workspace: vi.fn(), post: vi.fn(), bulkIssue: vi.fn() }))
vi.mock('@/api/warehouseOperations', () => ({ warehouseOperationsApi: api }))
let wrapper: VueWrapper | undefined
const empty = (): WarehouseOperationsWorkspace => ({ revision: 3, locations: ['A01', 'A02', 'B03'].map(code => ({ id: code, warehouse: '一仓', code, label: `一仓／${code}`, status: 'ACTIVE', revision: 1 })), stock: [], documents: [], permissions: { read: true, operate: true, quality: false, correct: false } })
async function open(section = 'inventory', view = 'pending-issues', data = empty(), warehouse: WarehouseDomain = 'fabric') {
  data.stock = data.stock.map(row => ({ location_id: row.location, location_verified: true, location_status: 'ACTIVE', ...row }))
  api.workspace.mockResolvedValue(data)
  const router = createRouter({ history: createMemoryHistory(), routes: [{ path: '/', component: Workspace, props: { warehouse, section, view } }] })
  await router.push('/'); await router.isReady()
  wrapper = mount(Workspace, { props: { warehouse, section, view }, global: { plugins: [router] }, attachTo: document.body })
  await flushPromises()
  return new DOMWrapper(document.body)
}
beforeEach(() => { vi.clearAllMocks() })
afterEach(() => { wrapper?.unmount(); wrapper = undefined; document.body.innerHTML = ''; vi.restoreAllMocks() })
async function fillRequest(body: DOMWrapper<Element>) {
  await wrapper!.findAll('button').find(button => button.text() === '登记领料申请')!.trigger('click')
  await body.get('[aria-label="来源单号"]').setValue('REQ-0001')
  await body.get('[aria-label="物料产品编码"]').setValue('00012')
  await body.get('[aria-label="名称规格"]').setValue('白色布')
  await body.get('[aria-label="原单位"]').setValue('码')
  await body.get('[aria-label="往来单位"]').setValue('车间一')
  await body.get('[aria-label="用途工序"]').setValue('生产领料')
  await body.get('[aria-label="本次数量"]').setValue('0.3')
}
describe('warehouse actual operations', () => {
  it.each<WarehouseDomain>(['fabric', 'semi'])('issues %s stock directly without a warehouse quality step', async warehouse => {
    api.post.mockResolvedValue({ id: 'quality' })
    const data = { ...empty(), permissions: { read: true, operate: true, quality: true, correct: true } }
    data.stock = [{ id: 'B1', item_code: '00012', item_name: '白布', unit: '码', process_state: '', material_category: 'FABRIC',
      location: 'A01', lot: '01', roll_no: '', quantity: '1', available_quantity: '1', quality_status: 'PENDING_INSPECTION',
      source_no: '', source_document: 'RECEIPT-ID', received_on: '2026-01-01', counterparty: '供应商', production_no: '' }]
    const body = await open('inventory', 'stock', data, warehouse)
    expect(wrapper!.text()).toContain('白布')
    expect(wrapper!.text()).not.toContain('RECEIPT-ID')
    expect(wrapper!.findAll('button').some(button => button.text().includes('质检'))).toBe(false)
    await wrapper!.findAll('button').find(button => button.text() === '出库')!.trigger('click')
    expect(body.get<HTMLSelectElement>('[aria-label="实际批次"]').element.value).toBe('B1')
    expect(body.get('[aria-label="关联原单"]').attributes('required')).toBeUndefined()
    expect(body.get('[aria-label="业务依据"]').attributes('required')).toBeUndefined()
    expect(body.get('[aria-label="来源单号"]').attributes('required')).toBeUndefined()
    const form = body.get('form').element as HTMLFormElement
    expect(form.checkValidity()).toBe(false)
    await body.get('[aria-label="领用方"]').setValue('车间一')
    await body.get('[aria-label="本次数量"]').setValue('0.3')
    expect(form.checkValidity()).toBe(true)
    await body.get('form').trigger('submit'); await flushPromises()
    expect(api.post.mock.calls[0]).toMatchObject([warehouse, { kind: 'ISSUE', batch_id: 'B1', original_id: '', counterparty: '车间一', quantity: '0.3', source_no: '', reason: '', allocations: [] }])
  })
  it.each([
    ['transfers', '登记调仓', 'fabric'], ['returns', '登记退料', 'fabric'],
    ['processing', '登记加工回货', 'semi'], ['packaging', '代录包装接收回执', 'semi'],
  ] as const)('makes %s notes optional while retaining linked identities', async (view, action, warehouse) => {
    const body = await open('inventory', view, empty(), warehouse)
    await wrapper!.findAll('button').find(button => button.text() === action)!.trigger('click')
    expect(body.get('[aria-label="业务依据"]').attributes('required')).toBeUndefined()
    expect(body.get('[aria-label="来源单号"]').attributes('required')).toBeUndefined()
    expect(body.get('[aria-label="本次数量"]').attributes('required')).toBeDefined()
    expect(body.get(view === 'transfers' ? '[aria-label="实际批次"]' : '[aria-label="关联原单"]').attributes('required')).toBeDefined()
  })
  it('allows omitted request purpose but retains source identity', async () => {
    const body = await open(); await fillRequest(body)
    await body.get('[aria-label="用途工序"]').setValue('')
    expect(body.get('[aria-label="用途工序"]').attributes('required')).toBeUndefined()
    expect((body.get('form').element as HTMLFormElement).checkValidity()).toBe(true)
    await body.get('[aria-label="来源单号"]').setValue('')
    expect((body.get('form').element as HTMLFormElement).checkValidity()).toBe(false)
  })
  it('shows received material totals and opens a transfer with the exact selected batch', async () => {
    api.post.mockResolvedValue({ id: 'transfer' })
    const batch: WarehouseOperationsWorkspace['stock'][number] = { id: 'B1', item_code: '001', item_name: '紫色布', unit: '码', process_state: '', material_category: 'FABRIC', location: 'A01', lot: '01', roll_no: 'R1', quantity: '1', available_quantity: '1', quality_status: 'PENDING_INSPECTION', source_no: 'DN1', source_document: 'DOC1', received_on: '2026-01-01', counterparty: '供应商', production_no: '' }
    const body = await open('inventory', 'stock', { ...empty(), stock: [batch, { ...batch, id: 'B2', location: 'A02', quantity: '11', available_quantity: '11' }] })
    expect(wrapper!.get('.stock-total-quantity').text()).toContain('12码')
    expect(wrapper!.findAll('tbody tr')).toHaveLength(2)
    await wrapper!.get('[aria-label="库存仓位"]').setValue('A02')
    expect(wrapper!.findAll('tbody tr')).toHaveLength(1)
    await wrapper!.findAll('tbody button').find(button => button.text() === '调仓')!.trigger('click')
    expect(body.get<HTMLSelectElement>('[aria-label="实际批次"]').element.value).toBe('B2')
    await body.get('[aria-label="目标仓位"]').setValue('一仓／B03')
    await body.get('[aria-label="本次数量"]').setValue('2')
    expect((body.get('form').element as HTMLFormElement).checkValidity()).toBe(true)
    await body.get('form').trigger('submit'); await flushPromises()
    expect(api.post.mock.calls[0]![1]).toMatchObject({ kind: 'TRANSFER', batch_id: 'B2', location_id: 'B03', location: '一仓／B03', quantity: '2', reason: '' })
  })
  it('retains a required explanation for stock reversal', async () => {
    const body = await open('exceptions', 'differences', { ...empty(), permissions: { read: true, operate: true, quality: true, correct: true } })
    await wrapper!.findAll('button').find(button => button.text() === '冲销录错单据')!.trigger('click')
    expect(body.get('[aria-label="业务依据"]').attributes('required')).toBeDefined()
    expect(body.text()).toContain('冲销原因（必填）')
    expect(body.get('[aria-label="关联原单"]').attributes('required')).toBeDefined()
  })
  it('keeps original identifiers and submits an actual source-bound request', async () => {
    api.post.mockResolvedValue({ id: 'new' })
    const body = await open()
    await fillRequest(body)
    await body.get('form[role="dialog"]').trigger('submit'); await flushPromises()
    const input = api.post.mock.calls[0]![1] as WarehouseDocumentInput
    expect(input).toMatchObject({ factory_id: 'huakang-c', item_code: '00012', kind: 'REQUEST', quantity: '0.3', expected_revision: 3, source_no: 'REQ-0001', allocations: [] })
    expect(body.find('[role="dialog"]').exists()).toBe(false)
    expect(wrapper!.text()).toContain('单据已保存')
  })
  it('freezes unknown outcomes and retries the exact same id and body', async () => {
    api.post.mockRejectedValueOnce(new Error('network disconnected')).mockResolvedValueOnce({ id: 'new' })
    const body = await open(); await fillRequest(body)
    await body.get('form[role="dialog"]').trigger('submit'); await flushPromises()
    const first = JSON.parse(JSON.stringify(api.post.mock.calls[0]![1]))
    expect(body.get('fieldset').attributes('disabled')).toBeDefined()
    expect(body.text()).toContain('用原内容重试')
    await body.get('form[role="dialog"]').trigger('submit'); await flushPromises()
    expect(api.post.mock.calls[1]![1]).toEqual(first)
  })
  it('does not expose quality confirmation as an ordinary receiving action', async () => {
    await open('inventory', 'stock')
    expect(wrapper!.findAll('button').some(button => button.text().includes('质检'))).toBe(false)
    expect(api.post).not.toHaveBeenCalled()
  })
  it('keeps legacy receipt movements while excluding requests and quality from the stock ledger', async () => {
    const input = { quantity: '2.2', unit: '码', source_no: 'OLD-DN', allocations: [] } as unknown as WarehouseDocumentInput
    const legacy = { id: 'OLD-BATCH', kind: 'RECEIPT', sequence: 0, business_date: '2026-09-01', actor_name: '仓管', data: input, occurred_at: '', read_only: true } as WarehouseDocument
    await open('inventory', 'movements', { ...empty(), original_receipts: [legacy], documents: [{ ...legacy, id: 'REQ', kind: 'REQUEST', data: { ...input, source_no: 'REQUEST-HIDDEN' } }] })
    expect(wrapper!.text()).toContain('OLD-DN')
    expect(wrapper!.text()).not.toContain('REQUEST-HIDDEN')
  })
  it('does not turn a failed read into an empty-stock success', async () => {
    const body = await open(); api.workspace.mockRejectedValueOnce(new Error('connection failed'))
    await wrapper!.findAll('button').find(button => button.text() === '刷新')!.trigger('click'); await flushPromises()
    expect(body.find('[role="alert"]').exists()).toBe(true)
    expect(wrapper!.text()).not.toContain('暂无业务记录')
  })
  it('keeps decimal progress exact', () => {
    expect(remaining('0.3', '0.1')).toBe('0.2')
    expect(sumQuantities(['0.1', '0.2'])).toBe('0.3')
    expect(sumQuantities(['1', '11'])).toBe('12')
    expect(sumQuantities(['9007199254740992', '1.000001'])).toBe('9007199254740993.000001')
    expect(documentProgress({ kind: 'REQUEST', data: { quantity: '0.3', unit: '码' }, issued_quantity: '0.1' } as WarehouseDocument)).toContain('待发 0.2 码')
  })
  it('keeps legacy quantities visible but requires explicit location reconciliation', async () => {
    const data = empty(); data.permissions.correct = true
    data.stock = [{ id: 'OLD', item_code: '001', item_name: '旧布料', unit: '码', process_state: '', material_category: 'FABRIC',
      location: '随手填的仓位', location_id: '', location_verified: false, lot: '01', roll_no: '', quantity: '12', available_quantity: '0', quality_status: 'HOLD',
      source_no: 'DN1', source_document: 'ORIGINAL', received_on: '2026-01-01', counterparty: '供应商', production_no: '' }]
    const body = await open('inventory', 'stock', data)
    expect(wrapper!.get('.stock-total-quantity').text()).toContain('12码')
    expect(wrapper!.text()).toContain('仓位待核实')
    expect(wrapper!.findAll('tbody button').some(button => button.text() === '出库')).toBe(false)
    await wrapper!.findAll('button').find(button => button.text() === '核实仓位')!.trigger('click')
    expect(body.get<HTMLSelectElement>('[aria-label="实际批次"]').element.value).toBe('OLD')
    expect(body.find('[aria-label="本次数量"]').exists()).toBe(false)
    expect(body.get('[aria-label="业务依据"]').attributes('required')).toBeDefined()
    await body.get('[aria-label="目标仓位"]').setValue('一仓／A01')
    await body.get('[aria-label="业务依据"]').setValue('现场核实')
    await body.get('input[type="checkbox"][required]').setValue(true)
    api.post.mockResolvedValue({ id: 'BIND' })
    await body.get('form').trigger('submit'); await flushPromises()
    expect(api.post.mock.calls[0]![1]).toMatchObject({ kind: 'LOCATION_BIND', batch_id: 'OLD', location_id: 'A01', quantity: '', confirmed: true, reason: '现场核实' })
  })
  it('blocks receiving when no formal location exists', async () => {
    const data = empty(); data.locations = []
    const body = await open('receipts', 'receipts', data, 'semi')
    await wrapper!.findAll('button').find(button => button.text() === '登记实收')!.trigger('click')
    expect(body.text()).toContain('没有可用仓位')
    expect(body.findAll('button').find(button => button.text() === '确认保存')!.attributes('disabled')).toBeDefined()
    await body.get('form').trigger('submit')
    expect(api.post).not.toHaveBeenCalled()
  })
  it('validates each selected stock row and retries bulk issue with the exact frozen request', async () => {
    const batch = { id: 'B1', item_code: '001', item_name: '白布', unit: '码', process_state: '', material_category: 'FABRIC' as const,
      location: 'A01', lot: '1', roll_no: '', quantity: '10', available_quantity: '10', quality_status: 'QUALIFIED' as const,
      source_no: 'DN1', source_document: 'DOC1', received_on: '2026-01-01', counterparty: '供应商', production_no: '' }
    const body = await open('inventory', 'stock', { ...empty(), stock: [batch, { ...batch, id: 'B2', quantity: '2' }] })
    await wrapper!.get('[aria-label="选择库存 B1"]').setValue(true)
    await wrapper!.get('[aria-label="选择库存 B2"]').setValue(true)
    await wrapper!.findAll('button').find(button => button.text() === '登记所选库存出库')!.trigger('click')
    await body.get('[aria-label="批量领用方"]').setValue('车间一')
    await body.get('[aria-label="本次出库数量 B1"]').setValue('3')
    await body.get('[aria-label="本次出库数量 B2"]').setValue('3')
    await body.get('form').trigger('submit'); expect(api.bulkIssue).not.toHaveBeenCalled()
    await body.get('[aria-label="本次出库数量 B2"]').setValue('1')
    api.bulkIssue.mockRejectedValueOnce(new Error('lost response')).mockResolvedValueOnce([])
    await body.get('form').trigger('submit'); await flushPromises()
    const first = JSON.parse(JSON.stringify(api.bulkIssue.mock.calls[0]![1]))
    expect(body.get('fieldset').attributes('disabled')).toBeDefined()
    await body.get('form').trigger('submit'); await flushPromises()
    expect(api.bulkIssue.mock.calls[1]![1]).toEqual(first)
    expect(first.items).toEqual([{ batch_id: 'B1', quantity: '3', counterparty: '' }, { batch_id: 'B2', quantity: '1', counterparty: '' }])
    expect(body.find('[aria-label="批量出库"]').exists()).toBe(false)
  })
  it('refreshes a conflicting bulk issue without discarding entered quantities', async () => {
    const batch = { id: 'B1', item_code: '001', item_name: '白布', unit: '码', process_state: '', material_category: 'FABRIC' as const,
      location: 'A01', location_id: 'A01', location_verified: true, lot: '1', roll_no: '', quantity: '10', available_quantity: '10', quality_status: 'QUALIFIED' as const,
      source_no: 'DN1', source_document: 'DOC1', received_on: '2026-01-01', counterparty: '供应商', production_no: '' }
    const body = await open('inventory', 'stock', { ...empty(), stock: [batch] })
    await wrapper!.get('[aria-label="选择库存 B1"]').setValue(true)
    await wrapper!.findAll('button').find(button => button.text() === '登记所选库存出库')!.trigger('click')
    await body.get('[aria-label="批量领用方"]').setValue('车间一')
    await body.get('[aria-label="本次出库数量 B1"]').setValue('3')
    api.bulkIssue.mockRejectedValueOnce({ response: { status: 409 } }).mockResolvedValueOnce([])
    api.workspace.mockResolvedValue({ ...empty(), revision: 8, stock: [{ ...batch, quantity: '2', available_quantity: '2' }] })
    await body.get('form').trigger('submit'); await flushPromises()
    expect(body.get<HTMLInputElement>('[aria-label="本次出库数量 B1"]').element.value).toBe('3')
    expect(body.text()).toContain('已保留填写内容')
    await body.get('form').trigger('submit'); expect(api.bulkIssue).toHaveBeenCalledTimes(1)
    await body.get('[aria-label="本次出库数量 B1"]').setValue('2')
    await body.get('form').trigger('submit'); await flushPromises()
    expect(api.bulkIssue.mock.calls[1]![1]).toMatchObject({ expected_revision: 8, items: [{ batch_id: 'B1', quantity: '2' }] })
  })
})
