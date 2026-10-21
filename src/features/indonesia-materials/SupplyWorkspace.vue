<script setup lang="ts">
import { ref } from 'vue'
import SectionPanel from './MaterialsPanel.vue'
import type { Data, MaterialRecord } from '@/api/indonesiaMaterials'
import Fields from './Fields.vue'
import { inputData, showStatus, supplyDefaults, supplyFields } from './forms'
import { useMaterials } from './workspace'
import { useMaterialDraft } from './useDraft'
import { recordRef, restoreRecord } from './draftPersistence'
const ws = useMaterials()
const form = ref<Data | null>(null)
const editing = ref<MaterialRecord>()
const selected = ref<MaterialRecord>()
const mode = ref<'reply' | 'receipt' | 'output'>('reply')
const actualDate = ref('')
const promisedDate = ref('')
const reason = ref('')
const draft = useMaterialDraft(() => form.value ?? (selected.value ? { actualDate: actualDate.value, promisedDate: promisedDate.value, reason: reason.value } : null), {
  id: 'supply', capture: () => form.value || selected.value ? { form: form.value, editing: recordRef(editing.value), selected: recordRef(selected.value), mode: mode.value, actualDate: actualDate.value, promisedDate: promisedDate.value, reason: reason.value } : null,
  allowed: saved => saved.selected && saved.mode === 'receipt' ? ws.has('receipt_confirm') : ws.canWrite,
  restore: saved => {
    const row = restoreRecord(ws.records, saved.editing, 'supply'), source = restoreRecord(ws.records, saved.selected, 'supply')
    if (!['reply', 'receipt', 'output'].includes(saved.mode)) throw new Error('回料草稿类型无法识别。')
    if ((saved.form && row?.data.status === 'received') || (source?.data.status === 'received' && saved.mode === 'receipt')) throw new Error('该批次已确认入库，不能恢复数量修改或再次入库；草稿仍保留。')
    editing.value = row; selected.value = source; form.value = saved.form ? inputData(supplyDefaults, saved.form) : null; mode.value = saved.mode
    actualDate.value = saved.actualDate || ''; promisedDate.value = saved.promisedDate || ''; reason.value = saved.reason || ''
  },
  reset: () => { form.value = null; selected.value = undefined; editing.value = undefined },
})
function close() { if (draft.permitDiscard()) { form.value = null; selected.value = undefined } }
function edit(row?: MaterialRecord) { if (!draft.beforeOpen()) return; selected.value = undefined; editing.value = row; form.value = inputData(supplyDefaults, row?.data); draft.accept() }
function select(row: MaterialRecord, action: 'reply' | 'receipt' | 'output') { if (!draft.beforeOpen(action === 'receipt' ? ws.has('receipt_confirm') : ws.canWrite)) return; form.value = null; selected.value = row; mode.value = action; actualDate.value = ''; promisedDate.value = row.data.promised_date ?? ''; reason.value = ''; draft.accept() }
function materialChanged() {
  if (!form.value || editing.value) return
  const data = ws.record(form.value.material_id)?.data
  if (data) Object.assign(form.value, { supplier: data.supplier, price: data.price, currency: data.currency, billing_basis: data.billing_basis, billing_factor: data.billing_factor })
}
async function save() { if (form.value) await draft.run('supply_save', form.value, editing.value, () => { form.value = null }) }
async function action() {
  if (!selected.value) return
  const committed = () => { selected.value = undefined }
  if (mode.value === 'receipt') await draft.run('receipt_confirm', { actual_date: actualDate.value }, selected.value, committed)
  else if (mode.value === 'output') await draft.run('output_material_refresh', { reason: reason.value }, selected.value, committed)
  else await draft.run('supply_reply', { promised_date: promisedDate.value, reason: reason.value }, selected.value, committed)
}
</script>
<template>
  <SectionPanel title="河源回料" subtitle="供应商回复只表示预计回料。船务核对正常量、免费备品量及实际到料日后，确认入库才形成实际齐料覆盖。">
    <template #action><button type="button" class="im-primary" :disabled="!ws.canWrite || ws.locked" @click="edit()">登记采购／回料批次</button></template>
    <div class="im-summary-strip"><div><span>采购 / 回料批次</span><strong>{{ ws.kind('supply').length }} <small>批</small></strong></div><div><span>待船务确认</span><strong>{{ ws.kind('supply').filter(row => row.data.status !== 'received').length }} <small>批</small></strong></div><div><span>已确认回料</span><strong>{{ ws.kind('supply').filter(row => row.data.status === 'received').length }} <small>批</small></strong></div></div>
    <div v-if="ws.kind('supply').length" class="im-scroll"><table><thead><tr><th>采购单／行</th><th>物料／供应商</th><th>批次</th><th>采购量</th><th>正常／备品</th><th>回复回料期</th><th>实际回料期</th><th>状态</th><th>操作</th></tr></thead><tbody>
      <tr v-for="row in ws.kind('supply')" :key="row.id"><td>{{ row.data.purchase_no }} / {{ row.data.purchase_line }}</td><td>{{ ws.materialName(row.data.material_id) }}<br>{{ row.data.supplier }}</td><td>{{ row.data.batch }}</td><td>{{ row.data.purchase_quantity }}</td><td>{{ row.data.normal_quantity }} / {{ row.data.spare_quantity }}</td><td>{{ row.data.promised_date || '待回复' }}</td><td>{{ row.data.actual_date || '未确认' }}</td><td>{{ showStatus(row.data.status) }}</td><td><div class="flex flex-wrap gap-2"><button v-if="row.data.status !== 'received'" type="button" :disabled="!ws.canWrite || ws.locked" @click="edit(row)">编辑数量</button><button type="button" :disabled="!ws.canWrite || ws.locked" @click="select(row, 'reply')">更新回复</button><button type="button" :disabled="!ws.canWrite || ws.locked" @click="select(row, 'output')">补全出货资料</button><button v-if="row.data.status !== 'received'" type="button" :disabled="!ws.has('receipt_confirm') || ws.locked" @click="select(row, 'receipt')">船务确认入库</button></div></td></tr>
    </tbody></table></div>
    <p v-else-if="!form" class="im-empty">暂无采购／回料批次。请先维护物料，再登记供应来源。</p>
    <form v-if="form" class="im-editor im-stack" @submit.prevent="save"><h3>{{ editing ? '编辑' : '登记' }}采购／回料批次</h3><fieldset :disabled="!ws.canWrite || ws.locked" class="im-stack"><label class="im-field"><span>物料 *</span><select v-model="form.material_id" required @change="materialChanged"><option value="">请选择物料</option><option v-for="row in ws.kind('material')" :key="row.id" :value="row.id">{{ ws.materialName(row.id) }}（{{ row.data.unit }}）</option></select></label><Fields :model="form" :fields="supplyFields" /><p class="im-note">正常量与备品量共同占采购总量；备品免费但计重量。实际入库确认后不能通过此表改写数量。</p><div class="im-actions"><button type="submit" class="im-primary">保存回料批次</button></div></fieldset><button type="button" :disabled="ws.busy || !!ws.pending" @click="close">关闭表单</button></form>
    <form v-if="selected" class="im-editor im-stack" @submit.prevent="action"><h3>{{ mode === 'receipt' ? '船务核对并确认入库' : mode === 'output' ? '从基础资料补全本批出货资料' : '记录供应商回复' }}：{{ selected.data.purchase_no }} / {{ selected.data.batch }}</h3><p>正常量 {{ selected.data.normal_quantity }} · 免费备品量 {{ selected.data.spare_quantity }} · {{ ws.materialName(selected.data.material_id) }}</p>
      <fieldset :disabled="ws.locked || !(mode === 'receipt' ? ws.has('receipt_confirm') : ws.canWrite)" class="im-stack">
        <label v-if="mode === 'receipt'" class="im-field"><span>实际回河源日期 *</span><input v-model="actualDate" type="date" required></label>
        <template v-else><label v-if="mode === 'reply'" class="im-field"><span>供应商回复回料日期 *</span><input v-model="promisedDate" type="date" required></label><label class="im-field"><span>{{ mode === 'output' ? '资料补全原因' : '回复来源／变更原因' }} *</span><input v-model="reason" required></label></template>
        <p v-if="mode === 'output'" class="im-note">先在基础资料库补齐英文名、类别、用途、部门、出口公司、图片或缺失单重，再执行此操作。规格和计数单位须一致；只补缺失重量，不覆盖已有重量、价格、数量或已确认出货。</p>
        <p v-if="mode === 'receipt'" class="im-note">确认将按以上正常量与备品量登记入库，并重新核算关联合同齐料；如数量不符，请先由业务修改批次。</p>
        <button type="submit" class="im-primary">{{ mode === 'receipt' ? '确认数量无误并入库' : mode === 'output' ? '确认补全出货资料' : '保存供应商回复' }}</button>
      </fieldset><button type="button" :disabled="ws.busy || !!ws.pending" @click="close">取消</button>
    </form>
    <div v-if="ws.kind('allocation').length" class="mt-6"><h3>回料分配去向</h3><div class="im-scroll"><table><thead><tr><th>采购／批次</th><th>合同／交付批次／货号</th><th>正常／备品分配</th><th>已发正常／备品</th></tr></thead><tbody><tr v-for="row in ws.kind('allocation')" :key="row.id"><td>{{ ws.record(row.data.supply_id)?.data.purchase_no }} / {{ ws.record(row.data.supply_id)?.data.batch }}</td><td>{{ ws.orderName(row.data.order_id) }}</td><td>{{ row.data.normal_quantity }} / {{ row.data.spare_quantity }}</td><td>{{ row.data.shipped_normal ?? '0' }} / {{ row.data.shipped_spare ?? '0' }}</td></tr></tbody></table></div></div>
  </SectionPanel>
</template>
