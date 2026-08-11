<script setup lang="ts">
import { ClipboardClock, History, PackageSearch, RotateCcw, ShieldCheck, X } from '@lucide/vue'
import { computed } from 'vue'
import EligibilityChecks from './EligibilityChecks.vue'
import ProductionReportPanel from './ProductionReportPanel.vue'
import SchedulingTechnicalDetails from './SchedulingTechnicalDetails.vue'
import type { AuditEvent, EditableCellKey, MachineRecord, MoldRecord, OrderRecord, ScheduleTaskRecord } from '../types'
import { fitDecisionMeta, priorityMeta } from '../presentation/schedulingLabels'
import { formatAuditEventLabel } from '../presentation/schedulingFormatters'
import { auditEventTechnicalDetails, taskTechnicalDetails } from '../presentation/technicalDetails'

const props = defineProps<{ task: ScheduleTaskRecord | null; order: OrderRecord | null; mold: MoldRecord | null; machine: MachineRecord | null; tab: 'order' | 'eligibility' | 'report' | 'history'; events: AuditEvent[]; planStatus: string; canReport: boolean; canWithdraw: boolean; withdrawDisabledReason: string; withdrawing: boolean; pendingCount: number; saving: boolean }>()
const emit = defineEmits<{ 'update:tab': [value: 'order' | 'eligibility' | 'report' | 'history']; close: []; stage: [edits: Array<{ key: EditableCellKey; value: string | number }>]; save: []; withdraw: [] }>()
const number = new Intl.NumberFormat('zh-CN')
const technicalItems = computed(() => props.task ? taskTechnicalDetails(props.task) : [])
function taskProgress(task: ScheduleTaskRecord) {
  if (!task.targetQuantity) return '0%'
  return `${Math.min(100, Math.max(0, task.reportedQuantity / task.targetQuantity * 100)).toLocaleString('zh-CN', { maximumFractionDigits: 1 })}%`
}
function fitConclusion(task: ScheduleTaskRecord) {
  const decision = task.autoExplanation?.decision
  if (decision === 'PASS' || decision === 'REVIEW_REQUIRED' || decision === 'FAIL') return fitDecisionMeta(decision).label
  return task.manualOverrideReason ? '人工调整后安排' : '按当前计划安排'
}
function businessReason(task: ScheduleTaskRecord) {
  const summary = task.autoExplanation?.summary
  if (typeof summary === 'string' && summary.trim()) return summary
  return task.manualOverrideReason || '暂无额外适配或冲突说明'
}
</script>

