import { flushPromises, mount, type DOMWrapper } from '@vue/test-utils'
import { reactive } from 'vue'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import type { BoardOrder, Data, MaterialRecord } from '@/api/indonesiaMaterials'
import IndonesiaMaterialsView from '@/views/IndonesiaMaterialsView.vue'
import BoardWorkspace from '../BoardWorkspace.vue'
import { materialDefaults, orderDefaults, productDefaults, supplyDefaults } from '../forms'
import { memoryDatabase, savedBuckets } from './draftMemory'
import { draftKind, recordDraftId, type SavedDraft } from '../draftPersistence'
vi.mock('../draftPersistence', async importOriginal => {
  const original = await importOriginal<typeof import('../draftPersistence')>()
  const { memoryDatabase } = await import('./draftMemory')
  return { ...original, createDraftPersistence: () => original.createDraftPersistence(memoryDatabase) }
})

const mocks = vi.hoisted(() => ({
  app: {} as Data, auth: {} as Data,
  api: { workspace: vi.fn(), command: vi.fn(), preview: vi.fn(), download: vi.fn(), warehouseTemplate: vi.fn(), masterPreview: vi.fn(), assignees: vi.fn() },
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
  board.push({ ...board[0]!, id: 'o2', contract_no: 'C-2', plan: { ...board[0]!.plan! }, demands: [{ ...board[0]!.demands[0]!, id: 'd2' }] })
  return { option_defaults: [{ group: 'unit', value: 'pcs', status: 'active' }, { group: 'customs_unit', value: 'KGM', status: 'active', billing_basis: 'weight', kg_per_unit: '1' }, { group: 'currency', value: 'USD', status: 'active' }], records: structuredClone(records), board, permissions: ['read', 'write', 'receipt_confirm', 'export', 'options_manage'] }
}
const packageData = { label: '整箱', cartons: 1, length_cm: '27', width_cm: '14.5', height_cm: '27.3', carton_weight_kg: '0.1', pallet: 'PALLET-1', items: [{ allocation_id: 'a', normal_quantity: '9', spare_quantity: '1' }] }
function shipment(status = 'draft') {
  return record('shipment', 'shipment', { customer: 'CLIENT', recipient: 'RRI', shipment_date: '2026-10-13', lines: [{ allocation_id: 'a', normal_quantity: '9', spare_quantity: '1' }], packages: [packageData], remarks: '', status })
}
let data = fixture()
const wrappers: ReturnType<typeof mount<typeof IndonesiaMaterialsView>>[] = []
async function setup(masterCategory: 'product' | 'customer' = 'product') {
  const wrapper = mount(IndonesiaMaterialsView, { attachTo: document.body, global: { stubs: { MaterialsHeader: { template: '<header><slot /></header>' } } } })
  wrappers.push(wrapper)
  await flushPromises()
  if (masterCategory === 'product' && wrapper.find('#im-panel-master').exists()) await button(wrapper.get('#im-panel-master'), '货号与物料').trigger('click')
  return wrapper
}
function button(scope: { findAll: (selector: string) => DOMWrapper<Element>[] }, text: string) {
  const found = scope.findAll('button').find(item => item.text() === text)
  if (!found) throw new Error(`Missing button: ${text}`)
  const trigger = found.trigger.bind(found)
  found.trigger = async (...args) => { await trigger(...args); await flushPromises() }
  return found
}
function storedDrafts() { return [...savedBuckets.values()].flatMap(bucket => Object.values(bucket.drafts)).filter(Boolean) as SavedDraft[] }
function addRecipeMaterials() {
  const p = data.records.find(row => row.id === 'p')!
  const additions = ['绿色拉杆', '蓝色拉杆', '推杆'].map((name, i) => record(`new-m-${i}`, 'material', { ...material.data, name, procurement_days: i + 10 }))
  data.records.push(...additions)
  p.version += 1
  p.data.materials.push(...additions.map(m => ({ material_id: m.id, usage: '2' })))
  return additions
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
  mocks.api.command.mockImplementation(async request => ({ record: request.action === 'shipment_confirm' ? { ...shipment('confirmed'), version: 4 } : material }))
})
afterEach(() => { wrappers.splice(0).forEach(wrapper => wrapper.unmount()); vi.restoreAllMocks(); vi.unstubAllGlobals() })

describe('unified material master import', () => {
  const staged = () => record('master-preview', 'import', { import_type: 'material_master', identity_rule: 'name-spec-v2', format_rule: 'unified-template-v1', status: 'preview', filename: '统一.xlsx', customer: 'CLIENT',
    products: [{ id: 'p', code: 'ITEM', version: 3 }], sheets: [{ sheet: '明细', header_row: 1, columns: { item_no: 1, name: 2 }, headers: ['货号', '物料名称'], enabled: true }],
    matched_rows: 1, skipped_rows: 1, asset_id: 'source', groups: [{ index: 0, existing: material, blocked: '',
      sources: [{ index: 0, source_sheet: '明细', source_row: 2, source: { item_no: 'ITEM', name: '导入名称', code: 'SCREW' }, warnings: [] }],
      products: [{ id: 'p', code: 'ITEM', existing_usage: '4' }], affected_products: [{ id: 'p', code: 'ITEM', customer: 'CLIENT' }] }] })
  async function openImport() {
    const wrapper = await setup('customer')
    await wrapper.get('#im-tab-master').trigger('click'); await flushPromises()
    await button(wrapper.get('#im-panel-master'), '统一资料导入').trigger('click')
    return { wrapper, panel: wrapper.get('#im-panel-master') }
  }
  async function chooseFile(panel: Pick<DOMWrapper<Element>, 'get'>, file: File | null) {
    const input = panel.get('input[type=file]')
    Object.defineProperty(input.element, 'files', { configurable: true, value: file ? [file] : [] })
    await input.trigger('change'); await flushPromises()
  }
  async function upload(panel: Pick<DOMWrapper<Element>, 'get'>) {
    await panel.get('select').setValue('CLIENT'); await flushPromises()
    await panel.get('.im-import-products input').setValue(true)
    await chooseFile(panel, new File(['xlsx'], '统一.xlsx'))
    mocks.api.masterPreview.mockImplementation(async () => { const row = staged(); data.records.push(row); return { record: row } })
    await panel.get('form').trigger('submit'); await flushPromises()
  }
  it('requires an explicit duplicate decision, keeps usage and sends one scoped command', async () => {
    const { panel } = await openImport(); await upload(panel)
    expect(mocks.api.masterPreview).toHaveBeenCalledWith('huaxing', 'CLIENT', ['p'], expect.any(File), [])
    expect(panel.text()).toContain('导入名称'); expect(panel.text()).toContain('螺丝')
    expect(button(panel, '确认导入 1 种物料').attributes('disabled')).toBeDefined()
    await panel.get('[data-master-import-group] .im-field select').setValue(0)
    const decision = panel.findAll('[data-master-import-group] select').find(node => node.text().includes('保留已有资料'))!
    await decision.setValue('keep'); await flushPromises()
    mocks.api.command.mockImplementation(async request => {
      const result = { ...staged(), version: 4, data: { ...staged().data, status: 'confirmed', choices: request.data.choices } }
      data.records = data.records.filter(row => row.id !== result.id).concat(result)
      return { record: result }
    })
    await panel.findAll('form')[1]!.trigger('submit'); await flushPromises()
    expect(mocks.api.command).toHaveBeenCalledWith(expect.objectContaining({ action: 'master_import_confirm', factory_id: 'huaxing', entity_id: 'master-preview', expected_version: 3,
      data: { choices: [{ group: 0, source_index: 0, decision: 'keep', material: null, recipes: [{ product_id: 'p', decision: 'keep', usage: null }] }] } }))
    expect(panel.text()).toContain('本次已导入 1 种物料')
    expect(storedDrafts().filter(draft => draftKind(draft.id) === 'masterimport')).toHaveLength(0)
  })
  it('canceling file selection preserves input; replacement and reload keep independent comparisons', async () => {
    const { wrapper, panel } = await openImport(); await upload(panel)
    const decision = panel.findAll('[data-master-import-group] select').find(node => node.text().includes('保留已有资料'))!
    await decision.setValue('import'); await flushPromises()
    await chooseFile(panel, null)
    expect(panel.text()).toContain('导入名称')
    await chooseFile(panel, new File(['another'], '另一份.xlsx'))
    expect(panel.find('[data-master-import-group]').exists()).toBe(false)
    const saved = storedDrafts().filter(draft => draftKind(draft.id) === 'masterimport')
    expect(saved).toHaveLength(2)
    expect(saved.some(draft => draft.state.file.name === '统一.xlsx' && draft.state.choices[0].decision === 'import')).toBe(true)
    wrapper.unmount()
    const next = await setup('customer')
    const savedId = saved.find(draft => draft.state.preview?.id === 'master-preview')!.id
    await button(next.get(`[data-draft-id="${savedId}"]`), '继续填写').trigger('click')
    expect(next.get('#im-panel-master').text()).toContain('导入名称')
    expect(next.get('#im-panel-master').findAll('[data-master-import-group] select').find(node => node.text().includes('保留已有资料'))!.element).toHaveProperty('value', 'import')
  })
  it('does not let native supplier search events replace the contract filter', async () => {
    const { wrapper, panel } = await openImport(); await upload(panel)
    const board = wrapper.getComponent(BoardWorkspace)
    board.vm.$emit('search', 'C-1'); await flushPromises()
    expect(board.props('search')).toBe('C-1')
    await panel.findAll('[data-master-import-group] select').find(node => node.text().includes('保留已有资料'))!.setValue('import')
    const supplier = panel.findAll('[data-master-import-group] label.im-field').find(label => label.find('span').text() === '供应商')!.get('input')
    await supplier.setValue('供应商草稿')
    await supplier.trigger('search'); await flushPromises()
    expect(board.props('search')).toBe('C-1')
    expect(supplier.element).toHaveProperty('value', '供应商草稿')
    expect(storedDrafts().some(draft => draft.state.choices?.[0]?.material?.supplier === '供应商草稿')).toBe(true)
    board.vm.$emit('search', 'C-2'); await flushPromises()
    expect(board.props('search')).toBe('C-2')
  })
  it('keeps all comparison choices after a concurrency rejection', async () => {
    const { panel } = await openImport(); await upload(panel)
    await panel.findAll('[data-master-import-group] select').find(node => node.text().includes('保留已有资料'))!.setValue('import')
    mocks.api.command.mockRejectedValue(Object.assign(new Error('物料已更新，请重新预览'), { response: { status: 409 } }))
    await panel.findAll('form')[1]!.trigger('submit'); await flushPromises()
    expect(panel.text()).toContain('导入名称')
    expect(storedDrafts().some(draft => draft.state.choices?.[0]?.decision === 'import')).toBe(true)
    await button(panel, '重新读取最新资料并对比').trigger('click')
    expect(mocks.api.masterPreview).toHaveBeenCalledTimes(2)
    expect(storedDrafts().filter(draft => draftKind(draft.id) === 'masterimport')).toHaveLength(2)
  })
  it('retains the mapping editor and choices when a new preview fails', async () => {
    const { panel } = await openImport(); await upload(panel)
    await panel.findAll('[data-master-import-group] select').find(node => node.text().includes('保留已有资料'))!.setValue('keep')
    mocks.api.masterPreview.mockRejectedValue(new Error('来源列重复，请核对映射'))
    await button(panel, '重新读取最新资料并对比').trigger('click')
    expect(panel.find('.im-import-mapping').exists()).toBe(true)
    expect(panel.findAll('[data-master-import-group] select').find(node => node.text().includes('保留已有资料'))!.element).toHaveProperty('value', 'keep')
    expect(storedDrafts().filter(draft => draftKind(draft.id) === 'masterimport')).toHaveLength(2)
  })
  it('blocks old code-grouped previews until the retained source is read again', async () => {
    const { panel } = await openImport(); await upload(panel)
    mocks.api.masterPreview.mockImplementation(async () => {
      const row = staged(); delete row.data.identity_rule
      data.records = data.records.filter(item => item.id !== row.id).concat(row)
      return { record: row }
    })
    await button(panel, '重新读取最新资料并对比').trigger('click'); await flushPromises()
    await panel.findAll('[data-master-import-group] select').find(node => node.text().includes('保留已有资料'))!.setValue('keep')
    expect(panel.text()).toContain('模板识别规则已更新')
    expect(button(panel, '确认导入 1 种物料').attributes('disabled')).toBeDefined()
  })
  it('shows four independently selectable names sharing one material code with a warning', async () => {
    const { panel } = await openImport(); await upload(panel)
    mocks.api.masterPreview.mockImplementation(async () => {
      const row = staged()
      row.data.groups = ['子弹筒', '绿色拉杆', '蓝色拉杆', '推杆'].map((name, index) => ({ ...row.data.groups[0], index,
        existing: null, code_warnings: ['编码 53003116 用于多个名称，分别维护'],
        sources: [{ index, source_sheet: '明细', source_row: index + 4, source: { code: '53003116', name, item_no: 'ITEM' }, warnings: [] }] }))
      row.data.matched_rows = 4; data.records = data.records.filter(item => item.id !== row.id).concat(row)
      return { record: row }
    })
    await button(panel, '重新读取最新资料并对比').trigger('click'); await flushPromises()
    expect(panel.findAll('[data-master-import-group]')).toHaveLength(4)
    expect(panel.text()).toContain('编码 53003116 用于多个名称')
    await panel.findAll('[data-master-import-group] .im-import-material-heading input')[1]!.setValue(false)
    expect(button(panel, '确认导入 3 种物料').exists()).toBe(true)
  })
  it('rereads an older format with automatic mapping while retaining the original draft', async () => {
    const { panel } = await openImport(); await upload(panel)
    mocks.api.masterPreview.mockImplementation(async () => {
      const row = staged(); delete row.data.format_rule
      data.records = data.records.filter(item => item.id !== row.id).concat(row)
      return { record: row }
    })
    await button(panel, '重新读取最新资料并对比').trigger('click'); await flushPromises()
    expect(button(panel, '确认导入 1 种物料').attributes('disabled')).toBeDefined()
    mocks.api.masterPreview.mockImplementation(async () => ({ record: staged() }))
    await button(panel, '重新读取最新资料并对比').trigger('click'); await flushPromises()
    expect(mocks.api.masterPreview).toHaveBeenLastCalledWith('huaxing', 'CLIENT', ['p'], expect.any(File), [])
    expect(storedDrafts().filter(draft => draftKind(draft.id) === 'masterimport').length).toBeGreaterThan(1)
  })
  it('compares old and incoming photos and restores the chosen photo from its own draft', async () => {
    const { wrapper, panel } = await openImport(); await upload(panel)
    mocks.api.masterPreview.mockImplementation(async () => {
      const row = staged()
      row.data.groups[0].existing = { ...material, data: { ...material.data, image_data: 'data:image/png;base64,b2xk' } }
      row.data.groups[0].sources[0].source.image_data = 'data:image/png;base64,bmV3'
      row.data.groups[0].sources[0].notes = ['单个净重取自 BD4 已保存的计算结果']
      data.records = data.records.filter(item => item.id !== row.id).concat(row)
      return { record: row }
    })
    await button(panel, '重新读取最新资料并对比').trigger('click'); await flushPromises()
    expect(panel.get('img[alt="已有物料图片"]').attributes('src')).toBe('data:image/png;base64,b2xk')
    expect(panel.get('img[alt="本次导入物料图片"]').attributes('src')).toBe('data:image/png;base64,bmV3')
    expect(panel.text()).toContain('识别来源（1 项）')
    await panel.findAll('[data-master-import-group] select').find(node => node.text().includes('保留已有资料'))!.setValue('import')
    await flushPromises()
    const saved = storedDrafts().find(draft => draft.state.choices?.[0]?.material?.image_data === 'data:image/png;base64,bmV3')!
    wrapper.unmount()
    const next = await setup('customer')
    await button(next.get(`[data-draft-id="${saved.id}"]`), '继续填写').trigger('click'); await flushPromises()
    expect(next.get('img[alt="本次导入物料图片"]').attributes('src')).toBe('data:image/png;base64,bmV3')
    expect(mocks.api.command).not.toHaveBeenCalled()
  })
})

describe('material-summary warehouse template', () => {
  function mockDownload() {
    const createObjectURL = vi.fn(() => 'blob:receipt-template')
    vi.stubGlobal('URL', Object.assign(class extends URL {}, { createObjectURL, revokeObjectURL: vi.fn() }))
    const click = vi.spyOn(HTMLAnchorElement.prototype, 'click').mockImplementation(() => {})
    mocks.api.warehouseTemplate.mockResolvedValue(new Blob(['xlsx']))
    return { createObjectURL, click }
  }
  async function openPicker() {
    const wrapper = await setup('customer')
    await wrapper.get('#im-tab-supply').trigger('click')
    const warehouse = wrapper.get('section[aria-label="仓库实收导入"]')
    await button(warehouse, '下载实收导入模板').trigger('click')
    return { wrapper, warehouse, picker: wrapper.get('form[aria-label="下载订单实收模板"]') }
  }
  it('updates every pending contract in place then downloads all materials without changing personal drafts', async () => {
    mockDownload()
    const additions = addRecipeMaterials()
    const { wrapper, warehouse, picker } = await openPicker()
    await field(warehouse, '仓库名称（原单无仓库列时填写）').setValue('保留的仓库草稿'); await flushPromises()
    const drafts = structuredClone(storedDrafts())
    expect(picker.get('[aria-label="回料模板待同步合同"]').text()).toContain('新增 3 种')
    expect(picker.get('[data-template-material="m"] input').attributes('disabled')).toBeDefined()
    await picker.trigger('submit'); await flushPromises()
    expect(mocks.api.warehouseTemplate).not.toHaveBeenCalled()
    mocks.api.command.mockImplementationOnce(async () => {
      const o = data.records.find(row => row.id === 'o')!
      for (const order of data.board) order.demands.push(...additions.map((m, i) => ({ ...order.demands[0]!, id: `${order.id}-added-${i}`, material_id: m.id, name: m.data.name, quantity: '20', coverage: '0', shortage: '20' })))
      data.board = structuredClone(data.board)
      return { record: { ...o, version: 4 } }
    })
    // Search narrows the displayed template rows, but never silently shrinks the stated batch scope.
    await field(picker, '查找物料').setValue('螺丝')
    await button(picker, '更新全部合同物料（2 张）').trigger('click'); await flushPromises()
    const request = mocks.api.command.mock.calls[0]![0]
    expect(request).toMatchObject({ action: 'order_materials_sync', entity_id: null, expected_version: 0,
      data: { customer: 'CLIENT', recipient: 'RRI', item_no: '', orders: [{ id: 'o', expected_version: 3 }, { id: 'o2', expected_version: 3 }] } })
    expect(request.data.products).toHaveLength(1)
    expect(request.data.materials).toEqual(additions.map(m => ({ id: m.id, expected_version: m.version })))
    expect(wrapper.get('#im-tab-supply').attributes('aria-selected')).toBe('true')
    expect(picker.text()).toContain('已更新 2 张合同，补入 6 项物料')
    expect(storedDrafts()).toEqual(drafts)
    await field(picker, '查找物料').setValue('')
    expect(picker.get('[data-template-material="new-m-0"] input').attributes('disabled')).toBeUndefined()
    await picker.get('[aria-label="全选当前模板物料"]').setValue(true)
    expect(button(picker, '下载所选 4 行 Excel').attributes('disabled')).toBeUndefined()
    await picker.trigger('submit'); await flushPromises()
    expect(mocks.api.warehouseTemplate.mock.calls[0]![0].material_ids).toEqual(['m', ...additions.map(m => m.id)])
    expect(picker.get('[data-template-material="m"] td:last-child').text()).toBe('38')
  })
  it('keeps the picker and drafts on a version conflict and refreshes without navigating', async () => {
    addRecipeMaterials()
    const { wrapper, picker } = await openPicker()
    const before = structuredClone(storedDrafts())
    mocks.api.command.mockRejectedValueOnce(Object.assign(new Error('合同已被更新，请刷新后重试；本次未保存'), { response: { status: 409 } }))
    await button(picker, '更新全部合同物料（2 张）').trigger('click'); await flushPromises()
    expect(picker.get('[role="alert"]').text()).toContain('本次未保存')
    expect(storedDrafts()).toEqual(before)
    expect(wrapper.get('#im-tab-supply').attributes('aria-selected')).toBe('true')
    await button(picker, '刷新合同清单').trigger('click'); await flushPromises()
    expect(picker.find('[role="alert"]').exists()).toBe(false)
    expect(button(picker, '更新全部合同物料（2 张）').attributes('disabled')).toBeUndefined()
  })
  it('restores the original bulk operation after a lost response and does not recreate it', async () => {
    addRecipeMaterials()
    const { wrapper, picker } = await openPicker()
    mocks.api.command.mockRejectedValueOnce(new Error('响应中断'))
    await button(picker, '更新全部合同物料（2 张）').trigger('click'); await flushPromises()
    const original = structuredClone(mocks.api.command.mock.calls[0]![0])
    wrapper.unmount()
    const reopened = await setup('customer')
    await button(reopened, '重试原操作').trigger('click'); await flushPromises()
    expect(mocks.api.command.mock.calls[1]![0]).toEqual(original)
  })
  it('clears an uncertain bulk error after retrying successfully on the same page', async () => {
    const additions = addRecipeMaterials()
    const { wrapper, picker } = await openPicker()
    mocks.api.command.mockRejectedValueOnce(new Error('响应中断'))
    await button(picker, '更新全部合同物料（2 张）').trigger('click'); await flushPromises()
    expect(picker.get('[role="alert"]').text()).toContain('重试原操作')
    const original = structuredClone(mocks.api.command.mock.calls[0]![0])
    mocks.api.command.mockImplementationOnce(async () => {
      for (const order of data.board) order.demands.push(...additions.map((m, i) => ({ ...order.demands[0]!, id: `${order.id}-retry-${i}`, material_id: m.id, name: m.data.name })))
      data.board = structuredClone(data.board)
      return { record: { ...data.records.find(row => row.id === 'o')!, version: 4 } }
    })
    await button(wrapper, '重试原操作').trigger('click'); await flushPromises()
    expect(mocks.api.command.mock.calls[1]![0]).toEqual(original)
    expect(picker.find('[role="alert"]').exists()).toBe(false)
    expect(picker.get('[data-template-material="new-m-0"] input').attributes('disabled')).toBeUndefined()
  })
  it('does not announce a complete template when workspace reload fails after committing', async () => {
    addRecipeMaterials()
    const { picker } = await openPicker()
    mocks.api.workspace.mockRejectedValueOnce(new Error('刷新失败'))
    await button(picker, '更新全部合同物料（2 张）').trigger('click'); await flushPromises()
    expect(picker.text()).toContain('更新已提交，请刷新清单')
    expect(picker.text()).not.toContain('可直接勾选下载')
    expect(button(picker, '刷新合同清单').exists()).toBe(true)
    expect(picker.get('[data-template-material="m"] input').attributes('disabled')).toBeDefined()
  })
  it('downloads only selected contract demand references and keeps the existing receipt draft intact', async () => {
    const downloads = mockDownload()
    const wrapper = await setup('customer')
    await wrapper.get('#im-tab-supply').trigger('click')
    const warehouse = wrapper.get('section[aria-label="仓库实收导入"]')
    await field(warehouse, '实收客户').setValue('CLIENT')
    await field(warehouse, '仓库名称（原单无仓库列时填写）').setValue('原实收仓库')
    await flushPromises()
    const before = structuredClone(storedDrafts())
    await button(warehouse, '下载实收导入模板').trigger('click')
    const picker = wrapper.get('form[aria-label="下载订单实收模板"]')
    const row = picker.get('[data-template-material="m"]')
    expect(row.findAll('td').slice(-3).map(cell => cell.text())).toEqual(['80', '42', '38'])
    expect(picker.text()).toContain('螺丝')
    expect(picker.text()).not.toContain('仓库别名')
    await row.get('input').setValue(true)
    expect((picker.get('[aria-label="全选当前模板物料"]').element as HTMLInputElement).indeterminate).toBe(false)
    await field(picker, '回传仓库').setValue('胶件仓')
    await picker.trigger('submit'); await flushPromises()
    expect(mocks.api.warehouseTemplate).toHaveBeenCalledExactlyOnceWith({ factory_id: 'huaxing', customer: 'CLIENT', recipient: 'RRI', warehouse: '胶件仓', mode: 'summary', item_no: '', material_ids: ['m'] })
    expect(downloads.click).toHaveBeenCalledOnce()
    expect((downloads.click.mock.instances[0] as HTMLAnchorElement).download).toBe('仓库实收回传模板.xlsx')
    expect(mocks.api.command).not.toHaveBeenCalled()
    expect(storedDrafts()).toEqual(before)
    expect((field(warehouse, '仓库名称（原单无仓库列时填写）').element as HTMLInputElement).value).toBe('原实收仓库')
  })
  it('preserves selections across filters, clears them for another recipient and blocks missing material rows', async () => {
    data.records = data.records.filter(row => row.kind !== 'product')
    data.board[1]!.demands[0]!.material_id = 'missing'
    const { picker } = await openPicker()
    expect(picker.get('[data-template-material="missing"] input').attributes('disabled')).toBeDefined()
    await picker.get('[aria-label="全选当前模板物料"]').setValue(true)
    await field(picker, '查找物料').setValue('not found')
    expect(picker.text()).toContain('另有 1 行已选物料')
    expect(button(picker, '下载所选 1 行 Excel').attributes('disabled')).toBeUndefined()
    await field(picker, '模板接收方').setValue('RRM')
    expect(button(picker, '下载所选 0 行 Excel').attributes('disabled')).toBeDefined()
  })
  it('retains selected rows after a download error and can retry without posting business data', async () => {
    mockDownload()
    mocks.api.warehouseTemplate.mockRejectedValueOnce(new Error('物料资料已更新，请重新核对'))
    const { picker } = await openPicker()
    await picker.get('[aria-label="全选当前模板物料"]').setValue(true)
    await picker.trigger('submit'); await flushPromises()
    expect(picker.get('[role="alert"]').text()).toContain('物料资料已更新')
    expect(button(picker, '下载所选 1 行 Excel').attributes('disabled')).toBeUndefined()
    await picker.trigger('submit'); await flushPromises()
    expect(mocks.api.warehouseTemplate).toHaveBeenCalledTimes(2)
    expect(mocks.api.command).not.toHaveBeenCalled()
    expect(picker.get('[role="status"]').text()).toContain('模板已下载')
  })
  it('discards an in-flight template response after changing factory', async () => {
    const downloads = mockDownload()
    let complete!: (blob: Blob) => void
    mocks.api.warehouseTemplate.mockImplementationOnce(() => new Promise(resolve => { complete = resolve }))
    const { wrapper, picker } = await openPicker()
    await picker.get('[aria-label="全选当前模板物料"]').setValue(true)
    await picker.trigger('submit'); await flushPromises()
    mocks.app.activeFactoryId = 'huadeng'; await flushPromises()
    complete(new Blob(['xlsx'])); await flushPromises()
    expect(downloads.createObjectURL).not.toHaveBeenCalled()
    expect(wrapper.get('form[aria-label="下载订单实收模板"]').isVisible()).toBe(false)
  })
  it('limits a template to 200 selected rows without silently truncating it', async () => {
    data.records = data.records.filter(row => row.kind !== 'product')
    data.records.push(...Array.from({ length: 201 }, (_, index) => record(`many-m-${index}`, 'material', { ...material.data, name: `物料${index}` })))
    data.board[0]!.demands = Array.from({ length: 201 }, (_, index) => ({ ...data.board[0]!.demands[0]!, id: `many-${index}`, material_id: `many-m-${index}` }))
    data.board = [data.board[0]!]
    const { picker } = await openPicker()
    await picker.get('[aria-label="全选当前模板物料"]').setValue(true)
    expect(picker.get('[role="alert"]').text()).toContain('每次最多下载 200 行')
    await picker.trigger('submit'); await flushPromises()
    expect(mocks.api.warehouseTemplate).not.toHaveBeenCalled()
  })
  it('does not open the template picker for a read-only account', async () => {
    data.permissions = ['read']
    const { warehouse, picker } = await openPicker()
    expect(button(warehouse, '下载实收导入模板').attributes('disabled')).toBeDefined()
    expect(picker.isVisible()).toBe(false)
    expect(mocks.api.warehouseTemplate).not.toHaveBeenCalled()
  })
})

describe('warehouse receipt to shipment flow', () => {
  it('combines receipt allocation and Excel output in one primary workspace', async () => {
    const wrapper = await setup()
    const tabs = wrapper.findAll('.im-main-tabs [role="tab"]')
    expect(tabs.map(tab => tab.text())).toEqual(['合同计划', '回料出货', '基础资料库'])
    await wrapper.get('#im-tab-supply').trigger('click')
    const panel = wrapper.get('#im-panel-supply')
    expect(panel.get('[aria-label="仓库实收导入"]').isVisible()).toBe(true)
    await button(panel, '已回料分配 PO').trigger('click')
    expect(panel.get('[data-allocation-workspace]').isVisible()).toBe(true)
    expect(panel.find('[data-received-supply-id="s"]').exists()).toBe(true)
    expect(panel.find('[data-received-supply-id="s-expected"]').exists()).toBe(false)
    await button(panel, '本次出货资料／Excel').trigger('click')
    expect(panel.get('#im-panel-shipment').isVisible()).toBe(true)
    expect(wrapper.get('#im-tab-supply').attributes('aria-selected')).toBe('true')
  })
  it('creates PO demand without a delivery batch or advance allocation controls', async () => {
    const wrapper = await setup(), panel = wrapper.get('#im-panel-demand')
    expect(panel.findAll('button').some(button => button.text() === '分配供应')).toBe(false)
    await button(panel, '新增合同需求').trigger('click')
    expect(panel.findAll('label').some(label => label.text().includes('交付批次'))).toBe(false)
    await field(panel, '客户').setValue('CLIENT'); await field(panel, '成品货号').setValue('ITEM')
    await field(panel, '客户合同号').setValue('C-NEW'); await field(panel, '客户 PO').setValue('CUSTOMER-PO')
    await field(panel, '合同成品数量').setValue('4000'); await field(panel, '印尼成品走货期').setValue('2026-12-21')
    await panel.get('form').trigger('submit'); await flushPromises()
    expect(mocks.api.command.mock.calls[0]![0]).toMatchObject({ action: 'order_save', data: { po_no: 'CUSTOMER-PO', batch: '', quantity: '4000' } })
  })
  function receipt(id = 'warehouse-a', ambiguous = false) {
    return record(id, 'import', { import_type: 'warehouse_receipt', filename: `${id}.csv`, customer: 'CLIENT', recipient: 'RRI', warehouse: '塑胶仓', asset_id: 'source', status: 'preview', shipment_ids: [], rows: [{
      index: 0, source_sheet: '实收单', source_row: 2, blocked: false, issues: [], auto_material_id: ambiguous ? null : 'm',
      source: { receipt_no: id, receipt_line: '1', actual_date: '2026-10-22', material_code: '', material_name: '螺丝', specification: '', unit: 'PCS', normal_quantity: '123456789012.12345678', spare_quantity: '0.00000001',
        purchase_no: 'P-WH', purchase_line: '1', purchase_date: '2026-10-01', purchase_quantity: '1000000000000', supplier: 'Supplier', price: '4', currency: 'USD' },
      materials: [{ id: 'm', version: 3, label: 'SCREW · 螺丝 · PCS', defaults: { supplier: 'Supplier', price: '4', currency: 'USD' } }],
      targets: { m: [{ order_id: 'o', demand_id: 'd', order_version: 3, remaining: '1000000000000', label: 'C-1 / ITEM / B-1' }, ...(ambiguous ? [{ order_id: 'o2', demand_id: 'd2', order_version: 3, remaining: '1000000000000', label: 'C-2 / ITEM / B-1' }] : [])] }, supplies: [],
    }] })
  }
  async function chooseFile(panel: Pick<DOMWrapper<Element>, 'get'>, name: string) {
    const file = new File(['receipt'], name, { type: 'text/csv' }), input = panel.get('input[type="file"]')
    Object.defineProperty(input.element, 'files', { configurable: true, value: [file] })
    await input.trigger('change'); await flushPromises()
    return file
  }
  async function prepareWarehouse(record = receipt()) {
    mocks.api.workspace.mockImplementation(async () => structuredClone(data))
    mocks.api.preview.mockImplementation(async () => { if (!data.records.some(item => item.id === record.id)) data.records.push(record); return { record } })
    const wrapper = await setup('customer'), panel = wrapper.get('section[aria-label="仓库实收导入"]')
    await field(panel, '实收客户').setValue('CLIENT'); await flushPromises()
    await chooseFile(panel, record.data.filename)
    await panel.get('form.im-upload-form').trigger('submit'); await flushPromises()
    return { wrapper, panel, record }
  }
  it('preserves newly typed warehouse context when first file selection precedes blur', async () => {
    const wrapper = await setup('customer'), panel = wrapper.get('section[aria-label="仓库实收导入"]')
    await field(panel, '实收客户').setValue('CLIENT')
    const warehouse = field(panel, '仓库名称（原单无仓库列时填写）')
    ;(warehouse.element as HTMLInputElement).value = '刚填写的胶件仓'
    await warehouse.trigger('input')
    await chooseFile(panel, '首份实收.csv')
    await field(panel, '实收接收方').setValue('RRM'); await flushPromises()
    const original = storedDrafts().find(item => item.state.customer === 'CLIENT' && item.state.recipient === 'RRI' && item.state.file?.name === '首份实收.csv')
    expect(original?.state.warehouse).toBe('刚填写的胶件仓')
    expect((field(panel, '仓库名称（原单无仓库列时填写）').element as HTMLInputElement).value).toBe('刚填写的胶件仓')
  })
  it('opens the receipt file picker on repeated entry clicks and returns to the upload form without clearing input', async () => {
    const wrapper = await setup('customer')
    await wrapper.get('#im-tab-supply').trigger('click')
    const supply = wrapper.get('#im-panel-supply'), panel = supply.get('section[aria-label="仓库实收导入"]')
    await field(panel, '实收客户').setValue('CLIENT')
    await field(panel, '仓库名称（原单无仓库列时填写）').setValue('塑胶仓')
    const input = panel.get('input[type="file"]'), picker = vi.spyOn(input.element as HTMLInputElement, 'click').mockImplementation(() => {})
    const scroll = vi.fn()
    Object.defineProperty(input.element, 'scrollIntoView', { configurable: true, value: scroll })
    document.body.appendChild(wrapper.element)
    try {
      await button(supply, '导入仓库实收单').trigger('click')
      await button(supply, '导入仓库实收单').trigger('click')
      expect(picker).toHaveBeenCalledTimes(2)
      expect(document.activeElement).toBe(input.element)
      expect(scroll).toHaveBeenCalled()
      await chooseFile(panel, '保留实收单.csv')
      const draftIds = storedDrafts().map(item => item.id)
      await button(supply, '采购与回料台账').trigger('click')
      await button(supply, '导入仓库实收单').trigger('click')
      await input.trigger('cancel')
      expect(panel.isVisible()).toBe(true)
      expect(picker).toHaveBeenCalledTimes(3)
      expect(document.activeElement).toBe(input.element)
      expect((field(panel, '实收客户').element as HTMLSelectElement).value).toBe('CLIENT')
      expect((field(panel, '仓库名称（原单无仓库列时填写）').element as HTMLInputElement).value).toBe('塑胶仓')
      expect(panel.text()).toContain('已保留：保留实收单.csv')
      expect(storedDrafts().map(item => item.id)).toEqual(draftIds)
      expect(mocks.api.preview).not.toHaveBeenCalled()
      expect(mocks.api.command).not.toHaveBeenCalled()
    } finally { wrapper.element.remove() }
  })
  it('keeps an existing receipt preview and PO allocation when the entry picker is cancelled', async () => {
    const { wrapper, panel } = await prepareWarehouse()
    await wrapper.get('#im-tab-supply').trigger('click')
    await panel.get('[aria-label="实收行 1 合同 1"]').setValue(JSON.stringify(['o', 'd']))
    await flushPromises()
    const before = storedDrafts().find(item => draftKind(item.id) === 'warehouse')!
    const input = panel.get('input[type="file"]'), picker = vi.spyOn(input.element as HTMLInputElement, 'click').mockImplementation(() => {})
    await button(wrapper.get('#im-panel-supply'), '导入仓库实收单').trigger('click')
    await input.trigger('cancel')
    expect(picker).toHaveBeenCalledOnce()
    expect(panel.text()).toContain('warehouse-a.csv · 实收匹配核对')
    expect((panel.get('[aria-label="实收行 1 合同 1"]').element as HTMLSelectElement).value).toBe(JSON.stringify(['o', 'd']))
    expect(storedDrafts().find(item => item.id === before.id)?.state).toEqual(before.state)
    expect(mocks.api.preview).toHaveBeenCalledOnce()
    expect(mocks.api.command).not.toHaveBeenCalled()
  })
  it('explains read-only receipt entry without opening a picker or creating a draft', async () => {
    data.permissions = ['read']
    const wrapper = await setup('customer')
    await wrapper.get('#im-tab-supply').trigger('click')
    const supply = wrapper.get('#im-panel-supply'), panel = supply.get('section[aria-label="仓库实收导入"]')
    const picker = vi.spyOn(panel.get('input[type="file"]').element as HTMLInputElement, 'click').mockImplementation(() => {})
    await button(supply, '导入仓库实收单').trigger('click')
    expect(picker).not.toHaveBeenCalled()
    expect(panel.get('[role="status"]').text()).toContain('当前账号没有实收单导入权限')
    expect(storedDrafts()).toHaveLength(0)
  })
  it('does not open a receipt picker while an upload is in progress', async () => {
    let finish!: () => void
    const pending = new Promise<void>(resolve => { finish = resolve })
    const source = receipt()
    mocks.api.preview.mockImplementation(async () => { await pending; data.records.push(source); return { record: source } })
    const wrapper = await setup('customer')
    await wrapper.get('#im-tab-supply').trigger('click')
    const supply = wrapper.get('#im-panel-supply'), panel = supply.get('section[aria-label="仓库实收导入"]')
    await field(panel, '实收客户').setValue('CLIENT')
    await chooseFile(panel, source.data.filename)
    const picker = vi.spyOn(panel.get('input[type="file"]').element as HTMLInputElement, 'click').mockImplementation(() => {})
    await panel.get('form.im-upload-form').trigger('submit'); await flushPromises()
    try {
      await button(supply, '导入仓库实收单').trigger('click')
      expect(picker).not.toHaveBeenCalled()
      expect(panel.get('[role="status"]').text()).toContain('请等待当前操作完成')
      expect(mocks.api.preview).toHaveBeenCalledOnce()
    } finally { finish(); await flushPromises() }
  })
  function postResult(record: MaterialRecord) {
    const shipmentRecord = { ...shipment(), id: 'warehouse-shipment', data: { ...shipment().data, packages: [], warehouse_import_id: record.id } }
    const updated = { ...record, version: 4, data: { ...record.data, status: 'confirmed', shipment_ids: [shipmentRecord.id], rows: record.data.rows.map((row: Data) => ({ ...row, imported_supply_id: 'received' })) } }
    data.records = [...data.records.filter(item => item.id !== record.id), updated, shipmentRecord]
    return { record: updated }
  }
  it('opens the generated shipment after a failed workspace refresh recovers without submitting again', async () => {
    const { wrapper, panel, record } = await prepareWarehouse()
    await wrapper.get('#im-tab-supply').trigger('click')
    await panel.get('[aria-label="实收行 1 合同 1"]').setValue(JSON.stringify(['o', 'd']))
    await field(panel, '本次计划河源出货日期').setValue('2026-10-23')
    mocks.api.command.mockImplementationOnce(async () => postResult(record))
    mocks.api.workspace.mockRejectedValueOnce(new Error('workspace refresh failed'))
    await panel.get('form.im-editor').trigger('submit'); await flushPromises()
    expect(wrapper.text()).toContain('workspace refresh failed')
    expect(mocks.api.command).toHaveBeenCalledOnce()
    await button(wrapper, '刷新工作区').trigger('click'); await flushPromises()
    expect(wrapper.get('#im-panel-supply').get('[aria-current="step"]').text()).toContain('补装箱')
    expect(wrapper.get('#im-panel-shipment').get('form').isVisible()).toBe(true)
    expect(wrapper.get('#im-panel-shipment').get('form').text()).toContain('补齐本次装箱资料')
    expect(mocks.api.command).toHaveBeenCalledOnce()
  })
  it.each([false, true])('completes matching, packing, review and export with interrupted response=%s', async interrupted => {
    const { wrapper, panel, record } = await prepareWarehouse()
    await wrapper.get('#im-tab-supply').trigger('click')
    await panel.get('[aria-label="实收行 1 合同 1"]').setValue(JSON.stringify(['o', 'd']))
    await field(panel, '本次计划河源出货日期').setValue('2026-10-23')
    const replies = new Map<string, { record: MaterialRecord }>()
    mocks.api.command.mockImplementation(async command => {
      const previous = replies.get(command.operation_id)
      if (previous) return previous
      let result
      if (command.action === 'warehouse_import_confirm') result = postResult(record)
      else {
        const current = data.records.find(r => r.id === command.entity_id)!
        const saved = { ...current, version: current.version + 1, data: command.action === 'shipment_save' ? { ...current.data, ...command.data } : { ...current.data, status: 'confirmed' } }
        data.records = data.records.map(r => r.id === saved.id ? saved : r)
        result = { record: saved }
      }
      replies.set(command.operation_id, result)
      if (interrupted) throw new Error('response lost')
      return result
    })
    vi.stubGlobal('URL', Object.assign(URL, { createObjectURL: vi.fn(() => 'blob:test'), revokeObjectURL: vi.fn() }))
    vi.spyOn(HTMLAnchorElement.prototype, 'click').mockImplementation(() => {})
    mocks.api.download.mockResolvedValue(new Blob(['xlsx']))
    async function retryIfNeeded() { await flushPromises(); if (interrupted) await button(wrapper, '重试原操作').trigger('click'); await flushPromises() }
    await panel.get('form.im-editor').trigger('submit'); await retryIfNeeded()
    const supply = wrapper.get('#im-panel-supply'), editor = wrapper.get('#im-panel-shipment')
    expect(supply.get('[aria-current="step"]').text()).toContain('补装箱')
    expect(editor.get('form').isVisible()).toBe(true)
    await button(editor, '添加包装组').trigger('click')
    for (const [name, value] of [['包装组名称／箱号', '向导整箱'], ['箱数', '1'], ['长（cm）', '27'], ['宽（cm）', '14.5'], ['高（cm）', '27.3']]) await field(editor, name!).setValue(value)
    await button(editor, '添加箱内物料').trigger('click')
    await editor.get('[aria-label="箱内出货物料"]').setValue('a')
    await editor.get('[aria-label="组内正常量"]').setValue('8')
    await editor.get('[aria-label="组内备品量"]').setValue('1')
    await button(editor, '保存装箱，去核对出货').trigger('click')
    expect(editor.text()).toContain('正常量还差 1')
    expect(replies.size).toBe(1)
    await editor.get('[aria-label="组内正常量"]').setValue('9')
    await button(editor, '保存装箱，去核对出货').trigger('click'); await retryIfNeeded()
    expect(supply.get('[aria-current="step"]').text()).toContain('确认导出')
    // Going back and saving again must review the new version, not an old confirmation draft.
    await supply.get('.im-wizard-steps button:nth-child(3)').trigger('click'); await flushPromises()
    await field(editor, '包装组名称／箱号').setValue('更新后的箱号')
    await button(editor, '保存装箱，去核对出货').trigger('click'); await retryIfNeeded()
    expect(editor.get('form').text()).toContain('更新后的箱号')
    await editor.get('form input[type=checkbox]').setValue(true)
    await editor.get('form').trigger('submit'); await retryIfNeeded()
    expect(editor.text()).toContain('已确认出货明细')
    expect(mocks.api.command.mock.calls.filter(([cmd]) => cmd.action === 'shipment_confirm').every(([cmd]) => cmd.expected_version === 5)).toBe(true)
    expect(mocks.api.download).toHaveBeenCalledOnce()
    const writes = mocks.api.command.mock.calls.length
    await button(editor, '下载出货 Excel').trigger('click')
    expect(mocks.api.download).toHaveBeenCalledTimes(2)
    expect(mocks.api.command).toHaveBeenCalledTimes(writes)
    // A new receipt cannot use the previous receipt's shipment as its next step.
    await supply.get('.im-wizard-steps button:nth-child(1)').trigger('click')
    await button(panel, '新建实收导入').trigger('click')
    expect(supply.get('.im-wizard-steps button:nth-child(3)').attributes('disabled')).toBeDefined()
    expect(supply.get('.im-wizard-steps button:nth-child(4)').attributes('disabled')).toBeDefined()
  })
  it('proposes a matching PO for business review, preserves decimal text and opens the generated draft for packing', async () => {
    const { wrapper, panel, record } = await prepareWarehouse()
    expect((panel.get('[aria-label="实收行 1 对应物料"]').element as HTMLSelectElement).value).toBe('m')
    expect((panel.get('[aria-label="实收行 1 合同 1"]').element as HTMLSelectElement).value).toBe(JSON.stringify(['o', 'd']))
    await panel.get('[aria-label="实收行 1 合同 1"]').setValue(JSON.stringify(['o', 'd']))
    await panel.get('[aria-label="实收行 1 正常量 1"]').setValue('123456789012.12345678')
    await field(panel, '本次计划河源出货日期').setValue('2026-10-23')
    mocks.api.command.mockImplementationOnce(async () => postResult(record))
    await panel.get('form.im-editor').trigger('submit'); await flushPromises()
    expect(mocks.api.command.mock.calls[0]![0]).toMatchObject({ factory_id: 'huaxing', action: 'warehouse_import_confirm', entity_id: record.id,
      data: { rows: [{ material_id: 'm', material_version: 3, allocations: [{ order_id: 'o', demand_id: 'd', order_version: 3, normal_quantity: '123456789012.12345678', spare_quantity: '0.00000001' }] }] } })
    await button(panel, '打开出货草稿并补装箱').trigger('click')
    expect(wrapper.get('#im-tab-supply').attributes('aria-selected')).toBe('true')
    expect(wrapper.get('#im-panel-shipment').text()).toContain('实收与 PO 已确认')
    expect(wrapper.get('#im-panel-shipment').get('form').text()).toContain('补齐本次装箱资料')
  })
  it('leaves ambiguous material and contract selections for business confirmation', async () => {
    const { panel } = await prepareWarehouse(receipt('ambiguous', true))
    expect((panel.get('[aria-label="实收行 1 对应物料"]').element as HTMLSelectElement).value).toBe('')
    await panel.get('[aria-label="实收行 1 对应物料"]').setValue('m')
    expect((panel.get('[aria-label="实收行 1 合同 1"]').element as HTMLSelectElement).value).toBe(JSON.stringify(['o', 'd']))
    await panel.get('[aria-label="实收行 1 合同 1"]').setValue(JSON.stringify(['o2', 'd2']))
    await flushPromises()
    const saved = storedDrafts().find(item => draftKind(item.id) === 'warehouse')!
    expect(saved.state.choices[0].allocations[0]).toMatchObject({ order_id: 'o2', demand_id: 'd2', order_version: 3 })
    expect(mocks.api.command).not.toHaveBeenCalled()
  })
  it('shares capacity across source rows, preserves manual edits on refresh and explicitly recomputes selected rows', async () => {
    const source = receipt(), first = source.data.rows[0]
    first.source.normal_quantity = '20'; first.source.spare_quantity = '0'
    first.targets.m = [{ order_id: 'o', demand_id: 'd', order_version: 3, remaining: '100', required_date: '2026-11-02', label: 'C-1' },
      { order_id: 'o2', demand_id: 'd2', order_version: 3, remaining: '30', required_date: '2026-11-01', label: 'C-2' }]
    source.data.rows.push({ ...structuredClone(first), index: 1, source: { ...first.source, receipt_line: '2' } })
    const { wrapper, panel } = await prepareWarehouse(source)
    expect((panel.get('[aria-label="实收行 1 合同 1"]').element as HTMLSelectElement).value).toBe(JSON.stringify(['o2', 'd2']))
    expect((panel.get('[aria-label="实收行 2 正常量 1"]').element as HTMLInputElement).value).toBe('10')
    expect((panel.get('[aria-label="实收行 2 正常量 2"]').element as HTMLInputElement).value).toBe('10')
    await panel.get('[aria-label="实收行 1 合同 1"]').setValue(JSON.stringify(['o', 'd']))
    await button(wrapper, '刷新工作区').trigger('click')
    expect((panel.get('[aria-label="实收行 1 合同 1"]').element as HTMLSelectElement).value).toBe(JSON.stringify(['o', 'd']))
    await panel.get('[aria-label="选择实收行 2"]').setValue(false)
    await button(panel, '重新按货期建议').trigger('click')
    expect(window.confirm).toHaveBeenCalledOnce()
    expect((panel.get('[aria-label="实收行 1 合同 1"]').element as HTMLSelectElement).value).toBe(JSON.stringify(['o2', 'd2']))
    expect(mocks.api.command).not.toHaveBeenCalled()
  })
  it('reserves an explicitly reassigned historical row before suggesting a second receipt', async () => {
    const source = receipt(), first = source.data.rows[0], expected = data.records.find(item => item.id === 's-expected')!
    first.source.normal_quantity = '10'; first.source.spare_quantity = '0'
    first.supplies = [expected]
    first.targets.m = [{ order_id: 'o', demand_id: 'd', order_version: 3, remaining: '0', required_date: '2026-11-02', label: 'C-1' },
      { order_id: 'o2', demand_id: 'd2', order_version: 3, remaining: '15', required_date: '2026-11-01', label: 'C-2' }]
    source.data.rows.push({ ...structuredClone(first), index: 1, supplies: [], source: { ...first.source, receipt_line: '2' } })
    const { panel } = await prepareWarehouse(source)
    await panel.get('[aria-label="实收行 1 原采购批次"]').setValue(expected.id)
    await panel.get('[aria-label="实收行 1 重新指定历史分配"]').setValue(true)
    await field(panel, '重新分配原因').setValue('按实际用途改供 C-2')
    await panel.get('[aria-label="实收行 1 合同 1"]').setValue(JSON.stringify(['o2', 'd2']))
    await button(panel, '重新按货期建议').trigger('click')
    expect((panel.get('[aria-label="实收行 2 正常量 1"]').element as HTMLInputElement).value).toBe('5')
    expect(panel.text()).toContain('待分配：正常 5')
    expect(button(panel, '确认实收与 PO，去补装箱').attributes('disabled')).toBeDefined()
  })
  it('requires an explicit acknowledged revision set before replacing historical PO allocations', async () => {
    const source = receipt(), expected = data.records.find(item => item.id === 's-expected')!
    source.data.rows[0].supplies = [expected]
    const { panel } = await prepareWarehouse(source)
    await panel.get('[aria-label="实收行 1 原采购批次"]').setValue(expected.id)
    expect((panel.get('[aria-label="实收行 1 合同 1"]').element as HTMLSelectElement).value).toBe(JSON.stringify(['o', 'd']))
    const acknowledge = panel.get('[aria-label="实收行 1 重新指定历史分配"]')
    expect((acknowledge.element as HTMLInputElement).checked).toBe(false)
    await acknowledge.setValue(true)
    await field(panel, '重新分配原因').setValue('按实际用途改供客户 PO')
    await panel.get('[aria-label="实收行 1 合同 1"]').setValue(JSON.stringify(['o', 'd']))
    await panel.get('[aria-label="实收行 1 正常量 1"]').setValue(source.data.rows[0].source.normal_quantity)
    await panel.get('[aria-label="实收行 1 备品量 1"]').setValue(source.data.rows[0].source.spare_quantity)
    await field(panel, '本次计划河源出货日期').setValue('2026-10-23')
    await panel.get('form.im-editor').trigger('submit'); await flushPromises()
    expect(mocks.api.command.mock.calls[0]![0]).toMatchObject({ action: 'warehouse_import_confirm', data: { rows: [{
      replace_allocations: [{ allocation_id: 'a-expected', version: 3 }], replacement_reason: '按实际用途改供客户 PO',
    }] } })
  })
  it('preserves pre-file customer and warehouse input after reopening', async () => {
    const wrapper = await setup('customer'), panel = wrapper.get('section[aria-label="仓库实收导入"]')
    await field(panel, '实收客户').setValue('CLIENT')
    await field(panel, '仓库名称（原单无仓库列时填写）').setValue('纸品仓'); await flushPromises()
    const saved = storedDrafts().find(item => draftKind(item.id) === 'warehouse')!
    wrapper.unmount(); wrappers.splice(wrappers.indexOf(wrapper), 1)
    const reopened = await setup('customer')
    await button(reopened.get(`[data-draft-id="${saved.id}"]`), '继续填写').trigger('click')
    const recovered = reopened.get('section[aria-label="仓库实收导入"]')
    expect((field(recovered, '实收客户').element as HTMLSelectElement).value).toBe('CLIENT')
    expect((field(recovered, '仓库名称（原单无仓库列时填写）').element as HTMLInputElement).value).toBe('纸品仓')
  })
  it('keeps each file and matching decision in its own independent draft', async () => {
    const first = receipt('warehouse-a', true), second = receipt('warehouse-b')
    const { wrapper, panel } = await prepareWarehouse(first)
    await panel.get('[aria-label="实收行 1 对应物料"]').setValue('m')
    await panel.get('[aria-label="实收行 1 合同 1"]').setValue(JSON.stringify(['o2', 'd2']))
    await flushPromises()
    const saved = storedDrafts().find(item => item.state.preview?.id === first.id)!
    mocks.api.preview.mockImplementationOnce(async () => { data.records.push(second); return { record: second } })
    await chooseFile(panel, second.data.filename)
    await panel.get('form.im-upload-form').trigger('submit'); await flushPromises()
    expect(storedDrafts().filter(item => draftKind(item.id) === 'warehouse')).toHaveLength(2)
    await button(wrapper.get(`[data-draft-id="${saved.id}"]`), '继续填写').trigger('click')
    expect((panel.get('[aria-label="实收行 1 合同 1"]').element as HTMLSelectElement).value).toBe(JSON.stringify(['o2', 'd2']))
    expect(panel.text()).toContain('warehouse-a.csv')
  })
  it('retries the exact warehouse operation after reopening without creating a second receipt', async () => {
    const { wrapper, panel, record } = await prepareWarehouse()
    await field(panel, '本次计划河源出货日期').setValue('2026-10-23')
    mocks.api.command.mockRejectedValueOnce(new Error('保存响应中断'))
    await panel.get('form.im-editor').trigger('submit'); await flushPromises()
    const original = structuredClone(mocks.api.command.mock.calls[0]![0])
    wrapper.unmount(); wrappers.splice(wrappers.indexOf(wrapper), 1)
    mocks.api.command.mockImplementationOnce(async () => postResult(record))
    const reopened = await setup('customer')
    await button(reopened, '重试原操作').trigger('click')
    expect(mocks.api.command.mock.calls[1]![0]).toEqual(original)
    expect(storedDrafts().some(item => draftKind(item.id) === 'warehouse')).toBe(false)
    expect(data.records.filter(item => item.id === 'warehouse-shipment')).toHaveLength(1)
  })
  it('does not suggest an existing batch with conflicting price and shows its conflict explicitly if selected', async () => {
    const source = receipt()
    source.data.rows[0].source.purchase_no = 'P-2'
    source.data.rows[0].supplies = [record('s-expected', 'supply', { ...supplyDefaults, material_id: 'm', normal_quantity: '123456789012.12345678', spare_quantity: '0.00000001', purchase_no: 'P-2', price: '2', purchase_quantity: '1000000000000' })]
    const { panel } = await prepareWarehouse(source)
    expect((panel.get('[aria-label="实收行 1 原采购批次"]').element as HTMLSelectElement).value).toBe('')
    await panel.get('[aria-label="实收行 1 原采购批次"]').setValue('s-expected')
    expect(panel.text()).toContain('原单采购资料与该批次不一致')
    expect(panel.text()).toContain('单价 2')
  })
})

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
    expect(panel.text()).toContain('货号下的物料明细')
  })

  it('restricts contract product choices by customer and clears a stale product when customer changes', async () => {
    data.records.push(record('other-client', 'customer', { name: 'OTHER', status: 'active' }))
    data.records.push(record('other-product', 'product', { ...productDefaults, code: 'OTHER-ITEM', customer: 'OTHER', unit: 'SET', materials: [{ material_id: 'm', usage: '2' }] }))
    const panel = (await setup()).get('#im-panel-demand')
    await button(panel, '新增合同需求').trigger('click')
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
  it('maintains only net weight and omits the former duplicate billing weight from material saves', async () => {
    const wrapper = await setup()
    const panel = wrapper.get('#im-panel-master')
    await button(panel, '编辑').trigger('click')
    await button(panel, '编辑物料资料').trigger('click')
    await field(panel, '单个净重（kg）').setValue('0.005')
    expect(panel.findAll('label').some(item => item.text().includes('单件计费重量'))).toBe(false)
    await panel.get('form').trigger('submit')
    await flushPromises()
    expect(mocks.api.command.mock.calls[0]![0]).toMatchObject({ action: 'product_save', entity_id: 'p', expected_version: 3, data: { materials: [{ material_id: 'm', material_version: 3, usage: '4', material: { net_weight_kg: '0.005' } }] } })
    expect(mocks.api.command.mock.calls[0]![0].data.materials[0].material).not.toHaveProperty('billing_weight_kg')
    expect(mocks.api.command.mock.calls[0]![0].data).not.toHaveProperty('status')
  })

  it('restores an old material draft with its net weight while omitting its obsolete billing input on save', async () => {
    const wrapper = await setup(), panel = wrapper.get('#im-panel-master')
    await button(panel, '编辑').trigger('click')
    await button(panel, '编辑物料资料').trigger('click')
    await field(panel, '单个净重（kg）').setValue('0.00654321')
    wrapper.unmount(); wrappers.splice(wrappers.indexOf(wrapper), 1)
    storedDrafts()[0]!.state.form.materials[0].material.billing_weight_kg = '999'
    const reopened = await setup('customer')
    await button(reopened, '继续填写').trigger('click')
    const restored = reopened.get('#im-panel-master')
    expect((field(restored, '单个净重（kg）').element as HTMLInputElement).value).toBe('0.00654321')
    expect(restored.findAll('label').some(item => item.text().includes('单件计费重量'))).toBe(false)
    await restored.get('form').trigger('submit'); await flushPromises()
    expect(mocks.api.command.mock.calls[0]![0].data.materials[0].material).toMatchObject({ net_weight_kg: '0.00654321' })
    expect(mocks.api.command.mock.calls[0]![0].data.materials[0].material).not.toHaveProperty('billing_weight_kg')
  })

  it('retries a legacy unresolved purchase without adding the new net-weight pricing marker', async () => {
    const wrapper = await setup(), panel = wrapper.get('#im-panel-supply')
    await button(panel, '登记采购／回料批次').trigger('click')
    await field(panel, '物料').setValue('m')
    await field(panel, '采购单号').setValue('OLD-UNRESOLVED')
    mocks.api.command.mockRejectedValueOnce(new Error('网络中断'))
    await panel.get('form').trigger('submit'); await flushPromises()
    wrapper.unmount(); wrappers.splice(wrappers.indexOf(wrapper), 1)
    const old = [...savedBuckets.values()][0]!.pending!.command
    delete old.data.billing_weight_source
    const original = structuredClone(old)
    const reopened = await setup('customer')
    await button(reopened, '重试原操作').trigger('click')
    expect(mocks.api.command.mock.calls[1]![0]).toEqual(original)
    expect(mocks.api.command.mock.calls[1]![0].data).not.toHaveProperty('billing_weight_source')
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
    await button(panel, '货号与物料').trigger('click')
    await button(panel, '编辑').trigger('click')
    await panel.get('input[aria-label="单件用量"]').setValue('4.12345678')
    await field(panel, '日产能').setValue('5000')
    await panel.get('form').trigger('submit'); await flushPromises()
    expect(mocks.api.command.mock.calls[0]![0]).toMatchObject({ action: 'product_save', entity_id: 'p', expected_version: 3, data: { code: 'ITEM', customer: 'CLIENT', daily_capacity: '5000', transport_days: 25, materials: [{ material_id: 'm', usage: '4.12345678' }] } })
  })

  it.each(['NEW-SCREW', ''])('adds complete material data with optional code "%s" under the chosen product', async newCode => {
    const panel = (await setup()).get('#im-panel-master')
    expect(panel.get('nav').findAll('button').map(item => item.text())).toEqual(['固定客人', '货号与物料', '统一资料导入', '基础选项'])
    await button(panel, '添加物料').trigger('click')
    const card = panel.findAll('.im-recipe-card')[1]!
    expect(field(card, '物料编码').attributes('required')).toBeUndefined()
    await field(card, '物料编码').setValue(newCode)
    await field(card, '物料名称').setValue('新螺丝')
    await field(card, '数量单位').setValue('pcs')
    await field(card, '供应商').setValue('新供应商')
    await field(card, '单个净重（kg）').setValue('0.00012345')
    await card.get('[aria-label="单件用量"]').setValue('2.12345678')
    await panel.get('form').trigger('submit'); await flushPromises()
    expect(mocks.api.command).toHaveBeenCalledTimes(1)
    const command = mocks.api.command.mock.calls[0]![0]
    expect(command).toMatchObject({ action: 'product_save', entity_id: 'p', expected_version: 3, data: { materials: [
      { material_id: 'm', usage: '4' },
      { material_id: null, material_version: 0, usage: '2.12345678', material: { code: newCode, name: '新螺丝', unit: 'pcs', supplier: '新供应商', net_weight_kg: '0.00012345' } },
    ] } })
    expect(JSON.stringify(command.data)).not.toContain('_key')
  })

  it('restores an unsaved code addition as editable while protecting already saved codes', async () => {
    data.records.find(row => row.id === 'm')!.data.code = ''
    const wrapper = await setup(), panel = wrapper.get('#im-panel-master')
    await button(panel, '编辑').trigger('click'); await button(panel, '编辑物料资料').trigger('click')
    expect(field(panel, '物料编码').attributes('readonly')).toBeUndefined()
    await field(panel, '物料编码').setValue('FIRST-DRAFT'); await flushPromises()
    const saved = storedDrafts().find(draft => draft.state.form?.materials?.[0]?.material?.code === 'FIRST-DRAFT')!
    expect(saved).toBeTruthy()
    wrapper.unmount(); wrappers.splice(wrappers.indexOf(wrapper), 1)
    const reopened = await setup('customer')
    await button(reopened.get(`[data-draft-id="${saved.id}"]`), '继续填写').trigger('click')
    const restored = reopened.get('#im-panel-master')
    expect(field(restored, '物料编码').element).toHaveProperty('value', 'FIRST-DRAFT')
    expect(field(restored, '物料编码').attributes('readonly')).toBeUndefined()
    await field(restored, '物料编码').setValue('FINAL-CODE')
    await restored.get('form').trigger('submit'); await flushPromises()
    expect(mocks.api.command.mock.calls[0]![0]).toMatchObject({ action: 'product_save', data: { materials: [{ material_id: 'm', material: { code: 'FINAL-CODE' } }] } })
    data.records.find(row => row.id === 'm')!.data.code = 'FINAL-CODE'
    await button(reopened, '刷新工作区').trigger('click')
    await button(restored, '编辑').trigger('click'); await button(restored, '编辑物料资料').trigger('click')
    expect(field(restored, '物料编码').attributes('readonly')).toBeDefined()
  })

  it('reuses an existing material without cloning it or offering a duplicate recipe choice', async () => {
    const panel = (await setup()).get('#im-panel-master')
    await button(panel, '新增货号').trigger('click')
    await button(panel, '选用已有物料').trigger('click')
    await panel.get('[aria-label="用量物料"]').setValue('m')
    await panel.get('[aria-label="单件用量"]').setValue('3')
    await button(panel, '选用已有物料').trigger('click')
    expect(panel.findAll('[aria-label="用量物料"]')[1]!.text()).not.toContain('SCREW')
    await button(panel.findAll('.im-recipe-card')[1]!, '删除物料资料').trigger('click')
    await panel.get('form').trigger('submit'); await flushPromises()
    expect(mocks.api.command.mock.calls[0]![0].data.materials).toEqual([{ material_id: 'm', usage: '3' }])
  })

  it('keeps the surviving material fields and image bound to their own stable row after removal', async () => {
    const panel = (await setup()).get('#im-panel-master')
    await button(panel, '添加物料').trigger('click')
    const newCard = panel.findAll('.im-recipe-card')[1]!
    await field(newCard, '物料名称').setValue('保留这一行')
    await field(newCard, '数量单位').setValue('pcs')
    await button(panel.findAll('.im-recipe-card')[0]!, '移除关联').trigger('click')
    expect((field(panel, '物料名称').element as HTMLInputElement).value).toBe('保留这一行')
    expect((field(panel, '数量单位').element as HTMLInputElement).value).toBe('pcs')
    expect(panel.findAll('.im-recipe-card')).toHaveLength(1)
  })

  it('opens an existing product form directly after its own row, before the next product', async () => {
    data.records.unshift(record('new-product', 'product', { ...productDefaults, code: '40149', customer: 'CLIENT', materials: [] }))
    const panel = (await setup()).get('#im-panel-master')
    const body = panel.findAll('tbody').find(item => item.text().includes('40149'))!
    await button(body, '添加物料').trigger('click')
    expect(body.find('form').exists()).toBe(true)
    expect(body.findAll('tr')).toHaveLength(2)
    expect(panel.findAll('tbody').find(item => item.text().includes('ITEM'))!.find('form').exists()).toBe(false)
    expect((field(body, '成品货号').element as HTMLInputElement).value).toBe('40149')
    expect(body.findAll('.im-recipe-card')).toHaveLength(1)
  })

  it('orders material inputs like the shipment sheet and removes duplicate manual billing controls', async () => {
    const panel = (await setup()).get('#im-panel-master')
    await button(panel, '添加物料').trigger('click')
    const card = panel.findAll('.im-recipe-card')[1]!
    const names = card.findAll('label').map(item => item.get('span').text().replace(/\s*\*$/, ''))
    expect(names).toEqual(['每件成品用量', '物料名称', '英文名称', '规格', '类别', '报关单位', '数量单位', '物料图片', '产品用途', '供应商', '单价', '币种', '出口公司', '物料编码', '使用部门', '单个净重（kg）', '采购备料自然日'])
    expect(names).not.toContain('计费单位')
    expect(names).not.toContain('计费换算系数')
    expect(field(card, '供应商').attributes('list')).toBeTruthy()
    expect(field(card, '出口公司').attributes('list')).toBeTruthy()
    expect(field(card, '报关单位').element.tagName).toBe('SELECT')
    expect(field(card, '产品用途').element.tagName).toBe('SELECT')
  })

  it('preserves a failed product delete draft and closes only its own form after retry', async () => {
    const wrapper = await setup(), panel = wrapper.get('#im-panel-master')
    await button(panel, '编辑').trigger('click')
    await field(panel, '成品名称').setValue('尚未保存的名称')
    mocks.api.command.mockRejectedValueOnce(new Error('网络中断'))
    await button(panel, '删除货号').trigger('click'); await flushPromises()
    expect(panel.find('form').exists()).toBe(true)
    const original = mocks.api.command.mock.calls[0]![0]
    expect(original).toMatchObject({ action: 'product_delete', entity_id: 'p', expected_version: 3, data: {} })
    await button(wrapper, '重试原操作').trigger('click'); await flushPromises()
    expect(mocks.api.command.mock.calls[1]![0]).toEqual(original)
    expect(panel.find('form').exists()).toBe(false)
  })

  it('separates the product row deletion from material card deletion and can undo unsaved material input', async () => {
    const panel = (await setup()).get('#im-panel-master')
    await button(panel, '添加物料').trigger('click')
    const form = panel.get('form'), card = panel.findAll('.im-recipe-card')[1]!
    expect(form.findAll('button').some(item => item.text() === '删除货号')).toBe(false)
    expect(button(panel.get('[data-product-id="p"] > tr'), '删除货号').exists()).toBe(true)
    await field(panel, '成品名称').setValue('保留货号资料')
    await field(card, '物料编码').setValue('NEW-MAT')
    await field(card, '物料名称').setValue('只删此物料')
    await card.get('[aria-label="单件用量"]').setValue('2.12345678')
    await button(card, '删除物料资料').trigger('click')
    expect(panel.findAll('.im-recipe-card')).toHaveLength(1)
    expect(mocks.api.command).not.toHaveBeenCalled()
    expect((field(panel, '成品名称').element as HTMLInputElement).value).toBe('保留货号资料')
    expect(panel.get('.im-pending-material-deletions').text()).toContain('NEW-MAT')
    await button(panel, '撤销删除').trigger('click')
    expect((field(panel.findAll('.im-recipe-card')[1]!, '物料名称').element as HTMLInputElement).value).toBe('只删此物料')
    expect(panel.findAll('[aria-label="单件用量"]')[1]!.element).toHaveProperty('value', '2.12345678')
    expect(panel.find('.im-pending-material-deletions').exists()).toBe(false)
  })

  it('cancels material deletion without removing a card or changing other input', async () => {
    const panel = (await setup()).get('#im-panel-master')
    await button(panel, '编辑').trigger('click')
    await panel.get('[aria-label="单件用量"]').setValue('7.12345678')
    vi.mocked(window.confirm).mockReturnValue(false)
    await button(panel.get('.im-recipe-card'), '删除物料资料').trigger('click')
    expect(panel.findAll('.im-recipe-card')).toHaveLength(1)
    expect(panel.get('[aria-label="单件用量"]').element).toHaveProperty('value', '7.12345678')
    expect(mocks.api.command).not.toHaveBeenCalled()
  })

  it('keeps staged new material images and decimals across product switching and reopening before undo', async () => {
    data.records.push(record('p2', 'product', { ...productDefaults, code: 'SECOND', customer: 'CLIENT', materials: [] }))
    const wrapper = await setup(), panel = wrapper.get('#im-panel-master')
    await button(panel.get('[data-product-id="p"]'), '添加物料').trigger('click')
    const card = panel.findAll('.im-recipe-card')[1]!
    await field(card, '物料编码').setValue('IMAGE-DELETE')
    await field(card, '物料名称').setValue('可撤销图片物料')
    await card.get('[aria-label="单件用量"]').setValue('2.12345678')
    const input = card.get('input[type="file"]')
    Object.defineProperty(input.element, 'files', { value: [new File([new Uint8Array([137, 80, 78, 71])], 'kept.png', { type: 'image/png' })], configurable: true })
    await input.trigger('change')
    await vi.waitFor(() => expect(card.find('img').exists()).toBe(true)); await flushPromises()
    const image = card.get('img').attributes('src')
    await button(card, '删除物料资料').trigger('click')
    await button(panel.get('[data-product-id="p2"]'), '添加物料').trigger('click')
    await field(panel, '物料名称').setValue('另一个货号的输入')
    wrapper.unmount(); wrappers.splice(wrappers.indexOf(wrapper), 1)
    const reopened = await setup('customer')
    await button(reopened.get('[data-draft-id="master:product:p"]'), '继续填写').trigger('click')
    const restored = reopened.get('#im-panel-master')
    await button(restored, '撤销删除').trigger('click')
    expect((field(restored, '物料名称').element as HTMLInputElement).value).toBe('可撤销图片物料')
    expect(restored.get('img').attributes('src')).toBe(image)
    expect(restored.findAll('[aria-label="单件用量"]')[1]!.element).toHaveProperty('value', '2.12345678')
    expect(storedDrafts().find(saved => saved.id === 'master:product:p2')!.state.form.materials[0].material.name).toBe('另一个货号的输入')
  })

  it('submits a saved material deletion with its original revision and keeps the product identity', async () => {
    const panel = (await setup()).get('#im-panel-master')
    await button(panel, '编辑').trigger('click')
    await button(panel, '编辑物料资料').trigger('click')
    await field(panel, '供应商').setValue('撤销删除时应保留的内容')
    await button(panel.get('.im-recipe-card'), '删除物料资料').trigger('click')
    expect(mocks.api.command).not.toHaveBeenCalled()
    await button(panel, '撤销删除').trigger('click')
    expect((field(panel, '供应商').element as HTMLInputElement).value).toBe('撤销删除时应保留的内容')
    await button(panel.get('.im-recipe-card'), '删除物料资料').trigger('click')
    await panel.get('form').trigger('submit'); await flushPromises()
    expect(mocks.api.command).toHaveBeenCalledTimes(1)
    expect(mocks.api.command.mock.calls[0]![0]).toMatchObject({ action: 'product_save', entity_id: 'p', expected_version: 3,
      data: { code: 'ITEM', customer: 'CLIENT', materials: [], material_deletions: [{ material_id: 'm', expected_version: 3 }] } })
    expect(mocks.api.command.mock.calls[0]![0].data.material_deletions[0]).not.toHaveProperty('material')
  })

  it('retains pending material deletions after reopening with their old versions and exact retry ownership', async () => {
    const wrapper = await setup(), panel = wrapper.get('#im-panel-master')
    await button(panel, '编辑').trigger('click')
    await button(panel.get('.im-recipe-card'), '删除物料资料').trigger('click')
    await flushPromises()
    wrapper.unmount(); wrappers.splice(wrappers.indexOf(wrapper), 1)
    data.records.find(row => row.id === 'm')!.version = 9
    const reopened = await setup('customer')
    await button(reopened, '继续填写').trigger('click')
    const restored = reopened.get('#im-panel-master')
    expect(restored.get('.im-pending-material-deletions').text()).toContain('SCREW')
    expect(restored.find('.im-recipe-card').exists()).toBe(false)
    mocks.api.command.mockRejectedValueOnce(new Error('网络中断'))
    await restored.get('form').trigger('submit'); await flushPromises()
    const original = mocks.api.command.mock.calls[0]![0]
    expect(original).toMatchObject({ action: 'product_save', expected_version: 3, data: { material_deletions: [{ material_id: 'm', expected_version: 3 }] } })
    expect(storedDrafts().some(saved => saved.state.form?.material_deletions.length === 1)).toBe(true)
    await button(reopened, '重试原操作').trigger('click')
    expect(mocks.api.command.mock.calls[1]![0]).toEqual(original)
    expect(restored.find('form').exists()).toBe(false)
  })

  it('keeps deletion input and unrelated new materials when the server refuses an in-use material', async () => {
    const panel = (await setup()).get('#im-panel-master')
    await button(panel, '添加物料').trigger('click')
    await field(panel, '物料名称').setValue('其他物料输入不能丢')
    await button(panel.findAll('.im-recipe-card')[0]!, '删除物料资料').trigger('click')
    mocks.api.command.mockRejectedValueOnce({ response: { status: 409 }, message: '该物料已有合同或采购引用' })
    await panel.get('form').trigger('submit'); await flushPromises()
    expect(panel.get('.im-pending-material-deletions').text()).toContain('SCREW')
    expect((field(panel, '物料名称').element as HTMLInputElement).value).toBe('其他物料输入不能丢')
    expect(storedDrafts()[0]!.state.form.material_deletions[0].delete_version).toBe(3)
    await button(panel, '撤销删除').trigger('click')
    expect(panel.findAll('.im-recipe-card')).toHaveLength(2)
  })

  it('treats unlinking as recipe-only and never sends it as a material deletion', async () => {
    const panel = (await setup()).get('#im-panel-master')
    await button(panel, '编辑').trigger('click')
    await button(panel.get('.im-recipe-card'), '移除关联').trigger('click')
    await panel.get('form').trigger('submit'); await flushPromises()
    expect(mocks.api.command.mock.calls[0]![0]).toMatchObject({ action: 'product_save', entity_id: 'p', data: { materials: [], material_deletions: [] } })
  })

  it('restores a deleted material by its own version without changing or closing a product draft', async () => {
    data.records.push(record('gone', 'material', { ...materialDefaults, code: 'GONE', name: '已删除物料', deleted: true }))
    const panel = (await setup()).get('#im-panel-master')
    await button(panel, '添加物料').trigger('click')
    await field(panel, '物料名称').setValue('保留打开的物料')
    await button(panel, '恢复物料资料').trigger('click')
    expect(mocks.api.command.mock.calls[0]![0]).toMatchObject({ action: 'material_restore', entity_id: 'gone', expected_version: 3, data: {} })
    expect((field(panel, '物料名称').element as HTMLInputElement).value).toBe('保留打开的物料')
    expect(storedDrafts().some(saved => saved.state.form?.materials.some((item: Data) => item.material?.name === '保留打开的物料'))).toBe(true)
  })

  it('cancels deleting a customer without losing the entered notes or sending a command', async () => {
    const panel = (await setup('customer')).get('#im-panel-master')
    await button(panel, '编辑客人').trigger('click')
    await field(panel, '备注').setValue('保留填写内容')
    vi.mocked(window.confirm).mockReturnValue(false)
    await button(panel, '删除客人').trigger('click')
    expect((field(panel, '备注').element as HTMLTextAreaElement).value).toBe('保留填写内容')
    expect(mocks.api.command).not.toHaveBeenCalled()
  })

  it('restores a deleted master by its current version without exposing it to business choices', async () => {
    data.records.find(row => row.id === 'p')!.data.deleted = true
    const panel = (await setup()).get('#im-panel-master')
    expect(panel.find('tbody').exists()).toBe(false)
    await button(panel, '恢复货号').trigger('click'); await flushPromises()
    expect(mocks.api.command.mock.calls[0]![0]).toMatchObject({ action: 'product_restore', entity_id: 'p', expected_version: 3 })
  })

  it('preserves order identity while sending explicit quantity, date and amendment reason', async () => {
    const panel = (await setup()).get('#im-panel-demand')
    await button(panel, '编辑合同').trigger('click')
    expect(field(panel, '客户').attributes('disabled')).toBeDefined()
    expect(field(panel, '印尼接收方').attributes('disabled')).toBeDefined()
    await field(panel, '合同成品数量').setValue('12')
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
    const panel = (await setup()).get('[data-allocation-workspace]')
    await button(panel, '选择分配 PO').trigger('click')
    await field(panel, '目标客户 PO／合同').setValue('o')
    await field(panel, '目标物料需求').setValue('d')
    await field(panel, '分配正常量').setValue('5.00000001')
    await field(panel, '分配备品量').setValue('1')
    await panel.get('form').trigger('submit'); await flushPromises()
    expect(mocks.api.command.mock.calls[0]![0]).toMatchObject({ action: 'allocate', entity_id: null, expected_version: 0, data: { order_id: 'o', demand_id: 'd', supply_id: 's', normal_quantity: '5.00000001', spare_quantity: '1' } })
  })

  it('rebinds only the entered unshipped normal and spare amounts with the original allocation revision', async () => {
    const panel = (await setup()).get('[data-allocation-workspace]')
    await button(panel, '未发改绑').trigger('click')
    await field(panel, '目标客户 PO／合同').setValue('o2')
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
    expect(command).toMatchObject({ action: 'supply_save', entity_id: null, data: { material_id: 'm', purchase_no: 'P-NEW', normal_quantity: '95', spare_quantity: '5', promised_date: null, price: '4', billing_weight_source: 'net_weight_kg' } })
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
    await button(wrapper.get('#im-panel-master'), '添加物料').trigger('click')
    await field(wrapper.get('#im-panel-master'), '物料名称').setValue('上一厂区私有草稿')
    await wrapper.get('#im-tab-board').trigger('keydown', { key: 'ArrowRight' })
    expect(wrapper.get('#im-tab-supply').attributes('aria-selected')).toBe('true')
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

describe('contract board follow-up entries', () => {
  async function details(wrapper: Awaited<ReturnType<typeof setup>>) {
    await wrapper.get('#im-tab-board').trigger('click')
    const panel = wrapper.get('#im-panel-board')
    await button(panel, '明细 ↓').trigger('click')
    return panel
  }
  it('shows every newly added material even when codes match and defaults are already complete', async () => {
    addRecipeMaterials()
    const wrapper = await setup(), board = await details(wrapper)
    expect(board.text()).toContain('新增 3 种物料待同步')
    expect(board.findAll('[data-pending-material]')).toHaveLength(3)
    expect(board.get('.im-contract-detail').text()).toContain('蓝色拉杆')
    expect(board.get('.im-contract-detail').text()).toContain('新增，待同步')
    await button(board, '填写／更新本合同计划').trigger('click')
    const editor = board.get('form[aria-label="当前合同计划参数"]')
    expect(editor.findAll('input[aria-label$="采购周期"]')).toHaveLength(4)
    expect(editor.get('input[aria-label="SCREW · 绿色拉杆 采购周期"]').element).toHaveProperty('value', '10')
    expect(editor.get('input[aria-label="SCREW · 蓝色拉杆 采购周期"]').element).toHaveProperty('value', '11')
    expect(editor.text()).toContain('本次补入 3 种新物料')
  })
  it('allows saving new materials before their procurement cycles are known', async () => {
    addRecipeMaterials()[2]!.data.procurement_days = null
    const wrapper = await setup(), board = await details(wrapper)
    await button(board, '填写／更新本合同计划').trigger('click')
    const editor = board.get('form[aria-label="当前合同计划参数"]')
    const cycle = editor.get('input[aria-label="SCREW · 推杆 采购周期"]')
    expect(cycle.element).toHaveProperty('value', '')
    expect(cycle.attributes('required')).toBeUndefined()
    await editor.trigger('submit'); await flushPromises()
    expect(mocks.api.command.mock.calls[0]![0].data.materials[3]).toMatchObject({ material_id: 'new-m-2', procurement_days: null })
  })
  it('refreshes an older planning draft without losing entered parameters or another contract draft', async () => {
    let wrapper = await setup(), board = await details(wrapper)
    await button(board, '填写／更新本合同计划').trigger('click')
    await field(board.get('form'), '日产能').setValue('222')
    await board.get('input[aria-label="SCREW · 螺丝 采购周期"]').setValue('29'); await flushPromises()
    await button(board, '明细 ↓').trigger('click')
    await button(board, '填写／更新本合同计划').trigger('click')
    await field(board.get('form'), '日产能').setValue('333'); await flushPromises()
    const otherDraft = structuredClone(storedDrafts().find(d => d.state.editing?.id === 'o2'))
    wrapper.unmount(); wrappers.splice(wrappers.indexOf(wrapper), 1)
    addRecipeMaterials()
    wrapper = await setup(); board = wrapper.get('#im-panel-board')
    const saved = storedDrafts().find(d => d.state.editing?.id === 'o')!
    await button(wrapper.get(`[data-draft-id="${saved.id}"]`), '继续填写').trigger('click')
    let editor = board.get('form[aria-label="当前合同计划参数"]')
    expect(button(editor, '保存并更新本合同').attributes('disabled')).toBeDefined()
    await button(editor, '载入最新物料与版本').trigger('click')
    editor = board.get('form[aria-label="当前合同计划参数"]')
    expect(field(editor, '日产能').element).toHaveProperty('value', '222')
    expect(editor.get('input[aria-label="SCREW · 螺丝 采购周期"]').element).toHaveProperty('value', '29')
    expect(editor.findAll('input[aria-label$="采购周期"]')).toHaveLength(4)
    expect(button(editor, '保存并更新本合同').attributes('disabled')).toBeUndefined()
    expect(storedDrafts().find(d => d.state.editing?.id === 'o2')).toEqual(otherDraft)
    expect(mocks.api.command).not.toHaveBeenCalled()
  })
  it('edits plan and procurement in this contract, carries existing defaults and updates only its plan', async () => {
    const wrapper = await setup(), board = await details(wrapper)
    await board.get('button[aria-label="维护 SCREW 的采购周期"]').trigger('click'); await flushPromises()
    const editor = board.get('form[aria-label="当前合同计划参数"]')
    expect(wrapper.get('#im-tab-board').attributes('aria-selected')).toBe('true')
    expect(field(editor, '日产能').element).toHaveProperty('value', '100')
    expect(editor.get('input[aria-label="SCREW · 螺丝 采购周期"]').element).toHaveProperty('value', '15')
    await field(editor, '日产能').setValue('200')
    await editor.get('input[aria-label="SCREW · 螺丝 采购周期"]').setValue('21')
    mocks.api.command.mockImplementationOnce(async command => {
      const existing = data.records.find(row => row.id === command.entity_id)!
      data.board[0]!.plan!.required_date = '2026-11-03'
      return { record: { ...existing, version: 4 } }
    })
    await editor.trigger('submit'); await flushPromises()
    expect(mocks.api.command).toHaveBeenCalledOnce()
    expect(mocks.api.command.mock.calls[0]![0]).toMatchObject({ action: 'order_plan_save', entity_id: 'o', expected_version: 3,
      data: { product_id: 'p', product_version: 3, daily_capacity: '200', transport_days: 25, materials: [{ material_id: 'm', expected_version: 3, procurement_days: 21 }] } })
    expect(board.get('.im-contract-detail').text()).toContain('2026/11/03')
    expect(board.find('form[aria-label="当前合同计划参数"]').exists()).toBe(false)
    expect(data.board[1]!.plan!.required_date).toBe('2026-11-02')
    expect(wrapper.get('#im-tab-board').attributes('aria-selected')).toBe('true')
  })
  it('retains a plan draft across bulk synchronization and explicitly adopts the latest contract version', async () => {
    const additions = addRecipeMaterials()
    const wrapper = await setup(), board = await details(wrapper)
    await button(board, '填写／更新本合同计划').trigger('click')
    await field(board.get('form'), '日产能').setValue('777')
    await board.get('input[aria-label="SCREW · 螺丝 采购周期"]').setValue('27'); await flushPromises()
    const saved = structuredClone(storedDrafts().find(d => d.state.editing?.id === 'o')!)
    await wrapper.get('#im-tab-supply').trigger('click')
    const warehouse = wrapper.get('section[aria-label="仓库实收导入"]')
    await field(warehouse, '实收客户').setValue('CLIENT')
    await button(warehouse, '下载实收导入模板').trigger('click')
    mocks.api.command.mockImplementationOnce(async () => {
      for (const order of data.board) order.demands.push(...additions.map((m, i) => ({ ...order.demands[0]!, id: `${order.id}-plan-${i}`, material_id: m.id, name: m.data.name })))
      data.board = structuredClone(data.board)
      data.records = data.records.map(r => ['o', 'o2'].includes(r.id) ? { ...r, version: 4 } : r)
      return { record: data.records.find(r => r.id === 'o')! }
    })
    await button(wrapper.get('form[aria-label="下载订单实收模板"]'), '更新全部合同物料（2 张）').trigger('click')
    expect(storedDrafts().find(d => d.id === saved.id)).toEqual(saved)
    await button(wrapper.get(`[data-draft-id="${saved.id}"]`), '继续填写').trigger('click')
    const editor = board.get('form[aria-label="当前合同计划参数"]')
    expect(button(editor, '保存并更新本合同').attributes('disabled')).toBeDefined()
    await button(editor, '载入最新物料与版本').trigger('click')
    expect(field(editor, '日产能').element).toHaveProperty('value', '777')
    expect(editor.get('input[aria-label="SCREW · 螺丝 采购周期"]').element).toHaveProperty('value', '27')
    await editor.trigger('submit'); await flushPromises()
    expect(mocks.api.command.mock.calls[1]![0]).toMatchObject({ action: 'order_plan_save', entity_id: 'o', expected_version: 4, data: { daily_capacity: '777' } })
  })
  it('keeps planning drafts independent across contracts, collapse and page reopen', async () => {
    let wrapper = await setup(), board = await details(wrapper)
    await board.get('button[aria-label="维护 SCREW 的采购周期"]').trigger('click'); await flushPromises()
    await field(board.get('form'), '日产能').setValue('222'); await flushPromises()
    await button(board, '明细 ↓').trigger('click')
    await board.get('button[aria-label="维护 SCREW 的采购周期"]').trigger('click'); await flushPromises()
    await field(board.get('form'), '日产能').setValue('333'); await flushPromises()
    expect(storedDrafts().filter(item => draftKind(item.id) === 'planning')).toHaveLength(2)
    wrapper.unmount(); wrappers.splice(wrappers.indexOf(wrapper), 1)
    wrapper = await setup(); board = wrapper.get('#im-panel-board')
    for (const [id, value] of [['o', '222'], ['o2', '333']]) {
      const saved = storedDrafts().find(item => item.state.editing?.id === id && draftKind(item.id) === 'planning')!
      await button(wrapper.get(`[data-draft-id="${saved.id}"]`), '继续填写').trigger('click')
      expect(field(board.get('form'), '日产能').element).toHaveProperty('value', value)
    }
    expect(mocks.api.command).not.toHaveBeenCalled()
  })
  it('filters procurement records and opens only a uniquely linked supplier reply', async () => {
    data.records = data.records.filter(row => row.id !== 'a-expected')
    data.records.push(record('unrelated', 'supply', { ...supplyDefaults, material_id: 'other-material', purchase_no: 'OTHER' }))
    const wrapper = await setup(), board = await details(wrapper)
    await board.get('button[aria-label="维护 SCREW 的供应商回复"]').trigger('click'); await flushPromises()
    const supply = wrapper.get('#im-panel-supply')
    expect(wrapper.get('#im-tab-supply').attributes('aria-selected')).toBe('true')
    expect(supply.get('[data-manual-supply]').isVisible()).toBe(true)
    expect(supply.find('[data-supply-id="unrelated"]').exists()).toBe(false)
    expect(supply.get('[data-supply-id="s"]').text()).toContain('本合同已关联')
    expect(supply.get('[data-supply-id="s-expected"]').text()).toContain('未关联本合同')
    expect(supply.get('form').text()).toContain('P-1')
    await field(supply, '供应商回复回料日期').setValue('2026-11-01')
    await field(supply, '回复来源／变更原因').setValue('供应商邮件确认')
    await supply.get('form').trigger('submit'); await flushPromises()
    expect(mocks.api.command.mock.calls[0]![0]).toMatchObject({ action: 'supply_reply', entity_id: 's', expected_version: 3, data: { promised_date: '2026-11-01', reason: '供应商邮件确认' } })
  })
  it('requires choosing a purchase when no supply is linked and keeps the prior reply draft', async () => {
    const wrapper = await setup(), board = await details(wrapper)
    await board.get('button[aria-label="维护 SCREW 的供应商回复"]').trigger('click'); await flushPromises()
    const supply = wrapper.get('#im-panel-supply')
    expect(supply.get('[data-manual-supply]').find('form').exists()).toBe(false)
    await button(supply.get('[data-supply-id="s"]'), '更新回复').trigger('click')
    await field(supply, '回复来源／变更原因').setValue('未写完的回复'); await flushPromises()
    await wrapper.get('#im-tab-board').trigger('click')
    await button(board, '明细 ↓').trigger('click')
    await board.get('button[aria-label="维护 SCREW 的供应商回复"]').trigger('click'); await flushPromises()
    expect(supply.get('[data-manual-supply]').find('form').exists()).toBe(false)
    expect(supply.get('[aria-label="供应商回复填写指引"]').text()).toContain('C-2')
    expect(supply.text()).toContain('未关联批次不会自动算作本合同回复')
    expect(storedDrafts().some(saved => saved.state.selected?.id === 's' && saved.state.reason === '未写完的回复')).toBe(true)
    await button(supply.get('[data-supply-id="s-expected"]'), '更新回复').trigger('click')
    expect(supply.get('form').text()).toContain('P-2')
    expect(field(supply, '回复来源／变更原因').element).toHaveProperty('value', '')
    expect(mocks.api.command).not.toHaveBeenCalled()
  })
  it('prefills the material when a procurement record is missing, without creating one automatically', async () => {
    data.records = data.records.filter(row => !['supply', 'allocation'].includes(row.kind))
    const wrapper = await setup(), board = await details(wrapper)
    await board.get('button[aria-label="维护 SCREW 的供应商回复"]').trigger('click'); await flushPromises()
    const supply = wrapper.get('#im-panel-supply')
    expect(supply.text()).toContain('该物料暂无采购批次')
    await button(supply, '登记采购／回料批次').trigger('click')
    expect(field(supply, '物料').element).toHaveProperty('value', 'm')
    expect(mocks.api.command).not.toHaveBeenCalled()
  })
  it('keeps follow-up editing unavailable to read-only users', async () => {
    data.permissions = ['read']
    const wrapper = await setup(), board = await details(wrapper)
    for (const label of ['维护 SCREW 的采购周期', '维护 SCREW 的供应商回复']) expect(board.get(`button[aria-label="${label}"]`).attributes('disabled')).toBeDefined()
    expect(button(board, '填写／更新本合同计划').attributes('disabled')).toBeDefined()
    expect(mocks.api.command).not.toHaveBeenCalled()
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
  it('selects all eligible rows, preserves the choice as a draft and clears it without importing', async () => {
    const partial = preview(); partial.data.status = 'partial'
    partial.data.rows.push({ ...mainOrder, index: 12, source_sheet: 'Sheet1', source_row: 25, blocked: false, imported_order_id: 'existing-order' })
    partial.data.rows.push({ ...mainOrder, index: 13, source_sheet: 'Sheet1', source_row: 26, blocked: false })
    mocks.api.preview.mockResolvedValue({ record: partial })
    const panel = await upload(await setup())
    await panel.get('input[aria-label="选择来源行 26"]').setValue(true)
    await button(panel, '全选可导入行').trigger('click')
    expect(panel.findAll<HTMLInputElement>('input[type="checkbox"]').map(input => input.element.checked)).toEqual([true, false, false, true])
    expect(button(panel, '确认导入选中 2 行').attributes('disabled')).toBeUndefined()
    expect(button(panel, '全选可导入行').attributes('disabled')).toBeDefined()
    expect(storedDrafts().find(saved => draftKind(saved.id) === 'import')?.state.selected).toEqual([7, 13])
    expect(mocks.api.command).not.toHaveBeenCalled()
    await button(panel, '取消全选').trigger('click')
    expect(panel.findAll<HTMLInputElement>('input[type="checkbox"]').every(input => !input.element.checked)).toBe(true)
    expect(button(panel, '确认导入选中 0 行').attributes('disabled')).toBeDefined()
    expect(button(panel, '取消全选').attributes('disabled')).toBeDefined()
    expect(mocks.api.command).not.toHaveBeenCalled()
    await button(panel, '全选可导入行').trigger('click')
    await button(panel, '确认导入选中 2 行').trigger('click')
    expect(mocks.api.command.mock.calls[0]![0]).toMatchObject({ action: 'import_confirm', entity_id: 'import', data: { indexes: [7, 13] } })
  })
  it('disables bulk selection when no eligible rows remain', async () => {
    const blocked = preview(); blocked.data.rows[0].imported_order_id = 'existing-order'
    mocks.api.preview.mockResolvedValue({ record: blocked })
    const panel = await upload(await setup())
    expect(button(panel, '全选可导入行').attributes('disabled')).toBeDefined()
    expect(button(panel, '取消全选').attributes('disabled')).toBeDefined()
  })
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
    await button(panel, '全选可导入行').trigger('click')
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
    expect(panel.findAll('button').some(item => ['全选可导入行', '取消全选'].includes(item.text()))).toBe(false)
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

  it('opens an empty shipment for another recipient while preserving the original packing draft', async () => {
    const panel = (await setup()).get('#im-panel-shipment')
    await button(panel, '新建出货草稿').trigger('click')
    await field(panel, '客户').setValue('CLIENT')
    await panel.get('input[type="checkbox"]').setValue(true)
    await button(panel, '添加包装组').trigger('click')
    await field(panel, '本次唯一接收方').setValue('RRM'); await flushPromises()
    expect(panel.find('input[aria-label="本次正常量"]').exists()).toBe(false)
    expect(panel.text()).not.toContain('包装组 1')
    expect(panel.findAll('input[type="checkbox"]')).toHaveLength(1)
    expect(storedDrafts().find(item => item.state.form?.recipient === 'RRI')!.state.form.packages).toHaveLength(1)
  })

  it('shows real package facts before confirmation and keeps the draft after server validation fails', async () => {
    data.records.push(shipment())
    const wrapper = await setup(); const panel = wrapper.get('#im-panel-shipment')
    await button(panel, '核对并确认出货').trigger('click')
    expect(panel.text()).toContain('27 × 14.5 × 27.3')
    expect(panel.text()).toContain('PALLET-1')
    expect(panel.text()).toContain('1 箱')
    expect(panel.text()).toContain('重复下载不会再次记账')
    await panel.get('form input[type=checkbox]').setValue(true)
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
  { name: '货号下的物料资料和单重', area: 'master', prepare: async panel => { await button(panel, '货号与物料').trigger('click'); await button(panel, '添加物料').trigger('click'); await field(panel, '物料名称').setValue('未保存物料'); await field(panel, '单个净重（kg）').setValue('0.006') } },
  { name: '货号与物料', area: 'master', prepare: async panel => { await button(panel, '维护客人货号').trigger('click'); await button(panel, '编辑').trigger('click'); await panel.get('input[aria-label="单件用量"]').setValue('7') } },
  { name: '合同交付批次', area: 'demand', prepare: async panel => { await button(panel, '新增合同需求').trigger('click'); await field(panel, '客户').setValue('CLIENT'); await field(panel, '成品货号').setValue('ITEM'); await field(panel, '客户合同号').setValue('未保存合同') } },
  { name: '调整物料需求', area: 'demand', prepare: async panel => { await button(panel, '调整需求').trigger('click'); await field(panel, '调整后的最终需求量').setValue('43'); await field(panel, '业务原因').setValue('需求草稿') } },
  { name: '重新生成需求', area: 'demand', prepare: async panel => { await button(panel, '重新生成需求').trigger('click'); await field(panel, '业务原因').setValue('重算草稿') } },
  { name: '分配供应', area: 'supply', prepare: async panel => { await button(panel, '已回料分配 PO').trigger('click'); await button(panel, '选择分配 PO').trigger('click'); await field(panel, '目标客户 PO／合同').setValue('o'); await field(panel, '目标物料需求').setValue('d'); await field(panel, '分配正常量').setValue('8') }, submit: async panel => panel.get('[data-allocation-workspace] form').trigger('submit') },
  { name: '未发物料改绑', area: 'supply', prepare: async panel => { await button(panel, '已回料分配 PO').trigger('click'); await button(panel, '未发改绑').trigger('click'); await field(panel, '目标客户 PO／合同').setValue('o2'); await field(panel, '目标物料需求').setValue('d2'); await field(panel, '转走正常量').setValue('2'); await field(panel, '业务原因').setValue('改绑草稿') }, submit: async panel => panel.get('[data-allocation-workspace] form').trigger('submit') },
  { name: '采购和回料数量', area: 'supply', prepare: async panel => { await button(panel, '登记采购／回料批次').trigger('click'); await field(panel, '物料').setValue('m'); await field(panel, '采购单号').setValue('未保存采购单'); await field(panel, '正常量').setValue('95') } },
  { name: '供应商回复', area: 'supply', prepare: async panel => { await button(panel, '更新回复').trigger('click'); await field(panel, '供应商回复回料日期').setValue('2026-11-05'); await field(panel, '回复来源／变更原因').setValue('回复草稿') } },
  { name: '船务入库', area: 'supply', prepare: async panel => { await button(panel, '船务确认入库').trigger('click'); await field(panel, '实际回河源日期').setValue('2026-11-06') } },
  { name: '出货资料补全', area: 'supply', prepare: async panel => { await button(panel, '补全出货资料').trigger('click'); await field(panel, '资料补全原因').setValue('补全原因草稿') } },
  { name: '出货数量和包装', area: 'shipment', prepare: async panel => { await button(panel, '新建出货草稿').trigger('click'); await field(panel, '客户').setValue('CLIENT'); await panel.get('input[type="checkbox"]').setValue(true); await panel.get('input[aria-label="本次正常量"]').setValue('9'); await button(panel, '添加包装组').trigger('click'); await field(panel, '包装组名称／箱号').setValue('混箱草稿'); await field(panel, '出货备注').setValue('出货草稿备注') } },
  { name: '出货确认核对', area: 'shipment', seed: () => { data.records.push(shipment()) }, prepare: async panel => { await button(panel, '核对并确认出货').trigger('click'); await panel.get('form input[type=checkbox]').setValue(true) } },
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
describe('separate product material drafts', () => {
  function twoProducts() {
    data.records.find(row => row.id === 'p')!.data.code = '40027'
    data.records.push(record('p2', 'product', { ...productDefaults, code: '40149', customer: 'CLIENT', materials: [] }))
  }
  async function addDraft(panel: Pick<DOMWrapper<Element>, 'get' | 'findAll'>, id: string, name: string) {
    await button(panel.get(`[data-product-id="${id}"]`), '添加物料').trigger('click'); await flushPromises()
    const card = panel.findAll('.im-recipe-card').at(-1)!
    await field(card, '物料编码').setValue(`MAT-${id}`)
    await field(card, '物料名称').setValue(name)
    await field(card, '数量单位').setValue('pcs')
    await card.get('[aria-label="单件用量"]').setValue('2.12345678')
    await flushPromises()
    return card
  }
  const stored = () => [...savedBuckets.values()][0]!.drafts

  it('keeps both product drafts, images and precise usage when switching and reopening the page', async () => {
    twoProducts()
    const wrapper = await setup(), panel = wrapper.get('#im-panel-master')
    const card = await addDraft(panel, 'p', '40027 的物料')
    const file = new File([new Uint8Array([137, 80, 78, 71])], 'material.png', { type: 'image/png' })
    const input = card.get('input[type="file"]')
    Object.defineProperty(input.element, 'files', { value: [file], configurable: true })
    await input.trigger('change')
    await vi.waitFor(() => expect(card.find('img').exists()).toBe(true)); await flushPromises()
    const image = card.get('img').attributes('src')
    await addDraft(panel, 'p2', '40149 的物料')
    await button(panel.get('[data-product-id="p"]'), '添加物料').trigger('click'); await flushPromises()
    expect(panel.findAll('.im-recipe-card')).toHaveLength(2)
    expect((field(panel, '物料名称').element as HTMLInputElement).value).toBe('40027 的物料')
    expect(panel.get('img').attributes('src')).toBe(image)
    expect(panel.findAll('[aria-label="单件用量"]').at(-1)!.element).toHaveProperty('value', '2.12345678')
    expect(stored()['master:product:p2']!.state.form.materials[0].material.name).toBe('40149 的物料')
    expect(vi.mocked(window.confirm)).not.toHaveBeenCalled()
    expect(wrapper.get('[data-draft-id="master:product:p"]').text()).toContain('CLIENT · 40027')
    expect(wrapper.get('[data-draft-id="master:product:p2"]').text()).toContain('CLIENT · 40149')
    wrapper.unmount(); wrappers.splice(wrappers.indexOf(wrapper), 1)
    const reopened = await setup('customer')
    await button(reopened.get('[data-draft-id="master:product:p2"]'), '继续填写').trigger('click'); await flushPromises()
    expect((field(reopened.get('#im-panel-master'), '物料名称').element as HTMLInputElement).value).toBe('40149 的物料')
    await button(reopened.get('[data-draft-id="master:product:p"]'), '继续填写').trigger('click'); await flushPromises()
    expect(reopened.get('#im-panel-master img').attributes('src')).toBe(image)
    expect(mocks.api.command).not.toHaveBeenCalled()
  })

  it('clears only the saved product draft and preserves the other one for later editing', async () => {
    twoProducts()
    const wrapper = await setup(), panel = wrapper.get('#im-panel-master')
    await addDraft(panel, 'p', '保留 A'); await addDraft(panel, 'p2', '保留 B')
    await button(panel.get('[data-product-id="p"]'), '编辑').trigger('click'); await flushPromises()
    await panel.get('form').trigger('submit'); await flushPromises()
    expect(mocks.api.command.mock.calls[0]![0]).toMatchObject({ action: 'product_save', entity_id: 'p', expected_version: 3 })
    expect(stored()['master:product:p']).toBeUndefined()
    expect(stored()['master:product:p2']!.state.form.materials[0].material.name).toBe('保留 B')
    expect(wrapper.find('[data-draft-id="master:product:p"]').exists()).toBe(false)
    await button(wrapper.get('[data-draft-id="master:product:p2"]'), '继续填写').trigger('click'); await flushPromises()
    expect((field(panel, '物料名称').element as HTMLInputElement).value).toBe('保留 B')
  })

  it('deletes another product draft without closing or changing the current editor', async () => {
    twoProducts()
    const wrapper = await setup(), panel = wrapper.get('#im-panel-master')
    await addDraft(panel, 'p', '当前 A'); await addDraft(panel, 'p2', '准备删除 B')
    await button(panel.get('[data-product-id="p"]'), '编辑').trigger('click'); await flushPromises()
    await button(wrapper.get('[data-draft-id="master:product:p2"]'), '删除草稿').trigger('click'); await flushPromises()
    expect((field(panel, '物料名称').element as HTMLInputElement).value).toBe('当前 A')
    expect(stored()['master:product:p']).toBeDefined()
    expect(stored()['master:product:p2']).toBeUndefined()
    expect(mocks.api.command).not.toHaveBeenCalled()
  })

  it('preserves a legacy product draft while opening a different product', async () => {
    twoProducts()
    const key = JSON.stringify(['v1', 'user', 1, 'huaxing'])
    savedBuckets.set(key, { format: 1, pending: null, drafts: { master: {
      id: 'master', revision: 'legacy-product-revision', writer: 'previous-version', savedAt: '2026-10-22T00:00:00Z',
      state: { category: 'product', customerFilter: '', editing: { id: 'p', kind: 'product', version: 2 }, form: { ...data.records.find(row => row.id === 'p')!.data, name: '旧版本未提交名称' } },
    } } })
    const wrapper = await setup(), panel = wrapper.get('#im-panel-master')
    await addDraft(panel, 'p2', '新草稿 B')
    await button(panel.get('[data-product-id="p"]'), '编辑').trigger('click'); await flushPromises()
    expect((field(panel, '成品名称').element as HTMLInputElement).value).toBe('旧版本未提交名称')
    expect(stored().master!.state.editing.version).toBe(2)
    expect(stored()['master:product:p']).toBeUndefined()
    await panel.get('form').trigger('submit'); await flushPromises()
    expect(mocks.api.command.mock.calls[0]![0]).toMatchObject({ entity_id: 'p', expected_version: 2 })
    expect(stored().master).toBeUndefined()
    expect(stored()['master:product:p2']).toBeDefined()
  })

  it('keeps separate drafts for multiple new products before either is saved', async () => {
    const wrapper = await setup(), panel = wrapper.get('#im-panel-master')
    await button(panel, '新增货号').trigger('click')
    await field(panel, '成品货号').setValue('NEW-A')
    await field(panel, '客户').setValue('CLIENT'); await flushPromises()
    await button(panel, '新增货号').trigger('click'); await flushPromises()
    await field(panel, '成品货号').setValue('NEW-B')
    await field(panel, '客户').setValue('CLIENT'); await flushPromises()
    const entries = Object.values(stored()).filter(item => item!.id.startsWith('master:new:'))
    expect(entries).toHaveLength(2)
    const first = entries.find(item => item!.state.form.code === 'NEW-A')!
    await button(wrapper.get(`[data-draft-id="${first.id}"]`), '继续填写').trigger('click'); await flushPromises()
    expect((field(panel, '成品货号').element as HTMLInputElement).value).toBe('NEW-A')
    expect(Object.values(stored()).some(item => item!.state.form.code === 'NEW-B')).toBe(true)
    expect(vi.mocked(window.confirm)).not.toHaveBeenCalled()
  })

  it('retries an interrupted product save after reload without resetting the other recovered product', async () => {
    twoProducts()
    const wrapper = await setup(), panel = wrapper.get('#im-panel-master')
    await addDraft(panel, 'p', 'A 待提交'); await addDraft(panel, 'p2', 'B 未提交')
    await button(panel.get('[data-product-id="p"]'), '编辑').trigger('click'); await flushPromises()
    mocks.api.command.mockRejectedValueOnce(new Error('响应中断'))
    await panel.get('form').trigger('submit'); await flushPromises()
    const original = structuredClone(mocks.api.command.mock.calls[0]![0])
    wrapper.unmount(); wrappers.splice(wrappers.indexOf(wrapper), 1)
    const reopened = await setup('customer')
    await button(reopened.get('[data-draft-id="master:product:p2"]'), '继续填写').trigger('click'); await flushPromises()
    await button(reopened, '重试原操作').trigger('click'); await flushPromises()
    expect(mocks.api.command.mock.calls[1]![0]).toEqual(original)
    expect(stored()['master:product:p']).toBeUndefined()
    expect((field(reopened.get('#im-panel-master'), '物料名称').element as HTMLInputElement).value).toBe('B 未提交')
    expect(stored()['master:product:p2']).toBeDefined()
  })

  it('keeps the current inputs visible when storage fails before switching products', async () => {
    twoProducts()
    const wrapper = await setup(), panel = wrapper.get('#im-panel-master')
    await addDraft(panel, 'p', '不能丢的 A')
    vi.spyOn(memoryDatabase, 'update').mockRejectedValueOnce(new Error('storage unavailable'))
    await button(panel.get('[data-product-id="p2"]'), '添加物料').trigger('click'); await flushPromises()
    expect((field(panel, '物料名称').element as HTMLInputElement).value).toBe('不能丢的 A')
    expect(panel.get('[data-product-id="p"]').find('form').exists()).toBe(true)
    expect(stored()['master:product:p2']).toBeUndefined()
    expect(wrapper.text()).toContain('尚未安全保存')
    expect(mocks.api.command).not.toHaveBeenCalled()
  })

  it('keeps equal product codes for different customers in separate draft slots', async () => {
    twoProducts()
    data.records.push(record('client-other', 'customer', { name: 'OTHER', status: 'active' }))
    Object.assign(data.records.find(row => row.id === 'p2')!.data, { code: '40027', customer: 'OTHER' })
    const wrapper = await setup(), panel = wrapper.get('#im-panel-master')
    await addDraft(panel, 'p', 'CLIENT 的物料'); await addDraft(panel, 'p2', 'OTHER 的物料')
    expect(wrapper.get('[data-draft-id="master:product:p"]').text()).toContain('CLIENT · 40027')
    expect(wrapper.get('[data-draft-id="master:product:p2"]').text()).toContain('OTHER · 40027')
    expect(stored()['master:product:p']!.state.form.materials.at(-1).material.name).toBe('CLIENT 的物料')
    expect(stored()['master:product:p2']!.state.form.materials.at(-1).material.name).toBe('OTHER 的物料')
  })

  it('hides all product drafts after a factory change and restores only their original factory bucket', async () => {
    twoProducts()
    mocks.api.workspace.mockImplementation(async factory => factory === 'huaxing' ? data : { ...data, records: [], board: [] })
    const wrapper = await setup(), panel = wrapper.get('#im-panel-master')
    await addDraft(panel, 'p', '华兴 A 私有'); await addDraft(panel, 'p2', '华兴 B 私有')
    mocks.app.activeFactoryId = 'huadeng'; await flushPromises()
    expect(wrapper.findAll('.im-draft-list li')).toHaveLength(0)
    expect(wrapper.find('#im-panel-master form').exists()).toBe(false)
    expect(wrapper.text()).not.toContain('华兴 A 私有')
    expect(wrapper.text()).not.toContain('华兴 B 私有')
    mocks.app.activeFactoryId = 'huaxing'; await flushPromises()
    expect(wrapper.findAll('.im-draft-list li')).toHaveLength(2)
    await button(wrapper.get('[data-draft-id="master:product:p"]'), '继续填写').trigger('click'); await flushPromises()
    expect((field(wrapper.get('#im-panel-master'), '物料名称').element as HTMLInputElement).value).toBe('华兴 A 私有')
  })
})

type RecordFormCase = {
  name: string; kind: 'customer' | 'options' | 'demand' | 'supply' | 'shipment' | 'allocation'; area: string
  seed?: () => void; open: (panel: FormPanel, second: boolean) => Promise<void>
  field: string; values: [string, string]; ids: [string, string]; operation: string; extraKeys?: [string[], string[]]
}
function twoSupplyBatches() {
  data.records.push(record('s-expected2', 'supply', { ...data.records.find(row => row.id === 's-expected')!.data, purchase_no: 'P-3', batch: 'SECOND' }))
}
function twoShipments() { data.records.push(shipment(), { ...shipment(), id: 'shipment2', data: { ...shipment().data, shipment_date: '2026-10-14' } }) }
describe('server document responsibility', () => {
  const person = (id: string, name: string) => ({ id, name, username: id, employment_epoch: 1 })
  function ownedShipment(canTransfer = false) {
    const row = shipment()
    row.responsibility = { uploader: person('user', '跟客甲'), assignee: person('user', '跟客甲'), transfers: [], can_transfer: canTransfer }
    data.records.push(row)
    return row
  }
  it('shows uploader and assignee, and a staff account has no transfer control', async () => {
    ownedShipment()
    const wrapper = await setup('customer'), panel = wrapper.get('#im-panel-shipment')
    expect(panel.get('[data-shipment-id="shipment"]').text()).toContain('上传人：跟客甲')
    expect(panel.get('[data-shipment-id="shipment"]').text()).toContain('负责人：跟客甲')
    expect(panel.findAll('button').some(item => item.text() === '转交')).toBe(false)
  })
  it('locks an open shipment after transfer and preserves the account local draft', async () => {
    ownedShipment()
    const wrapper = await setup('customer'), panel = wrapper.get('#im-panel-shipment')
    await rowAction(panel, '[data-shipment-id="shipment"]', '编辑草稿')
    await field(panel, '出货备注').setValue('转交前尚未提交的装箱备注'); await flushPromises()
    data.records = data.records.filter(row => row.id !== 'shipment')
    await button(wrapper, '刷新工作区').trigger('click')
    expect(panel.text()).toContain('此待办已转交')
    expect(panel.get('form fieldset').attributes('disabled')).toBeDefined()
    await panel.get('form').trigger('submit'); await flushPromises()
    expect(mocks.api.command).not.toHaveBeenCalled()
    expect(storedDrafts().some(item => item.state.form?.remarks === '转交前尚未提交的装箱备注')).toBe(true)
    await button(panel, '新建出货草稿').trigger('click')
    expect(panel.text()).not.toContain('此待办已转交')
    expect(storedDrafts().some(item => item.state.form?.remarks === '转交前尚未提交的装箱备注')).toBe(true)
  })
  it('a supervisor searches eligible people and sends a versioned reasoned transfer', async () => {
    const row = ownedShipment(true)
    mocks.api.assignees.mockResolvedValue({ people: [person('bob', '跟客乙')], refine_search: false })
    mocks.api.command.mockImplementation(async request => {
      expect(request.action).toBe('draft_transfer')
      const changed = { ...row, version: 4, responsibility: { ...row.responsibility!, assignee: person('bob', '跟客乙') } }
      data.records = data.records.map(item => item.id === row.id ? changed : item)
      return { record: changed }
    })
    const wrapper = await setup('customer'), panel = wrapper.get('#im-panel-shipment')
    await rowAction(panel, '[data-shipment-id="shipment"]', '转交')
    const editor = panel.get('.im-transfer')
    await field(editor, '搜索姓名或账号').setValue('跟客乙')
    await button(editor, '查找负责人').trigger('click')
    expect(mocks.api.assignees).toHaveBeenLastCalledWith('huaxing', '跟客乙')
    await field(editor, '接收人').setValue('bob'); await field(editor, '转交原因').setValue('本周跟客工作交接')
    await button(editor, '确认转交').trigger('click')
    expect(mocks.api.command).toHaveBeenCalledWith(expect.objectContaining({ entity_id: row.id, expected_version: 3,
      data: { assignee_id: 'bob', reason: '本周跟客工作交接' } }))
    expect(panel.get('[data-shipment-id="shipment"]').text()).toContain('上传人：跟客甲')
    expect(panel.get('[data-shipment-id="shipment"]').text()).toContain('负责人：跟客乙')
  })
})
async function rowAction(panel: FormPanel, selector: string, action: string) { await button(panel.get(selector), action).trigger('click') }
const recordFormCases: RecordFormCase[] = [
  { name: '固定客人', kind: 'customer', area: 'master', seed: () => { data.records.push(record('client2', 'customer', { name: 'OTHER', status: 'active', notes: '' })) },
    open: (panel, second) => rowAction(panel, `[data-customer-id="${second ? 'client2' : 'client'}"]`, '编辑客人'), field: '备注', values: ['客人 A 备注', '客人 B 备注'], ids: ['client', 'client2'], operation: 'edit' },
  { name: '基础选项', kind: 'options', area: 'master', seed: () => { data.records.push(record('option-a', 'option', { group: 'currency', value: 'RMB', status: 'active', billing_basis: 'quantity', kg_per_unit: '1' }), record('option-b', 'option', { group: 'currency', value: 'EUR', status: 'active', billing_basis: 'quantity', kg_per_unit: '1' })) },
    open: async (panel, second) => { if (!panel.findAll('[data-option-value]').length) await button(panel, '基础选项').trigger('click'); await field(panel, '资料分类').setValue('currency'); await flushPromises(); await rowAction(panel, `[data-option-value="${second ? 'EUR' : 'RMB'}"]`, '编辑选项') },
    field: '使用状态', values: ['inactive', 'active'], ids: ['currency', 'currency'], extraKeys: [['RMB'], ['EUR']], operation: 'edit' },
  { name: '合同批次', kind: 'demand', area: 'demand', open: (panel, second) => rowAction(panel, `[data-order-id="${second ? 'o2' : 'o'}"]`, '编辑合同'), field: '变更原因（修改时填写）', values: ['合同 A 修改', '合同 B 修改'], ids: ['o', 'o2'], operation: 'edit' },
  { name: '需求调整', kind: 'demand', area: 'demand', open: (panel, second) => rowAction(panel, `[data-demand-id="${second ? 'd2' : 'd'}"]`, '调整需求'), field: '业务原因', values: ['A 需求说明', 'B 需求说明'], ids: ['o', 'o2'], extraKeys: [['d'], ['d2']], operation: 'adjust' },
  { name: '需求重算', kind: 'demand', area: 'demand', open: (panel, second) => rowAction(panel, `[data-order-id="${second ? 'o2' : 'o'}"]`, '重新生成需求'), field: '业务原因', values: ['A 重算说明', 'B 重算说明'], ids: ['o', 'o2'], operation: 'recalculate' },
  { name: '供应分配', kind: 'allocation', area: 'supply', seed: () => { data.records.push(record('s2', 'supply', { ...data.records.find(row => row.id === 's')!.data, purchase_no: 'P-3' })) }, open: (panel, second) => rowAction(panel, `[data-received-supply-id="${second ? 's2' : 's'}"]`, '选择分配 PO'), field: '业务原因（选填）', values: ['A 分配说明', 'B 分配说明'], ids: ['s', 's2'], operation: 'received' },
  { name: '未发改绑', kind: 'allocation', area: 'supply', open: (panel, second) => rowAction(panel, `[data-allocation-id="${second ? 'a-rrm' : 'a'}"]`, '未发改绑'), field: '业务原因', values: ['A 改绑说明', 'B 改绑说明'], ids: ['a', 'a-rrm'], operation: 'reallocate' },
  { name: '采购数量', kind: 'supply', area: 'supply', seed: twoSupplyBatches, open: (panel, second) => rowAction(panel, `[data-supply-id="${second ? 's-expected2' : 's-expected'}"]`, '编辑数量'), field: '正常量', values: ['11.12345678', '22.12345678'], ids: ['s-expected', 's-expected2'], operation: 'edit' },
  { name: '供应商回复', kind: 'supply', area: 'supply', seed: twoSupplyBatches, open: (panel, second) => rowAction(panel, `[data-supply-id="${second ? 's-expected2' : 's-expected'}"]`, '更新回复'), field: '回复来源／变更原因', values: ['A 供应商回复', 'B 供应商回复'], ids: ['s-expected', 's-expected2'], operation: 'reply' },
  { name: '船务入库', kind: 'supply', area: 'supply', seed: twoSupplyBatches, open: (panel, second) => rowAction(panel, `[data-supply-id="${second ? 's-expected2' : 's-expected'}"]`, '船务确认入库'), field: '实际回河源日期', values: ['2026-11-01', '2026-11-02'], ids: ['s-expected', 's-expected2'], operation: 'receipt' },
  { name: '出货资料补全', kind: 'supply', area: 'supply', seed: twoSupplyBatches, open: (panel, second) => rowAction(panel, `[data-supply-id="${second ? 's-expected2' : 's-expected'}"]`, '补全出货资料'), field: '资料补全原因', values: ['A 补资料', 'B 补资料'], ids: ['s-expected', 's-expected2'], operation: 'output' },
  { name: '出货单', kind: 'shipment', area: 'shipment', seed: twoShipments, open: (panel, second) => rowAction(panel, `[data-shipment-id="${second ? 'shipment2' : 'shipment'}"]`, '编辑草稿'), field: '出货备注', values: ['A 出货备注', 'B 出货备注'], ids: ['shipment', 'shipment2'], operation: 'edit' },
]
const caseDraftId = (test: RecordFormCase, second: boolean) => recordDraftId(test.kind, test.operation, test.ids[second ? 1 : 0], ...(test.extraKeys?.[second ? 1 : 0] || []))

describe('independent drafts for all record forms', () => {
  it.each(recordFormCases)('$name retains each record while switching and after reopening', async test => {
    test.seed?.()
    const wrapper = await setup('customer'), panel = wrapper.get(`#im-panel-${test.area}`)
    await test.open(panel, false); await field(panel, test.field).setValue(test.values[0]); await flushPromises()
    await test.open(panel, true); await field(panel, test.field).setValue(test.values[1]); await flushPromises()
    expect(storedDrafts().filter(item => draftKind(item.id) === test.kind)).toHaveLength(2)
    await test.open(panel, false)
    expect((field(panel, test.field).element as HTMLInputElement).value).toBe(test.values[0])
    expect(wrapper.find(`[data-draft-id="${caseDraftId(test, false)}"]`).exists()).toBe(true)
    expect(wrapper.find(`[data-draft-id="${caseDraftId(test, true)}"]`).exists()).toBe(true)
    expect(vi.mocked(window.confirm)).not.toHaveBeenCalled()
    wrapper.unmount(); wrappers.splice(wrappers.indexOf(wrapper), 1)
    const reopened = await setup('customer')
    if (test.kind === 'options') await button(reopened.get('#im-panel-master'), '基础选项').trigger('click')
    await button(reopened.get(`[data-draft-id="${caseDraftId(test, true)}"]`), '继续填写').trigger('click')
    if (['demand', 'allocation', 'supply', 'shipment'].includes(test.kind)) expect(reopened.get(`#im-panel-${test.area}`).isVisible()).toBe(true)
    expect((field(reopened.get(`#im-panel-${test.area}`), test.field).element as HTMLInputElement).value).toBe(test.values[1])
    await button(reopened.get(`[data-draft-id="${caseDraftId(test, false)}"]`), '继续填写').trigger('click')
    expect((field(reopened.get(`#im-panel-${test.area}`), test.field).element as HTMLInputElement).value).toBe(test.values[0])
    expect(mocks.api.command).not.toHaveBeenCalled()
  })

  it.each(recordFormCases.filter(test => ['固定客人', '基础选项', '合同批次', '采购数量', '出货单'].includes(test.name)))('$name saves only its own draft', async test => {
    test.seed?.()
    const wrapper = await setup('customer'), panel = wrapper.get(`#im-panel-${test.area}`)
    await test.open(panel, false); await field(panel, test.field).setValue(test.values[0]); await flushPromises()
    await test.open(panel, true); await field(panel, test.field).setValue(test.values[1]); await flushPromises()
    await test.open(panel, false)
    await panel.get('form').trigger('submit'); await flushPromises()
    expect(mocks.api.command).toHaveBeenCalledTimes(1)
    expect(storedDrafts().some(item => item.id === caseDraftId(test, false))).toBe(false)
    expect(storedDrafts().some(item => item.id === caseDraftId(test, true))).toBe(true)
    await button(wrapper.get(`[data-draft-id="${caseDraftId(test, true)}"]`), '继续填写').trigger('click')
    expect((field(panel, test.field).element as HTMLInputElement).value).toBe(test.values[1])
  })

  it.each(recordFormCases.filter(test => ['固定客人', '基础选项', '合同批次', '采购数量', '出货单'].includes(test.name)))('$name resumes an old singleton draft from its original record button', async test => {
    test.seed?.()
    const wrapper = await setup('customer'), panel = wrapper.get(`#im-panel-${test.area}`)
    await test.open(panel, false); await field(panel, test.field).setValue(test.values[0]); await flushPromises()
    const key = [...savedBuckets.keys()][0]!, old = structuredClone(storedDrafts().find(item => item.id === caseDraftId(test, false))!)
    wrapper.unmount(); wrappers.splice(wrappers.indexOf(wrapper), 1)
    delete old.state.label
    savedBuckets.get(key)!.drafts = { [test.kind]: { ...old, id: test.kind } }
    const reopened = await setup('customer'), reopenedPanel = reopened.get(`#im-panel-${test.area}`)
    await test.open(reopenedPanel, false)
    expect((field(reopenedPanel, test.field).element as HTMLInputElement).value).toBe(test.values[0])
    expect(storedDrafts()).toHaveLength(1)
    expect(storedDrafts()[0]!.id).toBe(test.kind)
  })

  it.each(recordFormCases.filter(test => ['固定客人', '基础选项', '合同批次', '采购数量', '出货单'].includes(test.name)))('$name retries the original operation after reopening without closing another recovered record', async test => {
    test.seed?.()
    const wrapper = await setup('customer'), panel = wrapper.get(`#im-panel-${test.area}`)
    await test.open(panel, false); await field(panel, test.field).setValue(test.values[0]); await flushPromises()
    await test.open(panel, true); await field(panel, test.field).setValue(test.values[1]); await flushPromises()
    await test.open(panel, false)
    mocks.api.command.mockRejectedValueOnce(new Error('响应中断'))
    await panel.get('form').trigger('submit'); await flushPromises()
    const original = structuredClone(mocks.api.command.mock.calls[0]![0])
    expect([...savedBuckets.values()][0]!.pending!.owner).toBe(caseDraftId(test, false))
    wrapper.unmount(); wrappers.splice(wrappers.indexOf(wrapper), 1)
    const reopened = await setup('customer')
    if (test.kind === 'options') await button(reopened.get('#im-panel-master'), '基础选项').trigger('click')
    await button(reopened.get(`[data-draft-id="${caseDraftId(test, true)}"]`), '继续填写').trigger('click')
    await button(reopened, '重试原操作').trigger('click')
    expect(mocks.api.command.mock.calls[1]![0]).toEqual(original)
    expect((field(reopened.get(`#im-panel-${test.area}`), test.field).element as HTMLInputElement).value).toBe(test.values[1])
    expect(storedDrafts().some(item => item.id === caseDraftId(test, false))).toBe(false)
    expect(storedDrafts().some(item => item.id === caseDraftId(test, true))).toBe(true)
  })

  it.each([
    { kind: 'customer', area: 'master', button: '新增固定客人', field: '固定客人名称' },
    { kind: 'options', area: 'master', button: '新增选项', field: '选项名称' },
    { kind: 'demand', area: 'demand', button: '新增合同需求', field: '客户合同号' },
    { kind: 'supply', area: 'supply', button: '登记采购／回料批次', field: '采购单号' },
    { kind: 'shipment', area: 'shipment', button: '新建出货草稿', field: '出货备注' },
  ])('$kind keeps several unsaved new records independently', async test => {
    const wrapper = await setup('customer'), panel = wrapper.get(`#im-panel-${test.area}`)
    if (test.kind === 'options') await button(panel, '基础选项').trigger('click')
    await button(panel, test.button).trigger('click'); await field(panel, test.field).setValue('新记录 A'); await flushPromises()
    const original = storedDrafts().find(item => draftKind(item.id) === test.kind)!.id
    await button(panel, test.button).trigger('click'); await field(panel, test.field).setValue('新记录 B'); await flushPromises()
    const items = storedDrafts().filter(item => draftKind(item.id) === test.kind)
    expect(items).toHaveLength(2)
    expect(items.every(item => item.id.startsWith(`${test.kind}:new:`))).toBe(true)
    wrapper.unmount(); wrappers.splice(wrappers.indexOf(wrapper), 1)
    const reopened = await setup('customer')
    if (test.kind === 'options') await button(reopened.get('#im-panel-master'), '基础选项').trigger('click')
    await button(reopened.get(`[data-draft-id="${original}"]`), '继续填写').trigger('click')
    expect((field(reopened.get(`#im-panel-${test.area}`), test.field).element as HTMLInputElement).value).toBe('新记录 A')
    expect(storedDrafts().filter(item => draftKind(item.id) === test.kind)).toHaveLength(2)
    expect(mocks.api.command).not.toHaveBeenCalled()
  })

  it('keeps different operations for the same contract and supply batch in separate drafts', async () => {
    const wrapper = await setup('customer'), demand = wrapper.get('#im-panel-demand'), supply = wrapper.get('#im-panel-supply')
    await rowAction(demand, '[data-order-id="o"]', '编辑合同'); await field(demand, '变更原因（修改时填写）').setValue('编辑合同')
    await rowAction(demand, '[data-demand-id="d"]', '调整需求'); await field(demand, '业务原因').setValue('调整需求')
    await rowAction(supply, '[data-received-supply-id="s"]', '选择分配 PO'); await field(supply, '业务原因（选填）').setValue('分配供应')
    await rowAction(supply, '[data-supply-id="s-expected"]', '编辑数量'); await field(supply, '正常量').setValue('7')
    await rowAction(supply, '[data-supply-id="s-expected"]', '更新回复'); await field(supply, '回复来源／变更原因').setValue('供应商答复')
    await rowAction(supply, '[data-supply-id="s-expected"]', '船务确认入库'); await field(supply, '实际回河源日期').setValue('2026-11-07'); await flushPromises()
    expect(storedDrafts()).toHaveLength(6)
    await rowAction(demand, '[data-order-id="o"]', '编辑合同')
    expect((field(demand, '变更原因（修改时填写）').element as HTMLInputElement).value).toBe('编辑合同')
    await rowAction(supply, '[data-supply-id="s-expected"]', '更新回复')
    expect((field(supply, '回复来源／变更原因').element as HTMLInputElement).value).toBe('供应商答复')
    expect(vi.mocked(window.confirm)).not.toHaveBeenCalled()
  })

  it('supports multiple receipt drafts without Sales write permission and retries only the submitted batch', async () => {
    twoSupplyBatches(); data.permissions = ['read', 'receipt_confirm']
    const test = recordFormCases.find(item => item.name === '船务入库')!
    const wrapper = await setup('customer'), panel = wrapper.get('#im-panel-supply')
    await test.open(panel, false); await field(panel, test.field).setValue(test.values[0]); await flushPromises()
    await test.open(panel, true); await field(panel, test.field).setValue(test.values[1]); await flushPromises()
    wrapper.unmount(); wrappers.splice(wrappers.indexOf(wrapper), 1)
    const reopened = await setup('customer'), receiptPanel = reopened.get('#im-panel-supply')
    await button(reopened.get(`[data-draft-id="${caseDraftId(test, false)}"]`), '继续填写').trigger('click')
    expect(receiptPanel.get('fieldset').attributes('disabled')).toBeUndefined()
    mocks.api.command.mockRejectedValueOnce(new Error('响应中断'))
    await receiptPanel.get('form').trigger('submit'); await flushPromises()
    const original = structuredClone(mocks.api.command.mock.calls[0]![0])
    expect(original).toMatchObject({ action: 'receipt_confirm', entity_id: 's-expected', expected_version: 3 })
    await button(reopened, '重试原操作').trigger('click')
    expect(mocks.api.command.mock.calls[1]![0]).toEqual(original)
    expect(storedDrafts().some(item => item.id === caseDraftId(test, false))).toBe(false)
    expect(storedDrafts().some(item => item.id === caseDraftId(test, true))).toBe(true)
    await button(reopened.get(`[data-draft-id="${caseDraftId(test, true)}"]`), '继续填写').trigger('click')
    expect((field(receiptPanel, test.field).element as HTMLInputElement).value).toBe(test.values[1])
  })

  it('keeps shipment editing and confirmation separate and never restores a confirmed shipment as editable', async () => {
    twoShipments()
    const wrapper = await setup('customer'), panel = wrapper.get('#im-panel-shipment')
    await rowAction(panel, '[data-shipment-id="shipment"]', '编辑草稿'); await field(panel, '出货备注').setValue('编辑中的备注')
    await rowAction(panel, '[data-shipment-id="shipment"]', '核对并确认出货')
    await rowAction(panel, '[data-shipment-id="shipment2"]', '核对并确认出货')
    expect(storedDrafts().filter(item => draftKind(item.id) === 'shipment')).toHaveLength(3)
    data.records.find(row => row.id === 'shipment')!.data.status = 'confirmed'
    await button(wrapper, '刷新工作区').trigger('click')
    await button(wrapper.get(`[data-draft-id="${recordDraftId('shipment', 'edit', 'shipment')}"]`), '继续填写').trigger('click')
    expect(wrapper.text()).toContain('该出货单已确认')
    expect(storedDrafts()).toHaveLength(3)
    expect(mocks.api.command).not.toHaveBeenCalled()
  })

  it('keeps import selections for each source batch across switching and reopening', async () => {
    for (const [id, name] of [['import-a', 'A.xlsx'], ['import-b', 'B.xlsx']]) data.records.push(record(id!, 'import', { filename: name, customer: 'CLIENT', recipient: 'RRI', status: 'preview', rows: [{ ...mainOrder, index: 0, source_sheet: 'Sheet1', source_row: 20, blocked: false, issues: [] }] }))
    const wrapper = await setup('customer'), panel = wrapper.get('#im-panel-import')
    await rowAction(panel, '[data-import-id="import-a"]', '查看核对'); await panel.get('input[type="checkbox"]').setValue(true); await flushPromises()
    await rowAction(panel, '[data-import-id="import-b"]', '查看核对'); await panel.get('input[type="checkbox"]').setValue(true); await flushPromises()
    await rowAction(panel, '[data-import-id="import-a"]', '查看核对')
    expect((panel.get('input[type="checkbox"]').element as HTMLInputElement).checked).toBe(true)
    expect(panel.text()).toContain('预览：A.xlsx')
    expect(storedDrafts()).toHaveLength(2)
    wrapper.unmount(); wrappers.splice(wrappers.indexOf(wrapper), 1)
    const reopened = await setup('customer')
    await button(reopened.get(`[data-draft-id="${recordDraftId('import', 'inspect', 'import-b')}"]`), '继续填写').trigger('click')
    expect(reopened.get('#im-panel-import').text()).toContain('预览：B.xlsx')
    expect((reopened.get('#im-panel-import input[type="checkbox"]').element as HTMLInputElement).checked).toBe(true)
    expect(mocks.api.command).not.toHaveBeenCalled()
  })

  it('reuses the uploaded source draft by identity and retains another selected file separately', async () => {
    const { wrapper, panel } = await preparedForm(formCases[14]!)
    await flushPromises()
    const original = storedDrafts().find(item => draftKind(item.id) === 'import')!
    await rowAction(panel, '[data-import-id="import-matrix"]', '查看核对')
    expect(storedDrafts()).toHaveLength(1)
    expect(storedDrafts()[0]!.id).toBe(original.id)
    expect((panel.get('input[type="checkbox"]').element as HTMLInputElement).checked).toBe(true)
    const file = new File(['second source'], 'second.xlsx')
    const input = panel.get('input[type="file"]')
    Object.defineProperty(input.element, 'files', { value: [file], configurable: true })
    await input.trigger('change'); await flushPromises()
    expect(storedDrafts()).toHaveLength(2)
    expect(storedDrafts().find(item => item.id === original.id)!.state.file.name).toBe('schedule.xlsx')
    expect(storedDrafts().some(item => item.state.file?.name === 'second.xlsx')).toBe(true)
    await button(wrapper.get(`[data-draft-id="${original.id}"]`), '继续填写').trigger('click')
    expect(panel.text()).toContain('已保留文件：schedule.xlsx')
    expect((panel.get('input[type="checkbox"]').element as HTMLInputElement).checked).toBe(true)
  })
})

describe('all material form draft lifecycles', () => {
  it('deletes a maintained option from its row and restores its original record and version', async () => {
    const option = record('currency-rmb', 'option', { group: 'currency', value: 'RMB', status: 'active', billing_basis: 'quantity', kg_per_unit: '1' })
    data.records.push(option)
    mocks.api.command.mockImplementation(async body => {
      const current = data.records.find(item => item.id === body.entity_id)!
      const updated = { ...current, version: current.version + 1, data: body.action === 'option_save' ? structuredClone(body.data) : { ...current.data, deleted: body.action === 'option_delete', deleted_by: 'user', deleted_at: '2026-10-22' } }
      data.records = data.records.map(item => item.id === current.id ? updated : item)
      return { record: structuredClone(updated) }
    })
    const panel = (await setup()).get('#im-panel-master')
    await button(panel, '基础选项').trigger('click')
    await field(panel, '资料分类').setValue('currency')
    await field(panel, '搜索选项').setValue('RMB')
    await button(panel, '删除选项').trigger('click'); await flushPromises()
    expect(mocks.api.command.mock.calls[0]![0]).toMatchObject({ action: 'option_delete', entity_id: 'currency-rmb', expected_version: 3, data: {} })
    expect(panel.find('form').exists()).toBe(false)
    expect(panel.find('tbody tr').exists()).toBe(false)
    expect(panel.get('summary').text()).toContain('已删除选项（1）')
    await button(panel, '恢复选项').trigger('click'); await flushPromises()
    expect(mocks.api.command.mock.calls[1]![0]).toMatchObject({ action: 'option_restore', entity_id: 'currency-rmb', expected_version: 4, data: {} })
    expect(panel.get('tbody').text()).toContain('RMB')
    await button(panel, '编辑选项').trigger('click')
    await field(panel, '使用状态').setValue('inactive')
    await panel.get('form').trigger('submit'); await flushPromises()
    const payload = mocks.api.command.mock.calls[2]![0]
    expect(payload).toMatchObject({ action: 'option_save', entity_id: 'currency-rmb', expected_version: 5, data: { value: 'RMB', status: 'inactive' } })
    expect(payload.data).not.toHaveProperty('deleted')
    expect(payload.data).not.toHaveProperty('deleted_by')
    expect(payload.data).not.toHaveProperty('deleted_at')
  })

  it('keeps a failed built-in option delete across reload and retries the exact original command', async () => {
    const wrapper = await setup(), panel = wrapper.get('#im-panel-master')
    await button(panel, '基础选项').trigger('click')
    await field(panel, '资料分类').setValue('currency')
    await button(panel, '编辑选项').trigger('click')
    mocks.api.command.mockRejectedValueOnce(new Error('网络中断'))
    await button(panel.get('form'), '删除选项').trigger('click'); await flushPromises()
    const original = mocks.api.command.mock.calls[0]![0]
    expect(original).toMatchObject({ action: 'option_delete', entity_id: null, expected_version: 0, data: { group: 'currency', value: 'USD' } })
    expect(panel.find('form').exists()).toBe(true)
    wrapper.unmount(); wrappers.splice(wrappers.indexOf(wrapper), 1)
    const reopened = await setup('customer')
    await button(reopened.get('#im-panel-master'), '基础选项').trigger('click')
    expect(reopened.text()).toContain('重试原操作')
    await button(reopened, '重试原操作').trigger('click'); await flushPromises()
    expect(mocks.api.command.mock.calls[1]![0]).toEqual(original)
  })

  it('cancels an option delete without submitting or losing entered changes', async () => {
    const panel = (await setup()).get('#im-panel-master')
    await button(panel, '基础选项').trigger('click')
    await field(panel, '资料分类').setValue('currency')
    await button(panel, '编辑选项').trigger('click')
    await field(panel, '使用状态').setValue('inactive')
    vi.mocked(window.confirm).mockReturnValue(false)
    await button(panel.get('form'), '删除选项').trigger('click')
    expect(mocks.api.command).not.toHaveBeenCalled()
    expect((field(panel, '使用状态').element as HTMLSelectElement).value).toBe('inactive')
  })

  it('hides deleted default choices in new material forms and retains historical values only in existing materials', async () => {
    data.records.push(record('deleted-usd', 'option', { group: 'currency', value: 'USD', status: 'active', deleted: true }))
    const panel = (await setup()).get('#im-panel-master')
    await button(panel, '添加物料').trigger('click')
    const newCard = panel.findAll('.im-recipe-card')[1]!
    expect(field(newCard, '币种').findAll('option').map(item => item.attributes('value'))).not.toContain('USD')
    await button(panel, '编辑物料资料').trigger('click')
    expect(field(panel.findAll('.im-recipe-card')[0]!, '币种').findAll('option').map(item => item.text())).toContain('USD（历史值）')
  })

  it('lets ordinary sales add shared choices while locking status and conversion management', async () => {
    data.permissions = ['read', 'write']
    const panel = (await setup()).get('#im-panel-master')
    await button(panel, '基础选项').trigger('click')
    await button(panel, '新增选项').trigger('click')
    expect(field(panel, '使用状态').attributes('disabled')).toBeDefined()
    expect(panel.findAll('button').some(item => item.text() === '删除选项')).toBe(false)
    await button(panel, '关闭选项表单').trigger('click')
    await field(panel, '资料分类').setValue('customs_unit')
    await button(panel.get('[data-option-value="KGM"]'), '编辑选项').trigger('click')
    expect(field(panel, '计价依据').attributes('disabled')).toBeDefined()
    expect(field(panel, '每报关单位对应千克数').attributes('readonly')).toBeDefined()
  })

  it('keeps shared drafts across factories and preserves private customer drafts after shared save', async () => {
    const wrapper = await setup('customer'), panel = wrapper.get('#im-panel-master')
    await button(panel, '编辑客人').trigger('click')
    await field(panel, '备注').setValue('仅华兴的私有草稿')
    await flushPromises()
    await button(panel, '基础选项').trigger('click')
    await button(panel, '新增选项').trigger('click')
    await field(panel, '选项名称').setValue('切厂继续的共用类别')
    await flushPromises()
    mocks.app.activeFactoryId = 'huadeng'
    await flushPromises()
    const changed = wrapper.get('#im-panel-master')
    await button(changed, '基础选项').trigger('click')
    await button(changed.get('.im-shared-options'), '继续填写').trigger('click')
    expect((field(changed, '选项名称').element as HTMLInputElement).value).toBe('切厂继续的共用类别')
    expect(wrapper.get('section[aria-label="本机填写草稿"]').text()).not.toContain('仅华兴的私有草稿')
    await changed.get('form').trigger('submit'); await flushPromises()
    expect(mocks.api.command.mock.calls[0]![0]).toMatchObject({ factory_id: 'shared-options', action: 'option_save' })
    expect(storedDrafts().some(item => item.state.form?.notes === '仅华兴的私有草稿')).toBe(true)
    expect(storedDrafts().some(item => item.state.form?.value === '切厂继续的共用类别')).toBe(false)
  })

  it('keeps legacy factory option input private until explicitly copied to a new shared draft', async () => {
    const wrapper = await setup('customer')
    await button(wrapper.get('#im-panel-master'), '编辑客人').trigger('click')
    await field(wrapper.get('#im-panel-master'), '备注').setValue('保留本厂草稿')
    await flushPromises()
    wrapper.unmount(); wrappers.splice(wrappers.indexOf(wrapper), 1)
    const key = [...savedBuckets.keys()][0]!
    savedBuckets.get(key)!.drafts.options = { id: 'options', revision: 'old-option-revision', writer: 'old', savedAt: '2026-10-21', state: {
      editing: { id: 'old-private', kind: 'option', version: 2 }, group: 'category', named: true,
      form: { group: 'category', value: '旧厂区选项', status: 'active', billing_basis: 'quantity', kg_per_unit: '1' },
    } }
    const reopened = await setup('customer')
    await button(reopened.get('[data-draft-id="options"]'), '继续填写').trigger('click')
    expect(mocks.api.command).not.toHaveBeenCalled()
    const panel = reopened.get('#im-panel-master')
    expect(panel.get('.im-shared-options').text()).toContain('旧厂区选项')
    await button(panel, '复制到共用新建草稿').trigger('click')
    expect((field(panel, '选项名称').element as HTMLInputElement).value).toBe('旧厂区选项')
    await panel.get('form').trigger('submit'); await flushPromises()
    expect(mocks.api.command.mock.calls[0]![0]).toMatchObject({ action: 'option_save', factory_id: 'shared-options', entity_id: null, expected_version: 0 })
    expect(savedBuckets.get(key)!.drafts.options).toBeDefined()
  })

  it('does not expose option deletion to a read-only account', async () => {
    data.permissions = ['read']
    data.records.push(record('deleted-usd', 'option', { group: 'currency', value: 'USD', status: 'active', deleted: true }))
    const panel = (await setup()).get('#im-panel-master')
    await button(panel, '基础选项').trigger('click')
    await field(panel, '资料分类').setValue('currency')
    expect(panel.findAll('button').some(item => item.text() === '删除选项')).toBe(false)
    expect(button(panel, '恢复选项').attributes('disabled')).toBeDefined()
    expect(mocks.api.command).not.toHaveBeenCalled()
  })

  it('autosaves and restores an unfinished option in the options workspace after reopening', async () => {
    const wrapper = await setup(), panel = wrapper.get('#im-panel-master')
    await button(panel, '基础选项').trigger('click')
    await button(panel, '新增选项').trigger('click')
    await field(panel, '选项名称').setValue('业务新增类别')
    await flushPromises()
    wrapper.unmount(); wrappers.splice(wrappers.indexOf(wrapper), 1)
    const reopened = await setup('customer')
    await button(reopened.get('#im-panel-master'), '基础选项').trigger('click')
    await button(reopened, '继续填写').trigger('click'); await flushPromises()
    const restored = reopened.get('#im-panel-master')
    expect((field(restored, '选项名称').element as HTMLInputElement).value).toBe('业务新增类别')
    expect(mocks.api.command).not.toHaveBeenCalled()
    await restored.get('form').trigger('submit'); await flushPromises()
    expect(mocks.api.command.mock.calls[0]![0]).toMatchObject({ action: 'option_save', factory_id: 'shared-options', data: { group: 'category', value: '业务新增类别' } })
  })

  it('updates searchable supplier choices from a newly maintained option and retains historical values', async () => {
    const wrapper = await setup(), panel = wrapper.get('#im-panel-master')
    data.records.push(record('new-supplier', 'option', { group: 'supplier', value: '新供应商（河源）', status: 'active' }))
    await button(wrapper, '刷新工作区').trigger('click'); await flushPromises()
    await button(panel, '编辑').trigger('click'); await button(panel, '编辑物料资料').trigger('click')
    expect(panel.findAll('datalist option').map(option => option.attributes('value'))).toContain('新供应商（河源）')
    await field(panel, '供应商').setValue('新供应商（河源）')
    await flushPromises()
    expect((field(panel, '供应商').element as HTMLInputElement).value).toBe('新供应商（河源）')
    expect(mocks.api.command).not.toHaveBeenCalled()
  })
  it('preserves a closed import while opening a separate fresh upload form', async () => {
    const { wrapper } = await preparedForm(formCases[14]!)
    const original = storedDrafts().find(item => draftKind(item.id) === 'import')!
    await flushPromises(); wrapper.unmount(); wrappers.splice(wrappers.indexOf(wrapper), 1)
    const reopened = await setup('customer'), panel = reopened.get('#im-panel-import')
    expect(panel.get('fieldset').attributes('disabled')).toBeUndefined()
    vi.mocked(window.confirm).mockReturnValue(false)
    await button(panel, '新建导入表单').trigger('click')
    expect(panel.get('fieldset').attributes('disabled')).toBeUndefined()
    expect(storedDrafts().some(item => item.id === original.id)).toBe(true)
    await button(reopened.get(`[data-draft-id="${original.id}"]`), '继续填写').trigger('click'); await flushPromises()
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
    const active = storedDrafts().filter(item => draftKind(item.id) === 'import').at(-1)!.id
    await memoryDatabase.update(key, bucket => {
      bucket.drafts[active]!.revision = 'newer-other-tab'
      bucket.drafts[active]!.state.customer = 'OTHER PAGE INPUT'
    })
    window.dispatchEvent(new StorageEvent('storage', { key: 'rrn-indonesia-draft-signal' })); await flushPromises()
    release({ record: record('new-preview', 'import', { filename: 'new.xlsx', rows: [], status: 'preview' }) })
    await flushPromises()
    expect(savedBuckets.get(key)!.drafts[active]!.state.customer).toBe('OTHER PAGE INPUT')
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
    expect(storedDrafts().find(item => draftKind(item.id) === 'customer')!.state.form.notes).toBe('latest unsaved text')
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
    await button(panel, '货号与物料').trigger('click'); await button(panel, '查看').trigger('click'); await flushPromises()
    expect(field(panel, '英文名称').element).toBeInstanceOf(HTMLInputElement)
    expect(field(panel, '单个净重（kg）').element).toBeInstanceOf(HTMLInputElement)
    expect(panel.find('input[type="file"]').exists()).toBe(true)
    expect(panel.get('fieldset').attributes('disabled')).toBeDefined()
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
    else if (test.name === '出货确认核对') { expect(panel.text()).toContain('已确认出货明细'); expect(panel.get('fieldset').attributes('disabled')).toBeDefined() }
    else expect(panel.find(test.area === 'supply' ? '[data-manual-supply] form' : 'form').exists()).toBe(false)
  })

  it('keeps material input on its selected category and restores it after another category is opened', async () => {
    const { wrapper, panel } = await preparedForm(formCases[1]!)
    const before = enteredValues(panel)
    await button(panel, '货号与物料').trigger('click')
    expect(enteredValues(panel)).toEqual(before)
    const saved = storedDrafts().find(item => draftKind(item.id) === 'master')!
    await button(panel, '固定客人').trigger('click')
    expect(panel.find('form').exists()).toBe(false)
    await button(wrapper.get(`[data-draft-id="${saved.id}"]`), '继续填写').trigger('click')
    expect(enteredValues(panel)).toEqual(before)
  })

  it('protects a dirty fixed-customer editor before switching master categories', async () => {
    const { panel } = await preparedForm(formCases[0]!)
    const before = enteredValues(panel)
    vi.mocked(window.confirm).mockReturnValue(false)
    await button(panel, '货号与物料').trigger('click')
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
    expect(supply.find('[data-manual-supply] form').exists()).toBe(false)
    expect(master.find('form').exists()).toBe(true)
    expect(enteredValues(master)).toEqual(materialBefore)
  })

  it('retains shipment quantities and packing in the original draft after another recipient is opened', async () => {
    const { wrapper, panel } = await preparedForm(formCases[12]!)
    await flushPromises()
    const before = enteredValues(panel)
    const original = storedDrafts().find(item => draftKind(item.id) === 'shipment')!
    await field(panel, '本次唯一接收方').setValue('RRM'); await flushPromises()
    expect(storedDrafts().filter(item => draftKind(item.id) === 'shipment')).toHaveLength(2)
    await button(wrapper.get(`[data-draft-id="${original.id}"]`), '继续填写').trigger('click')
    expect(enteredValues(panel)).toEqual(before)
    expect(vi.mocked(window.confirm)).not.toHaveBeenCalled()
  })

  it('retains import selections in separate drafts when switching context or uploading another preview', async () => {
    data.records.push(record('other-customer', 'customer', { name: 'OTHER', status: 'active' }))
    const { wrapper, panel } = await preparedForm(formCases[14]!)
    await flushPromises()
    const before = enteredValues(panel)
    const original = storedDrafts().find(item => draftKind(item.id) === 'import')!
    await field(panel, '本次接收方').setValue('RRM'); await flushPromises()
    await field(panel, '客户').setValue('OTHER'); await flushPromises()
    expect(storedDrafts().filter(item => draftKind(item.id) === 'import')).toHaveLength(3)
    await button(wrapper.get(`[data-draft-id="${original.id}"]`), '继续填写').trigger('click')
    expect(enteredValues(panel).map(({ files: _files, ...value }) => value)).toEqual(before.map(({ files: _files, ...value }) => value))
    await panel.get('form').trigger('submit'); await flushPromises()
    expect(mocks.api.preview).toHaveBeenCalledTimes(2)
    expect(storedDrafts().find(item => item.id === original.id)!.state.selected).toEqual([0])
    expect(vi.mocked(window.confirm)).not.toHaveBeenCalled()
  })

  it('autosaves a new import context while keeping the previous source and selection separately', async () => {
    const { wrapper, panel } = await preparedForm(formCases[14]!)
    await flushPromises()
    await field(panel, '本次接收方').setValue('RRM'); await flushPromises()
    expect((field(panel, '本次接收方').element as HTMLSelectElement).value).toBe('RRM')
    expect(panel.find('input[aria-label="选择来源行 20"]').exists()).toBe(false)
    expect(storedDrafts().some(item => item.state.recipient === 'RRM' && item.state.preview === null && item.state.selected.length === 0)).toBe(true)
    expect(storedDrafts().some(item => item.state.recipient === 'RRI' && item.state.selected?.length === 1)).toBe(true)
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
    expect(enteredValues(restored).map(({ files: _files, ...input }) => input)).toEqual(test.name === '出货确认核对' ? values.map(input => ({ ...input, checked: false })) : values)
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

  it('restores nested material edits with the original child revision after another user changes that material', async () => {
    const wrapper = await setup(), panel = wrapper.get('#im-panel-master')
    await button(panel, '编辑').trigger('click')
    await button(panel, '编辑物料资料').trigger('click')
    await field(panel, '供应商').setValue('原草稿供应商')
    await panel.get('[aria-label="单件用量"]').setValue('4.12345678')
    await flushPromises()
    wrapper.unmount(); wrappers.splice(wrappers.indexOf(wrapper), 1)
    data.records.find(row => row.id === 'm')!.version = 9
    data.records.find(row => row.id === 'm')!.data.supplier = '服务器的新供应商'
    const reopened = await setup('customer')
    await button(reopened, '继续填写').trigger('click'); await flushPromises()
    const restored = reopened.get('#im-panel-master')
    expect((field(restored, '供应商').element as HTMLInputElement).value).toBe('原草稿供应商')
    await restored.get('form').trigger('submit'); await flushPromises()
    expect(mocks.api.command.mock.calls[0]![0]).toMatchObject({ action: 'product_save', expected_version: 3, data: { materials: [{ material_id: 'm', material_version: 3, usage: '4.12345678', material: { supplier: '原草稿供应商' } }] } })
  })

  it('continues a legacy standalone material draft without exposing a separate material creation category', async () => {
    const { wrapper } = await preparedForm(formCases[1]!)
    wrapper.unmount(); wrappers.splice(wrappers.indexOf(wrapper), 1)
    const key = [...savedBuckets.keys()][0]!
    savedBuckets.get(key)!.drafts.master = { id: 'master', revision: 'legacy-revision', writer: 'old-page', savedAt: '2026-10-21T00:00:00Z', state: {
      category: 'material', customerFilter: '', editing: null, form: { ...materialDefaults, code: 'LEGACY', name: '原版物料草稿', unit: 'PCS' },
    } }
    const reopened = await setup('customer')
    await button(reopened.get('[data-draft-id="master"]'), '继续填写').trigger('click'); await flushPromises()
    const panel = reopened.get('#im-panel-master')
    expect(panel.text()).toContain('恢复历史物料草稿')
    expect((field(panel, '物料名称').element as HTMLInputElement).value).toBe('原版物料草稿')
    expect(panel.get('nav').findAll('button')).toHaveLength(4)
    await panel.get('form').trigger('submit'); await flushPromises()
    expect(mocks.api.command.mock.calls[0]![0]).toMatchObject({ action: 'material_save', data: { code: 'LEGACY', name: '原版物料草稿' } })
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
