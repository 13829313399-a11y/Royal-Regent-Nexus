<script setup lang="ts">
import { computed, onBeforeUnmount, ref, watch } from 'vue'
import CartonReturnDateCorrection from './CartonReturnDateCorrection.vue'
import { cartonSupplierReturnsApi } from '@/api/cartonSupplierReturns'
import { supplierSettlementApi, type ReturnDateCorrection } from '@/api/cartonSupplierSettlement'
import type { SupplierReturn } from '@/api/cartonSupplierReturns'
import { createRandomUuid } from '@/lib/randomUuid'
import { getApiErrorMessage } from '@/lib/http'

const props = defineProps<{ factoryId: string; movementId: string; viewerKey?: string; disabled?: boolean }>()
const emit = defineEmits<{ saved: []; close: [] }>()
const source = ref<SupplierReturn | null>(null), loading = ref(false), busy = ref(false), error = ref('')
const verifying = computed(() => !!source.value?.allowed_actions.includes('VERIFY_DATE') && !source.value?.date_evidence?.return_date)
let generation = 0, controller = new AbortController()
const requests = new Map<string, string>()
watch(() => [props.factoryId, props.movementId, props.viewerKey], async () => {
  const token = ++generation
  controller.abort(); controller = new AbortController(); source.value = null; error.value = ''; busy.value = false
  requests.clear(); loading.value = true
  try {
    const row = await cartonSupplierReturnsApi.detail(props.movementId, props.factoryId, true, controller.signal)
    if (token !== generation) return
    if (row.factory_id !== props.factoryId || row.movement_id !== props.movementId) throw new Error('返回的退货凭证与当前厂区或原单不符。')
    if (row.allowed_actions.includes('VERIFY_DATE') && row.date_evidence?.date_basis === 'RETURN_POSTING' && !row.date_evidence.return_date) {
      source.value = row
      return
    }
    if (!row.can_correct_date && !row.allowed_actions.includes('CORRECT_DATE')) throw new Error('当前记录不可更正日期，请核对权限与退货状态。')
    if (!row.date_evidence?.return_date || row.date_evidence.date_basis !== 'RETURN_ACTUAL' || row.date_evidence.revision < 1) throw new Error('实际退货日期尚未核实，请先沿原日期补证入口核实。')
    source.value = row
  } catch (cause) { if (token === generation) error.value = getApiErrorMessage(cause) }
  finally { if (token === generation) loading.value = false }
}, { immediate: true, flush: 'sync' })
async function save(fields: { return_date: string; reason: string }) {
  const row = source.value, evidence = row?.date_evidence
  if (busy.value || props.disabled || !row || !evidence) return
  const token = generation
  busy.value = true; error.value = ''
  try {
    if (verifying.value) {
      await supplierSettlementApi.returnDate(row.movement_id, props.factoryId, row.posting_date, fields.return_date, fields.reason, controller.signal)
    } else {
      const identity = JSON.stringify([row.movement_id, evidence.revision, evidence.fingerprint, fields])
      const request = requests.get(identity) || createRandomUuid(); requests.set(identity, request)
      const body: ReturnDateCorrection = { factory_id: props.factoryId, request_id: request,
        expected_evidence_revision: evidence.revision, expected_evidence_fingerprint: evidence.fingerprint, ...fields }
      await supplierSettlementApi.correctReturnDate(row.movement_id, body, controller.signal)
      if (token === generation) requests.delete(identity)
    }
    if (token === generation) emit('saved')
  } catch (cause) { if (token === generation) error.value = getApiErrorMessage(cause) }
  finally { if (token === generation) busy.value = false }
}
onBeforeUnmount(() => { generation++; controller.abort() })
</script>

<template>
  <div class="space-y-3" :aria-label="verifying ? '实际退货日期核实' : '实际退货日期更正'">
    <p v-if="loading" role="status" class="rounded-xl border bg-card p-4 text-sm text-muted-foreground">正在核实最新日期版本…</p>
    <CartonReturnDateCorrection v-if="source?.date_evidence" :source="{ movementId: source.movement_id, documentNo: source.document_no, returnDate: source.date_evidence.return_date || '', postingDate: source.posting_date, revision: source.date_evidence.revision, fingerprint: source.date_evidence.fingerprint }" :busy="busy" :disabled="disabled" :error="error" @save="save" @cancel="emit('close')" />
    <div v-else-if="error" class="rounded-xl border border-red-200 bg-red-50 p-4 text-sm"><p role="alert" class="text-red-700">{{ error }}</p><button type="button" class="mt-3 rounded-lg border bg-white px-3 py-2" @click="emit('close')">返回</button></div>
  </div>
</template>
