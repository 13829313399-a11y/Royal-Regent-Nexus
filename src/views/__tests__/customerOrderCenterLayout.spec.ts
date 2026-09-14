import { flushPromises, mount } from '@vue/test-utils'
import { readFileSync } from 'node:fs'
import { join } from 'node:path'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import CustomerOrderCenterWorkspace from '@/components/modules/sales/customer-order-center/CustomerOrderCenterWorkspace.vue'

const customerOrderApiMock = vi.hoisted(() => ({
  previewBuzzbeeBatch: vi.fn(),
  exportBuzzbeeBatch: vi.fn(),
  previewDickieBatch: vi.fn(),
  exportDickieBatch: vi.fn(),
  previewCaixingBatch: vi.fn(),
  exportCaixingBatch: vi.fn(),
  previewHuaxingMappedBatch: vi.fn(),
  exportHuaxingMappedBatch: vi.fn(),
  previewMappedBatch: vi.fn(),
  exportMappedBatch: vi.fn(),
}))
const customerOrderLedgerApiMock = vi.hoisted(() => ({
  capabilities: vi.fn(),
  list: vi.fn(),
  detail: vi.fn(),
  amend: vi.fn(),
  cancel: vi.fn(),
  dispatch: vi.fn(),
  confirmShipment: vi.fn(),
  reverseShipment: vi.fn(),
  importConfirmed: vi.fn(),
}))

vi.mock('@/api/customerOrder', () => ({
  customerOrderApi: customerOrderApiMock,
}))
vi.mock('@/api/customerOrderLedger', () => ({
  customerOrderLedgerApi: customerOrderLedgerApiMock,
  customerOrderLedgerSourceUrl: vi.fn(),
}))

const read = (path: string) => readFileSync(join(process.cwd(), path), 'utf8')
const routerSource = read('src/router/index.ts')
const enterpriseSource = read('src/data/enterpriseMock.ts')
const viewSource = read('src/views/CustomerOrderCenterView.vue')
const workspaceSource = read('src/components/modules/sales/customer-order-center/CustomerOrderCenterWorkspace.vue')

