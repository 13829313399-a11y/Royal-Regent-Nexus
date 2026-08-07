<script setup lang="ts">
import { ClipboardClock, History, PackageSearch, ShieldCheck, X } from '@lucide/vue'
import EligibilityChecks from './EligibilityChecks.vue'
import ProductionReportPanel from './ProductionReportPanel.vue'
import type { AuditEvent, EditableCellKey, MachineRecord, MoldRecord, OrderRecord, ScheduleTaskRecord } from '../types'

defineProps<{ task: ScheduleTaskRecord | null; order: OrderRecord | null; mold: MoldRecord | null; machine: MachineRecord | null; tab: 'order' | 'eligibility' | 'report' | 'history'; events: AuditEvent[]; planStatus: string; canReport: boolean; pendingCount: number; saving: boolean }>()
const emit = defineEmits<{ 'update:tab': [value: 'order' | 'eligibility' | 'report' | 'history']; close: []; stage: [edits: Array<{ key: EditableCellKey; value: string | number }>]; save: [] }>()
const number = new Intl.NumberFormat('zh-CN')
function calculation(task: ScheduleTaskRecord) {
  const value = task.autoExplanation?.calculation
  return value && typeof value === 'object' ? value as Record<string, unknown> : {}
}
</script>

<template>
  <aside class="task-inspector" aria-label="任务详情抽屉">
    <header><div><span class="eyebrow">任务执行档案</span><strong>{{ order ? `${order.orderNo} · ${mold?.moldNo ?? '未关联模具'}` : '任务详情' }}</strong></div><button aria-label="关闭任务详情" @click="emit('close')"><X :size="17" /></button></header>
    <nav><button :class="{ active: tab === 'order' }" @click="emit('update:tab', 'order')"><PackageSearch :size="14" />订单 / 模具</button><button :class="{ active: tab === 'eligibility' }" @click="emit('update:tab', 'eligibility')"><ShieldCheck :size="14" />资格</button><button :class="{ active: tab === 'report' }" @click="emit('update:tab', 'report')"><ClipboardClock :size="14" />生产回报</button><button :class="{ active: tab === 'history' }" @click="emit('update:tab', 'history')"><History :size="14" />历史</button></nav>
    <div class="inspector-body">
      <template v-if="task && order">
        <section v-if="tab === 'order'" class="inspector-section"><div class="section-heading"><strong>订单与工模</strong><span :class="['priority', order.priorityCode.toLowerCase()]">{{ order.priorityCode === 'CRITICAL' ? '特急' : order.priorityCode === 'URGENT' ? '加急' : '普通' }}</span></div><dl><div><dt>产品名称</dt><dd>{{ order.productName || '—' }}</dd></div><div><dt>订单 / 货号</dt><dd>{{ order.orderNo }} / {{ order.itemNo || '—' }}</dd></div><div><dt>工模</dt><dd>{{ mold?.moldNo ?? '未关联' }}</dd></div><div><dt>模具安数</dt><dd>{{ mold?.aClass ? `${mold.aClass}A` : mold?.aClassRaw || '待复核' }}</dd></div><div><dt>来源</dt><dd>{{ task.sourceSheetName || task.origin || '系统' }}{{ task.sourceRow ? ` · 行 ${task.sourceRow}` : '' }} · Profile {{ task.profileId || 'LEGACY_UNKNOWN' }} r{{ task.profileRevision ?? '—' }}</dd></div><div><dt>订单数 / 欠数</dt><dd>{{ number.format(order.orderQuantity) }} / <b>{{ number.format(order.outstandingQuantity) }}</b></dd></div><div><dt>交货完成期</dt><dd :class="{ negative: (order.deliverySlackDays ?? 0) < 0 }">{{ order.deliveryDueDate || '—' }} · {{ order.deliverySlackDays ?? '—' }} 天</dd></div><div><dt>物料</dt><dd>{{ mold?.materialName || '待补充' }} · {{ mold?.colorProfile || '颜色待补充' }}</dd></div><div><dt>机械手 / 夹具</dt><dd>{{ mold?.requiredArmType || '待补充' }} / {{ mold?.requiredFixtureType || '待补充' }}</dd></div><div><dt>来源计划窗口</dt><dd>{{ task.plannedStart || '—' }}<br />至 {{ task.plannedFinish || '—' }}</dd></div><div><dt>系统预计窗口</dt><dd>{{ task.estimatedStart || '—' }}<br />至 {{ task.estimatedFinish || '—' }}</dd></div><div><dt>统一计算</dt><dd>setup {{ task.setupMinutes ?? 0 }} 分钟 · 生产 {{ task.productionMinutes ?? 0 }} 分钟 · 停机/日历 {{ task.plannedDowntimeMinutes ?? 0 }} 分钟<br />{{ task.changeoverType || '无 transition 分类' }}</dd></div><div><dt>接续锚点</dt><dd>{{ calculation(task).continuation_anchor || '暂无结构化锚点' }}</dd></div><div><dt>计算口径</dt><dd>{{ calculation(task).calculation_version || 'LEGACY_UNKNOWN' }} · {{ calculation(task).speed_source || '速度模型未记录' }}</dd></div><div><dt>备注</dt><dd>{{ order.remark || '无' }}</dd></div></dl></section>
        <EligibilityChecks v-else-if="tab === 'eligibility'" :machine="machine" :mold="mold" />
        <ProductionReportPanel v-else-if="tab === 'report'" :task="task" :order="order" :plan-status="planStatus" :can-report="canReport" :pending-count="pendingCount" :saving="saving" @stage="emit('stage', $event)" @save="emit('save')" />
        <section v-else class="inspector-section history-list"><div class="section-heading"><strong>历史与审计</strong><span>最近 {{ events.length }} 条</span></div><article v-for="event in events.slice(0, 8)" :key="event.id"><span>{{ event.sequence }}</span><div><strong>{{ event.eventType }}</strong><p>{{ event.actorName || '系统' }} · {{ event.createdAt }}</p></div></article><p v-if="!events.length" class="empty-copy">暂无可见审计事件</p></section>
      </template>
      <div v-else class="inspector-empty"><PackageSearch :size="20" /><strong>选择一条任务</strong><span>查看订单、资格、生产回报和审计信息。</span></div>
    </div>
  </aside>
</template>
