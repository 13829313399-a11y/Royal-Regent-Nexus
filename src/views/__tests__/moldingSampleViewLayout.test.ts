import assert from 'node:assert/strict'
import { readFileSync } from 'node:fs'
import { join } from 'node:path'

const source = readFileSync(join(process.cwd(), 'src/views/MoldingSampleView.vue'), 'utf8')
const searchSource = readFileSync(join(process.cwd(), 'src/lib/moldingSampleSearch.ts'), 'utf8')

for (const requiredCopy of [
  '啤办单管理',
  'Molding Sample · 试模 / 试色 / 啤办',
  '看板总览',
  '工程部 · 新建开单',
  '单据详情 · 审核',
  '物料结余',
  '日结余',
  '周结余',
  '月结余',
  '周期结余',
  '预计用料',
  '实际用料',
  '结余金额',
  '啤办生产任务单',
  '新建啤办单',
  '打印',
  '全选当前筛选单据',
  '清空选择',
  '啤办单打印内容',
  '打印预览',
  '确认打印',
  '关闭预览',
  '啤办业务导出打印操作区',
  '导出 / 打印',
  '默认当前单据',
  '选择单据后可打印详情或合并导出',
  '导入Excel',
  '下载导入模板',
  '导出Excel',
  '删除啤办单',
  '确认删除',
  '基础资料',
  '模具明细',
  '流程状态',
  '审核轨迹',
  '提交主管审核',
  '撤回审核',
  '修改驳回单并重提',
  '修改撤回单并重提',
  '修改后重提',
  '保存并重提',
  '重置修改',
  '生产问题反馈',
  '试模报告历史',
  '查看 / 再次打印',
  '啤机部保存后自动同步到此单据',
  '暂无啤机部反馈问题',
  '正式数据读取失败',
  '不会显示本地示例单据',
  '备注提示',
  '操作提示',
  '关闭操作提示',
  '新建成功',
  '已填写草稿会自动保留',
  '每页 10 条',
  '每页 5 条',
  '退回 / 撤回',
  '未解决异常',
  '生产数据待补',
  '配置配比',
  '用料用途',
  '正式生产',
  '试料',
  '试料金额不计结余',
  '配比合计',
  '水口料',
  '实际结算快照',
  '分项按当前原料价估算；合计以已存实际料费为准',
  '不是已启用的原料',
  '原料 \\+ 来源类型',
]) {
  assert.match(source, new RegExp(requiredCopy))
}

for (const preservedStatus of [
  '待审核',
  '待生产',
  '生产中',
  '已完成',
  '已驳回',
  '已撤回',
]) {
  assert.match(source, new RegExp(preservedStatus))
}

