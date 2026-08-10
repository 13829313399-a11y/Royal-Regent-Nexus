<script setup lang="ts">
import { AlertTriangle, LoaderCircle, Trash2, X } from '@lucide/vue'
import { computed, ref, watch } from 'vue'
import type { OrderRecord } from '../types'

const props = defineProps<{
  open: boolean
  order: OrderRecord | null
  canCancel: boolean
  cancelling: boolean
  error: string
}>()

const emit = defineEmits<{ close: []; confirm: [reason: string] }>()
const reason = ref('')
const canConfirm = computed(() => props.canCancel && reason.value.trim().length >= 2 && !props.cancelling)

watch(() => props.open, (open) => {
  if (open) reason.value = ''
})
</script>

<template>
  <Teleport to="body">
    <div v-if="open" class="modal-backdrop" @mousedown.self="!cancelling && emit('close')">
      <section class="phase2-dialog backlog-cancel-dialog" role="dialog" aria-modal="true" aria-labelledby="backlog-cancel-title">
        <header>
          <div><span class="eyebrow">待排管理</span><strong id="backlog-cancel-title">删除待排单</strong></div>
          <button type="button" aria-label="关闭删除确认" :disabled="cancelling" @click="emit('close')"><X :size="17" /></button>
        </header>

        <div class="backlog-cancel-body">
          <div class="backlog-cancel-icon"><Trash2 :size="22" /></div>
          <div class="backlog-cancel-summary">
            <strong>{{ order?.orderNo || '所选待排单' }} · {{ order?.productName || '排期需求' }}</strong>
            <p>确认后该订单将从待排池移除，不再参与自动排期或手工追加。</p>
          </div>

          <div class="backlog-cancel-notice">
            <AlertTriangle :size="16" />
            <span>这是可追溯的业务取消：原下单表、订单版本和操作记录会保留，不会直接删除历史数据。</span>
          </div>

          <label class="withdraw-reason">
            <span>删除原因 <em>必填</em></span>
            <textarea v-model="reason" rows="3" maxlength="500" placeholder="例如：订单作废、重复下单、暂不生产" :disabled="cancelling"></textarea>
            <small>{{ reason.trim().length }}/500</small>
          </label>

          <p v-if="error" class="publish-plan-error"><AlertTriangle :size="15" />{{ error }}</p>
        </div>

        <footer>
          <button type="button" :disabled="cancelling" @click="emit('close')">取消</button>
          <button type="button" class="danger" :disabled="!canConfirm" @click="emit('confirm', reason.trim())">
            <LoaderCircle v-if="cancelling" :size="15" class="spinning" />
            <Trash2 v-else :size="15" />
            {{ cancelling ? '正在删除…' : '确认删除待排单' }}
          </button>
        </footer>
      </section>
    </div>
  </Teleport>
</template>
