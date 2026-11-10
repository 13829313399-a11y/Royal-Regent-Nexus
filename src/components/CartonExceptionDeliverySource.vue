<script setup lang="ts">
import { computed, onBeforeUnmount, onMounted, ref } from 'vue'
import CartonOrderDetailDialog from './CartonOrderDetailDialog.vue'
import { cartonProcurementApi, type CartonExceptionResponse, type CartonImportBatchResponse } from '@/api/cartonProcurement'
import { getApiErrorMessage } from '@/lib/http'

const props = defineProps<{ exception: CartonExceptionResponse }>()
const emit = defineEmits<{ close: []; closeAutoFocus: [event: Event] }>()
const batch = ref<CartonImportBatchResponse | null>(null)
const busy = ref(false)
const error = ref('')
let active = true

const rows = computed(() => {
  const record = props.exception
  if (!record.contract_no && !record.item_no) return []
  return (batch.value?.parse_summary.rows ?? []).filter(row =>
    (!record.contract_no || (row.contract_no || row.reference) === record.contract_no)
    && (!record.item_no || row.item_no === record.item_no)
    && (!record.customer_code || row.customer_code === record.customer_code),
  )
})

async function load() {
  busy.value = true
  error.value = ''
  const { factory_id: factory, source_id: source } = props.exception
  try {
    const result = await cartonProcurementApi.importDetail(factory, source)
    if (!active) return
    if (result.id !== source || result.factory_id !== factory || result.import_type !== 'DELIVERY_NOTE') {
      throw new Error('返回的导入凭证与当前异常来源不符。')
    }
    batch.value = result
  } catch (cause) {
    if (active) error.value = getApiErrorMessage(cause)
  } finally {
    if (active) busy.value = false
  }
}

onMounted(() => { void load() })
onBeforeUnmount(() => { active = false })
</script>

<template>
  <CartonOrderDetailDialog title="原送货导入凭证" description="历史导入记录 · 只读" close-label="关闭原送货导入凭证" @close="emit('close')" @close-auto-focus="emit('closeAutoFocus', $event)">
    <p v-if="busy" role="status" class="text-sm text-slate-500">正在读取原导入批次…</p>
    <div v-else-if="error" role="alert" class="rounded-lg border border-red-200 bg-red-50 p-3 text-xs text-red-800">
      <p>{{ error }}</p>
      <button type="button" class="mt-2 font-semibold underline" @click="load">重试读取</button>
    </div>
    <template v-else-if="batch">
      <div class="space-y-1 break-words text-xs text-slate-600">
        <p class="text-sm font-semibold text-slate-900">{{ batch.original_filename }}</p>
        <p>导入批次 {{ batch.id }} · {{ batch.created_at.replace('T', ' ').slice(0, 16) }}</p>
        <p v-if="batch.parse_summary.document?.delivery_note_no">送货单 {{ batch.parse_summary.document.delivery_note_no }}</p>
      </div>
      <p v-if="rows.length > 1" class="text-xs text-slate-600">找到 {{ rows.length }} 条相符明细，请按原送货单和纸品逐条核实。</p>
      <ul v-if="rows.length" aria-label="相符的原导入明细" class="divide-y rounded-lg border text-xs">
        <li v-for="(row, index) in rows" :key="index" class="space-y-1 break-words p-3">
          <p class="font-semibold">{{ [row.delivery_note_no, row.contract_no || row.reference, row.item_no, row.packaging_type].filter(Boolean).join(' · ') }}</p>
          <p>{{ [row.source_sheet, row.source_row ? `第 ${row.source_row} 行` : '', row.delivered_quantity ?? row.quantity, row.unit, row.suggestion].filter(value => value !== undefined && value !== '').join(' · ') }}</p>
        </li>
      </ul>
      <p v-else class="text-xs text-slate-600">本批次保留导入凭证，当前异常缺少可定位的原始明细。</p>
      <p class="text-xs text-slate-600">实际验收或更正请到收料入库核对原送货单。</p>
    </template>
  </CartonOrderDetailDialog>
</template>
