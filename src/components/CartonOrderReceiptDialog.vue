<script setup lang="ts">
import { computed, onBeforeUnmount, ref, watch } from 'vue'
import { DialogRoot, DialogPortal, DialogOverlay, DialogContent, DialogTitle, DialogDescription } from 'reka-ui'
import { Button } from '@/components/ui/button'
import CartonSpecialManualReceipt from './CartonSpecialManualReceipt.vue'
import { cartonSpecialRequestsApi as api, type SpecialRequest } from '@/api/cartonSpecialRequests'
import type { CartonLocation } from '@/api/cartonPositions'
import { getApiErrorMessage } from '@/lib/http'

const props = defineProps<{ open: boolean; factoryId: string; requestId: string; viewerKey: string; libraryEnabled?: boolean }>()
const emit = defineEmits<{ 'update:open': [value: boolean]; saved: []; 'open-delivery': [number: string]; 'open-library': [requestId: string, lineId?: string] }>()
const request = ref<SpecialRequest | null>(null), locations = ref<CartonLocation[]>([])
const loading = ref(false), busy = ref(false), error = ref(''), locationError = ref('')
const pending = computed(() => request.value?.shipments.filter(row => row.lines.some(line => Number(line.remaining_quantity) > 0)) || [])
let generation = 0, controller = new AbortController()
watch(() => [props.factoryId, props.requestId, props.viewerKey, props.open], () => {
  generation++; controller.abort(); controller = new AbortController(); request.value = null; locations.value = []; busy.value = false; error.value = ''; locationError.value = ''; loading.value = false
  if (props.open && props.requestId) void load()
}, { immediate: true, flush: 'sync' })
onBeforeUnmount(() => { generation++; controller.abort() })
async function load() {
  const token = generation; loading.value = true; error.value = ''
  try {
    const [row, workspace] = await Promise.all([api.detail(props.factoryId, props.requestId, false, controller.signal), api.list(props.factoryId, false, controller.signal)])
    if (token !== generation) return
    request.value = row
    locations.value = (workspace.options?.locations || []).map(location => ({ ...location, factory_id: props.factoryId, warehouse: location.warehouse || '', bin_code: location.bin_code || '', status: 'ACTIVE' }))
  } catch (cause) { if (token === generation) error.value = getApiErrorMessage(cause) }
  finally { if (token === generation) loading.value = false }
}
function saved() { emit('saved'); emit('update:open', false) }
async function refreshLocations() {
  const token = generation; locationError.value = ''
  try {
    const workspace = await api.list(props.factoryId, false, controller.signal)
    if (token === generation) locations.value = (workspace.options?.locations || []).map(location => ({ ...location, factory_id: props.factoryId, warehouse: location.warehouse || '', bin_code: location.bin_code || '', status: 'ACTIVE' }))
  } catch (cause) { if (token === generation) locationError.value = getApiErrorMessage(cause) }
}
</script>

<template>
  <DialogRoot :open="open" @update:open="value => { if (!busy) emit('update:open', value) }"><DialogPortal>
    <DialogOverlay class="fixed inset-0 z-[70] bg-slate-950/40" />
    <DialogContent class="fixed left-1/2 top-1/2 z-[71] max-h-[88vh] w-[calc(100%-2rem)] max-w-5xl -translate-x-1/2 -translate-y-1/2 overflow-y-auto rounded-2xl border bg-white p-4 shadow-xl" @interact-outside.prevent @escape-key-down="event => { if (busy) event.preventDefault() }">
      <DialogTitle class="sr-only">登记收料</DialogTitle><DialogDescription class="sr-only">填写本次真实送货凭证、实收数量和仓位。</DialogDescription>
      <p v-if="loading" role="status" class="p-6 text-sm text-slate-500">正在读取收料表单…</p>
      <div v-else-if="error" class="space-y-3 p-4"><p role="alert" class="text-sm text-red-700">{{ error }}</p><Button variant="outline" @click="load">重试</Button><Button variant="outline" @click="emit('update:open', false)">返回</Button></div>
      <div v-else-if="pending.length" class="space-y-3 p-4"><h3 class="font-bold">已有待收送货单，请沿原单验收</h3><Button v-for="shipment in pending" :key="shipment.id" variant="outline" @click="emit('open-delivery', shipment.delivery_note_no)">{{ shipment.delivery_note_no }} · 前往验收</Button><Button variant="outline" @click="emit('update:open', false)">返回</Button></div>
      <template v-else-if="request">
        <CartonSpecialManualReceipt :request="request" :locations="locations" :viewer-key="viewerKey" @saved="saved" @busy="busy = $event" @cancel="emit('update:open', false)" @open-delivery="emit('open-delivery', $event)" @locations-changed="refreshLocations" />
        <p v-if="locationError" role="alert" class="mt-3 text-sm text-red-700">仓位刷新失败：{{ locationError }}<Button variant="link" @click="refreshLocations">重试</Button></p>
        <Button v-if="libraryEnabled && request.lines.some(line => !line.mark_ready && line.mark_mode !== 'NONE')" type="button" variant="link" :disabled="busy" @click="emit('open-library', request.id, request.lines.find(line => !line.mark_ready && line.mark_mode !== 'NONE')?.id)">箱唛资料库</Button>
      </template>
    </DialogContent>
  </DialogPortal></DialogRoot>
</template>
