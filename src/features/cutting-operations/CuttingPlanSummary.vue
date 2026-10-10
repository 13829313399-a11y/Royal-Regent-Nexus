<script setup lang="ts">
import type { ProductionPlan } from './planning'
defineProps<{ plan: ProductionPlan; title: string; stale?: boolean }>()
</script>
<template>
  <section class="plan-summary">
    <h3>{{ title }} · V{{ plan.version }}</h3>
    <p v-if="stale" role="alert">依据已变更，此计划待复核；请重新编制并发布，不作为当前执行依据。</p>
    <p>已分配 {{ plan.allocated_sets }} 套 · 未分配 {{ plan.unallocated_sets }} 套</p>
    <div class="cutting-table-scroll"><table><thead><tr><th>任务</th><th>执行方</th><th>目标套数</th><th>已排／未排</th><th>预计最早供数</th><th>实际核定最早供数</th><th>日期依据</th><th>首次计划供数</th><th>计划完成期</th></tr></thead><tbody>
      <tr v-for="task in plan.tasks" :key="task.task_id"><td>{{ task.name }}</td><td>{{ task.resource.data.name }} · {{ 'execution' in task.resource.data && task.resource.data.execution === 'outsourced' ? '外发裁剪' : '本厂裁剪' }}</td><td>{{ task.target_sets }}</td><td>{{ task.planned_sets }} / {{ task.unplanned_sets }}</td><td>{{ task.estimated_supply_date ?? '预计条件待补齐' }}</td><td>{{ task.actual_supply_date ?? '实际条件待核定' }}</td><td>{{ task.date_basis === 'actual' ? (task.actual_review_pending ? '实际核定 · 条件待补齐' : '实际核定') : '提前预排 · 实际待核定' }}</td><td>{{ task.first_supply_date ?? '未编排' }}</td><td>{{ task.completion_date ?? '计划未排完' }}</td></tr>
    </tbody></table></div>
    <details v-for="task in plan.tasks" :key="task.task_id"><summary>{{ task.name }} · 日计划与依据</summary>
      <p>供数准备周期：{{ task.preparation_workdays ?? 3 }} 个工作日（默认建议 3 天，可调整）</p>
      <p>供数起算日期：{{ task.readiness_date ?? '待补齐' }} · {{ task.calendar_source === 'resource' ? '执行方日历' : '默认工作周（周一至周六）' }} · 实际领料：{{ task.actual_issue_date ?? '未登记' }} · 凭据：{{ task.actual_issue_reference || '未登记' }}</p><p v-if="task.expected_issue_date">历史预计领料：{{ task.expected_issue_date }}（不得作为实际领料日）</p><p v-if="task.calendar">工作周：{{ task.calendar.weekdays.map(d => ['周一','周二','周三','周四','周五','周六','周日'][d-1]).join('、') }} · {{ task.calendar.basis }}</p>
      <p v-if="task.date_basis === 'actual'">前置工序实际就绪：{{ task.actual_prerequisite_date ?? '无日期' }} · {{ task.actual_prerequisite_reference }}</p>
      <p>执行资源版本：V{{ task.resource_version }}</p>
      <ul><li v-for="m in task.materials" :key="m.row">当前BOM物料行 {{ m.row+1 }} 预计就绪：{{ m.expected_date ?? '未填写' }}</li></ul>
      <ul v-if="task.calendar?.exceptions.length"><li v-for="e in task.calendar.exceptions" :key="e.day">日历例外 {{ e.day }}：{{ e.working ? '工作／加班' : '休息' }} · {{ e.reason }}</li></ul>
      <p v-if="task.prerequisite_change_reason">取消前置要求依据：{{ task.prerequisite_change_reason }}</p>
      <p v-if="task.resource_change_basis">更换执行方实际凭据复核：{{ task.resource_change_basis }}</p>
      <p>{{ task.readiness_basis || '物料依据待补充' }}；前置工序：{{ (task.prerequisite_required || task.prerequisite_date || task.actual_prerequisite_date) ? '需要' : '未设置要求' }} {{ task.prerequisite_date ?? '无日期' }} {{ task.prerequisite_basis }}</p>
      <ul><li v-for="day in task.days" :key="day.day">{{ day.day }}：{{ day.sets }} 套</li></ul>
    </details>
    <p>发布／保存依据：{{ plan.reason }} · {{ plan.created_at }}</p>
    <p v-if="plan.adjustment_reason">已发布计划调整原因：{{ plan.adjustment_reason }}</p>
    <ul v-if="plan.removed_task_reasons"><li v-for="(reason,id) in plan.removed_task_reasons" :key="id">取消原任务依据：{{ reason }}</li></ul>
  </section>
</template>
<style scoped>.plan-summary { border-top: 1px solid #e2e8f0; margin-top: 1rem; padding-top: .5rem; }.plan-summary [role=alert] { color: #b91c1c; }</style>
