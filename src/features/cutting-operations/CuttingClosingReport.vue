<script setup lang="ts">
import { computed, ref } from 'vue'
import { RouterLink } from 'vue-router'
import SectionPanel from '@/components/common/SectionPanel.vue'
import { Button } from '@/components/ui/button'
import type { ClosingPreview } from './closingApi'
import { cuttingDestination } from './location'
import CuttingClosingTrace from './CuttingClosingTrace.vue'
const props=defineProps<{value:ClosingPreview;storedSnapshot?:boolean}>()
const tab=ref(0)
const tabs=computed(()=>['生产与外发数量','领退料及耗用',props.storedSnapshot?'本版本材料费用':'材料费用试算','来源及更正追溯'])
// Older immutable snapshots also contain this P4a-only notice. Do not rewrite them.
const issues=computed(()=>props.value.issues.filter(issue=>!props.storedSnapshot||issue.code!=='period_wip_unconfirmed'))
function destination(issue:ClosingPreview['issues'][number]) {
  return cuttingDestination(props.value.line_id,props.value.month,issue.workspace,
    issue.document_id?'report':issue.issue_id?'issue':issue.task_id?'task':undefined,
    issue.document_id||issue.issue_id||issue.task_id)
}
</script>
<template>
  <SectionPanel :title="storedSnapshot?'月结依据快照':'月度核对预览'" class="cutting-content-panel">
    <div class="closing-content">
      <p>{{value.start}} 至 {{value.through}}<span v-if="value.partial"> · 本月尚未结束，月末为 {{value.end}}</span> · 取数时间：{{value.generated_at}}</p>
      <p v-if="storedSnapshot" class="cutting-notice">以下为该月结版本保存时的生产、物料、价格与追溯依据，后续操作不改写此快照。月末在制与完工归属见上方月结汇总；外发加工费仍另行结算。</p>
      <p v-else class="cutting-notice">补录和更正按业务日期更新未锁月结果，以下数量采用最新有效记录。计划使用当前发布版本；本页不代表已结清、正式月末在制或外发可付款金额。</p>
      <p v-if="value.plan_stale" role="alert" class="cutting-error">已发布计划依据已变化，需重新核对。本期计划及漏报提示仅作参考，实际生产数量仍按生效记录统计。</p>
      <details><summary>本次取数依据</summary><p>订单版本 {{value.basis.order_version}} · {{storedSnapshot?'保存时计划版本':'当前计划版本'}} {{value.basis.plan_version??'未发布'}} · 耗用流水 {{value.basis.usage_revision}} · 仓库流水 {{value.basis.warehouse_revision}}</p></details>
      <div class="cutting-section-nav" aria-label="月度核对视图"><Button v-for="(label,index) in tabs" :key="label" variant="outline" :aria-pressed="tab===index" @click="tab=index">{{label}}</Button></div>
      <template v-if="tab===0">
        <p>生产和交接以套为单位，散片另列。外发自报、收回及验收分别记录，合格完成仅计验收合格。</p>
        <div class="cutting-table-scroll" role="region" aria-label="月度生产核对" tabindex="0"><table>
          <thead><tr><th>任务／执行方</th><th>期初累计完成</th><th>本期计划</th><th>本期合格完成</th><th>本期交接</th><th>期末累计完成</th><th>期末完工未交接</th><th>计划日未报</th></tr></thead>
          <tbody><tr v-for="row in value.production" :key="row.task_id"><td>{{row.task_name}} · {{row.resource_name}}</td><td>{{row.opening_completed}}</td><td>{{row.planned}}</td><td>{{row.completed}}</td><td>{{row.handed}}</td><td>{{row.closing_completed}}</td><td>{{row.completed_unhanded}}</td><td>{{row.missing_days.join('、')||'无'}}</td></tr></tbody>
        </table></div>
        <p v-if="!value.production.length" class="cutting-no-records">该订单暂无生产任务或有效实绩，不代表核对完成。</p>
        <article v-for="row in value.production" :key="row.task_id" class="cutting-master-line">
          <p v-if="row.execution==='outsourced'">{{row.task_name}}：本期外发自报 {{row.claimed}} 套，收回 {{row.returned}} 套，验收合格 {{row.accepted}} 套，不合格 {{row.rejected}} 套；期末自报未收回 {{row.pending_return}} 套，收回待验收 {{row.pending_acceptance}} 套。</p>
          <p>{{row.task_name}}：本期日报不良 {{row.daily_rejected}} 套、报废 {{row.daily_scrap}} 套。</p>
          <p v-for="part in row.loose" :key="part.code">{{part.name}}（{{part.code}}）：期末散片 {{part.quantity}} 片，本期不良 {{part.rejected}} 片、报废 {{part.scrap}} 片。</p>
        </article>
      </template>
      <template v-else-if="tab===1">
        <p>期初现场余料＋本期签收－退仓－正常耗用－损耗＝期末现场余料。仓库实发与签收分别展示，未签物料不计入现场余料；不同单位不相加。</p>
        <div class="cutting-table-scroll" role="region" aria-label="月度领退耗存核对" tabindex="0"><table>
          <thead><tr><th>原实发／任务／物料</th><th>原单位</th><th>期初余料</th><th>本期实发</th><th>本期签收</th><th>本期退仓</th><th>正常耗用</th><th>损耗</th><th>期末余料</th><th>期末已发未签</th></tr></thead>
          <tbody><tr v-for="row in value.materials" :key="row.issue_id"><td>{{row.context.item_name}} · {{row.context.task_name}}<br />{{row.issue_id}}</td><td>{{row.context.unit}}</td><td>{{row.opening_quantity}}</td><td>{{row.issued_quantity}}</td><td>{{row.received_quantity}}</td><td>{{row.returned_quantity}}</td><td>{{row.consumed_quantity}}</td><td>{{row.loss_quantity}}</td><td>{{row.ending_quantity}}</td><td>{{row.unsigned_quantity}}</td></tr></tbody>
        </table></div>
        <p v-if="!value.materials.length" class="cutting-no-records">截至核对日无有效关联实发；不能据此确认全部应领物料已齐。</p>
      </template>
      <template v-else-if="tab===2">
        <p v-if="value.costs===undefined" class="cutting-notice">材料费用需单独授予成本查询权限；当前仅显示生产及实物数量。</p>
        <template v-else>
          <p v-if="storedSnapshot" class="cutting-notice">采用本版本保存的原批次成本，正常费用与损耗分列、币种分别核对。此历史版本不随后续改价更新。</p>
          <p v-else class="cutting-notice">采用当前已确认的原批次价格试算；月度金额为原实发期末累计费用减期初累计费用，保留分位差额。补价会更新此预览，缺价不填零，各币种分别核对。</p>
          <p>待计价实发笔数：{{value.pending_pricing}}。已计价部分不代表完整材料费用。</p>
          <div class="cutting-table-scroll" role="region" aria-label="月度材料费用试算" tabindex="0"><table><thead><tr><th>币种</th><th>已计价正常费用</th><th>已计价损耗费用</th></tr></thead><tbody><tr v-for="(cost,currency) in value.costs" :key="currency"><td>{{currency}}</td><td>{{cost.normal}}</td><td>{{cost.loss}}</td></tr></tbody></table></div>
          <p v-if="!Object.keys(value.costs).length">暂无已计价费用。</p>
          <details v-for="row in value.materials" :key="row.issue_id"><summary>{{row.context.item_name}} · 原实发 {{row.issue_id}} · 计价依据</summary><p>原批次 {{row.context.root_batch_id}} · 正常费用 {{row.normal_cost??'待计价'}} · 损耗费用 {{row.loss_cost??'待计价'}}</p><p v-if="row.price">{{storedSnapshot?'本版本保存单价':'当前单价'}} {{row.price.data.entry.unit_cost}} {{row.price.data.entry.currency}}／{{row.context.unit}} · V{{row.price.version}} · {{row.price.actor}} · {{row.price.date}} · {{row.price.data.entry.price_reference}}</p></details>
          <template v-if="!storedSnapshot">
            <h3>当前归集待办（不是所选月末余额）</h3>
            <p>历史月末在制及正式结转请查看内部月结记录；当前累计归属不能替代所选月末余额。</p>
            <p v-for="(review,index) in value.current_allocation_review" :key="index">{{review.task_name}} · {{review.resource_name}}：{{review.reasons.join('；')||'当前归集已确认，仍不代表该月已结清'}}</p>
          </template>
        </template>
      </template>
      <CuttingClosingTrace v-else :value="value" />
      <h3>{{storedSnapshot?'本版本核对事项':'待核对事项'}}</h3>
      <p v-for="(issue,index) in issues" :key="index">{{issue.message}}<span v-if="issue.document_id||issue.issue_id||issue.task_id"> · {{issue.document_id||issue.issue_id||issue.task_id}}</span> · <RouterLink :to="destination(issue)">{{storedSnapshot?'查看当前处理工作区':'前往处理工作区'}}</RouterLink></p>
      <p v-if="!issues.length">{{storedSnapshot?'本版本未保留其他核对事项，月结状态以上方记录为准。':'本次已支持的核对范围内未发现待办；不代表正式月结或全部业务验收完成。'}}</p>
    </div>
  </SectionPanel>
</template>
<style scoped>.closing-content{display:grid;gap:16px;padding:20px;min-width:0}.closing-content p{font-size:13px;line-height:1.8;overflow-wrap:anywhere}.closing-content h3{font-weight:600}.closing-content details{overflow-wrap:anywhere}</style>
