<script setup lang="ts">
import { computed, onBeforeUnmount, ref } from 'vue'
import { onBeforeRouteLeave, onBeforeRouteUpdate } from 'vue-router'
import { DialogRoot, DialogPortal, DialogOverlay, DialogContent, DialogTitle, DialogDescription } from 'reka-ui'
import { Button } from '@/components/ui/button'
import { fabricProcurementApi as api, type PurchaseDetail } from '@/api/fabricProcurement'
import { getApiErrorMessage } from '@/lib/http'
import { receiptQuantity, quantityText } from './receiptQuantities'
import { warehouseRequestId } from './requestIdentity'
const props = defineProps<{ source: PurchaseDetail }>()
const emit = defineEmits<{ close: []; saved: []; stale: [message: string] }>()
const amount = ref(props.source.starting_chase_quantity ?? ''), evidence = ref(''), busy = ref(false), error = ref('')
const initial = amount.value
type Payload = Parameters<typeof api.resolveChase>[1]
const submitted = ref<Payload>(), requestId = warehouseRequestId()
let alive = true, saved = false
const received = computed(() => receiptQuantity(props.source.warehouse_received_quantity ?? '0') ?? 0n)
const remaining = computed(() => { const start = receiptQuantity(amount.value); return start === undefined ? '待填写' : quantityText(start > received.value ? start - received.value : 0n) })
function leave() { return !busy.value && (saved || (amount.value === initial && !evidence.value && !submitted.value) || window.confirm(submitted.value ? '核对保存结果尚未确认，请先查来源详情再重复办理。确定离开？' : '起始待收核对尚未保存，确定离开？')) }
function close() { if (leave()) emit('close') }
onBeforeRouteLeave(leave); onBeforeRouteUpdate(leave); onBeforeUnmount(() => { alive = false })
async function save() {
  if (busy.value || (!submitted.value && (receiptQuantity(amount.value) === undefined || !evidence.value.trim()))) return
  submitted.value ??= { request_id: requestId, expected_source_revision: props.source.revision, expected_receipt_count: props.source.receipt_count ?? 0,
    expected_resolution_revision: props.source.chase_resolution?.revision ?? 0, starting_quantity: amount.value, evidence: evidence.value.trim(), confirmed_start: true }
  busy.value = true; error.value = ''
  try { await api.resolveChase(props.source.id, submitted.value); if (alive) { saved = true; emit('saved') } }
  catch (e) { if (!alive) return; error.value = getApiErrorMessage(e); const status = (e as { response?: { status?: number } }).response?.status
    if ([401,403,404,409].includes(status ?? 0)) { saved = true; emit('stale', error.value) }
    else if (status && status < 500 && status !== 408) submitted.value = undefined
  } finally { if (alive) busy.value = false }
}
</script>
<template>
  <DialogRoot :open="true" @update:open="value => { if (!value) close() }"><DialogPortal><DialogOverlay class="warehouse-guide-overlay" /><DialogContent class="warehouse-guide fabric-edit-dialog">
    <header class="warehouse-guide-heading"><div><DialogTitle>核对起始待收量</DialogTitle><DialogDescription>确认本系统首次入库之前还要追多少货；库存不会改变。</DialogDescription></div><Button variant="outline" :disabled="busy" @click="close">关闭</Button></header>
    <form class="warehouse-guide-body fabric-master-form" @submit.prevent="save">
      <p><strong>{{ source.facts.order_no }} · {{ source.facts.material_name }}</strong><br />{{ source.facts.supplier }} · 原单位 {{ source.facts.unit }}</p>
      <p class="fabric-intake-alert">请填起始数量，包含本系统已经登记的实收。例如已入库 10、现在欠 27，起始待收填 37。确认起始待收为 0 表示已核对无需继续追货。</p>
      <fieldset :disabled="busy || !!submitted"><label>起始待收数量 · {{ source.facts.unit }}<input v-model="amount" aria-label="起始待收数量" inputmode="decimal" maxlength="32" required /></label><label>核对依据<textarea v-model="evidence" aria-label="起始待收核对依据" placeholder="原始欠料记录、与采购核对的结果等" maxlength="2000" required /></label></fieldset>
      <p class="fabric-chase-equation">{{ amount || '待填写' }} − {{ source.warehouse_received_quantity ?? '0' }} = <strong>{{ remaining }} {{ source.facts.unit }}</strong><small>起始待收 − 本系统已入库 = 剩余待收（最低为 0）</small></p>
      <p v-if="error" class="fabric-error" role="alert">{{ error }}</p>
      <div class="fabric-dialog-actions"><Button variant="outline" type="button" :disabled="busy" @click="close">返回</Button><Button type="submit" :disabled="busy || (!submitted && (receiptQuantity(amount) === undefined || !evidence.trim()))">{{ busy ? '正在保存…' : submitted ? '重试确认' : '确认起始待收（库存不变）' }}</Button></div>
    </form>
  </DialogContent></DialogPortal></DialogRoot>
</template>
