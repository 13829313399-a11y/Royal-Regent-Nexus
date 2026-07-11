import { readFileSync } from 'node:fs'
import { join } from 'node:path'
import { describe, expect, it } from 'vitest'

const enterpriseSource = readFileSync(join(process.cwd(), 'src/data/enterpriseMock.ts'), 'utf8')
const moduleCenterSource = readFileSync(join(process.cwd(), 'src/views/ModuleCenterView.vue'), 'utf8')
const moduleDetailSource = readFileSync(join(process.cwd(), 'src/views/ModuleDetailView.vue'), 'utf8')
const routerSource = readFileSync(join(process.cwd(), 'src/router/index.ts'), 'utf8')
const moduleCardSource = readFileSync(join(process.cwd(), 'src/components/modules/ModuleCard.vue'), 'utf8')
const rawMaterialSource = readFileSync(join(process.cwd(), 'src/views/RawMaterialManagementView.vue'), 'utf8')
const rawMaterialDatabaseSource = readFileSync(join(process.cwd(), 'src/data/rawMaterialDatabase.ts'), 'utf8')
const quoteCenterPanelSource = readFileSync(join(process.cwd(), 'src/components/modules/sales/QuoteCenterPanel.vue'), 'utf8')
const customerPriceConversionViewSource = readFileSync(join(process.cwd(), 'src/views/CustomerPriceConversionView.vue'), 'utf8')
const injectionSchedulingViewSource = readFileSync(join(process.cwd(), 'src/views/InjectionSchedulingView.vue'), 'utf8')