for (const requiredImplementation of [
  "type ViewKey = 'overview' | 'create' | 'detail' | 'material-balance'",
  "type MaterialBalancePeriodMode = 'day' | 'week' | 'month'",
  'workflowSteps',
  'normalizeBoardStatus',
  'boardColumns',
  'materialBalanceRows',
  'materialBalanceSummary',
  'materialBalancePeriodMode',
  'materialBalancePeriodRows',
  'buildMaterialBalancePeriodRows',
  'getMaterialBalancePeriodKey',
  'formatSignedWeight',
  'formatSignedMoney',
  'selectedFactoryId',
  'tokenizeMoldingSampleSearchKeyword',
  'matchesMoldingSampleSearch',
  'productionTaskRoute',
  'apiRecords',
  'apiState',
  'actionToastVisible',
  'actionToastTone',
  'actionToastFrameClass',
  'actionToastIconClass',
  'showActionToast',
  'hideActionToast',
  'overviewDisplayMode',
  "'error'",
  'loadApiData',
  'moldingSampleApi.listOrders(requestedFactoryId)',
  '暂无正式啤办单',
  'watch(selectedFactoryId',
  'sourceRecords',
  'selectedProblems',
  'selectedTrialReports',
  'MoldingSampleTrialReportDialog',
  'openEngineeringTrialReportHistory',
  'engineeringTrialReportHistoryVisible',
  'MOLDING_SAMPLE_PAGE_SIZE = 10',
  'MOLDING_SAMPLE_BOARD_PAGE_SIZE = 5',
  'MOLDING_SAMPLE_SEARCH_DEBOUNCE_MS = 275',
  'createPaginationState',
  'createServerPaginationState',
  'boardPageByStatus',
  'boardSummary',
  'boardPagesByStatus',
  'boardLoadingByStatus',
  'serverBoardEnabled',
  'supportsServerBoardApi',
  'loadServerBoardOverview',
  'loadServerBoardColumn',
  'loadDeepLinkedOrderIfNeeded',
  'loadLegacyApiData',
  'refreshBoardAfterMutation',
  'paginatedVisibleRecords',
  'paginatedMaterialBalanceRows',
  'paginatedMaterialBalancePeriodRows',
  'setBoardColumnPage',
  'setOverviewListPage',
  'setMaterialBalanceDetailPage',
  'setMaterialBalancePeriodPage',
  'countMoldingSampleAttentionMetrics',
  'data-testid="molding-kpi-grid"',
  'lg:grid-cols-4',
  'xl:grid-cols-[minmax(0,4fr)_minmax(0,3fr)]',
  'moldingSampleApi.listOrders',
  "'huaxing'",
  'createDraft',
  'createLineGridClass',
  'createSuccessToast',
  'showCreateSuccessToast',
  'createDraftStorageKey',
  'persistCreateDraft',
  'restoreSavedCreateDraft',
  'clearSavedCreateDraft',
  'editingRejectedOrderId',
  'buildManualMoldingSampleCreateRequest',
  'submitManualCreate',
  'startRejectedEdit',
  'resubmitRejectedOrder',
  'moldingSampleApi.createOrder',
  'moldingSampleApi.editOrder',
  'moldingSampleApi.exportOrdersExcel',
  'moldingSampleApi.downloadEngineeringImportTemplate',
  'moldingSampleApi.previewOrderExcel',
  'excelFileInput',
  'triggerExcelImport',
  'downloadEngineeringImportTemplate',
  'handleExcelImportFile',
  'downloadOrderExcel',
  'printOverview',
  'if (!canExportSelectedOrder.value)',
  'confirmPrintOverview',
  'closePrintPreview',
  'printPreviewVisible',
  'selectedBatchOrderIds',
  'selectedBatchRecords',
  'batchActionRecords',
  'selectAllVisibleOrders',
  'clearBatchSelection',
  'toggleOrderBatchSelection',
  'readWorkbookAsArrayBuffer',
  'createDraftFromExcelPreview',
  'URL.createObjectURL',
  'approvalNote',
  'runApprovalTransition',
  'withdrawSelectedOrder',
  'moldingSampleApi.updateStatus',
  "'工程撤回'",
  "'工程重提'",
  'canEditSelectedRejectedOrder',
  'canWithdrawSelectedOrder',
  'canDeleteSelectedOrder',
  'canDeleteDraftOrder',
  'canDeleteSelectedWithdrawnOrder',
  'deleteSelectedOrder',
  'moldingSampleApi.deleteOrder',
  'useAuthStore',
  'authStore.currentUser',
  'authStore.can',
  'buildCompletionGate',
  'isExternalMoldingSampleOrder',
  '/modules/production/molding-sample-tasks',
  'appStore.setActiveFactory',
  'isProductionFactoryContextId',
  'rawMaterialApi',
  'rawMaterialPriceList',
  'rawMaterialMasterList',
  'loadProtectedMaterialPrices',
  'loadRawMaterialOptions',
  'rawMaterialApi.list(requestedFactoryId)',
  'moldingSampleApi.getMaterialPrices(requestedFactoryId)',
  'RawMaterialSelectOption',
  'rawMaterialOptions',
  'rawMaterialOptionByValue',
  'rawMaterialOptionValueSet',
  'RawMaterialPickerPosition',
  'RAW_MATERIAL_PICKER_WIDTH',
  'RAW_MATERIAL_PICKER_HEIGHT',
  'RAW_MATERIAL_PICKER_GAP',
  'RAW_MATERIAL_PICKER_VIEWPORT_PADDING',
  'RAW_MATERIAL_PICKER_VISIBLE_LIMIT',
  'activeRawMaterialPickerLineIndex',
  'rawMaterialSearchByLine',
  'rawMaterialPickerPositionByLine',
  'hasUnknownRawMaterialValue',
  'getRawMaterialPickerText',
  'updateRawMaterialPickerPosition',
  'getRawMaterialPickerStyle',
  'getVisibleRawMaterialOptions',
  'updateRawMaterialSearch',
  'selectRawMaterialOption',
  'selectFirstRawMaterialOption',
  'clearRawMaterialSelection',
  'handleRawMaterialPickerFocusOut',
  'materialCompositionDraftRows',
  'openMaterialCompositionEditor',
  'saveMaterialComposition',
  'calculateMaterialCostBreakdown',
  'getExpectedMaterialCostBreakdown',
  'getMaterialCompositionLabel',
  'getActualMaterialCostBreakdown',
  'material_usage_type',
  'resolveActualMaterialCostBreakdown',
  'findEnabledRawMaterialOption',
  'duplicateComponentIndex',
]) {
  assert.ok(source.includes(requiredImplementation), `Missing implementation: ${requiredImplementation}`)
}

