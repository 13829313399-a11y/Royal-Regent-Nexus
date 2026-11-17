<script setup lang="ts">
import type { OrderReceipt } from './ordersApi'
import { orderHistoryTime } from './orderDisplay'

defineProps<{ receipt: OrderReceipt; recordVersion: number }>()
const labels = { automatic: '首次下发自动接单', manual: '裁床人工确认', note_only: '系统同步备注 · 沿用生产依据' }
</script>

<template>
  <div class="receipt-evidence">
    <p>{{ labels[receipt.mode] }} · 业务下发 V{{ receipt.source_version }} · 裁床记录 V{{ recordVersion }}</p>
    <p v-if="receipt.received_at">接收时间 <time :datetime="receipt.received_at">{{ orderHistoryTime(receipt.received_at) }}</time></p>
    <dl v-if="receipt.note_comparison" class="receipt-comparison">
      <div>
        <dt>原备注 · 业务下发 V{{ receipt.note_comparison.before_version }}</dt>
        <dd>{{ receipt.note_comparison.before.trim() ? receipt.note_comparison.before : '无备注' }}</dd>
      </div>
      <div>
        <dt>同步后备注 · 业务下发 V{{ receipt.source_version }}</dt>
        <dd>{{ receipt.note_comparison.after.trim() ? receipt.note_comparison.after : '无备注' }}</dd>
      </div>
    </dl>
    <p v-else-if="receipt.mode === 'note_only'">原下发快照不完整，暂无法显示备注对照。</p>
  </div>
</template>

<style scoped>
.receipt-evidence { margin-block: 4px 8px; min-width: 0; overflow-wrap: anywhere; }
.receipt-comparison { display: grid; grid-template-columns: repeat(auto-fit, minmax(min(100%, 220px), 1fr)); gap: 8px; margin-top: 6px; }
.receipt-comparison > div { min-width: 0; padding: 8px 10px; border: 1px solid var(--border); border-radius: 8px; }
.receipt-comparison dt { font-weight: 600; }
.receipt-comparison dd { margin: 2px 0 0; white-space: pre-wrap; }
</style>
