<script setup lang="ts">
import { onBeforeUnmount, ref, watch } from 'vue'
import CartonPurchaseOrderDialog from './CartonPurchaseOrderDialog.vue'
import { cartonSpecialRequestsApi as api } from '@/api/cartonSpecialRequests'
import type { CartonPurchaseOrderContextResponse, CartonPurchaseOrderIssueResponse } from '@/api/cartonProcurement'
import { getApiErrorMessage } from '@/lib/http'
const props = defineProps<{ factoryId: string; requestId: string; orderNo: string; supplier?: boolean }>()
const emit = defineEmits<{ close: [] }>()
const context = ref<CartonPurchaseOrderContextResponse | null>(null), loading = ref(false), error = ref(''), downloadingId = ref('')
let generation = 0, controller = new AbortController()
watch(() => [props.factoryId, props.requestId, props.supplier], async () => {
  controller.abort(); controller = new AbortController(); const token = ++generation
  context.value = null; error.value = ''; loading.value = true; downloadingId.value = ''
  try { const value = await api.purchaseContext(props.factoryId, props.requestId, props.supplier, controller.signal); if (token === generation) context.value = value }
  catch (cause) { if (token === generation) error.value = getApiErrorMessage(cause) }
  finally { if (token === generation) loading.value = false }
}, { immediate: true })
onBeforeUnmount(() => { generation++; controller.abort() })
async function download(issue: CartonPurchaseOrderIssueResponse) {
  if (downloadingId.value) return
  const token = generation; downloadingId.value = issue.id; error.value = ''
  try {
    const blob = await api.purchaseExport(props.factoryId, props.requestId, issue.id, props.supplier, controller.signal)
    if (token !== generation) return
    const url = URL.createObjectURL(blob), a = document.createElement('a'); a.href = url; a.download = issue.document_no + '.xlsx'; a.click(); setTimeout(() => URL.revokeObjectURL(url), 1000)
  } catch (cause) { if (token === generation) error.value = getApiErrorMessage(cause) }
  finally { if (token === generation) downloadingId.value = '' }
}
</script>
<template><CartonPurchaseOrderDialog :order-no="orderNo" :context="context" :loading="loading" :error="error" :downloading-id="downloadingId" @close="emit('close')" @download="download" /></template>
