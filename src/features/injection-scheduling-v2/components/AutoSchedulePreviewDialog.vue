<script setup lang="ts">
import { computed, ref, watch } from 'vue'
import { AlertTriangle, Bot, CheckCircle2, Clock3, Gauge, GitCompareArrows, Layers3, LoaderCircle, LockKeyhole, RotateCcw, Sparkles, X } from '@lucide/vue'
import { useDialogFocus } from '../composables/useDialogFocus'
import type { AutoScheduleAssignmentRecord, AutoScheduleGenerationOptions, AutoScheduleObjectiveWeights, AutoScheduleRunRecord, MachineRecord, OrderRecord } from '../types'

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
useDialogFocus(() => props.open, dialogRoot)
const orderMap = computed(() => new Map(props.orders.map((item) => [item.id, item])))
const machineMap = computed(() => new Map(props.machines.map((item) => [item.id, item])))
const groupRuns = computed(() => props.comparisonRuns?.length ? [...props.comparisonRuns].sort((a, b) => a.alternativeNo - b.alternativeNo) : props.run ? [props.run] : [])
const canGenerate = computed(() => props.canEdit && props.planStatus === 'DRAFT' && !props.loading)
const applicableCount = computed(() => (props.run?.summary.scheduledCount ?? 0) + (props.run?.summary.reviewCount ?? 0))
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
const decisionLabel = (decision: AutoScheduleAssignmentRecord['decision']) => decision === 'PASS' ? '可应用' : decision === 'REVIEW_REQUIRED' ? '待复核' : '未安排'
const metricText = (value: { before: number; after: number; change: number } | undefined) => value ? `${value.before} → ${value.after}（${value.change > 0 ? '+' : ''}${value.change}）` : '—'
const detailList = (assignment: AutoScheduleAssignmentRecord, key: string) => {
  const value = assignment.explanation[key]
  return Array.isArray(value) ? value as Array<Record<string, unknown>> : []
}
const solverLabel = (run: AutoScheduleRunRecord) => run.solverType === 'CP_SAT' ? `CP-SAT · ${run.solverStatus}` : run.fallbackUsed ? `启发式回退 · ${run.solverStatus}` : '确定性启发式'

watch(selectedPreset, (value) => {
  if (value !== 'custom') weights.value = { ...presets[value].weights }
})
watch(() => props.run?.id, () => { reviewOverrideReason.value = '' })
</script>

