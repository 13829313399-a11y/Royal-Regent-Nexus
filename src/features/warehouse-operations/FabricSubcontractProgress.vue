<script setup lang="ts">
import { computed } from 'vue'
import { Progress } from '@/components/ui/progress'
import type { Output, SubOrder } from '@/api/fabricSubcontract'
import { remaining } from './operations'

const props = defineProps<{ order: SubOrder; output: Output }>()
const receivedPercent = computed(() => percentage(props.output.received))
const hasPendingCount = computed(() => Number(props.output.uncounted) > 0)
const complete = computed(() => Number(props.output.outstanding) === 0)
const percentLabel = computed(() => {
  if (complete.value) return '100%'
  if (receivedPercent.value > 99) return '>99%'
  if (receivedPercent.value > 0 && receivedPercent.value < 1) return '<1%'
  return Math.round(receivedPercent.value) + '%'
})
const stage = computed(() => {
  const { order, output } = props
  if (complete.value) return '已收齐'
  if (hasPendingCount.value) return '到货待点收'
  if (Number(output.received) > 0) return '部分回仓'
  if (order.outputs.some(line => Number(line.delivered) > 0)) return '待厂送回'
  if (!order.inputs.length) return '待选原料'
  if (order.inputs.every(line => Number(line.sent) === 0)) return '已选料，待发出'
  if (order.inputs.some(line => Number(remaining(line.planned, line.sent)) > 0)) return '原料部分发出'
  const shipments = order.events.filter(event => event.kind === 'SEND' && !event.voided)
  if (shipments.length && shipments.every(event => Number(event.remaining) === 0)) return '厂已签收，待送回'
  return '已发料，待厂送回'
})
const hasIssue = computed(() => props.order.events.some(event =>
  event.kind === 'ISSUE' && !event.voided && event.output_id === props.output.id))

function percentage(quantity: string) {
  const planned = Number(props.output.planned)
  return planned > 0 ? Math.min(100, Math.max(0, Number(quantity) / planned * 100)) : 0
}
</script>

<template>
  <div class="sub-progress">
    <small v-if="order.outputs.length > 1">{{ output.item_code }} · {{ output.item_name }}</small>
    <div class="sub-progress-heading">
      <strong>{{ stage }}<template v-if="hasIssue"> · 已有领用</template></strong>
      <span>已收 {{ percentLabel }}</span>
    </div>
    <Progress class="sub-progress-track h-1.5" indicator-class="transition-none"
      :model-value="receivedPercent" :aria-label="output.item_name + '回仓进度'"
      :aria-valuetext="`已收 ${output.received} ${output.unit}，应回 ${output.planned} ${output.unit}，待点收 ${output.uncounted} ${output.unit}，厂欠 ${output.undelivered} ${output.unit}`"
      :style="hasPendingCount ? { '--delivered': percentage(output.delivered) + '%' } : undefined"
      :class="{ 'sub-progress-pending': hasPendingCount }" />
    <div class="sub-progress-amounts">
      <span>已收 {{ output.received }} {{ output.unit }}</span>
      <span v-if="hasPendingCount" class="sub-pending-count">待点收 {{ output.uncounted }} {{ output.unit }}</span>
      <span v-if="Number(output.undelivered) > 0">厂欠 {{ output.undelivered }} {{ output.unit }}</span>
    </div>
  </div>
</template>
