import { flushPromises, mount } from '@vue/test-utils'
import { beforeEach, expect, it, vi } from 'vitest'
import Dialog from '../CartonScheduleBatchDialog.vue'
import { batchPaperError, batchPaperPreview, batchSourceError, emptyBatchPapers, pendingScheduleBatches, sameScheduleItem, scheduleBatchConfigurations, schedulePacking, readScheduleBatchDraft, writeScheduleBatchDraft, effectiveBatchWeights, batchWeightError, type ScheduleBatchPreview } from '@/features/carton-procurement/scheduleBatch'
import type { MasterRecord } from '@/api/cartonMaster'

const api = vi.hoisted(() => ({ get: vi.fn(), importDetail: vi.fn(), create: vi.fn(), responsibilities: vi.fn() }))
vi.mock('@/api/cartonCustomerResponsibilities', () => ({ cartonCustomerResponsibilitiesApi: { get: api.responsibilities } }))
vi.mock('@/api/cartonMaster', async importOriginal => ({ ...await importOriginal<typeof import('@/api/cartonMaster')>(), cartonMasterApi: api }))
vi.mock('@/api/cartonProcurement', () => ({ cartonProcurementApi: api }))
vi.mock('@/api/cartonScheduleBatch', () => ({ cartonScheduleBatchApi: api }))
const stubs = Object.fromEntries(['DialogRoot', 'DialogPortal', 'DialogOverlay', 'DialogContent', 'DialogTitle', 'DialogDescription'].map(name => [name, { template: '<div><slot /></div>' }]))
const source = { customer_code: 'C1', customer_name: 'BUZZ BEE', contract_no: '53607', item_no: '57520', quantity: 4842, carton_rule: '6', customer_due_date: '2026-12-01', schedule_section: 'PENDING' as const, source_sheet: 'ITEM', source_row: 2, source_reference: 'SO-1' }
const selection: ScheduleBatchPreview[] = [{ batchId: 'B1', source }, { batchId: 'B1', source: { ...source, contract_no: '53608', quantity: 588, source_row: 3, customer_due_date: '2026-12-03' } }]
const config = { id: 'M1', kind: 'CONFIG', customer_code: '', code: '57520', status: 'ACTIVE', revision: 3, data: { lines: [{ packaging_type: '外箱', paper_quality: 'A33', specification: '40*30*20', dimension_unit: 'cm', unit: '个', usage_quantity: 24 }] } } as MasterRecord
const props = { open: true, factoryId: 'huaxing', identityKey: 'actor', viewerKey: 'actor-auth1', selection }
function batch(rows = selection) { return { id: 'B1', status: 'PARSED', parse_summary: { schedule_customer: { customer_code: 'C1', customer_name: 'BUZZ BEE' }, rows: rows.map(row => row.source) } } }
function render(overrides = {}) { return mount(Dialog, { props: { ...props, ...overrides }, global: { stubs } }) }
beforeEach(() => { vi.resetAllMocks(); window.localStorage.clear(); pendingScheduleBatches.clear(); api.responsibilities.mockResolvedValue({ unrestricted: true, own_customer_codes: [] }); api.get.mockResolvedValue({ records: [config] }); api.importDetail.mockResolvedValue(batch()); api.create.mockResolvedValue([]) })

it('calculates each independent source with schedule packing, retaining individual tail rounding', () => {
  const lines = config.data.lines!.map(line => ({ ...line, usage_quantity: null }))
  expect(batchPaperPreview(source, lines)[0]!.actual).toBe(807)
  expect(batchPaperPreview(selection[1]!.source, lines)[0]!.actual).toBe(98)
  expect(batchPaperPreview({ ...source, quantity: 7 }, lines)[0]!.actual).toBe(2)
  expect(schedulePacking({ ...source, carton_rule: '0/6' })).toEqual({ 外箱: 6 })
  expect(schedulePacking({ ...source, carton_rule: '12/6' })).toBeNull()
  expect(batchPaperError({ ...source, carton_rule: '3/6' }, lines)).toContain('内外箱')
  expect(batchPaperError(source, [...lines, ...lines])).toContain('内外箱')
})

