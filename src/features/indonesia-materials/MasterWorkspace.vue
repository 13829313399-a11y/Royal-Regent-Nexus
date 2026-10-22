<script setup lang="ts">
import { computed, ref, watch } from 'vue'
import { Boxes, Plus, Users, SlidersHorizontal } from '@lucide/vue'
import SectionPanel from './MaterialsPanel.vue'
import type { Data, MaterialRecord } from '@/api/indonesiaMaterials'
import CustomerWorkspace from './CustomerWorkspace.vue'
import MasterEditor from './MasterEditor.vue'
import OptionsWorkspace from './SharedOptionsWorkspace.vue'
import { customerOptions, fixedCustomers } from './catalog'
import { clone, inputData, materialDefaults, productDefaults, productFields } from './forms'
import { createRandomUuid } from '@/lib/randomUuid'
import { useMaterials } from './workspace'
import { useMaterialDraft } from './useDraft'
import { draftKind, productDraftId, recordRef, restoreRecord, type DraftId } from './draftPersistence'
const ws = useMaterials()
const category = ref<'customer' | 'material' | 'product' | 'options'>('customer')
const customerFilter = ref('')
const editing = ref<MaterialRecord>()
const form = ref<Data | null>(null)
const imageReaders = ref(0)
const optionsEditor = ref<InstanceType<typeof OptionsWorkspace>>()
const customerEditor = ref<InstanceType<typeof CustomerWorkspace>>()
const draft = useMaterialDraft(() => form.value, {
  id: 'master', multiple: true, capture: () => form.value ? { form: form.value, category: category.value, customerFilter: customerFilter.value, editing: recordRef(editing.value) } : null,
  restore: saved => {
    if (imageReaders.value) throw new Error('正在读取物料图片，请等待完成后再切换草稿，当前内容仍保留。')
    if (!['material', 'product'].includes(saved.category)) throw new Error('草稿资料分类无法识别，原内容仍保留。')
    const row = restoreRecord(ws.records, saved.editing, saved.category)
    const data = inputData(saved.category === 'material' ? materialDefaults : productDefaults, saved.form)
    if (customerEditor.value?.permitDiscard() === false || optionsEditor.value?.permitDiscard() === false) throw new Error('请先处理当前客人表单；原草稿仍保留。')
    if (saved.category === 'product') prepareMaterials(data)
    category.value = saved.category; customerFilter.value = saved.customerFilter || ''; editing.value = row; form.value = data
  },
  reset: () => { form.value = null; editing.value = undefined },
})
watch(() => ws.restoreTarget, id => { const kind = id ? draftKind(id) : undefined; if (kind === 'customer' || kind === 'options') changeCategory(kind) })
function changeCategory(next: 'customer' | 'material' | 'product' | 'options') {
  if (next === category.value) return
  if (draft.switching.value || imageReaders.value || !draft.permitDiscard() || customerEditor.value?.permitDiscard() === false || optionsEditor.value?.permitDiscard() === false) return
  form.value = null; category.value = next
}
function close() { if (!draft.switching.value && !imageReaders.value && draft.permitDiscard()) form.value = null }
const rows = computed(() => ws.kind(category.value === 'options' ? 'option' : category.value).filter(row => category.value !== 'product' || !customerFilter.value || row.data.customer === customerFilter.value))
const customers = computed(() => fixedCustomers(ws.records, false))
const fields = computed(() => productFields.map(field => field.key === 'customer'
  ? { ...field, type: 'select' as const, options: customerOptions(ws.records, editing.value?.data.customer), readonly: !!editing.value }
  : { ...field, readonly: field.key === 'code' && !!editing.value }))
