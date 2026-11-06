import { beforeEach, afterEach, describe, expect, it, vi } from 'vitest'
import { mount, flushPromises, type VueWrapper } from '@vue/test-utils'
import { createRouter, createMemoryHistory } from 'vue-router'
import { useAuthStore } from '@/stores/auth'
import { newNode } from '@/features/engineering-bom/api'
import View from './MaterialPlanningView.vue'
import { trialApi as api, blankTrial, type FrozenBom, type TrialDraft, type TrialResult, type Amount, type OrderBasis } from './api'

vi.mock('@/stores/auth', async () => {
  const { reactive } = await import('vue')
  const store = reactive({ sessionVersion: 1, authorizationVersion: 1 })
  return { useAuthStore: () => store }
})
const amount = (value: string): Amount => ({ value, numerator: value, denominator: '1', approximate: false })
const frozen = (version = 2): FrozenBom => ({ id: 'bom-1', version, materials: {}, data: { item_no: '001', name: '成品', specification: '', source_reference: '',
  nodes: [{ ...newNode(), key: 'root', unit: '套' }, { ...newNode(), key: 'fabric', parent: 'root', source_code: '01-001', source_name: '布料', unit: '码', process: '裁床', exempt_loss: true }] } })
const result = (): TrialResult => ({ lines: [], totals: [], finished_quantity: amount('100'), finished_unit: '套', supply_status: 'PENDING_VERIFICATION',
  net_purchase_quantity: null, pending: ['库存基线', '有效在途', '工序物料期'], algorithm: 'gross-fraction-v1' })
const draft = (): TrialDraft => ({ id: 'draft-1', version: 1, owner_id: 'sales-1', owner_name: '业务员', status: 'DRAFT_DATA_PENDING',
  inputs: { ...blankTrial(), title: '历史试算', bom_id: 'bom-1', bom_version: 2, quantity: '100', loss_percent: '5', loss_exemptions: { fabric: true } },
  bom: frozen(), result: result(), occurred_at: '2026-11-04', reason: '核对用量' })
const attributedBom = (version = 2): FrozenBom => {
  const b = frozen(version)
  b.materials['m:1'] = { id: 'm', version: 1, code: '04-001', name: '裁片', status: 'APPROVED',
    data: { unit: '套', engineering: { group: '04', department: '裁床', attribute: '自制', approval: 'APPROVED' } } }
  Object.assign(b.data.nodes[1]!, { material_id: 'm', material_version: 1 })
  b.data.nodes.push({ ...b.data.nodes[1]!, key: 'sew', process: '车缝' })
  return b
}
let wrapper: VueWrapper
const order = (): OrderBasis => ({ line_id: 'order-1', revision: 3, version: 2, factory_id: 'huakang-c', customer_code: 'test', customer_name: '测试客户', reference_no: 'PO-123', product_no: '001', quantity: '100', shipped_quantity: '0', status: 'active' })
const button = (name: string) => wrapper.findAll('button').find(b => b.text() === name)!
const input = (label: string) => wrapper.findAll('label').find(l => l.text().startsWith(label))!.get('input')
const bomSelect = () => wrapper.findAll('label').find(l => l.text().startsWith('有效 BOM'))!.get('select')
async function start(rows: TrialDraft[] = [], boms = [frozen()], canWrite = true, factory = 'huakang-c', canReadOrders = false, workflow = false) {
  vi.spyOn(api, 'access').mockResolvedValue({ enabled: true, schema_ready: true, can_write: canWrite, can_read_orders: canReadOrders, order_schema_ready: true, can_submit: workflow, can_self_review: workflow })
  vi.spyOn(api, 'workspace').mockResolvedValue({ drafts: rows, boms })
  const router = createRouter({ history: createMemoryHistory(), routes: [{ path: '/:pathMatch(.*)*', component: View }] })
  await router.push(`/modules/sales-business/material-planning?factory=${factory}`); await router.isReady()
  wrapper = mount({ template: '<RouterView />' }, { global: { plugins: [router] } }); await flushPromises()
  return router
}
beforeEach(() => { vi.restoreAllMocks(); vi.spyOn(window, 'confirm').mockReturnValue(true) })
afterEach(() => { wrapper?.unmount() })

