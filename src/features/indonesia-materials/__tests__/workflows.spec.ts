import { flushPromises, mount, type DOMWrapper } from '@vue/test-utils'
import { reactive } from 'vue'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import type { BoardOrder, Data, MaterialRecord } from '@/api/indonesiaMaterials'
import IndonesiaMaterialsView from '@/views/IndonesiaMaterialsView.vue'
import { materialDefaults, orderDefaults, productDefaults, supplyDefaults } from '../forms'

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
async function setup() {
  const wrapper = mount(IndonesiaMaterialsView, { global: { stubs: { MaterialsHeader: { template: '<header><slot /></header>' } } } })
  wrappers.push(wrapper)
  await flushPromises()
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
  vi.resetAllMocks()
  mocks.app = reactive({ activeFactoryId: 'huaxing' })
  mocks.auth = reactive({ currentUser: { id: 'user' }, authorizationVersion: 1, permissions: [], grants: [], effectiveAccess: [] })
  data = fixture()
  mocks.api.workspace.mockImplementation(async () => data)
  mocks.api.command.mockResolvedValue({ record: material })
})
afterEach(() => wrappers.splice(0).forEach(wrapper => wrapper.unmount()))

describe('materials business forms', () => {
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
    expect(field(panel, '客户').attributes('readonly')).toBeDefined()
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
