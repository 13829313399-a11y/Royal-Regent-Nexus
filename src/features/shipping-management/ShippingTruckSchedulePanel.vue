<script setup lang="ts">
import { ref } from 'vue'
import ShippingBulkTruckSheetPanel from './ShippingBulkTruckSheetPanel.vue'
import ShippingGeneratedDocs from './ShippingGeneratedDocs.vue'

defineProps<{ factoryId: string }>()
const emit = defineEmits<{ notify: [message: string]; back: [] }>()

const seedTaskId = ref('')
const seedHeader = ref<Record<string, unknown> | null>(null)

function importTruck(payload: { taskId: string; header: Record<string, unknown>; lines: Array<Record<string, unknown>> }) {
  const header = { ...payload.header }
  const line = payload.lines[0] || {}
  header.brandName = header.brandName || header.brandNote || line.brand || line.tradingHouse || ''
  header.contractNo = header.contractNo || line.contract || ''
  header.poNo = header.poNo || line.po || ''
  header.bookingNo = header.bookingNo || line.so || ''
  header.filingCode = header.filingCode || line.filingCode || ''
  header.sailingDate = header.sailingDate || header.sheetDate || ''
  seedTaskId.value = payload.taskId
  seedHeader.value = header
  emit('notify', '已导入盐田散货 W 车。')
}
</script>

<template>
  <section class="space-y-4" aria-label="车的出货单">
    <ShippingGeneratedDocs :factory-id="factoryId" module="truck" label="车的出货单" heading="邮件信息资料" @import-truck="importTruck" />

    <ShippingBulkTruckSheetPanel :factory-id="factoryId" :initial-task-id="seedTaskId" :initial-header="seedHeader" @notify="emit('notify', $event)" @back="emit('back')" />
  </section>
</template>