describe('material trial workspace', () => {
  it('submits the saved revision, locks its inputs, and keeps new draft creation available', async () => {
    const saved = draft(); saved.inputs.order = { line_id: 'order-1', revision: 3 }
    await start([saved], [frozen()], true, 'huakang-c', true, true)
    await button('查看／编辑').trigger('click')
    const submit = vi.spyOn(api, 'save').mockResolvedValue({ ...saved, version: 2, status: 'AWAITING_PROCESS_DATES' })
    await input('试算数量').setValue('99')
    expect(button('提交采购填期').attributes('disabled')).toBeDefined()
    await button('查看／编辑').trigger('click')
    await button('提交采购填期').trigger('click'); await flushPromises()
    expect(submit.mock.calls[0]![0]).toBe('/drafts/draft-1/submit')
    expect(submit.mock.calls[0]![1]).toMatchObject({ expected_version: 1 })
    expect(wrapper.get('fieldset').attributes('disabled')).toBeDefined()
    expect(button('新建试算').attributes('disabled')).toBeUndefined()
    expect(button('退回草稿修改')).toBeDefined()
  })

  it('refreshes procurement dates before owner self-review and retains unknown requests', async () => {
    const saved = draft(); saved.status = 'AWAITING_PROCESS_DATES'; saved.inputs.order = { line_id: 'order-1', revision: 3 }
    await start([saved], [frozen()], true, 'huakang-c', true, true)
    await button('查看／编辑').trigger('click')
    const dated = { ...saved, version: 3, status: 'AWAITING_SELF_REVIEW', process_dates: { 裁床: '2026-11-12' } }
    vi.mocked(api.workspace).mockResolvedValue({ boms: [frozen()], drafts: [dated] })
    await button('刷新依据与草稿').trigger('click'); await flushPromises()
    expect(wrapper.text()).toContain('2026-11-12')
    const save = vi.spyOn(api, 'save').mockRejectedValueOnce(new Error('连接中断')).mockResolvedValueOnce({ ...dated, version: 4, status: 'SELF_REVIEWED_DATA_PENDING' })
    await button('业务自审确认').trigger('click'); await flushPromises()
    expect(button('退回草稿修改').attributes('disabled')).toBeDefined()
    await button('核对并重试原请求').trigger('click'); await flushPromises()
    expect(save.mock.calls[1]).toEqual(save.mock.calls[0])
    expect(save.mock.calls[0]![1]).toMatchObject({ expected_version: 3 })
    expect(wrapper.text()).toContain('业务已自审，待供给资料')
  })

  it('links an authoritative order reference without treating lookup text as order data', async () => {
    await start([], [frozen()], true, 'huakang-c', true)
    const search = vi.spyOn(api, 'orders').mockResolvedValue({ items: [order()], has_more: true })
    const saved = draft(); saved.inputs.order = { line_id: 'order-1', revision: 3 }; saved.result.order_basis = order()
    saved.result.release_gate = { can_release: false, blockers: ['STOCK_VERIFICATION'] }
    const save = vi.spyOn(api, 'save').mockResolvedValue(saved)
    await button('新建试算').trigger('click'); await bomSelect().setValue('bom-1:2')
    await input('试算数量').setValue('80'); await input('查找订单').setValue('PO-123')
    await input('查找订单').trigger('keydown', { key: 'Enter' }); await flushPromises()
    expect(search).toHaveBeenCalledWith('PO-123'); expect(save).not.toHaveBeenCalled()
    expect(wrapper.text()).toContain('仅显示前 50 条')
    await button('关联此订单').trigger('click')
    expect(input('试算数量').element).toHaveProperty('value', '80')
    await wrapper.get('form').trigger('submit'); await flushPromises()
    expect(save.mock.calls[0]![1]).toMatchObject({ data: { order: { line_id: 'order-1', revision: 3 }, quantity: '80' } })
    expect(wrapper.text()).toContain('尚不能正式放单')
    await button('解除关联').trigger('click')
    expect(wrapper.text()).not.toContain('本次试算结果')
  })

  it.each([false, true])('clears visible order evidence on revocation even if workspace fails (%s)', async failed => {
    const saved = draft(); saved.inputs.order = { line_id: 'order-1', revision: 3 }; saved.result.order_basis = order()
    await start([saved], [frozen()], true, 'huakang-c', true)
    await button('查看／编辑').trigger('click')
    expect(wrapper.text()).toContain('PO-123')
    vi.mocked(api.access).mockResolvedValue({ enabled: true, schema_ready: true, can_write: true, can_read_orders: false, order_schema_ready: true })
    if (failed) vi.mocked(api.workspace).mockRejectedValue(new Error('暂时无法读取'))
    else vi.mocked(api.workspace).mockResolvedValue({ boms: [frozen()], drafts: [] })
    await button('刷新依据与草稿').trigger('click'); await flushPromises()
    expect(wrapper.text()).not.toContain('PO-123')
    expect(wrapper.find('form').exists()).toBe(false)
    expect(wrapper.findAll('button').some(b => b.text() === '查看／编辑')).toBe(false)
  })

  it('discards late order searches after opening another draft', async () => {
    await start([draft()], [frozen()], true, 'huakang-c', true)
    let finish!: (value: { items: OrderBasis[]; has_more: boolean }) => void
    vi.spyOn(api, 'orders').mockImplementation(() => new Promise(resolve => { finish = resolve }))
    await button('查看／编辑').trigger('click'); await button('查询订单').trigger('click')
    await button('新建试算').trigger('click')
    finish({ items: [order()], has_more: false }); await flushPromises()
    expect(wrapper.text()).not.toContain('PO-123')
  })

  it('keeps per-occurrence attributes in requests and renders separate same-code totals', async () => {
    const b = attributedBom()
    await start([], [b, attributedBom(4)])
    const computed = result()
    computed.totals = ['自制', '委外'].map(attribute => ({ material_id: 'm', material_version: 1, code: '04-001', name: '裁片', unit: '套',
      attribute, base: amount('100'), loss: amount('5'), gross: amount('105'), processes: ['裁床'], keys: [] }))
    const preview = vi.spyOn(api, 'preview').mockResolvedValue(computed)
    const save = vi.spyOn(api, 'save').mockResolvedValue(draft())
    await button('新建试算').trigger('click'); await bomSelect().setValue('bom-1:2')
    const attr = () => wrapper.get('select[aria-label="布料 裁床 本次物料属性"]')
    expect(attr().element).toHaveProperty('value', '自制')
    await attr().setValue('委外'); await button('计算用料').trigger('click'); await flushPromises()
    expect(preview.mock.calls[0]![0]).toMatchObject({ data: { material_attributes: { fabric: '委外', sew: '自制' } } })
    const summary = wrapper.findAll('table').find(t => t.text().includes('同物料同属性汇总'))!
    expect(summary.findAll('tbody tr').map(r => r.findAll('td')[1]!.text())).toEqual(['自制', '委外'])
    await attr().setValue('自制')
    expect(wrapper.text()).not.toContain('本次试算结果')
    await attr().setValue('委外'); await wrapper.get('form').trigger('submit'); await flushPromises()
    expect(save.mock.calls[0]![1]).toMatchObject({ data: { material_attributes: { fabric: '委外', sew: '自制' } } })
    expect(b.materials['m:1']!.data.engineering!.attribute).toBe('自制')
    await bomSelect().setValue('bom-1:4')
    expect(attr().element).toHaveProperty('value', '自制')
  })

  it.each([false, true])('loads legacy defaults or saved business attribute choices (override=%s)', async override => {
    const saved = draft(); saved.bom = attributedBom()
    if (override) saved.inputs.material_attributes = { fabric: '委外', sew: '自制' }
    else Reflect.deleteProperty(saved.inputs, 'material_attributes')
    await start([saved], [attributedBom()]); await button('查看／编辑').trigger('click')
    expect(wrapper.get('select[aria-label="布料 裁床 本次物料属性"]').element).toHaveProperty('value', override ? '委外' : '自制')
    const save = vi.spyOn(api, 'save').mockResolvedValue(saved)
    await wrapper.get('form').trigger('submit'); await flushPromises()
    expect(save.mock.calls[0]![1]).toMatchObject({ data: { material_attributes: { fabric: override ? '委外' : '自制', sew: '自制' } } })
  })

  it('shows engineering defaults for a saved draft that omitted its exemption map', async () => {
    const saved = draft(); saved.inputs.loss_exemptions = {}
    await start([saved]); await button('查看／编辑').trigger('click')
    expect(wrapper.get<HTMLInputElement>('input[type=checkbox]').element.checked).toBe(true)
    const save = vi.spyOn(api, 'save').mockResolvedValue(saved)
    await wrapper.get('form').trigger('submit'); await flushPromises()
    expect(save.mock.calls[0]![1]).toMatchObject({ data: { loss_exemptions: { fabric: true } } })
  })

  it('adopts engineering exemptions, clears stale results on edit, and saves only draft inputs', async () => {
    await start()
    vi.spyOn(api, 'preview').mockResolvedValue(result())
    const save = vi.spyOn(api, 'save').mockResolvedValue(draft())
    await button('新建试算').trigger('click'); await input('试算名称').setValue('订单参考试算'); await bomSelect().setValue('bom-1:2')
    expect(wrapper.get<HTMLInputElement>('input[type=checkbox]').element.checked).toBe(true)
    await input('试算数量').setValue('100'); await input('统一损耗率').setValue('5')
    await button('计算用料').trigger('click'); await flushPromises()
    expect(wrapper.text()).toContain('采购数量：待资料核实，尚未计算')
    await wrapper.get('input[type=checkbox]').setValue(false)
    expect(wrapper.text()).not.toContain('本次试算结果')
    await wrapper.get('form').trigger('submit'); await flushPromises()
    expect(save.mock.calls[0]![0]).toBe('/drafts')
    expect(save.mock.calls[0]![1]).toMatchObject({ data: { bom_id: 'bom-1', bom_version: 2, quantity: '100', loss_percent: '5', loss_exemptions: { fabric: false } } })
    expect(wrapper.text()).toContain('仍待资料核实')
    expect(wrapper.findAll('button').some(b => /审核|下发采购/.test(b.text()))).toBe(false)
  })

  it('keeps the original request after an uncertain write and blocks competing edits', async () => {
    await start([draft()]); await button('查看／编辑').trigger('click')
    const save = vi.spyOn(api, 'save').mockRejectedValueOnce(new Error('连接中断')).mockResolvedValueOnce(draft())
    await input('试算数量').setValue('120'); await wrapper.get('form').trigger('submit'); await flushPromises()
    const original = save.mock.calls[0]![1]
    expect(wrapper.get('fieldset').attributes('disabled')).toBeDefined()
    expect(button('新建试算').attributes('disabled')).toBeDefined()
    await button('核对并重试原请求').trigger('click'); await flushPromises()
    expect(save.mock.calls[1]![1]).toEqual(original)
    expect(wrapper.text()).toContain('已保存')
  })

  it('preserves historical results and requires an explicit new effective BOM choice', async () => {
    await start([draft()], [frozen(4)]); await button('查看／编辑').trigger('click')
    expect(wrapper.text()).toContain('此草稿依据已不是当前有效版本')
    expect(button('保存试算草稿').attributes('disabled')).toBeDefined()
    await bomSelect().setValue('bom-1:4')
    expect(window.confirm).toHaveBeenCalled()
    expect(wrapper.text()).not.toContain('本次试算结果')
    expect(button('保存试算草稿').attributes('disabled')).toBeUndefined()
  })

  it('ignores late calculations after changing quantity or opening a different draft', async () => {
    await start([draft()]); await button('查看／编辑').trigger('click')
    let finish!: (value: TrialResult) => void
    vi.spyOn(api, 'preview').mockImplementation(() => new Promise(resolve => { finish = resolve }))
    await button('计算用料').trigger('click'); await input('试算数量').setValue('200')
    finish(result()); await flushPromises()
    expect(wrapper.text()).not.toContain('本次试算结果')
    await button('计算用料').trigger('click'); await button('新建试算').trigger('click')
    finish(result()); await flushPromises()
    expect(wrapper.text()).not.toContain('本次试算结果')
  })

  it('clears private data after authorization changes and discards late history', async () => {
    await start([draft()])
    let finish!: (value: { items: TrialDraft[] }) => void
    vi.spyOn(api, 'history').mockImplementation(() => new Promise(resolve => { finish = resolve }))
    await button('历史').trigger('click')
    vi.mocked(api.access).mockRejectedValue({ response: { status: 403, data: { detail: '无权限' } } })
    useAuthStore().authorizationVersion++; await flushPromises()
    finish({ items: [draft()] }); await flushPromises()
    expect(wrapper.text()).toContain('无权限')
    expect(wrapper.text()).not.toContain('历史试算')
    expect(wrapper.text()).not.toContain('历史试算依据')
  })

  it('keeps read-only users from editing or creating drafts', async () => {
    await start([draft()], [frozen()], false)
    expect(button('新建试算').attributes('disabled')).toBeDefined()
    await button('查看／编辑').trigger('click')
    expect(wrapper.get('fieldset').attributes('disabled')).toBeDefined()
    expect(wrapper.text()).toContain('本次试算结果')
  })

  it('does not request Huakang C data from a different factory route', async () => {
    await start([], [], true, 'huakang-a')
    await button('刷新依据与草稿').trigger('click'); await flushPromises()
    expect(api.access).not.toHaveBeenCalled()
    expect(api.workspace).not.toHaveBeenCalled()
    expect(wrapper.text()).toContain('请在华康 C')
  })

  it('warns before abandoning changed inputs on navigation', async () => {
    const router = await start([draft()]); await button('查看／编辑').trigger('click')
    await input('试算数量').setValue('123')
    vi.mocked(window.confirm).mockReturnValue(false)
    await router.push('/elsewhere?factory=huakang-c')
    expect(router.currentRoute.value.path).toBe('/modules/sales-business/material-planning')
    expect(input('试算数量').element).toHaveProperty('value', '123')
  })
})
