<script setup lang="ts">
import { computed, onBeforeUnmount, ref, watch } from 'vue'
import { onBeforeRouteLeave, onBeforeRouteUpdate, useRoute } from 'vue-router'
import { DialogRoot, DialogPortal, DialogOverlay, DialogContent, DialogTitle, DialogDescription } from 'reka-ui'
import { Button } from '@/components/ui/button'
import { getApiErrorMessage } from '@/lib/http'
import type { PurchaseDetail } from '@/api/fabricProcurement'
import { fabricReceivingApi as api, materialCategoryLabels, type MaterialCategory, type ReceiveSourcesRequest, type ReceiveSourcesResult } from '@/api/fabricReceiving'
import { quantityText, receiptQuantity, receiptTotal } from './receiptQuantities'
import { warehouseRequestId } from './requestIdentity'
import WarehouseLocationPicker from './WarehouseLocationPicker.vue'

const props = defineProps<{ sources: PurchaseDetail[] }>()
const emit = defineEmits<{ close: []; saved: [result: ReceiveSourcesResult]; stale: [message: string] }>()
const today = new Intl.DateTimeFormat('sv-SE', { timeZone: 'Asia/Shanghai', year: 'numeric', month: '2-digit', day: '2-digit' }).format(new Date())
const receiptDate = ref(today), deliveryReference = ref(''), deliveryDate = ref(today), note = ref('')
const newRow = (key: number) => ({ key, quantity: '', location: '', location_id: '', dye_lot: '', roll_no: '' })
const entries = ref(props.sources.map(source => ({ source, category: (source.material_category ?? '') as MaterialCategory | '', reason: '', rows: [newRow(1)] })))
const busy = ref(false), error = ref(''), submitted = ref<ReceiveSourcesRequest>()
let nextKey = 2, alive = true, saved = false
const requestId = warehouseRequestId()
const progress = computed(() => entries.value.map(entry => {
  const total = receiptTotal(entry.rows.map(row => row.quantity))
  const remaining = entry.source.warehouse_outstanding_quantity ?? undefined
  const amount = receiptQuantity(total ?? ''), pending = receiptQuantity(remaining ?? '')
  const overage = amount !== undefined && pending !== undefined && amount > pending ? quantityText(amount - pending) : undefined
  return { total, remaining, overage }
}))
const splitCount = computed(() => entries.value.reduce((sum, entry) => sum + entry.rows.length, 0))
const valid = computed(() => entries.value.length > 0 && entries.value.length <= 50 && splitCount.value <= 500 &&
  receiptDate.value && receiptDate.value <= today && deliveryReference.value.trim() && entries.value.every((entry, index) =>
    entry.source.can_receive && entry.category && progress.value[index]?.total &&
    entry.rows.every(row => row.location_id && (entry.category !== 'FABRIC' || row.dye_lot.trim())) &&
    (!progress.value[index]?.overage || entry.reason.trim())))
const dirty = computed(() => deliveryReference.value || receiptDate.value !== today || deliveryDate.value !== today || note.value ||
  entries.value.some(entry => entry.category !== (entry.source.material_category ?? '') || entry.reason || entry.rows.some(row => row.quantity || row.location_id || row.location || row.dye_lot || row.roll_no)))
