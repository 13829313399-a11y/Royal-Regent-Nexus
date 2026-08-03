import { flushPromises, mount } from '@vue/test-utils'
import { readFileSync } from 'node:fs'
import { join } from 'node:path'
import { describe, expect, it, vi } from 'vitest'
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

vi.mock('@/api/customerOrder', () => ({
  customerOrderApi: customerOrderApiMock,
}))

const read = (path: string) => readFileSync(join(process.cwd(), path), 'utf8')
const routerSource = read('src/router/index.ts')
const enterpriseSource = read('src/data/enterpriseMock.ts')
const viewSource = read('src/views/CustomerOrderCenterView.vue')
const workspaceSource = read('src/components/modules/sales/customer-order-center/CustomerOrderCenterWorkspace.vue')

describe('customer order center static frontend', () => {
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
    expect(viewSource).toContain('PO 入客户排期并输出')
    expect(viewSource).toContain('厂区月度走货与生产反馈')
    expect(viewSource).toContain("label: '异常与提醒'")
    expect(viewSource).toContain('交付异常与生产提醒')
    expect(workspaceSource).toContain('仍不提交PMC、不计算库存，也不进入啤机、喷油或装配排产')
    expect(workspaceSource).toContain('这张总排期是系统数据，不是第三张Excel')
    expect(workspaceSource).toContain('客户订单中心不能修改生产任务或完成数量')
    expect(workspaceSource).not.toContain('生成更新后的总排期')
    expect(workspaceSource).not.toContain('确认并发布至PMC')
  })

  it('registers EDU, 360, Yinhui, SEASONS, Maxx and Shushupapa under Huaxing', () => {
    for (const code of ['edu', '360', 'yinhui', 'seasons', 'maxx', 'shushupapa']) {
      expect(workspaceSource).toContain(`code: '${code}'`)
      expect(workspaceSource).toContain(`customer-choice-${'$'}{customer.code}`)
    }
    expect(workspaceSource).toContain('previewMappedBatch')
    expect(workspaceSource).toContain('exportMappedBatch')
  })

  it('registers Casdon, Jakks, Simba, Spin and Spin Master under Huadeng', () => {
    for (const code of ['casdon', 'jakks', 'simba', 'spin', 'spin-master']) {
      expect(workspaceSource).toContain(`code: '${code}'`)
    }
    expect(workspaceSource).toContain('huadeng: [')
    expect(workspaceSource).toContain('HUADENG_CASDON_NEW_ORDER_V1')
    expect(workspaceSource).toContain('HUADENG_SPIN_MASTER_NEW_ORDER_V1')
  })

  it('registers an independently mapped 360 customer under Huakang A', () => {
    expect(workspaceSource).toContain("'huakang-a': [")
    expect(workspaceSource).toContain('HUAKANG_A_360_NEW_ORDER_V1')
    expect(workspaceSource).toContain('ThreeSixty PURCHASE ORDER RELEASE')
    expect(workspaceSource).toContain('360客排期表新单')
  })

  it('shows only 360 in Huakang A and routes it with the Huakang A factory id', async () => {
    customerOrderApiMock.previewMappedBatch.mockResolvedValueOnce({
      preview_schema_version: 'customer-order-huakang-a-mapped-preview-v1',
      customer_code: '360',
      factory_id: 'huakang-a',
      po_file_name: 'RL-100-1.xls',
      po_file_names: ['RL-100-1.xls'],
      po_file_count: 1,
      schedule_file_name: '华康A 360排期.xlsx',
      source_po_sha256: 'po',
      source_po_sha256s: ['po'],
      source_schedule_sha256: 'schedule',
      input_template: 'HUAKANG_A_360_PO_RELEASE_V1',
      target_template: 'HUAKANG_A_360_NEW_ORDER_V1',
      output_file_name: '华康A 360排期_360新单.xlsx',
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
    expect(customerButtons).toHaveLength(1)
    expect(customerButtons[0]!.text()).toContain('360')
    expect(wrapper.text()).not.toContain('BuzzBee')

    await wrapper.get('[data-testid="customer-choice-360"]').trigger('click')
    const inputs = wrapper.findAll('input[type="file"]')
    expect(inputs[0]!.attributes('accept')).toBe('.pdf,.xls,.xlsx,.xlsm')
    expect(inputs[1]!.attributes('accept')).toBe('.xlsx,.xlsm')
    const po = new File(['po'], 'RL-100-1.xls')
    const schedule = new File(['schedule'], '华康A 360排期.xlsx')
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

  it('registers INDEX, JAZAWARES, MAXX, STROTTMAN and JP under Huakang C', () => {
    expect(workspaceSource).toContain("'huakang-c': [")
    for (const template of [
      'HUAKANG_C_INDEX_NEW_ORDER_V1',
      'HUAKANG_C_JAZWARES_NEW_ORDER_V1',
      'HUAKANG_C_MAXX_NEW_ORDER_V1',
      'HUAKANG_C_STROTTMAN_NEW_ORDER_V1',
      'HUAKANG_C_JP_NEW_ORDER_V1',
    ]) {
      expect(workspaceSource).toContain(template)
    }
    expect(workspaceSource).toContain('旧系统无真实样例验收，结果必须逐字段复核')
  })

  it('shows only the five Huakang C customers and routes INDEX with Huakang C scope', async () => {
    customerOrderApiMock.previewMappedBatch.mockResolvedValueOnce({
      preview_schema_version: 'customer-order-huakang-c-mapped-preview-v1',
      customer_code: 'index',
      factory_id: 'huakang-c',
      po_file_name: 'INDEX PO.pdf',
      po_file_names: ['INDEX PO.pdf'],
      po_file_count: 1,
      schedule_file_name: 'INDEX排期.xls',
      source_po_sha256: 'po',
      source_po_sha256s: ['po'],
      source_schedule_sha256: 'schedule',
      input_template: 'HUAKANG_C_INDEX_PO_V1',
      target_template: 'HUAKANG_C_INDEX_NEW_ORDER_V1',
      output_file_name: 'INDEX排期_INDEX新单.xlsx',
      summary: { total: 0, valid: 0, warning: 0, blocked: 0 },
      rows: [],
      warnings: [],
    })
    const wrapper = mount(CustomerOrderCenterWorkspace, {
      props: {
        activeSection: 'import',
        factoryId: 'huakang-c',
        factoryName: '华康C厂',
      },
    })

    const customerButtons = wrapper.findAll('[data-testid^="customer-choice-"]')
    expect(customerButtons).toHaveLength(5)
    expect(customerButtons.map((button) => button.text())).toEqual(
      expect.arrayContaining([
        expect.stringContaining('INDEX'),
        expect.stringContaining('JAZAWARES'),
        expect.stringContaining('MAXX'),
        expect.stringContaining('STROTTMAN'),
        expect.stringContaining('JP'),
      ]),
    )
    expect(wrapper.text()).not.toContain('BuzzBee')

    await wrapper.get('[data-testid="customer-choice-index"]').trigger('click')
    const inputs = wrapper.findAll('input[type="file"]')
    expect(inputs[0]!.attributes('accept')).toBe('.pdf,.xls,.xlsx,.xlsm')
    expect(inputs[1]!.attributes('accept')).toBe('.xls,.xlsx,.xlsm')
    const po = new File(['po'], 'INDEX PO.pdf')
    const schedule = new File(['schedule'], 'INDEX排期.xls')
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
      'huakang-c',
    )
  })

  it('shows only the five Huadeng customers and routes Spin Master through mapped APIs', async () => {
    customerOrderApiMock.previewMappedBatch.mockResolvedValueOnce({
      preview_schema_version: 'customer-order-huadeng-mapped-preview-v1',
      customer_code: 'spin-master',
      factory_id: 'huadeng',
      po_file_name: 'Spin Master PO.xls',
      po_file_names: ['Spin Master PO.xls'],
      po_file_count: 1,
      schedule_file_name: 'Spin Master排期.xls',
      source_po_sha256: 'po',
      source_po_sha256s: ['po'],
      source_schedule_sha256: 'schedule',
      input_template: 'HUADENG_SPIN_MASTER_PO_V1',
      target_template: 'HUADENG_SPIN_MASTER_NEW_ORDER_V1',
      output_file_name: 'Spin Master新单.xlsx',
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
    expect(wrapper.text()).toContain('Spin Master')
    expect(wrapper.text()).not.toContain('BuzzBee')

    await wrapper.get('[data-testid="customer-choice-spin-master"]').trigger('click')
    const inputs = wrapper.findAll('input[type="file"]')
    expect(inputs[0]!.attributes('accept')).toBe('.pdf,.xls,.xlsx,.xlsm')
    expect(inputs[1]!.attributes('accept')).toBe('.xls,.xlsx')
    const po = new File(['po'], 'Spin Master PO.xls')
    const schedule = new File(['schedule'], 'Spin Master排期.xls')
    Object.defineProperty(inputs[0]!.element, 'files', { configurable: true, value: [po] })
    Object.defineProperty(inputs[1]!.element, 'files', { configurable: true, value: [schedule] })
    await inputs[0]!.trigger('change')
    await inputs[1]!.trigger('change')
    const parseButton = wrapper.findAll('button').find((button) => button.text().includes('解析并进入预览'))
    await parseButton!.trigger('click')
    await flushPromises()

    expect(customerOrderApiMock.previewMappedBatch).toHaveBeenLastCalledWith(
      'spin-master',
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
    expect(wrapper.text()).toContain('厂区总排期数据看板')

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
    expect(workspaceSource).toContain('WMC读取首页双语PO区且P/O#必填')
    expect(workspaceSource).toContain('普通合同扫描标签和唛头区，P/O#允许为空')
    expect(workspaceSource).toContain('ITEM新增订单行，存在同货号备料单时按本合同数量扣减H列')
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
    const scheduleView = wrapper.get('[data-testid="order-schedule"]')
    expect(scheduleView.text()).toContain('华兴厂总排期')
    expect(scheduleView.text()).toContain('不输出总排期Excel')
    expect(scheduleView.text()).toContain('按月走货概览')
    expect(scheduleView.text()).toContain('客户月度PO汇总')
    expect(scheduleView.text()).toContain('客户PO交付排期')
    expect(scheduleView.text()).toContain('临期 / 逾期')
    expect(scheduleView.text()).toContain('生产未完成')
    expect(scheduleView.text()).toContain('供生产部门调用')
    expect(scheduleView.text()).toContain('可供生产调用')
    expect(scheduleView.text()).toContain('需求版本')
    expect(scheduleView.text()).toContain('下游权威、中心只读')
    expect(scheduleView.text()).toContain('0009382481')
    expect(scheduleView.text()).toContain('包装物料未齐（静态反馈示例）')
    expect(scheduleView.text()).not.toContain('生成更新后的总排期')
  })

  it('accepts the original xls schedule only for Caixing', async () => {
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
    expect(scheduleInput.attributes('accept')).toBe('.xls,.xlsx')
    Object.defineProperty(scheduleInput.element, 'files', {
      configurable: true,
      value: [new File(['schedule'], '2026年彩星生产排期表.xls')],
    })
    await scheduleInput.trigger('change')

    expect(wrapper.text()).toContain('2026年彩星生产排期表.xls')
  })

  it('allows a missing price blocker to be explicitly skipped while keeping it visible', async () => {
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

    expect(wrapper.text()).toContain('允许跳过')
    expect(wrapper.text()).toContain('2 份PO')
    expect(wrapper.text()).toContain('单价及金额留空，稍后由跟客补充')
    const skipCheckbox = wrapper.get('.skip-issue-option input')
    await skipCheckbox.setValue(true)
    expect(wrapper.text()).toContain('已跳过待补')
    expect(wrapper.get('.summary-strip .blocked strong').text()).toBe('0')
    const generateButton = wrapper.findAll('button').find((button) => button.text().includes('生成客户排期'))
    expect((generateButton!.element as HTMLButtonElement).disabled).toBe(false)
  })

  it('keeps unconfirmed demand visible but unavailable to production consumers', async () => {
    const wrapper = mount(CustomerOrderCenterWorkspace, {
      props: {
        activeSection: 'schedule',
        factoryId: 'huaxing',
        factoryName: '华兴厂',
      },
    })

    expect(wrapper.findAll('.customer-summary-grid > article')).toHaveLength(2)
    expect(wrapper.findAll('.downstream-chip').map((chip) => chip.text())).toEqual(['可调用', '不可调用'])
    expect(wrapper.text()).toContain('当前有效确认版本')

    const monthSelect = wrapper.findAll('.schedule-toolbar-card select')[0]
    expect(monthSelect).toBeDefined()
    await monthSelect!.setValue('2026-09')

    const scheduleRows = wrapper.findAll('.factory-schedule-table tbody tr')
    expect(scheduleRows).toHaveLength(1)
    expect(scheduleRows[0]!.text()).toContain('0009382481')
    expect(scheduleRows[0]!.text()).toContain('V1')
    expect(wrapper.findAll('.customer-summary-grid > article')).toHaveLength(1)
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
    expect(previewAlert.text()).toContain('当前批次有 1 项待确认/阻断')
    expect(previewAlert.text()).toContain('SC700130503-200.pdf')
    expect(previewAlert.text()).toContain('Iteam表第 561 行')
    expect(wrapper.text()).toContain('待确认')
    const summaryCards = wrapper.findAll('.summary-strip article')
    expect(summaryCards[2]!.text()).toContain('警告/待确认1')
    expect(summaryCards[2]!.text()).toContain('不形成阻断')
    expect(summaryCards[3]!.text()).toContain('阻断项0')
    const pendingGenerateButton = wrapper.findAll('button')
      .find((button) => button.text().includes('确认重复订单后生成'))
    expect(pendingGenerateButton?.attributes('disabled')).toBeDefined()

    const confirmation = wrapper.get('.skip-issue-option')
    expect(confirmation.text()).toContain('确认通过')
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
    expect(wrapper.text()).toContain('测试阶段：所有客户的重复订单均可在预览中人工确认后继续导出')
    expect(wrapper.text()).toContain('正单评审表 / 接单表 / ITEM表')
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
      '先列大货号总数量与总装箱数，再按 ASSORTMENT 展开小货号',
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

  it('centralizes primary delivery and production exceptions without mutating authority data', async () => {
    const wrapper = mount(CustomerOrderCenterWorkspace, {
      props: {
        activeSection: 'exceptions',
        factoryId: 'huaxing',
        factoryName: '华兴厂',
      },
    })

    const exceptionView = wrapper.get('[data-testid="order-exceptions"]')
    expect(exceptionView.text()).toContain('异常与提醒中心')
    expect(exceptionView.text()).toContain('30天/7天阈值待确认')
    expect(exceptionView.text()).toContain('交付日期待确认，订单不可供下游调用')
    expect(exceptionView.text()).toContain('生产状态：生产中，完成进度 68%')
    expect(wrapper.findAll('.exception-item')).toHaveLength(2)
    expect(wrapper.findAll('.exception-severity').map((chip) => chip.text())).toEqual(['关注', '紧急'])
    expect(exceptionView.text()).toContain('“标记已关注”不等于异常已解决')

    const prioritySelect = wrapper.findAll('.exception-toolbar select')[0]
    expect(prioritySelect).toBeDefined()
    await prioritySelect!.setValue('attention')
    expect(wrapper.findAll('.exception-item')).toHaveLength(1)
    expect(wrapper.get('.exception-item').text()).toContain('0009382481')

    const acknowledgeButton = wrapper.get('.exception-acknowledge')
    await acknowledgeButton.trigger('click')
    expect(wrapper.get('.exception-item').classes()).toContain('acknowledged')
    expect(acknowledgeButton.text()).toContain('取消关注标记')

    await wrapper.get('.exception-item .trace-button').trigger('click')
    expect(wrapper.get('[data-testid="trace-drawer"]').text()).toContain('字段级追溯')

    await wrapper.get('.exception-action').trigger('click')
    expect(wrapper.emitted('navigate')).toContainEqual(['schedule'])
  })
})
