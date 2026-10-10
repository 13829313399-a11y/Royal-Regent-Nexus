import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { mount, flushPromises, type VueWrapper } from '@vue/test-utils'
import { createRouter, createMemoryHistory, RouterView, type Router } from 'vue-router'
import { cuttingOperationsRoutes } from '../routes'
import { cuttingApi, type MasterRecord } from '../api'
import { ordersApi, type CuttingOrder } from '../ordersApi'

vi.mock('@/components/layout/AccountMenu.vue', () => ({ default: { template: '<span />' } }))
vi.mock('../api', async original => ({ ...await original<typeof import('../api')>(), cuttingApi: { access: vi.fn(), list: vi.fn(), versions: vi.fn() } }))
vi.mock('../ordersApi', () => ({ ordersApi: { list: vi.fn(), command: vi.fn(), history: vi.fn(), recover: vi.fn() } }))
const path = '/modules/production/cutting/planning?factory=huakang-c'
const row: CuttingOrder = { line_id: 'line-1', dispatch_id: 'dispatch-1', source_version: 1, needs_receipt: true, received_at: '', current: null,
  snapshot: { customer_name: '合成洋行', reference_no: 'ORDER-001', product_no: 'P001', quantity: '100', status: 'active' } }
const received: CuttingOrder = { ...row, needs_receipt: false, current: { version: 1, actor_id: 'receiver', created_at: '2026-10-09T00:00:00Z', reason: '接单',
  data: { order: row.snapshot, dispatch_id: row.dispatch_id, bom: null, requisition: null, batches: [], purchase_reconciliation_required: false } } }
const bom: MasterRecord = { id: 'bom-1', factory_id: 'huakang-c', kind: 'bom', code: 'B001', status: 'published', version: 2, actor_id: 'engineer', created_at: '2026-10-09T00:00:00Z', reason: '发布',
  data: { name: '配套BOM', item_no: 'P001', style: 'A', color: '蓝', source_reference: '工程', parts: [], requirements: [] } }
const page = <T,>(data: T[]) => ({ data, total: data.length, page: 1, page_size: 50 })
let wrapper: VueWrapper, router: Router
function button(text: string) {
  const b = wrapper.findAll('button').find(b => b.text() === text)
  if (!b) throw new Error(`Missing button: ${text}`)
  return b
}
async function open(record = row, permissions = ['read', 'order_receive', 'bom_write', 'requisition_submit', 'eta_write', 'requisition_reconcile']) {
  vi.mocked(cuttingApi.access).mockResolvedValue({ enabled: true, schema_ready: true, orders_schema_ready: true, permissions })
  vi.mocked(ordersApi.list).mockResolvedValue(page([record]))
  router = createRouter({ history: createMemoryHistory(), routes: [...cuttingOperationsRoutes, { path: '/modules/production', component: { template: '<div>生产部</div>' } }] })
  await router.push(path); await router.isReady()
  wrapper = mount(RouterView, { global: { plugins: [router] } }); await flushPromises()
  await button('查看').trigger('click')
}
async function receiptForm() {
  await button('签收订单版本').trigger('click')
  await wrapper.get('form.order-form textarea').setValue('核对来源订单签收')
}
beforeEach(() => { vi.resetAllMocks(); vi.spyOn(window, 'confirm').mockReturnValue(false) })
afterEach(() => { wrapper?.unmount(); vi.restoreAllMocks() })