function allowLeave() {
  if (busy.value) return false
  return saved || !dirty.value || window.confirm(submitted.value ? '保存结果尚未确认，系统可能已入库。离开后请先查入库记录，避免重复登记。确定离开？' : '本次批量收料尚未保存，离开会清空填写内容。确定离开？')
}
function close() { if (allowLeave()) emit('close') }
onBeforeRouteLeave(allowLeave)
onBeforeRouteUpdate(allowLeave)
const route = useRoute()
watch(() => route.fullPath, () => emit('close'))
onBeforeUnmount(() => { alive = false })
function removeRow(index: number, key: number) {
  const entry = entries.value[index], row = entry?.rows.find(item => item.key === key)
  if (!entry || !row || entry.rows.length === 1) return
  if (Object.entries(row).some(([name, value]) => name !== 'key' && value) && !window.confirm('此项已填写，确定删除？')) return
  entry.rows = entry.rows.filter(item => item.key !== key)
}
async function save() {
  if (busy.value || (!submitted.value && !valid.value)) return
  if (!submitted.value) submitted.value = {
    factory_id: 'huakang-c', request_id: requestId, receipt_date: receiptDate.value,
    delivery_reference: deliveryReference.value.trim(), delivery_note_date: deliveryDate.value || null, note: note.value.trim(), confirmed: true,
    items: entries.value.map((entry, index) => ({ source_line_id: entry.source.id, expected_source_revision: entry.source.revision,
      expected_receipt_count: entry.source.receipt_count ?? 0, material_category: entry.category as MaterialCategory,
      difference_reason: progress.value[index]?.overage ? entry.reason.trim() : '',
      batches: entry.rows.map(row => ({ quantity: row.quantity, location_id: row.location_id, location: (entry.source.available_locations ?? []).find(bin => bin.id === row.location_id)?.label ?? '',
        dye_lot: entry.category === 'FABRIC' ? row.dye_lot : '', roll_no: entry.category === 'FABRIC' ? row.roll_no : '' })),
    })),
  }
  busy.value = true; error.value = ''
  try {
    const result = await api.receiveBatch(submitted.value)
    if (alive) { saved = true; emit('saved', result) }
  } catch (e) {
    if (!alive) return
    error.value = getApiErrorMessage(e)
    const status = (e as { response?: { status?: number } }).response?.status
    if ([401, 403, 404, 409].includes(status ?? 0)) { saved = true; emit('stale', error.value) }
    else if (status && status < 500 && status !== 408) submitted.value = undefined
  } finally { if (alive) busy.value = false }
}
</script>

