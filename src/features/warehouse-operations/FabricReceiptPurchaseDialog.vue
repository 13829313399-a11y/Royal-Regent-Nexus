<script setup lang="ts">
import { computed, onBeforeUnmount, ref } from 'vue'
import { onBeforeRouteLeave, onBeforeRouteUpdate } from 'vue-router'
import { isAxiosError } from 'axios'
import { DialogRoot, DialogPortal, DialogOverlay, DialogContent, DialogTitle, DialogDescription } from 'reka-ui'
import { Button } from '@/components/ui/button'
import { HANDOVER_FACTORY, handoverApi, type HandoverPurchaseLink, type HandoverPurchaseReview } from '@/api/materialHandover'
import { getApiErrorMessage } from '@/lib/http'
import { receiptQuantity, quantityText } from './receiptQuantities'
import { warehouseRequestId } from './requestIdentity'

const props = defineProps<{ operationId: string; material: string }>()
const emit = defineEmits<{ close: []; saved: [orderNo: string] }>()
const client = handoverApi()
const review = ref<HandoverPurchaseReview>(), sourceId = ref(''), differenceReason = ref('')
const loading = ref(false), saving = ref(false), error = ref('')
const frozen = ref<HandoverPurchaseLink>()
const choice = computed(() => review.value?.sources.find(source => source.id === sourceId.value))
const remainingAfter = computed(() => {
  const remainder = receiptQuantity(choice.value?.remaining ?? '')
  const received = receiptQuantity(review.value?.quantity ?? '')
  return remainder === undefined || received === undefined ? undefined : remainder - received
})
const overage = computed(() => remainingAfter.value !== undefined && remainingAfter.value < 0n)
const canSubmit = computed(() => !!choice.value?.can_receive && (!overage.value || !!differenceReason.value.trim()))
let alive = true

function canLeave() { return !saving.value && !frozen.value }
function close() { if (canLeave()) emit('close') }
function beforeUnload(event: BeforeUnloadEvent) {
  if (!canLeave()) { event.preventDefault(); event.returnValue = '' }
}
onBeforeRouteLeave(canLeave)
onBeforeRouteUpdate(canLeave)
window.addEventListener('beforeunload', beforeUnload)
onBeforeUnmount(() => {
  alive = false
  window.removeEventListener('beforeunload', beforeUnload)
})

async function load() {
  if (loading.value || frozen.value) return
  loading.value = true
  error.value = ''
  review.value = undefined
  sourceId.value = ''
  differenceReason.value = ''
  try {
    const result = await client.purchaseReview(props.operationId)
    if (alive) review.value = result
  } catch (e) {
    if (alive) error.value = getApiErrorMessage(e)
  } finally {
    if (alive) loading.value = false
  }
}
void load()

async function submit() {
  if (loading.value || saving.value) return
  if (!frozen.value) {
    const current = review.value, source = choice.value
    if (!current || !source || !canSubmit.value) return
    frozen.value = {
      factory_id: HANDOVER_FACTORY, request_id: warehouseRequestId(), expected_revision: current.expected_revision,
      operation_ids: [...current.operation_ids], purchase_source_id: source.id,
      expected_source_revision: source.revision, expected_receipt_count: source.receipt_count,
      difference_reason: overage.value ? differenceReason.value.trim() : '',
    }
  }
  saving.value = true
  error.value = ''
  try {
    const result = await client.linkPurchase(props.operationId, frozen.value)
    if (alive) { frozen.value = undefined; emit('saved', result.purchase_order_no) }
  } catch (e) {
    if (!alive) return
    const status = isAxiosError(e) ? e.response?.status : undefined
    if (status === undefined || status === 408 || status >= 500) {
      error.value = '补关联结果待确认，请用原内容重试。'
    } else {
      frozen.value = undefined
      const message = getApiErrorMessage(e)
      if (status === 409) await load()
      if (status === 401 || status === 403) review.value = undefined
      error.value = message
    }
  } finally {
    if (alive) saving.value = false
  }
}
</script>

<template>
  <DialogRoot :open="true" @update:open="value => { if (!value) close() }">
    <DialogPortal>
      <DialogOverlay class="warehouse-guide-overlay" />
      <DialogContent class="warehouse-guide fabric-edit-dialog" @escape-key-down="event => { event.preventDefault(); close() }" @interact-outside="event => { event.preventDefault(); close() }">
        <header class="warehouse-guide-heading">
          <div><DialogTitle>补关联采购</DialogTitle><DialogDescription>核对采购明细后，按本批已入库的有效数量核减待收。</DialogDescription></div>
          <Button variant="ghost" :disabled="!canLeave()" @click="close">关闭</Button>
        </header>
        <form class="warehouse-guide-body purchase-review" @submit.prevent="submit">
          <p v-if="loading" role="status">正在读取本批实收与采购候选…</p>
          <template v-if="review">
            <p><strong>{{ material }}</strong> · 送货依据 {{ review.reference }} · 本批净实收 {{ review.quantity }} {{ review.unit }}</p>
            <p v-if="review.locations.length">入库仓位 {{ review.locations.join(' / ') }}</p>
            <p>待核对原因 {{ review.reason }}</p>
            <p v-if="!review.sources.length" role="status">暂未找到同供应商、物料编码和单位的采购明细。采购资料补齐后可重新读取。</p>
            <fieldset v-else :disabled="saving || !!frozen">
              <label>对应采购明细
                <select v-model="sourceId" aria-label="选择补关联采购明细">
                  <option value="">请选择正确的采购明细</option>
                  <option v-for="source in review.sources" :key="source.id" :value="source.id" :disabled="!source.can_receive">
                    {{ [source.order_no, source.contract_no, source.production_no, source.id.slice(-8)].filter(Boolean).join(' · ') }}{{ source.primary_match ? ' · 原单编号相符' : '' }} · 尚欠 {{ source.remaining ?? '待核对' }} {{ source.unit }}{{ source.can_receive ? '' : ' · 须核对' }}
                  </option>
                </select>
              </label>
              <p v-if="choice">采购待收 {{ choice.remaining ?? '待核对' }} {{ choice.unit }}<template v-if="remainingAfter !== undefined"> → {{ quantityText(remainingAfter < 0n ? 0n : remainingAfter) }} {{ choice.unit }}</template></p>
              <label v-if="overage">超收说明<textarea v-model="differenceReason" required maxlength="1000" rows="2" /></label>
            </fieldset>
          </template>
          <p v-if="error" class="fabric-error" role="alert">{{ error }}</p>
          <div class="fabric-dialog-actions">
            <Button type="button" variant="outline" :disabled="!canLeave()" @click="close">返回</Button>
            <Button v-if="!loading && !saving && !frozen" type="button" variant="outline" @click="load">重新读取</Button>
            <Button type="submit" :disabled="loading || saving || (!frozen && !canSubmit)">{{ saving ? '正在补关联…' : frozen ? '用原内容重试' : '确认补关联采购' }}</Button>
          </div>
        </form>
      </DialogContent>
    </DialogPortal>
  </DialogRoot>
</template>

<style scoped>
.purchase-review { display: grid; gap: 12px; overflow-wrap: anywhere; }
.purchase-review fieldset, .purchase-review label { display: grid; gap: 8px; min-width: 0; }
.purchase-review select, .purchase-review textarea {
  width: 100%;
  min-width: 0;
  padding: 8px;
  border: 1px solid #cbd5e1;
  border-radius: 6px;
  background: white;
}
.purchase-review .fabric-dialog-actions { flex-wrap: wrap; }
</style>
