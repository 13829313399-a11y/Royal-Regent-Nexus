import { beforeEach, afterEach, describe, expect, it, vi } from 'vitest'
import { mount, flushPromises, type VueWrapper } from '@vue/test-utils'
import { createRouter, createMemoryHistory } from 'vue-router'
import { useAuthStore } from '@/stores/auth'
import View from './MaterialPurchasingView.vue'
import { purchaseApi as api, emptyPurchase, type PurchaseSource, type PurchaseDocument, type PreparationChecks } from './purchaseApi'

vi.mock('@/stores/auth', async () => {
  const { reactive } = await import('vue')
  const state = reactive({ sessionVersion: 1, authorizationVersion: 1 })
  return { useAuthStore: () => state }
})
const amount = { value: '21', numerator: '21', denominator: '1', approximate: false }
const source = (): PurchaseSource => ({ id: 'd1', version: 4, item_no: '001', owner_name: '业务甲', process_dates: { 裁床: '2026-11-12' },
  groups: ['自制', '委外'].map((attribute, i) => ({ material_id: 'm1', material_version: 1, code: '04-001', name: '裁片', unit: '套', attribute, source_key: `g${i}`, purchasable: i === 1, processes: ['裁床'], base: amount, loss: amount, gross: amount })) })
const doc = (status = 'DRAFT', version = 1): PurchaseDocument => ({ id: 'p1', version, status, source: source(),
  data: { ...emptyPurchase(), demand_id: 'd1', demand_version: 4, supplier_reference: '供应商合成甲', currency: 'CNY', tax_rate: '13', delivery_date: '2026-11-20', delivery_location: '本厂', payment_terms: '按约定', lines: [{ source_key: 'g1', quantity: 22, purchase_unit: '套', unit_price: '0' }] },
  occurred_at: '2026-11-04', reason: '测试', created_by: { id: 'clerk', name: '采购甲', at: '2026-11-04' }, release_gate: { can_release: false, blockers: [] }, effective_on_order: false, released_at: null })
let wrapper: VueWrapper
const report = (): PreparationChecks => ({ document_id: 'p1', document_version: 1, demand_id: 'd1', bound_demand_version: 4, checked_at: '2026-11-04', source_current: false, source_issue: '订单依据已变化', can_release: false, cancelled_document_count: 1,
  source_comparison: { status: 'UNAVAILABLE', target_version: null, issue: '当前需求尚未重新自审，待业务完成后再核对差异。', rows: [], dates: [], unchanged_count: null },
  groups: [{ demand_version: 4, source_key: 'g1', code: '04-001', name: '裁片', attribute: '委外', material_version: 1, source_unit: '套', purchase_unit: '套', status: 'CHANGE_PENDING', known_quantity: '22', complete_quantity: '22', missing_quantity_count: 0, related_document_count: 2, possible_duplicate: true,
    documents: [{ id: 'p1', version: 1, supplier_reference: '供应商合成甲', quantity: 22, pending_kind: 'QUANTITY', proposed_quantity: 99 }] }] })
const button = (name: string) => wrapper.findAll('button').find(b => b.text() === name)!
async function start(rows: PurchaseDocument[] = [], write = true, approve = false, factory = 'huakang-c') {
  vi.spyOn(api, 'access').mockResolvedValue({ enabled: true, schema_ready: true, can_write: write, can_approve: approve, can_release: false })
  vi.spyOn(api, 'workspace').mockResolvedValue({ sources: [source()], documents: rows })
  const router = createRouter({ history: createMemoryHistory(), routes: [{ path: '/:pathMatch(.*)*', component: View }] })
  await router.push(`/modules/pmc-warehouse/material-purchasing?factory=${factory}`); await router.isReady()
  wrapper = mount({ template: '<RouterView />' }, { global: { plugins: [router] } }); await flushPromises()
  return router
}
beforeEach(() => { vi.restoreAllMocks(); vi.spyOn(window, 'confirm').mockReturnValue(true) })
afterEach(() => wrapper?.unmount())

