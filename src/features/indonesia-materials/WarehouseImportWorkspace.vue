<script setup lang="ts">
import { computed, nextTick, ref, watch } from 'vue'
import type { Data, MaterialRecord } from '@/api/indonesiaMaterials'
import { fixedCustomers } from './catalog'
import { newDraftId, recordDraftId, recordRef, restoreRecord } from './draftPersistence'
import { useMaterialDraft } from './useDraft'
import { useMaterials } from './workspace'
import Fields from './Fields.vue'
import type { Field } from './forms'
import { setNumberText } from './forms'
import { sameQuantity, purchaseFactsAgree } from './warehouseMatching'
import { focusFollowup } from './focusFollowup'
import ReceiptTemplatePicker from './ReceiptTemplatePicker.vue'
import WarehousePackingReview from './WarehousePackingReview.vue'
const ws = useMaterials()
const customer = ref(''), recipient = ref('RRI'), warehouse = ref(''), shipmentDate = ref('')
const file = ref<File | null>(null), preview = ref<MaterialRecord | null>(null), choices = ref<Data>({})
const context = ref({ customer: '', recipient: 'RRI', warehouse: '' })
const showUpload = ref(true)
const templatePicker = ref<InstanceType<typeof ReceiptTemplatePicker>>()
const completedShipment = ref('')
const sourceId = computed(() => preview.value?.id || '')
let beforePicker = true
watch([showUpload, preview, () => ws.supplyStage], () => { if (ws.supplyStage === 'warehouse') ws.wizardStep = preview.value && !showUpload.value ? 2 : 1 }, { flush: 'sync' })
function goStep(step: number) { if (step === 2 && !preview.value) return; showUpload.value = step === 1 }
const hasPreview = computed(() => !!preview.value)
const uploadForm = ref<HTMLFormElement | null>(null), fileInput = ref<HTMLInputElement | null>(null)
const importRequested = ref(false)
const records = computed(() => ws.kind('import').filter(row => row.data.import_type === 'warehouse_receipt'))
const customers = computed(() => fixedCustomers(ws.records))
const selectedRows = computed<Data[]>(() => (preview.value?.data.rows || []).filter((row: Data) => choices.value[row.index]?.selected && !row.blocked && !row.imported_supply_id))
const started = () => !!(file.value || preview.value || customer.value || warehouse.value || shipmentDate.value || recipient.value !== 'RRI')
const draft = useMaterialDraft(() => started() ? { customer: customer.value, recipient: recipient.value, warehouse: warehouse.value, shipmentDate: shipmentDate.value, choices: choices.value, preview: preview.value?.id, file: file.value } : null, {
  id: 'warehouse', multiple: true,
  capture: () => started() ? { customer: customer.value, recipient: recipient.value, warehouse: warehouse.value, shipmentDate: shipmentDate.value,
    showUpload: showUpload.value, choices: choices.value, preview: recordRef(preview.value), file: file.value, context: context.value,
    label: `${customer.value} · ${warehouse.value || '多仓库'} · ${file.value?.name || preview.value?.data.filename || '新实收单'}` } : null,
  restore: saved => {
    const source = restoreRecord(ws.records, saved.preview, 'import')
    if (source && source.data.import_type !== 'warehouse_receipt') throw new Error('原记录不是仓库实收单，草稿仍保留。')
    if (saved.file && !(saved.file instanceof File)) throw new Error('原实收文件草稿无法读取。')
    customer.value = saved.customer || ''; recipient.value = saved.recipient || 'RRI'; warehouse.value = saved.warehouse || ''; shipmentDate.value = saved.shipmentDate || ''
    showUpload.value = saved.showUpload ?? !source
    file.value = saved.file || null; preview.value = source || null; choices.value = saved.choices || {}; context.value = saved.context || { customer: customer.value, recipient: recipient.value, warehouse: warehouse.value }
  },
  reset: () => { file.value = null; preview.value = null; choices.value = {}; shipmentDate.value = ''; customer.value = ''; recipient.value = 'RRI'; warehouse.value = ''; context.value = { customer: '', recipient: 'RRI', warehouse: '' } },
})
const importBlocked = computed(() => !ws.canWrite || ws.locked || draft.switching.value || draft.recoveryWaiting.value)
const importHint = computed(() => {
  if (!importRequested.value) return ''
  if (!ws.canWrite) return '当前账号没有实收单导入权限，可查看已有导入记录。'
  if (draft.recoveryWaiting.value) return '请先在本机草稿中继续填写，或点击“新建实收导入”保留原草稿后开始新单。'
  if (ws.locked || draft.switching.value) return '请等待当前操作完成，再选择仓库实收文件。'
  return '选择仓库实收文件（XLSX／CSV），再点击“上传实收单并匹配”。取消选择会保留当前资料。'
})
async function openImport() {
  const epoch = ws.scopeEpoch
  importRequested.value = true
  beforePicker = showUpload.value
  showUpload.value = true
  // Keep the native picker in the user's click event, before waiting for the tab to render.
  if (!importBlocked.value) fileInput.value?.click()
  await nextTick()
  if (epoch === ws.scopeEpoch && ws.supplyStage === 'warehouse') {
    focusFollowup(uploadForm.value, importBlocked.value ? undefined : '仓库实收文件')
  }
}
watch([completedShipment, () => ws.locked, draft.submitting], () => {
  if (completedShipment.value && !ws.locked && !draft.submitting.value) {
    ws.shipmentTarget = completedShipment.value; completedShipment.value = ''
    ws.notice = '实收与 PO 已确认，下一步补齐装箱资料。'
  }
}, { flush: 'post' })
defineExpose({ openImport, goStep, hasPreview, sourceId })
const purchaseFields: Field[] = [
  { key: 'purchase_no', label: '采购单号', required: true }, { key: 'purchase_line', label: '采购行号', required: true },
  { key: 'purchase_date', label: '采购日期', type: 'date', required: true }, { key: 'purchase_quantity', label: '采购总量（含各回料批次）', type: 'number', required: true, min: '0.00000001', step: 'any' },
  { key: 'supplier', label: '供应商', required: true }, { key: 'price', label: '采购单价', type: 'number', required: true, min: '0', step: 'any' }, { key: 'currency', label: '币种', required: true },
]
function targets(row: Data): Data[] { return row.targets?.[choices.value[row.index]?.material_id] || [] }
function targetKey(target: Data) { return JSON.stringify([target.order_id, target.demand_id]) }
function changeTarget(row: Data, plan: Data, key: string) {
  const target = targets(row).find(item => targetKey(item) === key)
  Object.assign(plan, target ? { key, order_id: target.order_id, demand_id: target.demand_id, order_version: target.order_version } : { key: '', order_id: '', demand_id: '', order_version: 0 })
}
function matchingSupplies(row: Data): MaterialRecord[] { return (row.supplies || []).filter((item: MaterialRecord) => item.data.material_id === choices.value[row.index]?.material_id) }
function originalAllocations(row: Data): MaterialRecord[] {
  return ws.kind('allocation').filter(item => item.data.supply_id === choices.value[row.index]?.supply_id &&
    !(sameQuantity(item.data.normal_quantity, '0') && sameQuantity(item.data.spare_quantity, '0')))
}
function acknowledgeReplacement(row: Data, event: Event) {
  choices.value[row.index].replace_allocations = (event.target as HTMLInputElement).checked
    ? originalAllocations(row).map(item => ({ allocation_id: item.id, version: item.version })) : []
}
function chooseSupply(row: Data) {
  const choice = choices.value[row.index], supply = matchingSupplies(row).find(item => item.id === choice.supply_id)
  choice.supply_version = supply?.version || 0
  choice.replace_allocations = []; choice.replacement_reason = ''
  if (supply) {
    const allocations = ws.kind('allocation').filter(item => item.data.supply_id === supply.id)
    if (allocations.length && !choice.allocations.some((plan: Data) => plan.order_id)) choice.allocations = allocations.map(item => {
      return { key: '', order_id: '', demand_id: '', order_version: 0,
        normal_quantity: item.data.normal_quantity, spare_quantity: item.data.spare_quantity }
    })
  }
}
function chooseMaterial(row: Data) {
  const choice = choices.value[row.index], material = row.materials.find((item: Data) => item.id === choice.material_id)
  choice.material_version = material?.version || 0; choice.supply_id = ''; choice.supply_version = 0
  choice.replace_allocations = []; choice.replacement_reason = ''
  choice.purchase = { ...material?.defaults, ...Object.fromEntries(purchaseFields.map(field => [field.key, row.source[field.key] || material?.defaults?.[field.key] || ''])) }
  choice.allocations = []
  const plan: Data = { key: '', order_id: '', demand_id: '', order_version: 0, normal_quantity: row.source.normal_quantity, spare_quantity: row.source.spare_quantity }
  choice.allocations.push(plan)
  const supplies = matchingSupplies(row).filter(item => sameQuantity(item.data.normal_quantity, row.source.normal_quantity) && sameQuantity(item.data.spare_quantity, row.source.spare_quantity) && purchaseFactsAgree(row.source, item.data))
  if (supplies.length === 1 && row.source.purchase_no) { choice.supply_id = supplies[0]!.id; chooseSupply(row) }
}
function initialize(record: MaterialRecord) {
  preview.value = record; choices.value = {}; showUpload.value = false
  for (const row of record.data.rows) {
    choices.value[row.index] = { selected: !row.blocked && !row.imported_supply_id, material_id: row.auto_material_id || '', material_version: 0, supply_id: '', supply_version: 0, purchase: {}, allocations: [] }
    if (row.auto_material_id) chooseMaterial(row)
  }
}
function fresh() { return draft.openRecord(newDraftId('warehouse'), () => { showUpload.value = true; file.value = null; preview.value = null; choices.value = {}; shipmentDate.value = ''; context.value = { customer: customer.value, recipient: recipient.value, warehouse: warehouse.value } }) }
async function changeContext() {
  const next = { customer: customer.value, recipient: recipient.value, warehouse: warehouse.value }
  if (file.value || preview.value) {
    const original = file.value
    customer.value = context.value.customer; recipient.value = context.value.recipient; warehouse.value = context.value.warehouse
    await draft.openRecord(newDraftId('warehouse'), () => { customer.value = next.customer; recipient.value = next.recipient; warehouse.value = next.warehouse; context.value = next; file.value = original; preview.value = null; choices.value = {}; shipmentDate.value = '' })
  } else context.value = next
}
async function fileChanged(event: Event) {
  const input = event.target as HTMLInputElement, next = input.files?.[0]; input.value = ''
  if (!next) return
  if (file.value || preview.value) await draft.openRecord(newDraftId('warehouse'), () => { file.value = next; preview.value = null; choices.value = {}; shipmentDate.value = '' })
  else {
    // The native file picker may finish before the warehouse input's blur/change.
    // Freeze the actual upload context, so a later switch preserves all typed fields.
    context.value = { customer: customer.value, recipient: recipient.value, warehouse: warehouse.value }
    file.value = next
  }
}
async function upload() {
  if (!file.value || !customer.value || ws.locked) return
  if (preview.value && !await draft.openRecord(newDraftId('warehouse'), () => { preview.value = null; choices.value = {} })) return
  const owner = draft.activeId.value
  const result = await ws.preview(customer.value, recipient.value, file.value, warehouse.value)
  if (result && owner === draft.activeId.value) { initialize(result); draft.accept(); await ws.reload() }
}
function inspect(row: MaterialRecord) { return draft.openRecord(recordDraftId('warehouse', 'inspect', row.id), () => { file.value = null; customer.value = row.data.customer; recipient.value = row.data.recipient; warehouse.value = row.data.warehouse; context.value = { customer: customer.value, recipient: recipient.value, warehouse: warehouse.value }; initialize(row) }) }
watch(() => preview.value ? ws.record(preview.value.id) : undefined, row => { if (row) preview.value = row })
async function confirm() {
  if (!preview.value || !selectedRows.value.length) return
  const rows = selectedRows.value.map(row => {
    const choice = choices.value[row.index]
    return { index: row.index, material_id: choice.material_id, material_version: choice.material_version, supply_id: choice.supply_id || null, supply_version: choice.supply_version,
      purchase: choice.supply_id ? {} : choice.purchase, allocations: choice.allocations.map(({ key: _key, ...plan }: Data) => plan),
      ...(choice.replace_allocations?.length ? { replace_allocations: choice.replace_allocations, replacement_reason: choice.replacement_reason } : {}) }
  })
  await draft.run('warehouse_import_confirm', { shipment_date: shipmentDate.value, rows }, preview.value, result => { preview.value = result; for (const choice of Object.values(choices.value) as Data[]) choice.selected = false; completedShipment.value = result.data.shipment_ids?.at(-1) || '' })
}
</script>
<template>
  <section aria-label="仓库实收导入" class="im-stack">
    <div class="im-toolbar"><button type="button" :disabled="!ws.canWrite || ws.locked || draft.switching.value" @click="fresh">新建实收导入</button><button type="button" :disabled="!ws.canWrite || ws.locked || draft.switching.value" @click="templatePicker?.open(customer, recipient, warehouse)">下载实收导入模板</button></div>
    <ReceiptTemplatePicker ref="templatePicker" :blocked="draft.switching.value" />
    <form v-show="showUpload || !preview" id="im-warehouse-upload" ref="uploadForm" class="im-upload-form" @submit.prevent="upload"><p v-if="importHint" class="im-note" role="status">{{ importHint }}</p><fieldset class="im-fields" :disabled="importBlocked">
      <label class="im-field"><span>实收客户 *</span><select v-model="customer" required @change="changeContext"><option value="">请选择本厂区固定客人</option><option v-for="row in customers" :key="row.id" :value="row.data.name">{{ row.data.name }}</option></select></label>
      <label class="im-field"><span>实收接收方 *</span><select v-model="recipient" @change="changeContext"><option>RRI</option><option>RRM</option></select></label>
      <label class="im-field"><span>仓库名称（原单无仓库列时填写）</span><input v-model="warehouse" maxlength="160" @change="changeContext"></label>
      <label class="im-field"><span>仓库实收文件 *</span><input ref="fileInput" type="file" accept=".xlsx,.csv" :required="!file" @change="fileChanged" @cancel="showUpload = beforePicker"><small v-if="file">已保留：{{ file.name }}</small></label>
      <button class="im-primary" type="submit" :disabled="!customer || !file">上传实收单并匹配</button>
    </fieldset><p class="im-note">无物料编码时按名称、规格和单位匹配。取消或重新选文件，原草稿仍保留。</p></form>
    <form v-if="preview" v-show="!showUpload" class="im-editor im-stack" @submit.prevent="confirm">
      <fieldset class="im-stack" :disabled="draft.switching.value || ws.locked || !ws.canWrite">
      <div class="im-inline"><h3>{{ preview.data.filename }} · {{ preview.data.status === 'confirmed' ? '全部已导入' : '实收匹配核对' }}</h3><button type="button" :disabled="ws.busy" @click="ws.download(preview!.data.asset_id, preview!.data.filename, 'asset')">下载原单</button></div>
      <div class="im-scroll"><table><thead><tr><th>本次导入</th><th>仓库／收料单行</th><th>原单物料／规格</th><th>正常／备品实收</th><th>匹配与问题</th></tr></thead><tbody><tr v-for="row in preview.data.rows" :key="row.index"><td><input v-model="choices[row.index].selected" type="checkbox" :aria-label="`选择实收行 ${row.index + 1}`" :disabled="!ws.canWrite || ws.locked || row.blocked || !!row.imported_supply_id"></td><td>{{ row.source.warehouse || preview.data.warehouse }}<br>{{ row.source.receipt_no }} / {{ row.source.receipt_line }}<small>{{ row.source_sheet }} 第 {{ row.source_row }} 行 · {{ row.source.actual_date }}</small></td><td>{{ row.source.material_code || '无编码' }} · {{ row.source.material_name }}<small>{{ row.source.specification }} / {{ row.source.unit }}</small></td><td>{{ row.source.normal_quantity }} / {{ row.source.spare_quantity }}</td><td><strong>{{ row.imported_supply_id ? '已导入' : row.blocked ? '原单需核对' : !choices[row.index].material_id || choices[row.index].allocations.some((item: Data) => !item.order_id) ? '待业务确认' : '已匹配，待确认导入' }}</strong><p v-for="issue in row.issues" :key="issue" class="im-danger-text">{{ issue }}</p></td></tr></tbody></table></div>
      <fieldset v-for="row in selectedRows" :key="row.index" class="im-recipe-card im-stack" :disabled="!ws.canWrite || ws.locked || draft.switching.value">
        <h3>第 {{ row.index + 1 }} 行：{{ row.source.material_name || row.source.material_code }} · {{ row.source.receipt_no }}</h3>
        <div class="im-fields"><label class="im-field"><span>确认对应物料 *</span><select v-model="choices[row.index].material_id" required :aria-label="`实收行 ${row.index + 1} 对应物料`" @change="chooseMaterial(row)"><option value="">请选择匹配物料</option><option v-for="item in row.materials" :key="item.id" :value="item.id">{{ item.label }}</option></select><small v-if="!row.materials.length">未找到相同编码或名称／规格的物料，请先补齐基础资料后刷新核对。</small></label><label v-if="choices[row.index].material_id" class="im-field"><span>原采购／待回料批次</span><select v-model="choices[row.index].supply_id" :aria-label="`实收行 ${row.index + 1} 原采购批次`" @change="chooseSupply(row)"><option value="">按以下采购资料登记本次回料</option><option v-for="item in matchingSupplies(row)" :key="item.id" :value="item.id">{{ item.data.purchase_no }} / {{ item.data.purchase_line }} / {{ item.data.batch }} · 正常 {{ item.data.normal_quantity }} / 备品 {{ item.data.spare_quantity }}</option></select></label></div>
        <template v-if="choices[row.index].material_id">
          <Fields v-if="!choices[row.index].supply_id" :model="choices[row.index].purchase" :fields="purchaseFields" />
          <div v-else v-for="item in matchingSupplies(row).filter(item => item.id === choices[row.index].supply_id)" :key="item.id" class="im-message"><p>原批次：采购日期 {{ item.data.purchase_date }} · 采购总量 {{ item.data.purchase_quantity }} · 单价 {{ item.data.price }} {{ item.data.currency }}。保留原采购及换算快照。已有分配也须逐项点选核对客户 PO。</p><p v-if="!purchaseFactsAgree(row.source, item.data)" role="alert" class="im-danger-text">原单采购资料与该批次不一致，请先核对；系统不会覆盖原采购价格或静默忽略冲突。</p></div>
          <h3>这批实收用于哪些客户 PO</h3>
          <div v-if="originalAllocations(row).length" class="im-message">
            <p>此采购批次有历史预分配，请核对后点选本次抵扣的 PO。沿用时保持原数量；实际用途改变时，可明确确认重新指定。</p>
            <p v-for="item in originalAllocations(row)" :key="item.id">{{ ws.record(item.data.order_id)?.data.customer }}／{{ ws.record(item.data.order_id)?.data.recipient }} · {{ ws.orderName(item.data.order_id) }} · 正常 {{ item.data.normal_quantity }}／备品 {{ item.data.spare_quantity }}</p>
            <label class="im-inline"><input type="checkbox" :checked="!!choices[row.index].replace_allocations?.length" :aria-label="`实收行 ${row.index + 1} 重新指定历史分配`" @change="acknowledgeReplacement(row, $event)"><span>确认取消以上旧分配，改按下方所选 PO 抵扣（保留变更记录）</span></label>
            <label v-if="choices[row.index].replace_allocations?.length" class="im-field"><span>重新分配原因 *</span><input v-model="choices[row.index].replacement_reason" required maxlength="500"></label>
          </div>
          <div v-for="(plan, index) in choices[row.index].allocations" :key="index" class="im-fields">
            <label class="im-field"><span>客户 PO／合同／货号 *</span><select :value="plan.key" required :aria-label="`实收行 ${row.index + 1} 合同 ${Number(index) + 1}`" @change="changeTarget(row, plan, ($event.target as HTMLSelectElement).value)"><option value="">请选择本批物料对应的客户 PO</option><option v-for="target in targets(row)" :key="targetKey(target)" :value="targetKey(target)">{{ target.label }}</option></select></label>
            <label class="im-field"><span>分给此 PO 的正常量 *</span><input :value="plan.normal_quantity" type="number" min="0" step="any" required :aria-label="`实收行 ${row.index + 1} 正常量 ${Number(index) + 1}`" @input="setNumberText(plan, 'normal_quantity', $event)"></label>
            <label class="im-field"><span>分给此 PO 的备品量 *</span><input :value="plan.spare_quantity" type="number" min="0" step="any" required :aria-label="`实收行 ${row.index + 1} 备品量 ${Number(index) + 1}`" @input="setNumberText(plan, 'spare_quantity', $event)"></label>
            <button v-if="choices[row.index].allocations.length > 1" type="button" @click="choices[row.index].allocations.splice(Number(index), 1)">移除此 PO 分配</button>
          </div>
          <button type="button" @click="choices[row.index].allocations.push({ key: '', order_id: '', demand_id: '', order_version: 0, normal_quantity: '', spare_quantity: '0' })">拆分给另一个 PO</button>
        </template>
      </fieldset>
      <WarehousePackingReview :rows="preview.data.rows" :selected="selectedRows" />
      <fieldset v-if="selectedRows.length" class="im-stack" :disabled="!ws.canWrite || ws.locked || draft.switching.value"><label class="im-field"><span>本次计划河源出货日期 *</span><input v-model="shipmentDate" type="date" required></label><p class="im-note">确认 {{ selectedRows.length }} 行实收及 PO 分配，并生成出货草稿。正式出货在第 4 步确认。</p><button class="im-primary" type="submit" :disabled="selectedRows.length > 200">确认实收与 PO，去补装箱</button><p v-if="selectedRows.length > 200" class="im-error">每次最多确认 200 行，请分批选择。</p></fieldset>
      </fieldset>
      <div v-if="preview.data.shipment_ids?.length" class="im-message"><strong>已生成出货草稿</strong><p v-for="id in preview.data.shipment_ids" :key="id"><button type="button" :disabled="ws.locked" @click="ws.shipmentTarget = id">打开出货草稿并补装箱</button></p></div>
    </form>
    <details class="im-history"><summary>历史实收单 · {{ records.length }} 份</summary><h3>仓库实收导入记录</h3><div v-if="records.length" class="im-scroll"><table><thead><tr><th>原单</th><th>客人／接收方</th><th>已收行／总行数</th><th>出货草稿</th><th>操作</th></tr></thead><tbody><tr v-for="row in records" :key="row.id"><td>{{ row.data.filename }}</td><td>{{ row.data.customer }} / {{ row.data.recipient }}</td><td>{{ row.data.rows.filter((item: Data) => item.imported_supply_id).length }} / {{ row.data.rows.length }}</td><td>{{ row.data.shipment_ids.length }}</td><td><button type="button" :disabled="ws.locked || draft.switching.value" @click="inspect(row)">继续核对实收单</button></td></tr></tbody></table></div><p v-else class="im-empty">导入各仓库实际收到单后，在此核对匹配并生成出货草稿。</p>
    </details>
  </section>
</template>
