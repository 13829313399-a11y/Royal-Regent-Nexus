<script setup lang="ts">
import { computed } from 'vue'
import { RouterLink } from 'vue-router'
import { Activity, CalendarClock, ClipboardList, Gauge, HardHat, Route } from '@lucide/vue'
import { useSprayWorkspace, capabilities, localDate, str, amount, type Entity } from '../workspace'
import SprayStatusPill from '../components/ui/SprayStatusPill.vue'
const s = useSprayWorkspace()
/* 泳道顺序固定为手喷、自动、移印、UV，进场级联既有意义也稳定，不随数据顺序抖动。 */
const lanes = computed(() => capabilities.filter(v => v.value !== 'uv' || s.items('resources').some(r => r.capability === 'uv')))
const route = (page: string) => ({ path: '/modules/production/spray-production/' + page, query: { factory: s.factory } })
const tasks = (capability: string) => s.items('tasks').filter(t => !['cancelled', 'completed'].includes(str(t, 'status')) && s.find('steps', t.step_id)?.capability === capability)
const due = computed(() => [...s.items('orders')].filter(o => o.status === 'active').sort((a, b) => str(a, 'due_date').localeCompare(str(b, 'due_date'))).slice(0, 8))
const counts = computed(() => s.summary?.counts)
/* 每个数字同时给出业务口径与图标，避免只看数字不知道范围。 */
const metrics = computed(() => [
  { key: 'orders', value: counts.value?.orders, label: '执行工单', hint: '工单交付 · 待跟踪', to: 'orders', icon: ClipboardList },
  { key: 'running', value: counts.value?.running, label: '正在执行', hint: '资源占用中的任务', to: 'schedule', icon: Activity, live: true },
  { key: 'planned', value: counts.value?.planned, label: '已排待开工', hint: '已预留资源与时段', to: 'schedule', icon: CalendarClock },
  { key: 'resources', value: counts.value?.resources, label: '已配置资源', hint: '本厂机台 / 工位 / 班组', to: 'master', icon: HardHat },
])
function progress(task: Record<string, unknown>) {
  const total = Number(task.quantity)
  return total > 0 ? Math.min(100, Math.max(0, Number(task.reported) / total * 100)) : 0
}
/* 交期状态：过期用警告色、未过期用信息色、无日期用中性色，文字始终写明日期。 */
function dueTone(order: Entity) {
  const date = str(order, 'due_date')
  if (!date) return 'neutral' as const
  return date < localDate() ? 'warn' as const : 'info' as const
}
</script>
<template>
  <div class="spray-toolbar"><div><h2>生产总览</h2><p>沿实体批次查看工序、交接和下一步：哪个部件在哪里、等待谁处理。</p></div><div class="spray-toolbar-actions"><RouterLink :to="route('reports')" class="spray-badge info"><ClipboardList :size="14" aria-hidden="true" />快速报工</RouterLink></div></div>
  <div v-if="!s.items('orders').length" class="spray-empty"><h3>尚未建立喷油资料</h3><p>先登记工单和实体部件，再记录真实来料。各厂区独立建立资料。</p><RouterLink :to="route('orders')" class="spray-pill">建立第一张工单</RouterLink></div>
  <template v-else>
    <div class="spray-metrics-group spray-stagger" role="group" aria-label="本厂生产概况">
      <RouterLink v-for="metric in metrics" :key="metric.key" class="spray-metric" :to="route(metric.to)">
        <span class="spray-metric-head"><component :is="metric.icon" :size="15" aria-hidden="true" />{{ metric.label }}</span>
        <strong>{{ metric.value ?? '—' }}</strong>
        <small><i class="spray-dot" :class="{ pulse: metric.live && !!metric.value }" aria-hidden="true" />{{ metric.hint }}</small>
      </RouterLink>
    </div>
    <div class="spray-section-title"><h3>在制任务 · 按工序能力</h3><p class="spray-help">同一条实体量只出现在一个状态；返工沿用原批次，不增加来料。</p></div>
    <section v-for="(lane, laneIndex) in lanes" :key="lane.value" class="spray-lane spray-enter" :style="{ '--spray-enter-delay': laneIndex * 70 + 'ms' }">
      <div class="spray-lane-head"><h3>{{ lane.label }}</h3><p class="spray-muted"><b class="spray-num">{{ s.items('resources').filter(r => r.capability === lane.value).length }}</b> 个资源</p></div>
      <div class="spray-lane-body">
        <button v-for="(task, taskIndex) in tasks(lane.value)" :key="task.id" class="spray-task spray-enter" :class="{ selected: s.selection === task.batch_id }" :style="{ '--spray-enter-delay': Math.min(300, laneIndex * 70 + taskIndex * 40) + 'ms' }" @click="s.selection = str(task, 'batch_id')"><h4>{{ s.lineLabel(s.find('lines', s.find('batches', task.batch_id)?.line_id)) }}</h4><p><Route :size="12" aria-hidden="true" />{{ str(s.find('steps', task.step_id), 'name') }} · {{ str(s.find('resources', task.resource_id), 'name') }}</p><footer><span class="spray-num">{{ amount(task.reported) }} / {{ amount(task.quantity) }} 次</span><SprayStatusPill :status="task.status" :spinning="str(task, 'status') === 'running'" /></footer><div class="spray-progress" role="progressbar" :aria-valuenow="Math.round(progress(task))" aria-valuemin="0" aria-valuemax="100" :aria-label="'已完成 ' + Math.round(progress(task)) + '%'"><span :style="{ width: progress(task) + '%' }" /></div></button>
        <div v-if="!tasks(lane.value).length" class="spray-muted self-center">暂无执行任务 · <RouterLink :to="route('schedule')">查看可接批次</RouterLink></div>
      </div>
    </section>
    <section class="spray-panel"><div class="spray-section-title"><h3>未来交付窗口</h3><RouterLink :to="route('orders')">全部工单</RouterLink></div><div v-for="order in due" :key="order.id" class="spray-row"><RouterLink :to="route('orders/' + order.id)"><strong>{{ str(order, 'document_no') }}</strong><p class="spray-muted">委托客户：{{ str(order, 'customer') }}</p></RouterLink><span class="spray-due"><SprayStatusPill :status="dueTone(order)" :label="'交期 ' + str(order, 'due_date')" :tone="dueTone(order)" /></span></div><p v-if="!due.length" class="spray-muted">没有已登记的交付窗口。</p></section>
  </template>
  <details class="spray-note"><summary><Gauge :size="14" aria-hidden="true" />口径与限制说明</summary><p class="spray-help">实体数量按状态互斥划分，返工尝试不增加来料；排产只生成资源与时段预留，不直接占用库存。工价未定价不阻塞生产确认，金额由后端计算并留存版本快照。</p></details>
</template>
