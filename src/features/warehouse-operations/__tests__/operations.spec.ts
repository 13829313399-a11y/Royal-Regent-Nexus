import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { mount, flushPromises, DOMWrapper, type VueWrapper } from '@vue/test-utils'
import { createMemoryHistory, createRouter } from 'vue-router'
import { parseDate } from '@internationalized/date'
import DateRangeFilter from '@/components/DateRangeFilter.vue'
import Workspace from '../WarehouseOperationsWorkspace.vue'
import { documentProgress, remaining, sumQuantities } from '../operations'
import type { WarehouseDocument, WarehouseDocumentInput, WarehouseDomain, WarehouseOperationsWorkspace } from '@/api/warehouseOperations'

const api = vi.hoisted(() => ({ workspace: vi.fn(), post: vi.fn(), recover: vi.fn(), bulkIssue: vi.fn() }))
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
  it('shows frozen cutting identities and closes only the unissued remainder', async () => {
    const data=empty()
    const input={quantity:'6.5',unit:'米',source_no:'CUT-1',item_code:'FAB1',item_name:'蓝布',counterparty:'本厂',allocations:[],
      cutting_request:{line_id:'line',order_no:'O1',task_name:'裁剪任务',resource_name:'本厂',bom_version:2,plan_version:8,mapping_basis:'规格颜色原单位一致',
        cutting_material:{code:'M1',name:'蓝布',specification:'规格A',color:'蓝'},warehouse_material:{code:'FAB1',name:'蓝布',revision:3,spec:'规格A',color:'蓝',unit:'米',category:'FABRIC'}}} as WarehouseDocumentInput
    data.documents=[{id:'REQ',kind:'REQUEST',sequence:1,business_date:'2026-10-01',actor_name:'文员',occurred_at:'',data:input,issued_quantity:'2'}]
    const body=await open('inventory','pending-issues',data)
    expect(wrapper!.text()).toContain('裁床订单 O1')
    expect(wrapper!.text()).toContain('规格颜色原单位一致')
    await wrapper!.findAll('button').find(b=>b.text()==='关闭未发余量')!.trigger('click')
    expect(body.find('[aria-label="本次数量"]').exists()).toBe(false)
    expect(body.get('[aria-label="业务依据"]').attributes('required')).toBeDefined()
    await body.get('[aria-label="业务依据"]').setValue('计划改版，关闭尚未发出的余量')
    api.post.mockResolvedValue({id:'CLOSE'})
    await body.get('form').trigger('submit');await flushPromises()
    expect(api.post).toHaveBeenCalledWith('fabric',expect.objectContaining({kind:'REQUEST_CLOSE',original_id:'REQ',quantity:''}))
    data.documents[0]!.closed=true
    await wrapper!.findAll('button').find(b=>b.text()==='刷新')!.trigger('click');await flushPromises()
    expect(wrapper!.findAll('button').some(b=>b.text()==='办理出库')).toBe(false)
  })
  it.each([true, false])('opens an exact receipt link read-only and gates correction permission (%s)', async correct => {
    const receipt = { id: 'OP-1', kind: 'RECEIPT', sequence: 1, business_date: '2026-10-10', actor_name: '仓管', occurred_at: '',
      data: { quantity: '10', unit: '码', item_name: '白布', source_no: 'DN-1', allocations: [] } } as WarehouseDocument
    const data = { ...empty(), documents: [receipt] }
    data.permissions.correct = correct
    const body = await open('inventory', 'movements', data)
    await wrapper!.vm.$router.push('/?record=OP-1'); await flushPromises()
    expect(body.get('[role="dialog"]').text()).toContain('DN-1')
    const action = body.findAll('button').find(button => button.text() === '冲销本笔入库')
    expect(!!action).toBe(correct)
    expect(api.post).not.toHaveBeenCalled()
    if (action) {
      await action.trigger('click'); await flushPromises()
      expect(body.get('[role="dialog"]').text()).toContain('冲销')
      expect(api.post).not.toHaveBeenCalled()
    }
  })
  it('shows only completed corrections in fabric exceptions and combines original business, actor, date and ordering filters', async () => {
    const correction = { id: 'C1', kind: 'CORRECTION', sequence: 3, business_date: '2026-10-10', actor_name: '仓管甲', occurred_at: '',
      data: { quantity: '1', unit: '码', item_name: '白色布', source_no: 'COR-1', reversed_kind: 'ISSUE', original_id: 'I1', reason: '数量录错', allocations: [] },
    } as WarehouseDocument
    const documents: WarehouseDocument[] = [correction, { ...correction, id: 'C2', sequence: 4, business_date: '2026-10-11', actor_name: '仓管乙', data: { ...correction.data, source_no: 'COR-2', reversed_kind: 'TRANSFER' } },
      { ...correction, id: 'C3', sequence: 5, business_date: '2026-10-12', data: { ...correction.data, source_no: 'COR-3' } },
      { ...correction, id: 'R1', kind: 'RETURN', data: { ...correction.data, source_no: '正常退料' } }]
    await open('exceptions', 'differences', { ...empty(), documents })
    expect(wrapper!.findAll('tbody tr')).toHaveLength(3)
    expect(wrapper!.get('tbody').text()).not.toContain('正常退料')
    expect(wrapper!.get('tbody').text()).toContain('数量录错')
    await wrapper!.get('[aria-label="更正原业务"]').setValue('ISSUE')
    await wrapper!.get('[aria-label="更正经办人"]').setValue('仓管甲')
    await wrapper!.get('[aria-label="收发记录排序"]').setValue('DATE_ASC')
    expect(wrapper!.get('tbody tr').text()).toContain('COR-1')
    wrapper!.getComponent(DateRangeFilter).vm.$emit('update:modelValue', { start: parseDate('2026-10-12'), end: parseDate('2026-10-12') }); await flushPromises()
    expect(wrapper!.findAll('tbody tr')).toHaveLength(1)
    expect(wrapper!.get('tbody').text()).toContain('COR-3')
    expect(api.post).not.toHaveBeenCalled()
  })
  it('filters and sorts actual movement records before pagination, retaining reversed originals for review', async () => {
    const documents = Array.from({ length: 52 }, (_, index) => ({ id: `IS-${index}`, kind: 'ISSUE', sequence: index,
      business_date: '2026-10-10', actor_name: '仓管', occurred_at: '', reversed: index === 0,
      data: { quantity: '1', unit: '码', item_name: `材料-${index}`, source_no: `IS-${index}`, allocations: [] },
    } as WarehouseDocument))
    const receipt = { ...documents[0]!, id: 'ORIGINAL', kind: 'RECEIPT', read_only: true, reversed: false, business_date: '2026-10-01', data: { ...documents[0]!.data, source_no: '旧实收来源' } } as WarehouseDocument
    await open('inventory', 'movements', { ...empty(), documents, original_receipts: [receipt] })
    expect(wrapper!.findAll('tbody tr')).toHaveLength(50)
    await wrapper!.get('[aria-label="收发单据状态"]').setValue('REVERSED')
    expect(wrapper!.findAll('tbody tr')).toHaveLength(1)
    expect(wrapper!.get('tbody').text()).toContain('IS-0')
    await wrapper!.get('[aria-label="收发单据状态"]').setValue('ACTIVE')
    await wrapper!.get('[aria-label="收发业务类型"]').setValue('RECEIPT'); await flushPromises()
    expect(wrapper!.findAll('tbody tr')).toHaveLength(1)
    expect(wrapper!.get('tbody').text()).toContain('旧实收来源')
    await wrapper!.get('[aria-label="收发业务类型"]').setValue(''); await flushPromises()
    await wrapper!.get('[aria-label="收发记录排序"]').setValue('DATE_ASC')
    expect(wrapper!.get('tbody tr').text()).toContain('旧实收来源')
    wrapper!.getComponent(DateRangeFilter).vm.$emit('update:modelValue', { start: parseDate('2026-10-10'), end: parseDate('2026-10-13') }); await flushPromises()
    expect(wrapper!.get('tbody tr').text()).toContain('IS-1')
    await wrapper!.findAll('button').find(button => button.text() === '重置筛选')!.trigger('click')
    expect(wrapper!.get('[aria-label="收发记录日期范围"]').text()).toContain('选择日期范围')
    expect(api.post).not.toHaveBeenCalled()
  })
  it('distinguishes unfinished, fully issued and reversed requests without changing their progress', async () => {
    const request = { id: 'PARTIAL', kind: 'REQUEST', sequence: 1, business_date: '2026-10-10', actor_name: '仓管', occurred_at: '', issued_quantity: '0.1',
      data: { quantity: '0.3', unit: '码', source_no: '部分领料', allocations: [] } } as WarehouseDocument
    await open('inventory', 'pending-issues', { ...empty(), documents: [request, { ...request, id: 'DONE', issued_quantity: '0.3', data: { ...request.data, source_no: '全部领料' } }, { ...request, id: 'VOID', reversed: true, data: { ...request.data, source_no: '作废申请' } }] })
    for (const [state, label] of [['PENDING', '部分领料'], ['COMPLETE', '全部领料'], ['REVERSED', '作废申请']]) {
      await wrapper!.get('[aria-label="收发单据状态"]').setValue(state)
      expect(wrapper!.findAll('tbody tr')).toHaveLength(1)
      expect(wrapper!.get('tbody').text()).toContain(label)
    }
    expect(api.post).not.toHaveBeenCalled()
  })
  it('opens an issue row reversal with the locked original, reason and whole confirmation', async () => {
    const input = { quantity: '2.2', unit: '码', item_name: '紫色布', counterparty: '车间二', source_no: 'ISS-1', allocations: [] } as unknown as WarehouseDocumentInput
    const row = { id: 'ISS-1', kind: 'ISSUE', sequence: 3, business_date: '2026-09-01', actor_name: '仓管', data: input, occurred_at: '' } as WarehouseDocument
    const body = await open('inventory', 'issues', { ...empty(), documents: [row], permissions: { ...empty().permissions, correct: true } })
    await wrapper!.findAll('tbody button').find(button => button.text() === '冲销')!.trigger('click')
    expect(body.get('[aria-label="关联原单"]').attributes('disabled')).toBeDefined()
    expect(body.get<HTMLSelectElement>('[aria-label="关联原单"]').element.value).toBe(row.id)
    expect(body.text()).toContain('2.2 码')
    await body.get('[aria-label="业务依据"]').setValue('数量录错')
    await body.get('form[role="dialog"]').trigger('submit'); await flushPromises()
    expect(api.post).not.toHaveBeenCalled()
    await body.get('[aria-label="确认整单冲销"]').setValue(true)
    api.post.mockResolvedValueOnce({ id: 'REV' })
    await body.get('form[role="dialog"]').trigger('submit'); await flushPromises()
    expect(api.post.mock.calls[0]![1]).toMatchObject({ kind: 'CORRECTION', original_id: row.id, confirmed: true, reason: '数量录错' })
    expect(wrapper!.text()).toContain('库存与关联进度已恢复')
  })
  it('explains overview intake and request actions without posting stock', async () => {
    await open('overview', 'pending')
    expect(wrapper!.text()).toContain('登记实收')
    expect(wrapper!.text()).toContain('只建立申请')
    expect(api.post).not.toHaveBeenCalled()
  })
  it.each(['issues', 'transfers', 'returns'])('keeps the fabric %s toolbar for querying existing records', async view => {
    await open('inventory', view)
    expect(wrapper!.findAll('.warehouse-operation-toolbar button').map(button => button.text())).toEqual(['选择日期范围', '重置筛选'])
    expect(api.post).not.toHaveBeenCalled()
  })
  it.each(['issues', 'movements'])('returns stock from an eligible original issue in %s with locked identity and actual returned quantity', async view => {
    const issue = { id: 'ISS-1', kind: 'ISSUE', sequence: 3, business_date: '2026-09-01', actor_name: '仓管', occurred_at: '', returned_quantity: '0.2',
      data: { material_category: 'FABRIC', quantity: '2.2', unit: '码', item_code: '00012', item_name: '紫色布', counterparty: '车间二', source_no: 'OUT-1', allocations: [] },
    } as WarehouseDocument
    const documents = [issue, { ...issue, id: 'DONE', returned_quantity: '2.2' }, { ...issue, id: 'VOID', reversed: true }, { ...issue, id: 'READONLY', read_only: true }]
    const body = await open('inventory', view, { ...empty(), documents })
    const returns = wrapper!.findAll('tbody button').filter(button => button.text() === '退料')
    expect(returns).toHaveLength(1)
    expect(wrapper!.get('tbody tr').text()).toContain('已退 0.2 · 可退 2.0 码')
    await returns[0]!.trigger('click')
    expect(api.post).not.toHaveBeenCalled()
    const original = body.get<HTMLSelectElement>('[aria-label="关联原单"]')
    expect(original.element.value).toBe(issue.id)
    expect(original.attributes('disabled')).toBeDefined()
    expect(body.get('[role="dialog"]').text()).toContain('领用方：车间二')
    expect(body.get('[role="dialog"]').text()).toContain('可退 2.0 码')
    expect(body.get<HTMLInputElement>('[aria-label="本次数量"]').element.value).toBe('')
    expect(body.find('[aria-label="物料产品编码"]').exists()).toBe(false)
    expect(body.get('[aria-label="来源单号"]').attributes('required')).toBeUndefined()
    expect(body.get('[aria-label="业务依据"]').attributes('required')).toBeUndefined()
    await body.get('[aria-label="本次数量"]').setValue('0.3')
    await body.get('[aria-label="目标仓位"]').setValue('一仓／B03')
    expect((body.get('form').element as HTMLFormElement).checkValidity()).toBe(true)
    api.post.mockResolvedValueOnce({ id: 'RETURN-1' })
    await body.get('form').trigger('submit'); await flushPromises()
    expect(api.post.mock.calls[0]).toMatchObject(['fabric', { kind: 'RETURN', original_id: issue.id, counterparty: '车间二', location_id: 'B03', quantity: '0.3', source_no: '', reason: '', allocations: [] }])
    expect(body.find('[role="dialog"]').exists()).toBe(false)
    expect(wrapper!.text()).toContain('退料已登记，可在收发记录筛选“车间退料”查看')
  })
  it.each(['issues', 'movements'])('requires existing operate permission to open an issue return in %s', async view => {
    const issue = { id: 'ISS-1', kind: 'ISSUE', sequence: 3, business_date: '2026-09-01', actor_name: '仓管', occurred_at: '',
      data: { quantity: '1', unit: '码', item_name: '白布', allocations: [] },
    } as WarehouseDocument
    const body = await open('inventory', view, { ...empty(), documents: [issue], permissions: { ...empty().permissions, operate: false } })
    const action = wrapper!.findAll('tbody button').find(button => button.text() === '退料')!
    expect(action.attributes('disabled')).toBeDefined()
    await action.trigger('click')
    expect(body.find('[role="dialog"]').exists()).toBe(false)
    expect(api.post).not.toHaveBeenCalled()
  })
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
    ['transfers', '登记调仓', 'semi'], ['returns', '登记退料', 'semi'],
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
    const body = await open('overview', 'pending'); await fillRequest(body)
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
    const body = await open('exceptions', 'differences', { ...empty(), permissions: { read: true, operate: true, quality: true, correct: true } }, 'semi')
    await wrapper!.findAll('button').find(button => button.text() === '冲销录错单据')!.trigger('click')
    expect(body.get('[aria-label="业务依据"]').attributes('required')).toBeDefined()
    expect(body.text()).toContain('冲销原因（必填）')
    expect(body.get('[aria-label="关联原单"]').attributes('required')).toBeDefined()
  })
  it('keeps original identifiers and submits an actual source-bound request', async () => {
    api.post.mockResolvedValue({ id: 'new' })
    const body = await open('overview', 'pending')
    await fillRequest(body)
    await body.get('form[role="dialog"]').trigger('submit'); await flushPromises()
    const input = api.post.mock.calls[0]![1] as WarehouseDocumentInput
    expect(input).toMatchObject({ factory_id: 'huakang-c', item_code: '00012', kind: 'REQUEST', quantity: '0.3', expected_revision: 3, source_no: 'REQ-0001', allocations: [] })
    expect(body.find('[role="dialog"]').exists()).toBe(false)
    expect(wrapper!.text()).toContain('单据已保存')
  })
  it('freezes unknown outcomes and retries the exact same id and body', async () => {
    api.post.mockRejectedValueOnce(new Error('network disconnected')).mockResolvedValueOnce({ id: 'new' })
    const body = await open('overview', 'pending'); await fillRequest(body)
    await body.get('form[role="dialog"]').trigger('submit'); await flushPromises()
    const first = JSON.parse(JSON.stringify(api.post.mock.calls[0]![1]))
    expect(body.get('fieldset').attributes('disabled')).toBeDefined()
    expect(body.text()).toContain('用原内容重试')
    await body.get('form[role="dialog"]').trigger('submit'); await flushPromises()
    expect(api.post.mock.calls[1]![1]).toEqual(first)
  })
  it('retries frozen receiving content even after the current location category changes', async () => {
    api.post.mockRejectedValueOnce(new Error('network disconnected')).mockResolvedValueOnce({ id: 'receipt' })
    const state = empty()
    const body = await open('overview', 'pending', state)
    await wrapper!.findAll('button').find(button => button.text() === '登记实收')!.trigger('click')
    await body.get('[aria-label="来源单号"]').setValue('DN-ZONE')
    await body.get('[aria-label="物料产品编码"]').setValue('M1')
    await body.get('[aria-label="名称规格"]').setValue('布料')
    await body.get('[aria-label="原单位"]').setValue('码')
    await body.get('[aria-label="往来单位"]').setValue('供应商')
    await body.get('[aria-label="本次数量"]').setValue('1')
    await body.get('[aria-label="目标仓位"]').setValue('一仓／A01')
    await body.get('[aria-label="缸号批号"]').setValue('LOT')
    await body.get('form[role="dialog"]').trigger('submit'); await flushPromises()
    const first = JSON.parse(JSON.stringify(api.post.mock.calls[0]![1]))
    state.locations![0]!.category = 'THREAD'
    await wrapper!.findAll('button').find(button => button.text() === '刷新')!.trigger('click'); await flushPromises()
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
  it('describes return reversals as removing returned stock instead of restoring issued stock', () => {
    const correction = (kind: string) => documentProgress({kind:'CORRECTION',data:{reversed_kind:kind,quantity:'1.25',unit:'米'}} as WarehouseDocument)
    expect(correction('RETURN')).toBe('冲销退料入库，扣回库存 1.25 米')
    expect(correction('RECEIPT')).toContain('入库，扣回库存')
    expect(correction('ISSUE')).toContain('发出，恢复库存')
    expect(correction('TRANSFER')).toContain('移库，退回原仓位')
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


describe('warehouse uncertain outcome recovery',()=>{
  it.each([401,403,409])('retains the original request after uncertain retry %s',async status=>{
    api.post.mockRejectedValueOnce(new Error('timeout')).mockRejectedValueOnce({isAxiosError:true,response:{status}}).mockResolvedValueOnce({id:'ok'})
    const body=await open('overview','');await fillRequest(body)
    await body.get('form').trigger('submit');await flushPromises()
    const original=structuredClone(api.post.mock.calls[0]![1])
    await body.get('form').trigger('submit');await flushPromises()
    expect(body.get('fieldset').attributes('disabled')).toBeDefined()
    await body.get('form').trigger('submit');await flushPromises()
    expect(api.post.mock.calls[2]![1]).toEqual(original)
  })
  it.each(['committed','abandoned'])('resolves uncertain %s results through the server',async state=>{
    api.post.mockRejectedValueOnce(new Error('timeout'));api.recover.mockResolvedValue({state})
    const body=await open('overview','');await fillRequest(body)
    await body.get('form').trigger('submit');await flushPromises()
    const original=structuredClone(api.post.mock.calls[0]![1])
    await body.findAll('button').find(b=>b.text()==='核对保存结果／停止未执行操作')!.trigger('click');await flushPromises()
    expect(api.recover).toHaveBeenCalledWith('fabric',original)
    if(state==='committed')expect(body.find('form').exists()).toBe(false)
    else{expect(body.get('[aria-label="本次数量"]').element).toHaveProperty('value','0.3');expect(body.get('fieldset').attributes('disabled')).toBeUndefined()}
  })
})
