<script setup lang="ts">
import { computed, ref, watch } from 'vue'
import { AlertTriangle, Bot, CheckCircle2, Clock3, Gauge, GitCompareArrows, Layers3, LoaderCircle, LockKeyhole, RotateCcw, Sparkles, X } from '@lucide/vue'
import { useDialogFocus } from '../composables/useDialogFocus'
import type { AutoScheduleAssignmentRecord, AutoScheduleGenerationOptions, AutoScheduleObjectiveWeights, AutoScheduleRunRecord, MachineRecord, OrderRecord } from '../types'
import SchedulingTechnicalDetails from './SchedulingTechnicalDetails.vue'
import { assignmentDecisionMeta, autoScheduleRunStatusMeta, capacitySourceMeta, solverStatusMeta, solverTypeMeta, unassignedReasonMeta } from '../presentation/schedulingLabels'
import { formatElapsedMilliseconds } from '../presentation/schedulingFormatters'
import { autoScheduleTechnicalDetails } from '../presentation/technicalDetails'

const props = defineProps<{
  open: boolean
  backlogCount: number
  machineCount: number
  planStatus: string
  canEdit: boolean
  canOverride: boolean
  run: AutoScheduleRunRecord | null
  comparisonRuns?: AutoScheduleRunRecord[]
  loading: boolean
  error: string
  orders: OrderRecord[]
  machines: MachineRecord[]
}>()
const emit = defineEmits<{
  close: []
  generate: [options: AutoScheduleGenerationOptions]
  compare: []
  select: [run: AutoScheduleRunRecord]
  replay: [run: AutoScheduleRunRecord]
  apply: [reviewOverrideReason: string]
}>()

type Preset = 'balanced' | 'due' | 'changeover' | 'custom'
const presets: Record<Exclude<Preset, 'custom'>, { name: string; weights: AutoScheduleObjectiveWeights }> = {
  balanced: { name: '方案 A · 综合平衡', weights: { tardinessWeight: 100, transitionWeight: 2, classGapWeight: 1.5, loadBalanceWeight: 25, existingTaskMoveCost: 40 } },
  due: { name: '方案 B · 交期优先', weights: { tardinessWeight: 220, transitionWeight: 1, classGapWeight: 1, loadBalanceWeight: 10, existingTaskMoveCost: 30 } },
  changeover: { name: '方案 C · 少换模均衡', weights: { tardinessWeight: 80, transitionWeight: 8, classGapWeight: 2, loadBalanceWeight: 60, existingTaskMoveCost: 60 } },
}
const selectedPreset = ref<Preset>('balanced')
const solver = ref<'CP_SAT' | 'HEURISTIC'>('CP_SAT')
const weights = ref<AutoScheduleObjectiveWeights>({ ...presets.balanced.weights })
const reviewOverrideReason = ref('')
const dialogRoot = ref<HTMLElement | null>(null)
const { announcement: dialogAnnouncement } = useDialogFocus(() => props.open, dialogRoot, {
  onEscape: () => emit('close'),
  openAnnouncement: '智能排产对话框已打开，按 Escape 关闭。',
})
const orderMap = computed(() => new Map(props.orders.map((item) => [item.id, item])))
const machineMap = computed(() => new Map(props.machines.map((item) => [item.id, item])))
const groupRuns = computed(() => props.comparisonRuns?.length ? [...props.comparisonRuns].sort((a, b) => a.alternativeNo - b.alternativeNo) : props.run ? [props.run] : [])
const canGenerate = computed(() => props.canEdit && props.planStatus === 'DRAFT' && !props.loading)
const applicableCount = computed(() => (props.run?.summary.scheduledCount ?? 0) + (props.run?.summary.reviewCount ?? 0))
const technicalItems = computed(() => props.run ? autoScheduleTechnicalDetails(props.run) : [])
const canApply = computed(() => {
  if (!props.run || props.loading || !['SUCCEEDED', 'PARTIAL'].includes(props.run.status) || !applicableCount.value) return false
  if (props.run.summary.reviewCount && (!props.canOverride || !reviewOverrideReason.value.trim())) return false
  return props.canEdit && props.planStatus === 'DRAFT'
})
const generationOptions = computed<AutoScheduleGenerationOptions>(() => ({
  solver: solver.value,
  scenarioName: selectedPreset.value === 'custom' ? '自定义权重方案' : presets[selectedPreset.value].name,
  objectiveWeights: { ...weights.value },
}))
const decisionLabel = (decision: AutoScheduleAssignmentRecord['decision']) => assignmentDecisionMeta(decision).label
const metricText = (value: { before: number; after: number; change: number } | undefined) => value ? `${value.before} → ${value.after}（${value.change > 0 ? '+' : ''}${value.change}）` : '—'
const detailList = (assignment: AutoScheduleAssignmentRecord, key: string) => {
  const value = assignment.explanation[key]
  return Array.isArray(value) ? value as Array<Record<string, unknown>> : []
}
const productionDetails = (assignment: AutoScheduleAssignmentRecord) => {
  const value = assignment.explanation.production
  if (!value || typeof value !== 'object' || Array.isArray(value)) return []
  const item = value as Record<string, unknown>
  const source = String(item.capacity_source ?? '')
  const sourceLabel = capacitySourceMeta(source).label
  const numberText = (input: unknown) => Number.isFinite(Number(input)) ? Number(input).toLocaleString('zh-CN', { maximumFractionDigits: 3 }) : '—'
  const fullDays = Number(item.full_order_minutes) / 1440
  return [
    { label: '工时依据', value: sourceLabel },
    { label: '整单预计', value: Number.isFinite(fullDays) ? `${fullDays.toLocaleString('zh-CN', { maximumFractionDigits: 1 })} 天` : '—' },
    { label: '本窗口安排', value: numberText(item.planned_quantity) },
    { label: '窗口后待排', value: numberText(item.remaining_quantity) },
    { label: '预计生产时长', value: `${numberText(item.production_minutes)} 分钟` },
  ]
}
const solverLabel = (run: AutoScheduleRunRecord) => `${solverTypeMeta(run.solverType).label} · ${solverStatusMeta(run.solverStatus).label}`

