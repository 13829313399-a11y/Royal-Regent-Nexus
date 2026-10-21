<script setup lang="ts">
import { computed, ref, watch } from 'vue'
import { Boxes, Package, Plus, Users } from '@lucide/vue'
import SectionPanel from './MaterialsPanel.vue'
import type { Data, MaterialRecord } from '@/api/indonesiaMaterials'
import Fields from './Fields.vue'
import CustomerWorkspace from './CustomerWorkspace.vue'
import { customerOptions, fixedCustomers } from './catalog'
import { inputData, materialDefaults, materialFields, productDefaults, productFields, setNumberText } from './forms'
import { useMaterials } from './workspace'
import { useMaterialDraft } from './useDraft'
import { recordRef, restoreRecord } from './draftPersistence'
const ws = useMaterials()
const category = ref<'customer' | 'material' | 'product'>('customer')
const customerFilter = ref('')
const editing = ref<MaterialRecord>()
const form = ref<Data | null>(null)
const imageError = ref('')
const customerEditor = ref<InstanceType<typeof CustomerWorkspace>>()
const draft = useMaterialDraft(() => form.value, {
  id: 'master', capture: () => form.value ? { form: form.value, category: category.value, customerFilter: customerFilter.value, editing: recordRef(editing.value) } : null,
  restore: saved => {
    if (!['material', 'product'].includes(saved.category)) throw new Error('草稿资料分类无法识别，原内容仍保留。')
    const row = restoreRecord(ws.records, saved.editing, saved.category)
    const data = inputData(saved.category === 'material' ? materialDefaults : productDefaults, saved.form)
    if (customerEditor.value?.permitDiscard() === false) throw new Error('请先处理当前客人表单；原草稿仍保留。')
    category.value = saved.category; customerFilter.value = saved.customerFilter || ''; editing.value = row; form.value = data; imageError.value = ''
  },
  reset: () => { form.value = null; editing.value = undefined },
})
watch(() => ws.restoreTarget, id => { if (id === 'customer' && draft.permitDiscard()) { form.value = null; category.value = 'customer' } })
function changeCategory(next: 'customer' | 'material' | 'product') {
  if (next === category.value) return
  if (!draft.permitDiscard() || customerEditor.value?.permitDiscard() === false) return
  form.value = null; category.value = next
}
function close() { if (draft.permitDiscard()) form.value = null }
const rows = computed(() => ws.kind(category.value).filter(row => category.value !== 'product' || !customerFilter.value || row.data.customer === customerFilter.value))
const customers = computed(() => fixedCustomers(ws.records, false))
const fields = computed(() => category.value === 'material' ? materialFields : productFields.map(field => field.key === 'customer'
  ? { ...field, type: 'select' as const, options: customerOptions(ws.records, editing.value?.data.customer), readonly: !!editing.value }
  : { ...field, readonly: field.key === 'code' && !!editing.value }))