<template>
  <aside class="task-inspector" aria-label="任务详情抽屉">
    <header><div><span class="eyebrow">任务执行档案</span><strong>{{ order ? `${order.orderNo} · ${mold?.moldNo ?? '未关联模具'}` : '任务详情' }}</strong></div><button aria-label="关闭任务详情" @click="emit('close')"><X :size="17" /></button></header>
    <nav><button :class="{ active: tab === 'order' }" @click="emit('update:tab', 'order')"><PackageSearch :size="14" />订单 / 模具</button><button :class="{ active: tab === 'eligibility' }" @click="emit('update:tab', 'eligibility')"><ShieldCheck :size="14" />资格</button><button :class="{ active: tab === 'report' }" @click="emit('update:tab', 'report')"><ClipboardClock :size="14" />生产回报</button><button :class="{ active: tab === 'history' }" @click="emit('update:tab', 'history')"><History :size="14" />历史</button></nav>
    <div class="inspector-body">
      <template v-if="task && order">
        <section v-if="tab === 'order'" class="inspector-section"><div class="section-heading"><strong>订单与生产安排</strong><span :class="['priority', priorityMeta(order.priorityCode).cssToken]">{{ priorityMeta(order.priorityCode).label }}</span></div><dl class="inspector-business-details"><div><dt>产品名称</dt><dd>{{ order.productName || '—' }}</dd></div><div><dt>订单 / 货号</dt><dd>{{ order.orderNo }} / {{ order.itemNo || '—' }}</dd></div><div><dt>模具与机台</dt><dd>{{ mold?.moldNo ?? '未关联模具' }} / {{ machine?.code ?? '未关联机台' }}</dd></div><div><dt>模具安数</dt><dd>{{ mold?.aClass ? `${mold.aClass}A` : mold?.aClassRaw || '待复核' }}</dd></div><div><dt>来源</dt><dd>{{ task.sourceSheetName || task.origin || '系统' }}{{ task.sourceRow ? ` · 行 ${task.sourceRow}` : '' }}</dd></div><div><dt>欠数 / 目标数</dt><dd><b>{{ number.format(order.outstandingQuantity) }}</b> / {{ number.format(task.targetQuantity) }}</dd></div><div><dt>生产进度</dt><dd>{{ number.format(task.reportedQuantity) }} / {{ number.format(task.targetQuantity) }} · {{ taskProgress(task) }}</dd></div><div><dt>交货完成期</dt><dd :class="{ negative: (order.deliverySlackDays ?? 0) < 0 }">{{ order.deliveryDueDate || '—' }} · {{ order.deliverySlackDays ?? '—' }} 天</dd></div><div><dt>计划开始 / 完成</dt><dd>{{ task.plannedStart || '—' }}<br />至 {{ task.plannedFinish || '—' }}</dd></div><div><dt>系统预计窗口</dt><dd>{{ task.estimatedStart || '—' }}<br />至 {{ task.estimatedFinish || '—' }}</dd></div><div><dt>适配结论</dt><dd>{{ fitConclusion(task) }}</dd></div><div><dt>业务原因</dt><dd>{{ businessReason(task) }}</dd></div><div><dt>物料</dt><dd>{{ mold?.materialName || '待补充' }} · {{ mold?.colorProfile || '颜色待补充' }}</dd></div><div><dt>机械手 / 夹具</dt><dd>{{ mold?.requiredArmType || '待补充' }} / {{ mold?.requiredFixtureType || '待补充' }}</dd></div><div><dt>备注</dt><dd>{{ order.remark || '无' }}</dd></div></dl><SchedulingTechnicalDetails class="inspector-technical-details" :items="technicalItems" /><div class="withdraw-task-action"><div><strong>需要重新排机？</strong><span>{{ planStatus === 'PUBLISHED' ? '撤回会先进入调整草案，发布后正式生效。' : '撤回后未完成数量回到待排订单池。' }}</span></div><button type="button" :disabled="!canWithdraw || withdrawing" :title="withdrawDisabledReason || '撤回到待排订单池'" @click="emit('withdraw')"><RotateCcw :size="14" />{{ withdrawing ? '撤回中…' : '撤回待排' }}</button></div></section>
        <EligibilityChecks v-else-if="tab === 'eligibility'" :machine="machine" :mold="mold" />
        <ProductionReportPanel v-else-if="tab === 'report'" :task="task" :order="order" :plan-status="planStatus" :can-report="canReport" :pending-count="pendingCount" :saving="saving" @stage="emit('stage', $event)" @save="emit('save')" />
        <section v-else class="inspector-section history-list"><div class="section-heading"><strong>历史与审计</strong><span>最近 {{ events.length }} 条</span></div><article v-for="event in events.slice(0, 8)" :key="event.id"><div class="history-event-business"><span aria-hidden="true"></span><div><strong>{{ formatAuditEventLabel(event.eventType) }}</strong><p>{{ event.actorName || '系统' }} · {{ event.createdAt }}</p></div></div><SchedulingTechnicalDetails class="history-event-technical" :items="auditEventTechnicalDetails(event)" /></article><p v-if="!events.length" class="empty-copy">暂无可见审计事件</p></section>
      </template>
      <div v-else class="inspector-empty"><PackageSearch :size="20" /><strong>选择一条任务</strong><span>查看订单、资格、生产回报和审计信息。</span></div>
    </div>
  </aside>
</template>