describe('cutting order workflow and save protection', () => {
  it('sends planning state filters to the server', async () => {
    await open()
    await wrapper.get('[aria-label="排期状态筛选"]').setValue('review')
    await wrapper.get('form.order-toolbar').trigger('submit');await flushPromises()
    expect(ordersApi.list).toHaveBeenLastCalledWith(1,'','','review')
  })
  it('receives explicit source version and shows the new state', async () => {
    await open(); await receiptForm()
    vi.mocked(ordersApi.command).mockResolvedValue(received)
    await wrapper.get('form.order-form').trigger('submit'); await flushPromises()
    expect(ordersApi.command).toHaveBeenCalledWith('line-1', 'receive', expect.objectContaining({ factory_id: 'huakang-c', expected_version: 0, dispatch_id: 'dispatch-1' }))
    expect(wrapper.text()).toContain('待关联 BOM')
    expect(wrapper.text()).toContain('已保存，版本及操作依据已留存')
  })
  it('retains dirty reason when leaving or cancelling is declined', async () => {
    await open(); await receiptForm()
    await button('取消编辑').trigger('click')
    expect(wrapper.get('form.order-form textarea').element).toHaveProperty('value', '核对来源订单签收')
    await router.push('/modules/production?factory=huakang-c')
    expect(router.currentRoute.value.fullPath).toBe(path)
    const event = new Event('beforeunload', { cancelable: true }); window.dispatchEvent(event)
    expect(event.defaultPrevented).toBe(true)
    vi.mocked(window.confirm).mockReturnValue(true)
    await button('取消编辑').trigger('click')
    expect(wrapper.find('form.order-form').exists()).toBe(false)
  })
  it.each([401, 403, 409])('preserves an uncertain command through a subsequent %s and retries unchanged', async status => {
    await open(); await receiptForm()
    vi.mocked(ordersApi.command).mockRejectedValueOnce(new Error('timeout'))
      .mockRejectedValueOnce({ response: { status, data: { detail: '重试被拒绝' } } }).mockResolvedValueOnce(received)
    await wrapper.get('form.order-form').trigger('submit'); await flushPromises()
    const original = vi.mocked(ordersApi.command).mock.calls[0]
    await router.push('/modules/production?factory=huakang-c'); expect(router.currentRoute.value.fullPath).toBe(path)
    await button('重试原操作').trigger('click'); await flushPromises()
    expect(button('重试原操作').exists()).toBe(true)
    await button('重试原操作').trigger('click'); await flushPromises()
    expect(vi.mocked(ordersApi.command).mock.calls[2]).toEqual(original)
    expect(wrapper.text()).toContain('已保存')
  })
  it('can retry after a definitive first 401 without losing the hidden draft', async () => {
    await open(); await receiptForm()
    vi.mocked(ordersApi.command).mockRejectedValueOnce({ response: { status: 401 } }).mockResolvedValueOnce(received)
    await wrapper.get('form.order-form').trigger('submit'); await flushPromises()
    expect(wrapper.find('form.order-form').exists()).toBe(false)
    expect(wrapper.get('a[href="/login"]').attributes('target')).toBe('_blank')
    await button('重试原操作').trigger('click'); await flushPromises()
    expect(vi.mocked(ordersApi.command).mock.calls[1]).toEqual(vi.mocked(ordersApi.command).mock.calls[0])
    expect(wrapper.text()).toContain('ORDER-001')
  })
  it('does not expose actions to read-only users', async () => {
    await open(row, ['read'])
    expect(wrapper.findAll('button').some(b => b.text() === '签收订单版本')).toBe(false)
  })
  it.each([409, 422])('restores the draft after first 401 then a definitive %s on retry', async status => {
    await open(); await receiptForm()
    vi.mocked(ordersApi.command).mockRejectedValueOnce({ response: { status: 401 } }).mockRejectedValueOnce({ response: { status } })
    await wrapper.get('form.order-form').trigger('submit'); await flushPromises()
    await button('重试原操作').trigger('click'); await flushPromises()
    expect(wrapper.get('form.order-form textarea').element).toHaveProperty('value', '核对来源订单签收')
    expect(wrapper.find('a[href="/login"]').exists()).toBe(false)
    expect(wrapper.findAll('button').some(b => b.text() === '重试原操作')).toBe(false)
    vi.mocked(window.confirm).mockReturnValue(true)
    await button('取消编辑').trigger('click')
    expect(wrapper.find('form.order-form').exists()).toBe(false)
  })
  it('selects a published historical BOM and sends explicit engineering quantity basis', async () => {
    await open(received)
    vi.mocked(cuttingApi.list).mockResolvedValue(page([{ ...bom, version: 3, status: 'draft' }]))
    vi.mocked(cuttingApi.versions).mockResolvedValue(page([{ ...bom, version: 3, status: 'draft' }, bom]))
    await button('工程关联 BOM').trigger('click'); await button('查找 BOM').trigger('click'); await flushPromises()
    await button('查看发布版本').trigger('click'); await flushPromises()
    expect(wrapper.findAll('button').filter(b => b.text() === '选择此发布版')).toHaveLength(1)
    await button('选择此发布版').trigger('click')
    await wrapper.get('input[type="number"]').setValue('50')
    const areas = wrapper.findAll('form.order-form textarea')
    await areas[0]!.setValue('100件按每套2件核为50套'); await areas[2]!.setValue('工程确认')
    vi.mocked(ordersApi.command).mockResolvedValue(received)
    await wrapper.get('form.order-form').trigger('submit'); await flushPromises()
    expect(ordersApi.command).toHaveBeenCalledWith('line-1', 'bom', expect.objectContaining({ bom_version: 2, target_sets: 50, quantity_basis: '100件按每套2件核为50套' }))
  })
  it('ignores a stale BOM search after query changes', async () => {
    await open(received); await button('工程关联 BOM').trigger('click')
    let resolve!: (result: ReturnType<typeof page<MasterRecord>>) => void
    vi.mocked(cuttingApi.list).mockReturnValue(new Promise(res => { resolve = res }))
    await button('查找 BOM').trigger('click')
    await wrapper.get('form.order-form input').setValue('另一编码')
    resolve(page([bom])); await flushPromises()
    expect(wrapper.text()).not.toContain('配套BOM')
  })
  it('blocks downstream actions for stale or cancelled source versions', async () => {
    await open({ ...received, needs_receipt: true, snapshot: { ...row.snapshot, status: 'cancelled' } })
    expect(wrapper.text()).toContain('取消待签收')
    expect(wrapper.findAll('button').some(b => b.text() === '工程关联 BOM')).toBe(false)
  })
  it('recovers committed writes and refreshes the current source instead of replaying stale data', async () => {
    await open(); await receiptForm()
    vi.mocked(ordersApi.command).mockRejectedValueOnce(new Error('timeout'))
    vi.mocked(ordersApi.recover).mockResolvedValue({ state: 'committed', result: received })
    await wrapper.get('form.order-form').trigger('submit'); await flushPromises()
    const original = vi.mocked(ordersApi.command).mock.calls[0]!
    await button('核对保存结果／停止未执行操作').trigger('click'); await flushPromises()
    expect(ordersApi.recover).toHaveBeenCalledWith(...original)
    expect(wrapper.text()).toContain('已核实原操作成功')
    expect(ordersApi.list).toHaveBeenCalledTimes(2)
  })
  it('keeps the draft after server-fenced abandonment and uses a fresh operation id', async () => {
    await open(); await receiptForm()
    vi.mocked(ordersApi.command).mockRejectedValueOnce(new Error('timeout')).mockResolvedValueOnce(received)
    vi.mocked(ordersApi.recover).mockResolvedValue({ state: 'abandoned' })
    await wrapper.get('form.order-form').trigger('submit'); await flushPromises()
    await button('核对保存结果／停止未执行操作').trigger('click'); await flushPromises()
    expect(wrapper.get('form.order-form textarea').element).toHaveProperty('value', '核对来源订单签收')
    await wrapper.get('form.order-form').trigger('submit'); await flushPromises()
    expect(vi.mocked(ordersApi.command).mock.calls[0]![2].operation_id).not.toBe(vi.mocked(ordersApi.command).mock.calls[1]![2].operation_id)
  })
  it('does not clear the pending command when recovery itself is uncertain', async () => {
    await open(); await receiptForm()
    vi.mocked(ordersApi.command).mockRejectedValue(new Error('timeout'))
    vi.mocked(ordersApi.recover).mockRejectedValue(new Error('timeout'))
    await wrapper.get('form.order-form').trigger('submit'); await flushPromises()
    await button('核对保存结果／停止未执行操作').trigger('click'); await flushPromises()
    expect(button('重试原操作').exists()).toBe(true)
    await router.push('/modules/production?factory=huakang-c'); expect(router.currentRoute.value.fullPath).toBe(path)
  })
  it('applies the reply status filter server-side and labels passed estimates without claiming receipt', async () => {
    await open({ ...received, workflow_status: 'partial_reply', expected_date_passed: true })
    expect(wrapper.text()).toContain('预计日期已过，实收待核实')
    await wrapper.get('[aria-label="办理状态筛选"]').setValue('partial_reply')
    await wrapper.get('form.order-toolbar').trigger('submit'); await flushPromises()
    expect(ordersApi.list).toHaveBeenLastCalledWith(1, '', 'partial_reply', '')
  })
  it('refreshes filtered rows and totals after a save changes the workflow status', async () => {
    await open()
    await wrapper.get('[aria-label="办理状态筛选"]').setValue('awaiting_receipt')
    await receiptForm()
    vi.mocked(ordersApi.command).mockResolvedValue(received)
    vi.mocked(ordersApi.list).mockResolvedValue(page([]))
    await wrapper.get('form.order-form').trigger('submit'); await flushPromises()
    expect(ordersApi.list).toHaveBeenLastCalledWith(1, '', 'awaiting_receipt', '')
    expect(wrapper.text()).not.toContain('ORDER-001')
    expect(wrapper.text()).toContain('共 0 条')
  })
})

