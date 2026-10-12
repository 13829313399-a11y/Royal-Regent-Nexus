<script setup lang="ts">
import { onBeforeUnmount, ref } from 'vue'
import { onBeforeRouteLeave, onBeforeRouteUpdate } from 'vue-router'
import { isAxiosError } from 'axios'
import { DialogRoot, DialogPortal, DialogOverlay, DialogContent, DialogTitle, DialogDescription } from 'reka-ui'
import { Button } from '@/components/ui/button'
import { fabricReceivingApi as api, type FabricReceipt, type FabricReceiptReversalPreview, type FabricReceiptReversalRequest } from '@/api/fabricReceiving'
import { getApiErrorMessage } from '@/lib/http'
import { warehouseRequestId } from './requestIdentity'

const props = defineProps<{ record: FabricReceipt }>()
const emit = defineEmits<{ close: []; saved: [] }>()
const preview = ref<FabricReceiptReversalPreview>(), loading = ref(true), saving = ref(false), error = ref('')
const date = ref(new Intl.DateTimeFormat('sv-SE', { timeZone: 'Asia/Shanghai' }).format(new Date()))
const reason = ref(''), confirmed = ref(false), frozen = ref<FabricReceiptReversalRequest>()
let alive = true
function canLeave() { return !saving.value && !frozen.value && (!reason.value || window.confirm('冲销原因尚未提交，确定离开？')) }
function close() { if (canLeave()) emit('close') }
onBeforeRouteLeave(canLeave); onBeforeRouteUpdate(canLeave)
function beforeUnload(event: BeforeUnloadEvent) { if (saving.value || frozen.value || reason.value) { event.preventDefault(); event.returnValue = '' } }
window.addEventListener('beforeunload', beforeUnload)
onBeforeUnmount(() => { alive = false; window.removeEventListener('beforeunload', beforeUnload) })
async function load() {
  loading.value = true; error.value = ''; preview.value = undefined
  try { const result = await api.reversalPreview(props.record.id); if (alive) preview.value = result }
  catch (e) { if (alive) error.value = getApiErrorMessage(e) }
  finally { if (alive) loading.value = false }
}
void load()
async function submit() {
  if (!preview.value?.can_reverse || saving.value || (!frozen.value && (!confirmed.value || !reason.value.trim()))) return
  frozen.value ??= { factory_id: 'huakang-c', request_id: warehouseRequestId(), expected_revision: preview.value.expected_revision,
    business_date: date.value, reason: reason.value.trim(), confirmed: true }
  saving.value = true; error.value = ''
  try { await api.reverse(props.record.id, frozen.value); if (alive) { frozen.value = undefined; reason.value = ''; emit('saved') } }
  catch (e) {
    if (!alive) return
    const status = isAxiosError(e) ? e.response?.status : undefined
    error.value = getApiErrorMessage(e)
    if (status === undefined || status === 408 || status >= 500) error.value = '冲销结果待确认，内容已锁定。请用原内容重试，避免重复办理。'
    else { frozen.value = undefined; if (status === 401 || status === 403) preview.value = undefined; if (status === 409) { const message = error.value; await load(); error.value = message } }
  } finally { if (alive) saving.value = false }
}
</script>

<template>
  <DialogRoot :open="true" @update:open="value => { if (!value) close() }"><DialogPortal>
    <DialogOverlay class="warehouse-guide-overlay" />
    <DialogContent class="warehouse-guide fabric-edit-dialog" @escape-key-down="event => { event.preventDefault(); close() }" @interact-outside="event => { event.preventDefault(); close() }">
      <header class="warehouse-guide-heading"><div><DialogTitle>整单冲销入库</DialogTitle><DialogDescription>扣回这张入库单全部实收库存，恢复采购待收量。原单、价格和经办记录保留；已有后续收发时不能直接冲销。</DialogDescription></div><Button variant="ghost" :disabled="saving || !!frozen" @click="close">关闭</Button></header>
      <form class="warehouse-guide-body" @submit.prevent="submit">
        <p>{{ record.facts.order_no }} · {{ record.facts.material_name }} · 送货依据 {{ record.delivery_reference }}</p>
        <p>本次整单冲销：<strong>{{ record.quantity }} {{ record.unit }}</strong>，共 {{ record.batches.length }} 项实物。</p>
        <p v-if="loading" role="status">正在核对原批次和后续业务…</p>
        <p v-if="preview && !preview.can_reverse" class="fabric-error" role="alert">{{ preview.blocked_reason }}</p>
        <fieldset :disabled="loading || saving || !!frozen || !preview?.can_reverse" class="warehouse-operation-fields">
          <label>冲销日期<input v-model="date" type="date" required aria-label="入库冲销日期" /></label>
          <label class="full">冲销原因<textarea v-model="reason" required maxlength="1000" rows="3" aria-label="入库冲销原因" /></label>
          <label class="full"><span><input v-model="confirmed" type="checkbox" required aria-label="确认整单冲销入库" /> 已核对原单，确认整单冲销并保留记录</span></label>
        </fieldset>
        <p v-if="error" class="fabric-error" role="alert">{{ error }}</p>
        <div class="fabric-dialog-actions"><Button type="button" variant="outline" :disabled="saving || !!frozen" @click="close">返回</Button><Button type="submit" :disabled="loading || saving || !preview?.can_reverse || (!frozen && (!confirmed || !reason.trim()))">{{ saving ? '正在冲销…' : frozen ? '用原内容重试冲销' : '确认整单冲销' }}</Button></div>
      </form>
    </DialogContent>
  </DialogPortal></DialogRoot>
</template>

<style scoped>
form>p{margin-bottom:14px;font-size:13px}.warehouse-operation-fields{display:grid;gap:16px;border:0;padding:12px 0}.warehouse-operation-fields label{display:grid;gap:6px;font-size:13px}.warehouse-operation-fields input[type=date],textarea{padding:8px;border:1px solid #cbd5e1;border-radius:6px}.warehouse-operation-fields input[type=checkbox]{margin-right:6px}
</style>
