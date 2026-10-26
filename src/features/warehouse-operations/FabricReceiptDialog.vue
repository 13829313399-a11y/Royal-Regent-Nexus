<script setup lang="ts">
import { computed, onBeforeUnmount, ref, watch } from 'vue'
import { onBeforeRouteLeave, onBeforeRouteUpdate, useRoute } from 'vue-router'
import { DialogRoot, DialogPortal, DialogOverlay, DialogContent, DialogTitle, DialogDescription } from 'reka-ui'
import { Button } from '@/components/ui/button'
import { getApiErrorMessage } from '@/lib/http'
import type { PurchaseDetail } from '@/api/fabricProcurement'
import { fabricReceivingApi as api, materialCategoryLabels, type MaterialCategory, type ReceiveRequest, type FabricReceipt } from '@/api/fabricReceiving'
import { quantityText, receiptQuantity } from './receiptQuantities'
import FabricReceiptPriceFields from './FabricReceiptPriceFields.vue'
import type { ReceiptPriceInput } from '@/api/fabricReceiving'
import { warehouseRequestId } from './requestIdentity'
import WarehouseLocationPicker from './WarehouseLocationPicker.vue'
import { suggestMaterialCategory } from './materialCategorySuggestion'

const props = defineProps<{ source: PurchaseDetail }>()
const emit = defineEmits<{ close: []; saved: [receipt: FabricReceipt]; stale: [message: string] }>()
const today = new Intl.DateTimeFormat('sv-SE', { timeZone: 'Asia/Shanghai', year: 'numeric', month: '2-digit', day: '2-digit' }).format(new Date())
const receiptDate = ref(today), deliveryReference = ref(''), deliveryDate = ref(today)
const deliveryQuantity = ref('')
const initialCategory = props.source.material_category || suggestMaterialCategory(props.source.facts.unit)
const category = ref<MaterialCategory | ''>(initialCategory)
const reason = ref(''), note = ref(''), busy = ref(false), error = ref('')
const unitPrice = ref(''), currency = ref<NonNullable<ReceiptPriceInput['currency']>>('CNY')
const newRow = (key: number) => ({ key, counted_quantity: '', damaged_quantity: '0', rejected_quantity: '0', other_unusable_quantity: '0', location: '', location_id: '', dye_lot: '', roll_no: '' })
type ReceiptRow = ReturnType<typeof newRow>
const rows = ref([newRow(1)])
const quantityFields = [
  { key: 'counted_quantity', label: '实点数量' }, { key: 'damaged_quantity', label: '破损数量' },
  { key: 'rejected_quantity', label: '拒收数量' }, { key: 'other_unusable_quantity', label: '其他不可用' },
] as const
function accepted(row: ReceiptRow): string | undefined {
  const counted = receiptQuantity(row.counted_quantity), damaged = receiptQuantity(row.damaged_quantity),
    rejected = receiptQuantity(row.rejected_quantity), other = receiptQuantity(row.other_unusable_quantity)
  if (counted === undefined || damaged === undefined || rejected === undefined || other === undefined || damaged + rejected + other > counted) return undefined
  return quantityText(counted - damaged - rejected - other)
}
function sum(values: (string | undefined)[]): string | undefined {
  const amounts = values.map(value => receiptQuantity(value ?? ''))
  if (!amounts.every(value => value !== undefined)) return undefined
  const result = quantityText(amounts.reduce<bigint>((total, value) => total + value!, 0n))
  return receiptQuantity(result) === undefined ? undefined : result
}
function rowDirty(row: ReceiptRow) {
  return row.counted_quantity || row.location_id || row.location || row.dye_lot || row.roll_no ||
    row.damaged_quantity !== '0' || row.rejected_quantity !== '0' || row.other_unusable_quantity !== '0'
}
function addRoll(row: ReceiptRow) {
  if (rows.value.length < 200) rows.value.push({ ...newRow(nextKey++), location_id: row.location_id, location: row.location, dye_lot: row.dye_lot })
}
let nextKey = 2, alive = true, saved = false
const requestId = warehouseRequestId()
const submitted = ref<ReceiveRequest>()
const total = computed(() => sum(rows.value.map(accepted)))
const counted = computed(() => sum(rows.value.map(row => row.counted_quantity)))
const damaged = computed(() => sum(rows.value.map(row => row.damaged_quantity)))
const rejected = computed(() => sum(rows.value.map(row => row.rejected_quantity)))
const other = computed(() => sum(rows.value.map(row => row.other_unusable_quantity)))
const returned = computed(() => sum([damaged.value, rejected.value, other.value]))
const shortage = computed(() => {
  const d = receiptQuantity(deliveryQuantity.value), c = receiptQuantity(counted.value ?? '')
  return d !== undefined && c !== undefined && d >= c ? quantityText(d - c) : undefined
})
const summary = computed(() => [
  ['送货量', receiptQuantity(deliveryQuantity.value) !== undefined ? deliveryQuantity.value : undefined], ['实点合计', counted.value],
  ['破损合计', damaged.value], ['拒收合计', rejected.value], ['其他不可用合计', other.value],
  ['入库合计', total.value], ['短少', shortage.value], ['退供应商合计', returned.value],
])
const duplicate = computed(() => {
  if (category.value !== 'FABRIC') return false
  const keys = rows.value.filter(row => row.location_id && row.dye_lot.trim()).map(row => JSON.stringify([row.location_id, row.dye_lot.trim(), row.roll_no.trim()]))
  return new Set(keys).size !== keys.length
})
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
const deliveryLimit = computed(() => receiptQuantity(deliveryQuantity.value))
const exceedsDelivery = computed(() => deliveryLimit.value !== undefined && (receiptQuantity(counted.value ?? '') ?? 0n) > deliveryLimit.value)
const valid = computed(() => props.source.can_receive && total.value !== undefined && counted.value !== undefined && deliveryLimit.value !== undefined && deliveryLimit.value > 0n && !exceedsDelivery.value && !duplicate.value && (!unitPrice.value.trim() || (currency.value && receiptQuantity(unitPrice.value) !== undefined)) && rows.value.every(row => row.location_id && (category.value !== 'FABRIC' || row.dye_lot.trim())) && (!overage.value || reason.value.trim()) && category.value && deliveryReference.value.trim() && receiptDate.value && receiptDate.value <= today)
const dirty = computed(() => deliveryQuantity.value || unitPrice.value || currency.value !== 'CNY' || rows.value.some(rowDirty) || deliveryReference.value || deliveryDate.value !== today || receiptDate.value !== today || category.value !== initialCategory || reason.value || note.value)
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
  if (rowDirty(row) && !window.confirm('此项已填写，确定删除？')) return
  rows.value = rows.value.filter(item => item.key !== key)
}
async function save() {
  if (busy.value || (!submitted.value && !valid.value)) return
  if (!submitted.value) submitted.value = {
    factory_id: 'huakang-c', request_id: requestId, expected_source_revision: props.source.revision, expected_receipt_count: props.source.receipt_count ?? 0,
    receipt_date: receiptDate.value, delivery_reference: deliveryReference.value.trim(), delivery_note_date: deliveryDate.value || null,
    delivery_quantity: deliveryQuantity.value.trim(),
    material_category: category.value as MaterialCategory, difference_reason: overage.value ? reason.value.trim() : '', note: note.value.trim(),
    ...(unitPrice.value.trim() ? { unit_price: unitPrice.value.trim(), price_unit: props.source.facts.unit, currency: currency.value } : {}),
    batches: rows.value.map(row => ({ quantity: accepted(row)!, counted_quantity: row.counted_quantity.trim(), damaged_quantity: row.damaged_quantity.trim(), rejected_quantity: row.rejected_quantity.trim(), other_unusable_quantity: row.other_unusable_quantity.trim(), location_id: row.location_id, location: (props.source.available_locations ?? []).find(bin => bin.id === row.location_id)?.label ?? '', dye_lot: category.value === 'FABRIC' ? row.dye_lot : '', roll_no: category.value === 'FABRIC' ? row.roll_no : '' })), confirmed: true,
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
  <DialogRoot :open="true" @update:open="value => { if (!value) close() }"><DialogPortal><DialogOverlay class="warehouse-guide-overlay" /><DialogContent class="fabric-receipt-dialog fabric-touch-dialog">
    <header class="fabric-intake-header"><div><span class="fabric-intake-eyebrow">布料仓 · 收料入库</span><DialogTitle>登记入库</DialogTitle><DialogDescription>逐卷实点，扣除当场退供应商的不可用量后入库。</DialogDescription></div><Button variant="outline" :disabled="busy" @click="close">关闭</Button></header>
    <form class="fabric-intake-form" @submit.prevent="save">
      <div class="fabric-intake-body">
        <div class="fabric-intake-source"><div><span class="fabric-intake-tag">{{ source.facts.source_category === 'SUPPLEMENT' ? '补数追货' : '正常采购' }}</span><strong>{{ source.facts.material_name }}</strong><p>{{ source.facts.material_code }} · {{ source.facts.order_no }}</p><p>{{ source.facts.supplier }}</p></div><div class="fabric-intake-progress"><span>待收数量</span><strong>{{ remaining ?? '待核对' }} <small v-if="remaining !== undefined">{{ source.facts.unit }}</small></strong><p>本系统已入库 {{ source.warehouse_received_quantity ?? '0' }} {{ source.facts.unit }}</p></div></div>
        <p v-if="remaining === undefined" class="fabric-intake-alert" role="note">起始待收量待负责人核对。本次按实物入库，剩余待收暂不计算。</p>
        <fieldset :disabled="busy || !!submitted" class="fabric-receipt-fields">
          <div class="fabric-intake-document-fields">
            <label>收货日期<input v-model="receiptDate" type="date" aria-label="实际收货日期" :max="today" required /></label>
            <label>送货单号 / 收料依据<input v-model="deliveryReference" aria-label="送货依据编号" placeholder="填写单号" maxlength="128" required /></label>
            <label>本单该采购明细到货量（{{ source.facts.unit }}）<input v-model.trim="deliveryQuantity" aria-label="本单到货量" inputmode="decimal" maxlength="32" placeholder="按送货单填写，不能用采购总数代替" required /></label>
            <label>物料分类<select v-model="category" aria-label="入库物料分类" required><option value="" disabled>请选择</option><option v-for="(label, value) in materialCategoryLabels" :key="value" :value="value">{{ label }}</option></select><small v-if="!source.material_category && suggestMaterialCategory(source.facts.unit)">已按单位建议分类，可修改。</small></label>
          </div>
          <section class="fabric-intake-details"><div class="fabric-intake-section-heading"><h3>收货明细</h3><Button variant="outline" size="sm" type="button" :disabled="rows.length >= 200" @click="rows.push(newRow(nextKey++))">＋ 增加明细</Button></div>
            <div class="fabric-intake-table-wrap" tabindex="0" role="region" aria-label="逐卷收货明细"><table class="fabric-intake-table"><thead><tr><th class="fabric-intake-index">序号</th><th>仓位 <span>*</span></th><th v-if="category === 'FABRIC'">缸号 <span>*</span></th><th v-if="category === 'FABRIC'">卷号（选填）</th><th v-for="field in quantityFields" :key="field.key" class="numeric">{{ field.label }}<span v-if="field.key === 'counted_quantity'"> *</span></th><th class="numeric">入库数量</th><th class="fabric-intake-remove">操作</th></tr></thead><tbody>
              <tr v-for="(row, index) in rows" :key="row.key">
                <td class="fabric-intake-index">{{ index + 1 }}</td>
                <td data-label="仓位"><WarehouseLocationPicker :category="category" :disabled="busy || !!submitted" v-model="row.location_id" :locations="source.available_locations ?? []" :label="`第${index + 1}项仓位`" /></td>
                <td v-if="category === 'FABRIC'" data-label="缸号"><input v-model="row.dye_lot" :aria-label="`第${index + 1}项缸号`" placeholder="染色批次号" maxlength="128" required /></td>
                <td v-if="category === 'FABRIC'" data-label="卷号（选填）"><input v-model="row.roll_no" :aria-label="`第${index + 1}项卷号`" placeholder="单卷编号" maxlength="128" /></td>
                <td v-for="field in quantityFields" :key="field.key" :data-label="field.label" class="numeric"><input v-model="row[field.key]" :aria-label="`第${index + 1}项${field.label}`" inputmode="decimal" maxlength="32" required :placeholder="field.key === 'counted_quantity' ? '现场实点' : '0'" /></td>
                <td data-label="入库数量" class="numeric"><output :aria-label="`第${index + 1}项入库数量`">{{ accepted(row) ?? '—' }}</output><small v-if="row.counted_quantity && accepted(row) === undefined" class="fabric-intake-error">数量须非负、最多六位小数；不可用合计不得超过实点。</small></td>
                <td class="fabric-intake-remove"><Button v-if="category === 'FABRIC'" variant="outline" size="sm" type="button" :disabled="rows.length >= 200" :aria-label="`第${index + 1}项同缸新增一卷`" @click="addRoll(row)">同缸新增一卷</Button><Button v-if="rows.length > 1" variant="ghost" size="sm" type="button" :aria-label="`删除第${index + 1}项`" @click="removeRow(row.key)">删除</Button></td>
              </tr>
            </tbody></table></div>
            <div class="fabric-intake-totals"><span>{{ rows.length }} 项明细 · 单位：{{ source.facts.unit }}<span v-if="category === 'FABRIC'"> · 同卷分仓请填写不同仓位</span></span><strong>本次入库合计：{{ total ?? '—' }} {{ source.facts.unit }}</strong></div>
            <dl class="receipt-quantity-summary" aria-label="本次数量汇总"><div v-for="[label, value] in summary" :key="label"><dt>{{ label }}</dt><dd>{{ value ?? '—' }} {{ source.facts.unit }}</dd></div></dl>
          </section>
          <p v-if="exceedsDelivery" class="fabric-intake-error" role="alert">实点合计超过本单到货量，不能入库。</p>
          <p v-if="duplicate" class="fabric-intake-error" role="alert">同缸号、卷号和仓位重复，请合并核对。</p>
          <p v-if="total === '0'" class="fabric-intake-alert" role="status">本次全部不可用，只登记差异，不增加库存</p>
          <p class="fabric-intake-alert">同一送货依据分仓请在本次增加明细；需要分次入库时，请从“送货单入库”打开同一张已确认单据，系统会累计校验剩余量。</p>
          <FabricReceiptPriceFields v-model:price="unitPrice" v-model:currency="currency" :quantity="total" :unit="source.facts.unit" :reference="source.facts.unit_price" />
          <label v-if="overage" class="fabric-receipt-overage">超出待收数量 {{ overage }} {{ source.facts.unit }} · 超收说明<textarea v-model="reason" aria-label="超收说明" placeholder="说明本次超收的原因" maxlength="1000" rows="2" required /></label>
          <details class="fabric-receipt-more"><summary>补充信息（选填）</summary><div class="fabric-intake-extra-fields"><label>送货单日期<input v-model="deliveryDate" type="date" aria-label="送货单日期" /></label><label>收料备注<textarea v-model="note" aria-label="收料备注" placeholder="其他需要记录的信息" maxlength="2000" rows="2" /></label></div></details>
        </fieldset>
      </div>
      <footer class="fabric-intake-footer"><div class="fabric-intake-feedback"><p v-if="submitted && !busy" role="status">保存结果尚未确认。填写内容已锁定，重试会查询同一次入库结果。</p><p v-if="error" class="fabric-intake-error" role="alert">{{ error }}</p><span v-if="!error && !submitted">{{ total === '0' ? '保存后保留差异证据，不增加库存' : '保存后，仅可用入库量计入待检库存；不可用量当场退供应商' }}</span></div><div class="fabric-intake-actions"><Button type="button" variant="outline" :disabled="busy" @click="close">返回待收料</Button><Button type="submit" :disabled="busy || (!submitted && !valid)">{{ busy ? '正在保存…' : submitted ? '重试本次入库' : '保存并入库' }}</Button></div></footer>
    </form>
  </DialogContent></DialogPortal></DialogRoot>
</template>

<style scoped>
@media(min-width: 701px) { .fabric-receipt-dialog { width: min(1280px, calc(100vw - 32px)); } }
.fabric-intake-table-wrap { overflow-x: auto; }
.fabric-intake-table { min-width: 1140px; }
.fabric-intake-table .fabric-intake-remove { width: 128px; }
.fabric-intake-table .numeric, .fabric-intake-table .numeric input { text-align: right; font-variant-numeric: tabular-nums; }
.fabric-intake-table output { display: block; padding: 9px 0; font-weight: 650; color: var(--primary); }
.fabric-intake-table small { display: block; font-size: 11px; text-align: left; }
.receipt-quantity-summary { display: grid; grid-template-columns: repeat(4, minmax(0, 1fr)); gap: 12px 20px; margin-top: 16px; padding: 16px; background: var(--muted); border: 1px solid var(--border); border-radius: 8px; }
.receipt-quantity-summary dt { font-size: 12px; color: var(--muted-foreground); }
.receipt-quantity-summary dd { margin: 6px 0 0; font-size: 14px; font-weight: 600; font-variant-numeric: tabular-nums; overflow-wrap: anywhere; }
@media(max-width: 700px) { .fabric-intake-table { min-width: 0; } .fabric-intake-table .fabric-intake-remove { width: auto; } .receipt-quantity-summary { grid-template-columns: repeat(2, minmax(0, 1fr)); } }
</style>
