<script setup lang="ts">
import { lostRecordAccess } from './recordAccess'
import RecordResponsibility from './RecordResponsibility.vue'
import { computed, nextTick, ref, watch } from 'vue'
import SectionPanel from './MaterialsPanel.vue'
import StatusPill from '@/components/common/StatusPill.vue'
import { FileSpreadsheet, Plus } from '@lucide/vue'
import ShipmentSummary from './ShipmentSummary.vue'
import type { Data, MaterialRecord } from '@/api/indonesiaMaterials'
import Fields from './Fields.vue'
import { inputData, packageFields, showStatus, setNumberText } from './forms'
import { packingBalance } from './packingBalance'
import { focusFollowup } from './focusFollowup'
import { useMaterials } from './workspace'
import { useMaterialDraft } from './useDraft'
import { newDraftId, recordDraftId, recordRef, restoreRecord } from './draftPersistence'
const ws = useMaterials()
const defaults: Data = { customer: '', recipient: 'RRI', shipment_date: '', lines: [], packages: [], remarks: '' }
const form = ref<Data | null>(null)
const editing = ref<MaterialRecord>()
const confirming = ref<MaterialRecord>()
const editorElement = ref<HTMLFormElement | null>(null), confirmElement = ref<HTMLFormElement | null>(null)
const reviewed = ref(false), showOriginal = ref(false)
const completion = ref<{ record: MaterialRecord; confirmed: boolean }>()
const sourceId = computed(() => {
  const row = confirming.value || editing.value
  return row?.data.warehouse_import_id || (row && ws.kind('import').find(source => source.data.import_type === 'warehouse_receipt' && source.data.shipment_ids?.includes(row.id))?.id) || ''
})
const balances = computed(() => form.value ? packingBalance(form.value) : [])
const hasActive = computed(() => !!(form.value || confirming.value))
const canReview = computed(() => !!confirming.value || (!!form.value?.lines.length && !balances.value.length && !!editing.value))
watch([form, confirming, () => ws.supplyStage], () => { if (ws.supplyStage === 'shipment') ws.wizardStep = confirming.value || form.value && readOnly.value ? 4 : 3 }, { flush: 'post' })
async function goStep(step: number) { if (step === 4 && form.value && !readOnly.value) await save(true); else if (step === 3 && confirming.value) await edit(confirming.value) }
defineExpose({ goStep, hasActive, canReview, sourceId, canPack: computed(() => hasActive.value && !readOnly.value) })
const readOnly = computed(() => editing.value?.data.status === 'confirmed')
const context = ref({ customer: '', recipient: 'RRI' })
const accessLost = computed(() => lostRecordAccess(ws, confirming.value || editing.value))
const draft = useMaterialDraft(() => readOnly.value ? null : form.value ?? (confirming.value ? { confirming: confirming.value.id } : null), {
  id: 'shipment', multiple: true, capture: () => readOnly.value || (!form.value && !confirming.value) ? null : { form: form.value, editing: recordRef(editing.value), confirming: recordRef(confirming.value), context: context.value,
    label: confirming.value ? `${confirming.value.data.customer} · ${confirming.value.data.recipient} · ${confirming.value.data.shipment_date} · 确认出货` : '' },
  restore: saved => {
    const row = restoreRecord(ws.records, saved.editing, 'shipment'), source = restoreRecord(ws.records, saved.confirming, 'shipment')
    if (row?.data.status === 'confirmed' || source?.data.status === 'confirmed') throw new Error('该出货单已确认，不能恢复为可编辑草稿或再次确认；原草稿仍保留。')
    const data = saved.form ? inputData(defaults, saved.form) : null
    if (data && data.lines.some((line: Data) => !ws.kind('allocation').some(item => item.id === line.allocation_id))) throw new Error('草稿中的原分配记录已不可用，请先核对，草稿仍保留。')
    reviewed.value = false; editing.value = row; confirming.value = source; form.value = data; context.value = saved.context || { customer: data?.customer || '', recipient: data?.recipient || 'RRI' }
  },
  reset: () => { form.value = null; confirming.value = undefined; editing.value = undefined },
})
const packingTotals = computed(() => readOnly.value ? editing.value?.data.packing_totals : null)
const candidates = computed(() => ws.kind('allocation').filter(row => {
  const order = ws.record(row.data.order_id)?.data
  const supply = ws.record(row.data.supply_id)?.data
  return order?.customer === form.value?.customer && order?.recipient === form.value?.recipient && supply?.status === 'received'
}))
const customers = computed(() => [...new Set(ws.board.map(row => row.customer))])
function label(id: string) {
  const allocation = ws.record(id)
  if (!allocation) return '原分配记录不可用'
  const supply = ws.record(allocation.data.supply_id)
  const order = ws.record(allocation.data.order_id)?.data
  return `${ws.materialName(supply?.data.material_id)} · PO ${order?.po_no || '未填写'} · 合同 ${order?.contract_no || '—'}`
}
function edit(row?: MaterialRecord) { return draft.openRecord(row ? recordDraftId('shipment', 'edit', row.id) : newDraftId('shipment'), () => { confirming.value = undefined; editing.value = row; form.value = inputData(defaults, row?.data); context.value = { customer: form.value.customer, recipient: form.value.recipient } }, ws.canWrite && row?.data.status !== 'confirmed') }
let openingTarget = false
watch([() => ws.shipmentTarget, () => ws.record(ws.shipmentTarget || ''), () => ws.locked, draft.submitting, draft.switching], async () => {
  const id = ws.shipmentTarget, row = id ? ws.record(id) : undefined
  if (!id || row?.kind !== 'shipment' || ws.locked || draft.submitting.value || draft.switching.value || openingTarget) return
  openingTarget = true
  try { if (await edit(row) && ws.shipmentTarget === id) ws.shipmentTarget = null }
  finally { openingTarget = false }
}, { flush: 'post' })
function close() { if (!draft.switching.value && draft.permitDiscard()) form.value = null }
function beginConfirm(row: MaterialRecord) { reviewed.value = false; return draft.openRecord(recordDraftId('shipment', 'confirm', row.id, String(row.version)), () => { editing.value = undefined; confirming.value = row; form.value = null }) }
async function resetLines(_key: 'customer' | 'recipient', _event: Event) {
  if (!form.value) return
  const next = { customer: form.value.customer, recipient: form.value.recipient }
  if (editing.value || form.value.lines.length || form.value.packages.length) {
    const date = form.value.shipment_date, remarks = form.value.remarks
    Object.assign(form.value, context.value)
    await draft.openRecord(newDraftId('shipment'), () => { editing.value = undefined; confirming.value = undefined; form.value = { ...inputData(defaults), ...next, shipment_date: date, remarks }; context.value = next })
  } else {
    form.value.lines = []; form.value.packages = []; context.value = next
  }
}
function selected(id: string) { return form.value?.lines.some((row: Data) => row.allocation_id === id) }
function toggle(row: MaterialRecord, event: Event) {
  if (!form.value) return
  if ((event.target as HTMLInputElement).checked) form.value.lines.push({ allocation_id: row.id, normal_quantity: '', spare_quantity: '0' })
  else {
    form.value.lines = form.value.lines.filter((line: Data) => line.allocation_id !== row.id)
    for (const group of form.value.packages) group.items = group.items.filter((item: Data) => item.allocation_id !== row.id)
  }
}
function addPackage() { form.value?.packages.push({ label: '', cartons: 1, length_cm: '', width_cm: '', height_cm: '', carton_weight_kg: '0', pallet: '', items: [] }) }
const confirmationCartons = computed(() => confirming.value?.data.packages.reduce((total: number, group: Data) => total + Number(group.cartons), 0) ?? 0)
async function save(advance = false) {
  if (accessLost.value || !form.value) return
  if (advance && (balances.value.length || !form.value.packages.length)) { ws.error = '请先核平下方装箱数量并填写包装组。'; return }
  if (advance && editorElement.value && !editorElement.value.reportValidity()) return
  await draft.run('shipment_save', form.value, editing.value, result => { form.value = null; if (advance) completion.value = { record: result, confirmed: false } })
}
async function confirm() {
  if (accessLost.value || !confirming.value || !reviewed.value) { ws.error = '请先勾选已核对数量与装箱资料。'; return }
  await draft.run('shipment_confirm', {}, confirming.value, result => { confirming.value = undefined; completion.value = { record: result, confirmed: true } })
}
watch([completion, () => ws.locked, draft.submitting], async () => {
  if (!completion.value || ws.locked || draft.submitting.value) return
  const { record, confirmed } = completion.value; completion.value = undefined
  if (confirmed) {
    if (await edit(record) && ws.has('export')) await ws.download(record.id, `${record.data.shipment_date}_${record.data.customer}_${record.data.recipient}_出货明细.xlsx`)
  } else { await beginConfirm(record); await nextTick(); focusFollowup(confirmElement.value) }
}, { flush: 'post' })
</script>
<template>
  <SectionPanel title="本次出货资料">
    <p v-if="accessLost" class="im-message" role="alert">此待办已转交其他跟客或不可用，不能继续处理。原本机草稿保留，可新建或打开其他单据。</p>
    <template #action><button type="button" class="im-primary" :disabled="!ws.canWrite || (ws.locked || draft.switching.value)" @click="edit()"><Plus :size="15" />新建出货草稿</button></template>
    <details :open="!hasActive" class="im-history"><summary>出货记录 · {{ ws.kind('shipment').length }} 单</summary>
    <div v-if="ws.kind('shipment').length" class="im-scroll"><table><thead><tr><th>客户／接收方</th><th>出货日期</th><th>分配行／包装组</th><th>状态</th><th>上传人／负责人</th><th>操作</th></tr></thead><tbody><tr v-for="row in ws.kind('shipment')" :key="row.id" :data-shipment-id="row.id"><td>{{ row.data.customer }} / {{ row.data.recipient }}</td><td>{{ row.data.shipment_date }}</td><td>{{ row.data.lines.length }} / {{ row.data.packages.length }}</td><td><StatusPill :label="showStatus(row.data.status)" :tone="row.data.status === 'confirmed' ? 'green' : 'slate'" /></td><td><RecordResponsibility :record="row" /></td><td><div class="flex flex-wrap gap-2"><button type="button" :disabled="(ws.locked || draft.switching.value)" @click="edit(row)">{{ row.data.status === 'draft' && ws.canWrite ? '编辑草稿' : '查看明细' }}</button><button v-if="row.data.status === 'draft'" type="button" :disabled="!ws.canWrite || (ws.locked || draft.switching.value)" @click="beginConfirm(row)">核对并确认出货</button><button v-else type="button" :disabled="!ws.has('export') || ws.busy" @click="ws.download(row.id, `${row.data.shipment_date}_${row.data.customer}_${row.data.recipient}_出货明细.xlsx`)">下载原版出货明细</button></div></td></tr></tbody></table></div>
    <div v-else-if="!form" class="im-onboarding"><span class="im-empty-icon"><FileSpreadsheet :size="28" /></span><h3>整理一份客户出货明细</h3><p>暂无出货记录。先完成物料分配及船务入库确认，再建立出货草稿。</p><p>支持整箱、尾箱与混箱；同一物料在导出表中归为一行。</p></div>
    </details>
    <form v-if="form" ref="editorElement" class="im-editor im-stack" @submit.prevent="save()">
      <h3>{{ readOnly ? '已确认出货明细' : editing ? '编辑出货草稿' : '新建出货草稿' }}</h3>
      <p v-if="editing?.data.warehouse_import_id && !readOnly" class="im-message">实收与 PO 已确认。补齐本次装箱资料后进入出货核对。</p>
      <details v-if="editing?.data.packing_notes?.length && !readOnly" open class="im-message"><summary>导入时待核对的装箱资料</summary><p v-for="note in editing.data.packing_notes" :key="note">{{ note }}</p></details>
      <ShipmentSummary v-if="readOnly && editing" :shipment="editing.data" /><button v-if="readOnly && editing" type="button" class="im-primary" :disabled="!ws.has('export') || ws.busy" @click="ws.download(editing.id, `${editing.data.shipment_date}_${editing.data.customer}_${editing.data.recipient}_出货明细.xlsx`)">下载出货 Excel</button>
      <template v-if="packingTotals">
        <details><summary>查看合同与采购来源的重量明细</summary>
        <p class="im-message">服务器确认：物理箱数 {{ packingTotals.cartons }} 箱 · 总方数 {{ packingTotals.cbm }} m³（卡板不计重量及体积）</p>
        <div class="im-scroll"><table><thead><tr><th>合同物料／来源</th><th>净重（kg）</th><th>分摊纸箱重（kg）</th><th>毛重（kg）</th></tr></thead><tbody><tr v-for="(total, id) in packingTotals.lines" :key="id"><td>{{ label(String(id)) }}</td><td>{{ total.net_weight_kg }}</td><td>{{ total.carton_weight_kg }}</td><td>{{ total.gross_weight_kg }}</td></tr></tbody></table></div>
        </details>
      </template>

      <button v-if="readOnly" type="button" :aria-expanded="showOriginal" @click="showOriginal = !showOriginal">{{ showOriginal ? '收起原始装箱资料' : '查看原始装箱资料' }}</button>
      <fieldset v-show="!readOnly || showOriginal" :disabled="accessLost || readOnly || !ws.canWrite || (ws.locked || draft.switching.value)" class="im-stack">
        <div class="im-fields"><label class="im-field"><span>客户 *</span><select v-model="form.customer" required @change="resetLines('customer', $event)"><option value="">请选择客户</option><option v-for="customer in customers" :key="customer" :value="customer">{{ customer }}</option></select></label><label class="im-field"><span>本次唯一接收方 *</span><select v-model="form.recipient" @change="resetLines('recipient', $event)"><option>RRI</option><option>RRM</option></select></label><label class="im-field"><span>实际出货日期 *</span><input v-model="form.shipment_date" type="date" required></label></div>
        <details><summary>调整客户或出货来源</summary><p class="im-note">更换客户保留原单草稿；只可选择已实收且已分配的物料。</p>
        <div v-if="candidates.length && !readOnly" class="im-scroll"><table><thead><tr><th>选择</th><th>合同物料／来源</th><th>已分配正常／备品</th><th>已发正常／备品</th></tr></thead><tbody><tr v-for="row in candidates" :key="row.id"><td><input type="checkbox" :checked="selected(row.id)" :aria-label="`选择出货 ${label(row.id)}`" @change="toggle(row, $event)"></td><td>{{ label(row.id) }}</td><td>{{ row.data.normal_quantity }} / {{ row.data.spare_quantity }}</td><td>{{ row.data.shipped_normal ?? '0' }} / {{ row.data.shipped_spare ?? '0' }}</td></tr></tbody></table></div>
        <p v-else-if="!readOnly" class="im-message">{{ form.customer ? '该客户及接收方暂无已入库的物料分配行。' : '选择客户后查看可出货分配。' }}</p>
        </details><h3>本次出货数量</h3>
        <div v-if="form.lines.length" class="im-scroll"><table><thead><tr><th>合同物料／来源</th><th>本次正常量</th><th>本次免费备品量</th></tr></thead><tbody><tr v-for="line in form.lines" :key="line.allocation_id"><td>{{ label(line.allocation_id) }}</td><td><input :value="line.normal_quantity" aria-label="本次正常量" type="number" min="0" step="any" required @input="setNumberText(line, 'normal_quantity', $event)"></td><td><input :value="line.spare_quantity" aria-label="本次免费备品量" type="number" min="0" step="any" required @input="setNumberText(line, 'spare_quantity', $event)"></td></tr></tbody></table></div>
        <p v-else class="im-note">尚未选择出货物料。</p>
        <h3>包装组与箱内明细</h3>
        <div v-if="!readOnly" class="im-packing-status" role="status"><p v-for="issue in balances" :key="`${issue.id}-${issue.message}`" class="im-danger-text">{{ label(issue.id) }}：{{ issue.message }}</p><p v-if="!balances.length && form.lines.length" class="im-note">正常量与备品量已核平</p></div><details><summary>装箱填写说明</summary><p class="im-note">组内数量填全部箱合计，正常量与备品分别核平。同物料尺寸须一致，混箱箱数和体积只计一次。</p></details>
        <section v-for="(group, index) in form.packages" :key="index" class="im-editor im-stack">
          <h3>包装组 {{ Number(index) + 1 }}</h3><Fields :model="group" :fields="packageFields" />
          <div v-if="group.items.length" class="im-scroll"><table><thead><tr><th>箱内出货物料</th><th>组内正常量</th><th>组内备品量</th><th>操作</th></tr></thead><tbody><tr v-for="(item, itemIndex) in group.items" :key="itemIndex"><td><select v-model="item.allocation_id" aria-label="箱内出货物料" required><option value="">请选择本次物料</option><option v-for="line in form.lines" :key="line.allocation_id" :value="line.allocation_id">{{ label(line.allocation_id) }}</option></select></td><td><input :value="item.normal_quantity" aria-label="组内正常量" type="number" min="0" step="any" required @input="setNumberText(item, 'normal_quantity', $event)"></td><td><input :value="item.spare_quantity" aria-label="组内备品量" type="number" min="0" step="any" required @input="setNumberText(item, 'spare_quantity', $event)"></td><td><button type="button" @click="group.items.splice(itemIndex, 1)">移除此行</button></td></tr></tbody></table></div>
          <div class="im-actions"><button type="button" :disabled="!form.lines.length" @click="group.items.push({ allocation_id: '', normal_quantity: '', spare_quantity: '0' })">添加箱内物料</button><button type="button" @click="form.packages.splice(index, 1)">删除包装组</button></div>
        </section>
        <button type="button" :disabled="!form.lines.length" @click="addPackage">添加包装组</button>
        <label class="im-field"><span>出货备注</span><textarea v-model="form.remarks" maxlength="1000" /></label>
        <div v-if="!readOnly" class="im-actions"><button type="submit" :disabled="!form.lines.length">保存出货草稿</button><button class="im-primary" type="button" :disabled="!form.lines.length" @click="save(true)">保存装箱，去核对出货</button></div>
      </fieldset><button type="button" :disabled="ws.busy || !!ws.pending || draft.switching.value" @click="close">关闭明细</button>
    </form>
    <form v-if="confirming" ref="confirmElement" class="im-editor im-stack" @submit.prevent="confirm">
      <h3>业务确认出货：{{ confirming.data.customer }} / {{ confirming.data.recipient }} · {{ confirming.data.shipment_date }}</h3>
      <div class="im-scroll"><table><thead><tr><th>出货物料</th><th>正常量</th><th>免费备品量</th></tr></thead><tbody><tr v-for="line in confirming.data.lines" :key="line.allocation_id"><td>{{ label(line.allocation_id) }}</td><td>{{ line.normal_quantity }}</td><td>{{ line.spare_quantity }}</td></tr></tbody></table></div>
      <div v-if="confirming.data.packages.length" class="im-scroll"><table><thead><tr><th>包装组／箱号</th><th>箱数</th><th>长 × 宽 × 高（cm）</th><th>每箱纸箱重（kg）</th><th>箱内物料与正常／备品量</th><th>卡板标记</th></tr></thead><tbody><tr v-for="(group, index) in confirming.data.packages" :key="index"><td>{{ group.label }}</td><td>{{ group.cartons }}</td><td>{{ group.length_cm }} × {{ group.width_cm }} × {{ group.height_cm }}</td><td>{{ group.carton_weight_kg }}</td><td><p v-for="item in group.items" :key="item.allocation_id">{{ label(item.allocation_id) }} · {{ item.normal_quantity }} / {{ item.spare_quantity }}</p></td><td>{{ group.pallet || '—' }}</td></tr></tbody></table></div>
      <p class="im-note">{{ confirmationCartons }} 箱 · 确认后正式记录出货，生成 Excel。重复下载不会再次记账。</p>
      <label class="im-inline"><input v-model="reviewed" type="checkbox" required :disabled="accessLost || ws.locked"><span>已核对本次数量、装箱与实际出货日期</span></label>
      <div class="im-actions"><button type="submit" class="im-primary" :disabled="accessLost || !ws.canWrite || (ws.locked || draft.switching.value)">{{ ws.has('export') ? '确认出货并导出 Excel' : '确认出货' }}</button><button type="button" :disabled="ws.busy || !!ws.pending || draft.switching.value" @click="confirming = undefined">取消</button></div>
    </form>
  </SectionPanel>
</template>