describe('material purchase preparation', () => {
  it('shows process redistribution even when grouped totals have no differences', async () => {
    await start([doc()], false); await button('查看准备单').trigger('click')
    const result = report(), original = source().groups[1]!
    const delta = (value: string) => ({ ...amount, value, numerator: value })
    result.source_comparison = { status: 'COMPARED', target_version: 9, issue: null, unchanged_count: 1, rows: [], dates: [],
      process_comparison: { available: true, issue: null, unchanged_count: 0, rows: ['裁床', '车缝'].map((process, i) => ({
        process, source_key: 'g1', changes: ['QUANTITY'], before: { ...original, processes: [process] },
        after: { ...original, processes: [process], gross: delta(i ? '22' : '20') },
        delta: { base: delta(i ? '1' : '-1'), loss: delta('0'), gross: delta(i ? '1' : '-1') },
      })) } }
    vi.spyOn(api, 'checks').mockResolvedValue(result)
    await button('核对来源与重复准备').trigger('click'); await flushPromises()
    expect(wrapper.text()).toContain('分组汇总用量及参与工序无变化；各工序分配见下方')
    const table = wrapper.findAll('table').find(t => t.text().includes('各工序基础用量、损耗及毛需求'))!
    expect(table.findAll('tbody tr')).toHaveLength(2)
    expect(table.text()).toContain('裁床 ／ 用量变化'); expect(table.text()).toContain('车缝 ／ 用量变化')
    expect(table.text()).toContain('-1'); expect(table.text()).toContain('委外')
    expect(wrapper.text()).toContain('不代表补购数量')
    expect(wrapper.text()).not.toContain('各工序用量无变化')
  })
  it('does not present incomplete process evidence as unchanged or zero quantities', async () => {
    await start([doc()], false); await button('查看准备单').trigger('click')
    const result = report()
    result.source_comparison = { status: 'COMPARED', target_version: 9, issue: null, unchanged_count: 1, rows: [], dates: [],
      process_comparison: { available: false, issue: '原版缺少完整工序依据', unchanged_count: null, rows: [] } }
    vi.spyOn(api, 'checks').mockResolvedValue(result)
    await button('核对来源与重复准备').trigger('click'); await flushPromises()
    expect(wrapper.text()).toContain('原版缺少完整工序依据')
    expect(wrapper.text()).not.toContain('各工序用量无变化')
    expect(wrapper.text()).not.toContain('0 组工序用料未变化')
  })
  it.each(['DRAFT', 'PENDING_APPROVAL'])('requests cancellation from %s and shows its original status', async (status) => {
    const initial = doc(status), pending = doc('CHANGE_PENDING', 2)
    pending.pending_change = { kind: 'CANCEL', quantities: {}, before: { g1: null }, before_status: status, reason: '依据已更新', requested_by: { id: 'c', name: '采购甲', at: '' } }
    await start([initial]); await button('查看准备单').trigger('click')
    vi.mocked(api.workspace).mockResolvedValue({ sources: [source()], documents: [pending] })
    const cancel = vi.spyOn(api, 'command').mockResolvedValue(pending)
    await button('申请取消整单').trigger('click'); await flushPromises()
    expect(cancel.mock.calls[0]![0]).toBe('/documents/p1/change')
    expect(cancel.mock.calls[0]![1]).toMatchObject({ expected_version: 1, kind: 'CANCEL', quantities: {} })
    expect(wrapper.text()).toContain(`申请前状态：${status === 'DRAFT' ? '草稿' : '待负责人审核'}；驳回后恢复此状态`)
    expect(wrapper.get('fieldset').attributes('disabled')).toBeDefined()
    expect(wrapper.findAll('button').some(b => ['内部审核通过', '批准变更', '申请取消整单'].includes(b.text()))).toBe(false)
  })
  it.each(['DRAFT', 'PENDING_APPROVAL'])('restores %s after responsible rejection without marking it approved', async (status) => {
    const pending = doc('CHANGE_PENDING', 2)
    pending.pending_change = { kind: 'CANCEL', quantities: {}, before: {}, before_status: status, reason: '撤销', requested_by: { id: 'c', name: '采购甲', at: '' } }
    await start([pending], true, true); await button('查看准备单').trigger('click')
    const restored = doc(status, 3); restored.last_change = { ...pending.pending_change, decision: 'reject-change' }
    vi.spyOn(api, 'command').mockResolvedValue(restored)
    vi.mocked(api.workspace).mockResolvedValue({ sources: [source()], documents: [restored] })
    await button('驳回变更').trigger('click'); await flushPromises()
    expect(wrapper.text()).not.toContain('内部已审，未下发')
    expect(wrapper.get('fieldset').attributes('disabled') !== undefined).toBe(status !== 'DRAFT')
    expect(wrapper.findAll('button').some(b => b.text() === '内部审核通过')).toBe(status === 'PENDING_APPROVAL')
  })
  it('does not discard unsaved fields or a quantity proposal through cancellation', async () => {
    await start([doc(), { ...doc('APPROVED_UNRELEASED', 3), id: 'p2' }]); await button('查看准备单').trigger('click')
    await wrapper.get('input[aria-label="04-001 委外 拟订量"]').setValue('23')
    expect(button('申请取消整单').attributes('disabled')).toBeDefined()
    await wrapper.findAll('button').filter(b => b.text() === '查看准备单')[1]!.trigger('click')
    await wrapper.get('input[aria-label="申请新量"]').setValue('25')
    expect(button('申请取消整单').attributes('disabled')).toBeDefined()
    expect(button('提交改量申请').attributes('disabled')).toBeUndefined()
  })
  it('creates a linked empty draft only from cancelled preparation and freezes retries', async () => {
    const old = doc('CANCELLED_UNRELEASED', 5), latest = { ...source(), version: 9 }
    await start([old]); await button('查看准备单').trigger('click')
    const result = report(); result.document_version = 5
    result.source_comparison = { status: 'COMPARED', target_version: 9, issue: null, unchanged_count: 2, rows: [], dates: [] }
    vi.spyOn(api, 'checks').mockResolvedValue(result)
    await button('核对来源与重复准备').trigger('click'); await flushPromises()
    const created: PurchaseDocument = { ...doc(), id: 'p2', source: latest, data: { ...emptyPurchase(), demand_id: 'd1', demand_version: 9 }, replacement_of: { id: 'p1', version: 5, demand_version: 4 } }
    const command = vi.spyOn(api, 'command').mockRejectedValueOnce(new Error('连接中断')).mockResolvedValueOnce(created)
    await button('按新需求建立关联草稿').trigger('click'); await flushPromises()
    expect(command.mock.calls[0]![0]).toBe('/documents/p1/replacement')
    expect(command.mock.calls[0]![1]).toMatchObject({ expected_version: 5, demand_version: 9 })
    expect(command.mock.calls[0]![1]).not.toHaveProperty('data')
    vi.mocked(api.workspace).mockResolvedValue({ sources: [latest], documents: [old, created] })
    await button('核对并重试原请求').trigger('click'); await flushPromises()
    expect(command.mock.calls[1]).toEqual(command.mock.calls[0])
    expect(wrapper.text()).toContain('关联原准备单：p1 · v5')
    expect(wrapper.find('input[aria-label="04-001 委外 拟订量"]').exists()).toBe(false)
    expect(wrapper.get('input[aria-label="选择 04-001 自制"]').attributes('disabled')).toBeDefined()
    await wrapper.get('input[aria-label="选择 04-001 委外"]').setValue(true)
    expect(wrapper.get('input[aria-label="04-001 委外 拟订量"]').element).toHaveProperty('value', '')
    await wrapper.findAll('button').find(b => b.text() === '查看准备单')!.trigger('click')
    expect(wrapper.text()).toContain('原单已建立关联新单：p2')
    await button('查看关联新单').trigger('click')
    expect(wrapper.text()).toContain('关联原准备单：p1 · v5')
  })
  it.each([['APPROVED_UNRELEASED', true], ['CANCELLED_UNRELEASED', false]])('does not offer replacement for %s with write %s', async (status, write) => {
    await start([doc(status as string)], write as boolean); await button('查看准备单').trigger('click')
    const result = report(); result.source_comparison = { status: 'COMPARED', target_version: 9, issue: null, unchanged_count: 0, rows: [], dates: [] }
    vi.spyOn(api, 'checks').mockResolvedValue(result)
    await button('核对来源与重复准备').trigger('click'); await flushPromises()
    expect(wrapper.findAll('button').some(b => b.text() === '按新需求建立关联草稿')).toBe(false)
  })
  it('shows reviewed demand differences without treating them as purchase changes', async () => {
    await start([doc()], false); await button('查看准备单').trigger('click')
    const result = report(), before = source().groups[0]!, after = source().groups[1]!
    result.source_comparison = { status: 'COMPARED', target_version: 9, issue: null, unchanged_count: 0,
      rows: [
        { source_key: 'old', changes: ['REMOVED'], before, after: null, delta: { base: amount, loss: amount, gross: { ...amount, value: '-21', numerator: '-21' } } },
        { source_key: 'new', changes: ['ADDED'], before: null, after, delta: { base: amount, loss: amount, gross: amount } },
      ], dates: [{ process: '裁床', before: '2026-11-12', after: '2026-11-15' }] }
    vi.spyOn(api, 'checks').mockResolvedValue(result)
    await button('核对来源与重复准备').trigger('click'); await flushPromises()
    expect(wrapper.text()).toContain('原依据 v4 → 当前已自审 v9')
    expect(wrapper.text()).toContain('差额不是补购量')
    expect(wrapper.text()).toContain('原无此组'); expect(wrapper.text()).toContain('当前无此组')
    expect(wrapper.text()).toContain('-21'); expect(wrapper.text()).toContain('裁床 物料期：2026-11-12 → 2026-11-15')
    expect(wrapper.text()).toContain('自制'); expect(wrapper.text()).toContain('委外')
  })
  it('shows an unavailable comparison without suggesting a zero difference', async () => {
    await start([doc()], false); await button('查看准备单').trigger('click')
    vi.spyOn(api, 'checks').mockResolvedValue(report())
    await button('核对来源与重复准备').trigger('click'); await flushPromises()
    expect(wrapper.text()).toContain('当前需求尚未重新自审')
    expect(wrapper.text()).not.toContain('用料分组、用量和参与工序无变化')
  })
  it('checks saved versions with read permission and distinguishes proposed amounts from prepared quantities', async () => {
    await start([doc()], false); await button('查看准备单').trigger('click')
    const checks = vi.spyOn(api, 'checks').mockResolvedValue(report())
    await button('核对来源与重复准备').trigger('click'); await flushPromises()
    expect(checks).toHaveBeenCalledWith('p1', 1)
    expect(wrapper.text()).toContain('订单依据已变化')
    expect(wrapper.text()).toContain('见于 2 张准备单')
    expect(wrapper.text()).toContain('申请改为 99（未计入）')
    expect(wrapper.text()).toContain('已排除 1 张已取消准备单')
    expect(wrapper.text()).toContain('正式下发仍未开放')
  })
  it('invalidates pending checks on edits and hides results when opening another document', async () => {
    await start([doc()]); await button('查看准备单').trigger('click')
    let finish!: (value: PreparationChecks) => void
    vi.spyOn(api, 'checks').mockImplementation(() => new Promise(resolve => { finish = resolve }))
    await button('核对来源与重复准备').trigger('click')
    await wrapper.get('input[aria-label="04-001 委外 拟订量"]').setValue('23')
    finish(report()); await flushPromises()
    expect(wrapper.text()).not.toContain('核对时间')
    expect(button('核对来源与重复准备').attributes('disabled')).toBeDefined()
    await button('查看准备单').trigger('click')
    vi.mocked(api.checks).mockResolvedValue(report())
    await button('核对来源与重复准备').trigger('click'); await flushPromises()
    expect(wrapper.text()).toContain('核对时间')
    await button('新建准备单').trigger('click')
    expect(wrapper.text()).not.toContain('核对时间')
  })
  it('discards a late preparation report after read permission is revoked', async () => {
    await start([doc()]); await button('查看准备单').trigger('click')
    let finish!: (value: PreparationChecks) => void
    vi.spyOn(api, 'checks').mockImplementation(() => new Promise(resolve => { finish = resolve }))
    await button('核对来源与重复准备').trigger('click')
    vi.mocked(api.access).mockRejectedValue({ response: { status: 403, data: { detail: '无权限' } } })
    useAuthStore().authorizationVersion++; await flushPromises(); finish(report()); await flushPromises()
    expect(wrapper.text()).not.toContain('供应商合成甲'); expect(wrapper.text()).not.toContain('核对时间')
  })
  it('preserves source attributes and leaves proposed quantities unfilled when creating lines', async () => {
    await start(); await button('新建准备单').trigger('click')
    await wrapper.get('select').setValue('d1:4')
    expect(wrapper.get('input[aria-label="选择 04-001 自制"]').attributes('disabled')).toBeDefined()
    await wrapper.get('input[aria-label="选择 04-001 委外"]').setValue(true)
    const saved = doc(); vi.mocked(api.workspace).mockResolvedValue({ sources: [source()], documents: [saved] })
    const save = vi.spyOn(api, 'command').mockResolvedValue(saved)
    await wrapper.get('form').trigger('submit'); await flushPromises()
    expect(save.mock.calls[0]![1]).toMatchObject({ data: { demand_id: 'd1', demand_version: 4, lines: [{ source_key: 'g1', quantity: null, purchase_unit: '', unit_price: null }] } })
    expect(wrapper.text()).toContain('正式下发未开放')
    expect(wrapper.findAll('button').some(b => b.text() === '正式下发')).toBe(false)
  })
  it('requires saving edits before submitting and does not give clerks approval buttons', async () => {
    await start([doc()]); await button('查看准备单').trigger('click')
    const submit = vi.spyOn(api, 'command').mockResolvedValue(doc('PENDING_APPROVAL', 2))
    await wrapper.get('input[aria-label="04-001 委外 拟订量"]').setValue('23')
    expect(button('提交负责人审核').attributes('disabled')).toBeDefined()
    await button('查看准备单').trigger('click')
    vi.mocked(api.workspace).mockResolvedValue({ sources: [source()], documents: [doc('PENDING_APPROVAL', 2)] })
    await button('提交负责人审核').trigger('click'); await flushPromises()
    expect(submit.mock.calls[0]![0]).toBe('/documents/p1/actions/submit')
    expect(wrapper.get('fieldset').attributes('disabled')).toBeDefined()
    expect(button('内部审核通过')).toBeUndefined()
  })
  it('shows old and requested quantities to the responsible approver', async () => {
    const changed = doc('CHANGE_PENDING', 4)
    changed.pending_change = { kind: 'QUANTITY', before: { g1: 22 }, quantities: { g1: 25 }, reason: '需要改量', requested_by: { id: 'clerk', name: '采购甲', at: '2026-11-04' } }
    await start([changed], false, true); await button('查看准备单').trigger('click')
    expect(wrapper.text()).toContain('22 → 25'); expect(wrapper.text()).toContain('委外')
    const approve = vi.spyOn(api, 'command').mockResolvedValue(doc('APPROVED_UNRELEASED', 5))
    vi.mocked(api.workspace).mockResolvedValue({ sources: [source()], documents: [doc('APPROVED_UNRELEASED', 5)] })
    await button('批准变更').trigger('click'); await flushPromises()
    expect(approve.mock.calls[0]![0]).toBe('/documents/p1/actions/approve-change')
    expect(wrapper.text()).toContain('内部已审，未下发')
  })
  it('sends quantity changes as a proposal rather than overwriting the document', async () => {
    await start([doc('APPROVED_UNRELEASED', 3)]); await button('查看准备单').trigger('click')
    const save = vi.spyOn(api, 'command').mockResolvedValue(doc('CHANGE_PENDING', 4))
    await wrapper.get('input[aria-label="申请新量"]').setValue('25')
    await button('提交改量申请').trigger('click'); await flushPromises()
    expect(save.mock.calls[0]![0]).toBe('/documents/p1/change')
    expect(save.mock.calls[0]![1]).toMatchObject({ expected_version: 3, kind: 'QUANTITY', quantities: { g1: 25 } })
  })
  it('locks uncertain requests and rereads current state after replaying an older receipt', async () => {
    await start([doc()]); await button('查看准备单').trigger('click')
    const save = vi.spyOn(api, 'command').mockRejectedValueOnce(new Error('连接中断')).mockResolvedValueOnce(doc('DRAFT', 2))
    await wrapper.get('form').trigger('submit'); await flushPromises()
    expect(wrapper.get('fieldset').attributes('disabled')).toBeDefined()
    vi.mocked(api.workspace).mockResolvedValue({ sources: [source()], documents: [doc('PENDING_APPROVAL', 3)] })
    await button('核对并重试原请求').trigger('click'); await flushPromises()
    expect(save.mock.calls[1]).toEqual(save.mock.calls[0])
    expect(wrapper.get('fieldset').attributes('disabled')).toBeDefined()
    expect(wrapper.text()).toContain('待负责人审核')
  })
  it('clears private records on revocation and discards late history', async () => {
    await start([doc()]); await button('查看准备单').trigger('click')
    let finish!: (value: { items: PurchaseDocument[] }) => void
    vi.spyOn(api, 'history').mockImplementation(() => new Promise(resolve => { finish = resolve }))
    await button('查看历史').trigger('click')
    vi.mocked(api.access).mockRejectedValue({ response: { status: 403, data: { detail: '无权限' } } })
    useAuthStore().authorizationVersion++; await flushPromises(); finish({ items: [doc()] }); await flushPromises()
    expect(wrapper.text()).toContain('无权限'); expect(wrapper.text()).not.toContain('供应商合成甲')
  })
  it('does not fetch another factory', async () => {
    await start([], true, false, 'huakang-a')
    expect(api.access).not.toHaveBeenCalled()
    expect(api.workspace).not.toHaveBeenCalled()
  })
  it('shows historical proposed quantities separately from the effective quantities and decisions', async () => {
    const old = doc('CHANGE_PENDING', 4)
    old.pending_change = { kind: 'QUANTITY', before: { g1: 22 }, quantities: { g1: 25 }, reason: '申请说明', requested_by: { id: 'c', name: '采购甲', at: '' } }
    const decided = doc('APPROVED_UNRELEASED', 5)
    decided.last_change = { ...old.pending_change, decision: 'reject-change', decided_by: { id: 'h', name: '负责人甲', at: '' }, decision_reason: '暂不改量' }
    await start([decided], false, true); await button('查看准备单').trigger('click')
    vi.spyOn(api, 'history').mockResolvedValue({ items: [decided, old] })
    await button('查看历史').trigger('click'); await flushPromises()
    const history = wrapper.findAll('details')
    expect(history[0]!.text()).toContain('驳回改量'); expect(history[0]!.text()).toContain('22 → 25')
    expect(history[1]!.text()).toContain('当时申请：改量'); expect(history[1]!.text()).toContain('22 → 25')
  })
})
