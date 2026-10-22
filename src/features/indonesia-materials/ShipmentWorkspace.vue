<script setup lang="ts">
import { computed, ref } from 'vue'
import SectionPanel from './MaterialsPanel.vue'
import StatusPill from '@/components/common/StatusPill.vue'
import { FileSpreadsheet, Plus } from '@lucide/vue'
import ShipmentSummary from './ShipmentSummary.vue'
import type { Data, MaterialRecord } from '@/api/indonesiaMaterials'
import Fields from './Fields.vue'
import { inputData, packageFields, showStatus, setNumberText } from './forms'
import { useMaterials } from './workspace'
import { useMaterialDraft } from './useDraft'
import { recordRef, restoreRecord } from './draftPersistence'
const ws = useMaterials()
const defaults: Data = { customer: '', recipient: 'RRI', shipment_date: '', lines: [], packages: [], remarks: '' }
const form = ref<Data | null>(null)
const editing = ref<MaterialRecord>()
const confirming = ref<MaterialRecord>()
const readOnly = computed(() => editing.value?.data.status === 'confirmed')
const context = ref({ customer: '', recipient: 'RRI' })
const draft = useMaterialDraft(() => readOnly.value ? null : form.value ?? (confirming.value ? { confirming: confirming.value.id } : null), {
  id: 'shipment', capture: () => readOnly.value || (!form.value && !confirming.value) ? null : { form: form.value, editing: recordRef(editing.value), confirming: recordRef(confirming.value), context: context.value },
  restore: saved => {
    const row = restoreRecord(ws.records, saved.editing, 'shipment'), source = restoreRecord(ws.records, saved.confirming, 'shipment')
    if (row?.data.status === 'confirmed' || source?.data.status === 'confirmed') throw new Error('该出货单已确认，不能恢复为可编辑草稿或再次确认；原草稿仍保留。')
    const data = saved.form ? inputData(defaults, saved.form) : null
    if (data && data.lines.some((line: Data) => !ws.kind('allocation').some(item => item.id === line.allocation_id))) throw new Error('草稿中的原分配记录已不可用，请先核对，草稿仍保留。')
    editing.value = row; confirming.value = source; form.value = data; context.value = saved.context || { customer: data?.customer || '', recipient: data?.recipient || 'RRI' }
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
  return `${ws.orderName(allocation.data.order_id)} · ${ws.materialName(supply?.data.material_id)} · ${supply?.data.batch ?? ''}`
}
function edit(row?: MaterialRecord) { if (!draft.beforeOpen()) return; confirming.value = undefined; editing.value = row; form.value = inputData(defaults, row?.data); context.value = { customer: form.value.customer, recipient: form.value.recipient }; draft.accept() }
function close() { if (draft.permitDiscard()) form.value = null }
function beginConfirm(row: MaterialRecord) { if (draft.beforeOpen()) { editing.value = undefined; confirming.value = row; form.value = null; draft.accept() } }
function resetLines(key: 'customer' | 'recipient', event: Event) {
  if (!form.value) return
  if ((form.value.lines.length || form.value.packages.length) && !window.confirm('更改客户或接收方会清空本次出货数量和包装资料，确定继续吗？')) {
    Object.assign(form.value, context.value)
    ;(event.target as HTMLSelectElement).value = context.value[key]
    return
  }
  form.value.lines = []; form.value.packages = []
  context.value = { customer: form.value.customer, recipient: form.value.recipient }
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
async function save() { if (form.value) await draft.run('shipment_save', form.value, editing.value, () => { form.value = null }) }
async function confirm() { if (confirming.value) await draft.run('shipment_confirm', {}, confirming.value, () => { confirming.value = undefined }) }
</script>
<template>
  <SectionPanel title="客户出货单台账" subtitle="每次一个客户、一个接收方。保存草稿、业务确认出货、下载原版文件分别操作。">
    <template #action><button type="button" class="im-primary" :disabled="!ws.canWrite || ws.locked" @click="edit()"><Plus :size="15" />新建出货草稿</button></template>
    <div class="im-summary-strip"><div><span>出货单</span><strong>{{ ws.kind('shipment').length }} <small>张</small></strong></div><div><span>待业务确认</span><strong>{{ ws.kind('shipment').filter(row => row.data.status === 'draft').length }} <small>张</small></strong></div><div><span>已确认出货</span><strong>{{ ws.kind('shipment').filter(row => row.data.status === 'confirmed').length }} <small>张</small></strong></div></div>
    <div v-if="ws.kind('shipment').length" class="im-scroll"><table><thead><tr><th>客户／接收方</th><th>出货日期</th><th>分配行／包装组</th><th>状态</th><th>操作</th></tr></thead><tbody><tr v-for="row in ws.kind('shipment')" :key="row.id"><td>{{ row.data.customer }} / {{ row.data.recipient }}</td><td>{{ row.data.shipment_date }}</td><td>{{ row.data.lines.length }} / {{ row.data.packages.length }}</td><td><StatusPill :label="showStatus(row.data.status)" :tone="row.data.status === 'confirmed' ? 'green' : 'slate'" /></td><td><div class="flex flex-wrap gap-2"><button type="button" :disabled="ws.locked" @click="edit(row)">{{ row.data.status === 'draft' && ws.canWrite ? '编辑草稿' : '查看明细' }}</button><button v-if="row.data.status === 'draft'" type="button" :disabled="!ws.canWrite || ws.locked" @click="beginConfirm(row)">核对并确认出货</button><button v-else type="button" :disabled="!ws.has('export') || ws.busy" @click="ws.download(row.id, `${row.data.shipment_date}_${row.data.customer}_${row.data.recipient}_出货明细.xlsx`)">下载原版出货明细</button></div></td></tr></tbody></table></div>
    <div v-else-if="!form" class="im-onboarding"><span class="im-empty-icon"><FileSpreadsheet :size="28" /></span><h3>整理一份客户出货明细</h3><p>暂无出货记录。先完成物料分配及船务入库确认，再建立出货草稿。</p><p>支持整箱、尾箱与混箱；同一物料在导出表中归为一行。</p></div>
    <form v-if="form" class="im-editor im-stack" @submit.prevent="save">
      <h3>{{ readOnly ? '已确认出货明细' : editing ? '编辑出货草稿' : '新建出货草稿' }}</h3>
      <ShipmentSummary v-if="readOnly && editing" :shipment="editing.data" />
      <template v-if="packingTotals">
        <details><summary>查看合同与采购来源的重量明细</summary>
        <p class="im-message">服务器确认：物理箱数 {{ packingTotals.cartons }} 箱 · 总方数 {{ packingTotals.cbm }} m³（卡板不计重量及体积）</p>
        <div class="im-scroll"><table><thead><tr><th>合同物料／来源</th><th>净重（kg）</th><th>分摊纸箱重（kg）</th><th>毛重（kg）</th></tr></thead><tbody><tr v-for="(total, id) in packingTotals.lines" :key="id"><td>{{ label(String(id)) }}</td><td>{{ total.net_weight_kg }}</td><td>{{ total.carton_weight_kg }}</td><td>{{ total.gross_weight_kg }}</td></tr></tbody></table></div>
        </details>
      </template>
      <p v-else class="im-message">草稿先核对出货数量与装箱构成；确认成功后显示已核算的物料重量、混箱总箱数及供应商金额。</p>
      <fieldset :disabled="readOnly || !ws.canWrite || ws.locked" class="im-stack">
        <div class="im-fields"><label class="im-field"><span>客户 *</span><select v-model="form.customer" required @change="resetLines('customer', $event)"><option value="">请选择客户</option><option v-for="customer in customers" :key="customer" :value="customer">{{ customer }}</option></select></label><label class="im-field"><span>本次唯一接收方 *</span><select v-model="form.recipient" @change="resetLines('recipient', $event)"><option>RRI</option><option>RRM</option></select></label><label class="im-field"><span>实际出货日期 *</span><input v-model="form.shipment_date" type="date" required></label></div>
        <p class="im-note">更改客户或接收方会清空本次选择及包装资料。以下仅列该客户、该接收方且船务已确认入库的分配行。</p>
        <div v-if="candidates.length && !readOnly" class="im-scroll"><table><thead><tr><th>选择</th><th>合同物料／来源</th><th>已分配正常／备品</th><th>已发正常／备品</th></tr></thead><tbody><tr v-for="row in candidates" :key="row.id"><td><input type="checkbox" :checked="selected(row.id)" :aria-label="`选择出货 ${label(row.id)}`" @change="toggle(row, $event)"></td><td>{{ label(row.id) }}</td><td>{{ row.data.normal_quantity }} / {{ row.data.spare_quantity }}</td><td>{{ row.data.shipped_normal ?? '0' }} / {{ row.data.shipped_spare ?? '0' }}</td></tr></tbody></table></div>
        <p v-else-if="!readOnly" class="im-message">{{ form.customer ? '该客户及接收方暂无已入库的物料分配行。' : '选择客户后查看可出货分配。' }}</p>
        <h3>本次出货数量</h3>
        <div v-if="form.lines.length" class="im-scroll"><table><thead><tr><th>合同物料／来源</th><th>本次正常量</th><th>本次免费备品量</th></tr></thead><tbody><tr v-for="line in form.lines" :key="line.allocation_id"><td>{{ label(line.allocation_id) }}</td><td><input :value="line.normal_quantity" aria-label="本次正常量" type="number" min="0" step="any" required @input="setNumberText(line, 'normal_quantity', $event)"></td><td><input :value="line.spare_quantity" aria-label="本次免费备品量" type="number" min="0" step="any" required @input="setNumberText(line, 'spare_quantity', $event)"></td></tr></tbody></table></div>
        <p v-else class="im-note">尚未选择出货物料。</p>
        <h3>包装组与箱内明细</h3>
        <p class="im-note">每组填写同一装载构成的箱数、尺寸及每箱纸箱重量，箱内数量填该组全部纸箱的合计。同款物料本次各箱尺寸须相同，装量不同可分组登记；导出仍一物料一行，显示装量组合，共用混箱箱数及方数只计一次。卡板只记录标记，不计重量及体积。</p>
        <section v-for="(group, index) in form.packages" :key="index" class="im-editor im-stack">
          <h3>包装组 {{ Number(index) + 1 }}</h3><Fields :model="group" :fields="packageFields" />
          <div v-if="group.items.length" class="im-scroll"><table><thead><tr><th>箱内出货物料</th><th>组内正常量</th><th>组内备品量</th><th>操作</th></tr></thead><tbody><tr v-for="(item, itemIndex) in group.items" :key="itemIndex"><td><select v-model="item.allocation_id" aria-label="箱内出货物料" required><option value="">请选择本次物料</option><option v-for="line in form.lines" :key="line.allocation_id" :value="line.allocation_id">{{ label(line.allocation_id) }}</option></select></td><td><input :value="item.normal_quantity" aria-label="组内正常量" type="number" min="0" step="any" required @input="setNumberText(item, 'normal_quantity', $event)"></td><td><input :value="item.spare_quantity" aria-label="组内备品量" type="number" min="0" step="any" required @input="setNumberText(item, 'spare_quantity', $event)"></td><td><button type="button" @click="group.items.splice(itemIndex, 1)">移除此行</button></td></tr></tbody></table></div>
          <div class="im-actions"><button type="button" :disabled="!form.lines.length" @click="group.items.push({ allocation_id: '', normal_quantity: '', spare_quantity: '0' })">添加箱内物料</button><button type="button" @click="form.packages.splice(index, 1)">删除包装组</button></div>
        </section>
        <button type="button" :disabled="!form.lines.length" @click="addPackage">添加包装组</button>
        <label class="im-field"><span>出货备注</span><textarea v-model="form.remarks" maxlength="1000" /></label>
        <div v-if="!readOnly" class="im-actions"><button class="im-primary" type="submit" :disabled="!form.lines.length">保存出货草稿</button><span class="im-note">保存草稿不扣减出货数量；草稿列表另行核对确认。</span></div>
      </fieldset><button type="button" :disabled="ws.busy || !!ws.pending" @click="close">关闭明细</button>
    </form>
    <form v-if="confirming" class="im-editor im-stack" @submit.prevent="confirm">
      <h3>业务确认出货：{{ confirming.data.customer }} / {{ confirming.data.recipient }} · {{ confirming.data.shipment_date }}</h3>
      <div class="im-scroll"><table><thead><tr><th>出货物料</th><th>正常量</th><th>免费备品量</th></tr></thead><tbody><tr v-for="line in confirming.data.lines" :key="line.allocation_id"><td>{{ label(line.allocation_id) }}</td><td>{{ line.normal_quantity }}</td><td>{{ line.spare_quantity }}</td></tr></tbody></table></div>
      <div v-if="confirming.data.packages.length" class="im-scroll"><table><thead><tr><th>包装组／箱号</th><th>箱数</th><th>长 × 宽 × 高（cm）</th><th>每箱纸箱重（kg）</th><th>箱内物料与正常／备品量</th><th>卡板标记</th></tr></thead><tbody><tr v-for="(group, index) in confirming.data.packages" :key="index"><td>{{ group.label }}</td><td>{{ group.cartons }}</td><td>{{ group.length_cm }} × {{ group.width_cm }} × {{ group.height_cm }}</td><td>{{ group.carton_weight_kg }}</td><td><p v-for="item in group.items" :key="item.allocation_id">{{ label(item.allocation_id) }} · {{ item.normal_quantity }} / {{ item.spare_quantity }}</p></td><td>{{ group.pallet || '—' }}</td></tr></tbody></table></div>
      <p class="im-message">共 {{ confirming.data.packages.length }} 个包装组，实际 {{ confirmationCartons }} 箱。确认将核对库存、正常／备品数量、包装及模板资料，并记录一次实际出货。导出一物料一行，共用混箱箱数与方数只计一次；通过后可反复下载同一已确认文件，下载不会再次过账。</p>
      <p class="im-note">同一供应商本次只使用一种采购币种。资料、数量或尺寸不一致时会阻止确认并保留草稿，请按提示核对。</p>
      <div class="im-actions"><button type="submit" class="im-primary" :disabled="!ws.canWrite || ws.locked">确认以上数量及包装无误并出货</button><button type="button" :disabled="ws.busy || !!ws.pending" @click="confirming = undefined">取消</button></div>
    </form>
  </SectionPanel>
</template>
