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
  '经理审核通过后',
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
  "'huaxing'",
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

assert.equal(source.includes('文件编号'), false, 'new-order form should not show the unused file-number field')
assert.equal(source.includes('v-model="createDraft.doc_number"'), false, 'new-order form should not bind an unused file-number input')
assert.match(source, /填写部/)
assert.match(source, /<select v-model="createDraft\.workshop"[\s\S]*<option>工程部<\/option>/)
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
assert.match(source, /grid-cols-\[44px_132px_144px_132px_184px_96px_88px_96px_152px_72px\]/)
assert.match(source, /v-for="\(line, index\) in createDraft\.items"[\s\S]*role="row"/)
assert.match(source, /v-model="line\.mold_name" class="h-9 w-full/)

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