it('matches factory shared item configurations but never combines different customers or items', () => {
  expect(scheduleBatchConfigurations([config], source)).toEqual([config])
  expect(sameScheduleItem(source, { ...source, customer_code: 'C2' })).toBe(false)
  expect(sameScheduleItem(source, { ...source, item_no: '57521' })).toBe(false)
  expect(batchSourceError({ ...source, manual_ordered: true })).toContain('已下单')
  expect(batchSourceError({ ...source, date_review_required: true })).toContain('核对')
  expect(batchSourceError({ ...source, customer_due_date: '' })).toContain('交期')
  expect(emptyBatchPapers([{ batchId: 'B1', source: { ...source, carton_rule: '3/6' } }]).map(line => line.packaging_type)).toEqual(['内箱', '外箱'])
})

it('automatically carries config, readonly source quantities and separate dates, submits one command', async () => {
  const wrapper = render(); await flushPromises()
  expect(wrapper.text()).toContain('807 个'); expect(wrapper.text()).toContain('98 个')
  expect(wrapper.text()).toContain('2026-12-01'); expect(wrapper.text()).toContain('2026-12-03')
  expect(wrapper.findAll('input[type="date"]')).toHaveLength(1)
  await wrapper.get('[aria-label="批量下单计划交期"]').setValue('2026-11-25')
  await wrapper.get('form').trigger('submit'); await flushPromises()
  const body = api.create.mock.calls[0]![0]
  expect(body.sources).toHaveLength(2); expect(body.master_config_revision).toBe(3)
  expect(body.lines[0]).toMatchObject({ paper_quality: 'A33', specification: '40*30*20', usage_quantity: null })
  expect(body.supplier_id).toBeUndefined(); expect(body.customer_due_date).toBeUndefined()
  expect(wrapper.emitted('saved')).toHaveLength(1)
  wrapper.unmount()
})

it('shows actual customer PO separately from SO and keeps a blank PO blank', async () => {
  const selected = selection.map((entry, index) => ({ ...entry, source: { ...entry.source, customer_po: index ? '' : '0004685' } }))
  api.importDetail.mockResolvedValue({ ...batch(), parse_summary: { ...batch().parse_summary, rows: selected.map(entry => entry.source) } })
  const wrapper = render({ selection: selected }); await flushPromises()
  expect(wrapper.text()).toContain('客户 PO：0004685')
  expect(wrapper.text()).toContain('客户 PO：未填')
  expect(wrapper.text()).toContain('业务 SO：SO-1')
  expect(wrapper.text()).not.toContain('客户 PO：SO-1')
  wrapper.unmount()
})

it('asks for a configuration when the same item has multiple specifications', async () => {
  api.get.mockResolvedValue({ records: [config, { ...config, id: 'M2', revision: 4 }] })
  const wrapper = render(); await flushPromises()
  await wrapper.get('[aria-label="批量下单计划交期"]').setValue('2026-11-25')
  await wrapper.get('form').trigger('submit'); await flushPromises()
  expect(api.create).not.toHaveBeenCalled(); expect(wrapper.text()).toContain('请选择本次使用的一套')
  await wrapper.get('[aria-label="批量下单纸箱配置"]').setValue('M2')
  await wrapper.get('form').trigger('submit'); await flushPromises()
  expect(api.create.mock.calls[0]![0].master_config_id).toBe('M2')
  wrapper.unmount()
})

it('fills missing common material and dimensions once for both sources', async () => {
  api.get.mockResolvedValue({ records: [] })
  const wrapper = render({ defaultDimension: 'inch' }); await flushPromises()
  await wrapper.get('[aria-label="纸质 1"]').setValue('A33')
  await wrapper.get('[aria-label="规格 1"]').setValue('20*12*10')
  await wrapper.get('[aria-label="批量下单计划交期"]').setValue('2026-11-25')
  await wrapper.get('form').trigger('submit'); await flushPromises()
  expect(api.create.mock.calls[0]![0]).toMatchObject({ master_config_id: '', lines: [{ paper_quality: 'A33', specification: '20*12*10', dimension_unit: 'in' }] })
  wrapper.unmount()
})

