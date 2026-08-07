import { flushPromises, mount } from '@vue/test-utils'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import CartonProcurementView from '../CartonProcurementView.vue'

const routerReplaceMock = vi.hoisted(() => vi.fn())
const routeState = vi.hoisted(() => ({
  query: { factory: 'huaxing' } as Record<string, string>,
}))
const appStoreMock = vi.hoisted(() => ({
  activeProductionFactory: { id: 'huaxing', name: '华兴', shortName: '华兴' },
  setActiveFactory: vi.fn(),
}))
const authStoreMock = vi.hoisted(() => ({
  can: vi.fn(() => true),
}))
const cartonApiMock = vi.hoisted(() => ({
  listCustomers: vi.fn(),
  createCustomer: vi.fn(),
  updateCustomer: vi.fn(),
  deleteCustomer: vi.fn(),
  listOrders: vi.fn(),
  listMovements: vi.fn(),
  listClosings: vi.fn(),
  listExceptions: vi.fn(),
  createOrder: vi.fn(),
  exportPurchaseOrder: vi.fn(),
  uploadReceipt: vi.fn(),
  latestReceiptImport: vi.fn(),
  uploadWeeklySchedule: vi.fn(),
  createReceipt: vi.fn(),
  confirmReceipt: vi.fn(),
  generateClosings: vi.fn(),
  updateClosingStatus: vi.fn(),
  updateException: vi.fn(),
}))

vi.mock('@/api/cartonProcurement', () => ({
  cartonProcurementApi: cartonApiMock,
}))

vi.mock('vue-router', () => ({
  RouterLink: {
    name: 'RouterLink',
    props: ['to'],
    template: '<a><slot /></a>',
  },
  useRoute: () => routeState,
  useRouter: () => ({ replace: routerReplaceMock }),
}))

vi.mock('@/stores/app', () => ({
  useAppStore: () => appStoreMock,
}))

vi.mock('@/stores/auth', () => ({
  useAuthStore: () => authStoreMock,
}))

function mountView(tab?: string) {
  routeState.query = tab
    ? { factory: 'huaxing', tab }
    : { factory: 'huaxing' }

  return mount(CartonProcurementView, {
    global: {
      stubs: {
        AccountMenu: true,
      },
    },
  })
}

function findButton(wrapper: ReturnType<typeof mountView>, label: string) {
  const button = wrapper.findAll('button').find((candidate) => candidate.text().includes(label))
  if (!button) throw new Error(`Button not found: ${label}`)
  return button
}