const requirement = { material_id: 'm1', material_version: 1, part_codes: ['front'], quantity_per_set: '0.125', unit: '米', required_for_cutting: true, stage: '裁剪', note: '' }
const boundRow: CuttingOrder = { ...received, current: { ...received.current!, version: 2, data: { ...received.current!.data, target_sets: 50, quantity_basis: '工程核定', bom: { ...bom, data: { ...bom.data, requirements: [requirement] } as typeof bom.data, material_references: { 'm1:1': { code: 'M001', name: '测试布料' } } } } } }
const submittedRow: CuttingOrder = { ...boundRow, current: { ...boundRow.current!, version: 3, data: { ...boundRow.current!.data, requisition: { version: 3, actor_id: 'engineering', created_at: '', lines: [{ ...requirement, row: 0, quantity: '7', theoretical_quantity: '6.25', replied_quantity: '0', awaiting_reply_quantity: '7', material: { code: 'M001', name: '测试布料' }, purchase_mode: 'purchase', no_purchase_reason: '' }] } } } }

describe('engineering requisitions and procurement form operations', () => {
  it('shows the no-purchase basis in current and historical demand without asking for a reply', async () => {
    const noPurchase = structuredClone(submittedRow)
    const r = noPurchase.current!.data.requisition!.lines[0]!
    Object.assign(r, { quantity: '0', purchase_mode: 'no_purchase', no_purchase_reason: '客户供料依据001' })
    noPurchase.workflow_status = 'no_purchase'
    await open(noPurchase)
    expect(wrapper.text()).toContain('本次不采购：客户供料依据001')
    expect(wrapper.text()).toContain('无需采购交期')
    expect(wrapper.findAll('button').some(b => b.text() === '采购回复分批交期')).toBe(false)
    vi.mocked(ordersApi.history).mockResolvedValue(page([noPurchase.current!]))
    await button('查看历史版本').trigger('click'); await flushPromises()
    expect(wrapper.get('details').text()).toContain('客户供料依据001')
  })
  it('submits an explicit zero no-purchase line with its reason and keeps dirty protection', async () => {
    await open(boundRow)
    await button('工程提交物料需求').trigger('click')
    await wrapper.get('[aria-label="采购方式1"]').setValue('no_purchase')
    expect(wrapper.get('[aria-label="需求数量1"]').element).toHaveProperty('value', '0')
    await wrapper.get('[aria-label="不采购原因1"]').setValue('客户供料，尚未确认库存')
    await button('取消编辑').trigger('click')
    expect(wrapper.find('form.order-form').exists()).toBe(true)
    await wrapper.get('form.order-form textarea').setValue('工程核定采购范围')
    vi.mocked(ordersApi.command).mockResolvedValue(submittedRow)
    await wrapper.get('form.order-form').trigger('submit'); await flushPromises()
    expect(ordersApi.command).toHaveBeenCalledWith('line-1', 'requisition', expect.objectContaining({ lines: [{ row: 0, quantity: '0', purchase_mode: 'no_purchase', no_purchase_reason: '客户供料，尚未确认库存' }] }))
  })
  it('adds, edits and removes date batches without sending removed rows', async () => {
    await open(submittedRow)
    await button('采购回复分批交期').trigger('click'); await button('增加交期批次').trigger('click')
    const inputs = wrapper.findAll('.eta-row input')
    await inputs[0]!.setValue('3.5'); await inputs[1]!.setValue('2026-10-18'); await inputs[2]!.setValue('供应商A'); await inputs[3]!.setValue('PO001')
    await button('增加交期批次').trigger('click')
    await wrapper.findAll('.eta-row button')[1]!.trigger('click')
    await wrapper.get('form.order-form textarea').setValue('供应商确认首批日期')
    vi.mocked(ordersApi.command).mockResolvedValue(submittedRow)
    await wrapper.get('form.order-form').trigger('submit'); await flushPromises()
    expect(ordersApi.command).toHaveBeenCalledWith('line-1', 'eta', expect.objectContaining({ requisition_version: 3, batches: [{ row: 0, quantity: '3.5', expected_date: '2026-10-18', supplier: '供应商A', purchase_reference: 'PO001' }] }))
  })
  it('preserves batch edits after a server over-allocation rejection', async () => {
    await open(submittedRow); await button('采购回复分批交期').trigger('click'); await button('增加交期批次').trigger('click')
    await wrapper.get('.eta-row input').setValue('100')
    vi.mocked(ordersApi.command).mockRejectedValue({ response: { status: 422, data: { detail: '分批交期数量合计不能超过需求量' } } })
    await wrapper.get('form.order-form').trigger('submit'); await flushPromises()
    expect(wrapper.get('.eta-row input').element).toHaveProperty('value', '100')
    expect(wrapper.text()).toContain('分批交期数量合计不能超过需求量')
  })
  it('submits engineering withdrawal against the exact requisition version', async () => {
    await open(submittedRow)
    await button('工程申请撤回／修订').trigger('click'); await wrapper.get('form.order-form textarea').setValue('原需求数量需修订')
    vi.mocked(ordersApi.command).mockResolvedValue(submittedRow)
    await wrapper.get('form.order-form').trigger('submit'); await flushPromises()
    expect(ordersApi.command).toHaveBeenCalledWith('line-1', 'withdraw', expect.objectContaining({ requisition_version: 3, expected_version: 3 }))
  })
  it('requires procurement disposition evidence and completion confirmation for the old demand', async () => {
    const pending: CuttingOrder = { ...submittedRow, pending_purchase: submittedRow.current!.data, current: { ...submittedRow.current!, version: 4, data: { ...submittedRow.current!.data, purchase_reconciliation_required: true, pending_requisition_version: 3 } } }
    await open(pending)
    expect(wrapper.findAll('button').some(b => b.text() === '采购回复分批交期')).toBe(false)
    await button('采购核对旧需求').trigger('click')
    await wrapper.get('[aria-label="旧采购处理结果"]').setValue('cancelled_or_reallocated')
    const fields = wrapper.findAll('form.order-form textarea')
    await fields[0]!.setValue('PO001全部已转用并核对数量'); await fields[1]!.setValue('采购核对完成')
    await wrapper.get('form.order-form input[type="checkbox"]').setValue(true)
    vi.mocked(ordersApi.command).mockResolvedValue(boundRow)
    await wrapper.get('form.order-form').trigger('submit'); await flushPromises()
    expect(ordersApi.command).toHaveBeenCalledWith('line-1', 'reconcile', expect.objectContaining({ requisition_version: 3, disposition: 'cancelled_or_reallocated', all_handled: true, evidence: 'PO001全部已转用并核对数量' }))
  })
})


