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
  '正式数据读取失败',
  '不会显示本地示例单据',
  '备注提示',
  '新建成功',
  '已填写草稿会自动保留',
]) {
  assert.match(source, new RegExp(requiredCopy))
}

for (const preservedStatus of [
  '待审核',
  '待生产',
  '生产中',
  '已完成',
  '已驳回',
]) {
  assert.match(source, new RegExp(preservedStatus))
}

for (const requiredImplementation of [
  "type ViewKey = 'overview' \\| 'create' \\| 'detail' \\| 'material-balance'",
  "type MaterialBalancePeriodMode = 'day' \\| 'week' \\| 'month'",
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
  'productionTaskRoute',
  'apiRecords',
  'apiState',
  'overviewDisplayMode',
  "'error'",
  'loadApiData',
  'sourceRecords',
  'selectedProblems',
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

assert.match(source, /type OverviewDisplayMode = 'board' \| 'list'/)
assert.match(source, /overviewDisplayMode = ref<OverviewDisplayMode>\('board'\)/)
assert.match(source, /@click="overviewDisplayMode = 'board'"/)
assert.match(source, /@click="overviewDisplayMode = 'list'"/)
assert.match(source, /v-if="overviewDisplayMode === 'board'"/)
assert.match(source, /v-else[\s\S]*aria-label="啤办单列表"/)
assert.match(source, /v-for="record in visibleRecords"[\s\S]*openRecord\(record\)/)
assert.match(source, /@click="setView\('material-balance'\)"/)
assert.match(source, /activeView === 'material-balance'/)
assert.match(source, /aria-label="物料结余明细"/)
assert.match(source, /v-for="row in materialBalanceRows"/)
assert.match(source, /v-for="option in materialBalancePeriodOptions"/)
assert.match(source, /@click="materialBalancePeriodMode = option\.key"/)
assert.match(source, /aria-label="物料周期结余"/)
assert.match(source, /v-for="row in materialBalancePeriodRows"/)
assert.match(source, /materialBalancePeriodMode === 'day'[\s\S]*materialBalancePeriodMode === 'week'[\s\S]*materialBalancePeriodMode === 'month'/)
assert.match(source, /required_material_kg[\s\S]*actual_weight_kg[\s\S]*balanceWeightKg/)
assert.match(source, /balanceAmountHkd/)

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
assert.match(source, /<div class="space-y-4 xl:contents">/)
assert.match(source, /<aside class="space-y-4 xl:col-start-2 xl:row-start-1">/)
assert.match(source, /<section class="rounded-lg border border-slate-200 bg-white shadow-sm xl:col-span-2">/)
assert.match(source, /createLineGridClass = 'grid-cols-\[40px_132px_142px_132px_124px_74px_96px_82px_92px_112px_118px_138px_160px_72px\]'/)
assert.match(source, /:class="createLineGridClass"/)
assert.match(source, /role="columnheader">整啤毛重\(g\)<\/div>/)
assert.match(source, /role="columnheader">所需用料\(kg\)<\/div>/)
assert.match(source, /v-model="line\.gross_weight_g"/)
assert.match(source, /v-model="line\.required_material_kg"/)
assert.match(source, /data-testid="create-line-gross-weight"/)
assert.match(source, /data-testid="create-line-required-material"/)
assert.match(source, /v-model="line\.notes"/)
assert.match(source, /min-w-\[1660px\]/)
assert.doesNotMatch(source, /grid-cols-\[44px_132px_144px_132px_184px_96px_88px_96px_152px_72px\]/)
assert.doesNotMatch(source, /role="columnheader">颜色 \/ PMS<\/div>/)
assert.match(source, /role="columnheader">颜色<\/div>[\s\S]*role="columnheader">PMS<\/div>/)
assert.match(source, /v-model="line\.color"[\s\S]*v-model="line\.pms"/)
assert.match(source, /v-model="line\.shoot_qty"[\s\S]*v-model="line\.gross_weight_g"[\s\S]*v-model="line\.required_material_kg"[\s\S]*v-model="line\.required_date"/)
assert.match(source, /v-for="\(line, index\) in createDraft\.items"[\s\S]*role="row"/)
assert.match(source, /v-model="line\.mold_name"[\s\S]*class="h-9 w-full min-w-0/)

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
