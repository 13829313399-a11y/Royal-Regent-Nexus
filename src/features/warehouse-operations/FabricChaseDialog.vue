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
function leave() { return !busy.value && (saved || (amount.value === initial && !evidence.value && !submitted.value) || window.confirm(submitted.value ? '保存结果尚未确认，请先查采购来源详情。确定离开？' : '原欠数量尚未保存，确定离开？')) }
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
  <DialogRoot :open="true" @update:open="value => { if (!value) close() }"><DialogPortal><DialogOverlay class="warehouse-guide-overlay" /><DialogContent class="warehouse-guide fabric-edit-dialog fabric-chase-dialog">
    <header class="warehouse-guide-heading"><div><DialogTitle>确认原欠数量</DialogTitle><DialogDescription>保存后重新计算采购剩余待收。库存保持原数。</DialogDescription></div><Button variant="outline" :disabled="busy" @click="close">关闭</Button></header>
    <form class="warehouse-guide-body fabric-master-form" @submit.prevent="save">
      <p><strong>{{ source.facts.order_no }} · {{ source.facts.material_name }}</strong><br />{{ source.facts.supplier }}</p>
      <fieldset :disabled="busy || !!submitted">
        <label>本系统首次入库前还欠多少（{{ source.facts.unit }}）
          <input v-model="amount" aria-label="本系统首次入库前还欠多少" inputmode="decimal" maxlength="32" required />
          <small>如果本系统已入库 10 {{ source.facts.unit }}、现在还欠 27 {{ source.facts.unit }}，这里填 37。</small>
        </label>
        <label>采购确认依据
          <textarea v-model="evidence" aria-label="采购确认依据" placeholder="填写原始欠料记录或与采购核对的结果" maxlength="2000" required />
        </label>
      </fieldset>
      <p class="fabric-chase-equation">{{ amount || '待填写' }} − {{ source.warehouse_received_quantity ?? '0' }} = <strong>{{ remaining }} {{ source.facts.unit }}</strong><small>原欠量 − 本系统已入库 = 保存后的剩余待收（最低为 0）</small></p>
      <p v-if="error" class="fabric-error" role="alert">{{ error }}</p>
      <div class="fabric-dialog-actions"><Button variant="outline" type="button" :disabled="busy" @click="close">返回采购详情</Button><Button type="submit" :disabled="busy || (!submitted && (receiptQuantity(amount) === undefined || !evidence.trim()))">{{ busy ? '正在保存…' : submitted ? '重试保存' : '保存原欠数量' }}</Button></div>
    </form>
  </DialogContent></DialogPortal></DialogRoot>
</template>

<style scoped>
.fabric-chase-dialog { height: fit-content; max-height: calc(100dvh - 40px); grid-template-rows: auto minmax(0, 1fr); }
.fabric-chase-dialog .warehouse-guide-heading { padding-block: 14px; }
.fabric-chase-dialog .warehouse-guide-body { gap: 14px; overscroll-behavior: contain; }
.fabric-chase-dialog .warehouse-guide-body p { margin-top: 0; }
.fabric-chase-dialog fieldset { grid-template-columns: minmax(0, 1fr); gap: 12px; }
@media (max-width: 700px) {
  .fabric-chase-dialog { width: 100%; height: 100dvh; max-height: none; border: 0; border-radius: 0; }
  .fabric-chase-dialog .fabric-dialog-actions { flex-wrap: wrap; }
}
</style>
