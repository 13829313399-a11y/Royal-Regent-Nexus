import assert from 'node:assert/strict'
import { readFileSync } from 'node:fs'
import { join } from 'node:path'

const source = readFileSync(join(process.cwd(), 'src/views/MoldingSampleView.vue'), 'utf8')

assert.match(
  source,
  /<div class="xl:sticky xl:top-24 xl:self-start">[\s\S]*<SectionPanel title="单据队列"/,
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
  '正式列表',
  '状态筛选',
  '厂区筛选',
  '客户 / 产品编号 / 订单编号',
  '工程师',
  '日期范围',
  '异常项',
  '单据编号',
  '要求完成',
  '是否逾期',
  '缺实际用料',
  '缺啤办费',
  '缺料价',
  '库存不足',
]) {
  assert.match(source, new RegExp(queueListCopy))
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
  '件数 / 套数',
  '毛重 g',
  '预计需料 kg',
  '行状态',
]) {
  assert.match(source, new RegExp(detailTableActionCopy))
}

assert.match(source, /order_id/)
assert.doesNotMatch(source, /label: '明细行'/)
assert.doesNotMatch(source, /label: '完成卡点'/)
assert.match(source, /v-if="showAdminDebugActions"[\s\S]*v-for="tab in roleTabs"/)
assert.doesNotMatch(
  source,
  /<div class="overflow-x-auto rounded-lg border border-slate-200 bg-white p-1">[\s\S]{0,900}v-for="tab in roleTabs"/,
)

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
