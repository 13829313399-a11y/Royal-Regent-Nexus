import { flushPromises, mount, type DOMWrapper } from '@vue/test-utils'
import { reactive } from 'vue'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import type { BoardOrder, Data, MaterialRecord } from '@/api/indonesiaMaterials'
import IndonesiaMaterialsView from '@/views/IndonesiaMaterialsView.vue'
import { materialDefaults, orderDefaults, productDefaults, supplyDefaults } from '../forms'
import { memoryDatabase, savedBuckets } from './draftMemory'
vi.mock('../draftPersistence', async importOriginal => {
  const original = await importOriginal<typeof import('../draftPersistence')>()
  const { memoryDatabase } = await import('./draftMemory')
  return { ...original, createDraftPersistence: () => original.createDraftPersistence(memoryDatabase) }
})

const mocks = vi.hoisted(() => ({
  app: {} as Data, auth: {} as Data,
  api: { workspace: vi.fn(), command: vi.fn(), preview: vi.fn(), download: vi.fn() },
}))
vi.mock('@/stores/app', () => ({ useAppStore: () => mocks.app }))
vi.mock('@/stores/auth', () => ({ useAuthStore: () => mocks.auth }))
vi.mock('@/api/indonesiaMaterials', () => ({ indonesiaMaterialsApi: mocks.api }))
vi.mock('@/lib/http', () => ({ getApiErrorMessage: (cause: Error) => cause.message }))
vi.mock('@/features/indonesia-materials/MaterialsHeader.vue', () => ({ default: { template: '<header><slot /></header>' } }))

function record(id: string, kind: MaterialRecord['kind'], data: Data): MaterialRecord { return { id, kind, version: 3, data } }
const mainOrder = { ...orderDefaults, customer: 'CLIENT', recipient: 'RRI', contract_no: 'C-1', po_no: '', item_no: 'ITEM', batch: 'B-1', quantity: '10', unit: 'PCS', delivery_date: '2026-11-30' }
const material = record('m', 'material', { ...materialDefaults, code: 'SCREW', name: '螺丝', unit: 'PCS', net_weight_kg: '0.002', billing_weight_kg: '0.003', price: '4', procurement_days: 15 })
function fixture() {
  const records = [
    record('client', 'customer', { name: 'CLIENT', status: 'active', notes: '' }),
    material, record('p', 'product', { ...productDefaults, code: 'ITEM', customer: 'CLIENT', daily_capacity: '100', materials: [{ material_id: 'm', usage: '4' }] }),
    record('o', 'order', mainOrder), record('o2', 'order', { ...mainOrder, contract_no: 'C-2' }), record('o-rrm', 'order', { ...mainOrder, recipient: 'RRM' }), record('o-other', 'order', { ...mainOrder, customer: 'OTHER' }),
    record('s', 'supply', { ...supplyDefaults, material_id: 'm', purchase_no: 'P-1', purchase_line: '1', purchase_date: '2026-10-13', supplier: 'Supplier', batch: 'S-1', purchase_quantity: '100', normal_quantity: '95', spare_quantity: '5', status: 'received', actual_date: '2026-10-13', material_snapshot: material }),
    record('s-expected', 'supply', { ...supplyDefaults, material_id: 'm', purchase_no: 'P-2', batch: 'EXPECTED', normal_quantity: '10', spare_quantity: '0', status: 'expected' }),
    record('a', 'allocation', { order_id: 'o', demand_id: 'd', supply_id: 's', normal_quantity: '20', spare_quantity: '1', shipped_normal: '0', shipped_spare: '0' }),
    record('a-rrm', 'allocation', { order_id: 'o-rrm', demand_id: 'd-rrm', supply_id: 's', normal_quantity: '20', spare_quantity: '0' }),
    record('a-other', 'allocation', { order_id: 'o-other', demand_id: 'd-other', supply_id: 's', normal_quantity: '20', spare_quantity: '0' }),
    record('a-expected', 'allocation', { order_id: 'o', demand_id: 'd', supply_id: 's-expected', normal_quantity: '10', spare_quantity: '0' }),
  ]
  const board: BoardOrder[] = [{
    id: 'o', ...mainOrder, status: 'shortage', planning_status: 'ready',
    plan: { production_days: 1, start_date: '2026-11-27', dispatch_date: '2026-11-02', required_date: '2026-11-02', transport_days: 25, preparation_days: 0 },
    demands: [{ id: 'd', material_id: 'm', code: 'SCREW', name: '螺丝', unit: 'PCS', computed_quantity: '40', quantity: '40', procurement_days: 15, purchase_start: '2026-10-18', coverage: '21', shortage: '19', allocated: '31', shipped: '0', promised_date: null, risk: 'awaiting_reply' }],
  }]
  board.push({ ...board[0]!, id: 'o2', contract_no: 'C-2', demands: [{ ...board[0]!.demands[0]!, id: 'd2' }] })
  return { records: structuredClone(records), board, permissions: ['read', 'write', 'receipt_confirm', 'export'] }
}
const packageData = { label: '整箱', cartons: 1, length_cm: '27', width_cm: '14.5', height_cm: '27.3', carton_weight_kg: '0.1', pallet: 'PALLET-1', items: [{ allocation_id: 'a', normal_quantity: '9', spare_quantity: '1' }] }
function shipment(status = 'draft') {
  return record('shipment', 'shipment', { customer: 'CLIENT', recipient: 'RRI', shipment_date: '2026-10-13', lines: [{ allocation_id: 'a', normal_quantity: '9', spare_quantity: '1' }], packages: [packageData], remarks: '', status })
}
let data = fixture()
const wrappers: ReturnType<typeof mount<typeof IndonesiaMaterialsView>>[] = []
async function setup(masterCategory: 'material' | 'customer' = 'material') {
  const wrapper = mount(IndonesiaMaterialsView, { global: { stubs: { MaterialsHeader: { template: '<header><slot /></header>' } } } })
  wrappers.push(wrapper)
  await flushPromises()
  if (masterCategory === 'material' && wrapper.find('#im-panel-master').exists()) await button(wrapper.get('#im-panel-master'), '物料资料').trigger('click')
  return wrapper
}
function button(scope: { findAll: (selector: string) => DOMWrapper<Element>[] }, text: string) {
  const found = scope.findAll('button').find(item => item.text() === text)
  if (!found) throw new Error(`Missing button: ${text}`)
  return found
}
function field(scope: { findAll: (selector: string) => DOMWrapper<Element>[] }, text: string) {
  const label = scope.findAll('label').find(item => item.get('span').text().replace(/\s*\*$/, '') === text)
  if (!label) throw new Error(`Missing field: ${text}`)
  return label.get('input, select, textarea')
}
beforeEach(() => {
  savedBuckets.clear()
  vi.resetAllMocks()
  vi.spyOn(window, 'confirm').mockReturnValue(true)
  mocks.app = reactive({ activeFactoryId: 'huaxing' })
  mocks.auth = reactive({ currentUser: { id: 'user' }, authorizationVersion: 1, permissions: [], grants: [], effectiveAccess: [] })
  data = fixture()
  mocks.api.workspace.mockImplementation(async () => data)
  mocks.api.command.mockResolvedValue({ record: material })
})
afterEach(() => { wrappers.splice(0).forEach(wrapper => wrapper.unmount()); vi.restoreAllMocks() })

