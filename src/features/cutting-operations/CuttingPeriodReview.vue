<script setup lang="ts">
import { computed } from 'vue'
import { RouterLink } from 'vue-router'
import type { PeriodSnapshot, PeriodComparison } from './periodApi'
import { periodMatches, periodOrderLabel } from './periodDisplay'
import { cuttingDestination } from './location'
import CuttingClosingReport from './CuttingClosingReport.vue'
const props=defineProps<{snapshot:PeriodSnapshot;comparison?:PeriodComparison|null;query:string}>()
const rows=computed(()=>props.snapshot.allocations.filter(row=>periodMatches(props.snapshot.orders,row.line_id,props.query)))
const orders=computed(()=>props.snapshot.orders.filter(row=>periodMatches(props.snapshot.orders,row.line_id,props.query)))
const changes=computed(()=>props.comparison?.rows.filter(row=>periodMatches([...props.snapshot.orders,...props.comparison!.orders],row.line_id,props.query))??[])
const amountFields=[['opening_completed','期初完工'],['opening_wip','期初在制'],['period_normal','本期正常'],['period_completed','本期转完工'],['ending_completed','期末累计完工'],['ending_wip','期末在制'],['period_loss','本期损耗'],['ending_custody','期末现场余料']] as const
</script>
<template>
  <div class="period-review">
    <h3>原实发归集与费用明细</h3>
    <p>显示 {{rows.length}} / {{snapshot.allocations.length}} 笔实发。金额按各自币种列示，数量保留原单位；缺价显示待计价。</p>
    <div class="cutting-table-scroll" role="region" aria-label="原实发完工与在制费用" tabindex="0"><table>
      <thead><tr><th>客户／订单／货号／货名</th><th>任务／物料／原实发</th><th>原单位</th><th>期初完工／在制数量</th><th>期末完工／在制数量</th><th>币种</th><th v-for="[key,label] in amountFields" :key="key">{{label}}金额</th></tr></thead>
      <tbody><tr v-for="row in rows" :key="row.issue_id"><td>{{periodOrderLabel(snapshot.orders,row.line_id)}}</td><td>{{row.context.task_name}} · {{row.context.resource_name}}<br />{{row.context.item_name}}<br /><RouterLink :to="cuttingDestination(row.line_id,snapshot.month,'costs','issue',row.issue_id)">{{row.issue_id}}</RouterLink></td><td>{{row.context.unit}}</td><td>{{row.opening_completed_quantity}} / {{row.opening_wip_quantity}}</td><td>{{row.completed_quantity}} / {{row.ending_wip_quantity}}</td><td>{{row.currency??'待计价'}}</td><td v-for="[key] in amountFields" :key="key">{{row.amounts?.[key]??'待计价'}}</td></tr></tbody>
    </table></div>
    <p v-if="!rows.length">当前筛选范围暂无实发明细。</p>
    <details v-for="row in rows" :key="`price-${row.issue_id}`"><summary>{{row.context.item_name}} · {{row.issue_id}} · 原批次成本凭据</summary>
      <p>原批次 {{row.context.root_batch_id}}</p>
      <p v-if="row.price">本版本保存单价 {{row.price.data.entry.unit_cost}} {{row.price.data.entry.currency}}／{{row.context.unit}} · V{{row.price.version}} · {{row.price.actor}} · {{row.price.date}}<br />凭据：{{row.price.data.entry.price_reference}}<br />原因：{{row.price.reason}}</p><p v-else>待计价，尚无确认的批次成本凭据。</p>
    </details>
    <details v-if="comparison" class="period-comparison"><summary>与上一编制版本 V{{comparison.previous_version}} 比较</summary>
      <p>上一编制人：{{comparison.previous_actor}} · {{comparison.previous_date}} · {{comparison.previous_reason}}</p>
      <p>以下差额为所查看版本减上一编制版本；提交、锁月等沿用同一编制依据的操作不单独作为比较基准。{{comparison.evidence_changed?'生产、物料或成本依据发生变化，请结合来源追溯核对。':'取数依据相同，可重点核对人工归属和声明。'}}</p>
      <p v-if="comparison.partial_pricing" class="cutting-notice">比较版本存在缺价，下列汇总仅为已计价部分的差额，不代表完整费用变化。</p>
      <div class="cutting-table-scroll" role="region" aria-label="整月版本金额差异" tabindex="0"><table><thead><tr><th>币种</th><th>本期正常费用差额</th><th>本期转完工差额</th><th>期末在制差额</th><th>本期损耗差额</th></tr></thead><tbody><tr v-for="(cost,currency) in comparison.costs" :key="currency"><td>{{currency}}</td><td>{{cost.period_normal}}</td><td>{{cost.period_completed}}</td><td>{{cost.ending_wip}}</td><td>{{cost.period_loss}}</td></tr></tbody></table></div>
      <p v-if="!comparison.rows.length">原实发数量与金额未变化；请结合本版本声明、说明和历史操作记录复核。</p>
      <article v-for="row in changes" :key="row.issue_id" class="cutting-master-line">
        <p>{{row.after?.context.item_name??row.before?.context.item_name}} · {{row.issue_id}} · {{!row.before?'新增实发':!row.after?'移除实发':'实发依据或归属变更'}}</p>
        <p>期末完工归属：{{row.before?.completed_quantity??'无原记录'}} → {{row.after?.completed_quantity??'无本版本记录'}}；差额 {{row.quantity_delta.completed_quantity}} {{row.after?.context.unit??row.before?.context.unit}}。期末在制差额 {{row.quantity_delta.ending_wip_quantity}}。</p>
        <p>期末完工金额：{{row.before?.amounts?.ending_completed??(row.before?'待计价':'无原记录')}} {{row.before?.currency}} → {{row.after?.amounts?.ending_completed??(row.after?'待计价':'无本版本记录')}} {{row.after?.currency}}</p>
        <p v-if="row.amount_delta">同币种完工金额差额 {{row.amount_delta.ending_completed}}，在制金额差额 {{row.amount_delta.ending_wip}} {{row.after?.currency}}。</p><p v-else>新增、移除、缺价或币种变化不直接计算此行金额差额，请核对两版凭据。</p>
        <p>成本凭据：{{row.before?.price?.data.entry.price_reference??'无已确认凭据'}} → {{row.after?.price?.data.entry.price_reference??'无已确认凭据'}}</p>
      </article>
    </details><p v-else>首次编制版本，暂无更早的编制版本可比较。</p>
    <details v-for="order in orders" :key="order.line_id"><summary>{{periodOrderLabel(snapshot.orders,order.line_id)}} · 生产、领退耗存及来源依据</summary><CuttingClosingReport :value="order" stored-snapshot /></details>
  </div>
</template>
<style scoped>.period-review{display:grid;gap:16px;margin-top:20px;min-width:0}.period-review p,.period-review summary{line-height:1.8;overflow-wrap:anywhere}.period-review h3{font-weight:600}</style>
