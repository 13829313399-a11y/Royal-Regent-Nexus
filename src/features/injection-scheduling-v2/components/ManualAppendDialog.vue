<script setup lang="ts">
import { computed, ref, watch } from 'vue'
import { AlertTriangle, CheckCircle2, Clock3, X } from '@lucide/vue'
import { getApiErrorMessage } from '@/lib/http'
import { confirmManualAppend, previewManualAppend } from '../api/injectionSchedulingV2Api'
import type { FactoryId, MachineRecord, ManualAppendPreviewRecord, OrderRecord, SchedulingPlanRecord } from '../types'
import { useDialogFocus } from '../composables/useDialogFocus'
import { fitDecisionMeta } from '../presentation/schedulingLabels'
import SchedulingTechnicalDetails from './SchedulingTechnicalDetails.vue'

const props = defineProps<{ open: boolean; factoryId: FactoryId; plan: SchedulingPlanRecord | null; order: OrderRecord | null; machines: MachineRecord[]; canEdit: boolean }>()
const emit = defineEmits<{ close: []; confirmed: [] }>()
const machineId = ref('')
const preview = ref<ManualAppendPreviewRecord | null>(null)
const overrideReason = ref('')
const busy = ref(false)
const error = ref('')
const dialogRoot = ref<HTMLElement | null>(null)
const { announcement: dialogAnnouncement } = useDialogFocus(() => props.open, dialogRoot, {
  onEscape: () => emit('close'),
  openAnnouncement: '手工追加对话框已打开，按 Escape 关闭。',
})
const availableMachines = computed(() => props.machines.filter((item) => !['maintenance', 'offline'].includes(item.status)))
const setupMinutes = computed(() => Number(preview.value?.calculation.setup_minutes ?? 0))
const productionMinutes = computed(() => Number(preview.value?.calculation.production_minutes ?? 0))
const calendarDelay = computed(() => Number(preview.value?.calculation.calendar_delay_minutes ?? 0))
const appendTechnicalItems = computed(() => preview.value ? [
  { label: '资格原始结论', rawValue: preview.value.decision },
  { label: '计划 ID', rawValue: preview.value.planId },
  { label: '计划 revision', rawValue: String(preview.value.planRevision) },
  { label: '订单 ID', rawValue: preview.value.orderId },
  { label: '订单 revision', rawValue: String(preview.value.orderRevision) },
  { label: '规则 revision', rawValue: String(preview.value.ruleRevision) },
  { label: '输入指纹', rawValue: preview.value.inputFingerprint },
  { label: '接续锚点', rawValue: JSON.stringify(preview.value.continuationAnchor) },
  { label: '计算明细', rawValue: JSON.stringify(preview.value.calculation) },
  { label: '警告原始值', rawValue: JSON.stringify(preview.value.warnings) },
] : [])

watch(() => [props.open, props.order?.id] as const, ([open]) => {
  if (!open) return
  machineId.value = availableMachines.value[0]?.id ?? ''
  preview.value = null
  overrideReason.value = ''
  error.value = ''
})
async function createPreview() {
  if (!props.plan || !props.order || !machineId.value || busy.value) return
  busy.value = true; error.value = ''
  try { preview.value = await previewManualAppend(props.factoryId, props.plan, props.order, machineId.value) }
  catch (cause) { error.value = getApiErrorMessage(cause) }
  finally { busy.value = false }
}
async function confirm() {
  if (!props.plan || !props.order || !preview.value || preview.value.decision === 'FAIL' || busy.value) return
  if (preview.value.decision === 'REVIEW_REQUIRED' && !overrideReason.value.trim()) { error.value = '待复核候选必须填写覆盖原因'; return }
  busy.value = true; error.value = ''
  try {
    await confirmManualAppend(props.factoryId, props.plan, props.order, preview.value, overrideReason.value.trim())
    emit('confirmed')
    emit('close')
  } catch (cause) { error.value = getApiErrorMessage(cause) }
  finally { busy.value = false }
}
</script>