watch(selectedPreset, (value) => {
  if (value !== 'custom') weights.value = { ...presets[value].weights }
})
watch(() => props.run?.id, () => { reviewOverrideReason.value = '' })
</script>

<template>
  <Teleport to="body">
  <Transition name="modal">
  <div v-if="open" ref="dialogRoot" class="modal-layer" role="dialog" aria-modal="true" aria-labelledby="auto-schedule-title" tabindex="-1" @click.self="emit('close')">
    <section class="auto-schedule-dialog phase3-dialog phase4-dialog">
      <header><div><span class="modal-icon"><Bot :size="20" /></span><div><span class="eyebrow">方案生成设置</span><strong id="auto-schedule-title">智能排产优化与方案对比</strong></div></div><button aria-label="关闭智能排产弹窗" @click="emit('close')"><X :size="18" /></button></header>

      <div v-if="!run" class="phase3-intro">
        <div class="phase-notice" :class="{ blocked: planStatus !== 'DRAFT' }"><LockKeyhole :size="18" /><div><strong>独立生成方案，选定后再应用</strong><p>{{ planStatus === 'DRAFT' ? '系统将同时校验机台、实体模具副本和锁定任务；优化服务未完成时会自动切换到快速排产。' : '当前不是可编辑的排产草案，任何方案都不会覆盖当前执行计划。' }}</p></div></div>
        <div class="business-preset-grid" aria-label="业务排期方案">
          <button type="button" data-preset="balanced" :class="{ active: selectedPreset === 'balanced' }" @click="selectedPreset = 'balanced'"><strong>综合平衡</strong><span>兼顾交期、换模与机台负荷</span></button>
          <button type="button" data-preset="due" :class="{ active: selectedPreset === 'due' }" @click="selectedPreset = 'due'"><strong>交期优先</strong><span>优先降低订单超期风险</span></button>
          <button type="button" data-preset="changeover" :class="{ active: selectedPreset === 'changeover' }" @click="selectedPreset = 'changeover'"><strong>少换模</strong><span>优先减少换模并均衡机台</span></button>
        </div>
        <div class="solver-overview business-input-overview"><article><span>输入范围</span><strong>{{ backlogCount }} 条待排 + 未锁定任务</strong></article><article><span>候选机台</span><strong>{{ machineCount }} 台</strong></article></div>
        <div v-if="loading" class="auto-generation-progress" role="status" aria-live="polite"><LoaderCircle class="spin" :size="16" /><span>正在检查条件并生成排产方案…</span></div>
        <details class="optimization-details">
          <summary>优化详情</summary>
          <div class="phase4-config">
            <label><span>排产方式</span><select v-model="solver"><option value="CP_SAT">{{ solverTypeMeta('CP_SAT').label }}</option><option value="HEURISTIC">{{ solverTypeMeta('HEURISTIC').label }}</option></select></label>
            <div class="custom-weight-heading"><strong>自定义权重</strong><span>修改任一权重后自动切换为自定义方案</span></div>
            <div class="weight-grid"><label><span>拖期</span><input v-model.number="weights.tardinessWeight" type="number" min="0" max="1000" @input="selectedPreset = 'custom'" /></label><label><span>换型</span><input v-model.number="weights.transitionWeight" type="number" min="0" max="100" @input="selectedPreset = 'custom'" /></label><label><span>安数阶差</span><input v-model.number="weights.classGapWeight" type="number" min="0" max="100" @input="selectedPreset = 'custom'" /></label><label><span>负荷均衡</span><input v-model.number="weights.loadBalanceWeight" type="number" min="0" max="1000" @input="selectedPreset = 'custom'" /></label><label><span>移动扰动</span><input v-model.number="weights.existingTaskMoveCost" type="number" min="0" max="1000" @input="selectedPreset = 'custom'" /></label></div>
          </div>
          <div class="optimization-constraint-note"><strong>技术约束</strong><span>10 秒 · 单线程确定性；保留锁定任务并校验机台、实体模具副本与占用。</span></div>
          <div class="solver-flow"><span><CheckCircle2 :size="14" />保留锁定任务</span><i></i><span><CheckCircle2 :size="14" />校验机台与模具占用</span><i></i><span><Sparkles :size="14" />按业务目标优化</span></div>
        </details>
      </div>

      <div v-else class="auto-run-result">
        <div class="business-result-layer">
          <div v-if="groupRuns.length > 1" class="scenario-strip"><button v-for="item in groupRuns" :key="item.id" :class="{ active: item.id === run.id }" @click="emit('select', item)"><span>{{ item.scenarioName }}</span><strong>预计超期 {{ item.summary.overdue.after }} · 换模 {{ item.summary.moldChanges.after }}</strong><small>待复核 {{ item.summary.reviewCount }} · 未安排 {{ item.summary.unassignedCount }}</small></button></div>
          <div class="run-banner" :class="run.status.toLowerCase()"><div><Sparkles :size="18" /><strong>{{ autoScheduleRunStatusMeta(run.status).label }}</strong></div><span>{{ run.scenarioName }}</span></div>
          <div v-if="run.fallbackUsed" class="solver-fallback"><AlertTriangle :size="15" /><span>系统已使用快速排产生成本方案，请复核安排结果。</span></div>
          <div class="comparison-grid business-result-kpis">
            <article><Clock3 :size="15" /><span>预计超期</span><strong>{{ metricText(run.summary.overdue) }}</strong></article>
            <article><GitCompareArrows :size="15" /><span>换模次数</span><strong>{{ metricText(run.summary.moldChanges) }}</strong></article>
            <article><AlertTriangle :size="15" /><span>待复核</span><strong class="review">{{ run.summary.reviewCount }}</strong></article>
            <article><AlertTriangle :size="15" /><span>未安排</span><strong class="bad">{{ run.summary.unassignedCount }}</strong></article>
          </div>
          <section class="load-section"><header><Gauge :size="15" /><strong>机台负荷</strong></header><div><label v-for="load in run.summary.machineLoads" :key="load.machineId"><span>{{ load.machineCode }}</span><i><b :style="{ width: `${Math.min(100, load.loadRatio * 100)}%` }"></b></i><em>{{ (load.loadRatio * 100).toFixed(1) }}%</em></label><p v-if="!run.summary.machineLoads.length" class="empty-copy">暂无机台负荷数据</p></div></section>
        </div>
        <details class="optimization-details result-optimization-details">
          <summary>优化详情</summary>
          <div class="optimization-result-overview"><strong>{{ solverLabel(run) }}</strong><span>{{ formatElapsedMilliseconds(run.summary.solverElapsedMs) }}</span></div>
          <SchedulingTechnicalDetails :items="technicalItems" summary="原始运行记录" />
          <div class="comparison-grid optimization-metrics">
            <article><AlertTriangle :size="15" /><span>深色→浅色</span><strong>{{ metricText(run.summary.darkToLightChanges) }}</strong></article>
            <article><LockKeyhole :size="15" /><span>冻结任务</span><strong>{{ run.summary.frozenTaskCount }}</strong></article>
            <article><Clock3 :size="15" /><span>机台接续点</span><strong>{{ run.summary.continuationAnchors?.length ?? 0 }}</strong></article>
          </div>
          <div v-if="run.status !== 'APPLIED'" class="optimization-actions"><button type="button" :disabled="!canGenerate" @click="emit('replay', run)"><RotateCcw :size="15" />按此权重回放</button><button type="button" :disabled="loading" @click="emit('generate', generationOptions)"><LoaderCircle v-if="loading" class="spin" :size="15" /><Sparkles v-else :size="15" />重新生成</button></div>
        </details>
        <details v-if="run.assignments.length" class="assignment-section assignment-business-details"><summary><strong>安排明细与业务说明</strong><span>{{ run.assignments.length }} 条</span></summary><div class="assignment-list"><details v-for="assignment in run.assignments" :key="assignment.id" :class="assignment.decision.toLowerCase()"><summary><span class="decision">{{ decisionLabel(assignment.decision) }}</span><div><strong>{{ orderMap.get(assignment.orderId)?.orderNo || assignment.orderId }}</strong><small>{{ orderMap.get(assignment.orderId)?.productName }}</small></div><span>{{ assignment.machineId ? machineMap.get(assignment.machineId)?.code || assignment.machineId : unassignedReasonMeta(assignment.unassignedReasonCode).label }}</span><time>{{ assignment.plannedStart ? `${assignment.plannedStart.slice(5, 16)} → ${assignment.plannedFinish.slice(5, 16)}` : '—' }}</time><b>{{ assignment.score == null ? '—' : assignment.score.toFixed(1) }}</b></summary><div class="assignment-detail"><p>{{ String(assignment.explanation.summary ?? '暂无说明') }}</p><dl v-if="productionDetails(assignment).length" class="production-details"><div v-for="item in productionDetails(assignment)" :key="item.label"><dt>{{ item.label }}</dt><dd>{{ item.value }}</dd></div></dl><ul><li v-for="item in detailList(assignment, 'hard_checks')" :key="String(item.code)"><CheckCircle2 :size="13" /><span><strong>{{ item.label }}</strong>{{ item.detail }}</span></li><li v-for="item in detailList(assignment, 'hard_failures')" :key="String(item.rule_code)"><AlertTriangle :size="13" /><span><strong>{{ item.label }}</strong>{{ item.detail }}</span></li></ul><dl v-if="detailList(assignment, 'score_breakdown').length"><div v-for="item in detailList(assignment, 'score_breakdown')" :key="String(item.code)"><dt>{{ item.code }}</dt><dd>{{ item.detail }} · {{ item.cost }}</dd></div></dl></div></details></div></details>
        <label v-if="run.summary.reviewCount" class="override-field"><span>待复核覆盖原因</span><textarea v-model="reviewOverrideReason" :disabled="!canOverride || run.status === 'APPLIED'" placeholder="具备发布/覆盖权限的人员填写后，才可应用含待复核项的方案"></textarea><small v-if="!canOverride">当前账号没有发布/覆盖权限，不能应用待复核安排。</small></label>
      </div>

      <p v-if="error" class="auto-error"><AlertTriangle :size="15" />{{ error }}</p>
      <footer><button @click="emit('close')">关闭</button><button v-if="!run" :disabled="!canGenerate" @click="emit('compare')"><LoaderCircle v-if="loading" class="spin" :size="15" /><Layers3 v-else :size="15" />生成三套方案</button><button v-if="run && run.status !== 'APPLIED'" class="primary enabled" :disabled="!canApply" @click="emit('apply', reviewOverrideReason)"><LoaderCircle v-if="loading" class="spin" :size="15" /><CheckCircle2 v-else :size="15" />应用到草案</button><button v-else-if="!run" class="primary enabled" :disabled="!canGenerate" @click="emit('generate', generationOptions)"><LoaderCircle v-if="loading" class="spin" :size="15" /><Sparkles v-else :size="15" />生成选定方案</button></footer>
      <p class="scheduling-sr-only dialog-live-announcement" role="status" aria-live="polite">{{ dialogAnnouncement }}</p>
    </section>
  </div>
  </Transition>
  </Teleport>
</template>
