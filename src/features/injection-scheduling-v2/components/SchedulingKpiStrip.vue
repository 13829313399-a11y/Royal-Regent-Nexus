<script setup lang="ts">
import { AlertTriangle, Boxes, CheckCircle2, Clock3, Cog, Gauge, PackageOpen, ShieldAlert } from '@lucide/vue'
import AnimatedMetricValue from './AnimatedMetricValue.vue'
defineProps<{ summary: { availableMachines: number; totalMachines: number; scheduledTasks: number; runningTasks: number; overdue: number; dueSoon: number; remaining: number; completeness: number; backlog: number; review: number } }>()
</script>

<template>
  <section class="kpi-strip" aria-label="排产关键指标">
    <article class="kpi-card core teal"><div><span>可用机台</span><strong><AnimatedMetricValue :value="summary.availableMachines" /><small>/ {{ summary.totalMachines }}</small></strong><p>覆盖全部排产机台</p></div><Cog :size="20" /></article>
    <article class="kpi-card core blue"><div><span>正在生产</span><strong><AnimatedMetricValue :value="summary.runningTasks" /><small> 条</small></strong><p>已排任务 {{ summary.scheduledTasks }} 条</p></div><Boxes :size="20" /></article>
    <article class="kpi-card core red"><div><span>已超交期</span><strong><AnimatedMetricValue :value="summary.overdue" /><small> 条</small></strong><p>需立即处理的交期风险</p></div><AlertTriangle :size="20" /></article>
    <article class="kpi-card core violet"><div><span>当前欠数</span><strong><AnimatedMetricValue :value="summary.remaining" /></strong><p>按订单剩余数量汇总</p></div><Gauge :size="20" /></article>
    <article class="kpi-card compact amber"><div><span>3 天内到期</span><strong><AnimatedMetricValue :value="summary.dueSoon" /><small> 条</small></strong><p>需要优先确认</p></div><Clock3 :size="18" /></article>
    <article class="kpi-card compact teal"><div><span>模具资料完整率</span><strong><AnimatedMetricValue :value="summary.completeness" :decimals="1" /><small>%</small></strong><p>按标准化状态计算</p></div><CheckCircle2 :size="18" /></article>
    <article class="kpi-card compact blue"><div><span>待排订单</span><strong><AnimatedMetricValue :value="summary.backlog" /><small> 条</small></strong><p>尚未进入当前计划</p></div><PackageOpen :size="18" /></article>
    <article class="kpi-card compact amber"><div><span>资格待复核</span><strong><AnimatedMetricValue :value="summary.review" /><small> 项</small></strong><p>不满足自动放行条件</p></div><ShieldAlert :size="18" /></article>
  </section>
</template>