<template>
  <div v-if="open" ref="dialogRoot" class="manual-append-backdrop" tabindex="-1" @mousedown.self="emit('close')">
    <section role="dialog" aria-modal="true" aria-labelledby="manual-append-title">
      <p class="scheduling-sr-only dialog-live-announcement" role="status" aria-live="polite">{{ dialogAnnouncement }}</p>
      <header>
        <div><Clock3 :size="19" /><strong id="manual-append-title">追加到机台末尾</strong></div>
        <button aria-label="关闭" @click="emit('close')"><X :size="17" /></button>
      </header>
      <div class="append-body">
        <p v-if="!plan" class="notice"><AlertTriangle :size="15" />当前没有排产草案，不能追加；请先创建接续草案。</p>
        <p v-if="error" class="notice error"><AlertTriangle :size="15" />{{ error }}</p>
        <div v-if="order" class="order-copy"><strong>{{ order.orderNo }} · {{ order.productName }}</strong><span>全部可排欠数 {{ order.outstandingQuantity.toLocaleString('zh-CN') }}；首期不拆分多机台。</span></div>
        <label>目标机台<select v-model="machineId" :disabled="!canEdit || busy" @change="preview = null"><option v-for="machine in availableMachines" :key="machine.id" :value="machine.id">{{ machine.code }} · {{ machine.aClass ?? '—' }}A · {{ machine.injectionCapacityG ?? '—' }}g</option></select></label>
        <button class="primary" :disabled="!plan || !order || !machineId || !canEdit || busy" @click="createPreview">{{ busy ? '计算中' : '预览接续排产' }}</button>
        <div v-if="preview" class="append-preview">
          <div class="decision" :class="preview.decision.toLowerCase()"><CheckCircle2 v-if="preview.decision === 'PASS'" :size="16" /><AlertTriangle v-else :size="16" />{{ fitDecisionMeta(preview.decision).label }}</div>
          <dl><div><dt>计划数量</dt><dd>{{ preview.plannedQuantity }}</dd></div><div><dt>接续开始</dt><dd>{{ preview.plannedStart }}</dd></div><div><dt>预计完成</dt><dd>{{ preview.plannedFinish }}</dd></div><div><dt>换模准备</dt><dd>{{ setupMinutes }} 分钟</dd></div><div><dt>生产时长</dt><dd>{{ productionMinutes }} 分钟</dd></div><div><dt>日历延后</dt><dd>{{ calendarDelay }} 分钟</dd></div></dl>
          <p v-for="(warning, index) in preview.warnings" :key="index" class="warning">{{ warning.message || '存在需要关注的排产提示' }}</p>
          <SchedulingTechnicalDetails :items="appendTechnicalItems" summary="追加计算技术信息" />
          <label v-if="preview.decision === 'REVIEW_REQUIRED'">覆盖原因<textarea v-model="overrideReason" rows="2" /></label>
          <button class="primary" :disabled="preview.decision === 'FAIL' || busy" @click="confirm">确认写入排产草案</button>
        </div>
      </div>
    </section>
  </div>
</template>

<style scoped>
.manual-append-backdrop{position:fixed;inset:0;z-index:72;background:rgba(15,23,42,.55);display:grid;place-items:center}.manual-append-backdrop>section{width:min(620px,94vw);max-height:90vh;overflow:auto;background:#fff;border-radius:15px;box-shadow:0 24px 70px rgba(15,23,42,.35)}header{display:flex;justify-content:space-between;align-items:center;padding:16px 18px;border-bottom:1px solid #e2e8f0}header>div{display:flex;gap:8px;align-items:center}button,select,textarea{border:1px solid #cbd5e1;border-radius:8px;padding:8px;background:#fff}.append-body{display:grid;gap:12px;padding:18px}.append-body label,.order-copy{display:grid;gap:6px}.order-copy span{color:#64748b;font-size:12px}.notice{display:flex;gap:7px;padding:9px;background:#fff7ed;color:#9a3412;border-radius:8px}.notice.error{background:#fff1f2;color:#be123c}.primary{background:#0f766e;color:#fff;border-color:#0f766e}.primary:disabled{opacity:.5}.append-preview{display:grid;gap:10px;border-top:1px solid #e2e8f0;padding-top:12px}.decision{font-weight:700}.decision.pass{color:#15803d}.decision.review_required,.decision.fail{color:#b45309}.append-preview dl{display:grid;grid-template-columns:repeat(3,1fr);gap:8px;margin:0}.append-preview dl>div{background:#f8fafc;padding:8px;border-radius:8px}.append-preview dt{font-size:11px;color:#64748b}.append-preview dd{margin:3px 0 0;font-weight:600;font-size:12px}.warning{margin:0;padding:7px;background:#fff7ed;font-size:12px}
</style>