describe('materials business forms', () => {
  it('opens the fixed-customer library first and submits only the customer master fields', async () => {
    const panel = (await setup('customer')).get('#im-panel-master')
    expect(panel.text()).toContain('当前厂区')
    expect(panel.text()).toContain('CLIENT')
    await button(panel, '新增固定客人').trigger('click')
    await field(panel, '固定客人名称').setValue('NEW CLIENT')
    await field(panel, '备注').setValue('只维护本厂区送印尼客人')
    await panel.get('form').trigger('submit'); await flushPromises()
    expect(mocks.api.command.mock.calls[0]![0]).toMatchObject({ factory_id: 'huaxing', action: 'customer_save', entity_id: null, data: { name: 'NEW CLIENT', status: 'active', notes: '只维护本厂区送印尼客人' } })
  })

  it('opens the selected customer’s products and preselects that customer for a new product', async () => {
    const panel = (await setup('customer')).get('#im-panel-master')
    await button(panel, '维护客人货号').trigger('click')
    expect((field(panel, '筛选固定客人').element as HTMLSelectElement).value).toBe('CLIENT')
    await button(panel, '新增货号').trigger('click')
    expect((field(panel, '客户').element as HTMLSelectElement).value).toBe('CLIENT')
    expect(panel.text()).toContain('每件成品物料用量')
  })

  it('restricts contract product choices by customer and clears a stale product when customer changes', async () => {
    data.records.push(record('other-client', 'customer', { name: 'OTHER', status: 'active' }))
    data.records.push(record('other-product', 'product', { ...productDefaults, code: 'OTHER-ITEM', customer: 'OTHER', unit: 'SET', materials: [{ material_id: 'm', usage: '2' }] }))
    const panel = (await setup()).get('#im-panel-demand')
    await button(panel, '新增合同交付批次').trigger('click')
    await field(panel, '客户').setValue('CLIENT')
    expect(field(panel, '成品货号').text()).not.toContain('OTHER-ITEM')
    await field(panel, '成品货号').setValue('ITEM')
    expect(panel.text()).toContain('每件 4 PCS')
    await field(panel, '客户').setValue('OTHER')
    expect((field(panel, '成品货号').element as HTMLSelectElement).value).toBe('')
    expect(field(panel, '成品货号').text()).toContain('OTHER-ITEM')
    await field(panel, '成品货号').setValue('OTHER-ITEM')
    expect((field(panel, '成品单位').element as HTMLInputElement).value).toBe('SET')
    expect((field(panel, '印尼接收方').element as HTMLSelectElement).value).toBe('RRI')
  })

  it('keeps an empty catalog actionable but disables new imports and protects read-only customer maintenance', async () => {
    data.records = data.records.filter(row => row.kind !== 'customer')
    data.permissions = ['read']
    const wrapper = await setup('customer')
    const panel = wrapper.get('#im-panel-master')
    expect(panel.text()).toContain('先维护本厂区的固定客人')
    expect(button(panel, '新增固定客人').attributes('disabled')).toBeDefined()
    const importPanel = wrapper.get('#im-panel-import')
    expect(field(importPanel, '客户').findAll('option')).toHaveLength(1)
    expect(button(importPanel, '上传并预览').attributes('disabled')).toBeDefined()
  })
  it('saves separate net and billing weights without server-only state', async () => {
    const wrapper = await setup()
    const panel = wrapper.get('#im-panel-master')
    await button(panel, '编辑').trigger('click')
    await field(panel, '单个净重（kg）').setValue('0.005')
    await field(panel, '单件计费重量（kg）').setValue('0.009')
    await panel.get('form').trigger('submit')
    await flushPromises()
    expect(mocks.api.command.mock.calls[0]![0]).toMatchObject({ action: 'material_save', entity_id: 'm', expected_version: 3, data: { net_weight_kg: '0.005', billing_weight_kg: '0.009' } })
    expect(mocks.api.command.mock.calls[0]![0].data).not.toHaveProperty('status')
  })

  it.each(['45', '999999999.12345678'])('saves exact decimal demand %s using the order revision', async quantity => {
    const wrapper = await setup()
    const panel = wrapper.get('#im-panel-demand')
    await button(panel, '调整需求').trigger('click')
    await field(panel, '调整后的最终需求量').setValue(quantity)
    await field(panel, '业务原因').setValue('新增损耗')
    await panel.get('form').trigger('submit')
    await flushPromises()
    expect(mocks.api.command.mock.calls[0]![0]).toMatchObject({ action: 'demand_adjust', entity_id: 'o', expected_version: 3, data: { demand_id: 'd', quantity, reason: '新增损耗' } })
  })

  it('saves the product recipe with its exact usage and explicit 25-day transport parameter', async () => {
    const panel = (await setup()).get('#im-panel-master')
    await button(panel, '货号与单件用量').trigger('click')
    await button(panel, '编辑').trigger('click')
    await panel.get('input[aria-label="单件用量"]').setValue('4.12345678')
    await field(panel, '日产能').setValue('5000')
    await panel.get('form').trigger('submit'); await flushPromises()
    expect(mocks.api.command.mock.calls[0]![0]).toMatchObject({ action: 'product_save', entity_id: 'p', expected_version: 3, data: { code: 'ITEM', customer: 'CLIENT', daily_capacity: '5000', transport_days: 25, materials: [{ material_id: 'm', usage: '4.12345678' }] } })
  })

  it('preserves order identity while sending explicit quantity, date and amendment reason', async () => {
    const panel = (await setup()).get('#im-panel-demand')
    await button(panel, '编辑批次').trigger('click')
    expect(field(panel, '客户').attributes('disabled')).toBeDefined()
    expect(field(panel, '印尼接收方').attributes('disabled')).toBeDefined()
    await field(panel, '本批成品数量').setValue('12')
    await field(panel, '变更原因（修改时填写）').setValue('客户增加数量')
    await panel.get('form').trigger('submit'); await flushPromises()
    expect(mocks.api.command.mock.calls[0]![0]).toMatchObject({ action: 'order_save', entity_id: 'o', data: { customer: 'CLIENT', recipient: 'RRI', contract_no: 'C-1', batch: 'B-1', quantity: '12', reason: '客户增加数量' } })
  })

  it('recalculates only after an explicit reason without passing client demand snapshots', async () => {
    const panel = (await setup()).get('#im-panel-demand')
    await button(panel, '重新生成需求').trigger('click')
    await field(panel, '业务原因').setValue('核对新用量')
    await panel.get('form').trigger('submit'); await flushPromises()
    expect(mocks.api.command.mock.calls[0]![0]).toMatchObject({ action: 'order_recalculate', entity_id: 'o', expected_version: 3, data: { reason: '核对新用量' } })
  })

  it('binds the selected demand and supply with separate decimal normal and spare quantities', async () => {
    const panel = (await setup()).get('#im-panel-demand')
    await button(panel, '分配供应').trigger('click')
    await field(panel, '同物料采购／回料来源').setValue('s')
    await field(panel, '分配正常量').setValue('5.00000001')
    await field(panel, '分配备品量').setValue('1')
    await panel.get('form').trigger('submit'); await flushPromises()
    expect(mocks.api.command.mock.calls[0]![0]).toMatchObject({ action: 'allocate', entity_id: null, expected_version: 0, data: { order_id: 'o', demand_id: 'd', supply_id: 's', normal_quantity: '5.00000001', spare_quantity: '1' } })
  })

  it('rebinds only the entered unshipped normal and spare amounts with the original allocation revision', async () => {
    const panel = (await setup()).get('#im-panel-demand')
    await button(panel, '未发改绑').trigger('click')
    await field(panel, '目标合同交付批次').setValue('o2')
    await field(panel, '目标物料需求').setValue('d2')
    await field(panel, '转走正常量').setValue('3')
    await field(panel, '转走备品量').setValue('1')
    await field(panel, '业务原因').setValue('改供另一合同')
    await panel.get('form').trigger('submit'); await flushPromises()
    expect(mocks.api.command.mock.calls[0]![0]).toMatchObject({ action: 'reallocate', entity_id: 'a', expected_version: 3, data: { order_id: 'o2', demand_id: 'd2', normal_quantity: '3', spare_quantity: '1', reason: '改供另一合同' } })
  })

  it('registers a purchase batch without submitting receipt state or material snapshots', async () => {
    const panel = (await setup()).get('#im-panel-supply')
    await button(panel, '登记采购／回料批次').trigger('click')
    await field(panel, '物料').setValue('m')
    for (const [label, value] of [['采购单号', 'P-NEW'], ['采购行号', '1'], ['采购日期', '2026-10-13'], ['供应商', 'Supplier'], ['采购总量', '100'], ['正常量', '95'], ['免费备品量', '5'], ['回料批次', 'NEW']]) {
      await field(panel, label!).setValue(value!)
    }
    await panel.get('form').trigger('submit'); await flushPromises()
    const command = mocks.api.command.mock.calls[0]![0]
    expect(command).toMatchObject({ action: 'supply_save', entity_id: null, data: { material_id: 'm', purchase_no: 'P-NEW', normal_quantity: '95', spare_quantity: '5', promised_date: null, price: '4' } })
    expect(command.data).not.toHaveProperty('status')
    expect(command.data).not.toHaveProperty('material_snapshot')
  })

  it('records a supplier reply independently from the received quantities', async () => {
    const panel = (await setup()).get('#im-panel-supply')
    await button(panel, '更新回复').trigger('click')
    await field(panel, '供应商回复回料日期').setValue('2026-10-20')
    await field(panel, '回复来源／变更原因').setValue('来料仓提供回复')
    await panel.get('form').trigger('submit'); await flushPromises()
    expect(mocks.api.command.mock.calls[0]![0]).toMatchObject({ action: 'supply_reply', entity_id: 's', expected_version: 3, data: { promised_date: '2026-10-20', reason: '来料仓提供回复' } })
  })

  it('requires an explicit reason to refresh output descriptions without submitting weights or quantities', async () => {
    const panel = (await setup()).get('#im-panel-supply')
    await button(panel, '补全出货资料').trigger('click')
    await field(panel, '资料补全原因').setValue('基础资料补齐英文名和照片')
    await panel.get('form').trigger('submit'); await flushPromises()
    expect(mocks.api.command.mock.calls[0]![0]).toMatchObject({ action: 'output_material_refresh', entity_id: 's', expected_version: 3, data: { reason: '基础资料补齐英文名和照片' } })
    expect(Object.keys(mocks.api.command.mock.calls[0]![0].data)).toEqual(['reason'])
  })

  it('displays promised and actual receipt dates together with the server risk', async () => {
    Object.assign(data.board[0]!.demands[0]!, { promised_date: '2026-10-20', actual_date: '2026-10-22', risk: 'late_received' })
    const panel = (await setup()).get('#im-panel-board')
    await button(panel, '明细 ↓').trigger('click')
    expect(panel.text()).toContain('2026-10-20')
    expect(panel.text()).toContain('2026-10-22')
    expect(panel.text()).toContain('已回料，实际晚于要求')
  })

  it('offers receipt confirmation to shipping staff while business writes stay disabled', async () => {
    data.permissions = ['read', 'receipt_confirm']
    const wrapper = await setup()
    const panel = wrapper.get('#im-panel-supply')
    expect(button(panel, '登记采购／回料批次').attributes('disabled')).toBeDefined()
    await button(panel, '船务确认入库').trigger('click')
    await field(panel, '实际回河源日期').setValue('2026-10-13')
    await panel.get('form').trigger('submit')
    await flushPromises()
    expect(mocks.api.command.mock.calls[0]![0]).toMatchObject({ action: 'receipt_confirm', entity_id: 's-expected', data: { actual_date: '2026-10-13' } })
  })

  it('clears open private forms on factory change and supports keyboard tab navigation', async () => {
    const wrapper = await setup()
    await button(wrapper.get('#im-panel-master'), '新增物料').trigger('click')
    await field(wrapper.get('#im-panel-master'), '物料名称').setValue('上一厂区私有草稿')
    await wrapper.get('#im-tab-board').trigger('keydown', { key: 'ArrowRight' })
    expect(wrapper.get('#im-tab-import').attributes('aria-selected')).toBe('true')
    expect(wrapper.get('#im-tab-board').attributes('tabindex')).toBe('-1')
    mocks.app.activeFactoryId = 'huadeng'
    await flushPromises()
    expect(wrapper.get('#im-panel-master').find('form').exists()).toBe(false)
    expect(wrapper.text()).not.toContain('上一厂区私有草稿')
  })

  it('keeps the selected product editor and per-piece usage through an ordinary login refresh', async () => {
    mocks.auth.currentUser.identity = { employment_epoch: 1, identity_version: 1, effective_context_key: 'same', server_now: '2026-10-21T01:00:00Z' }
    const wrapper = await setup('customer')
    await wrapper.get('#im-tab-master').trigger('click')
    let panel = wrapper.get('#im-panel-master')
    await button(panel, '维护客人货号').trigger('click')
    await button(panel, '编辑').trigger('click')
    await panel.get('input[aria-label="单件用量"]').setValue('7')
    await field(panel, '日产能').setValue('5000')
    mocks.auth.currentUser = { ...mocks.auth.currentUser, identity: { ...mocks.auth.currentUser.identity, server_now: '2026-10-21T01:00:45Z' } }
    await flushPromises()
    panel = wrapper.get('#im-panel-master')
    expect(wrapper.get('#im-tab-master').attributes('aria-selected')).toBe('true')
    expect(panel.find('form').exists()).toBe(true)
    expect((panel.get('input[aria-label="单件用量"]').element as HTMLInputElement).value).toBe('7')
    expect((field(panel, '日产能').element as HTMLInputElement).value).toBe('5000')
    expect(mocks.api.command).not.toHaveBeenCalled()
    expect(mocks.api.workspace).toHaveBeenCalledTimes(1)
  })
})

