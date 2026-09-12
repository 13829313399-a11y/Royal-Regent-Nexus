<script setup lang="ts">
import { computed } from 'vue'
import { RouterLink } from 'vue-router'
import { ClipboardList } from '@lucide/vue'
import { useSprayWorkspace, capabilities, str, amount, statusName } from '../workspace'
const s = useSprayWorkspace()
const lanes = computed(() => capabilities.filter(v => v.value !== 'uv' || s.items('resources').some(r => r.capability === 'uv')))
const route = (page: string) => ({ path: '/modules/production/spray-production/' + page, query: { factory: s.factory } })
const tasks = (capability: string) => s.items('tasks').filter(t => !['cancelled', 'completed'].includes(str(t, 'status')) && s.find('steps', t.step_id)?.capability === capability)
const due = computed(() => [...s.items('orders')].filter(o => o.status === 'active').sort((a,b) => str(a,'due_date').localeCompare(str(b,'due_date'))).slice(0,8))
const counts = computed(() => s.summary?.counts)
/* 每个数字同时给出业务口径，避免只看数字不知道范围。 */
const metrics = computed(() => [
  { key: 'orders', value: counts.value?.orders, label: '执行工单', hint: '工单交付 · 待跟踪', to: 'orders' },
  { key: 'running', value: counts.value?.running, label: '正在执行', hint: '资源占用中的任务', to: 'schedule' },
  { key: 'planned', value: counts.value?.planned, label: '已排待开工', hint: '已预留资源与时段', to: 'schedule' },
  { key: 'resources', value: counts.value?.resources, label: '已配置资源', hint: '本厂机台 / 工位 / 班组', to: 'master' },
])
function progress(task: Record<string, unknown>) {
  const total = Number(task.quantity)
  return total > 0 ? Math.min(100, Math.max(0, Number(task.reported) / total * 100)) : 0
}
</script>
<template>
  <div class="spray-toolbar"><div><h2>生产总览</h2><p>沿实体批次查看工序、交接和下一步：哪个部件在哪里、等待谁处理。</p></div><div class="spray-toolbar-actions"><RouterLink :to="route('reports')"><span class="spray-badge info"><ClipboardList :size="14" aria-hidden="true" />快速报工</span></RouterLink></div></div>
  <div class="spray-metrics-group" role="group" aria-label="本厂生产概况">
    <RouterLink v-for="metric in metrics" :key="metric.key" class="spray-metric" :to="route(metric.to)">
      <strong>{{ metric.value ?? '—' }}</strong>
      <span>{{ metric.label }}</span>
      <small>{{ metric.hint }}</small>
    </RouterLink>
  </div>
  <div v-if="!s.items('orders').length" class="spray-empty"><h3>尚未建立喷油资料</h3><p>先登记工单和实体部件，再记录真实来料。各厂区独立建立资料。</p><RouterLink :to="route('orders')" class="spray-pill">建立第一张工单</RouterLink></div>
  <template v-else>
    <div class="spray-section-title"><h3>在制任务 · 按工序能力</h3><p class="spray-help">同一条实体量只出现在一个状态；返工沿用原批次，不增加来料。</p></div>
    <section v-for="lane in lanes" :key="lane.value" class="spray-lane">
      <div class="spray-lane-head"><h3>{{ lane.label }}</h3><p class="spray-muted">{{ s.items('resources').filter(r => r.capability === lane.value).length }} 个资源</p></div>
      <div class="spray-lane-body">
        <button v-for="task in tasks(lane.value)" :key="task.id" class="spray-task" :class="{ selected: s.selection === task.batch_id }" @click="s.selection = str(task, 'batch_id')"><h4>{{ s.lineLabel(s.find('lines', s.find('batches', task.batch_id)?.line_id)) }}</h4><p>{{ str(s.find('steps', task.step_id), 'name') }} · {{ str(s.find('resources', task.resource_id), 'name') }}</p><footer><span>{{ amount(task.reported) }} / {{ amount(task.quantity) }} 次</span><span class="spray-pill">{{ statusName(task.status) }}</span></footer><div class="spray-progress" role="progressbar" :aria-valuenow="Math.round(progress(task))" aria-valuemin="0" aria-valuemax="100" :aria-label="'已完成 ' + Math.round(progress(task)) + '%'"><span :style="{ width: progress(task) + '%' }" /></div></button>
        <div v-if="!tasks(lane.value).length" class="spray-muted self-center">暂无执行任务 · <RouterLink :to="route('schedule')">查看可接批次</RouterLink></div>
      </div>
    </section>
    <section class="spray-panel"><div class="spray-section-title"><h3>未来交付窗口</h3><RouterLink :to="route('orders')">全部工单</RouterLink></div><div v-for="order in due" :key="order.id" class="spray-row"><RouterLink :to="route('orders/' + order.id)"><strong>{{ str(order, 'document_no') }}</strong><p class="spray-muted">委托客户：{{ str(order, 'customer') }}</p></RouterLink><span>交期 {{ str(order, 'due_date') }}</span></div><p v-if="!due.length" class="spray-muted">没有已登记的交付窗口。</p></section>
  </template>
  <details class="spray-note"><summary>口径与限制说明</summary><p class="spray-help">实体数量按状态互斥划分，返工尝试不增加来料；排产只生成资源与时段预留，不直接占用库存。工价未定价不阻塞生产确认，金额由后端计算并留存版本快照。</p></details>
</template>