it('keeps exact uncertain request across close and reopen even if source quantities change', async () => {
  api.create.mockRejectedValueOnce(new Error('网络中断')).mockResolvedValueOnce([])
  const wrapper = render(); await flushPromises()
  await wrapper.get('[aria-label="批量下单计划交期"]').setValue('2026-11-25')
  await wrapper.get('form').trigger('submit'); await flushPromises()
  const original = JSON.parse(JSON.stringify(api.create.mock.calls[0]![0]))
  await wrapper.setProps({ open: false }); await flushPromises()
  api.importDetail.mockResolvedValue(batch(selection.map(row => ({ ...row, source: { ...row.source, quantity: 99, order_no: 'NEW-ORDER' } }))))
  await wrapper.setProps({ open: true, selection: [], viewerKey: 'actor-auth2' }); await flushPromises()
  expect(wrapper.text()).toContain('807 个'); expect(wrapper.text()).toContain('核对原提交结果')
  await wrapper.get('form').trigger('submit'); await flushPromises()
  expect(api.create.mock.calls[1]![0]).toEqual(original); expect(pendingScheduleBatches.size).toBe(0)
  wrapper.unmount()
})

it('refreshes source quantities before a new submission instead of using stale selection', async () => {
  api.importDetail.mockResolvedValue(batch(selection.map(row => ({ ...row, source: { ...row.source, quantity: 600 } }))))
  const wrapper = render(); await flushPromises()
  expect(wrapper.text()).toContain('100 个'); expect(wrapper.text()).not.toContain('807 个')
  wrapper.unmount()
})

it('hides old drafts and ignores late loads when factory changes', async () => {
  let resolve!: (value: unknown) => void
  api.get.mockImplementationOnce(() => new Promise(r => { resolve = r }))
  const wrapper = render()
  await wrapper.setProps({ factoryId: 'huakang-a', selection: [] }); await flushPromises()
  resolve({ records: [config] }); await flushPromises()
  expect(wrapper.text()).not.toContain('53607'); expect(api.create).not.toHaveBeenCalled()
  wrapper.unmount()
})

it('does not expose a retained uncertain preview after source permission is revoked', async () => {
  api.create.mockRejectedValueOnce(new Error('网络中断'))
  const wrapper = render(); await flushPromises()
  await wrapper.get('[aria-label="批量下单计划交期"]').setValue('2026-11-25')
  await wrapper.get('form').trigger('submit'); await flushPromises()
  await wrapper.setProps({ open: false }); await flushPromises()
  api.importDetail.mockResolvedValue(batch(selection.map(row => ({ ...row, source: { ...row.source, can_operate_source: false } }))))
  await wrapper.setProps({ open: true, viewerKey: 'actor-auth2' }); await flushPromises()
  expect(wrapper.text()).not.toContain('53607'); expect(wrapper.text()).toContain('部分来源不可访问')
  expect(pendingScheduleBatches.size).toBe(1)
  wrapper.unmount()
})

it('supports accessory rules and exact per-order quantities and weights without changing other orders', async () => {
  const wrapper = render(); await flushPromises()
  await wrapper.get('[aria-label="纸品每箱净重 1"]').setValue('1')
  await wrapper.get('[aria-label="纸品每箱毛重 1"]').setValue('2')
  await wrapper.findAll('button').find(button => button.text() === '新增纸品明细')!.trigger('click')
  await wrapper.get('[aria-label="纸品类型 2"]').setValue('平卡')
  await wrapper.get('[aria-label="纸质 2"]').setValue('A33')
  await wrapper.get('[aria-label="规格 2"]').setValue('20*10')
  await wrapper.get('[aria-label="每箱配套用量 2"]').setValue('2')
  await wrapper.get('[aria-label="调整本单数量重量 53607"]').trigger('click')
  const first = wrapper.get('[aria-label="本单纸品 53607"]')
  expect(wrapper.find('[aria-label="纸品每箱净重 2"]').exists()).toBe(false)
  expect(wrapper.find('[aria-label="纸品每箱毛重 2"]').exists()).toBe(false)
  expect(first.find('[aria-label="单独填写重量 53607 2"]').exists()).toBe(false)
  await first.get('[aria-label="纸箱数量 1"]').setValue('810')
  expect(first.text()).toContain('自动参考：807')
  expect(wrapper.text()).toContain('1620 个')
  await first.get('[aria-label="单独填写重量 53607 1"]').setValue(true)
  await first.get('[aria-label="53607每箱净重 1"]').setValue('3')
  await first.get('[aria-label="53607每箱毛重 1"]').setValue('4')
  await wrapper.get('[aria-label="批量下单加急"]').setValue(true)
  await wrapper.get('[aria-label="订单备注"]').setValue('两个合同分别包装')
  await wrapper.get('[aria-label="批量下单计划交期"]').setValue('2026-11-25')
  await wrapper.get('form').trigger('submit'); await flushPromises()
  expect(api.create.mock.calls[0]![0]).toMatchObject({ rush: true, rush_reason: '', note: '两个合同分别包装',
    order_overrides: [{ source_row: 2, lines: [{ line_no: 1, manual_quantity: 810, net_weight_kg: 3, gross_weight_kg: 4 }] }] })
  expect(api.create.mock.calls[0]![0].lines[1].quantity_rule).toMatchObject({ mode: 'PER_CARTON', carton_line_no: 1, per_carton_quantity: '2' })
  wrapper.unmount()
})

