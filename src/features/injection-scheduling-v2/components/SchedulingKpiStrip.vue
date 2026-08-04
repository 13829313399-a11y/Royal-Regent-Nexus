<script setup lang="ts">
import { AlertTriangle, Boxes, CheckCircle2, Clock3, Cog, Gauge, PackageOpen, ShieldAlert } from '@lucide/vue'
defineProps<{ summary: { availableMachines: number; totalMachines: number; scheduledTasks: number; runningTasks: number; overdue: number; dueSoon: number; remaining: number; completeness: number; backlog: number; review: number } }>()
const number = new Intl.NumberFormat('zh-CN')
</script>

<template>
  <section class="kpi-strip" aria-label="排产关键指标">
    <article class="kpi-card teal"><div><span>机台覆盖</span><strong>{{ summary.availableMachines }}<small>/ {{ summary.totalMachines }}</small></strong><p>可用机台 / 全部机台</p></div><Cog :size="19" /></article>
    <article class="kpi-card blue"><div><span>已排任务</span><strong>{{ summary.scheduledTasks }}<small> 条</small></strong><p>{{ summary.runningTasks }} 条正在生产</p></div><Boxes :size="19" /></article>
    <article class="kpi-card red"><div><span>已超交期</span><strong>{{ summary.overdue }}<small> 条</small></strong><p>交期差小于 0</p></div><AlertTriangle :size="19" /></article>
    <article class="kpi-card amber"><div><span>3 天内到期</span><strong>{{ summary.dueSoon }}<small> 条</small></strong><p>需要优先确认</p></div><Clock3 :size="19" /></article>
    <article class="kpi-card violet"><div><span>当前欠数</span><strong>{{ number.format(summary.remaining) }}</strong><p>按订单剩余数量</p></div><Gauge :size="19" /></article>
    <article class="kpi-card teal"><div><span>模具资料完整率</span><strong>{{ summary.completeness.toFixed(1) }}<small>%</small></strong><p>按标准化状态计算</p></div><CheckCircle2 :size="19" /></article>
    <article class="kpi-card blue"><div><span>待排订单</span><strong>{{ summary.backlog }}<small> 条</small></strong><p>尚未进入当前计划</p></div><PackageOpen :size="19" /></article>
    <article class="kpi-card amber"><div><span>资格待复核</span><strong>{{ summary.review }}<small> 项</small></strong><p>不满足自动放行条件</p></div><ShieldAlert :size="19" /></article>
  </section>
</template>
