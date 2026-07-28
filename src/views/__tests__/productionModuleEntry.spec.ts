import { readFileSync } from 'node:fs'
import { join } from 'node:path'
import { describe, expect, it } from 'vitest'

const enterpriseSource = readFileSync(join(process.cwd(), 'src/data/enterpriseMock.ts'), 'utf8')
const moduleCenterSource = readFileSync(join(process.cwd(), 'src/views/ModuleCenterView.vue'), 'utf8')
const routerSource = readFileSync(join(process.cwd(), 'src/router/index.ts'), 'utf8')
const moduleCardSource = readFileSync(join(process.cwd(), 'src/components/modules/ModuleCard.vue'), 'utf8')
const rawMaterialSource = readFileSync(join(process.cwd(), 'src/views/RawMaterialManagementView.vue'), 'utf8')
const rawMaterialBaseline = JSON.parse(readFileSync(join(process.cwd(), 'backend/app/data/raw_material_baseline.json'), 'utf8')) as Array<Record<string, unknown>>
const quoteCenterPanelSource = readFileSync(join(process.cwd(), 'src/components/modules/sales/QuoteCenterPanel.vue'), 'utf8')
const customerPriceArtifactPanelSource = readFileSync(join(process.cwd(), 'src/components/modules/sales/CustomerPriceArtifactPanel.vue'), 'utf8')
const customerPriceConversionViewSource = readFileSync(join(process.cwd(), 'src/views/CustomerPriceConversionView.vue'), 'utf8')