<template>
  <DialogRoot :open="true" @update:open="value => { if (!value) close() }"><DialogPortal><DialogOverlay class="warehouse-guide-overlay" /><DialogContent class="fabric-receipt-dialog fabric-batch-receipt">
    <header class="fabric-intake-header"><div><span class="fabric-intake-eyebrow">布料仓 · 收料入库</span><DialogTitle>批量登记入库 · {{ sources.length }} 项物料</DialogTitle><DialogDescription>共用收货日期和收料依据，每项按实物填写。全部核对通过后一起入库。</DialogDescription></div><Button variant="outline" :disabled="busy" @click="close">关闭</Button></header>
    <form class="fabric-intake-form" @submit.prevent="save"><div class="fabric-intake-body"><fieldset :disabled="busy || !!submitted" class="fabric-receipt-fields">
      <div class="fabric-intake-document-fields"><label>收货日期<input v-model="receiptDate" type="date" aria-label="批量收货日期" :max="today" required /></label><label>送货单号 / 收料依据<input v-model="deliveryReference" aria-label="批量送货依据编号" placeholder="送货单号或本批手工收料编号" maxlength="128" required /></label></div>
      <section v-for="(entry, itemIndex) in entries" :key="entry.source.id" class="fabric-batch-item" :aria-label="`第${itemIndex + 1}项物料 ${entry.source.facts.order_no}`">
        <div class="fabric-batch-item-heading"><div><span class="fabric-intake-tag">{{ itemIndex + 1 }} · {{ entry.source.facts.source_category === 'SUPPLEMENT' ? '补数' : '正常采购' }}</span><h3>{{ entry.source.facts.material_name }}</h3><p>{{ entry.source.facts.order_no }} · {{ entry.source.facts.material_code }} · {{ entry.source.facts.supplier }}</p><p>剩余待收 {{ progress[itemIndex]?.remaining ?? '待核对' }} {{ entry.source.facts.unit }} · 本系统已入库 {{ entry.source.warehouse_received_quantity ?? '0' }} {{ entry.source.facts.unit }}</p></div><label>物料分类<select v-model="entry.category" :aria-label="`第${itemIndex + 1}项物料分类`" required><option value="" disabled>请选择</option><option v-for="(label, value) in materialCategoryLabels" :key="value" :value="value">{{ label }}</option></select></label></div>
        <p v-if="progress[itemIndex]?.remaining === undefined" class="fabric-intake-alert" role="note">起始数量待核对，本次可按实物入库。</p>

        <div class="fabric-intake-table-wrap"><table class="fabric-intake-table"><thead><tr><th class="fabric-intake-index">序号</th><th>本次实收（{{ entry.source.facts.unit }}）</th><th>仓位 *</th><th v-if="entry.category === 'FABRIC'">缸号 *</th><th v-if="entry.category === 'FABRIC'">卷号（选填）</th><th class="fabric-intake-remove"></th></tr></thead><tbody><tr v-for="(row, rowIndex) in entry.rows" :key="row.key"><td class="fabric-intake-index">{{ rowIndex + 1 }}</td><td data-label="本次实收"><input v-model="row.quantity" :aria-label="`物料${itemIndex + 1}明细${rowIndex + 1}实收数量`" inputmode="decimal" placeholder="填写数量" maxlength="32" required /></td><td data-label="仓位"><WarehouseLocationPicker v-model="row.location_id" :locations="entry.source.available_locations ?? []" :label="`物料${itemIndex + 1}明细${rowIndex + 1}仓位`" /></td><td v-if="entry.category === 'FABRIC'" data-label="缸号"><input v-model="row.dye_lot" :aria-label="`物料${itemIndex + 1}明细${rowIndex + 1}缸号`" placeholder="染色批次号" maxlength="128" required /></td><td v-if="entry.category === 'FABRIC'" data-label="卷号（选填）"><input v-model="row.roll_no" :aria-label="`物料${itemIndex + 1}明细${rowIndex + 1}卷号`" placeholder="单卷编号" maxlength="128" /></td><td class="fabric-intake-remove"><Button v-if="entry.rows.length > 1" type="button" variant="ghost" size="sm" :aria-label="`删除物料${itemIndex + 1}明细${rowIndex + 1}`" @click="removeRow(itemIndex, row.key)">删除</Button></td></tr></tbody></table></div>
        <div class="fabric-intake-totals"><Button type="button" variant="outline" size="sm" :disabled="entry.rows.length >= 200 || splitCount >= 500" @click="entry.rows.push(newRow(nextKey++))">＋ 增加明细</Button><strong>本项实收：{{ progress[itemIndex]?.total ?? '—' }} {{ entry.source.facts.unit }}</strong></div>
        <label v-if="progress[itemIndex]?.overage" class="fabric-receipt-overage">超出待收 {{ progress[itemIndex]?.overage }} {{ entry.source.facts.unit }} · 超收说明<textarea v-model="entry.reason" :aria-label="`第${itemIndex + 1}项超收说明`" maxlength="1000" rows="2" required /></label>
      </section>
      <details class="fabric-receipt-more"><summary>补充信息（选填）</summary><div class="fabric-intake-extra-fields"><label>送货单日期<input v-model="deliveryDate" type="date" aria-label="批量送货单日期" /></label><label>收料备注<textarea v-model="note" aria-label="批量收料备注" maxlength="2000" rows="2" /></label></div></details>
    </fieldset></div><footer class="fabric-intake-footer"><div class="fabric-intake-feedback"><p v-if="submitted && !busy" role="status">保存结果尚未确认。填写内容已锁定，重试会查询同一次入库结果。</p><p v-if="error" class="fabric-intake-error" role="alert">{{ error }}</p><span v-if="!error && !submitted">{{ sources.length }} 项物料 · {{ splitCount }} 项实物明细，保存后计入待检库存</span></div><div class="fabric-intake-actions"><Button type="button" variant="outline" :disabled="busy" @click="close">返回待收料</Button><Button type="submit" :disabled="busy || (!submitted && !valid)">{{ busy ? '正在保存…' : submitted ? '重试本次入库' : '保存全部并入库' }}</Button></div></footer></form>
  </DialogContent></DialogPortal></DialogRoot>
</template>
