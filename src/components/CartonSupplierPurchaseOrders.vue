<script setup lang="ts">
import { computed, onBeforeUnmount, ref, watch } from 'vue'
import { cartonSupplierPortalApi as api, type SupplierDocument } from '@/api/cartonSupplierPortal'
import type { CartonPurchaseOrderContextResponse, CartonPurchaseOrderIssueResponse } from '@/api/cartonProcurement'
import CartonPurchaseOrderDialog from './CartonPurchaseOrderDialog.vue'
import { getApiErrorMessage } from '@/lib/http'
const props = defineProps<{ factoryId: string; orderNo: string }>()
const emit = defineEmits<{ close: [] }>()
const documents = ref<SupplierDocument[]>([]), loading = ref(false), error = ref(''), downloadingId = ref('')
let generation = 0
watch(() => [props.factoryId, props.orderNo], async () => {
  const token = ++generation; documents.value = []; loading.value = true; error.value = ''
  try { const rows = await api.documents(props.factoryId); if (token === generation) documents.value = rows.filter(row => row.kind === 'PURCHASE' && row.orders.some(order => order.order_no === props.orderNo)) }
  catch (cause) { if (token === generation) error.value = getApiErrorMessage(cause) }
  finally { if (token === generation) loading.value = false }
}, { immediate: true })
onBeforeUnmount(() => { generation++ })
const context = computed<CartonPurchaseOrderContextResponse>(() => ({ factory_id: props.factoryId, order_no: props.orderNo, order_revision: 0, pending_type: 'NONE', pending_product_quantity: null, pending_line_count: 0, can_generate: false, latest_document_no: documents.value[0]?.document_no || '', historical_baseline: false,
  issues: documents.value.map((doc, index) => ({ id: doc.id, factory_id: doc.factory_id, order_no: props.orderNo, document_no: doc.document_no, document_type: doc.document_type as CartonPurchaseOrderIssueResponse['document_type'], issue_sequence: index + 1, source_order_revision: 0, before_product_quantity: null, after_product_quantity: null, product_quantity_delta: null, generated_by: '', generated_by_name: '', generated_at: doc.created_at, is_cancellation: doc.is_cancellation, is_replenishment: doc.replenishment })) }))
async function download(issue: CartonPurchaseOrderIssueResponse) {
  const row = documents.value.find(doc => doc.id === issue.id)
  if (!row || downloadingId.value) return
  const token = generation; downloadingId.value = issue.id; error.value = ''
  try { await api.exportDocuments([row]) } catch (cause) { if (token === generation) error.value = getApiErrorMessage(cause) }
  finally { if (token === generation) downloadingId.value = '' }
}
</script>
<template><CartonPurchaseOrderDialog :order-no="orderNo" :context="context" :loading="loading" :error="error" :downloading-id="downloadingId" @close="emit('close')" @download="download" /></template>
