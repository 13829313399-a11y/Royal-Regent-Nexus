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
  '导入Excel',
  '导出Excel',
  '基础资料',
  '模具明细',
  '流程状态',
  '审核轨迹',
  '提交主管审核',
  '修改驳回单并重提',
  '修改后重提',
  '保存并重提',
  '重置修改',
  '生产问题反馈',
  '暂无啤机部反馈问题',
  '啤机部通知',
  '经理审核通过后',
  '正式数据读取失败',
  '不会显示本地示例单据',
  '备注提示',
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
  'apiRecords',
  'apiState',
  "'error'",
  'loadApiData',
  'sourceRecords',
  'selectedProblems',
  'moldingSampleApi.listOrders',
  "'huaxing'",
  'createDraft',
  'createLineGridClass',
  'editingRejectedOrderId',
  'buildManualMoldingSampleCreateRequest',
  'submitManualCreate',
  'startRejectedEdit',
  'resubmitRejectedOrder',
  'moldingSampleApi.createOrder',
  'moldingSampleApi.editOrder',
  'moldingSampleApi.exportOrderExcel',
  'moldingSampleApi.importOrderExcel',
  'excelFileInput',
  'triggerExcelImport',
  'handleExcelImportFile',
  'downloadOrderExcel',
  'readWorkbookAsArrayBuffer',
  'URL.createObjectURL',
  'approvalNote',
  'runApprovalTransition',
  'moldingSampleApi.updateStatus',
  "'工程重提'",
  'canEditSelectedRejectedOrder',
  'useAuthStore',
  'authStore.currentUser',
  'authStore.hasPermission',
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
assert.match(source, /createLineGridClass = 'grid-cols-\[40px_132px_142px_132px_124px_74px_96px_82px_92px_138px_160px_72px\]'/)
assert.match(source, /:class="createLineGridClass"/)
assert.match(source, /v-model="line\.notes"/)
assert.match(source, /min-w-\[1410px\]/)
assert.doesNotMatch(source, /grid-cols-\[44px_132px_144px_132px_184px_96px_88px_96px_152px_72px\]/)
assert.doesNotMatch(source, /role="columnheader">颜色 \/ PMS<\/div>/)
assert.match(source, /role="columnheader">颜色<\/div>[\s\S]*role="columnheader">PMS<\/div>/)
assert.match(source, /v-model="line\.color"[\s\S]*v-model="line\.pms"/)
assert.match(source, /v-for="\(line, index\) in createDraft\.items"[\s\S]*role="row"/)
assert.match(source, /v-model="line\.mold_name" class="h-9 w-full min-w-0/)

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
assert.doesNotMatch(source, /moldingSampleWorkflowMock/)
assert.doesNotMatch(source, /moldingSampleFactoryRecords/)
assert.doesNotMatch(source, /getMoldingSampleRecord/)
assert.doesNotMatch(source, /apiState\.value === 'fallback'/)
assert.doesNotMatch(source, /apiState === 'fallback'/)
assert.doesNotMatch(source, /本地示例数据/)
