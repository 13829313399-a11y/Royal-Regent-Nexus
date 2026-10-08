<script setup lang="ts">
import { computed, onBeforeUnmount, ref, watch } from 'vue'
import { onBeforeRouteLeave, onBeforeRouteUpdate, useRoute } from 'vue-router'
import { DialogRoot, DialogPortal, DialogOverlay, DialogContent, DialogTitle, DialogDescription } from 'reka-ui'
import { Button } from '@/components/ui/button'
import { getApiErrorMessage } from '@/lib/http'
import type { PurchaseDetail } from '@/api/fabricProcurement'
import { fabricReceivingApi as api, materialCategoryLabels, type MaterialCategory, type ReceiveRequest, type FabricReceipt } from '@/api/fabricReceiving'
import { quantityText, receiptQuantity, receiptTotal } from './receiptQuantities'
import { warehouseRequestId } from './requestIdentity'

const props = defineProps<{ source: PurchaseDetail }>()
const emit = defineEmits<{ close: []; saved: [receipt: FabricReceipt]; stale: [message: string] }>()
const today = new Intl.DateTimeFormat('sv-SE', { timeZone: 'Asia/Shanghai', year: 'numeric', month: '2-digit', day: '2-digit' }).format(new Date())
const receiptDate = ref(today), deliveryReference = ref(''), deliveryDate = ref(today)
const initialCategory = props.source.material_category ?? ''
const category = ref<MaterialCategory | ''>(initialCategory)
const reason = ref(''), note = ref(''), busy = ref(false), error = ref('')
const rows = ref([{ key: 1, quantity: '', location: '', dye_lot: '', roll_no: '' }])
let nextKey = 2, alive = true, saved = false
const requestId = warehouseRequestId()
const submitted = ref<ReceiveRequest>()
const total = computed(() => receiptTotal(rows.value.map(row => row.quantity)))
const ordered = computed(() => receiptQuantity(props.source.facts.ordered_quantity))
const prior = computed(() => receiptQuantity(props.source.prior_received_quantity ?? ''))
const remaining = computed(() => {
  if (props.source.receipt_quantity_review_required || props.source.receipt_reconciliation_required) return undefined
  if (props.source.warehouse_outstanding_quantity != null) return props.source.warehouse_outstanding_quantity
  const recorded = receiptQuantity(props.source.warehouse_received_quantity ?? '0')
  if (prior.value === undefined || ordered.value === undefined || recorded === undefined || prior.value > ordered.value) return undefined
  const amount = ordered.value - prior.value - recorded
  return quantityText(amount > 0n ? amount : 0n)
})
const overage = computed(() => {
  const current = receiptQuantity(total.value ?? ''), pending = receiptQuantity(remaining.value ?? '')
  if (pending === undefined || current === undefined) return undefined
  const extra = current - pending
  return extra > 0n ? quantityText(extra) : undefined
})
const valid = computed(() => props.source.can_receive && total.value && rows.value.every(row => row.location.trim() && (category.value !== 'FABRIC' || row.dye_lot.trim())) && (!overage.value || reason.value.trim()) && category.value && deliveryReference.value.trim() && receiptDate.value && receiptDate.value <= today)
const dirty = computed(() => rows.value.some(row => row.quantity || row.location || row.dye_lot || row.roll_no) || deliveryReference.value || deliveryDate.value !== today || receiptDate.value !== today || category.value !== initialCategory || reason.value || note.value)
function allowLeave() {
  if (busy.value) return false
  return saved || !dirty.value || window.confirm(submitted.value ? '保存结果尚未确认，系统可能已入库。离开后请先查入库记录，避免重复登记。确定离开？' : '本次收料尚未保存，离开会清空填写内容。确定离开？')
}
function close() { if (allowLeave()) emit('close') }
onBeforeRouteLeave(allowLeave)
onBeforeRouteUpdate(allowLeave)
const route = useRoute()
watch(() => route.fullPath, () => emit('close'))
onBeforeUnmount(() => { alive = false })
function removeRow(key: number) {
  const row = rows.value.find(item => item.key === key)
  if (!row || rows.value.length === 1) return
  if (Object.entries(row).some(([name, value]) => name !== 'key' && value) && !window.confirm('此项已填写，确定删除？')) return
  rows.value = rows.value.filter(item => item.key !== key)
}
async function save() {
  if (busy.value || (!submitted.value && !valid.value)) return
  if (!submitted.value) submitted.value = {
    factory_id: 'huakang-c', request_id: requestId, expected_source_revision: props.source.revision, expected_receipt_count: props.source.receipt_count ?? 0,
    receipt_date: receiptDate.value, delivery_reference: deliveryReference.value.trim(), delivery_note_date: deliveryDate.value || null,
    material_category: category.value as MaterialCategory, difference_reason: overage.value ? reason.value.trim() : '', note: note.value.trim(),
    batches: rows.value.map(row => ({ quantity: row.quantity, location: row.location, dye_lot: category.value === 'FABRIC' ? row.dye_lot : '', roll_no: category.value === 'FABRIC' ? row.roll_no : '' })), confirmed: true,
  }
  busy.value = true; error.value = ''
  try {
    const result = await api.receive(props.source.id, submitted.value)
    if (!alive) return
    saved = true; emit('saved', result)
  } catch (e) {
    if (!alive) return
    error.value = getApiErrorMessage(e)
    const status = (e as { response?: { status?: number } }).response?.status
    if (status === 409 || status === 404 || status === 403 || status === 401) { saved = true; emit('stale', error.value) }
    else if (status && status < 500 && status !== 408) submitted.value = undefined
  } finally { if (alive) busy.value = false }
}
</script>