describe('P2a preplan editor and protection', () => {
  const bound = (): CuttingOrder => ({ ...received, current: { ...received.current!, data: { ...received.current!.data, bom, target_sets: 50 } } })
  const resource: MasterRecord = { id: 'resource-1', factory_id: 'huakang-c', kind: 'resource', code: 'R001', version: 1, status: 'active', actor_id: 'planner', created_at: '', reason: '', data: { name: '本厂一组', execution: 'internal', process: 'cutting', contact: '', source_reference: '主管', calendar: null } }
  async function planForm() {
    await open(bound(), ['read', 'plan_write', 'plan_publish'])
    await button('编制任务与日计划').trigger('click')
    vi.mocked(cuttingApi.list).mockResolvedValue(page([resource]))
    await button('查本厂／外发资源').trigger('click'); await flushPromises()
    await button('增加任务：R001 · 本厂一组 V1').trigger('click')
    await wrapper.get('.plan-task input[type="date"]').setValue('2026-10-12')
    await wrapper.findAll('.plan-task input').find(i => i.attributes('maxlength') === '500')!.setValue('ISSUE-001')
    await wrapper.get('.plan-task textarea').setValue('本批50套物料实际领料依据')
    expect(wrapper.text()).not.toContain('本次操作依据')
  }
  it('saves explicit task allocation without posting production output', async () => {
    await planForm()
    vi.mocked(ordersApi.command).mockResolvedValue(bound())
    await wrapper.get('form.order-form').trigger('submit'); await flushPromises()
    expect(ordersApi.command).toHaveBeenCalledWith('line-1', 'plan', expect.objectContaining({ tasks: [expect.objectContaining({ resource_id: 'resource-1', resource_version: 1, target_sets: 50, actual_issue_date: '2026-10-12', actual_issue_reference: 'ISSUE-001', days: [] })] }))
    expect(wrapper.text()).toContain('实际填数、领料和库存记账在后续阶段接入')
  })
  it('protects task drafts on route exit and freezes the original payload after timeout', async () => {
    await planForm()
    await router.push('/modules/production?factory=huakang-c'); expect(router.currentRoute.value.fullPath).toBe(path)
    vi.mocked(ordersApi.command).mockRejectedValueOnce(new Error('lost'))
    await wrapper.get('form.order-form').trigger('submit'); await flushPromises()
    const original = vi.mocked(ordersApi.command).mock.calls[0]
    expect(wrapper.get('form.order-form fieldset').attributes()).toHaveProperty('disabled')
    vi.mocked(ordersApi.command).mockResolvedValueOnce(bound())
    await button('重试原操作').trigger('click'); await flushPromises()
    expect(vi.mocked(ordersApi.command).mock.calls[1]).toEqual(original)
  })
  it('rejects late resource-search success after the query changes', async () => {
    await open(bound(), ['read', 'plan_write']); await button('编制任务与日计划').trigger('click')
    let resolve!: (value: ReturnType<typeof page<MasterRecord>>) => void
    vi.mocked(cuttingApi.list).mockImplementationOnce(() => new Promise(r => { resolve = r }))
    await button('查本厂／外发资源').trigger('click')
    await wrapper.get('.plan-editor input').setValue('other')
    resolve(page([resource])); await flushPromises()
    expect(wrapper.text()).not.toContain('增加任务：R001')
  })
  it('hides preplan editing for read-only users', async () => {
    await open(bound(), ['read'])
    expect(wrapper.text()).not.toContain('编制任务与日计划')
  })
  it('publishes only the saved draft version and displays incomplete scheduling honestly', async () => {
    const record = bound()
    const plan = { version: 3, allocated_sets: 50, unallocated_sets: 0, actor_id: 'planner', created_at: '', reason: '首版', tasks: [{ task_id: 't1', name: '本厂', resource_id: resource.id, resource_version: 1, resource, target_sets: 50, materials: [], readiness_basis: '预计用料', actual_issue_date: '2026-10-12', actual_issue_reference: 'ISSUE-001', prerequisite_date: null, prerequisite_basis: '', days: [{ day: '2026-10-15', sets: 20 }], planned_sets: 20, unplanned_sets: 30, completion_date: null, first_supply_date: '2026-10-15', earliest_supply_date: '2026-10-15' }] }
    record.current!.data.planning = { draft: plan }
    await open(record, ['read', 'plan_publish'])
    expect(wrapper.text()).toContain('计划未排完')
    await button('发布生产预排').trigger('click')
    expect(wrapper.find('form.order-form textarea').exists()).toBe(false)
    vi.mocked(ordersApi.command).mockResolvedValue(record)
    await wrapper.get('form.order-form').trigger('submit'); await flushPromises()
    expect(ordersApi.command).toHaveBeenCalledWith('line-1', 'plan-publish', expect.objectContaining({ draft_version: 3 }))
    wrapper.unmount()
    record.planning_summary = { draft_stale: true, published_stale: false, draft_version: 3, published_version: null }
    await open(record, ['read','plan_write','plan_publish'])
    expect(button('发布生产预排').attributes()).toHaveProperty('disabled')
    await button('编制任务与日计划').trigger('click')
    expect(wrapper.get('.plan-task input[type="date"]').element).toHaveProperty('value','')
    expect(wrapper.text()).toContain('须重新核对填写')
  })
  it('prefills purchase reply dates and submits an advance plan without actual issue evidence', async () => {
    const record = bound()
    record.current!.data.bom = { ...bom, material_references: { 'm1:1': { code: 'M1', name: '蓝布' } }, data: { ...bom.data, requirements: [{ material_id: 'm1', material_version: 1, required_for_cutting: true, part_codes: ['front'], quantity_per_set: '1', unit: '米', stage: '裁剪', note: '' }] } as import('../api').BomData }
    record.current!.data.batches = [{ row: 0, quantity: '50', expected_date: '2026-11-02', supplier: '供应商', purchase_reference: 'PO-001' }]
    await open(record, ['read', 'plan_write'])
    await button('编制任务与日计划').trigger('click')
    vi.mocked(cuttingApi.list).mockResolvedValue(page([resource]))
    await button('查本厂／外发资源').trigger('click'); await flushPromises()
    await button('增加任务：R001 · 本厂一组 V1').trigger('click')
    expect(wrapper.get('.plan-task input[type="date"]').element).toHaveProperty('value','2026-11-02')
    await wrapper.get('.plan-task textarea').setValue('PO-001支持本批50套')
    expect(wrapper.text()).not.toContain('本次操作依据')
    await button('增加日计划').trigger('click')
    await wrapper.get('.plan-task .plan-tools input[type="date"]').setValue('2026-11-05')
    vi.mocked(ordersApi.command).mockResolvedValue(record)
    await wrapper.get('form.order-form').trigger('submit'); await flushPromises()
    expect(ordersApi.command).toHaveBeenCalledWith('line-1','plan',expect.objectContaining({ tasks:[expect.objectContaining({ date_basis:'estimated', actual_issue_date:null, actual_issue_reference:'', materials:[{row:0,expected_date:'2026-11-02'}] })] }))
  })
  it('offers actual verification and preserves its reference in the saved adjustment', async () => {
    await planForm()
    await wrapper.get('.plan-task select').setValue('actual')
    expect(wrapper.text()).toContain('前置工序实际就绪日期')
    vi.mocked(ordersApi.command).mockResolvedValue(bound())
    await wrapper.get('form.order-form').trigger('submit'); await flushPromises()
    expect(ordersApi.command).toHaveBeenCalledWith('line-1','plan',expect.objectContaining({ tasks:[expect.objectContaining({ date_basis:'actual', actual_issue_date:'2026-10-12', actual_issue_reference:'ISSUE-001' })] }))
  })

  it('requires a reason for an already published plan and carries the saved reason into publication', async () => {
    const record=bound()
    const original={ version:3,tasks:[],allocated_sets:0,unallocated_sets:50,actor_id:'planner',created_at:'',reason:'首次发布' }
    record.current!.data.planning={ published:original,baseline:original }
    await open(record,['read','plan_write','plan_publish'])
    await button('编制任务与日计划').trigger('click')
    const reason=wrapper.get('form.order-form textarea')
    expect(reason.attributes()).toHaveProperty('required')
    expect(wrapper.text()).toContain('已发布计划调整原因')
    await reason.setValue('采购延期调整日计划')
    const revised={ ...record, current:{...record.current!,version:4,data:{...record.current!.data,planning:{...record.current!.data.planning,draft:{...original,version:4,reason:'采购延期调整日计划',adjustment_reason:'采购延期调整日计划'}}}} }
    vi.mocked(ordersApi.command).mockResolvedValue(revised)
    await wrapper.get('form.order-form').trigger('submit');await flushPromises()
    expect(ordersApi.command).toHaveBeenCalledWith('line-1','plan',expect.objectContaining({ reason:'采购延期调整日计划' }))
    await button('发布生产预排').trigger('click')
    expect(wrapper.get('form.order-form textarea').element).toHaveProperty('value','采购延期调整日计划')
    expect(wrapper.get('form.order-form textarea').attributes()).toHaveProperty('required')
    await wrapper.get('form.order-form').trigger('submit');await flushPromises()
    expect(ordersApi.command).toHaveBeenLastCalledWith('line-1','plan-publish',expect.objectContaining({ reason:'采购延期调整日计划',draft_version:4 }))
  })

})