describe('selected import rows', () => {
  const preview = () => record('import', 'import', { filename: 'schedule.xlsx', status: 'preview', asset_id: 'asset', rows: [
    { ...mainOrder, index: 7, source_sheet: 'Sheet1', source_row: 20, blocked: false, issues: [] },
    { ...mainOrder, index: 11, source_sheet: 'Sheet1', source_row: 24, blocked: true, issues: ['缺少货号'] },
  ] })
  async function upload(wrapper: Awaited<ReturnType<typeof setup>>) {
    const panel = wrapper.get('#im-panel-import')
    await field(panel, '客户').setValue('CLIENT')
    const input = panel.get('input[type="file"]')
    Object.defineProperty(input.element, 'files', { value: [new File(['xlsx'], 'schedule.xlsx')], configurable: true })
    await input.trigger('change')
    await panel.get('form').trigger('submit')
    await flushPromises()
    return panel
  }
  it('refreshes the open preview after master data changes and removes selections that are no longer eligible', async () => {
    const initial = preview()
    data.records.push(initial)
    mocks.api.preview.mockResolvedValue({ record: initial })
    const wrapper = await setup()
    const panel = await upload(wrapper)
    await panel.get('input[aria-label="选择来源行 20"]').setValue(true)
    expect(panel.get('input[aria-label="选择来源行 24"]').attributes('disabled')).toBeDefined()
    const refreshed = preview()
    refreshed.data.rows[0].blocked = true
    refreshed.data.rows[0].issues = ['客人已停用']
    refreshed.data.rows[1].blocked = false
    refreshed.data.rows[1].issues = []
    data = { ...data, records: data.records.map(row => row.id === initial.id ? refreshed : row) }
    await button(wrapper, '刷新工作区').trigger('click'); await flushPromises()
    expect(panel.get('input[aria-label="选择来源行 20"]').attributes('disabled')).toBeDefined()
    expect(panel.get('input[aria-label="选择来源行 24"]').attributes('disabled')).toBeUndefined()
    expect(button(panel, '确认导入选中 0 行').attributes('disabled')).toBeDefined()
    await panel.get('input[aria-label="选择来源行 24"]').setValue(true)
    await button(panel, '确认导入选中 1 行').trigger('click'); await flushPromises()
    expect(mocks.api.command.mock.calls[0]![0]).toMatchObject({ action: 'import_confirm', data: { indexes: [11] } })
  })
  it('disables blocked rows and sends authoritative indexes for the selected row', async () => {
    mocks.api.preview.mockResolvedValue({ record: preview() })
    const panel = await upload(await setup())
    expect(panel.get('input[aria-label="选择来源行 24"]').attributes('disabled')).toBeDefined()
    await panel.get('input[aria-label="选择来源行 20"]').setValue(true)
    await button(panel, '确认导入选中 1 行').trigger('click')
    await flushPromises()
    expect(mocks.api.command.mock.calls[0]![0]).toMatchObject({ action: 'import_confirm', entity_id: 'import', expected_version: 3, data: { indexes: [7] } })
  })
  it('shows the original confirmed record without another confirmation action', async () => {
    const confirmed = preview(); confirmed.data.status = 'confirmed'
    mocks.api.preview.mockResolvedValue({ record: confirmed })
    const panel = await upload(await setup())
    expect(panel.findAll('input[type="checkbox"]').every(input => input.attributes('disabled') !== undefined)).toBe(true)
    expect(panel.findAll('button').some(item => item.text().startsWith('确认导入'))).toBe(false)
    expect(mocks.api.command).not.toHaveBeenCalled()
  })
  it('allows remaining rows in a partial import and exposes changed values without enabling them', async () => {
    const partial = preview(); partial.data.status = 'partial'
    partial.data.rows[0].imported_order_id = 'existing-order'
    partial.data.rows.push({ ...mainOrder, index: 12, source_sheet: 'Sheet1', source_row: 25, blocked: true, match_status: 'changed', issues: ['请在合同中确认变更'], changes: [{ field: 'quantity', old: '10', new: '15' }] })
    partial.data.rows.push({ ...mainOrder, index: 13, source_sheet: 'Sheet1', source_row: 26, blocked: false, match_status: 'new', issues: [] })
    mocks.api.preview.mockResolvedValue({ record: partial })
    const panel = await upload(await setup())
    expect(panel.get('input[aria-label="选择来源行 20"]').attributes('disabled')).toBeDefined()
    expect(panel.get('input[aria-label="选择来源行 25"]').attributes('disabled')).toBeDefined()
    expect(panel.text()).toContain('数量：10 → 15')
    await panel.get('input[aria-label="选择来源行 26"]').setValue(true)
    await button(panel, '确认导入选中 1 行').trigger('click'); await flushPromises()
    expect(mocks.api.command.mock.calls[0]![0]).toMatchObject({ action: 'import_confirm', entity_id: 'import', data: { indexes: [13] } })
  })
})

