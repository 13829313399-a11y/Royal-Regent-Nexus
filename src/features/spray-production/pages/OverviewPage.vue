<script setup lang="ts">
import { computed } from 'vue'
import { RouterLink } from 'vue-router'
import { useSprayWorkspace, capabilities, str, amount, statusName } from '../workspace'
const s = useSprayWorkspace()
const lanes = computed(() => capabilities.filter(v => v.value !== 'uv' || s.items('resources').some(r => r.capability === 'uv')))
const route = (page: string) => ({ path: '/modules/production/spray-production/' + page, query: { factory: s.factory } })
const tasks = (capability: string) => s.items('tasks').filter(t => !['cancelled', 'completed'].includes(str(t, 'status')) && s.find('steps', t.step_id)?.capability === capability)
const due = computed(() => [...s.items('orders')].filter(o => o.status === 'active').sort((a,b) => str(a,'due_date').localeCompare(str(b,'due_date'))).slice(0,8))
</script>
<template>
  <div class="spray-toolbar"><div><h2>生产总览</h2><p>沿实体批次查看工序、交接和下一步。</p></div><RouterLink class="spray-pill" :to="route('reports')">快速报工</RouterLink></div>
  <div class="spray-metrics"><RouterLink :to="route('orders')"><strong>{{ s.summary?.counts.orders }}</strong><span>执行工单</span></RouterLink><RouterLink :to="route('schedule')"><strong>{{ s.summary?.counts.running }}</strong><span>正在执行</span></RouterLink><RouterLink :to="route('schedule')"><strong>{{ s.summary?.counts.planned }}</strong><span>已排待开工</span></RouterLink><RouterLink :to="route('master')"><strong>{{ s.summary?.counts.resources }}</strong><span>已配置资源</span></RouterLink></div>
  <div v-if="!s.items('orders').length" class="spray-empty"><h3>尚未建立喷油资料</h3><p>先登记工单和实体部件，再记录真实来料。各厂区独立建立资料。</p><RouterLink :to="route('orders')" class="spray-pill">建立第一张工单</RouterLink></div>
  <section v-for="lane in lanes" :key="lane.value" class="spray-lane"><div class="spray-lane-head"><h3>{{ lane.label }}</h3><p class="spray-muted">{{ s.items('resources').filter(r => r.capability === lane.value).length }} 个资源</p></div><div class="spray-lane-body">
    <button v-for="task in tasks(lane.value)" :key="task.id" class="spray-task" :class="{ selected: s.selection === task.batch_id }" @click="s.selection = str(task, 'batch_id')"><h4>{{ s.lineLabel(s.find('lines', s.find('batches', task.batch_id)?.line_id)) }}</h4><p>{{ str(s.find('steps', task.step_id), 'name') }} · {{ str(s.find('resources', task.resource_id), 'name') }}</p><footer><span>{{ amount(task.reported) }} / {{ amount(task.quantity) }} 次</span><span class="spray-pill">{{ statusName(task.status) }}</span></footer><div class="spray-progress"><span :style="{ width: Math.min(100, Number(task.reported) / Number(task.quantity) * 100) + '%' }" /></div></button>
    <div v-if="!tasks(lane.value).length" class="spray-muted self-center">暂无执行任务 · <RouterLink :to="route('schedule')">查看可接批次</RouterLink></div>
  </div></section>
  <section class="spray-panel"><div class="spray-section-title"><h3>未来交付窗口</h3><RouterLink :to="route('orders')">全部工单</RouterLink></div><div v-for="order in due" :key="order.id" class="spray-row"><RouterLink :to="route('orders/' + order.id)"><strong>{{ str(order, 'document_no') }}</strong><p class="spray-muted">委托客户：{{ str(order, 'customer') }}</p></RouterLink><span>交期 {{ str(order, 'due_date') }}</span></div><p v-if="!due.length" class="spray-muted">没有已登记的交付窗口。</p></section>
</template>