describe('customer order center static frontend', () => {
  const resetLedgerApi = () => {
    customerOrderLedgerApiMock.capabilities.mockResolvedValue({ read: true, write: true, dispatch: true, shipment_confirm: true, inbox_read: false, inbox_receive: false })
    customerOrderLedgerApiMock.list.mockResolvedValue({ items: [], total: 0, page: 1, page_size: 50, customers: [] })
  }

  beforeEach(() => {
    vi.clearAllMocks()
    resetLedgerApi()
  })
  it('registers the dedicated full-page route before the generic module route', () => {
    const orderRouteIndex = routerSource.indexOf("path: '/modules/sales-business/po-schedule-intake'")
    const genericRouteIndex = routerSource.indexOf("path: '/modules/:department/:module'")

    expect(orderRouteIndex).toBeGreaterThan(-1)
    expect(orderRouteIndex).toBeLessThan(genericRouteIndex)
    expect(routerSource).toContain("name: 'customer-order-center'")
    expect(routerSource).toContain("title: '客户订单中心'")
    expect(routerSource.slice(orderRouteIndex, genericRouteIndex)).toContain('fullPage: true')
    expect(routerSource.slice(orderRouteIndex, genericRouteIndex)).toContain('requiresAuth: true')
  })

  it('separates customer-schedule output from the system factory schedule data view', () => {
    expect(enterpriseSource).toContain("title: '客户订单中心'")
    expect(enterpriseSource).toContain('按月份形成可供生产部门调用的厂区总排期')
    expect(enterpriseSource).toContain("label: 'PO 入客户排期'")
    expect(enterpriseSource).toContain("label: '厂区总排期'")
    expect(enterpriseSource).toContain("label: '异常与提醒'")
    expect(viewSource).toContain("ref<CustomerOrderCenterSection>('ledger')")
    expect(viewSource).toContain('订单中心不维护生产、物料、库存或排产数据。')
    expect(viewSource).toContain("label: '异常与提醒'")
    expect(viewSource).toContain('发送订单与凭出货单确认走货')
    expect(workspaceSource).toContain('仍不提交PMC、不计算库存，也不进入啤机、喷油或装配排产')
    expect(workspaceSource).toContain('厂区总排期只显示这些公共字段。')
    expect(workspaceSource).toContain('不维护生产、物料、库存或排产数据')
    expect(workspaceSource).not.toContain('生成更新后的总排期')
    expect(workspaceSource).not.toContain('确认并发布至PMC')
  })

  it('offers manual field entry and controlled release for hard blockers', () => {
    expect(workspaceSource).toContain('人工补录 {{ issue.edit_label }}')
    expect(workspaceSource).toContain('该值会写入新排期，不修改客户原 PO')
    expect(workspaceSource).toContain('确认缺失并放行')
    expect(workspaceSource).toContain('requestedManualOverrides')
    expect(workspaceSource).not.toContain('请修正来源文件后重新解析')
  })

  it('registers EDU, 360, Yinhui, SEASONS, Maxx, Shushupapa and Barter under Huaxing', () => {
    for (const code of ['edu', '360', 'yinhui', 'seasons', 'maxx', 'shushupapa', 'barter']) {
      expect(workspaceSource).toContain(`code: '${code}'`)
      expect(workspaceSource).toContain(`customer-choice-${'$'}{customer.code}`)
    }
    expect(workspaceSource).toContain('previewMappedBatch')
    expect(workspaceSource).toContain('exportMappedBatch')
  })

  it('registers Casdon, Jakks, Simba and Spin under Huadeng', () => {
    for (const code of ['casdon', 'jakks', 'simba', 'spin']) {
      expect(workspaceSource).toContain(`code: '${code}'`)
    }
    expect(workspaceSource).toContain('huadeng: [')
    expect(workspaceSource).toContain('HUADENG_CASDON_NEW_ORDER_V1')
    expect(workspaceSource).not.toContain("code: 'spin-master'")
  })

  it('registers independent 360, Green Toys and HeadStart mappings under Huakang A', () => {
    expect(workspaceSource).toContain("'huakang-a': [")
    expect(workspaceSource).toContain('HUAKANG_A_360_SCHEDULE_APPEND_V3')
    expect(workspaceSource).toContain('HUAKANG_A_GREEN_TOYS_SCHEDULE_APPEND_V1')
    expect(workspaceSource).toContain('HUAKANG_A_HEADSTART_SCHEDULE_APPEND_V1')
    expect(workspaceSource).toContain('ThreeSixty PURCHASE ORDER RELEASE')
    expect(workspaceSource).toContain('Green Toys Purchase Order 图片')
    expect(workspaceSource).toContain('HeadStart 文本型 PURCHASE ORDER PDF')
    expect(workspaceSource).toContain('每个货号先按现有产品标题行写入货号和名称')
  })

  it('shows three independent customers in Huakang A and routes 360 with the Huakang A factory id', async () => {
    customerOrderApiMock.previewMappedBatch.mockResolvedValueOnce({
      preview_schema_version: 'customer-order-huakang-a-mapped-preview-v1',
      customer_code: '360',
      factory_id: 'huakang-a',
      po_file_name: 'RL-100-1.xls',
      po_file_names: ['RL-100-1.xls'],
      po_file_count: 1,
      schedule_file_name: '河源业务统一排期.xlsx',
      source_po_sha256: 'po',
      source_po_sha256s: ['po'],
      source_schedule_sha256: 'schedule',
      input_template: 'HUAKANG_A_360_PO_RELEASE_V1',
      target_template: 'HEYUAN_BUSINESS_UNIFIED_SCHEDULE_V1',
      output_file_name: '河源业务统一排期_360新单.xlsx',
      summary: { total: 0, valid: 0, warning: 0, blocked: 0 },
      rows: [],
      warnings: [],
    })
    const wrapper = mount(CustomerOrderCenterWorkspace, {
      props: {
        activeSection: 'import',
        factoryId: 'huakang-a',
        factoryName: '华康A厂',
      },
    })

    const customerButtons = wrapper.findAll('[data-testid^="customer-choice-"]')
    expect(customerButtons).toHaveLength(3)
    expect(customerButtons.map((button) => button.text())).toEqual(
      expect.arrayContaining([
        expect.stringContaining('360'),
        expect.stringContaining('Green Toys'),
        expect.stringContaining('HeadStart'),
      ]),
    )
    expect(wrapper.text()).not.toContain('BuzzBee')

    await wrapper.get('[data-testid="customer-choice-360"]').trigger('click')
    const inputs = wrapper.findAll('input[type="file"]')
    expect(inputs[0]!.attributes('accept')).toBe('.pdf,.xls,.xlsx,.xlsm')
    expect(inputs[1]!.attributes('accept')).toBe('.xlsx')
    const po = new File(['po'], 'RL-100-1.xls')
    const schedule = new File(['schedule'], '河源业务统一排期.xlsx')
    Object.defineProperty(inputs[0]!.element, 'files', { configurable: true, value: [po] })
    Object.defineProperty(inputs[1]!.element, 'files', { configurable: true, value: [schedule] })
    await inputs[0]!.trigger('change')
    await inputs[1]!.trigger('change')
    const parseButton = wrapper.findAll('button').find((button) => button.text().includes('解析并进入预览'))
    await parseButton!.trigger('click')
    await flushPromises()

    expect(customerOrderApiMock.previewMappedBatch).toHaveBeenLastCalledWith(
      '360',
      [po],
      schedule,
      expect.any(String),
      'huakang-a',
    )
  })

  it('uses image PO input for Green Toys and PDF input for HeadStart', async () => {
    const wrapper = mount(CustomerOrderCenterWorkspace, {
      props: {
        activeSection: 'import',
        factoryId: 'huakang-a',
        factoryName: '华康A厂',
      },
    })

    await wrapper.get('[data-testid="customer-choice-green-toys"]').trigger('click')
    let inputs = wrapper.findAll('input[type="file"]')
    expect(inputs[0]!.attributes('accept')).toBe('.png,.jpg,.jpeg')
    expect(inputs[1]!.attributes('accept')).toBe('.xlsx')

    await wrapper.get('[data-testid="customer-choice-headstart"]').trigger('click')
    inputs = wrapper.findAll('input[type="file"]')
    expect(inputs[0]!.attributes('accept')).toBe('.pdf')
    expect(inputs[1]!.attributes('accept')).toBe('.xlsx')
  })

  it('offers INDEX, JAZAWARES, MAXX and STROTTMAN external orders in Huakang D', () => {
    expect(workspaceSource).toContain("'huakang-c': [")
    expect(workspaceSource).toContain("CUSTOMER_PROFILES_BY_FACTORY['huakang-d'] = CUSTOMER_PROFILES_BY_FACTORY['huakang-c']")
    expect(workspaceSource).toContain("CUSTOMER_PROFILES_BY_FACTORY['huakang-c'] = []")
    for (const template of [
      'HUAKANG_C_INDEX_NEW_ORDER_V1',
      'HUAKANG_C_JAZWARES_NEW_ORDER_V1',
      'HUAKANG_C_MAXX_NEW_ORDER_V1',
      'HUAKANG_C_STROTTMAN_NEW_ORDER_V1',
    ]) {
      expect(workspaceSource).toContain(template)
    }
    expect(workspaceSource).not.toContain("code: 'jp'")
  })

  it('shows six external customers without JP in Huakang D and routes INDEX with Huakang D scope', async () => {
    customerOrderApiMock.previewMappedBatch.mockResolvedValueOnce({
      preview_schema_version: 'customer-order-huakang-c-mapped-preview-v1',
      customer_code: 'index',
      factory_id: 'huakang-d',
      po_file_name: 'INDEX PO.pdf',
      po_file_names: ['INDEX PO.pdf'],
      po_file_count: 1,
      schedule_file_name: '河源业务统一排期.xlsx',
      source_po_sha256: 'po',
      source_po_sha256s: ['po'],
      source_schedule_sha256: 'schedule',
      input_template: 'HUAKANG_C_INDEX_PO_V1',
      target_template: 'HEYUAN_BUSINESS_UNIFIED_SCHEDULE_V1',
      output_file_name: '河源业务统一排期_INDEX新单.xlsx',
      summary: { total: 0, valid: 0, warning: 0, blocked: 0 },
      rows: [],
      warnings: [],
    })
    const wrapper = mount(CustomerOrderCenterWorkspace, {
      props: {
        activeSection: 'import',
        factoryId: 'huakang-d',
        factoryName: '华康D厂',
      },
    })

    const customerButtons = wrapper.findAll('[data-testid^="customer-choice-"]')
    expect(customerButtons).toHaveLength(6)
    expect(customerButtons.map((button) => button.text())).toEqual(
      expect.arrayContaining([
        expect.stringContaining('INDEX'),
        expect.stringContaining('JAZAWARES'),
        expect.stringContaining('MAXX'),
        expect.stringContaining('STROTTMAN'),
        expect.stringContaining('迪士尼'),
        expect.stringContaining('优必选'),
      ]),
    )
    expect(wrapper.text()).not.toContain('BuzzBee')
    expect(wrapper.find('[data-testid="customer-choice-jp"]').exists()).toBe(false)

    await wrapper.get('[data-testid="customer-choice-index"]').trigger('click')
    const inputs = wrapper.findAll('input[type="file"]')
    expect(inputs[0]!.attributes('accept')).toBe('.pdf,.xls,.xlsx,.xlsm')
    expect(inputs[1]!.attributes('accept')).toBe('.xlsx')
    const po = new File(['po'], 'INDEX PO.pdf')
    const schedule = new File(['schedule'], '河源业务统一排期.xlsx')
    Object.defineProperty(inputs[0]!.element, 'files', { configurable: true, value: [po] })
    Object.defineProperty(inputs[1]!.element, 'files', { configurable: true, value: [schedule] })
    await inputs[0]!.trigger('change')
    await inputs[1]!.trigger('change')
    const parseButton = wrapper.findAll('button').find((button) => button.text().includes('解析并进入预览'))
    await parseButton!.trigger('click')
    await flushPromises()

    expect(customerOrderApiMock.previewMappedBatch).toHaveBeenLastCalledWith(
      'index',
      [po],
      schedule,
      expect.any(String),
      'huakang-d',
    )
  })

  it('does not offer external customer profiles from the Huakang C workspace', () => {
    const wrapper = mount(CustomerOrderCenterWorkspace, {
      props: {
        activeSection: 'import',
        factoryId: 'huakang-c',
        factoryName: '华康C厂',
      },
    })

    expect(wrapper.findAll('[data-testid^="customer-choice-"]')).toHaveLength(0)
  })

  it.each(['mismatched-response', 'factory-switch'])('rejects Disney preview crossing factory scope: %s', async (scenario) => {
    let resolvePreview!: (value: unknown) => void
    customerOrderApiMock.previewMappedBatch.mockReturnValueOnce(new Promise((resolve) => { resolvePreview = resolve }))
    const wrapper = mount(CustomerOrderCenterWorkspace, {
      props: { activeSection: 'import', factoryId: 'huakang-d', factoryName: '华康D' },
    })
    await wrapper.get('[data-testid="customer-choice-disney"]').trigger('click')
    const inputs = wrapper.findAll('input[type="file"]')
    for (const [index, file] of [new File(['po'], 'Disney.pdf'), new File(['xlsx'], 'D.xlsx')].entries()) {
      Object.defineProperty(inputs[index]!.element, 'files', { configurable: true, value: [file] })
      await inputs[index]!.trigger('change')
    }
    await wrapper.findAll('button').find((button) => button.text().includes('解析并进入预览'))!.trigger('click')
    if (scenario === 'factory-switch') await wrapper.setProps({ factoryId: 'huaxing' })
    resolvePreview({ factory_id: scenario === 'factory-switch' ? 'huakang-d' : 'huaxing', rows: [] })
    await flushPromises()
    if (scenario === 'mismatched-response') expect(wrapper.text()).toContain('已拒绝展示')
    expect(wrapper.emitted('navigate')).toBeUndefined()
    await wrapper.setProps({ activeSection: 'schedule' })
    await flushPromises()
    expect(wrapper.get('[data-testid="customer-order-ledger"]').text()).toContain('当前筛选范围没有订单记录。')
    expect(customerOrderLedgerApiMock.list).toHaveBeenLastCalledWith(scenario === 'factory-switch' ? 'huaxing' : 'huakang-d', expect.objectContaining({ view: 'all' }))
    wrapper.unmount()
  })

  it.each([['huakang-d', 'disney'], ['huaxing', 'disney'], ['huakang-d', 'ubtech']])('keeps mapped preview/export isolated while the persisted schedule remains an empty real ledger', async (factoryId, customerCode) => {
    const targetTemplate = customerCode === 'ubtech' ? 'HEYUAN_BUSINESS_UNIFIED_HUAKANG_D_UBTECH_V1' : factoryId === 'huakang-d'
      ? 'HEYUAN_BUSINESS_UNIFIED_HUAKANG_D_DISNEY_V1' : 'HEYUAN_BUSINESS_UNIFIED_HUAXING_V2'
    const preview = {
      customer_code: customerCode, factory_id: factoryId, preview_fingerprint: `${factoryId}-fingerprint`,
      po_file_count: 1, po_file_names: ['Disney.pdf'], po_file_name: 'Disney.pdf',
      schedule_file_name: 'schedule.xlsx', output_file_name: 'disney-new.xlsx',
      input_template: 'DISNEY', target_template: targetTemplate,
      summary: { total: 1, valid: 1, warning: 0, blocked: 0 }, warnings: [],
      rows: [{
        id: 'disney-1', status: 'valid', status_label: '可导出',
        issues: customerCode === 'ubtech' ? [{
          severity: 'warning', code: 'ubtech_ship_date_review', field: 'requested_ship_date',
          message: '默认使用PO需求日期，可按客户最新要求更正。', skip_key: 'date-key',
          can_edit: true, edit_field: 'requested_ship_date', edit_label: '客要求走货期', edit_input_type: 'date',
          can_skip: true, skip_label: '',
        }] : [], lineage: {},
        received_date: '2026-09-08', po_no: 'DISNEY-FACTORY-PO', contract_no: '',
        customer_country: '迪士尼 / DLR', customer_name: '迪士尼', product_no: '1000128076',
        product_name_zh: `${factoryId}产品`, product_name_en: 'MICKEY', quantity: '2502',
        units_per_carton: '6', carton_count: '417', standard: '', unit_price_hkd: '', amount_hkd: '',
        packaging: '', line_q: '', customer_q: '', requested_ship_date: '2026-11-30',
        input_template: 'DISNEY', target_template: targetTemplate, item_sheet_name: 'ITEM表',
        source_po_file_name: 'Disney.pdf',
      }],
    }
    customerOrderApiMock.previewMappedBatch.mockResolvedValueOnce(preview)
    customerOrderApiMock.exportMappedBatch.mockResolvedValueOnce({
      blob: new Blob(['xlsx']), fileName: 'disney-new.xlsx', passwordRequired: false,
    })
    const wrapper = mount(CustomerOrderCenterWorkspace, {
      props: { activeSection: 'import', factoryId, factoryName: factoryId },
    })
    expect(wrapper.findAll(`[data-testid="customer-choice-${customerCode}"]`)).toHaveLength(1)
    await wrapper.get(`[data-testid="customer-choice-${customerCode}"]`).trigger('click')
    const inputs = wrapper.findAll('input[type="file"]')
    expect(inputs[0]!.attributes('accept')).toBe('.pdf')
    const po = new File(['po'], 'Disney.pdf')
    const schedule = new File(['schedule'], 'schedule.xlsx')
    for (const [index, file] of [po, schedule].entries()) {
      Object.defineProperty(inputs[index]!.element, 'files', { configurable: true, value: [file] })
      await inputs[index]!.trigger('change')
    }
    await wrapper.findAll('button').find((button) => button.text().includes('解析并进入预览'))!.trigger('click')
    await flushPromises()
    expect(customerOrderApiMock.previewMappedBatch).toHaveBeenLastCalledWith(customerCode, [po], schedule, expect.any(String), factoryId)
    await wrapper.setProps({ activeSection: 'preview' })
    if (customerCode === 'ubtech') {
      await wrapper.get('[data-testid="open-field-resolution"]').trigger('click')
      const dialog = wrapper.get('[data-testid="blocker-resolution-dialog"]')
      expect(dialog.text()).toContain('可选更正')
      expect(dialog.text()).toContain('不填写则使用PO原值')
      expect(dialog.find('[data-testid="select-all-skippable-issues"]').exists()).toBe(false)
      await dialog.get('[aria-label="关闭人工处理窗口"]').trigger('click')
    }
    await wrapper.get('[data-testid="preview-next-step"] .button').trigger('click')
    await flushPromises()
    expect(customerOrderApiMock.exportMappedBatch).toHaveBeenLastCalledWith(
      customerCode, [po], schedule, expect.any(String), 'disney-new.xlsx', factoryId,
      [], `${factoryId}-fingerprint`, '', [],
    )
    await wrapper.setProps({ activeSection: 'schedule' })
    await flushPromises()
    expect(wrapper.get('[data-testid="customer-order-ledger"]').text()).toContain('当前筛选范围没有订单记录。')
    expect(wrapper.text()).not.toContain('DISNEY-FACTORY-PO')
    expect(customerOrderLedgerApiMock.list).toHaveBeenLastCalledWith(factoryId, expect.objectContaining({ view: 'all' }))
    const otherFactory = factoryId === 'huaxing' ? 'huakang-d' : 'huaxing'
    await wrapper.setProps({ factoryId: otherFactory })
    await flushPromises()
    expect(customerOrderLedgerApiMock.list).toHaveBeenLastCalledWith(otherFactory, expect.objectContaining({ view: 'all' }))
    wrapper.unmount()
  })

  it('shows five Huadeng customers including Goliath and routes Spin through mapped APIs', async () => {
    customerOrderApiMock.previewMappedBatch.mockResolvedValueOnce({
      preview_schema_version: 'customer-order-huadeng-mapped-preview-v1',
      customer_code: 'spin',
      factory_id: 'huadeng',
      po_file_name: 'Spin PO.pdf',
      po_file_names: ['Spin PO.pdf'],
      po_file_count: 1,
      schedule_file_name: '河源业务统一排期.xlsx',
      source_po_sha256: 'po',
      source_po_sha256s: ['po'],
      source_schedule_sha256: 'schedule',
      input_template: 'HUADENG_SPIN_PO_V1',
      target_template: 'HEYUAN_BUSINESS_UNIFIED_SCHEDULE_V1',
      output_file_name: '河源业务统一排期_Spin新单.xlsx',
      summary: { total: 0, valid: 0, warning: 0, blocked: 0 },
      rows: [],
      warnings: [],
    })
    const wrapper = mount(CustomerOrderCenterWorkspace, {
      props: {
        activeSection: 'import',
        factoryId: 'huadeng',
        factoryName: '华登厂',
      },
    })

    expect(wrapper.findAll('[data-testid^="customer-choice-"]')).toHaveLength(5)
    expect(wrapper.text()).toContain('Casdon')
    expect(wrapper.text()).toContain('Jakks')
    expect(wrapper.text()).toContain('Simba')
    expect(wrapper.find('[data-testid="customer-choice-goliath"]').exists()).toBe(true)
    expect(wrapper.text()).toContain('Spin')
    expect(wrapper.find('[data-testid="customer-choice-spin-master"]').exists()).toBe(false)
    expect(wrapper.text()).not.toContain('BuzzBee')

    await wrapper.get('[data-testid="customer-choice-spin"]').trigger('click')
    const inputs = wrapper.findAll('input[type="file"]')
    expect(inputs[0]!.attributes('accept')).toBe('.pdf,.xlsx,.xlsm')
    expect(inputs[1]!.attributes('accept')).toBe('.xlsx')
    const po = new File(['po'], 'Spin PO.pdf')
    const schedule = new File(['schedule'], '河源业务统一排期.xlsx')
    Object.defineProperty(inputs[0]!.element, 'files', { configurable: true, value: [po] })
    Object.defineProperty(inputs[1]!.element, 'files', { configurable: true, value: [schedule] })
    await inputs[0]!.trigger('change')
    await inputs[1]!.trigger('change')
    const parseButton = wrapper.findAll('button').find((button) => button.text().includes('解析并进入预览'))
    await parseButton!.trigger('click')
    await flushPromises()

    expect(customerOrderApiMock.previewMappedBatch).toHaveBeenLastCalledWith(
      'spin',
      [po],
      schedule,
      expect.any(String),
      'huadeng',
    )
  })

  it('uses a clear text link back to the sales-business module center', () => {
    expect(viewSource).toContain('aria-label="返回业务部模块中心"')
    expect(viewSource).toContain('<span>业务部模块中心</span>')
    expect(viewSource).not.toContain('<span class="order-nexus">Nexus</span>')
  })

  it('uses the Internal Quote Desk readability scale and responsive motion feedback', () => {
    expect(workspaceSource).toContain('--order-motion-normal: 220ms')
    expect(workspaceSource).toContain('font-size: 12px !important')
    expect(workspaceSource).toContain('@keyframes order-rise-in')
    expect(workspaceSource).toContain('@keyframes order-drop-pulse')
    expect(workspaceSource).toContain('@media (prefers-reduced-motion: reduce)')
    expect(viewSource).toContain('font-size: 18px')
    expect(viewSource).toContain('font-size: 14px')
    expect(viewSource).toContain('@keyframes order-main-enter')
  })

  it('renders the reference-inspired dashboard and navigates to the import flow', async () => {
    const wrapper = mount(CustomerOrderCenterWorkspace, {
      props: {
        activeSection: 'dashboard',
        factoryId: 'huaxing',
        factoryName: '华兴厂',
      },
    })

    expect(wrapper.get('[data-testid="order-dashboard"]').text()).toContain('客户订单中心')
    expect(wrapper.text()).toContain('流程 01')
    expect(wrapper.text()).toContain('流程 02')
    expect(wrapper.text()).toContain('已保存订单与走货台账')

    const importButton = wrapper.findAll('button').find((button) => button.text().includes('进入PO导入'))
    expect(importButton).toBeDefined()
    await importButton!.trigger('click')
    expect(wrapper.emitted('navigate')).toContainEqual(['import'])
  })

  it('shows PO mapping, full lineage, monthly delivery schedule and read-only production feedback', async () => {
    const wrapper = mount(CustomerOrderCenterWorkspace, {
      props: {
        activeSection: 'import',
        factoryId: 'huaxing',
        factoryName: '华兴厂',
      },
    })

    expect(wrapper.get('[data-testid="order-import"]').text()).toContain('导入客户原始 PO')
    expect(wrapper.text()).toContain('导入客户现有排期')
    expect(wrapper.text()).toContain('先选择 华兴厂 的客户')
    expect(wrapper.text()).toContain('BuzzBee')
    expect(wrapper.text()).toContain('Dickie')
    expect(wrapper.text()).toContain('彩星')
    expect(workspaceSource).toContain('WMC读取首页双语PO区')
    expect(workspaceSource).toContain('WMU从首页复用货号、品名及装箱数')
    expect(workspaceSource).toContain('按PO Attached逐行生成S/C与Walmart PO子订单')
    expect(workspaceSource).toContain('仅明确标注印尼的资料另行处理')
    expect(workspaceSource).toContain('已按 ${customerName} 映射处理')
    expect(workspaceSource).toContain('源排期文件未被覆盖')
    expect(workspaceSource).toContain('ITEM去向')

    expect(wrapper.text()).toContain('真实文件试用')
    expect(wrapper.text()).toContain('解析并进入预览')
    expect(workspaceSource).toContain('customerOrderApi.previewBuzzbeeBatch')
    expect(workspaceSource).toContain('customerOrderApi.exportBuzzbeeBatch')
    expect(workspaceSource).toContain('customerOrderApi.previewDickieBatch')
    expect(workspaceSource).toContain('customerOrderApi.exportDickieBatch')
    expect(workspaceSource).toContain('customerOrderApi.previewCaixingBatch')
    expect(workspaceSource).toContain('customerOrderApi.exportCaixingBatch')
    expect(workspaceSource).toContain('downloadGeneratedSchedule')
    expect(wrapper.text()).toContain('批量选择PO')
    expect(wrapper.get('input[type="file"][multiple]').exists()).toBe(true)

    await wrapper.setProps({ activeSection: 'preview' })
    const headings = wrapper.findAll('th').map((cell) => cell.text())
    for (const field of [
      '来单日期',
      'P/O#',
      'Contract No.',
      '客名/国家',
      '产品编号',
      '中文名称',
      '产品名称',
      '数量',
      '装箱数',
      '箱数',
      '国家标准',
      '单价HK',
      '金额HK',
      '包装',
      '行Q',
      '客Q',
      '客要求走货期',
    ]) {
      expect(headings).toContain(field)
    }

    const generateButton = wrapper.findAll('button').find((button) => button.text().includes('确认并生成客户排期'))
    expect(generateButton).toBeDefined()
    expect((generateButton!.element as HTMLButtonElement).disabled).toBe(true)
    expect(wrapper.text()).toContain('尚未建立真实预览批次')
    expect(wrapper.text()).toContain('显示 0 / 0 条')

    await wrapper.setProps({ activeSection: 'schedule' })
    await flushPromises()
    const scheduleView = wrapper.get('[data-testid="order-schedule"]')
    expect(scheduleView.text()).toContain('华兴厂总排期')
    expect(scheduleView.text()).toContain('仅展示本厂各客户订单的公共字段、发送状态和走货数量。')
    expect(scheduleView.text()).toContain('当前筛选范围没有订单记录。')
    expect(scheduleView.text()).not.toContain('0009382481')
    expect(scheduleView.text()).not.toContain('生产未完成')
  })

  it('uses the unified xlsx schedule for Caixing', async () => {
    const wrapper = mount(CustomerOrderCenterWorkspace, {
      props: {
        activeSection: 'import',
        factoryId: 'huaxing',
        factoryName: '华兴厂',
      },
    })

    const scheduleInputBeforeSelection = wrapper.findAll('input[type="file"]')[1]!
    expect(scheduleInputBeforeSelection.attributes('accept')).toBe('.xlsx')

    await wrapper.get('[data-testid="customer-choice-caixing"]').trigger('click')
    const scheduleInput = wrapper.findAll('input[type="file"]')[1]!
    expect(scheduleInput.attributes('accept')).toBe('.xlsx')
    Object.defineProperty(scheduleInput.element, 'files', {
      configurable: true,
      value: [new File(['schedule'], '河源业务统一排期.xlsx')],
    })
    await scheduleInput.trigger('change')

    expect(wrapper.text()).toContain('河源业务统一排期.xlsx')
  })

  it('offers a single-preview formal-PO reconciliation picker and submits its revision controls', async () => {
    customerOrderApiMock.previewBuzzbeeBatch.mockResolvedValueOnce({
      customer_code: 'buzzbee', factory_id: 'huaxing', preview_fingerprint: 'formal-preview',
      po_file_count: 1, po_file_names: ['PO.xlsx'], po_file_name: 'PO.xlsx', schedule_file_name: 'schedule.xlsx',
      output_file_name: 'schedule.xlsx', input_template: 'BUZZBEE_WALMART_WMC_INLINE_V1', target_template: 'BUZZBEE_PRODUCTION_SCHEDULE_V1',
      summary: { total: 1, valid: 1, warning: 0, blocked: 0 }, warnings: [],
      rows: [{ id: 'preview-line', status: 'valid', status_label: '有效', issues: [], lineage: {}, received_date: '2026-09-14', po_no: 'FORMAL-001', contract_no: '', customer_country: 'BuzzBee', customer_name: 'BuzzBee', product_no: '000123', product_name_zh: '产品', product_name_en: 'Product', quantity: '0100', units_per_carton: '', carton_count: '', standard: '', unit_price_hkd: '', amount_hkd: '', packaging: '', line_q: '', customer_q: '', requested_ship_date: '2026-10-01', input_template: 'BUZZBEE_WALMART_WMC_INLINE_V1', target_template: 'BUZZBEE_PRODUCTION_SCHEDULE_V1', item_sheet_name: '', source_po_file_name: 'PO.xlsx' }],
    })
    customerOrderLedgerApiMock.list
      .mockResolvedValueOnce({
        items: [
          { id: 'existing-1', factory_id: 'huaxing', customer_code: 'buzzbee', customer_name: 'BuzzBee', reference_no: 'SUP-001', product_no: '000123', quantity: '0100', shipped_quantity: '0000', remaining_quantity: '0100', status: 'active', version: 1, revision: 7, dispatch_status: 'sent', data: {}, created_at: '', updated_at: '' },
          { id: 'cancelled-1', factory_id: 'huaxing', customer_code: 'buzzbee', customer_name: 'BuzzBee', reference_no: 'CANCEL-001', product_no: '000123', quantity: '0100', shipped_quantity: '0000', remaining_quantity: '0100', status: 'cancelled', version: 1, revision: 1, dispatch_status: 'unsent', data: {}, created_at: '', updated_at: '' },
          { id: 'wrong-product', factory_id: 'huaxing', customer_code: 'buzzbee', customer_name: 'BuzzBee', reference_no: 'OTHER-001', product_no: '000124', quantity: '0100', shipped_quantity: '0000', remaining_quantity: '0100', status: 'active', version: 1, revision: 1, dispatch_status: 'unsent', data: {}, created_at: '', updated_at: '' },
        ], total: 101, page: 1, page_size: 50, customers: [],
      })
      .mockResolvedValueOnce({
        items: [{ id: 'existing-search', factory_id: 'huaxing', customer_code: 'buzzbee', customer_name: 'BuzzBee', reference_no: 'SUP-SEARCH', product_no: '000123', quantity: '0100', shipped_quantity: '0000', remaining_quantity: '0100', status: 'active', version: 1, revision: 8, dispatch_status: 'sent', data: {}, created_at: '', updated_at: '' }], total: 101, page: 1, page_size: 50, customers: [],
      })
      .mockResolvedValueOnce({
        items: [{ id: 'existing-next', factory_id: 'huaxing', customer_code: 'buzzbee', customer_name: 'BuzzBee', reference_no: 'SUP-NEXT', product_no: '000123', quantity: '0100', shipped_quantity: '0000', remaining_quantity: '0100', status: 'active', version: 1, revision: 9, dispatch_status: 'sent', data: {}, created_at: '', updated_at: '' }], total: 101, page: 2, page_size: 50, customers: [],
      })
    customerOrderLedgerApiMock.importConfirmed.mockResolvedValueOnce({ items: [], created_count: 0, existing_count: 0, reconciled_count: 1 })
    const wrapper = mount(CustomerOrderCenterWorkspace, { props: { activeSection: 'import', factoryId: 'huaxing', factoryName: '华兴厂' } })
    await wrapper.get('[data-testid="customer-choice-buzzbee"]').trigger('click')
    const inputs = wrapper.findAll('input[type="file"]')
    Object.defineProperty(inputs[0]!.element, 'files', { configurable: true, value: [new File(['po'], 'PO.xlsx')] })
    Object.defineProperty(inputs[1]!.element, 'files', { configurable: true, value: [new File(['schedule'], 'schedule.xlsx')] })
    await inputs[0]!.trigger('change')
    await inputs[1]!.trigger('change')
    await wrapper.findAll('button').find((button) => button.text().includes('解析并进入预览'))!.trigger('click')
    await flushPromises()
    await wrapper.setProps({ activeSection: 'preview' })
    const card = wrapper.get('[data-testid="order-reconciliation-card"]')
    expect(card.text()).toContain('关联已有订单')
    await card.get('input[type="checkbox"]').setValue(true)
    await flushPromises()
    const select = card.get('select')
    expect(select.text()).toContain('SUP-001 · 000123 · 数量 0100')
    expect(select.text()).not.toContain('CANCEL-001')
    expect(select.text()).not.toContain('OTHER-001')
    await card.get('input[type="search"]').setValue('SUP')
    await card.findAll('button').find((button) => button.text() === '搜索已有订单')!.trigger('click')
    await flushPromises()
    expect(customerOrderLedgerApiMock.list).toHaveBeenLastCalledWith('huaxing', expect.objectContaining({ q: 'SUP', page: 1 }))
    expect(select.text()).toContain('SUP-SEARCH · 000123 · 数量 0100')
    await card.findAll('button').find((button) => button.text() === '下一页')!.trigger('click')
    await flushPromises()
    expect(customerOrderLedgerApiMock.list).toHaveBeenLastCalledWith('huaxing', expect.objectContaining({ q: 'SUP', page: 2 }))
    expect(select.text()).toContain('SUP-NEXT · 000123 · 数量 0100')
    await select.setValue('existing-next')
    await card.get('textarea').setValue('正式 PO 已核对数量与交期')
    await wrapper.findAll('button').find((button) => button.text().includes('确认并保存订单'))!.trigger('click')
    await flushPromises()
    const payload = customerOrderLedgerApiMock.importConfirmed.mock.calls[0]![1] as FormData
    expect(payload.get('reconcile_line_id')).toBe('existing-next')
    expect(payload.get('expected_revision')).toBe('9')
    expect(payload.get('reconciliation_reason')).toBe('正式 PO 已核对数量与交期')
    expect(wrapper.text()).toContain('订单已关联并更新原订单')
  })

  it('writes a manual value for a missing field and clears the blocker', async () => {
    customerOrderApiMock.exportBuzzbeeBatch.mockResolvedValueOnce({
      blob: new Blob(['schedule']),
      fileName: 'schedule.xlsx',
      passwordRequired: false,
    })
    customerOrderApiMock.previewBuzzbeeBatch.mockResolvedValueOnce({
      preview_schema_version: 'customer-order-buzzbee-preview-v1',
      customer_code: 'buzzbee',
      factory_id: 'huaxing',
      po_file_name: '2个PO文件',
      po_file_names: ['PO-1.xlsx', 'PO-2.xlsx'],
      po_file_count: 2,
      schedule_file_name: 'schedule.xlsx',
      source_po_sha256: 'po',
      source_po_sha256s: ['po-1', 'po-2'],
      source_schedule_sha256: 'schedule',
      input_template: 'BUZZBEE_WALMART_WMC_INLINE_V1',
      target_template: 'BUZZBEE_PRODUCTION_SCHEDULE_V1',
      output_file_name: 'schedule.xlsx',
      summary: { total: 1, valid: 0, warning: 0, blocked: 1 },
      warnings: [],
      rows: [{
        id: 'buzzbee-53138-67771-1',
        status: 'blocked',
        status_label: '阻断',
        received_date: '2026-07-27',
        po_no: '0009382481',
        contract_no: '53138',
        customer_country: 'WMC / 加拿大',
        customer_name: 'WMC',
        country: '加拿大',
        product_no: '67771',
        product_name_zh: '双管枪',
        product_name_en: 'AF DOUBLE FIRE',
        quantity: '3000',
        units_per_carton: '5',
        carton_count: '600',
        standard: '加拿大标准',
        unit_price_hkd: '',
        amount_hkd: '',
        packaging: '67771-05-26-WMC',
        line_q: '2026-09-17',
        customer_q: '2026-09-17',
        requested_ship_date: '2026-09-17',
        input_template: 'BUZZBEE_WALMART_WMC_INLINE_V1',
        target_template: 'BUZZBEE_PRODUCTION_SCHEDULE_V1',
        item_sheet_name: '子弹枪ITEM表',
        source_po_file_name: 'PO-1.xlsx',
        lineage: {},
        issues: [{
          severity: 'blocked',
          code: 'missing_unit_price',
          field: 'unit_price_hkd',
          message: '产品 67771 在当前排期中没有可确认的 HKD 单价',
          can_skip: true,
          skip_key: 'buzzbee-53138-67771-1|missing_unit_price|unit_price_hkd',
          skip_label: '单价及金额留空，稍后由跟客补充',
          can_edit: true,
          edit_field: 'unit_price_hkd',
          edit_label: '单价 HKD',
          edit_input_type: 'number',
        }],
      }],
    })
    const wrapper = mount(CustomerOrderCenterWorkspace, {
      props: {
        activeSection: 'import',
        factoryId: 'huaxing',
        factoryName: '华兴厂',
      },
    })
    await wrapper.get('[data-testid="customer-choice-buzzbee"]').trigger('click')
    const inputs = wrapper.findAll('input[type="file"]')
    Object.defineProperty(inputs[0]!.element, 'files', {
      configurable: true,
      value: [new File(['po-1'], 'PO-1.xlsx'), new File(['po-2'], 'PO-2.xlsx')],
    })
    Object.defineProperty(inputs[1]!.element, 'files', {
      configurable: true,
      value: [new File(['schedule'], 'schedule.xlsx')],
    })
    await inputs[0]!.trigger('change')
    await inputs[1]!.trigger('change')
    const poSelectionSummary = wrapper.findAll('.upload-card strong')[0]
    expect(poSelectionSummary!.text()).toBe('已选择 2 份 PO')
    expect(poSelectionSummary!.attributes('title')).toBe('PO-1.xlsx\nPO-2.xlsx')
    const parseButton = wrapper.findAll('button').find((button) => button.text().includes('解析并进入预览'))
    await parseButton!.trigger('click')
    await flushPromises()
    await wrapper.setProps({ activeSection: 'preview' })

    const openResolutionButton = wrapper.findAll('button')
      .find((button) => button.text().includes('打开待确认/阻断处理'))
    expect(openResolutionButton).toBeDefined()
    await openResolutionButton!.trigger('click')
    const resolutionDialog = wrapper.get('[data-testid="blocker-resolution-dialog"]')
    expect(resolutionDialog.attributes('role')).toBe('dialog')
    expect(resolutionDialog.text()).toContain('补录缺失内容或人工确认放行')
    expect(resolutionDialog.text()).toContain('确认缺失并放行')
    expect(resolutionDialog.get('[data-testid="select-all-skippable-issues"]').text()).toContain('全选可放行项（1）')
    expect(wrapper.text()).toContain('2 份PO')
    expect(wrapper.text()).toContain('单价及金额留空，稍后由跟客补充')
    const manualInput = resolutionDialog.get('.manual-override-field input')
    await manualInput.setValue('18.50')
    expect(wrapper.text()).toContain('已人工补录')
    expect(wrapper.text()).toContain('18.50')
    expect(wrapper.get('.summary-strip .blocked strong').text()).toBe('0')
    expect(wrapper.get('[data-testid="confirmation-reason-card"]').text()).toContain('人工确认原因')
    const generateButton = wrapper.get('[data-testid="preview-next-step"] .button')
    expect((generateButton.element as HTMLButtonElement).disabled).toBe(true)
    await wrapper.get('[data-testid="confirmation-reason-card"] textarea').setValue(
      '已向客户确认正确单价并人工补录',
    )
    expect((generateButton.element as HTMLButtonElement).disabled).toBe(false)
    await generateButton.trigger('click')
    await flushPromises()
    expect(customerOrderApiMock.exportBuzzbeeBatch).toHaveBeenLastCalledWith(
      expect.any(Array),
      expect.any(File),
      expect.any(String),
      'schedule.xlsx',
      'huaxing',
      ['buzzbee-53138-67771-1|missing_unit_price|unit_price_hkd'],
      undefined,
      '已向客户确认正确单价并人工补录',
      [{
        row_id: 'buzzbee-53138-67771-1',
        issue_key: 'buzzbee-53138-67771-1|missing_unit_price|unit_price_hkd',
        field: 'unit_price_hkd',
        value: '18.50',
      }],
    )
  })

  it('does not treat an unconfirmed preview as a persisted factory schedule', async () => {
    const wrapper = mount(CustomerOrderCenterWorkspace, {
      props: {
        activeSection: 'schedule',
        factoryId: 'huaxing',
        factoryName: '华兴厂',
      },
    })

    await flushPromises()
    expect(wrapper.get('[data-testid="customer-order-ledger"]').text()).toContain('当前筛选范围没有订单记录。')
    expect(wrapper.text()).not.toContain('生产未完成')
  })

  it('keeps real ledger requests isolated to the active factory and never shows demo orders', async () => {
    const huakangA = mount(CustomerOrderCenterWorkspace, {
      props: {
        activeSection: 'schedule',
        factoryId: 'huakang-a',
        factoryName: '华康A厂',
      },
    })

    await flushPromises()
    expect(huakangA.get('[data-testid="customer-order-ledger"]').text()).toContain('当前筛选范围没有订单记录。')
    expect(huakangA.text()).not.toContain('BuzzBee / WMC')

    const huaxing = mount(CustomerOrderCenterWorkspace, {
      props: {
        activeSection: 'schedule',
        factoryId: 'huaxing',
        factoryName: '华兴厂',
      },
    })

    await flushPromises()
    expect(huaxing.get('[data-testid="customer-order-ledger"]').text()).toContain('当前筛选范围没有订单记录。')
    expect(huaxing.text()).not.toContain('BuzzBee / WMC')

    const huakangDashboard = mount(CustomerOrderCenterWorkspace, {
      props: {
        activeSection: 'dashboard',
        factoryId: 'huakang-a',
        factoryName: '华康A厂',
      },
    })

    expect(huakangDashboard.get('.metric-grid').text()).toContain('当前导入批次0')
    expect(huakangDashboard.get('.metric-grid').text()).toContain('待确认数据0')
    expect(huakangDashboard.get('.activity-table tbody').text()).toContain('当前厂区暂无处理记录')
    expect(huakangDashboard.text()).not.toContain('BuzzBee')

    const huakangLedger = mount(CustomerOrderCenterWorkspace, {
      props: {
        activeSection: 'ledger',
        factoryId: 'huakang-a',
        factoryName: '华康A厂',
      },
    })

    await flushPromises()
    expect(huakangLedger.get('[data-testid="customer-order-ledger"]').text()).toContain('当前筛选范围没有订单记录。')
    expect(huakangLedger.get('select[aria-label="筛选客户"]').findAll('option')).toHaveLength(1)
    expect(huakangLedger.text()).not.toContain('BuzzBee')

    const huakangExceptions = mount(CustomerOrderCenterWorkspace, {
      props: {
        activeSection: 'exceptions',
        factoryId: 'huakang-a',
        factoryName: '华康A厂',
      },
    })

    expect(huakangExceptions.findAll('.exception-kpis strong').map((item) => item.text())).toEqual(['0', '0', '0'])
    expect(huakangExceptions.get('.empty-exception').text()).toContain('当前没有独立风险数据')
    expect(huakangExceptions.text()).not.toContain('BuzzBee')
  })

  it('accepts multiple PO files and one schedule through the upload drop zones', async () => {
    const wrapper = mount(CustomerOrderCenterWorkspace, {
      props: {
        activeSection: 'import',
        factoryId: 'huaxing',
        factoryName: '华兴厂',
      },
    })
    await wrapper.get('[data-testid="customer-choice-buzzbee"]').trigger('click')
    const poDropZone = wrapper.get('[data-testid="po-drop-zone"]')
    const scheduleDropZone = wrapper.get('[data-testid="schedule-drop-zone"]')
    const poFiles = [
      new File(['po-1'], 'PO-1.xls'),
      new File(['po-2'], 'PO-2.xlsx'),
    ]
    const scheduleFiles = [new File(['schedule'], '2026年 BUZZ BEE 生产排期表.xls.xlsx')]

    await poDropZone.trigger('dragover', {
      dataTransfer: { files: [], dropEffect: 'none' },
    })
    expect(poDropZone.classes()).toContain('upload-card--dragging')

    await poDropZone.trigger('drop', {
      dataTransfer: { files: poFiles },
    })
    await scheduleDropZone.trigger('drop', {
      dataTransfer: { files: scheduleFiles },
    })

    expect(poDropZone.classes()).not.toContain('upload-card--dragging')
    expect(poDropZone.get('strong').text()).toBe('已选择 2 份 PO')
    expect(poDropZone.get('strong').attributes('title')).toBe('PO-1.xls\nPO-2.xlsx')
    expect(scheduleDropZone.get('strong').text()).toBe('2026年 BUZZ BEE 生产排期表.xls.xlsx')
    expect(wrapper.text()).toContain('也可直接拖入此区域')
  })

  it('ignores macOS metadata files and keeps only the real Yinhui PO', async () => {
    const wrapper = mount(CustomerOrderCenterWorkspace, {
      props: {
        activeSection: 'import',
        factoryId: 'huaxing',
        factoryName: '华兴厂',
      },
    })
    await wrapper.get('[data-testid="customer-choice-yinhui"]').trigger('click')
    const poDropZone = wrapper.get('[data-testid="po-drop-zone"]')

    await poDropZone.trigger('drop', {
      dataTransfer: {
        files: [new File(['Mac OS X metadata'], '._RR-4500002299.pdf')],
      },
    })

    expect(poDropZone.get('strong').text()).toBe('尚未选择 PO 文件')
    expect(wrapper.get('[role="status"]').text()).toContain('Mac 解压产生的隐藏资源文件')
    expect(wrapper.get('[role="status"]').text()).toContain('不带“._”前缀')

    await poDropZone.trigger('drop', {
      dataTransfer: {
        files: [
          new File(['metadata'], '._RR-4500002299.pdf'),
          new File(['%PDF-1.7'], 'RR-4500002299.pdf', { type: 'application/pdf' }),
        ],
      },
    })

    expect(poDropZone.get('strong').text()).toBe('RR-4500002299.pdf')
    expect(poDropZone.get('strong').attributes('title')).toBe('RR-4500002299.pdf')
    expect(wrapper.get('[role="status"]').text()).toContain('已自动忽略 1 个 Mac 隐藏资源文件')
    expect(wrapper.get('[role="status"]').text()).toContain('已选择 1 份真实 PO')
  })

  it('requires a factory-owned customer and switches PO file types and APIs for Dickie', async () => {
    customerOrderApiMock.previewDickieBatch.mockResolvedValueOnce({
      preview_schema_version: 'customer-order-dickie-preview-v1',
      customer_code: 'dickie',
      factory_id: 'huaxing',
      po_file_name: 'SC700142026-1200.pdf',
      po_file_names: ['SC700142026-1200.pdf'],
      po_file_count: 1,
      schedule_file_name: '2026年.Dickie 生产情况.xlsx',
      source_po_sha256: 'po',
      source_po_sha256s: ['po'],
      source_schedule_sha256: 'schedule',
      input_template: 'DICKIE_SIMBA_RELEASE_ORDER_PDF_V1',
      target_template: 'DICKIE_PRODUCTION_SCHEDULE_V1',
      output_file_name: '2026年.Dickie 生产情况.xlsx',
      summary: { total: 0, valid: 0, warning: 0, blocked: 0 },
      warnings: [],
      rows: [],
    })
    customerOrderApiMock.exportDickieBatch.mockResolvedValueOnce({
      blob: new Blob(['dickie-schedule']),
      fileName: '2026年.Dickie 生产情况.xlsx',
    })
    const wrapper = mount(CustomerOrderCenterWorkspace, {
      props: {
        activeSection: 'import',
        factoryId: 'huaxing',
        factoryName: '华兴厂',
      },
    })

    const uploadButtons = wrapper.findAll('.upload-card .button')
    expect(uploadButtons.every((button) => (button.element as HTMLButtonElement).disabled)).toBe(true)
    expect(wrapper.get('[data-testid="factory-customer-selector"]').text()).toContain('每个客户使用独立 PO 识别和排期写入规则')

    await wrapper.get('[data-testid="customer-choice-dickie"]').trigger('click')
    expect(wrapper.get('[data-testid="customer-choice-dickie"]').attributes('aria-pressed')).toBe('true')
    const inputs = wrapper.findAll('input[type="file"]')
    expect(inputs[0]!.attributes('accept')).toBe('.pdf')
    expect(uploadButtons.every((button) => !(button.element as HTMLButtonElement).disabled)).toBe(true)

    Object.defineProperty(inputs[0]!.element, 'files', {
      configurable: true,
      value: [new File(['%PDF'], 'SC700142026-1200.pdf', { type: 'application/pdf' })],
    })
    Object.defineProperty(inputs[1]!.element, 'files', {
      configurable: true,
      value: [new File(['schedule'], '2026年.Dickie 生产情况.xlsx')],
    })
    await inputs[0]!.trigger('change')
    await inputs[1]!.trigger('change')
    const parseButton = wrapper.findAll('button').find((button) => button.text().includes('解析并进入预览'))
    await parseButton!.trigger('click')
    await flushPromises()

    expect(customerOrderApiMock.previewDickieBatch).toHaveBeenCalledOnce()
    expect(wrapper.emitted('navigate')).toContainEqual(['preview'])

    await wrapper.setProps({ activeSection: 'preview' })
    expect(wrapper.get('[data-testid="preview-next-step"]').text()).toContain('当前尚未输出排期')
    const generateButton = wrapper.get('[data-testid="preview-next-step"] .button')
    expect(generateButton.text()).toContain('生成并下载客户排期')
    await generateButton.trigger('click')
    await flushPromises()

    expect(customerOrderApiMock.exportDickieBatch).toHaveBeenCalledOnce()
    expect(wrapper.get('[data-testid="generated-schedule-output"]').text()).toContain(
      '2026年.Dickie 生产情况.xlsx',
    )
  })

  it('keeps a Dickie parse failure visible in the import page', async () => {
    customerOrderApiMock.previewDickieBatch.mockRejectedValueOnce(
      new Error('Dickie PDF OCR 失败：附件页无法识别'),
    )
    const wrapper = mount(CustomerOrderCenterWorkspace, {
      props: {
        activeSection: 'import',
        factoryId: 'huaxing',
        factoryName: '华兴厂',
      },
    })

    await wrapper.get('[data-testid="customer-choice-dickie"]').trigger('click')
    const inputs = wrapper.findAll('input[type="file"]')
    Object.defineProperty(inputs[0]!.element, 'files', {
      configurable: true,
      value: [new File(['%PDF'], 'SC700130503-200.pdf', { type: 'application/pdf' })],
    })
    Object.defineProperty(inputs[1]!.element, 'files', {
      configurable: true,
      value: [new File(['schedule'], '2026年.Dickie 生产情况.xlsx')],
    })
    await inputs[0]!.trigger('change')
    await inputs[1]!.trigger('change')
    const parseButton = wrapper.findAll('button').find((button) => button.text().includes('解析并进入预览'))
    await parseButton!.trigger('click')
    await flushPromises()

    const alert = wrapper.get('[data-testid="import-parse-alert"]')
    expect(alert.attributes('role')).toBe('alert')
    expect(alert.text()).toContain('解析未完成')
    expect(alert.text()).toContain('Dickie PDF OCR 失败：附件页无法识别')
    expect(wrapper.emitted('navigate')).toBeUndefined()
  })

  it('keeps duplicate orders visible and allows test-stage confirmation', async () => {
    customerOrderApiMock.previewDickieBatch.mockResolvedValueOnce({
      preview_schema_version: 'customer-order-dickie-preview-v1',
      customer_code: 'dickie',
      factory_id: 'huaxing',
      po_file_name: 'SC700130503-200.pdf',
      po_file_names: ['SC700130503-200.pdf'],
      po_file_count: 1,
      schedule_file_name: '2026年.Dickie 生产情况.xlsx',
      source_po_sha256: 'po',
      source_po_sha256s: ['po'],
      source_schedule_sha256: 'schedule',
      input_template: 'DICKIE_SIMBA_RELEASE_ORDER_PDF_V1',
      target_template: 'DICKIE_PRODUCTION_SCHEDULE_V1',
      output_file_name: '2026年.Dickie 生产情况.xlsx',
      summary: { total: 1, valid: 0, warning: 0, blocked: 1 },
      warnings: [],
      rows: [{
        id: 'dickie-SC700130503-200',
        status: 'blocked',
        status_label: '阻断',
        received_date: '2026-08-03',
        po_no: '',
        contract_no: '300459663/60',
        customer_country: 'Dickie Germany',
        customer_name: 'Dickie Germany',
        country: '德国',
        product_no: '203712034ASW',
        product_name_zh: '',
        product_name_en: 'RC My First NL, 4-asst',
        quantity: '14004',
        units_per_carton: '12',
        carton_count: '1167',
        standard: '欧洲标准',
        unit_price_hkd: '',
        amount_hkd: '',
        packaging: 'Dickie open box',
        line_q: '2026-07-04',
        customer_q: '',
        requested_ship_date: '2026-07-04',
        input_template: 'DICKIE_SIMBA_RELEASE_ORDER_PDF_V1',
        target_template: 'DICKIE_PRODUCTION_SCHEDULE_V1',
        item_sheet_name: 'Iteam表',
        source_po_file_name: 'SC700130503-200.pdf',
        lineage: {},
        issues: [{
          severity: 'blocked',
          code: 'duplicate_reference',
          field: 'reference_no',
          message: 'Reference SC700130503-200 已存在于当前排期 Iteam表第 561 行；测试阶段可人工确认后重复导入',
          can_skip: true,
          skip_key: 'dickie-SC700130503-200|duplicate_reference|reference_no',
          skip_label: '测试阶段确认重复导入当前排期已有 Reference',
        }],
      }],
    })
    const wrapper = mount(CustomerOrderCenterWorkspace, {
      props: {
        activeSection: 'import',
        factoryId: 'huaxing',
        factoryName: '华兴厂',
      },
    })

    await wrapper.get('[data-testid="customer-choice-dickie"]').trigger('click')
    const inputs = wrapper.findAll('input[type="file"]')
    Object.defineProperty(inputs[0]!.element, 'files', {
      configurable: true,
      value: [new File(['%PDF'], 'SC700130503-200.pdf', { type: 'application/pdf' })],
    })
    Object.defineProperty(inputs[1]!.element, 'files', {
      configurable: true,
      value: [new File(['schedule'], '2026年.Dickie 生产情况.xlsx')],
    })
    await inputs[0]!.trigger('change')
    await inputs[1]!.trigger('change')
    const parseButton = wrapper.findAll('button').find((button) => button.text().includes('解析并进入预览'))
    await parseButton!.trigger('click')
    await flushPromises()

    expect(wrapper.get('[data-testid="import-parse-alert"]').text()).toContain('可人工确认后重复导入')
    await wrapper.setProps({ activeSection: 'preview' })
    const previewAlert = wrapper.get('[data-testid="preview-blocker-alert"]')
    expect(previewAlert.text()).toContain('当前批次有 1 项待人工处理')
    expect(previewAlert.text()).toContain('SC700130503-200.pdf')
    expect(previewAlert.text()).toContain('Iteam表第 561 行')
    expect(wrapper.text()).toContain('待确认')
    const summaryCards = wrapper.findAll('.summary-strip article')
    expect(summaryCards[2]!.text()).toContain('警告/待确认1')
    expect(summaryCards[2]!.text()).toContain('不形成阻断')
    expect(summaryCards[3]!.text()).toContain('待人工处理0')
    const pendingGenerateButton = wrapper.findAll('button')
      .find((button) => button.text().includes('确认重复订单后生成'))
    expect(pendingGenerateButton?.attributes('disabled')).toBeDefined()

    const confirmation = wrapper.get('.skip-issue-option')
    expect(confirmation.text()).toContain('确认重复订单')
    await confirmation.get('input').trigger('change')

    expect(wrapper.find('[data-testid="preview-blocker-alert"]').exists()).toBe(false)
    expect(wrapper.text()).toContain('已确认通过')
    const generateButton = wrapper.findAll('button')
      .find((button) => button.text().includes('生成并下载客户排期'))
    expect(generateButton?.attributes('disabled')).toBeUndefined()
  })

  it('selects Huaxing Caixing and routes Playmates PDFs to the three-sheet schedule flow', async () => {
    const caixingRowBase = {
      status: 'valid' as const,
      status_label: '有效',
      received_date: '2026-05-27',
      po_no: 'OL-1932232',
      contract_no: 'SL-1926604',
      customer_country: 'EUROPLAY-PHI',
      customer_name: 'EUROPLAY-PHI',
      country: '',
      product_name_zh: '',
      standard: '美国标准',
      unit_price_hkd: '',
      amount_hkd: '',
      packaging: '美版彩盒',
      line_q: '',
      customer_q: '',
      requested_ship_date: '2026-07-15',
      input_template: 'CAIXING_PLAYMATES_PO_PDF_V2',
      target_template: 'CAIXING_PRODUCTION_SCHEDULE_REVIEW_ORDER_ITEM_V2',
      item_sheet_name: '正单评审表 / 接单表 / ITEM表',
      source_po_file_name: '1931815.pdf',
      lineage: {},
      issues: [],
    }
    customerOrderApiMock.previewCaixingBatch.mockResolvedValueOnce({
      preview_schema_version: 'customer-order-caixing-preview-v2',
      customer_code: 'caixing',
      factory_id: 'huaxing',
      po_file_name: '1931815.pdf',
      po_file_names: ['1931815.pdf'],
      po_file_count: 1,
      schedule_file_name: '2026年彩星排期.xlsx',
      source_po_sha256: 'po',
      source_po_sha256s: ['po'],
      source_schedule_sha256: 'schedule',
      input_template: 'CAIXING_PLAYMATES_PO_PDF_V2',
      target_template: 'CAIXING_PRODUCTION_SCHEDULE_REVIEW_ORDER_ITEM_V2',
      output_file_name: '2026年彩星排期.xlsx',
      summary: { total: 2, valid: 2, warning: 0, blocked: 0 },
      warnings: [],
      rows: [
        {
          ...caixingRowBase,
          id: 'caixing-parent-57810',
          row_role: 'parent',
          parent_product_no: '',
          product_no: '57810 E8',
          product_name_en: 'WINX CLUB FAIRIES ASST',
          quantity: '1800',
          units_per_carton: '8',
          carton_count: '225',
        },
        {
          ...caixingRowBase,
          id: 'caixing-detail-57811',
          row_role: 'detail',
          parent_product_no: '57810 E8',
          product_no: '57811 E8',
          product_name_en: 'WINX CLUB BLOOM FAIRY DOLL',
          quantity: '675',
          units_per_carton: '3',
          carton_count: '225',
          unit_price_hkd: '31.01',
          amount_hkd: '20931.75',
        },
      ],
    })
    customerOrderApiMock.exportCaixingBatch.mockResolvedValueOnce({
      blob: new Blob(['caixing-schedule']),
      fileName: '2026年彩星排期.xlsx',
      passwordRequired: false,
    })
    const wrapper = mount(CustomerOrderCenterWorkspace, {
      props: {
        activeSection: 'import',
        factoryId: 'huaxing',
        factoryName: '华兴厂',
      },
    })

    await wrapper.get('[data-testid="customer-choice-caixing"]').trigger('click')
    expect(wrapper.get('[data-testid="customer-choice-caixing"]').attributes('aria-pressed')).toBe('true')
    expect(wrapper.text()).toContain('彩星 V2')
    expect(wrapper.text()).toContain('重复订单是否允许确认以当前环境策略和预览结果为准')
    expect(wrapper.text()).toContain('华兴 彩星 最新统一排期（含 ITEM 分类页）')
    const inputs = wrapper.findAll('input[type="file"]')
    expect(inputs[0]!.attributes('accept')).toBe('.pdf')

    Object.defineProperty(inputs[0]!.element, 'files', {
      configurable: true,
      value: [new File(['%PDF'], '1931815.pdf', { type: 'application/pdf' })],
    })
    Object.defineProperty(inputs[1]!.element, 'files', {
      configurable: true,
      value: [new File(['schedule'], '2026年彩星排期.xlsx')],
    })
    await inputs[0]!.trigger('change')
    await inputs[1]!.trigger('change')
    const parseButton = wrapper.findAll('button').find((button) => button.text().includes('解析并进入预览'))
    await parseButton!.trigger('click')
    await flushPromises()

    expect(customerOrderApiMock.previewCaixingBatch).toHaveBeenCalledOnce()
    await wrapper.setProps({ activeSection: 'preview' })
    expect(wrapper.get('[data-testid="order-preview"]').text()).toContain('彩星 PO 映射预览')
    expect(wrapper.get('[data-testid="order-preview"]').text()).toContain('全部 彩星')
    expect(wrapper.get('[data-testid="order-preview"]').text()).toContain('当前彩星输入规则已启用')
    expect(wrapper.get('[data-testid="order-preview"]').text()).toContain(
      '接单表、正单评审表关联实际明细页和行',
    )
    const hierarchyRows = wrapper.findAll('.unified-table tbody tr')
    expect(hierarchyRows[0]!.text()).toContain('大货号')
    expect(hierarchyRows[0]!.text()).toContain('57810 E8')
    expect(hierarchyRows[0]!.text()).toContain('1800')
    expect(hierarchyRows[0]!.text()).toContain('8')
    expect(hierarchyRows[1]!.text()).toContain('小货号')
    expect(hierarchyRows[1]!.text()).toContain('57811 E8')
    expect(hierarchyRows[1]!.text()).toContain('675')
    expect(hierarchyRows[1]!.text()).toContain('3')
    expect(wrapper.get('[data-testid="order-preview"]').text()).not.toContain('BuzzBee PO 映射预览')
    await wrapper.get('[data-testid="preview-next-step"] .button').trigger('click')
    await flushPromises()

    expect(customerOrderApiMock.exportCaixingBatch).toHaveBeenCalledOnce()
    expect(wrapper.get('[data-testid="generated-schedule-output"]').text()).toContain(
      '2026年彩星排期.xlsx',
    )
  })

  it('labels exceptions as a non-persistent preview aid and omits production mock data', async () => {
    const wrapper = mount(CustomerOrderCenterWorkspace, {
      props: {
        activeSection: 'exceptions',
        factoryId: 'huaxing',
        factoryName: '华兴厂',
      },
    })

    const exceptionView = wrapper.get('[data-testid="order-exceptions"]')
    expect(exceptionView.text()).toContain('异常与提醒中心')
    expect(exceptionView.text()).toContain('预览辅助页 · 非订单台账')
    expect(exceptionView.text()).toContain('订单台账不包含生产、物料、库存或排产数据')
    expect(wrapper.findAll('.exception-item')).toHaveLength(0)
    expect(exceptionView.text()).not.toContain('生产状态：')
    expect(exceptionView.text()).not.toContain('包装物料未齐')
  })
})
