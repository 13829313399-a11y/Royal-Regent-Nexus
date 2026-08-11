<script setup lang="ts">
import { AlertTriangle, LoaderCircle, RotateCcw, X } from '@lucide/vue'
import { computed, ref, watch } from 'vue'
import type { OrderRecord, ScheduleTaskRecord } from '../types'
import { useDialogFocus } from '../composables/useDialogFocus'
import { planStatusMeta } from '../presentation/schedulingLabels'
import SchedulingTechnicalDetails from './SchedulingTechnicalDetails.vue'

const props = defineProps<{
  open: boolean
  task: ScheduleTaskRecord | null
  order: OrderRecord | null
  planStatus: string
  canWithdraw: boolean
  disabledReason: string
  withdrawing: boolean
  error: string
}>()

const emit = defineEmits<{ close: []; confirm: [reason: string] }>()
const reason = ref('')
const canConfirm = computed(() => props.canWithdraw && reason.value.trim().length >= 2 && !props.withdrawing)
const withdrawTechnicalItems = computed(() => [
  { label: '计划原始状态', rawValue: props.planStatus || '—' },
  { label: '任务 ID', rawValue: props.task?.id || '—' },
  { label: '任务 revision', rawValue: String(props.task?.revision ?? '—') },
  { label: '订单 ID', rawValue: props.order?.id || '—' },
  { label: '订单 revision', rawValue: String(props.order?.revision ?? '—') },
])
const dialogRoot = ref<HTMLElement | null>(null)
function requestClose() {
  if (!props.withdrawing) emit('close')
}
const { announcement: dialogAnnouncement } = useDialogFocus(() => props.open, dialogRoot, {
  onEscape: requestClose,
  openAnnouncement: '撤回排产任务确认已打开，按 Escape 关闭。',
})

watch(() => props.open, (open) => {
  if (open) reason.value = ''
})
</script>

<template>
  <Teleport to="body">
    <div v-if="open" ref="dialogRoot" class="modal-backdrop" tabindex="-1" @mousedown.self="requestClose">
      <section class="phase2-dialog withdraw-task-dialog" role="dialog" aria-modal="true" aria-labelledby="withdraw-task-title">
        <p class="scheduling-sr-only dialog-live-announcement" role="status" aria-live="polite">{{ dialogAnnouncement }}</p>
        <header>
          <div><span class="eyebrow">计划调整 · {{ planStatusMeta(planStatus).label }}</span><strong id="withdraw-task-title">撤回订单到待排池</strong></div>
          <button type="button" aria-label="关闭撤回确认" :disabled="withdrawing" @click="requestClose"><X :size="17" /></button>
        </header>

        <div class="withdraw-task-body">
          <div class="withdraw-task-icon"><RotateCcw :size="22" /></div>
          <div class="withdraw-task-summary">
            <strong>{{ order?.orderNo || '所选订单' }} · {{ order?.productName || '排产任务' }}</strong>
            <p>将从排期表撤下该订单的排产行，未完成数量重新回到待排订单池。</p>
          </div>

          <div v-if="planStatus === 'PUBLISHED'" class="withdraw-task-notice">
            <AlertTriangle :size="16" />
            <span>当前是正式执行计划。系统会自动建立或复用调整草案，正式计划暂不改变；发布新草案后撤回才正式生效。</span>
          </div>
          <div v-else-if="planStatus === 'DRAFT'" class="withdraw-task-notice is-draft">
            <RotateCcw :size="16" />
            <span>当前是规划草案，确认后该订单会立即从草案排期中移除。</span>
          </div>
          <div v-else class="withdraw-task-notice">
            <AlertTriangle :size="16" />
            <span>当前计划状态待确认；系统仍会按服务端校验结果决定是否允许撤回。</span>
          </div>

          <SchedulingTechnicalDetails :items="withdrawTechnicalItems" summary="撤回技术信息" />

          <label class="withdraw-reason">
            <span>撤回原因 <em>必填</em></span>
            <textarea v-model="reason" rows="3" maxlength="500" placeholder="例如：订单暂停、物料未到、需要重新换机排期" :disabled="withdrawing"></textarea>
            <small>{{ reason.trim().length }}/500</small>
          </label>

          <p v-if="disabledReason" class="publish-plan-warning"><AlertTriangle :size="15" />{{ disabledReason }}</p>
          <p v-if="error" class="publish-plan-error"><AlertTriangle :size="15" />{{ error }}</p>
        </div>

        <footer>
          <button type="button" :disabled="withdrawing" @click="requestClose">取消</button>
          <button type="button" class="primary" :disabled="!canConfirm" @click="emit('confirm', reason.trim())">
            <LoaderCircle v-if="withdrawing" :size="15" class="spinning" />
            <RotateCcw v-else :size="15" />
            {{ withdrawing ? '正在撤回…' : '确认撤回待排' }}
          </button>
        </footer>
      </section>
    </div>
  </Teleport>
</template>