it('restores automatic quantities and repairs accessory references after deleting a paper', async () => {
  const wrapper = render(); await flushPromises()
  await wrapper.get('[aria-label="调整本单数量重量 53607"]').trigger('click')
  const first = wrapper.get('[aria-label="本单纸品 53607"]')
  await first.get('[aria-label="纸箱数量 1"]').setValue('900')
  await first.findAll('button').find(button => button.text() === '恢复自动')!.trigger('click')
  expect((first.get('[aria-label="纸箱数量 1"]').element as HTMLInputElement).value).toBe('807')
  await wrapper.findAll('button').find(button => button.text() === '新增纸品明细')!.trigger('click')
  await wrapper.get('[aria-label="删除纸品明细 1"]').trigger('click')
  expect((wrapper.get('[aria-label="对应纸箱 1"]').element as HTMLSelectElement).value).toBe('')
  await wrapper.get('[aria-label="批量下单计划交期"]').setValue('2026-11-25')
  await wrapper.get('form').trigger('submit'); await flushPromises()
  expect(api.create).not.toHaveBeenCalled()
  wrapper.unmount()
})

it('persists partially completed fields across remount and isolates actor, epoch and factory', async () => {
  api.get.mockResolvedValue({ records: [] })
  const wrapper = render(); await flushPromises()
  await wrapper.get('[aria-label="纸质 1"]').setValue('B33')
  await wrapper.get('[aria-label="订单备注"]').setValue('还没填完规格')
  wrapper.unmount(); pendingScheduleBatches.clear()
  const saved = readScheduleBatchDraft(window.localStorage, 'actor', 'huaxing')
  expect(saved?.papers[0]?.paper_quality).toBe('B33')
  expect(readScheduleBatchDraft(window.localStorage, 'actor-new-epoch', 'huaxing')).toBeNull()
  expect(readScheduleBatchDraft(window.localStorage, 'actor', 'huakang-a')).toBeNull()
  const restored = render({ selection: [] }); await flushPromises()
  expect(restored.text()).toContain('已恢复本机未完成草稿')
  expect((restored.get('[aria-label="订单备注"]').element as HTMLTextAreaElement).value).toBe('还没填完规格')
  expect((restored.get('[aria-label="纸质 1"]').element as HTMLInputElement).value).toBe('B33')
  restored.unmount()
})

it('warns when source PO changed while restoring an unsubmitted draft', async () => {
  let wrapper = render(); await flushPromises()
  await wrapper.get('[aria-label="订单备注"]').setValue('未提交的排期草稿')
  wrapper.unmount(); pendingScheduleBatches.clear()
  const updated = batch()
  updated.parse_summary.rows![0]!.customer_po = '0004685'
  api.importDetail.mockResolvedValue(updated)
  wrapper = render({ selection: [] }); await flushPromises()
  expect(wrapper.text()).toContain('0004685')
  expect(wrapper.text()).toContain('来源的合同、SO、客户 PO、数量、装箱或交期已有变化')
  wrapper.unmount()
})

it('restores the exact uncertain command from persistent storage after a simulated browser reload', async () => {
  api.create.mockRejectedValueOnce(new Error('timeout')).mockRejectedValueOnce({ isAxiosError: true, response: { status: 403 }, message: 'permission changed' }).mockResolvedValueOnce([])
  let wrapper = render(); await flushPromises()
  await wrapper.get('[aria-label="批量下单计划交期"]').setValue('2026-11-25')
  await wrapper.get('form').trigger('submit'); await flushPromises()
  const body = JSON.parse(JSON.stringify(api.create.mock.calls[0]![0]))
  wrapper.unmount(); pendingScheduleBatches.clear()
  const interrupted = readScheduleBatchDraft(window.localStorage, 'actor', 'huaxing')!
  interrupted.attempt!.uncertain = false
  writeScheduleBatchDraft(window.localStorage, 'actor', 'huaxing', interrupted)
  wrapper = render({ selection: [] }); await flushPromises()
  expect(wrapper.findAll('button').some(button => button.text() === '清空批量草稿')).toBe(false)
  await wrapper.get('form').trigger('submit'); await flushPromises()
  expect(api.create.mock.calls[1]![0]).toEqual(body)
  expect(wrapper.findAll('button').some(button => button.text() === '清空批量草稿')).toBe(false)
  expect(readScheduleBatchDraft(window.localStorage, 'actor', 'huaxing')?.attempt).toBeDefined()
  await wrapper.get('form').trigger('submit'); await flushPromises()
  expect(api.create.mock.calls[2]![0]).toEqual(body)
  expect(readScheduleBatchDraft(window.localStorage, 'actor', 'huaxing')).toBeNull()
  wrapper.unmount()
})