<template>
  <Teleport to="body">
  <Transition name="modal">
  <div v-if="open" ref="dialogRoot" class="modal-layer" role="dialog" aria-modal="true" aria-labelledby="auto-schedule-title" tabindex="-1" @click.self="emit('close')" @keydown.esc="emit('close')">
    <section class="auto-schedule-dialog phase3-dialog phase4-dialog">
      <header><div><span class="modal-icon"><Bot :size="20" /></span><div><span class="eyebrow">求解器配置 · CP-SAT</span><strong id="auto-schedule-title">智能排产优化与方案对比</strong></div></div><button aria-label="关闭智能排产弹窗" @click="emit('close')"><X :size="18" /></button></header>

      <div v-if="!run" class="phase3-intro">
        <div class="phase-notice" :class="{ blocked: planStatus !== 'DRAFT' }"><LockKeyhole :size="18" /><div><strong>独立求解，选定后再应用</strong><p>{{ planStatus === 'DRAFT' ? 'CP-SAT 生成 optional interval 方案，约束机台、实体模具副本和锁定任务；超时或组件不可用时自动回退启发式。' : '当前不是可编辑草案，任何方案都不会覆盖已发布计划。' }}</p></div></div>
        <div class="phase4-config">
          <label><span>求解器</span><select v-model="solver"><option value="CP_SAT">CP-SAT 优化</option><option value="HEURISTIC">确定性启发式</option></select></label>
          <label><span>目标预设</span><select v-model="selectedPreset"><option value="balanced">综合平衡</option><option value="due">交期优先</option><option value="changeover">少换模均衡</option><option value="custom">自定义</option></select></label>
          <div class="weight-grid"><label><span>拖期</span><input v-model.number="weights.tardinessWeight" type="number" min="0" max="1000" @input="selectedPreset = 'custom'" /></label><label><span>换型</span><input v-model.number="weights.transitionWeight" type="number" min="0" max="100" @input="selectedPreset = 'custom'" /></label><label><span>安数阶差</span><input v-model.number="weights.classGapWeight" type="number" min="0" max="100" @input="selectedPreset = 'custom'" /></label><label><span>负荷均衡</span><input v-model.number="weights.loadBalanceWeight" type="number" min="0" max="1000" @input="selectedPreset = 'custom'" /></label><label><span>移动扰动</span><input v-model.number="weights.existingTaskMoveCost" type="number" min="0" max="1000" @input="selectedPreset = 'custom'" /></label></div>
        </div>
        <div class="solver-overview"><article><span>输入范围</span><strong>{{ backlogCount }} 条待排 + 未锁定任务</strong></article><article><span>候选机台</span><strong>{{ machineCount }} 台</strong></article><article><span>时间上限</span><strong>10 秒 · 单线程确定性</strong></article></div>
        <div class="solver-flow"><span><CheckCircle2 :size="14" />冻结锁定任务</span><i></i><span><CheckCircle2 :size="14" />双重 NoOverlap</span><i></i><span><Sparkles :size="14" />加权目标求解</span></div>
      </div>

      <div v-else class="auto-run-result">
        <div v-if="groupRuns.length > 1" class="scenario-strip"><button v-for="item in groupRuns" :key="item.id" :class="{ active: item.id === run.id }" @click="emit('select', item)"><span>{{ item.scenarioName }}</span><strong>{{ solverLabel(item) }}</strong><small>超期 {{ item.summary.overdue.after }} · 换模 {{ item.summary.moldChanges.after }} · 未排 {{ item.summary.unassignedCount }}</small></button></div>
        <div class="run-banner" :class="run.status.toLowerCase()"><div><Sparkles :size="18" /><strong>{{ run.status === 'APPLIED' ? '方案已应用' : run.status === 'SUCCEEDED' ? '方案可应用' : run.status === 'PARTIAL' ? '方案部分完成' : `运行 ${run.status}` }}</strong></div><span>{{ run.scenarioName }} · {{ solverLabel(run) }} · {{ run.summary.solverElapsedMs }} ms</span></div>
        <div v-if="run.fallbackUsed" class="solver-fallback"><AlertTriangle :size="15" /><span>CP-SAT 已回退至启发式：{{ run.fallbackReason }}</span></div>
        <div class="solver-overview result-kpis"><article><span>自动安排</span><strong class="good">{{ run.summary.scheduledCount }}</strong></article><article><span>待复核</span><strong class="review">{{ run.summary.reviewCount }}</strong></article><article><span>未安排</span><strong class="bad">{{ run.summary.unassignedCount }}</strong></article><article><span>目标值 / 下界</span><strong>{{ run.summary.objectiveValue ?? '—' }} / {{ run.summary.bestObjectiveBound ?? '—' }}</strong></article></div>
        <div class="comparison-grid">
          <article><Clock3 :size="15" /><span>预计超期</span><strong>{{ metricText(run.summary.overdue) }}</strong></article>
          <article><GitCompareArrows :size="15" /><span>换模次数</span><strong>{{ metricText(run.summary.moldChanges) }}</strong></article>
          <article><AlertTriangle :size="15" /><span>深色→浅色</span><strong>{{ metricText(run.summary.darkToLightChanges) }}</strong></article>
          <article><LockKeyhole :size="15" /><span>冻结任务</span><strong>{{ run.summary.frozenTaskCount }}</strong></article>
        </div>
        <section class="load-section"><header><Gauge :size="15" /><strong>机台负荷</strong></header><div><label v-for="load in run.summary.machineLoads" :key="load.machineId"><span>{{ load.machineCode }}</span><i><b :style="{ width: `${Math.min(100, load.loadRatio * 100)}%` }"></b></i><em>{{ (load.loadRatio * 100).toFixed(1) }}%</em></label></div></section>
        <section class="assignment-section"><header><strong>安排与解释</strong><span>{{ run.assignments.length }} 条</span></header><div class="assignment-list"><details v-for="assignment in run.assignments" :key="assignment.id" :class="assignment.decision.toLowerCase()"><summary><span class="decision">{{ decisionLabel(assignment.decision) }}</span><div><strong>{{ orderMap.get(assignment.orderId)?.orderNo || assignment.orderId }}</strong><small>{{ orderMap.get(assignment.orderId)?.productName }}</small></div><span>{{ assignment.machineId ? machineMap.get(assignment.machineId)?.code || assignment.machineId : assignment.unassignedReasonCode }}</span><time>{{ assignment.plannedStart ? `${assignment.plannedStart.slice(5, 16)} → ${assignment.plannedFinish.slice(5, 16)}` : '—' }}</time><b>{{ assignment.score == null ? '—' : assignment.score.toFixed(1) }}</b></summary><div class="assignment-detail"><p>{{ String(assignment.explanation.summary ?? '暂无说明') }}</p><ul><li v-for="item in detailList(assignment, 'hard_checks')" :key="String(item.code)"><CheckCircle2 :size="13" /><span><strong>{{ item.label }}</strong>{{ item.detail }}</span></li><li v-for="item in detailList(assignment, 'hard_failures')" :key="String(item.rule_code)"><AlertTriangle :size="13" /><span><strong>{{ item.label }}</strong>{{ item.detail }}</span></li></ul><dl v-if="detailList(assignment, 'score_breakdown').length"><div v-for="item in detailList(assignment, 'score_breakdown')" :key="String(item.code)"><dt>{{ item.code }}</dt><dd>{{ item.detail }} · {{ item.cost }}</dd></div></dl></div></details></div></section>
        <label v-if="run.summary.reviewCount" class="override-field"><span>待复核覆盖原因</span><textarea v-model="reviewOverrideReason" :disabled="!canOverride || run.status === 'APPLIED'" placeholder="具备发布/覆盖权限的人员填写后，才可应用含待复核项的方案"></textarea><small v-if="!canOverride">当前账号没有发布/覆盖权限，不能应用待复核安排。</small></label>
      </div>

      <p v-if="error" class="auto-error"><AlertTriangle :size="15" />{{ error }}</p>
      <footer><button @click="emit('close')">关闭</button><button v-if="!run" :disabled="!canGenerate" @click="emit('compare')"><LoaderCircle v-if="loading" class="spin" :size="15" /><Layers3 v-else :size="15" />生成三套方案</button><button v-if="run && run.status !== 'APPLIED'" :disabled="!canGenerate" @click="emit('replay', run)"><RotateCcw :size="15" />按此权重回放</button><button v-if="run && run.status !== 'APPLIED'" :disabled="loading" @click="emit('generate', generationOptions)"><LoaderCircle v-if="loading" class="spin" :size="15" /><Sparkles v-else :size="15" />重新生成</button><button v-if="run && run.status !== 'APPLIED'" class="primary enabled" :disabled="!canApply" @click="emit('apply', reviewOverrideReason)"><LoaderCircle v-if="loading" class="spin" :size="15" /><CheckCircle2 v-else :size="15" />应用到草案</button><button v-else-if="!run" class="primary enabled" :disabled="!canGenerate" @click="emit('generate', generationOptions)"><LoaderCircle v-if="loading" class="spin" :size="15" /><Sparkles v-else :size="15" />生成选定方案</button></footer>
    </section>
  </div>
  </Transition>
  </Teleport>
</template>
