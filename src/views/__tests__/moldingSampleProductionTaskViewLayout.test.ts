import assert from 'node:assert/strict'
import { readFileSync } from 'node:fs'
import { join } from 'node:path'

const source = readFileSync(join(process.cwd(), 'src/views/MoldingSampleProductionTaskView.vue'), 'utf8')

for (const requiredCopy of [
  '啤办生产任务单',
  '接收工程啤办单通知',
  '主管审核通过后任务进入生产队列',
  '铃铛通知独立同步',
  '正式生产任务',
  '任务通知',
  '啤机部只处理生产执行字段',
  '看板',
  '列表',
  '每页 10 条',
  '开始生产',
  '撤回开始生产',
  '保存回填',
  '打印任务单',
  '试模报告填写 / 打印',
  '试模报告历史',
  '查看 / 再次打印',
  '自动同步到工程部单据详情',
  '确认打印',
  '工程啤办明细',
  '工程部下发 · 啤机部执行',
  '工程模具明细',
  '模具信息',
  '工程时点',
  '用料与颜色',
  '数量 / 需料',
  '不含啤机回填及费用',
  '完成并回传',
  '撤回完成',
  '啤机回填明细',
  '完成通知回传',
  '标记已读',
  '标记已处理',
  '通知已读',
  '通知已处理',
  '真实任务读取失败',
  '不会显示本地示例任务',
  '生产完成通知已回传到工程啤办单',
  '问题反馈已保存并同步给工程部',
  '保存中...',
  '工程啤办单',
]) {
  assert.match(source, new RegExp(requiredCopy))
}

for (const requiredImplementation of [
  'moldingSampleApi.listOrders',
  'moldingSampleApi.listNotifications',
  'moldingSampleApi.updateItems',
  'moldingSampleApi.upsertTrialReport',
  'MoldingSampleTrialReportDialog',
  'canSaveSelectedTrialReport',
  'openTrialReportHistory',
  'trialReportReadOnly',
  'trialReportInitialItemId',
  'molding-sample-trial-report-history',
  'data-testid="molding-sample-task-print-preview"',
  'data-testid="molding-sample-task-print-area"',
  'canPrintSelectedTask',
  'openTaskPrintPreview',
  'confirmTaskPrint',
  'window.print()',
  'moldingSampleApi.updateStatus',
  "'撤回开始生产'",
  "'撤回完成'",
  'moldingSampleApi.updateNotification',
  'moldingSampleApi.createProblem',
  'moldingSampleApi.getMaterialPrices',
  'loadProtectedMaterialPrices',
  'protectedMaterialPrices',
  'protectedRmbToHkdRate',
  'canProductionPermission',
  'molding_sample:production_read',
  'molding_sample:production_start',
  'molding_sample:production_fillback',
  'molding_sample:production_complete',
  'molding_sample:notification_read',
  'Promise.resolve\\(\\[\\]\\)',
  'apiNotifications',
  "'error'",
  'selectedNotification',
  'notificationUpdating',
  'updateSelectedNotificationStatus',
  'replaceApiNotification',
  'selectedProblems',
  'problemSubmitting',
  'appendProblemForOrder',
  'production_molding_sample_task',
  "'huaxing'",
  'buildCompletionGate',
  'resolveActualMaterialCostBreakdown',
  'getActualMaterialCostSourceLabel',
  'isExternalMoldingSampleOrder',
  'selectedFactoryId',
  'engineeringOrderRoute',
  "type ProductionTaskDisplayMode = 'board' | 'list'",
  'PRODUCTION_TASK_PAGE_SIZE = 10',
  'createPaginationState',
  'queueDisplayMode',
  'filteredTaskPagination',
  'paginatedFilteredTaskEntries',
  'productionSearchKeyword',
  'productionSearchTokens',
  'searchMatchedTaskEntries',
  'tokenizeMoldingSampleSearchKeyword',
  'matchesMoldingSampleSearch',
  'setQueuePage',
  'setQueueDisplayMode',
  'aria-label="啤办生产任务队列"',
  'PRODUCTION_TASK_STATUSES',
  '待生产',
  '生产中',
  '已完成',
]) {
  assert.match(source, new RegExp(requiredImplementation))
}