it('checks current customer responsibility before revealing persisted source information', async () => {
  let wrapper = render(); await flushPromises(); wrapper.unmount()
  api.responsibilities.mockResolvedValue({ unrestricted: false, own_customer_codes: [] })
  wrapper = render({ selection: [] }); await flushPromises()
  expect(wrapper.text()).not.toContain('53607'); expect(wrapper.text()).not.toContain('BUZZ BEE')
  expect(wrapper.text()).toContain('无权办理')
  await wrapper.findAll('button').find(button => button.text() === '清空不可用草稿')!.trigger('click')
  await wrapper.findAll('button').find(button => button.text() === '确认清空草稿')!.trigger('click')
  expect(readScheduleBatchDraft(window.localStorage, 'actor', 'huaxing')).toBeNull()
  wrapper.unmount()
})

it('submits an explicit packing rule for a legacy non-carton master line without changing its demand', async () => {
  api.get.mockResolvedValue({ records: [{ ...config, data: { lines: [config.data.lines![0], {
    ...config.data.lines![0], packaging_type: '自定义卡', usage_quantity: 3, quantity_rule: null,
    net_weight_kg: 1, gross_weight_kg: 2,
  }] } }] })
  const wrapper = render(); await flushPromises()
  expect(wrapper.text()).toContain('自定义卡：1614 个')
  await wrapper.get('[aria-label="批量下单计划交期"]').setValue('2026-11-25')
  await wrapper.get('form').trigger('submit'); await flushPromises()
  expect(api.create.mock.calls[0]![0].lines[1]).toMatchObject({ usage_quantity: 3, quantity_rule: { mode: 'PACKING' }, net_weight_kg: 1, gross_weight_kg: 2 })
  wrapper.unmount()
})

it('clears a rejected weight message as the operator corrects the form', async () => {
  const wrapper = render(); await flushPromises()
  await wrapper.get('[aria-label="批量下单计划交期"]').setValue('2026-11-25')
  await wrapper.get('[aria-label="纸品每箱净重 1"]').setValue('2')
  await wrapper.get('[aria-label="纸品每箱毛重 1"]').setValue('1')
  await wrapper.get('form').trigger('submit'); await flushPromises()
  expect(api.create).not.toHaveBeenCalled()
  expect(wrapper.get('[role="alert"]').text()).toContain('毛重不能小于净重')
  await wrapper.get('[aria-label="纸品每箱毛重 1"]').setValue('3')
  expect(wrapper.find('[role="alert"]').exists()).toBe(false)
  await wrapper.get('form').trigger('submit'); await flushPromises()
  expect(api.create.mock.calls[0]![0].lines[0]).toMatchObject({ net_weight_kg: 2, gross_weight_kg: 3 })
  wrapper.unmount()
})

it('validates common and per-order weights and treats explicit null as unknown', () => {
  const paper = { ...config.data.lines![0]!, usage_quantity: null, net_weight_kg: 1, gross_weight_kg: 2 }
  expect(effectiveBatchWeights(paper, { line_no: 1, net_weight_kg: null })).toEqual({ net_weight_kg: null, gross_weight_kg: 2 })
  expect(batchWeightError({ net_weight_kg: 3, gross_weight_kg: 2 })).toContain('不能小于')
  expect(batchWeightError({ net_weight_kg: 0.12345 })).toContain('四位')
  expect(batchPaperPreview(source, [paper, { ...paper, packaging_type: '自定义卡', usage_quantity: 3 }])[1]!.actual).toBe(1614)
  expect(batchPaperError(source, [paper, { ...paper, packaging_type: '自定义卡', usage_quantity: 3 }])).toBe('')
})
