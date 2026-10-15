<script setup lang="ts">
import type { UsageCostSummary } from './usageApi'
defineProps<{ summary:UsageCostSummary }>()
</script>

<template>
  <section aria-label="任务与物料成本核对汇总" class="cost-summary">
    <h3>成本核对汇总</h3>
    <p class="cutting-notice">已计价金额按原实发明细汇总，正常耗用和损耗分列、币种分列；待计价部分未计入金额。在制与单套正常材料成本见下方主管归集确认，当前核对数尚未锁月。</p>
    <p v-if="!summary.tasks.length" class="cutting-no-records">暂无有效实发可汇总。</p>
    <template v-else>
      <h4>按任务与执行方核对</h4>
      <div class="cutting-table-scroll" role="region" aria-label="任务成本汇总" tabindex="0"><table>
        <thead><tr><th>任务／执行方</th><th>实发笔数</th><th>各币种已计价费用</th><th>待计价实发笔数</th></tr></thead>
        <tbody><tr v-for="task in summary.tasks" :key="task.key">
          <td>{{task.context.task_name}}<br />{{task.context.resource_name}}（{{task.context.execution==='internal'?'本厂':'外发'}}）<br />BOM V{{task.context.bom_version}} · 执行方 V{{task.context.resource_version??'历史未记录'}}</td>
          <td>{{task.issue_count}}</td>
          <td><p v-for="(cost,currency) in task.costs" :key="currency">{{currency}} · 正常 {{cost.normal}} ＋ 损耗 {{cost.loss}} ＝ {{cost.total}}</p><span v-if="!Object.keys(task.costs).length">{{task.pending_pricing?'待计价':'暂无已计价耗用'}}</span></td>
          <td>{{task.pending_pricing}}<span v-if="task.pending_pricing"> · 金额未完整</span></td>
        </tr></tbody>
      </table></div>
      <h4>按物料与原单位核对</h4>
      <div class="cutting-table-scroll" role="region" aria-label="物料耗用与费用汇总" tabindex="0"><table>
        <thead><tr><th>物料／资料版本</th><th>原单位</th><th>签收／退仓</th><th>正常耗用／损耗</th><th>账面余料</th><th>各币种已计价合计</th><th>待计价用料量（含损耗）</th></tr></thead>
        <tbody><tr v-for="material in summary.materials" :key="material.key">
          <td>{{material.item_code}} · {{material.item_name}}<br />{{material.material.spec}} / {{material.material.color}} · V{{material.material.revision}}</td><td>{{material.unit}}</td>
          <td>{{material.received_quantity}} / {{material.returned_quantity}}</td><td>{{material.consumed_quantity}} / {{material.loss_quantity}}</td><td>{{material.remaining_quantity}}</td>
          <td><p v-for="(cost,currency) in material.costs" :key="currency">{{currency}} {{cost.total}}</p><span v-if="!Object.keys(material.costs).length">{{material.pending_pricing?'待计价':'暂无已计价耗用'}}</span></td>
          <td>{{material.pending_quantity}} {{material.unit}} · {{material.pending_pricing}} 笔实发</td>
        </tr></tbody>
      </table></div>
    </template>
  </section>
</template>

<style scoped>
.cost-summary{display:grid;gap:16px;margin:24px 0}
</style>
