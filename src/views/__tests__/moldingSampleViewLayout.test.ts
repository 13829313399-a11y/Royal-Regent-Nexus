import assert from 'node:assert/strict'
import { readFileSync } from 'node:fs'
import { join } from 'node:path'

const source = readFileSync(join(process.cwd(), 'src/views/MoldingSampleView.vue'), 'utf8')

assert.match(
  source,
  /<div id="sample-order-list" class="xl:sticky xl:top-24 xl:self-start">[\s\S]*<SectionPanel title="单据列表"/,
)

assert.match(
  source,
  /<RouterLink\s+to="\/modules"\s+class="fixed left-4 top-4 z-50[^"]*"/,
)

assert.match(source, /华登集团 \/ Royal Regent/)
assert.match(source, /工程啤办单/)
assert.match(source, /MOLDING SAMPLE ORDER/)

for (const stepLabel of ['工程开单', '主管审核', '经理终审', '仓库领料', '啤机生产', '完成归档']) {
  assert.match(source, new RegExp(stepLabel))
}

for (const formalRoleCopy of [
  '我的待办',
  '待我审核',
  '待我处理',
  '待补资料',
  '当前登录身份',
  '可用入口',
]) {
  assert.match(source, new RegExp(formalRoleCopy))
}

for (const roleScopedEntry of [
  '基础资料',
  '明细资料',
  '提交 / 保存 / 处理驳回',
  '审核轨迹',
  '待审核单',
  '审核意见',
  '终审',
  '价格口径',
  '敏感操作审计',
  'PIN 管理',
]) {
  assert.match(source, new RegExp(roleScopedEntry))
}

for (const queueListCopy of [
  '单据列表',
  '打开左侧单据列表，按状态、厂区、客户或产品编号筛选',
  '列表总数',
  '待处理',
  '异常数量',
  '状态快筛',
  '高级筛选',
  '筛选摘要',
  '清空筛选',
  '状态筛选',
  '厂区筛选',
  '客户 / 产品编号 / 订单编号',
  '工程师',
  '日期范围',
  '异常项',
  '单据编号',
  '要求完成日期',
  '是否逾期',
  '明细行数',
  '缺实际用料',
  '缺啤办费',
  '缺料价',
  '库存不足',
]) {
  assert.match(source, new RegExp(queueListCopy))
}

for (const activeOrderCopy of [
  '当前单据',
  '当前查看：',
  '返回单据列表',
  '多张单据从列表切换',
]) {
  assert.match(source, new RegExp(activeOrderCopy))
}

for (const restrainedSummaryCopy of [
  '单据状态',
  '明细 / 模具数',
  '当前节点待办',
  '费用状态',
  '未到结算节点',
]) {
  assert.match(source, new RegExp(restrainedSummaryCopy))
}

for (const operationGuideCopy of [
  '操作总览',
  '当前节点指引',
  '下一步动作',
  '当前处理人',
  '风控提示',
  '可见角色',
]) {
  assert.match(source, new RegExp(operationGuideCopy))
}

for (const quickNavCopy of [
  '本单快捷导航',
  '单据列表',
  '单头信息',
  '角色工作台',
  '明细清单',
  '审核轨迹',
]) {
  assert.match(source, new RegExp(quickNavCopy))
}

for (const anchorId of [
  'sample-order-list',
  'sample-order-head',
  'sample-role-workbench',
  'sample-detail-table',
  'sample-audit-trail',
]) {
  assert.match(source, new RegExp(`id="${anchorId}"`))
  assert.match(source, new RegExp(`#${anchorId}`))
}

for (const formalFormCopy of [
  '客户名称',
  '开单日期',
  '跟进工程师',
  '必填',
  'T0',
  'EP',
  'FEP',
  'PP',
  '内部',
  '发至湖南',
  '发至模厂',
]) {
  assert.match(source, new RegExp(formalFormCopy))
}

for (const detailTableActionCopy of [
  '新增行',
  '删除行',
  '复制行',
  '上移',
  '下移',
  '批量导入',
  'Excel 导入前先预览',
  '行级校验',
  '颜色 / PMS',
  '件数 / 套数',
  '毛重 g',
  '预计需料 kg',
  '行状态',
]) {
  assert.match(source, new RegExp(detailTableActionCopy))
}

for (const manualCreateCopy of [
  '新建啤办单',
  '人工新建啤办单',
  '根目录啤办单映射',
  '文件编号',
  '落单人',
  '落单日期',
  '注意事项',
  '客模具编号',
  '所需用料',
  '所需颜色',
  'PMS',
  '啤/套',
  '啤数',
  '整啤毛重\\(g\\)',
  '所需用量\\(kg\\)',
  '需办日期',
  '新增明细',
  '创建啤办单',
  '取消新建',
]) {
  assert.match(source, new RegExp(manualCreateCopy))
}

assert.match(source, /showManualCreatePanel/)
assert.match(source, /createManualMoldingSampleOrder/)
const manualCreatePanelStart = source.indexOf('v-if="showManualCreatePanel"')
const manualCreatePanelEnd = source.indexOf('</section>', manualCreatePanelStart)
assert.notEqual(manualCreatePanelStart, -1)
assert.notEqual(manualCreatePanelEnd, -1)
const manualCreatePanelSource = source.slice(manualCreatePanelStart, manualCreatePanelEnd)
assert.doesNotMatch(manualCreatePanelSource, /min-w-\[1520px\]/)
assert.doesNotMatch(manualCreatePanelSource, /<table/)
assert.match(manualCreatePanelSource, /grid gap-3 md:grid-cols-2 xl:grid-cols-4/)
assert.match(manualCreatePanelSource, /max-w-full overflow-hidden/)
for (const manualTextFieldModel of [
  'manualCreateDraft.workshop',
  'manualCreateDraft.send_to',
  'manualCreateDraft.supervisor',
  'manualCreateDraft.eng_name',
]) {
  const escapedModel = manualTextFieldModel.replaceAll('.', '\\.')
  assert.match(manualCreatePanelSource, new RegExp(`<input[\\s\\S]{0,220}v-model="${escapedModel}"`))
  assert.doesNotMatch(manualCreatePanelSource, new RegExp(`<select[\\s\\S]{0,220}v-model="${escapedModel}"`))
}

assert.match(source, /order_id/)
assert.doesNotMatch(source, /label: '明细行'/)
assert.match(source, /max-h-\[[^\]]+\]\s+overflow-auto/)
assert.match(source, /sticky top-0/)
assert.match(source, /v-if="showAdminDebugActions"[\s\S]*v-for="tab in roleTabs"/)
assert.doesNotMatch(
  source,
  /<div class="overflow-x-auto rounded-lg border border-slate-200 bg-white p-1">[\s\S]{0,900}v-for="tab in roleTabs"/,
)
const queuePanelStart = source.indexOf('SectionPanel title="单据列表"')
const queuePanelEnd = source.indexOf('</SectionPanel>', queuePanelStart)
assert.notEqual(queuePanelStart, -1)
assert.notEqual(queuePanelEnd, -1)
const queuePanelSource = source.slice(queuePanelStart, queuePanelEnd)
assert.doesNotMatch(queuePanelSource, /<table/)

for (const removedCopy of [
  '啤办单工作台',
  '后端已连接',
  '后端空库',
  '前端 mock',
  '同步当前示例',
  '刷新后端',
  '导入新单ID',
  '规格字段统一为 injection 啤办单口径',
  '当前为前端 mock 数据',
]) {
  assert.equal(source.includes(removedCopy), false, `${removedCopy} should not be visible copy`)
}
