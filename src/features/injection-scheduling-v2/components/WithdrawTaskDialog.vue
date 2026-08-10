<script setup lang="ts">
import { AlertTriangle, LoaderCircle, RotateCcw, X } from '@lucide/vue'
import { computed, ref, watch } from 'vue'
import type { OrderRecord, ScheduleTaskRecord } from '../types'

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

watch(() => props.open, (open) => {
  if (open) reason.value = ''
})
</script>

<template>
  <Teleport to="body">
    <div v-if="open" class="modal-backdrop" @mousedown.self="!withdrawing && emit('close')">
      <section class="phase2-dialog withdraw-task-dialog" role="dialog" aria-modal="true" aria-labelledby="withdraw-task-title">
        <header>
          <div><span class="eyebrow">计划调整</span><strong id="withdraw-task-title">撤回订单到待排池</strong></div>
          <button type="button" aria-label="关闭撤回确认" :disabled="withdrawing" @click="emit('close')"><X :size="17" /></button>
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
          <div v-else class="withdraw-task-notice is-draft">
            <RotateCcw :size="16" />
            <span>当前是规划草案，确认后该订单会立即从草案排期中移除。</span>
          </div>

          <label class="withdraw-reason">
            <span>撤回原因 <em>必填</em></span>
            <textarea v-model="reason" rows="3" maxlength="500" placeholder="例如：订单暂停、物料未到、需要重新换机排期" :disabled="withdrawing"></textarea>
            <small>{{ reason.trim().length }}/500</small>
          </label>

          <p v-if="disabledReason" class="publish-plan-warning"><AlertTriangle :size="15" />{{ disabledReason }}</p>
          <p v-if="error" class="publish-plan-error"><AlertTriangle :size="15" />{{ error }}</p>
        </div>

        <footer>
          <button type="button" :disabled="withdrawing" @click="emit('close')">取消</button>
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
