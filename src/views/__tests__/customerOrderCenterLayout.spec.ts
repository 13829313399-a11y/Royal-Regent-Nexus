import { flushPromises, mount } from '@vue/test-utils'
import { readFileSync } from 'node:fs'
import { join } from 'node:path'
import { describe, expect, it, vi } from 'vitest'
import CustomerOrderCenterWorkspace from '@/components/modules/sales/customer-order-center/CustomerOrderCenterWorkspace.vue'

const customerOrderApiMock = vi.hoisted(() => ({
  previewBuzzbeeBatch: vi.fn(),
  exportBuzzbeeBatch: vi.fn(),
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

  it('uses a clear text link back to the sales-business module center', () => {
    expect(viewSource).toContain('aria-label="返回业务部模块中心"')
    expect(viewSource).toContain('<span>业务部模块中心</span>')
    expect(viewSource).not.toContain('<span class="order-nexus">Nexus</span>')
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
    expect(wrapper.text()).toContain('普通合同 / WMC首页内嵌')
    expect(wrapper.text()).toContain('印尼排期不参与当前映射')
    expect(workspaceSource).toContain('WMC读取首页双语PO区且P/O#必填')
    expect(workspaceSource).toContain('普通合同扫描标签和唛头区，P/O#允许为空')
    expect(workspaceSource).toContain('ITEM新增订单行，存在同货号备料单时按本合同数量扣减H列')
    expect(workspaceSource).toContain('ITEM去向')

    expect(wrapper.text()).toContain('真实文件试用')
    expect(wrapper.text()).toContain('解析并进入预览')
    expect(workspaceSource).toContain('customerOrderApi.previewBuzzbeeBatch')
    expect(workspaceSource).toContain('customerOrderApi.exportBuzzbeeBatch')
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
