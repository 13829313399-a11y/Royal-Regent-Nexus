<script setup lang="ts">
import { computed, ref, watch } from 'vue'
import WarehouseProgressTable from '@/features/warehouse-foundation/WarehouseProgressTable.vue'
import { Button } from '@/components/ui/button'
import StatusPill from '@/components/common/StatusPill.vue'
import type { SemiOrderProgress, SemiProgressItem, WarehouseDocument } from '@/api/warehouseOperations'

const props = defineProps<{
  progress: SemiOrderProgress[]
  releases: WarehouseDocument[]
  canOperate: boolean
  busy: boolean
  pendingOnly?: boolean
  extraInitially?: boolean
}>()
defineEmits<{ open: [id: string, event: MouseEvent] }>()

const receiptStatus = ref('')
watch(() => props.extraInitially, extra => { receiptStatus.value = extra ? 'extra' : '' }, { immediate: true })
const columns = [
  { key: 'release', label: '生产单 / 放产明细' },
  { key: 'receipt', label: '计划与实收', numeric: true },
  { key: 'stock', label: '仓内结余', numeric: true },
  { key: 'processing', label: '加工在外', numeric: true },
  { key: 'packaging', label: '包装交接', numeric: true },
  { key: 'actions', label: '操作' },
]
const rows = computed(() => {
  const releases = new Map(props.releases.map(row => [row.id, row]))
  return props.progress.flatMap(progress => {
    const release = releases.get(progress.release_id)
    if (!release) return []
    if ((props.pendingOnly || receiptStatus.value === 'pending') && Number(progress.pending_receipt) === 0) return []
    if (!props.pendingOnly && receiptStatus.value === 'extra' && Number(progress.extra_received) === 0) return []
    return [{ ...progress, id: release.id, release }]
  })
})
function searchText({ release }: { release: WarehouseDocument }) {
  const { production_no, item_code, item_name, part, label_code, source_no, source_line, process_state } = release.data
  return [production_no, item_code, item_name, part, label_code, source_no, source_line, process_state].join(' ')
}
function itemKey(item: SemiProgressItem) {
  return JSON.stringify([item.item_code, item.process_state, item.unit])
}
</script>

<template>
  <WarehouseProgressTable :rows="rows" :columns="columns" :label="pendingOnly ? '待收货' : '订单进度'" :search-text="searchText"
    search-placeholder="生产单号、产品、部位或布标" :empty-title="pendingOnly ? '暂无待收明细' : '暂无放产明细'" :filtered="!pendingOnly && !!receiptStatus"
    :empty-description="pendingOnly ? '已登记且仍有待收量的放产明细会显示在这里。' : canOperate ? '核对已有放产单后，登记要跟进的产品明细。' : '仓库登记放产明细后，进度将在这里显示。'">
    <template #filters>
      <label v-if="!pendingOnly" class="semi-progress-filter">实收进度
        <select v-model="receiptStatus" aria-label="实收进度筛选">
          <option value="">全部明细</option>
          <option value="pending">有待收数</option>
          <option value="extra">实收超计划</option>
        </select>
      </label>
    </template>
    <template #cell="{ row, column }">
      <div v-if="column === 'release'" class="semi-progress-source">
        <strong>{{ row.release.data.production_no }}</strong>
        <span>{{ row.release.data.item_code }} · {{ row.release.data.item_name }}</span>
        <span>{{ row.release.data.part }}<template v-if="row.release.data.label_code"> · 布标 {{ row.release.data.label_code }}</template></span>
        <small>{{ row.release.data.source_no }} / {{ row.release.data.source_line }}<template v-if="row.release.data.due_date"> · 应收 {{ row.release.data.due_date }}</template></small>
      </div>
      <div v-else-if="column === 'receipt'" class="semi-progress-readout">
        <div>实收 <strong>{{ row.received }} {{ row.release.data.unit }}</strong></div>
        <small>计划 {{ row.release.data.quantity }} {{ row.release.data.unit }}</small>
        <StatusPill v-if="Number(row.pending_receipt) > 0" :label="`待收 ${row.pending_receipt} ${row.release.data.unit}`" tone="amber" compact />
        <StatusPill v-else-if="Number(row.extra_received) > 0" :label="`超收 ${row.extra_received} ${row.release.data.unit}`" tone="blue" compact />
        <StatusPill v-else label="已收齐" tone="teal" compact />
      </div>
      <template v-else-if="column === 'stock' || column === 'processing'">
        <ul v-if="row[column].length" class="semi-progress-readout">
          <li v-for="item in row[column]" :key="itemKey(item)">
            <strong>{{ item.quantity }} {{ item.unit }}</strong>
            <small>{{ item.item_code }} · {{ item.process_state }}</small>
          </li>
        </ul>
        <span v-else class="text-muted-foreground">—</span>
      </template>
      <template v-else-if="column === 'packaging'">
        <ul v-if="row.packaging.length" class="semi-progress-readout">
          <li v-for="item in row.packaging" :key="itemKey(item)">
            <div>已收 <strong>{{ item.received }} {{ item.unit }}</strong></div>
            <small>已发 {{ item.sent }} · 待签 {{ item.pending }}<template v-if="Number(item.returned) > 0"> · 退回 {{ item.returned }}</template> {{ item.unit }}</small>
            <small>{{ item.item_code }} · {{ item.process_state }}</small>
          </li>
        </ul>
        <span v-else class="text-muted-foreground">—</span>
      </template>
      <Button v-else variant="outline" size="sm" :disabled="busy" @click="$emit('open', row.id, $event)">查看进度</Button>
    </template>
  </WarehouseProgressTable>
</template>

<style scoped>
.semi-progress-filter { display: grid; gap: 6px; font-size: 12px; color: var(--muted-foreground); }
.semi-progress-source, .semi-progress-readout { display: grid; gap: 4px; line-height: 1.5; }
.semi-progress-source strong { font-size: 14px; font-weight: 650; }
.semi-progress-readout strong { font-size: 13px; font-weight: 650; }
.semi-progress-source small, .semi-progress-readout small { display: block; font-size: 12px; color: var(--muted-foreground); }
.semi-progress-readout > span { justify-self: end; margin-top: 3px; }
.semi-progress-readout > li + li { padding-top: 5px; border-top: 1px solid var(--border); }
@media (max-width: 639px) {
  .semi-progress-readout > span { justify-self: start; }
  .semi-progress-filter { width: 100%; }
}
</style>