assert.match(source, /type OverviewDisplayMode = 'board' \| 'list'/)
assert.match(source, /type ActionToastTone = 'success' \| 'error' \| 'info'/)
assert.match(source, /class="fixed left-1\/2 top-24 z-50/)
assert.match(source, /<Transition[\s\S]*appear[\s\S]*mode="out-in"[\s\S]*enter-from-class="-translate-y-4 scale-95 opacity-0"/)
assert.match(source, /leave-to-class="-translate-y-3 scale-95 opacity-0"[\s\S]*:key="actionMessage"/)
assert.match(source, /class="fixed left-1\/2 top-24 z-50[\s\S]*origin-top transform-gpu/)
assert.doesNotMatch(source, /<span>\{\{ actionMessage \}\}<\/span>/)
assert.match(source, /overviewDisplayMode = ref<OverviewDisplayMode>\('board'\)/)
assert.match(source, /@click="setOverviewDisplayMode\('board'\)"/)
assert.match(source, /@click="setOverviewDisplayMode\('list'\)"/)
assert.match(source, /:aria-pressed="overviewDisplayMode === 'board'"/)
assert.match(source, /:aria-pressed="overviewDisplayMode === 'list'"/)
assert.match(source, /v-if="overviewDisplayMode === 'board'"/)
assert.match(source, /v-else[\s\S]*aria-label="啤办单列表"/)
assert.match(source, /class="app-shell min-h-screen bg-transparent/)
assert.match(source, /class="enterprise-panel[^\"]*"[\s\S]*data-testid="molding-sample-export-print-toolbar"[\s\S]*Molding Sample Operations/)
assert.match(source, /data-testid="molding-kpi-grid"[\s\S]*啤办流程概览[\s\S]*啤办风险提醒/)
assert.match(source, /enterprise-panel group relative min-h-\[104px\]/)
assert.doesNotMatch(source, /enterprise-panel interactive-surface group relative min-h-\[104px\]/)
assert.match(source, /surface-subtle flex items-center gap-1 rounded-lg/)
assert.match(source, /reveal-grid grid grid-cols-1 gap-3 overflow-x-auto overscroll-x-contain/)
assert.match(source, /selectedOrder\.id === record\.order\.id \? 'border-teal-300 bg-teal-50\/70/)
assert.match(source, /<span class="inline-flex min-h-8 items-center gap-1 rounded-lg border border-slate-200 bg-slate-50\/80 px-2\.5 text-\[12px\] font-medium text-slate-600">[\s\S]*车间：/)
assert.doesNotMatch(source, /<button[^>]*>[\s\S]{0,180}车间：/)
assert.match(source, /role="progressbar"[\s\S]*正在刷新啤办业务数据/)
assert.match(source, /<RefreshCw[\s\S]*animate-spin motion-reduce:animate-none/)
assert.match(source, /:disabled="apiState === 'checking'"[\s\S]*:aria-busy="apiState === 'checking'"/)
assert.match(source, /v-for="record in column\.pagedRecords"[\s\S]*openRecord\(record\)/)
assert.match(source, /:aria-busy="column\.loading"/)
assert.match(source, /column\.pagination\.total/)
assert.match(source, /requestBoardPage\(requestedFactoryId, status, requestedQuery, 1\)/)
assert.match(source, /pageSize: MOLDING_SAMPLE_BOARD_PAGE_SIZE/)
assert.match(source, /v-for="record in paginatedVisibleRecords"[\s\S]*openRecord\(record\)/)
assert.match(source, /@click="setView\('material-balance'\)"/)
assert.match(source, /activeView === 'material-balance'/)
assert.match(source, /aria-label="物料结余明细"/)
assert.match(source, /v-for="row in paginatedMaterialBalanceRows"/)
assert.match(source, /v-for="option in materialBalancePeriodOptions"/)
assert.match(source, /@click="materialBalancePeriodMode = option\.key"/)
assert.match(source, /aria-label="物料周期结余"/)
assert.match(source, /v-for="row in paginatedMaterialBalancePeriodRows"/)
assert.match(source, /materialBalancePeriodMode === 'day'[\s\S]*materialBalancePeriodMode === 'week'[\s\S]*materialBalancePeriodMode === 'month'/)
assert.match(source, /required_material_kg[\s\S]*actual_weight_kg[\s\S]*balanceWeightKg/)
assert.match(source, /balanceAmountHkd/)

assert.equal(source.includes('v-model="createDraft.doc_number"'), false, 'new-order form should not bind an unused file-number input')
assert.equal(source.includes('v-model="createDraft.id"'), false, 'new-order form should not expose the generated order identifier as an editable field')
assert.match(source, /完整单据数据/)
assert.match(source, /data-testid="molding-sample-print-preview"/)
assert.match(source, /@click="confirmPrintOverview"/)
assert.match(source, /window\.print\(\)/)
assert.doesNotMatch(source, /文件编号/)
assert.doesNotMatch(source, /啤机确认机台/)
assert.doesNotMatch(source, /啤办费\(RMB\)|啤办费\(HKD\)|回填实际用料和啤办费/)
assert.match(source, /data-testid="molding-sample-detail-table"/)
assert.match(source, /data-testid="molding-sample-detail-table" class="w-full min-w-\[920px\] table-fixed text-\[12px\]"/)
assert.doesNotMatch(source, /data-testid="molding-sample-detail-table" class="w-full min-w-\[1300px\]/)
assert.match(source, /data-testid="molding-sample-detail-table"[\s\S]*模具资料[\s\S]*原料 \/ 颜色[\s\S]*预计用料 \/ 料费[\s\S]*实际用料 \/ 料费[\s\S]*状态/)
assert.match(source, /data-testid="molding-sample-detail-row"/)
assert.match(source, /data-testid="molding-sample-detail-scroll-region"[\s\S]*role="region"[\s\S]*tabindex="0"/)
assert.match(source, /function handoffWheelAtBoundary\(event: WheelEvent\)[\s\S]*event\.preventDefault\(\)[\s\S]*window\.scrollBy/)
assert.match(source, /data-testid="molding-sample-detail-scroll-region"[\s\S]*@wheel="handoffWheelAtBoundary"/)
assert.match(source, /grid min-w-0 gap-4 xl:grid-cols-\[minmax\(0,1fr\)_340px\][\s\S]*<div class="min-w-0 space-y-4">[\s\S]*<section class="min-w-0 rounded-lg/)
assert.match(source, /data-testid="molding-sample-detail-scroll-region"[\s\S]*md:max-h-\[min\(62vh,640px\)\][\s\S]*md:overflow-auto/)
assert.equal(
  source.replaceAll('overscroll-x-contain', '').includes('overscroll-contain'),
  false,
  'vertical scroll regions must hand wheel scrolling back to the page at their boundaries',
)
assert.doesNotMatch(source, /overscroll-y-(?:contain|none)/)
assert.match(source, /data-testid="molding-sample-detail-scroll-region"[\s\S]*sidebar-scrollbar/)
assert.match(source, /data-testid="molding-full-item-card"[\s\S]*overflow-clip/)
assert.match(source, /data-testid="molding-full-item-index"[\s\S]*overscroll-x-contain/)
assert.match(source, /data-testid="molding-full-item-index"[\s\S]*@wheel="handoffWheelAtBoundary"/)
assert.match(source, /data-testid="molding-full-item-detail-pane"[\s\S]*sidebar-scrollbar/)
assert.match(source, /data-testid="molding-full-item-detail-pane"[\s\S]*@wheel="handoffWheelAtBoundary"/)
assert.match(source, /<thead class="sticky top-0 z-10/)
assert.match(source, /data-testid="expected-material-cost-panel"/)
assert.match(source, /data-testid="actual-material-cost-panel"/)
assert.match(source, /aria-controls="molding-sample-full-data"[\s\S]*@click="toggleSelectedOrderData"/)
assert.match(source, /data-testid="molding-full-data-workspace"[\s\S]*lg:h-\[min\(70vh,680px\)\][\s\S]*lg:grid-cols-\[240px_minmax\(0,1fr\)\]/)
assert.match(source, /data-testid="molding-full-item-index"[\s\S]*overflow-x-auto[\s\S]*lg:auto-rows-max[\s\S]*lg:content-start[\s\S]*lg:overflow-y-auto[\s\S]*v-for="item in selectedItems"/)
assert.match(source, /data-testid="molding-full-item-selector"[\s\S]*min-w-\[210px\][\s\S]*lg:min-w-0/)
assert.match(source, /data-testid="molding-full-item-selector"[\s\S]*:aria-pressed="selectedFullItem\.id === item\.id"/)
assert.match(source, /data-testid="molding-full-item-selector"[\s\S]*border-teal-300 bg-teal-50 text-teal-950[\s\S]*bg-teal-600 text-white/)
assert.match(source, /ref="selectedFullItemDetailPane"[\s\S]*data-testid="molding-full-item-detail-pane"[\s\S]*lg:overflow-y-auto[\s\S]*role="region"[\s\S]*tabindex="0"/)
assert.match(source, /selectedFullItemDetailPane\.value\.scrollTop = 0/)
assert.match(source, /motion-reduce:transition-none/)
assert.match(source, /data-testid="molding-full-item-card"/)
assert.match(source, /data-testid="molding-full-item-metadata-section"[\s\S]*模具资料/)
assert.match(source, /data-testid="molding-full-item-material-section"[\s\S]*原料与颜色/)
assert.match(source, /data-testid="molding-full-item-usage-section"[\s\S]*用量概览/)
assert.match(source, /data-testid="molding-full-item-cost-grid"/)
assert.match(source, /data-testid="molding-full-item-expected-cost-panel"[\s\S]*预计料费\(HKD\)/)
assert.match(source, /data-testid="molding-full-item-actual-cost-panel"[\s\S]*实际料费\(HKD\)/)
assert.match(source, /data-testid="molding-sample-search-input"[\s\S]*type="search"[\s\S]*aria-label="模糊搜索啤办单"/)
assert.match(source, /placeholder="搜索单号 \/ 产品 \/ 客户 \/ 模具 \/ 原料\.\.\."/)
assert.match(source, /aria-label="清除搜索"[\s\S]*searchKeyword = ''/)
assert.match(searchSource, /normalizeMoldingSampleSearchValue/)
assert.match(searchSource, /buildMoldingSampleSearchValues/)
assert.match(searchSource, /tokens\.every\(\(token\) => searchValues\.some\(\(value\) => value\.includes\(token\)\)\)/)
assert.match(source, /return components\.length \? formatMaterialComposition\(components\) : formatBlank\(item\.material\)/)
assert.match(source, /data-testid="molding-sample-detail-table"[\s\S]*工模尺寸[\s\S]*模具在厂[\s\S]*需办日期/)
assert.doesNotMatch(source, /data-testid="molding-sample-detail-table"[\s\S]*回厂时间/)
assert.doesNotMatch(source, /data-testid="molding-sample-detail-table"[\s\S]*适配机型/)
assert.match(source, /data-testid="molding-sample-detail-table"[\s\S]*v-for="item in selectedItems"/)
assert.match(source, /展开完整数据/)
assert.match(source, /收起完整数据/)
assert.match(source, /填写部/)
assert.match(source, /<select v-model="createDraft\.workshop"[\s\S]*<option>工程部<\/option>/)
assert.match(source, /data-testid="create-client-name"[\s\S]*data-testid="create-product-no"/)
assert.doesNotMatch(source, /<select v-model="createDraft\.send_to"/)
assert.match(source, /<input v-model="createDraft\.send_to"/)
assert.doesNotMatch(source, /<select v-model="createDraft\.supervisor"/)
assert.match(source, /<input v-model="createDraft\.supervisor"/)
assert.match(source, /supervisor:\s*''/)
assert.match(source, /eng_name:\s*''/)
assert.doesNotMatch(source, /supervisor:\s*template\.order\.supervisor/)
assert.doesNotMatch(source, /eng_name:\s*template\.order\.eng_name/)
assert.doesNotMatch(source, /<table class="w-full min-w-\[900px\] text-\[12px\]">/)
assert.match(source, /aria-label="模具明细录入表"/)
assert.match(source, /role="table"/)
assert.match(source, /<div class="space-y-4 xl:contents">/)
assert.match(source, /<aside class="space-y-4 xl:col-start-2 xl:row-start-1">/)
assert.match(source, /<section class="rounded-lg border border-slate-200 bg-white shadow-sm xl:col-span-2">/)
assert.match(source, /createLineGridClass = 'grid-cols-\[40px_132px_142px_210px_120px_124px_74px_96px_82px_92px_118px_138px_150px_130px_118px_160px_72px\]'/)
assert.match(source, /:class="createLineGridClass"/)
assert.match(source, /role="columnheader">原料价格\(HKD\/磅\)<\/div>/)
assert.doesNotMatch(source, /role="columnheader">整啤毛重\(g\)<\/div>/)
assert.match(source, /role="columnheader">所需用料\(kg\)<\/div>/)
assert.match(source, /data-testid="create-line-material-price"/)
assert.match(source, /getDraftWeightedUnitPrice\(line\)/)
assert.match(source, /v-model="line\.required_material_kg"/)
assert.doesNotMatch(source, /data-testid="create-line-gross-weight"/)
assert.match(source, /data-testid="create-line-required-material"/)
assert.match(source, /v-model="line\.notes"/)
assert.match(source, /min-w-\[2180px\]/)
assert.match(source, /columnheader">工模尺寸/)
assert.doesNotMatch(source, /columnheader">适配机型/)
assert.match(source, /columnheader">模具状态（是否在厂）/)
assert.doesNotMatch(source, /columnheader">模具是否在厂/)
assert.doesNotMatch(source, /columnheader">模具回厂时间/)
assert.match(source, /columnheader">模具编号/)
assert.doesNotMatch(source, /columnheader">客模具编号/)
assert.match(source, /v-model="line\.mold_dimensions"/)
assert.doesNotMatch(source, /data-testid="create-line-machine-type"/)
assert.match(source, /v-model="line\.mold_presence_status"/)
assert.doesNotMatch(source, /v-model="line\.mold_return_time"/)
assert.match(source, /data-testid="create-line-material"[\s\S]*role="combobox"[\s\S]*aria-label="选择所需用料"/)
assert.match(source, /placeholder="搜索原料名称\/编号"/)
assert.match(source, /@focus="openRawMaterialPicker\(index, line\.material, \$event\)"/)
assert.match(source, /@input="updateRawMaterialSearch\(index, \$event\)"/)
assert.match(source, /@keydown\.enter\.prevent="selectFirstRawMaterialOption\(line, index\)"/)
assert.match(source, /<Teleport to="body">[\s\S]*role="listbox"/)
assert.match(source, /class="fixed z-\[80\][^"]*shadow-xl shadow-slate-900\/10"/)
assert.match(source, /:style="getRawMaterialPickerStyle\(index\)"/)
assert.match(source, /role="listbox"/)
assert.match(source, /v-if="hasUnknownRawMaterialValue\(line\.material\)"[\s\S]*当前值/)
assert.match(source, /v-for="option in getVisibleRawMaterialOptions\(index\)"[\s\S]*:key="option\.value"[\s\S]*@click="selectRawMaterialOption\(line, index, option\)"/)
assert.match(source, /aria-label="清除所需用料"[\s\S]*@click="clearRawMaterialSelection\(line, index\)"/)
assert.match(source, /data-testid="`create-line-material-composition-\$\{index\}`"[\s\S]*配置配比/)
assert.match(source, /data-testid="create-line-material-usage-type"[\s\S]*value="production">正式生产[\s\S]*value="trial">试料/)
assert.match(source, /aria-label="配置原料配比"[\s\S]*v-for="\(component, componentIndex\) in materialCompositionDraftRows"[\s\S]*value="virgin">原料[\s\S]*value="runner">水口料[\s\S]*合计 \{\{ materialCompositionPercentageTotal/)
assert.doesNotMatch(source, /<select[\s\S]*v-model="line\.material"/)
assert.doesNotMatch(source, /<input v-model="line\.material"/)
assert.doesNotMatch(source, /class="absolute left-0 top-10[^"]*role="listbox"/)
assert.doesNotMatch(source, /grid-cols-\[44px_132px_144px_132px_184px_96px_88px_96px_152px_72px\]/)
assert.doesNotMatch(source, /role="columnheader">颜色 \/ PMS<\/div>/)
assert.match(source, /role="columnheader">颜色<\/div>[\s\S]*role="columnheader">PMS<\/div>/)
assert.match(source, /v-model="line\.color"[\s\S]*v-model="line\.pms"/)
assert.match(source, /v-model="line\.shoot_qty"[\s\S]*v-model="line\.required_material_kg"[\s\S]*v-model="line\.required_date"[\s\S]*v-model="line\.mold_dimensions"[\s\S]*v-model="line\.mold_presence_status"[\s\S]*v-model="line\.notes"/)
assert.match(source, /v-for="\(line, index\) in createDraft\.items"[\s\S]*role="row"/)
assert.match(source, /v-model="line\.mold_name"[\s\S]*class="h-9 w-full min-w-0/)
assert.match(source, /moldingSampleApi\.previewOrderExcel\(workbook,\s*\{\s*factory_id:\s*selectedFactoryId\.value,\s*\}\)/)
assert.match(source, /setView\('create'\)/)
assert.match(source, /Excel已导入到新建开单草稿/)

for (const removedClearedLayoutCopy of [
  'MOLDING SAMPLE REDESIGN',
  'layout cleared',
  '啤办单页面排版已清空',
  '空白重构画布',
]) {
  assert.equal(source.includes(removedClearedLayoutCopy), false, `${removedClearedLayoutCopy} should be replaced by redesigned layout`)
}

assert.doesNotMatch(source, /activeView = ref<ViewKey>\('production'\)/)
assert.doesNotMatch(source, /id="view-production"/)
assert.doesNotMatch(source, /approvalPin/)
assert.doesNotMatch(source, /PIN/)
assert.doesNotMatch(source, /window\.confirm/)
assert.doesNotMatch(source, /confirmLeaveCreateDraft/)
assert.doesNotMatch(source, /beforeunload/)
assert.doesNotMatch(source, /onBeforeRouteLeave/)
assert.doesNotMatch(source, /啤机部通知/)
assert.doesNotMatch(source, /打开生产任务单/)
assert.doesNotMatch(source, /主管审核通过后会在/)
assert.doesNotMatch(source, /管理员调试/)
assert.doesNotMatch(source, /moldingSampleWorkflowMock/)
assert.doesNotMatch(source, /moldingSampleFactoryRecords/)
assert.doesNotMatch(source, /getMoldingSampleRecord/)
assert.doesNotMatch(source, /apiState\.value === 'fallback'/)
assert.doesNotMatch(source, /apiState === 'fallback'/)
assert.doesNotMatch(source, /本地示例数据/)