describe('production module entry', () => {
  it('wires the injection scheduling hub to the front-end preview route', () => {
    const moduleBlock = enterpriseSource.match(
      /id: 'injection-scheduling'[\s\S]*?\n      },/,
    )?.[0]

    expect(moduleBlock).toBeDefined()
    expect(moduleBlock).toContain("title: '注塑排产中枢'")
    expect(moduleBlock).toContain("status: '前端预览'")
    expect(moduleBlock).toContain("stats: '华兴 Mock 快照 · 后端未接入'")
    expect(moduleBlock).toContain(
      "route: getDepartmentRoute('production', 'injection-scheduling')",
    )
    expect(moduleBlock).not.toContain('href:')
    expect(routerSource).toContain("path: '/modules/production/injection-scheduling'")
    expect(routerSource).toContain("name: 'injection-scheduling-hub'")
    expect(routerSource).toContain("InjectionSchedulingHubView.vue")
    expect(routerSource).toMatch(/path: '\/modules\/production\/injection-scheduling'[\s\S]{0,280}fullPage: true/)
    expect(routerSource).not.toContain('injection_schedule:')
  })

  it('keeps the molding sample production task wired to the real task page', () => {
    expect(enterpriseSource).toMatch(/id: 'molding-sample-production-task'/)
    expect(enterpriseSource).toMatch(/title: '啤办生产任务单'/)
    expect(enterpriseSource).toMatch(/接收工程啤办单通知、啤机执行、用料费用回填、完成回传/)
    expect(enterpriseSource).toMatch(/route: '\/modules\/production\/molding-sample-tasks'/)
    expect(enterpriseSource).not.toMatch(/啤机外发协同/)
    expect(enterpriseSource).not.toMatch(/\/pi-outsource\//)

    expect(moduleCenterSource).toMatch(/module\.id === 'molding-sample-production-task'/)
    expect(moduleCenterSource).toMatch(
      /getFactoryScopedRoute\('\/modules\/production\/molding-sample-tasks', factory\.id\)/,
    )
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
    expect(routerSource).toMatch(/path: '\/modules\/pmc-warehouse\/raw-material-management'[\s\S]{0,360}permissions: \['molding_sample:raw_material_write'\]/)
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
    expect(rawMaterialSource).toMatch(/const canManageSelectedFactory = computed/)
    expect(rawMaterialSource).toContain('当前厂区为只读，可查看原料资料，但不能新增、编辑、领料或调整库存。')
    expect(rawMaterialSource).toMatch(/:disabled="!canManageSelectedFactory"[\s\S]{0,260}@click="openMaterialModal"/)
    expect(rawMaterialSource).toMatch(/:disabled="!canManageSelectedFactory"[\s\S]{0,260}@click="openRequisitionModal"/)
    expect(rawMaterialSource).toMatch(/:disabled="!canManageSelectedFactory"[\s\S]{0,260}@click="openBatchModal"/)
    expect(rawMaterialSource).toMatch(/isSavingMaterial \|\| !canManageSelectedFactory/)

    expect(rawMaterialSource).toContain('rawMaterialApi.list(factoryId)')
    expect(rawMaterialSource).toContain('requestSequence !== rawMaterialRequestSequence')
    expect(rawMaterialSource).toContain('mapPersistedRawMaterialRow')
    expect(rawMaterialSource).toContain('公共原料资料库读取')
    expect(rawMaterialSource).toContain('rawMaterialApi.create({')
    expect(rawMaterialSource).toContain('物料编号（系统自动生成）')
    expect(rawMaterialSource).toContain('保存后自动生成')
    expect(rawMaterialSource).not.toContain('material_code: materialCode')
    expect(rawMaterialSource).not.toContain('请填写物料编号和原料名称。')
    expect(rawMaterialSource).toContain('rawMaterialApi.update(editingMaterialId.value, selectedFactoryId.value, payload)')
    expect(rawMaterialSource).toContain('openEditMaterialModal(row)')
    expect(rawMaterialSource).toContain('unitPriceHkdPerLb')
    expect(rawMaterialSource).toContain('工程部维护后会同步用于啤办成本计算。')
    expect(rawMaterialSource).toContain('已保存到')
    expect(rawMaterialSource).toContain('及单价已更新')
    expect(rawMaterialSource).not.toContain('由受保护价格接口维护')
    expect(rawMaterialSource).not.toContain('unitPriceHkdPerLb: source.unitPriceHkdPerLb')
    expect(rawMaterialSource).toMatch(/显示 \{\{ materialStartIndex \}\}-\{\{ materialEndIndex \}\} 条/)
    expect(rawMaterialSource).not.toMatch(/rawMaterialDatabase/)
    expect(rawMaterialSource).not.toMatch(/rawMaterialDatabaseColumns/)
    expect(rawMaterialSource).not.toMatch(/v-for="column in rawMaterialColumns"/)
    expect(rawMaterialSource).not.toMatch(/单价\(HK\$\/Lb\)/)
    expect(rawMaterialSource).not.toMatch(/RM-PVC-001/)

    expect(rawMaterialBaseline).toHaveLength(286)
    expect(rawMaterialBaseline[0]).toMatchObject({
      materialCode: '91000001',
      materialName: 'ABS 750NSW',
    })
    expect(rawMaterialBaseline.some((row) => row.blendMaterialName01 === 'HDPE 5502BN（BL）')).toBe(true)
    expect(rawMaterialBaseline.every((row) => !row.unitPriceHkdPerLb && !row.otherCostHkdPerLb)).toBe(true)

    expect(rawMaterialSource).not.toMatch(/v-for="factory in productionFactories"/)
    expect(rawMaterialSource).not.toMatch(/function selectFactory/)
    expect(rawMaterialSource).not.toMatch(/@click="selectFactory/)

    expect(moduleCardSource).toMatch(/useRouter/)
    expect(moduleCardSource).toMatch(/router\.push\(module\.route\)/)
    expect(moduleCardSource).toMatch(/:role="module\.route \? 'link' : undefined"/)
    expect(moduleCardSource).toMatch(/@click\.stop/)
  })

  it('registers customer conversion and the remaining sales modules', () => {
    expect(enterpriseSource).toMatch(/id: 'customer-price-conversion'/)
    expect(enterpriseSource).toMatch(/title: '客价转换台'/)
    expect(enterpriseSource).toMatch(/选择客户、导入内部报价、输出报客价 Excel/)
    expect(enterpriseSource).toMatch(/route: '\/modules\/sales-business\/customer-price-conversion'/)
    expect(enterpriseSource).not.toMatch(/id: 'internal-pricing'/)
    expect(enterpriseSource).not.toMatch(/id: 'quote-center'/)
    expect(enterpriseSource).not.toMatch(/title: '报价与成本中心'/)
    expect(enterpriseSource).not.toMatch(/id: 'order-approval'/)
    expect(enterpriseSource).not.toMatch(/title: '订单审批工作台'/)
    expect(enterpriseSource).toMatch(/id: 'indonesia-material-shipment'/)
    expect(enterpriseSource).toMatch(/title: '送印尼物料'/)
    expect(enterpriseSource).toMatch(/统筹送往印尼的物料需求、备料、装运、清关和到货跟踪/)
    expect(enterpriseSource).toMatch(/route: '\/modules\/sales-business\/indonesia-material-shipment'/)
    expect(enterpriseSource).not.toMatch(/id: 'customer-delivery'/)
    expect(enterpriseSource).not.toMatch(/title: '客户交付风险'/)
    expect(enterpriseSource).toMatch(/id: 'po-schedule-intake'/)
    expect(enterpriseSource).toMatch(/title: '客户订单中心'/)
    expect(enterpriseSource).toMatch(/导入客户PO与客户排期，沉淀统一订单数据，并按月份形成可供生产部门调用的厂区总排期/)
    expect(enterpriseSource).toMatch(/route: '\/modules\/sales-business\/po-schedule-intake'/)
    expect(enterpriseSource).toMatch(/role: '车间业务主管'/)
    expect(enterpriseSource).toMatch(/role: '车间业务员'/)

    expect(routerSource).toMatch(/path: '\/modules\/sales-business\/customer-price-conversion'/)
    expect(routerSource).toMatch(/name: 'customer-price-conversion'/)
    expect(routerSource).toMatch(/title: '客价转换台'/)
    expect(routerSource).toMatch(/path: '\/modules\/sales-business\/customer-price-conversion'[\s\S]{0,360}permissions: \['customer_price:read', 'customer_price:import_internal_quote'\]/)
    expect(routerSource).not.toMatch(/\/modules\/sales-business\/internal-pricing/)
    expect(routerSource).not.toMatch(/InternalPricingView\.vue/)
    expect(routerSource).toMatch(/path: '\/modules\/sales-business\/quote-center'/)
    expect(routerSource).toMatch(/path: '\/modules\/sales-business\/quote-center\/customer-price-conversion'/)
    expect(routerSource).toMatch(/path: '\/modules\/sales-business\/order-approval'/)
    expect(routerSource).toMatch(/path: '\/modules\/sales-business\/po-schedule-intake'/)
    expect(routerSource).toMatch(/name: 'customer-order-center'/)
    expect(routerSource).toMatch(/CustomerOrderCenterView\.vue/)
    expect(routerSource).toMatch(/CustomerPriceConversionView\.vue/)

    expect(customerPriceConversionViewSource).toMatch(/QuoteCenterPanel/)
    expect(customerPriceConversionViewSource).toMatch(/SalesModuleWorkbench/)
    expect(customerPriceConversionViewSource).toMatch(/title="客价转换台"/)
    expect(customerPriceConversionViewSource).toMatch(/\['huakang-c', 'huakang-d'\]\.includes\(appStore\.activeProductionFactory\.id\)/)
    expect(customerPriceConversionViewSource).toContain("{ label: '待转换', value: '0'")
    expect(customerPriceConversionViewSource).toContain("{ label: '客户范围', value: '待配置'")
    expect(customerPriceConversionViewSource).not.toMatch(/InternalPricingPanel/)
    expect(customerPriceConversionViewSource).not.toMatch(/quoteDeskTabs/)

    for (const requiredCopy of [
      '导入内部报价',
      '优先从上方 P4 v2 交接池直接转换',
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
      'visibleCustomers',
      'canImportSelectedCustomer',
      'canExportSelectedCustomer',
      '全部客户按相同权限操作',
      'handleInternalQuoteImport',
      'exportCustomerQuoteExcel',
    ]) {
      expect(quoteCenterPanelSource).toContain(requiredCopy)
    }
    expect(quoteCenterPanelSource).toContain('v-for="customer in visibleCustomers"')
    expect(quoteCenterPanelSource).toContain(':disabled="!canImportSelectedCustomer"')
    expect(quoteCenterPanelSource).toMatch(/authStore\.can\(\s*'customer_price:import_internal_quote'/)
    expect(quoteCenterPanelSource).toMatch(/authStore\.can\(\s*'customer_price:export_customer_quote'/)
    expect(quoteCenterPanelSource).not.toContain('v-for="customer in ownCustomers"')
    expect(quoteCenterPanelSource).not.toContain('writableCustomerIds')
    expect(quoteCenterPanelSource).not.toContain('workshopSalesWorkshopNames')

    for (const requiredArtifactCopy of [
      '内部报价交接池',
      'p4_final_approved',
      '待接收',
      '已接收',
      '已撤销',
      '接收并转换',
      'customer_price:import_internal_quote',
    ]) {
      expect(customerPriceArtifactPanelSource).toContain(requiredArtifactCopy)
    }

    expect(quoteCenterPanelSource).not.toContain('{{ currentAccount }}')
    expect(quoteCenterPanelSource).not.toContain('{{ currentWorkshop }}')
  })

})
