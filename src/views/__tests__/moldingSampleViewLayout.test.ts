import assert from 'node:assert/strict'
import { readFileSync } from 'node:fs'
import { join } from 'node:path'

const source = readFileSync(join(process.cwd(), 'src/views/MoldingSampleView.vue'), 'utf8')

for (const requiredCopy of [
  '啤办单管理',
  'Molding Sample · 试模 / 试色 / 啤办',
  '看板总览',
  '工程部 · 新建开单',
  '单据详情 · 审核',
  '啤办生产任务单',
  '新建啤办单',
  '基础资料',
  '模具明细',
  '流程状态',
  '审核轨迹',
  '提交主管审核',
  '啤机部通知',
]) {
  assert.match(source, new RegExp(requiredCopy))
}

for (const preservedStatus of [
  '待审核',
  '待经理审核',
  '待生产',
  '生产中',
  '已完成',
  '已驳回',
]) {
  assert.match(source, new RegExp(preservedStatus))
}

for (const requiredImplementation of [
  "type ViewKey = 'overview' \\| 'create' \\| 'detail'",
  'workflowSteps',
  'boardColumns',
  'selectedFactoryId',
  'productionTaskRoute',
  'moldingSampleFactoryRecords',
  'apiRecords',
  'apiState',
  'loadApiData',
  'sourceRecords',
  'moldingSampleApi.listOrders',
  'createDraft',
  'buildManualMoldingSampleCreateRequest',
  'submitManualCreate',
  'moldingSampleApi.createOrder',
  'approvalNote',
  'runApprovalTransition',
  'moldingSampleApi.updateStatus',
  'useAuthStore',
  'authStore.currentUser',
  'authStore.hasPermission',
  'getMoldingSampleRecord',
  'buildCompletionGate',
  'isExternalMoldingSampleOrder',
  '/modules/production/molding-sample-tasks',
  'appStore.setActiveFactory',
  'isProductionFactoryContextId',
]) {
  assert.match(source, new RegExp(requiredImplementation))
}

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
assert.doesNotMatch(source, /管理员调试/)