function showCustomerProducts(name: string) { changeCategory('product'); if (category.value === 'product') customerFilter.value = name }
function open(kind: 'material' | 'product', row?: MaterialRecord) {
  if (!draft.beforeOpen()) return
  category.value = kind; editing.value = row
  form.value = inputData(kind === 'material' ? materialDefaults : productDefaults, row?.data)
  if (kind === 'product' && !row && fixedCustomers(ws.records).some(customer => customer.data.name === customerFilter.value)) form.value.customer = customerFilter.value
  imageError.value = ''
  draft.accept()
}
async function save() {
  if (!form.value) return
  await draft.run(category.value === 'material' ? 'material_save' : 'product_save', form.value, editing.value, () => { form.value = null })
}
async function imageChanged(event: Event) {
  const input = event.target as HTMLInputElement
  const file = input.files?.[0]; input.value = ''
  if (!file || !form.value) return
  if (!['image/png', 'image/jpeg'].includes(file.type) || file.size > 1_400_000) { imageError.value = '请选择小于 1.4 MB 的 PNG 或 JPEG 图片。'; return }
  const original = form.value
  const reader = new FileReader()
  reader.onload = () => { if (form.value === original) { form.value.image_data = reader.result; imageError.value = '' } }
  reader.readAsDataURL(file)
}
</script>
<template>
  <div class="im-master-layout">
    <nav class="im-master-nav" aria-label="基础资料分类"><button type="button" :disabled="ws.locked" :aria-pressed="category === 'customer'" @click="changeCategory('customer')"><Users :size="16" />固定客人</button><button type="button" :disabled="ws.locked" :aria-pressed="category === 'product'" @click="changeCategory('product')"><Boxes :size="16" />货号与单件用量</button><button type="button" :disabled="ws.locked" :aria-pressed="category === 'material'" @click="changeCategory('material')"><Package :size="16" />物料资料</button></nav>
    <CustomerWorkspace ref="customerEditor" v-if="category === 'customer'" @products="showCustomerProducts" />
  <SectionPanel v-else :title="category === 'material' ? '物料资料' : '货号与单件用量'" :subtitle="category === 'material' ? '维护编码、单位、单重、供应商计费与采购周期；RRI / RRM 共用编码。' : '先选择本厂区固定客人，再维护其货号、日产能与物料单件用量。'">
    <template #action><button type="button" class="im-primary" :disabled="!ws.canWrite || ws.locked" @click="open(category)"><Plus :size="15" />新增{{ category === 'material' ? '物料' : '货号' }}</button></template>
    <label v-if="category === 'product'" class="im-field im-customer-filter"><span>筛选固定客人</span><select v-model="customerFilter"><option value="">全部客人／历史资料</option><option v-for="customer in customers" :key="customer.id" :value="customer.data.name">{{ customer.data.name }}{{ customer.data.status === 'inactive' ? '（已停用）' : '' }}</option></select></label>
    <p v-if="category === 'product' && !customers.length" class="im-message">请先在“固定客人”新增本厂区客人，再维护客人名下的货号。已有历史货号仍可查看。</p>
    <div v-if="rows.length" class="im-scroll">
      <table><thead><tr><th>{{ category === 'material' ? '物料编码' : '成品货号' }}</th><th>名称</th><th>单位</th><th>{{ category === 'material' ? '采购备料周期' : '客户／日产能' }}</th><th>{{ category === 'material' ? '供应商／计费' : '运输／用量行数' }}</th><th>操作</th></tr></thead>
        <tbody><tr v-for="row in rows" :key="row.id"><td>{{ row.data.code }}</td><td>{{ row.data.name || '—' }}</td><td>{{ row.data.unit }}</td>
          <td>{{ category === 'material' ? (row.data.procurement_days === null ? '待维护' : `${row.data.procurement_days} 天`) : `${row.data.customer} / ${row.data.daily_capacity ?? '待维护'}` }}</td>
          <td>{{ category === 'material' ? `${row.data.supplier || '未维护'} / ${row.data.billing_basis === 'weight' ? '按重量' : '按数量'}` : `${row.data.transport_days} 天 / ${row.data.materials.length} 行` }}</td>
          <td><button type="button" :disabled="ws.locked" @click="open(category, row)">{{ ws.canWrite ? '编辑' : '查看' }}</button></td>
        </tr></tbody></table>
    </div>
    <p v-else-if="!form" class="im-empty">暂无{{ category === 'material' ? '物料' : '货号' }}资料，请先新增资料。</p>
    <form v-if="form" class="im-editor im-stack" @submit.prevent="save">
      <h3>{{ editing ? '维护' : '新增' }}{{ category === 'material' ? '物料资料' : '货号资料' }}</h3>
      <fieldset :disabled="!ws.canWrite || ws.locked" class="im-stack">
        <Fields :model="form" :fields="fields" />
        <template v-if="category === 'material'">
          <p class="im-note">单个净重用于实际重量，单件计费重量用于按重量计价；请按采购资料分别填写。采购备料周期留空时会明确提示计划参数缺失。</p>
          <label class="im-field"><span>物料图片</span><input type="file" accept="image/png,image/jpeg" @change="imageChanged"></label>
          <p v-if="imageError" role="alert" class="im-error">{{ imageError }}</p>
          <div v-if="form.image_data" class="flex items-center gap-3"><img :src="form.image_data" alt="物料图片" class="h-24 w-24 object-contain"><button type="button" @click="form.image_data = ''">移除图片</button></div>
        </template>
        <template v-else>
          <h3>每件成品物料用量</h3>
          <div v-if="form.materials.length" class="im-scroll"><table><thead><tr><th>物料</th><th>每件成品用量</th><th>操作</th></tr></thead>
            <tbody><tr v-for="(item, index) in form.materials" :key="index"><td><select v-model="item.material_id" aria-label="用量物料" required><option value="">请选择物料</option><option v-for="material in ws.kind('material')" :key="material.id" :value="material.id">{{ ws.materialName(material.id) }}（{{ material.data.unit }}）</option></select></td><td><input :value="item.usage" aria-label="单件用量" type="number" min="0.00000001" step="any" required @input="setNumberText(item, 'usage', $event)"></td><td><button type="button" @click="form.materials.splice(index, 1)">移除</button></td></tr></tbody></table></div>
          <button type="button" @click="form.materials.push({ material_id: '', usage: '' })">添加用量行</button>
        </template>
        <div class="im-actions"><button type="submit" class="im-primary">保存资料</button></div>
      </fieldset>
      <button type="button" :disabled="ws.busy || !!ws.pending" @click="close">关闭表单</button>
    </form>
  </SectionPanel>
  </div>
</template>