describe('customer shipment packaging', () => {
  it('selects only the customer, recipient and received allocations, then saves typed package quantities', async () => {
    const panel = (await setup()).get('#im-panel-shipment')
    await button(panel, '新建出货草稿').trigger('click')
    await field(panel, '客户').setValue('CLIENT')
    await field(panel, '实际出货日期').setValue('2026-10-13')
    const checkboxes = panel.findAll('input[type="checkbox"]')
    expect(checkboxes).toHaveLength(1)
    await checkboxes[0]!.setValue(true)
    await panel.get('input[aria-label="本次正常量"]').setValue('9')
    await panel.get('input[aria-label="本次免费备品量"]').setValue('1')
    await button(panel, '添加包装组').trigger('click')
    for (const [label, value] of [['包装组名称／箱号', '整箱'], ['箱数', '1'], ['长（cm）', '27'], ['宽（cm）', '14.5'], ['高（cm）', '27.3'], ['每箱纸箱重量（kg）', '0.1'], ['卡板标记（不计重／体积）', 'PALLET-1']]) {
      await field(panel, label!).setValue(value!)
    }
    await button(panel, '添加箱内物料').trigger('click')
    await panel.get('select[aria-label="箱内出货物料"]').setValue('a')
    await panel.get('input[aria-label="组内正常量"]').setValue('9')
    await panel.get('input[aria-label="组内备品量"]').setValue('1')
    await panel.get('form').trigger('submit'); await flushPromises()
    const command = mocks.api.command.mock.calls[0]![0]
    expect(command).toMatchObject({ action: 'shipment_save', data: { customer: 'CLIENT', recipient: 'RRI', lines: [{ allocation_id: 'a', normal_quantity: '9', spare_quantity: '1' }], packages: [{ ...packageData, cartons: '1' }] } })
    expect(command.data.packages[0]).not.toHaveProperty('net_weight_kg')
    expect(mocks.api.download).not.toHaveBeenCalled()
  })

  it('clears selected shipment and package rows when the recipient changes', async () => {
    const panel = (await setup()).get('#im-panel-shipment')
    await button(panel, '新建出货草稿').trigger('click')
    await field(panel, '客户').setValue('CLIENT')
    await panel.get('input[type="checkbox"]').setValue(true)
    await button(panel, '添加包装组').trigger('click')
    await field(panel, '本次唯一接收方').setValue('RRM')
    expect(panel.find('input[aria-label="本次正常量"]').exists()).toBe(false)
    expect(panel.text()).not.toContain('包装组 1')
    expect(panel.findAll('input[type="checkbox"]')).toHaveLength(1)
  })

  it('shows real package facts before confirmation and keeps the draft after server validation fails', async () => {
    data.records.push(shipment())
    const wrapper = await setup(); const panel = wrapper.get('#im-panel-shipment')
    await button(panel, '核对并确认出货').trigger('click')
    expect(panel.text()).toContain('27 × 14.5 × 27.3')
    expect(panel.text()).toContain('PALLET-1')
    expect(panel.text()).toContain('实际 1 箱')
    expect(panel.text()).toContain('导出一物料一行')
    mocks.api.command.mockRejectedValueOnce(Object.assign(new Error('纸箱长宽高不一致，请核对包装资料'), { response: { status: 422 } }))
    await panel.get('form').trigger('submit'); await flushPromises()
    expect(mocks.api.command.mock.calls[0]![0]).toMatchObject({ action: 'shipment_confirm', entity_id: 'shipment', expected_version: 3, data: {} })
    expect(wrapper.get('[role="alert"]').text()).toContain('纸箱长宽高不一致')
    expect(panel.find('form').exists()).toBe(true)
    expect(panel.findAll('button').some(item => item.text() === '下载原版出货明细')).toBe(false)
    expect(mocks.api.download).not.toHaveBeenCalled()
  })

  it('renders server-frozen packing weights for a confirmed shipment and prevents editing', async () => {
    const confirmed = shipment('confirmed')
    confirmed.data.packing_totals = { cartons: 1, cbm: '0.01', lines: { a: { net_weight_kg: '0.02', carton_weight_kg: '0.1', gross_weight_kg: '0.12' } } }
    data.records.push(confirmed)
    const panel = (await setup()).get('#im-panel-shipment')
    await button(panel, '查看明细').trigger('click')
    expect(panel.text()).toContain('服务器确认：物理箱数 1 箱')
    expect(panel.text()).toContain('0.12')
    expect(panel.get('fieldset').attributes('disabled')).toBeDefined()
    expect(panel.findAll('button').some(item => item.text() === '保存出货草稿')).toBe(false)
  })
})

