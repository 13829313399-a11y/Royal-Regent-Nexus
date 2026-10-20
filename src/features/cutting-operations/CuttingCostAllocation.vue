<script setup lang="ts">
import { Button } from '@/components/ui/button'
import type { CostAllocationView } from './usageApi'
defineProps<{ value:CostAllocationView; canConfirm:boolean; disabled:boolean }>()
defineEmits<{ confirm:[issueId:string] }>()
const labels={blocked:'依据待核对',unconfirmed:'待确认归属',stale:'变更待复核',pending:'成本待核对',confirmed:'已确认归集'}
</script>

<template>
  <section class="allocation-summary" aria-label="在制归集与单套材料成本">
    <h3>在制归集与单套材料成本</h3>
    <p class="cutting-notice">主管逐笔确认累计正常耗用中归属于合格完工的数量，其余列在制。单套成本＝已归属完工的正常材料费用÷合格完成套数，损耗单列；公共耗料未分配、缺价或归集未完整时不计算单套成本。各币种分别核算。本归集为实时核对数，已锁月份以内部月结的冻结快照为准。</p>
    <p v-if="!value.schema_ready" role="status">每日填数证据尚未就绪，暂不能确认成本归属。</p>
    <p v-if="!value.groups.length" class="cutting-no-records">暂无有效实发可归集。</p>
    <article v-for="group in value.groups" :key="group.key" class="cutting-master-line">
      <h4>{{group.context.task_name}} · {{group.context.resource_name}} · {{labels[group.status]}}</h4>
      <p>合格完成 {{group.completed_sets??'待核对'}} 套 · BOM V{{group.context.bom_version}} · 执行方 V{{group.context.resource_version??'待核对'}} · 待计价实发笔数 {{group.pending_pricing}}</p>
      <p v-if="group.reasons.length" role="status">{{group.reasons.join('；')}}。已计价部分不能代表完整成本。</p>
      <div class="cutting-table-scroll" role="region" aria-label="完工与在制耗用归属" tabindex="0"><table>
        <thead><tr><th>原实发／物料／原批次</th><th>原单位</th><th>累计正常耗用</th><th>已归属完工</th><th>在制耗用</th></tr></thead>
        <tbody><tr v-for="row in group.rows" :key="row.issue_id"><td>{{row.issue_id}}<br />{{row.item_name}} · {{row.root_batch_id}}</td><td>{{row.unit}}</td><td>{{row.consumed_quantity}}</td><td>{{row.completed_quantity??'待核对'}}</td><td>{{row.wip_quantity??'待核对'}}</td></tr></tbody>
      </table></div>
      <div class="cutting-table-scroll" role="region" aria-label="分币种材料成本核算" tabindex="0"><table>
        <thead><tr><th>币种</th><th>已计价完工材料费用</th><th>已计价在制材料费用</th><th>已计价损耗费用</th><th>单套正常材料成本</th></tr></thead>
        <tbody><tr v-for="(cost,currency) in group.costs" :key="currency"><td>{{currency}}</td><td>{{cost.completed??'待核对'}}</td><td>{{cost.wip??'待核对'}}</td><td>{{cost.loss}}</td><td>{{cost.unit_cost??'待核对'}}</td></tr></tbody>
      </table></div>
      <p v-if="!Object.keys(group.costs).length">暂无已计价费用，不以零成本代替缺价。</p>
      <Button v-if="canConfirm" variant="outline" :disabled="disabled||group.status==='blocked'" @click="$emit('confirm',group.key)">{{group.latest_id?'重新确认完工耗用归属':'确认完工耗用归属'}}</Button>
    </article>
    <details v-if="value.history.length"><summary>归集确认与更正历史</summary>
      <article v-for="event in value.history" :key="event.id" class="cutting-master-line">
        <p>{{event.context.task_name}} · V{{event.version}} · {{event.actor}} · {{event.date}} · {{event.reason}}</p>
        <p>确认单 {{event.id}}<span v-if="event.replaces_id"> · 替代确认单 {{event.replaces_id}}</span> · 当时合格完成 {{event.completed_sets}} 套</p>
        <p>全部物料核对：{{event.entry.materials_complete?'已确认':'未完整'}}；公共耗料：{{event.entry.public_material_pending?'待分配':'已核对无待分配项'}}</p>
        <p v-for="row in event.entry.allocations" :key="row.issue_id">原实发 {{row.issue_id}} · 累计完工归属 {{row.completed_quantity}}（原单位见实发明细）</p>
        <p v-for="snapshot in event.price_snapshot" :key="snapshot.issue_id">原实发 {{snapshot.issue_id}} · 确认时成本 {{snapshot.price?`${snapshot.price.data.entry.unit_cost} ${snapshot.price.data.entry.currency} · V${snapshot.price.version}`:'待计价'}} · 正常费用 {{snapshot.normal_cost??'待计价'}} · 损耗 {{snapshot.loss_cost??'待计价'}}</p>
        <details><summary>当时耗用及生产依据</summary>
          <p v-for="source in event.basis_documents?.usage" :key="source.event_id">耗用单 {{source.document_id}} · V{{source.version}} · {{source.entry.day}} · 正常耗用 {{source.entry.consumed_quantity}} · 损耗 {{source.entry.loss_quantity}}</p>
          <p v-for="source in event.basis_documents?.production" :key="source.event_id">生产凭据 {{source.document_id}} · V{{source.version}} · {{source.entry.day}}</p>
        </details>
      </article>
    </details>
  </section>
</template>

<style scoped>.allocation-summary{display:grid;gap:16px;margin:24px 0}</style>
