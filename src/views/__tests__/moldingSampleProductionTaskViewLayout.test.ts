import assert from 'node:assert/strict'
import { readFileSync } from 'node:fs'
import { join } from 'node:path'

const source = readFileSync(join(process.cwd(), 'src/views/MoldingSampleProductionTaskView.vue'), 'utf8')

for (const requiredCopy of [
  '啤办生产任务单',
  '接收工程啤办单通知',
  '工程新建后先进入通知区',
  '任务通知队列',
  '独立通知表',
  '啤机部只处理生产执行字段',
  '开始生产',
  '保存回填',
  '完成并回传',
  '啤机回填明细',
  '完成通知回传',
  '生产完成通知已回传到工程啤办单',
  '工程啤办单',
]) {
  assert.match(source, new RegExp(requiredCopy))
}

for (const requiredImplementation of [
  'moldingSampleApi.listOrders',
  'moldingSampleApi.listNotifications',
  'moldingSampleApi.updateItems',
  'moldingSampleApi.updateStatus',
  'apiNotifications',
  'notificationOrderIds',
  'production_molding_sample_task',
  'buildCompletionGate',
  'isExternalMoldingSampleOrder',
  'selectedFactoryId',
  'engineeringOrderRoute',
  '待审核',
  '待经理审核',
  '待生产',
  '生产中',
  '已完成',
]) {
  assert.match(source, new RegExp(requiredImplementation))
}

for (const excludedWorkbenchCopy of [
  '主管工作台',
  '经理工作台',
  '仓库工作台',
  '汇总查账',
  '价格口径',
  'PIN',
]) {
  assert.equal(source.includes(excludedWorkbenchCopy), false, `${excludedWorkbenchCopy} should not be part of the production task view`)
}