describe('CartonProcurementView frontend workspace', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    appStoreMock.activeProductionFactory = { id: 'huaxing', name: '华兴', shortName: '华兴' }
    authStoreMock.can.mockReturnValue(true)
    cartonApiMock.listCustomers.mockRejectedValue(new Error('offline test'))
    cartonApiMock.listOrders.mockRejectedValue(new Error('offline test'))
    cartonApiMock.listMovements.mockRejectedValue(new Error('offline test'))
    cartonApiMock.listClosings.mockRejectedValue(new Error('offline test'))
    cartonApiMock.listExceptions.mockRejectedValue(new Error('offline test'))
    cartonApiMock.latestReceiptImport.mockResolvedValue(null)
    cartonApiMock.exportPurchaseOrder.mockResolvedValue(new Blob(['xlsx']))
    Object.defineProperty(window.URL, 'createObjectURL', {
      configurable: true,
      value: vi.fn(() => 'blob:carton-purchase-order'),
    })
    Object.defineProperty(window.URL, 'revokeObjectURL', {
      configurable: true,
      value: vi.fn(),
    })
    cartonApiMock.createOrder.mockImplementation(async (payload: any) => ({
      id: 'CTO-TEST',
      factory_id: payload.factory_id,
      order_no: 'CT-260805-ABC123',
      customer_code: payload.customer_code,
      customer_name: payload.customer_name,
      supplier_id: 'CSP-huaxing-HEYUAN-DONGKANG',
      supplier_name: '河源东康纸品有限公司',
      contract_no: payload.contract_no,
      item_no: payload.item_no,
      product_name: '',
      product_order_quantity: String(payload.product_order_quantity),
      order_date: payload.order_date,
      due_date: payload.due_date,
      status: 'CONFIRMED',
      note: payload.note,
      revision: 1,
      created_by: 'user-test',
      created_by_name: '测试用户',
      updated_by: 'user-test',
      updated_by_name: '测试用户',
      created_at: '2026-08-05T10:00:00+08:00',
      updated_at: '2026-08-05T10:00:00+08:00',
      lines: payload.lines.map((line: any, index: number) => ({
        id: `CTL-${index + 1}`,
        line_no: index + 1,
        packaging_type: line.packaging_type,
        paper_quality: line.paper_quality,
        specification: line.specification,
        dimension_unit: line.dimension_unit,
        usage_quantity: String(line.usage_quantity),
        required_quantity: String(line.usage_quantity * payload.product_order_quantity),
        received_quantity: '0',
        remaining_quantity: String(line.usage_quantity * payload.product_order_quantity),
        unit: line.unit,
        unit_price: '0',
        currency: 'CNY',
        price_source: 'manual',
        note: '',
      })),
    }))
  })

  it('exposes the seven V2.1 work areas and clearly labels the offline fallback', async () => {
    const wrapper = mountView()
    await flushPromises()

    expect(wrapper.text()).toContain('纸箱采购协同看板')
    expect(wrapper.text()).toContain('纸箱订单管理')
    expect(wrapper.text()).toContain('每周防漏核对')
    expect(wrapper.text()).toContain('收料反馈平台')
    expect(wrapper.text()).toContain('库存台账与交易流水')
    expect(wrapper.text()).toContain('库存月结与对账报表')
    expect(wrapper.text()).toContain('异常中心')
    expect(wrapper.text()).toContain('只读演示 · 后端不可用')
    expect(wrapper.text()).toContain('周排期只用于防漏核对，不会自动创建正式订单')

    await findButton(wrapper, '订单管理').trigger('click')
    expect(routerReplaceMock).toHaveBeenCalledWith({
      query: {
        factory: 'huaxing',
        tab: 'orders',
      },
    })
  })

  it('groups multiple paper items under one contract and keeps paper quality separate from specification', async () => {
    const wrapper = mountView('orders')

    expect(wrapper.text()).toContain('合同内纸品明细 · 4 行')
    expect(wrapper.text()).toContain('纸品类型')
    expect(wrapper.text()).toContain('纸质')
    expect(wrapper.text()).toContain('规格')
    expect(wrapper.text()).toContain('单件用量')
    expect(wrapper.text()).toContain('需求数量（自动）')
    expect(wrapper.text()).toContain('滑板纸')
    expect(wrapper.text()).toContain('卡纸')

    await findButton(wrapper, '新建纸箱订单').trigger('click')
    expect(wrapper.get('input[aria-label="纸箱供应商"]').attributes('disabled')).toBeDefined()
    await wrapper.get('input[aria-label="合同号"]').setValue('SC-DEMO-001')
    await wrapper.get('input[aria-label="货号"]').setValue('203399999')
    await wrapper.get('input[aria-label="规格 1"]').setValue('30 × 20 × 15 cm')
    expect(wrapper.get('output[aria-label="需求数量 1"]').text()).toBe('30')
    await findButton(wrapper, '新增纸品明细').trigger('click')
    await wrapper.get('input[aria-label="纸质 2"]').setValue('A9A')
    await wrapper.get('input[aria-label="规格 2"]').setValue('29 × 19 cm')
    await wrapper.get('input[aria-label="单件用量 2"]').setValue('0.5')
    expect(wrapper.get('output[aria-label="需求数量 2"]').text()).toBe('1,800')
    await wrapper.get('form').trigger('submit')
    await flushPromises()

    expect(wrapper.text()).toContain('SC-DEMO-001')
    expect(wrapper.text()).toContain('203399999')
    expect(wrapper.text()).toContain('合同内纸品明细 · 2 行')
    expect(wrapper.text()).toContain('A9A')
    expect(cartonApiMock.createOrder).toHaveBeenCalledWith(expect.objectContaining({ status: 'CONFIRMED' }))
    expect(wrapper.text()).toContain('已下单')
    expect(wrapper.text()).toContain('含 2 条纸品明细')
    expect(wrapper.text()).toContain('已自动进入排期核对、收料和库存后续流程')

    await wrapper.get('button[aria-label="导出 CT-260805-ABC123 采购单"]').trigger('click')
    await flushPromises()
    expect(cartonApiMock.exportPurchaseOrder).toHaveBeenCalledWith('huaxing', 'CT-260805-ABC123')
    expect(wrapper.text()).toContain('CT-260805-ABC123 采购单已生成并开始下载')
  })

  it('calculates effective receipts from manual unusable quantities without posting inventory', async () => {
    const wrapper = mountView('receipts')

    expect(findButton(wrapper, '导入送货单').exists()).toBe(true)
    expect(findButton(wrapper, '查找').exists()).toBe(true)
    expect(wrapper.text()).toContain('送货单 DN26061301')
    expect(wrapper.text()).toContain('有效收料 = 实收 − 破损 − 拒收 − 其他不可用')
    await wrapper.get('input[aria-label="RC-DN26061301-01 破损"]').setValue('2')
    await findButton(wrapper, '保存待确认收料单').trigger('click')

    expect(wrapper.text()).toContain('有效收料45')
    expect(wrapper.text()).toContain('请先导入送货单并完成订单纸品匹配')
  })

  it('searches receipt details by delivery note, contract or item number', async () => {
    const wrapper = mountView('receipts')

    await wrapper.get('input[aria-label="查找送货单"]').setValue('203302028')
    await wrapper.get('form').trigger('submit')

    expect(wrapper.text()).toContain('找到 1 条送货明细')
    expect(wrapper.text()).toContain('SC700142616/Z00-203302028')
    expect(wrapper.text()).not.toContain('SC700145011/3600-203302044')
  })

  it('shows a visible OCR result when a real delivery image has no matching formal orders', async () => {
    cartonApiMock.listCustomers.mockResolvedValue([])
    cartonApiMock.listOrders.mockResolvedValue([])
    cartonApiMock.listMovements.mockResolvedValue([])
    cartonApiMock.listClosings.mockResolvedValue([])
    cartonApiMock.listExceptions.mockResolvedValue([])
    cartonApiMock.uploadReceipt.mockResolvedValue({
      id: 'CIB-REAL-IMAGE',
      factory_id: 'huaxing',
      import_type: 'DELIVERY_NOTE',
      original_filename: 'DN26061301.jpg',
      source_sha256: 'abc123',
      status: 'REQUIRES_REVIEW',
      duplicate: false,
      parse_summary: {
        engine: 'rapidocr-pp-ocrv6',
        row_count: 18,
        matched_count: 0,
        issue_count: 18,
        warnings: ['图片/PDF 仅作为 OCR 预览，数量和纸品字段必须逐行人工复核'],
        document: { delivery_note_no: 'DN26061301', delivery_date: '2013-06-26' },
        rows: [{
          source_sheet: 'OCR',
          source_row: 1,
          delivery_note_no: 'DN26061301',
          contract_no: 'SC700145011/3600',
          item_no: '203302038',
          packaging_type: '待复核',
          paper_quality: '待复核',
          delivered_quantity: 0,
          match_status: 'MISSING_ORDER',
          suggestion: '未找到可关联的正式订单明细',
        }],
      },
    })

    const wrapper = mountView('receipts')
    await flushPromises()
    const input = wrapper.get('input[aria-label="选择送货单文件"]')
    const file = new File(['delivery-note-image'], 'DN26061301.jpg', { type: 'image/jpeg' })
    Object.defineProperty(input.element, 'files', { configurable: true, value: [file] })
    await input.trigger('change')
    await flushPromises()

    expect(cartonApiMock.uploadReceipt).toHaveBeenCalledWith('huaxing', file)
    expect(wrapper.text()).toContain('送货单识别完成')
    expect(wrapper.text()).toContain('识别总行数18 行')
    expect(wrapper.text()).toContain('已匹配正式订单0 行')
    expect(wrapper.text()).toContain('需要人工处理18 行')
    expect(wrapper.text()).toContain('文件已成功导入，但没有找到可关联的正式纸箱订单')
    expect(wrapper.text()).toContain('SC700145011/3600')
    expect(wrapper.text()).toContain('前往异常中心')
    expect(wrapper.text()).not.toContain('等待导入并复核送货单')
  })

  it('separates realtime inventory operations from period-end reconciliation', () => {
    const inventoryWrapper = mountView('inventory')
    expect(inventoryWrapper.text()).toContain('实时库存作业页')
    expect(inventoryWrapper.text()).toContain('实时库存结存台账')
    expect(inventoryWrapper.text()).toContain('逐笔交易流水')
    expect(inventoryWrapper.text()).toContain('纸品类型')
    expect(inventoryWrapper.text()).toContain('纸质')

    const closingWrapper = mountView('closing')
    expect(closingWrapper.text()).toContain('期间月结与供应商对账页')
    expect(closingWrapper.text()).toContain('客户月结汇总快照')
    expect(closingWrapper.text()).toContain('不承担日常收发记录')
    expect(closingWrapper.text()).not.toContain('逐笔交易流水')
  })

  it('lets an authorized carton supervisor maintain factory customer data', async () => {
    cartonApiMock.listCustomers.mockResolvedValue([])
    cartonApiMock.listOrders.mockResolvedValue([])
    cartonApiMock.listMovements.mockResolvedValue([])
    cartonApiMock.listClosings.mockResolvedValue([])
    cartonApiMock.listExceptions.mockResolvedValue([])
    cartonApiMock.createCustomer.mockImplementation(async (payload: any) => ({
      id: 'CCU-NEW',
      ...payload,
      revision: 1,
      created_by: 'supervisor',
      created_by_name: '纸箱部主管',
      updated_by: 'supervisor',
      updated_by_name: '纸箱部主管',
      created_at: '2026-08-05T10:00:00+08:00',
      updated_at: '2026-08-05T10:00:00+08:00',
    }))

    const wrapper = mountView('orders')
    await flushPromises()
    await findButton(wrapper, '客户资料维护').trigger('click')

    expect(wrapper.text()).toContain('仅维护 华兴 客户')
    await wrapper.get('input[aria-label="客户编号"]').setValue('new-customer')
    await wrapper.get('input[aria-label="客户名称"]').setValue('新客户')
    await wrapper.get('input[aria-label="客户国家地区"]').setValue('德国')
    await wrapper.get('form').trigger('submit')
    await flushPromises()

    expect(cartonApiMock.createCustomer).toHaveBeenCalledWith(expect.objectContaining({
      factory_id: 'huaxing',
      customer_code: 'NEW-CUSTOMER',
      customer_name: '新客户',
      country_region: '德国',
      status: 'ACTIVE',
    }))
    expect(wrapper.text()).toContain('客户 新客户 已加入 华兴 客户主数据')
    expect(wrapper.text()).toContain('NEW-CUSTOMER')
  })

  it('switches to formal ledger state when the backend responds', async () => {
    cartonApiMock.listCustomers.mockResolvedValue([{
      id: 'CCU-DICKIE',
      factory_id: 'huaxing',
      customer_code: 'DICKIE',
      customer_name: 'Dickie',
      country_region: '德国',
      contact_name: '',
      contact_phone: '',
      note: '',
      status: 'ACTIVE',
      revision: 1,
      created_by: 'admin',
      created_by_name: '管理员',
      updated_by: 'admin',
      updated_by_name: '管理员',
      created_at: '2026-08-05T10:00:00+08:00',
      updated_at: '2026-08-05T10:00:00+08:00',
    }])
    cartonApiMock.listOrders.mockResolvedValue([])
    cartonApiMock.listMovements.mockResolvedValue([])
    cartonApiMock.listClosings.mockResolvedValue([])
    cartonApiMock.listExceptions.mockResolvedValue([])

    const wrapper = mountView('orders')
    await flushPromises()

    expect(wrapper.text()).toContain('正式台账 · 后端已连接')
    expect(wrapper.text()).toContain('订单、收料导入、库存流水和月结均由后端保存')
    expect(wrapper.text()).not.toContain('CT-260805-006')
  })
})