<template>
  <DialogRoot :open="true" @update:open="value => { if (!value) close() }"><DialogPortal><DialogOverlay class="warehouse-guide-overlay" /><DialogContent class="fabric-receipt-dialog">
    <header class="fabric-intake-header"><div><span class="fabric-intake-eyebrow">布料仓 · 收料入库</span><DialogTitle>登记入库</DialogTitle><DialogDescription>按实物填写本次数量，分仓位、分缸可增加明细。</DialogDescription></div><Button variant="outline" :disabled="busy" @click="close">关闭</Button></header>
    <form class="fabric-intake-form" @submit.prevent="save">
      <div class="fabric-intake-body">
        <div class="fabric-intake-source"><div><span class="fabric-intake-tag">{{ source.facts.source_category === 'SUPPLEMENT' ? '补数追货' : '正常采购' }}</span><strong>{{ source.facts.material_name }}</strong><p>{{ source.facts.material_code }} · {{ source.facts.order_no }}</p><p>{{ source.facts.supplier }}</p></div><div class="fabric-intake-progress"><span>待收数量</span><strong>{{ remaining ?? '待核对' }} <small v-if="remaining !== undefined">{{ source.facts.unit }}</small></strong><p>本系统已入库 {{ source.warehouse_received_quantity ?? '0' }} {{ source.facts.unit }}</p></div></div>
        <p v-if="remaining === undefined" class="fabric-intake-alert" role="note">起始待收量待负责人核对。本次按实物入库，剩余待收暂不计算。</p>
        <datalist id="fabric-active-locations"><option v-for="bin in source.available_locations" :key="bin.code" :value="bin.code">{{ bin.warehouse }} · {{ bin.name }}</option></datalist><fieldset :disabled="busy || !!submitted" class="fabric-receipt-fields">
          <div class="fabric-intake-document-fields">
            <label>收货日期<input v-model="receiptDate" type="date" aria-label="实际收货日期" :max="today" required /></label>
            <label>送货单号 / 收料依据<input v-model="deliveryReference" aria-label="送货依据编号" placeholder="填写单号" maxlength="128" required /></label>
            <label>物料分类<select v-model="category" aria-label="入库物料分类" required><option value="" disabled>请选择</option><option v-for="(label, value) in materialCategoryLabels" :key="value" :value="value">{{ label }}</option></select></label>
          </div>
          <section class="fabric-intake-details"><div class="fabric-intake-section-heading"><h3>收货明细</h3><Button variant="outline" size="sm" type="button" :disabled="rows.length >= 200" @click="rows.push({ key: nextKey++, quantity: '', location: '', dye_lot: '', roll_no: '' })">＋ 增加明细</Button></div>
            <div class="fabric-intake-table-wrap"><table class="fabric-intake-table"><thead><tr><th class="fabric-intake-index">序号</th><th>本次实收（{{ source.facts.unit }}）</th><th>仓位 <span>*</span></th><th v-if="category === 'FABRIC'">缸号 <span>*</span></th><th v-if="category === 'FABRIC'">卷号（选填）</th><th class="fabric-intake-remove"></th></tr></thead><tbody>
              <tr v-for="(row, index) in rows" :key="row.key"><td class="fabric-intake-index">{{ index + 1 }}</td><td data-label="本次实收"><input v-model="row.quantity" :aria-label="`第${index + 1}项实收数量`" inputmode="decimal" placeholder="填写数量" maxlength="32" required /></td><td data-label="仓位"><input v-model="row.location" list="fabric-active-locations" :aria-label="`第${index + 1}项仓位`" placeholder="填写仓位" maxlength="128" required /></td><td v-if="category === 'FABRIC'" data-label="缸号"><input v-model="row.dye_lot" :aria-label="`第${index + 1}项缸号`" placeholder="染色批次号" maxlength="128" required /></td><td v-if="category === 'FABRIC'" data-label="卷号（选填）"><input v-model="row.roll_no" :aria-label="`第${index + 1}项卷号`" placeholder="单卷编号" maxlength="128" /></td><td class="fabric-intake-remove"><Button v-if="rows.length > 1" variant="ghost" size="sm" type="button" :aria-label="`删除第${index + 1}项`" @click="removeRow(row.key)">删除</Button></td></tr>
            </tbody></table></div>
            <div class="fabric-intake-totals"><span>{{ rows.length }} 项明细<span v-if="category === 'FABRIC'"> · 缸号必填，卷号为单卷编号</span></span><strong>本次实收合计：{{ total ?? '—' }} {{ source.facts.unit }}</strong></div>
          </section>
          <label v-if="overage" class="fabric-receipt-overage">超出待收数量 {{ overage }} {{ source.facts.unit }} · 超收说明<textarea v-model="reason" aria-label="超收说明" placeholder="说明本次超收的原因" maxlength="1000" rows="2" required /></label>
          <details class="fabric-receipt-more"><summary>补充信息（选填）</summary><div class="fabric-intake-extra-fields"><label>送货单日期<input v-model="deliveryDate" type="date" aria-label="送货单日期" /></label><label>收料备注<textarea v-model="note" aria-label="收料备注" placeholder="其他需要记录的信息" maxlength="2000" rows="2" /></label></div></details>
        </fieldset>
      </div>
      <footer class="fabric-intake-footer"><div class="fabric-intake-feedback"><p v-if="submitted && !busy" role="status">保存结果尚未确认。填写内容已锁定，重试会查询同一次入库结果。</p><p v-if="error" class="fabric-intake-error" role="alert">{{ error }}</p><span v-if="!error && !submitted">保存后，本次实收计入待检库存</span></div><div class="fabric-intake-actions"><Button type="button" variant="outline" :disabled="busy" @click="close">返回待收料</Button><Button type="submit" :disabled="busy || (!submitted && !valid)">{{ busy ? '正在保存…' : submitted ? '重试本次入库' : '保存并入库' }}</Button></div></footer>
    </form>
  </DialogContent></DialogPortal></DialogRoot>
</template>