type FormPanel = Pick<DOMWrapper<Element>, 'get' | 'findAll'>
type FormCase = { name: string; area: string; prepare: (panel: FormPanel) => Promise<void>; seed?: () => void; submit?: (panel: FormPanel) => Promise<unknown> }
const formCases: FormCase[] = [
  { name: '固定客人', area: 'master', prepare: async panel => { await button(panel, '新增固定客人').trigger('click'); await field(panel, '固定客人名称').setValue('未保存客人'); await field(panel, '备注').setValue('客人备注草稿') } },
  { name: '物料资料和单重', area: 'master', prepare: async panel => { await button(panel, '物料资料').trigger('click'); await button(panel, '新增物料').trigger('click'); await field(panel, '物料名称').setValue('未保存物料'); await field(panel, '单个净重（kg）').setValue('0.006') } },
  { name: '货号与单件用量', area: 'master', prepare: async panel => { await button(panel, '维护客人货号').trigger('click'); await button(panel, '编辑').trigger('click'); await panel.get('input[aria-label="单件用量"]').setValue('7') } },
  { name: '合同交付批次', area: 'demand', prepare: async panel => { await button(panel, '新增合同交付批次').trigger('click'); await field(panel, '客户').setValue('CLIENT'); await field(panel, '成品货号').setValue('ITEM'); await field(panel, '客户合同号').setValue('未保存合同') } },
  { name: '调整物料需求', area: 'demand', prepare: async panel => { await button(panel, '调整需求').trigger('click'); await field(panel, '调整后的最终需求量').setValue('43'); await field(panel, '业务原因').setValue('需求草稿') } },
  { name: '重新生成需求', area: 'demand', prepare: async panel => { await button(panel, '重新生成需求').trigger('click'); await field(panel, '业务原因').setValue('重算草稿') } },
  { name: '分配供应', area: 'demand', prepare: async panel => { await button(panel, '分配供应').trigger('click'); await field(panel, '同物料采购／回料来源').setValue('s'); await field(panel, '分配正常量').setValue('8') } },
  { name: '未发物料改绑', area: 'demand', prepare: async panel => { await button(panel, '未发改绑').trigger('click'); await field(panel, '目标合同交付批次').setValue('o2'); await field(panel, '目标物料需求').setValue('d2'); await field(panel, '转走正常量').setValue('2'); await field(panel, '业务原因').setValue('改绑草稿') } },
  { name: '采购和回料数量', area: 'supply', prepare: async panel => { await button(panel, '登记采购／回料批次').trigger('click'); await field(panel, '物料').setValue('m'); await field(panel, '采购单号').setValue('未保存采购单'); await field(panel, '正常量').setValue('95') } },
  { name: '供应商回复', area: 'supply', prepare: async panel => { await button(panel, '更新回复').trigger('click'); await field(panel, '供应商回复回料日期').setValue('2026-11-05'); await field(panel, '回复来源／变更原因').setValue('回复草稿') } },
  { name: '船务入库', area: 'supply', prepare: async panel => { await button(panel, '船务确认入库').trigger('click'); await field(panel, '实际回河源日期').setValue('2026-11-06') } },
  { name: '出货资料补全', area: 'supply', prepare: async panel => { await button(panel, '补全出货资料').trigger('click'); await field(panel, '资料补全原因').setValue('补全原因草稿') } },
  { name: '出货数量和包装', area: 'shipment', prepare: async panel => { await button(panel, '新建出货草稿').trigger('click'); await field(panel, '客户').setValue('CLIENT'); await panel.get('input[type="checkbox"]').setValue(true); await panel.get('input[aria-label="本次正常量"]').setValue('9'); await button(panel, '添加包装组').trigger('click'); await field(panel, '包装组名称／箱号').setValue('混箱草稿'); await field(panel, '出货备注').setValue('出货草稿备注') } },
  { name: '出货确认核对', area: 'shipment', seed: () => { data.records.push(shipment()) }, prepare: async panel => { await button(panel, '核对并确认出货').trigger('click') } },
  { name: '导入文件和选中行', area: 'import', prepare: async panel => {
    const imported = record('import-matrix', 'import', { filename: 'schedule.xlsx', status: 'preview', rows: [{ ...mainOrder, index: 0, source_sheet: 'Sheet1', source_row: 20, blocked: false, issues: [] }] })
    data.records.push(imported)
    mocks.api.preview.mockResolvedValue({ record: imported })
    await field(panel, '客户').setValue('CLIENT')
    const input = panel.get('input[type="file"]')
    Object.defineProperty(input.element, 'files', { value: [new File(['xlsx'], 'schedule.xlsx')], configurable: true })
    await input.trigger('change'); await panel.get('form').trigger('submit'); await flushPromises()
    await panel.get('input[aria-label="选择来源行 20"]').setValue(true)
  }, submit: async panel => button(panel, '确认导入选中 1 行').trigger('click') },
]
function enteredValues(panel: Pick<DOMWrapper<Element>, 'findAll'>) {
  return panel.findAll('input, select, textarea').map(node => {
    const input = node.element as HTMLInputElement
    return { value: input.value, checked: input.checked, files: Array.from(input.files ?? []).map(file => file.name) }
  })
}
async function preparedForm(test: FormCase) {
  test.seed?.()
  mocks.auth.currentUser.identity = { employment_epoch: 1, identity_version: 1, effective_context_key: 'same', server_now: '2026-10-21T01:00:00Z' }
  const wrapper = await setup('customer')
  await wrapper.get(`#im-tab-${test.area}`).trigger('click')
  const panel = wrapper.get(`#im-panel-${test.area}`)
  await test.prepare(panel)
  return { wrapper, panel }
}
describe('all material form draft lifecycles', () => {
  it('protects a closed saved import until the user explicitly restores or replaces it', async () => {
    const { wrapper } = await preparedForm(formCases[14]!)
    await flushPromises(); wrapper.unmount(); wrappers.splice(wrappers.indexOf(wrapper), 1)
    const reopened = await setup('customer'), panel = reopened.get('#im-panel-import')
    expect(panel.get('fieldset').attributes('disabled')).toBeDefined()
    vi.mocked(window.confirm).mockReturnValue(false)
    await button(panel, '新建导入表单').trigger('click')
    expect(panel.get('fieldset').attributes('disabled')).toBeDefined()
    await button(reopened, '继续填写').trigger('click'); await flushPromises()
    expect(panel.get('fieldset').attributes('disabled')).toBeUndefined()
    expect(panel.text()).toContain('已保留文件：schedule.xlsx')
  })

  it('does not adopt another tab’s revision when an asynchronous import preview returns', async () => {
    const { wrapper, panel } = await preparedForm(formCases[14]!)
    await flushPromises()
    let release!: (value: { record: MaterialRecord }) => void
    mocks.api.preview.mockReturnValueOnce(new Promise(resolve => { release = resolve }))
    await panel.get('form').trigger('submit'); await flushPromises()
    const key = [...savedBuckets.keys()][0]!
    await memoryDatabase.update(key, bucket => {
      bucket.drafts.import!.revision = 'newer-other-tab'
      bucket.drafts.import!.state.customer = 'OTHER PAGE INPUT'
    })
    window.dispatchEvent(new StorageEvent('storage', { key: 'rrn-indonesia-draft-signal' })); await flushPromises()
    release({ record: record('new-preview', 'import', { filename: 'new.xlsx', rows: [], status: 'preview' }) })
    await flushPromises()
    expect(savedBuckets.get(key)!.drafts.import!.state.customer).toBe('OTHER PAGE INPUT')
    expect(wrapper.text()).toContain('此草稿已在其他页面更新')
    expect(mocks.api.command).not.toHaveBeenCalled()
  })
  it('blocks closing after an autosave failure and retries the current live input without losing it', async () => {
    const { wrapper, panel } = await preparedForm(formCases[0]!)
    await flushPromises()
    vi.spyOn(memoryDatabase, 'update').mockRejectedValueOnce(new Error('browser storage unavailable'))
    await field(panel, '备注').setValue('latest unsaved text'); await flushPromises()
    expect(wrapper.text()).toContain('自动保存异常')
    await button(panel, '关闭客人表单').trigger('click')
    expect(panel.find('form').exists()).toBe(true)
    expect((field(panel, '备注').element as HTMLTextAreaElement).value).toBe('latest unsaved text')
    await button(wrapper, '重新读取草稿').trigger('click'); await flushPromises()
    expect(wrapper.text()).toContain('已保存到本机')
    expect([...savedBuckets.values()][0]!.drafts.customer?.state.form.notes).toBe('latest unsaved text')
    expect(mocks.api.command).not.toHaveBeenCalled()
  })

  it('deletes only the explicitly chosen local draft without submitting or touching other input', async () => {
    const { wrapper } = await preparedForm(formCases[0]!)
    const supply = wrapper.get('#im-panel-supply')
    await formCases[8]!.prepare(supply); await flushPromises()
    const cards = wrapper.findAll('.im-draft-list li')
    const customerCard = cards.find(row => row.text().includes('固定客人'))!
    await button(customerCard, '删除草稿').trigger('click'); await flushPromises()
    expect(wrapper.get('#im-panel-master').find('form').exists()).toBe(false)
    expect((field(supply, '采购单号').element as HTMLInputElement).value).toBe('未保存采购单')
    expect(wrapper.findAll('.im-draft-list li')).toHaveLength(1)
    expect(mocks.api.command).not.toHaveBeenCalled()
  })
  it('lets read-only users view, close and change master categories without creating or replacing drafts', async () => {
    data.permissions = ['read']
    const wrapper = await setup('customer'), panel = wrapper.get('#im-panel-master')
    await button(panel, '查看客人').trigger('click'); await flushPromises()
    await button(panel, '关闭客人表单').trigger('click')
    expect(panel.find('form').exists()).toBe(false)
    await button(panel, '物料资料').trigger('click'); await button(panel, '查看').trigger('click'); await flushPromises()
    await button(panel, '关闭表单').trigger('click')
    expect(panel.find('form').exists()).toBe(false)
    expect(wrapper.findAll('.im-draft-list button')).toHaveLength(0)
  })

  it('restores a shipper receipt with receipt permission but refuses a business draft without write permission', async () => {
    const { wrapper } = await preparedForm(formCases[10]!)
    await flushPromises(); wrapper.unmount(); wrappers.splice(wrappers.indexOf(wrapper), 1)
    data.permissions = ['read', 'receipt_confirm']
    const reopened = await setup('customer')
    await button(reopened, '继续填写').trigger('click'); await flushPromises()
    expect((field(reopened.get('#im-panel-supply'), '实际回河源日期').element as HTMLInputElement).value).toBe('2026-11-06')
    expect(mocks.api.command).not.toHaveBeenCalled()
  })
  it.each(formCases)('$name keeps entered values through login refresh, workspace refresh and tab navigation', async test => {
    const { wrapper, panel } = await preparedForm(test)
    const before = enteredValues(panel)
    const forms = panel.findAll('form').length
    mocks.auth.currentUser = { ...mocks.auth.currentUser, identity: { ...mocks.auth.currentUser.identity, server_now: '2026-10-21T01:00:45Z' } }
    data = { ...data, records: structuredClone(data.records) }
    await button(wrapper, '刷新工作区').trigger('click'); await flushPromises()
    await wrapper.get('#im-tab-board').trigger('click'); await wrapper.get(`#im-tab-${test.area}`).trigger('click')
    expect(panel.findAll('form')).toHaveLength(forms)
    expect(enteredValues(panel)).toEqual(before)
    expect(mocks.api.command).not.toHaveBeenCalled()
  })

  it.each(formCases)('$name keeps entered values after a rejected save', async test => {
    const { wrapper, panel } = await preparedForm(test)
    const before = enteredValues(panel)
    mocks.api.command.mockRejectedValueOnce(Object.assign(new Error('资料需核对'), { response: { status: 422 } }))
    if (test.submit) await test.submit(panel)
    else await panel.get('form').trigger('submit')
    await flushPromises()
    expect(wrapper.get('[role="alert"]').text()).toContain('资料需核对')
    expect(enteredValues(panel)).toEqual(before)
    expect(panel.find('form').exists()).toBe(true)
  })

  it.each(formCases)('$name completes its own editor on an idempotent retry', async test => {
    const { wrapper, panel } = await preparedForm(test)
    mocks.api.command.mockRejectedValueOnce(new Error('保存响应中断'))
    if (test.submit) await test.submit(panel)
    else await panel.get('form').trigger('submit')
    await flushPromises()
    const original = structuredClone(mocks.api.command.mock.calls[0]![0])
    await button(wrapper, '重试原操作').trigger('click'); await flushPromises()
    expect(mocks.api.command.mock.calls[1]![0]).toEqual(original)
    if (test.area === 'import') expect(button(panel, '确认导入选中 0 行').attributes('disabled')).toBeDefined()
    else expect(panel.find('form').exists()).toBe(false)
  })

  it('does not close a dirty material editor on its selected category or a cancelled category change', async () => {
    const { panel } = await preparedForm(formCases[1]!)
    const before = enteredValues(panel)
    await button(panel, '物料资料').trigger('click')
    expect(enteredValues(panel)).toEqual(before)
    vi.mocked(window.confirm).mockReturnValue(false)
    await button(panel, '货号与单件用量').trigger('click')
    await button(panel, '关闭表单').trigger('click')
    await button(panel, '新增物料').trigger('click')
    expect(panel.find('form').exists()).toBe(true)
    expect(enteredValues(panel)).toEqual(before)
  })

  it('protects a dirty fixed-customer editor before switching master categories', async () => {
    const { panel } = await preparedForm(formCases[0]!)
    const before = enteredValues(panel)
    vi.mocked(window.confirm).mockReturnValue(false)
    await button(panel, '货号与单件用量').trigger('click')
    expect(enteredValues(panel)).toEqual(before)
    expect(panel.text()).toContain('新增固定客人')
  })

  it('closes only the saved form on retry and preserves the other workspace drafts', async () => {
    const { wrapper, panel: master } = await preparedForm(formCases[1]!)
    const materialBefore = enteredValues(master)
    const supply = wrapper.get('#im-panel-supply')
    await formCases[8]!.prepare(supply)
    mocks.api.command.mockRejectedValueOnce(new Error('网络中断'))
    await supply.get('form').trigger('submit'); await flushPromises()
    const submitted = structuredClone(mocks.api.command.mock.calls[0]![0])
    await button(wrapper, '重试原操作').trigger('click'); await flushPromises()
    expect(mocks.api.command.mock.calls[1]![0]).toEqual(submitted)
    expect(supply.find('form').exists()).toBe(false)
    expect(master.find('form').exists()).toBe(true)
    expect(enteredValues(master)).toEqual(materialBefore)
  })

  it('cancels an accidental recipient change without losing shipment quantities and packing', async () => {
    const { panel } = await preparedForm(formCases[12]!)
    const before = enteredValues(panel)
    vi.mocked(window.confirm).mockReturnValue(false)
    await field(panel, '本次唯一接收方').setValue('RRM')
    expect(enteredValues(panel)).toEqual(before)
  })

  it('protects import selections when changing source context or uploading another preview is cancelled', async () => {
    data.records.push(record('other-customer', 'customer', { name: 'OTHER', status: 'active' }))
    const { panel } = await preparedForm(formCases[14]!)
    const before = enteredValues(panel)
    vi.mocked(window.confirm).mockReturnValue(false)
    await field(panel, '本次接收方').setValue('RRM')
    expect(enteredValues(panel)).toEqual(before)
    await field(panel, '客户').setValue('OTHER')
    expect(enteredValues(panel)).toEqual(before)
    await panel.get('form').trigger('submit'); await flushPromises()
    expect(mocks.api.preview).toHaveBeenCalledTimes(1)
    expect(enteredValues(panel)).toEqual(before)
  })

  it('allows an explicitly confirmed import source change and autosaves the new context', async () => {
    const { wrapper, panel } = await preparedForm(formCases[14]!)
    await flushPromises()
    vi.mocked(window.confirm).mockReturnValue(true)
    await field(panel, '本次接收方').setValue('RRM'); await flushPromises()
    expect((field(panel, '本次接收方').element as HTMLSelectElement).value).toBe('RRM')
    expect(panel.find('input[aria-label="选择来源行 20"]').exists()).toBe(false)
    expect([...savedBuckets.values()][0]!.drafts.import?.state).toMatchObject({ recipient: 'RRM', selected: [], preview: null })
    expect(wrapper.text()).toContain('已保存到本机')
    expect(mocks.api.command).not.toHaveBeenCalled()
  })

  it('warns during a pending autosave, then allows refresh once the draft is durable even after closing the editor', async () => {
    const { panel } = await preparedForm(formCases[0]!)
    const dirty = new Event('beforeunload', { cancelable: true })
    window.dispatchEvent(dirty)
    expect(dirty.defaultPrevented).toBe(true)
    await button(panel, '关闭客人表单').trigger('click')
    await flushPromises()
    const clean = new Event('beforeunload', { cancelable: true })
    window.dispatchEvent(clean)
    expect(clean.defaultPrevented).toBe(false)
  })

  it.each(formCases)('$name restores its full context after closing and reopening the page without submitting business data', async test => {
    const { wrapper, panel } = await preparedForm(test)
    await flushPromises()
    const values = enteredValues(panel).map(({ files: _files, ...input }) => input)
    const forms = panel.findAll('form').length
    expect(wrapper.text()).toContain('已保存到本机')
    wrapper.unmount(); wrappers.splice(wrappers.indexOf(wrapper), 1)
    const reopened = await setup('customer')
    expect(mocks.api.command).not.toHaveBeenCalled()
    await button(reopened, '继续填写').trigger('click'); await flushPromises()
    const restored = reopened.get(`#im-panel-${test.area}`)
    expect(restored.findAll('form')).toHaveLength(forms)
    expect(enteredValues(restored).map(({ files: _files, ...input }) => input)).toEqual(values)
    if (test.area === 'import') expect(restored.text()).toContain('已保留文件：schedule.xlsx')
    expect(mocks.api.command).not.toHaveBeenCalled()
  })

  it('retains a material image and partial decimal text in durable storage', async () => {
    const { wrapper, panel } = await preparedForm(formCases[1]!)
    await field(panel, '物料编码').setValue('IMAGE-DRAFT')
    const file = new File([new Uint8Array([137, 80, 78, 71])], 'material.png', { type: 'image/png' })
    const input = panel.get('input[type="file"]')
    Object.defineProperty(input.element, 'files', { value: [file], configurable: true })
    await input.trigger('change')
    await vi.waitFor(() => expect(panel.find('img').exists()).toBe(true))
    await flushPromises()
    const source = panel.get('img').attributes('src')
    wrapper.unmount(); wrappers.splice(wrappers.indexOf(wrapper), 1)
    const reopened = await setup('customer')
    await button(reopened, '继续填写').trigger('click'); await flushPromises()
    expect(reopened.get('#im-panel-master img').attributes('src')).toBe(source)
    expect((field(reopened.get('#im-panel-master'), '单个净重（kg）').element as HTMLInputElement).value).toBe('0.006')
  })

  it('restores the old edit version rather than silently adopting the latest server revision', async () => {
    const { wrapper, panel } = await preparedForm(formCases[2]!)
    await flushPromises()
    wrapper.unmount(); wrappers.splice(wrappers.indexOf(wrapper), 1)
    data.records.find(row => row.id === 'p')!.version = 9
    const reopened = await setup('customer')
    await button(reopened, '继续填写').trigger('click'); await flushPromises()
    await reopened.get('#im-panel-master form').trigger('submit'); await flushPromises()
    expect(mocks.api.command.mock.calls[0]![0]).toMatchObject({ expected_version: 3, entity_id: 'p' })
    expect(reopened.findAll('.im-draft-list button')).toHaveLength(0)
  })

  it('refuses to restore editing when the original shipment has already been confirmed', async () => {
    const { wrapper } = await preparedForm(formCases[13]!)
    await flushPromises()
    wrapper.unmount(); wrappers.splice(wrappers.indexOf(wrapper), 1)
    data.records.find(row => row.id === 'shipment')!.data.status = 'confirmed'
    const reopened = await setup('customer')
    await button(reopened, '继续填写').trigger('click'); await flushPromises()
    expect(reopened.text()).toContain('该出货单已确认')
    expect(reopened.get('#im-panel-shipment').find('form').exists()).toBe(false)
    expect(button(reopened, '继续填写').exists()).toBe(true)
    expect(mocks.api.command).not.toHaveBeenCalled()
  })

  it('does not expose another account or factory draft, and preserves it for its original scope', async () => {
    const { wrapper } = await preparedForm(formCases[0]!)
    await flushPromises()
    mocks.app.activeFactoryId = 'huadeng'; await flushPromises()
    expect(wrapper.findAll('.im-draft-list button')).toHaveLength(0)
    mocks.app.activeFactoryId = 'huaxing'; await flushPromises()
    expect(wrapper.findAll('.im-draft-list button')).toHaveLength(2)
    mocks.auth.currentUser = { id: 'another-user' }; await flushPromises()
    expect(wrapper.findAll('.im-draft-list button')).toHaveLength(0)
    expect(wrapper.text()).not.toContain('未保存客人')
  })

  it('keeps a recovered editor closed after a successful replay from a new page', async () => {
    const { wrapper, panel } = await preparedForm(formCases[0]!)
    mocks.api.command.mockRejectedValueOnce(new Error('响应中断'))
    await panel.get('form').trigger('submit'); await flushPromises()
    const original = structuredClone(mocks.api.command.mock.calls[0]![0])
    wrapper.unmount(); wrappers.splice(wrappers.indexOf(wrapper), 1)
    const reopened = await setup('customer')
    expect(reopened.text()).toContain('上次尚未确认的提交')
    await button(reopened, '继续填写').trigger('click'); await flushPromises()
    expect(reopened.find('#im-panel-master form').exists()).toBe(true)
    await button(reopened, '重试原操作').trigger('click'); await flushPromises()
    expect(mocks.api.command.mock.calls[1]![0]).toEqual(original)
    expect(reopened.get('#im-panel-master').find('form').exists()).toBe(false)
    expect(reopened.findAll('.im-draft-list button')).toHaveLength(0)
  })
})