describe('production module entry', () => {
  it('keeps the molding sample production task wired to the real task page', () => {
    expect(enterpriseSource).toMatch(/id: 'molding-sample-production-task'/)
    expect(enterpriseSource).toMatch(/title: '啤办生产任务单'/)
    expect(enterpriseSource).toMatch(/接收工程啤办单通知、啤机执行、用料费用回填、完成回传/)
    expect(enterpriseSource).toMatch(/route: '\/modules\/production\/molding-sample-tasks'/)
    expect(enterpriseSource).not.toMatch(/啤机外发协同/)
    expect(enterpriseSource).not.toMatch(/\/pi-outsource\//)

    expect(moduleCenterSource).toMatch(/module\.id === 'molding-sample-production-task'/)
    expect(moduleCenterSource).toMatch(/\/modules\/production\/molding-sample-tasks\?factory=/)
    expect(moduleCenterSource).not.toMatch(/moldingSampleWorkflowMock/)
    expect(moduleCenterSource).not.toMatch(/getMoldingSampleProductionTaskStats/)

    expect(routerSource).toMatch(/path: '\/modules\/production\/molding-sample-tasks'/)
    expect(routerSource).toMatch(/name: 'molding-sample-production-tasks'/)
    expect(routerSource).toMatch(/MoldingSampleProductionTaskView\.vue/)
  })

  it('shows business flow labels on online module cards instead of implementation flags', () => {
    for (const businessCopy of [
      '工程开单后流转到生产任务',
      '主管审核后进入任务队列',
      '工程登记',
      '主管审核',
      '生产回传',
      '审核通知',
      '用料回填',
      '工程同步',
    ]) {
      expect(moduleCenterSource).toMatch(new RegExp(businessCopy))
    }

    expect(moduleCenterSource).not.toMatch(/正式接口|显错|不兜底|不离线/)
  })

  it('wires the PMC warehouse raw material module to the dedicated management page', () => {
    expect(enterpriseSource).toMatch(/id: 'raw-material-management'/)
    expect(enterpriseSource).toMatch(/title: '原料管理模块'/)
    expect(enterpriseSource).toMatch(/原料资料、仓库领料、库存批次与库存流水统一管理/)
    expect(enterpriseSource).toMatch(/route: getDepartmentRoute\('pmc-warehouse', 'raw-material-management'\)/)
    expect(enterpriseSource).not.toMatch(/id: 'inventory-alert'/)

    expect(routerSource).toMatch(/path: '\/modules\/pmc-warehouse\/raw-material-management'/)
    expect(routerSource).toMatch(/name: 'raw-material-management'/)
    expect(routerSource).toMatch(/RawMaterialManagementView\.vue/)
    expect(routerSource).toMatch(/title: '原料管理模块'/)
    expect(routerSource).toMatch(/fullPage: true/)

    for (const requiredCopy of [
      'Warehouse & Raw Material',
      '原料资料',
      '仓库领料单',
      '库存批次',
      '库存流水',
      '新增原料',
      '新建领料单',
      '入库新批次',
      '库存流水 · 出入库记录',
      '当前厂区：',
      'paginatedMaterialRows',
      'materialPageCount',
      '全部状态',
      '原料名称 / 型号',
      '规格',
      '供应商',
      '单价(HKD/磅)',
      '安全库存(KG)',
      '当前库存(KG)',
    ]) {
      expect(rawMaterialSource).toContain(requiredCopy)
    }

    expect(rawMaterialSource).toMatch(/rawMaterialDatabaseRows/)
    expect(rawMaterialSource).toMatch(/RAW_MATERIAL_PAGE_SIZE/)
    expect(rawMaterialSource).toMatch(/function mapRawMaterialRow/)
    expect(rawMaterialSource).toMatch(/supplier: source\.origin \|\| '未填写'/)
    expect(rawMaterialSource).toMatch(/spec: source\.commodityName/)
    expect(rawMaterialSource).toMatch(/显示 \{\{ materialStartIndex \}\}-\{\{ materialEndIndex \}\} 条/)
    expect(rawMaterialSource).not.toMatch(/const rawMaterialRows: RawMaterialRow\[\]/)
    expect(rawMaterialSource).not.toMatch(/rawMaterialDatabaseColumns/)
    expect(rawMaterialSource).not.toMatch(/v-for="column in rawMaterialColumns"/)
    expect(rawMaterialSource).not.toMatch(/单价\(HK\$\/Lb\)/)
    expect(rawMaterialSource).not.toMatch(/RM-PVC-001/)

    expect(rawMaterialDatabaseSource).toMatch(/RAW_MATERIAL_PAGE_SIZE = 10/)
    expect(rawMaterialDatabaseSource).toMatch(/rowCount: 286/)
    expect(rawMaterialDatabaseSource).toMatch(/sourceFileName: '新建 XLS 工作表 \(2\)\.xls'/)
    expect(rawMaterialDatabaseSource).toMatch(/"materialCode": "91000001"/)
    expect(rawMaterialDatabaseSource).toMatch(/"materialName": "ABS 750NSW"/)
    expect(rawMaterialDatabaseSource).toMatch(/"blendMaterialName01": "HDPE 5502BN（BL）"/)

    expect(rawMaterialSource).not.toMatch(/v-for="factory in productionFactories"/)
    expect(rawMaterialSource).not.toMatch(/function selectFactory/)
    expect(rawMaterialSource).not.toMatch(/@click="selectFactory/)

    expect(moduleCardSource).toMatch(/useRouter/)
    expect(moduleCardSource).toMatch(/router\.push\(module\.route\)/)
    expect(moduleCardSource).toMatch(/:role="module\.route \? 'link' : undefined"/)
    expect(moduleCardSource).toMatch(/@click\.stop/)
  })

  it('registers the customer price conversion desk inside the sales quote center', () => {
    expect(enterpriseSource).toMatch(/id: 'quote-center'/)
    expect(enterpriseSource).toMatch(/选择客户、导入内部报价、输出报客价 Excel/)
    expect(enterpriseSource).toMatch(/待转换 2 · 待复核 1/)
    expect(enterpriseSource).toMatch(/label: '客价转换台'/)
    expect(enterpriseSource).toMatch(/route: '\/modules\/sales-business\/quote-center'/)
    expect(enterpriseSource).toMatch(/先选择本人客户，再导入内部报价 Excel 并输出报客价 Excel/)
    expect(enterpriseSource).toMatch(/role: '车间业务主管'/)
    expect(enterpriseSource).toMatch(/role: '车间业务员'/)

    expect(moduleDetailSource).not.toMatch(/报价与成本中心入口/)
    expect(moduleDetailSource).not.toMatch(/打开客价转换台/)

    expect(routerSource).toMatch(/path: '\/modules\/sales-business\/quote-center'/)
    expect(routerSource).toMatch(/name: 'quote-center'/)
    expect(routerSource).toMatch(/path: '\/modules\/sales-business\/quote-center\/customer-price-conversion'/)
    expect(routerSource).toMatch(/redirect: '\/modules\/sales-business\/quote-center'/)
    expect(routerSource).toMatch(/CustomerPriceConversionView\.vue/)
    expect(routerSource).toMatch(/title: '报价与成本中心'/)
    expect(routerSource).toMatch(/title: '报价与成本中心',\s+fullPage: true,/)

    expect(customerPriceConversionViewSource).toMatch(/QuoteCenterPanel/)
    expect(customerPriceConversionViewSource).toMatch(/返回业务部模块中心/)
    expect(customerPriceConversionViewSource).toMatch(/quoteDeskTabs/)
    expect(customerPriceConversionViewSource).toMatch(/selectDesk/)
    expect(customerPriceConversionViewSource).toMatch(/内部报价/)
    expect(customerPriceConversionViewSource).toMatch(/InternalPricingPanel/)
    expect(customerPriceConversionViewSource).toMatch(/rawValue === 'quote-pool' \? 'internal-pricing'/)
    expect(customerPriceConversionViewSource).toMatch(/核价复核/)
    expect(customerPriceConversionViewSource).toMatch(/利润分析/)

    for (const requiredCopy of [
      '导入内部报价',
      '右上角先点选客户，再把内部报价 Excel 导入到当前客户名下',
      '当前客户：',
      '导入后会锁定客户并生成下方明细对比',
      '输出报客价 Excel',
      '明细对比区',
      '下方整块区域用于承接 Sheet、报客价版本、明细价格差异和利润带对比',
      '多 Sheet / 多报客价明细对比区',
      '导出版本',
      'importOverviewMetrics',
      'createMockWorkbookSheets',
      'activeWorkbookSheets',
      'selectedSheetRows',
      'useAuthStore',
      'huaxing_molding_a_sales',
      'isWorkshopSalesSupervisorAccount',
      'isWorkshopSalesAccount',
      'workshopSalesWorkshopNames',
      'canAccessWorkshop',
      'handleInternalQuoteImport',
      'exportCustomerQuoteExcel',
    ]) {
      expect(quoteCenterPanelSource).toContain(requiredCopy)
    }
    expect(quoteCenterPanelSource).toContain('.filter((customer) => workshopSalesWorkshopNames.value.has(customer.workshop))')
    expect(quoteCenterPanelSource).toContain('return inScope && canAccessWorkshop(row.workshop)')
    expect(quoteCenterPanelSource).toContain('return canAccessWorkshop(row.workshop)')

    expect(quoteCenterPanelSource).not.toContain('{{ currentAccount }}')
    expect(quoteCenterPanelSource).not.toContain('{{ currentWorkshop }}')
  })

  it('keeps injection scheduling browseable but disables imports without write permission', () => {
    expect(routerSource).toMatch(/path: '\/modules\/production\/injection-scheduling'/)
    expect(injectionSchedulingViewSource).toContain("import { useAuthStore } from '@/stores/auth'")
    expect(injectionSchedulingViewSource).toContain('const authStore = useAuthStore()')
    expect(injectionSchedulingViewSource).toContain("authStore.hasPermission('injection_schedule:import')")
    expect(injectionSchedulingViewSource).toContain('authStore.hasFactoryScope(selectedFactoryId.value)')
    expect(injectionSchedulingViewSource).toContain('canImportDailySchedule')
    expect(injectionSchedulingViewSource).toContain('当前账号没有导入排产权限，仅可浏览排产数据')
    expect(injectionSchedulingViewSource).toContain(':disabled="!canImportDailySchedule"')
    expect(injectionSchedulingViewSource).toContain(':aria-disabled="!canImportDailySchedule"')
    expect(injectionSchedulingViewSource).toContain(':disabled="isImportingDailySchedule || !canImportDailySchedule"')
  })
})