function showCustomerProducts(name: string) { changeCategory('product'); if (category.value === 'product') customerFilter.value = name }
function prepareMaterials(data: Data) {
  data.materials = data.materials.map((item: Data) => ({ ...item, _key: item._key || createRandomUuid() }))
  data.material_deletions = (data.material_deletions || []).map((item: Data) => ({ ...item, _key: item._key || createRandomUuid() }))
}
function existingDraftId(row: MaterialRecord): DraftId {
  const id = productDraftId(row.id), legacy = ws.localDrafts.bucket.drafts.master
  return !ws.localDrafts.bucket.drafts[id] && legacy?.state.category === 'product' && legacy.state.editing?.id === row.id ? 'master' : id
}
async function open(kind: 'material' | 'product', row?: MaterialRecord, add = false) {
  if (imageReaders.value || draft.switching.value || ws.locked) return false
  if (form.value && category.value === kind && row && editing.value?.id === row.id) { if (add) addMaterial(); return true }
  const id: DraftId = kind === 'material' ? 'master' : row ? existingDraftId(row) : `master:new:${createRandomUuid()}`
  return await draft.openRecord(id, () => {
    category.value = kind; editing.value = row
    form.value = inputData(kind === 'material' ? materialDefaults : productDefaults, row?.data)
    if (kind === 'product' && !row && fixedCustomers(ws.records).some(customer => customer.data.name === customerFilter.value)) form.value.customer = customerFilter.value
    if (kind === 'product') {
      prepareMaterials(form.value)
      if (!ws.canWrite) form.value.materials.forEach(editMaterial)
      if (add) addMaterial()
    }
  })
}
function addMaterial(existing = false) {
  form.value?.materials.push({ _key: createRandomUuid(), material_id: '', usage: '', material_version: 0, material: existing ? null : inputData(materialDefaults) })
}
function materialFor(item: Data) { return ws.kind('material').find(row => row.id === item.material_id) }
function editMaterial(item: Data) {
  const row = materialFor(item)
  if (row) { item.material = inputData(materialDefaults, row.data); item.material_version = row.version }
}
function removeMaterial(item: Data) {
  if (!form.value || !ws.canWrite || imageReaders.value || ws.locked || draft.switching.value) return
  const index = form.value.materials.indexOf(item)
  if (index < 0) return
  const row = materialFor(item)
  if (item.material_id && !row) { ws.error = '该物料资料已变化，请核对后再删除；当前填写内容仍保留。'; return }
  const name = item.material?.code || row?.data.code || item.material?.name || '这条新物料'
  if (!window.confirm(item.material_id
    ? `删除物料资料 ${name}？点击“保存资料”后删除该物料及本货号关联，货号本身保留。有其他货号或合同、采购引用时不能删除；仅解除用量请选“移除关联”。删除后可在“已删除物料”恢复。`
    : `删除 ${name} 的本次物料资料？货号和其他物料保持不变，保存前可撤销删除。`)) return
  form.value.material_deletions.push({ ...clone(item), delete_version: item.material ? item.material_version : row?.version, _index: index })
  form.value.materials.splice(index, 1)
}
function undoMaterialDeletion(item: Data) {
  if (!form.value || !ws.canWrite || imageReaders.value || ws.locked || draft.switching.value) return
  const index = form.value.material_deletions.indexOf(item)
  if (index < 0) return
  const { delete_version: _version, _index: position, ...recipe } = item
  form.value.materials.splice(Math.min(position, form.value.materials.length), 0, recipe)
  form.value.material_deletions.splice(index, 1)
}
const inlineEditor = computed(() => !!form.value && category.value === 'product' && rows.value.some(row => row.id === editing.value?.id))
const deletedProducts = computed(() => ws.records.filter(row => row.kind === 'product' && row.data.deleted))
const deletedMaterials = computed(() => ws.records.filter(row => row.kind === 'material' && row.data.deleted))
async function removeProduct(row: MaterialRecord) {
  if (!ws.canWrite || !await open('product', row) || !editing.value || !window.confirm(`删除整个货号 ${editing.value.data.code}？这是货号操作，不会删除物料资料。删除后可在“已删除货号”恢复。`)) return
  await draft.run('product_delete', {}, editing.value, () => { form.value = null })
}
async function save() {
  if (!form.value || imageReaders.value) return
  const data = category.value === 'material' ? form.value : { ...form.value, materials: form.value.materials.map((item: Data) => item.material
    ? { material_id: item.material_id || null, usage: item.usage, material: inputData(materialDefaults, item.material), material_version: item.material_version }
    : { material_id: item.material_id, usage: item.usage }), material_deletions: form.value.material_deletions.filter((item: Data) => item.material_id).map((item: Data) => ({ material_id: item.material_id, expected_version: item.delete_version })) }
  await draft.run(category.value === 'material' ? 'material_save' : 'product_save', data, editing.value, () => { form.value = null })
}
</script>
<template>
  <div class="im-master-layout">
    <nav class="im-master-nav" aria-label="基础资料分类"><p class="im-note">本厂区资料</p><button type="button" :disabled="ws.locked || !!imageReaders || draft.switching.value" :aria-pressed="category === 'customer'" @click="changeCategory('customer')"><Users :size="16" />固定客人</button><button type="button" :disabled="ws.locked || !!imageReaders || draft.switching.value" :aria-pressed="category === 'product'" @click="changeCategory('product')"><Boxes :size="16" />货号与物料</button><p class="im-note">全厂共用资料</p><button type="button" :disabled="ws.locked || !!imageReaders || draft.switching.value" :aria-pressed="category === 'options'" @click="changeCategory('options')"><SlidersHorizontal :size="16" />基础选项</button></nav>
    <CustomerWorkspace ref="customerEditor" v-if="category === 'customer'" @products="showCustomerProducts" />
    <OptionsWorkspace ref="optionsEditor" v-else-if="category === 'options'" />
  <SectionPanel v-else :title="category === 'material' ? '恢复历史物料草稿' : '货号与物料'" :subtitle="category === 'material' ? '原草稿可继续保存；新增物料请从所属货号内维护。' : '选择固定客人，在每个货号下直接维护物料资料及单件用量。'">
    <template #action><button v-if="category === 'product'" type="button" class="im-primary" :disabled="!ws.canWrite || ws.locked || !!imageReaders || draft.switching.value" @click="open('product')"><Plus :size="15" />新增货号</button></template>
    <label v-if="category === 'product'" class="im-field im-customer-filter"><span>筛选固定客人</span><select v-model="customerFilter" :disabled="!!form"><option value="">全部客人／历史资料</option><option v-for="customer in customers" :key="customer.id" :value="customer.data.name">{{ customer.data.name }}{{ customer.data.status === 'inactive' ? '（已停用）' : '' }}</option></select></label>
    <p v-if="category === 'product' && !customers.length" class="im-message">请先在“固定客人”新增本厂区客人，再维护客人名下的货号。已有历史货号仍可查看。</p>
    <div v-if="category === 'product' && rows.length" class="im-scroll">
      <table class="im-master-products"><thead><tr><th>成品货号</th><th>名称</th><th>单位</th><th>客户／日产能</th><th>运输／物料数</th><th>操作</th></tr></thead>
        <tbody v-for="row in rows" :key="row.id" :data-product-id="row.id"><tr><td data-label="成品货号">{{ row.data.code }} <span v-if="ws.localDrafts.bucket.drafts[existingDraftId(row)]" class="im-tag">有草稿</span></td><td data-label="名称">{{ row.data.name || '—' }}</td><td data-label="单位">{{ row.data.unit }}</td>
          <td data-label="客户／日产能">{{ row.data.customer }} / {{ row.data.daily_capacity ?? '待维护' }}</td>
          <td data-label="运输／物料数">{{ row.data.transport_days }} 天 / {{ row.data.materials.length }} 种物料</td>
          <td data-label="操作"><div class="im-row-actions"><button type="button" :disabled="ws.locked || !!imageReaders || draft.switching.value" @click="open('product', row)">{{ ws.canWrite ? '编辑' : '查看' }}</button><button v-if="ws.canWrite" type="button" :disabled="ws.locked || !!imageReaders || draft.switching.value" @click="open('product', row, true)"><Plus :size="14" />添加物料</button><button v-if="ws.canWrite" type="button" class="im-danger-text" :disabled="ws.locked || !!imageReaders || draft.switching.value" @click="removeProduct(row)">删除货号</button></div></td>
        </tr><tr v-if="inlineEditor && editing?.id === row.id"><td colspan="6" class="im-inline-editor-cell"><MasterEditor :form="form!" :editing="editing" :legacy="category !== 'product'" :fields="fields" :image-readers="imageReaders" :switching="draft.switching.value" @save="save" @close="close" @delete-material="removeMaterial" @undo-delete="undoMaterialDeletion" @reading="imageReaders += $event ? 1 : -1" @add="addMaterial" @edit-material="editMaterial" /></td></tr></tbody></table>
    </div>
    <p v-else-if="!form" class="im-empty">暂无{{ category === 'material' ? '物料' : '货号' }}资料，请先新增资料。</p>
    <template v-if="form && !inlineEditor"><MasterEditor :form="form!" :editing="editing" :legacy="category !== 'product'" :fields="fields" :image-readers="imageReaders" :switching="draft.switching.value" @save="save" @close="close" @delete-material="removeMaterial" @undo-delete="undoMaterialDeletion" @reading="imageReaders += $event ? 1 : -1" @add="addMaterial" @edit-material="editMaterial" /></template>
    <details v-if="deletedMaterials.length" class="im-deleted-list"><summary>已删除物料（{{ deletedMaterials.length }}）</summary><p class="im-note">恢复物料资料后，可在货号中“选用已有物料”重新关联；不会自动改变货号用量。</p><p v-for="row in deletedMaterials" :key="row.id">{{ row.data.code }} / {{ row.data.name }} <button type="button" :disabled="!ws.canWrite || ws.locked || !!imageReaders || draft.switching.value" @click="ws.run('material_restore', {}, row)">恢复物料资料</button></p></details>
    <details v-if="deletedProducts.length" class="im-deleted-list"><summary>已删除货号（{{ deletedProducts.length }}）</summary><p v-for="row in deletedProducts" :key="row.id">{{ row.data.customer }} / {{ row.data.code }} <button type="button" :disabled="!ws.canWrite || ws.locked" @click="ws.run('product_restore', {}, row)">恢复货号</button></p></details>
  </SectionPanel>
  </div>
</template>
