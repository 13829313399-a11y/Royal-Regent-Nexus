import assert from 'node:assert/strict'
import { readFileSync } from 'node:fs'
import { join } from 'node:path'

const source = readFileSync(join(process.cwd(), 'src/views/MoldingSampleProductionTaskView.vue'), 'utf8')

for (const requiredCopy of [
  '啤办生产任务单',
  '接收工程啤办单通知',
  '主管审核通过后进入通知区',
  '任务通知队列',
  '独立通知表',
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
  'notificationOrderIds',
  'production_molding_sample_task',
  "'huaxing'",
  'buildCompletionGate',
  'isExternalMoldingSampleOrder',
  'selectedFactoryId',
  'engineeringOrderRoute',
  "type ProductionTaskDisplayMode = 'board' | 'list'",
  'PRODUCTION_TASK_PAGE_SIZE = 10',
  'createPaginationState',
  'queueDisplayMode',
  'filteredTaskPagination',
  'paginatedFilteredTaskEntries',
  'setQueuePage',
  'setQueueDisplayMode',
  'aria-label="啤办生产任务队列"',
  '待审核',
  '待经理审核',
  '待生产',
  '生产中',
  '已完成',
]) {
  assert.match(source, new RegExp(requiredImplementation))
}

assert.match(source, /<div class="flex flex-wrap items-center gap-2 text-xs text-slate-400">[\s\S]*<div class="fixed right-4 top-4 z-50 flex items-center gap-2[\s\S]*当前厂区：\{\{ activeFactory\.shortName \}\}[\s\S]*<AccountMenu \/>/)
assert.doesNotMatch(source, /<div class="sticky top-14 z-40/)
assert.match(source, /total_material_cost/)
assert.match(source, /<\/main>\s*<section class="molding-sample-task-print-root hidden"/)
assert.match(source, /#app > main \{ display: none !important; \}/)
assert.match(source, /body\.molding-sample-task-printing #app > \.molding-sample-task-print-root \{ display: block !important; position: static !important;/)
assert.match(source, /@page \{ size: A4 landscape; margin: 7mm; \}/)
assert.match(source, /min-height: 196mm/)
assert.match(source, /molding-sample-task-print-page\.is-dense/)
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