assert.match(source, /<div class="flex flex-wrap items-center gap-2 text-xs text-slate-400">[\s\S]*<div class="fixed right-4 top-4 z-50 flex items-center gap-2[\s\S]*当前厂区：\{\{ activeFactory\.shortName \}\}[\s\S]*<AccountMenu \/>/)
assert.match(source, /const PRODUCTION_TASK_STATUSES = new Set<MoldingSampleStatus>\(\['待生产', '生产中', '已完成'\]\)/)
assert.match(source, /\.filter\(\(record\) => PRODUCTION_TASK_STATUSES\.has\(record\.order\.status\)\)/)
assert.doesNotMatch(source, /notificationOrderIds/)
assert.doesNotMatch(source, /<div class="sticky top-14 z-40/)
assert.match(source, /total_material_cost/)
assert.match(source, /selectedTask\.value\.order\.status === '已完成'[\s\S]*return activeItems\.value/)
assert.match(source, /实际结算快照/)
assert.match(source, /分项按当前原料价估算；合计以已存实际料费为准/)
assert.match(source, /data-testid="production-fillback-list"/)
assert.match(source, /data-testid="production-fillback-grid" class="production-fillback-grid"/)
assert.match(source, /class="production-fillback-scroll[\s\S]*role="region"[\s\S]*aria-label="啤机回填模具明细"/)
assert.match(source, /\.production-fillback-grid \{[\s\S]*repeat\(auto-fit, minmax\(min\(100%, 25rem\), 1fr\)\)/)
assert.match(source, /\.production-fillback-scroll \{[\s\S]*max-height: min\(72vh, 52rem\);[\s\S]*overflow-y: auto;/)
assert.match(source, /data-testid="production-fillback-item"/)
assert.match(source, /data-testid="production-fillback-usage-panel"[\s\S]*用量回填/)
assert.match(source, /data-testid="production-fillback-cost-grid"/)
assert.match(source, /data-testid="production-fillback-actual-cost-panel"/)
assert.match(source, /data-testid="production-actual-weight-input"[\s\S]*:aria-label="`\$\{item\.mold_id\} 实际用料`"/)
assert.match(source, /data-testid="production-fillback-actual-total"/)
assert.match(source, /selectedReportSummary\?\.has_missing_actual_weight[\s\S]*全部模具已回填实际用料/)
assert.match(source, /data-testid="production-fillback-summary"/)
assert.match(source, /data-testid="production-full-item-card"/)
assert.match(source, /selectedFullDataItemId/)
assert.match(source, /const selectedFullDataItem = computed\(\(\) =>[\s\S]*activeItems\.value\.find/)
assert.match(source, /data-testid="production-full-item-master-detail" class="production-full-item-master/)
assert.match(source, /class="production-full-item-index enterprise-panel sidebar-scrollbar min-w-0 rounded-xl/)
assert.match(source, /class="production-full-item-index-options" aria-label="选择要核对的模具"/)
assert.match(source, /:aria-pressed="selectedFullDataItem\?\.id === item\.id"/)
assert.match(source, /data-testid="production-full-item-index-button"[\s\S]*border-teal-300 bg-teal-50 text-teal-950[\s\S]*bg-teal-600 text-white/)
assert.match(source, /Number\(item\.actual_weight_kg\) > 0 \? 'text-emerald-700' : 'text-amber-700'/)
assert.match(source, /@click="selectFullDataItem\(item\.id\)"/)
assert.match(source, /function selectFullDataItem\(itemId: string\)[\s\S]*fullDataItemPane\.value\.scrollTop = 0/)
assert.match(source, /role="region"[\s\S]*tabindex="0"[\s\S]*selectedFullDataItem \? \[selectedFullDataItem\] : \[\]/)
assert.match(source, /\.production-full-item-master \{[\s\S]*grid-template-columns: 14rem minmax\(0, 1fr\);[\s\S]*height: min\(76vh, 52rem\);/)
assert.match(source, /\.production-full-item-index-options \{[\s\S]*align-content: start;[\s\S]*grid-auto-rows: max-content;/)
assert.match(source, /data-testid="production-full-item-material-section"[\s\S]*原料与颜色/)
assert.match(source, /data-testid="production-full-item-timing-section"[\s\S]*生产数量与时点/)
assert.match(source, /data-testid="production-full-item-usage-section"[\s\S]*实际用量/)
assert.match(source, /data-testid="production-full-item-cost-grid"/)
assert.match(source, /data-testid="production-task-search-input"[\s\S]*type="search"[\s\S]*aria-label="模糊搜索生产任务"/)
assert.match(source, /placeholder="搜索单号 \/ 产品 \/ 客户 \/ 模具 \/ 原料\.\.\."/)
assert.match(source, /aria-label="清除生产任务搜索"[\s\S]*productionSearchKeyword = ''/)
assert.match(source, /:aria-expanded="isSelectedTaskDataExpanded"[\s\S]*aria-controls="production-complete-order-data"/)
assert.match(source, /id="production-complete-order-data"/)
assert.match(source, /class="production-task-page app-shell/)
assert.match(source, /bg-\[radial-gradient/)
assert.match(source, /class="app-page mx-auto max-w-\[1720px\]/)
assert.match(source, /enterprise-panel relative overflow-hidden rounded-2xl/)
assert.match(source, /surface-subtle/)
assert.match(source, /interactive-surface/)
assert.match(source, /reveal-grid/)
assert.match(source, /sidebar-scrollbar/)
assert.match(source, /:aria-busy="apiState === 'checking'"/)
assert.match(source, /apiState === 'checking' \? '刷新中' : '刷新任务'/)
assert.match(source, /production-loading-bar/)
assert.match(source, /:aria-pressed="queueFilter === filter"/)
assert.match(source, /:aria-pressed="queueDisplayMode === 'board'"/)
assert.match(source, /:aria-pressed="queueDisplayMode === 'list'"/)
assert.match(source, /:aria-current="selectedTask\?\.order\.id === entry\.order\.id \? 'true' : undefined"/)
assert.match(source, /overscroll-behavior-y: auto;/)
assert.doesNotMatch(source, /overscroll-behavior(?:-y)?:\s*contain;/)
assert.match(source, /function handoffWheelAtBoundary\(event: WheelEvent\)[\s\S]*event\.preventDefault\(\)[\s\S]*window\.scrollBy/)
assert.match(source, /production-fillback-scroll[\s\S]*@wheel="handoffWheelAtBoundary"/)
assert.match(source, /production-full-item-index[\s\S]*@wheel="handoffWheelAtBoundary"/)
assert.match(source, /production-full-item-pane[\s\S]*@wheel="handoffWheelAtBoundary"/)
assert.match(source, /enterprise-panel min-w-0 overflow-clip rounded-2xl/)
assert.match(source, /\.production-full-item-master \{[\s\S]*overflow: clip;/)
assert.doesNotMatch(source, /border-2 border-teal/)
assert.match(source, /@media \(prefers-reduced-motion: reduce\)/)
assert.doesNotMatch(source, /<table class="w-full min-w-\[860px\] text-\[12px\]">/)
assert.match(source, /<\/main>\s*<section class="molding-sample-task-print-root hidden"/)
assert.match(source, /#app > :not\(\.molding-sample-task-print-root\) \{ display: none !important; \}/)
assert.match(source, /body\.molding-sample-task-printing #app > \.molding-sample-task-print-root \{ display: block !important; position: static !important;/)
assert.match(source, /body\.molding-sample-task-printing #app \{ min-height: 0 !important; height: auto !important;/)
assert.match(source, /@page \{ size: A4 landscape; margin: 5mm; \}/)
assert.match(source, /width: calc\(297mm - 10mm\) !important; max-width: none !important;/)
assert.match(source, /molding-sample-task-print-table \{ width: 100%;/)
assert.match(source, /molding-sample-task-print-index \{ width: 3%; \}/)
assert.match(source, /molding-sample-task-print-mold \{ width: 25%; \}/)
assert.match(source, /molding-sample-task-print-timing \{ width: 17%; \}/)
assert.match(source, /molding-sample-task-print-material \{ width: 27%; \}/)
assert.match(source, /molding-sample-task-print-quantity \{ width: 12%; \}/)
assert.match(source, /molding-sample-task-print-notes \{ width: 16%; \}/)
assert.doesNotMatch(source, /min-height: 196mm/)
assert.match(source, /molding-sample-task-print-page \{[\s\S]*min-height: 0; height: auto;[\s\S]*break-inside: auto;/)
assert.match(source, /molding-sample-task-print-table thead \{ display: table-header-group; \}/)
assert.match(source, /molding-sample-task-print-table tr \{ break-inside: avoid-page; page-break-inside: avoid; \}/)
assert.match(source, /taskPrintDensityClass/)
assert.match(source, /molding-sample-task-print-page\.is-compact/)
assert.match(source, /molding-sample-task-print-page\.is-dense/)
assert.doesNotMatch(source, /molding-sample-task-print-footer/)
assert.match(source, /formatMaterialComposition\(resolveMaterialComponents\(item\)\)/)
assert.match(source, /试料 · 不计结余/)
assert.doesNotMatch(source, /molding-sample-task-print-signatures/)
assert.doesNotMatch(source, /molding-sample-task-print-handoff/)
assert.doesNotMatch(source, /本任务单由工程部下发给啤机部执行/)
assert.doesNotMatch(source, /啤机确认机台/)
assert.doesNotMatch(source, /文件编号/)
assert.doesNotMatch(source, /production_machine/)
for (const removedFeeCopy of ['啤办费', 'total_injection_cost', 'total_cost']) {
  assert.equal(source.includes(removedFeeCopy), false, `${removedFeeCopy} should not be part of the production task view`)
}

for (const excludedWorkbenchCopy of [
  '主管工作台',
  '经理工作台',
  '仓库工作台',
  '汇总查账',
  '价格口径',
  'PIN',
  'moldingSampleWorkflowMock',
  'moldingSampleCostMock',
  'hasFactoryScope',
  'moldingSampleFactoryRecords',
  "apiState.value === 'fallback'",
  "apiState === 'fallback'",
  '本地示例通知',
  '暂以本地示例单据展示生产任务',
  '离线示例',
]) {
  assert.equal(source.includes(excludedWorkbenchCopy), false, `${excludedWorkbenchCopy} should not be part of the production task view`)
}
