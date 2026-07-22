import assert from 'node:assert/strict'
import { readFileSync } from 'node:fs'
import { join } from 'node:path'

const source = readFileSync(join(process.cwd(), 'src/views/MoldingSampleProductionTaskView.vue'), 'utf8')
const productionPrintSource = readFileSync(join(process.cwd(), 'src/components/molding/print/MoldingSampleProductionPrintDocument.vue'), 'utf8')
const printCssSource = readFileSync(join(process.cwd(), 'src/components/molding/print/moldingSamplePrint.css'), 'utf8')

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
  '来源 → 承接',
  '来源厂 → 承接生产厂',
  '派厂时间',
  '单据归属来源厂',
  '生产执行承接厂',
  '啤办跨厂生产跟踪',
  '当前厂区不会生成可操作的啤机生产队列',
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
  assert.match(`${source}\n${productionPrintSource}`, new RegExp(requiredCopy))
}

for (const requiredImplementation of [
  'moldingSampleApi.listProductionTasks',
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
  'data-testid="production-task-print-selection-toolbar"',
  'data-testid="production-task-print-button"',
  'canPrintSelectedTask',
  'selectedTaskPrintOrderIds',
  'selectedTaskPrintRecords',
  'printableTaskRecords',
  'TaskPrintRouteSnapshot',
  'printableTaskRouteSnapshots',
  'taskPrintActionRecords',
  'selectAllPrintableTasksOnCurrentPage',
  'clearTaskPrintSelection',
  'toggleTaskPrintSelection',
  '选择打印任务',
  'openTaskPrintPreview',
  'confirmTaskPrint',
  'resolveCurrentTaskPrintRecords',
  'invalidateTaskPrintPreview',
  'productionAssignmentVersion',
  '打印预览已失效，请重新选择任务后再打印',
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
  'normalizeMoldingSampleSearchValue',
  'matchesProductionTaskSearch',
  'setQueuePage',
  'setQueueDisplayMode',
  'aria-label="啤办生产任务队列"',
  'PRODUCTION_TASK_STATUSES',
  'resolveMoldingSampleProductionFactoryId',
  'getOrderProductionFactoryId',
  'getOrderFactoryRouteLabel',
  'getOrderFactoryOwnershipLabel',
  'production_assigned_at',
  'selectedFactoryHasMoldingDepartment',
  'data-testid="molding-sample-cross-factory-tracking"',
  'data-testid="molding-sample-cross-factory-tracking-link"',
  'isProductionTaskRequestContextCurrent',
  'isProductionTaskResponseForContext',
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
assert.match(source, /function matchesProductionTaskSearch\([\s\S]*record\.order\.factory_id[\s\S]*getMoldingSampleFactoryLabel\(record\.order\.factory_id\)[\s\S]*productionFactoryId[\s\S]*getMoldingSampleFactoryLabel\(productionFactoryId\)[\s\S]*tokens\.every/)
assert.doesNotMatch(source, /系统(?:提交|更新)时间（北京时间）/)
assert.equal((source.match(/<MoldingSampleProductionPrintDocument/g) ?? []).length, 2, 'preview and print should use the same production document component')
assert.match(source, /<\/main>\s*<MoldingSampleProductionPrintDocument[\s\S]*class="hidden"/)
assert.match(productionPrintSource, /啤机部生产任务单[\s\S]*注意事项 \/ 开单事由[\s\S]*工程模具明细/)
assert.match(productionPrintSource, /模具信息[\s\S]*工程时点[\s\S]*用料与颜色[\s\S]*数量 \/ 需料[\s\S]*工程备注/)
assert.doesNotMatch(productionPrintSource, /回模|来源厂|承接生产厂|单据归属|派厂时间|填写部 \/ 发至|工程 \/ 审核主管|业务开单日期|产品编号|阶段 \/ 类型/)
assert.match(printCssSource, /body\.molding-sample-task-printing #app > :not\(\.molding-print-production-root\)/)
assert.match(printCssSource, /\.molding-print-table thead \{\s*display: table-header-group;/)
assert.match(printCssSource, /\.molding-print-table tr \{\s*break-inside: avoid;\s*page-break-inside: avoid;/)
assert.doesNotMatch(printCssSource, /height:\s*273mm|overflow:\s*hidden/)
assert.match(source, /interface TaskPrintRouteSnapshot \{[\s\S]*originFactoryId: string[\s\S]*productionFactoryId: string[\s\S]*productionAssignmentVersion: number[\s\S]*productionAssignedAt: string/)
assert.match(source, /async function confirmTaskPrint\(\) \{[\s\S]*resolveCurrentTaskPrintRecords\(\)[\s\S]*printableTaskRecords\.value = \[\.\.\.currentRecords\][\s\S]*await nextTick\(\)[\s\S]*resolveCurrentTaskPrintRecords\(\)[\s\S]*window\.print\(\)/)
assert.match(source, /watch\(taskEntries,[\s\S]*resolveCurrentTaskPrintRecords\(\)[\s\S]*invalidateTaskPrintPreview\(\)[\s\S]*\{ deep: true \}\)/)
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
assert.match(source, /<\/main>\s*<MoldingSampleProductionPrintDocument[\s\S]*class="hidden"/)
assert.match(source, /@media print \{ @page \{ size: A4 landscape; margin: 6mm; \} \}/)
assert.match(productionPrintSource, /v-for="\(record, recordIndex\) in records"/)
assert.match(productionPrintSource, /molding-sample-task-print-notice/)
assert.match(printCssSource, /\.molding-print-page \{[\s\S]*min-height: 0 !important;[\s\S]*height: auto !important;[\s\S]*overflow: visible !important;/)
assert.match(printCssSource, /\.molding-print-col-production-mold \{ width: 24%; \}/)
assert.match(printCssSource, /\.molding-print-col-production-timing \{ width: 14%; \}/)
assert.match(printCssSource, /\.molding-print-col-production-material \{ width: 27%; \}/)
assert.match(printCssSource, /\.molding-print-col-production-quantity \{ width: 14%; \}/)
assert.match(printCssSource, /\.molding-print-col-production-notes \{ width: 17%; \}/)
assert.match(source, /getTaskPrintDensityClass/)
assert.match(printCssSource, /molding-print-production-page\.is-compact/)
assert.match(printCssSource, /molding-print-production-page\.is-dense/)
assert.match(printCssSource, /\.molding-print-root \{[\s\S]*font-size: 10\.5pt;[\s\S]*line-height: 1\.4;/)
assert.match(printCssSource, /\.molding-print-table \{[\s\S]*font-size: 10\.5pt;[\s\S]*line-height: 1\.4;/)
assert.match(printCssSource, /\.molding-print-table th \{[\s\S]*font-size: 10pt;/)
assert.match(printCssSource, /\.molding-print-table td > span \{[\s\S]*font-size: 9\.5pt;/)
for (const match of printCssSource.matchAll(/font-size:\s*([0-9.]+)pt/g)) {
  assert.ok(Number(match[1]) >= 9.5, `print font size must stay readable: ${match[0]}`)
}
assert.doesNotMatch(productionPrintSource, /molding-sample-task-print-footer/)
assert.match(productionPrintSource, /formatMaterialComposition\(components\)/)
assert.match(productionPrintSource, /试料/)
assert.doesNotMatch(productionPrintSource, /molding-sample-task-print-signatures/)
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
