<script setup lang="ts">
import { computed, ref } from 'vue'
import { Boxes, Package, Plus } from '@lucide/vue'
import SectionPanel from './MaterialsPanel.vue'
import type { Data, MaterialRecord } from '@/api/indonesiaMaterials'
import Fields from './Fields.vue'
import { inputData, materialDefaults, materialFields, productDefaults, productFields, setNumberText } from './forms'
import { useMaterials } from './workspace'
const ws = useMaterials()
const category = ref<'material' | 'product'>('material')
const editing = ref<MaterialRecord>()
const form = ref<Data | null>(null)
const imageError = ref('')
const rows = computed(() => ws.kind(category.value))
function open(kind: 'material' | 'product', row?: MaterialRecord) {
  category.value = kind; editing.value = row
  form.value = inputData(kind === 'material' ? materialDefaults : productDefaults, row?.data)
  imageError.value = ''
}
async function save() {
  if (!form.value) return
  if (await ws.run(category.value === 'material' ? 'material_save' : 'product_save', form.value, editing.value)) form.value = null
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
    <nav class="im-master-nav" aria-label="基础资料分类"><button type="button" :aria-pressed="category === 'material'" @click="category = 'material'; form = null"><Package :size="16" />物料资料</button><button type="button" :aria-pressed="category === 'product'" @click="category = 'product'; form = null"><Boxes :size="16" />货号与单件用量</button></nav>
  <SectionPanel :title="category === 'material' ? '物料资料' : '货号与单件用量'" :subtitle="category === 'material' ? '维护编码、单位、单重、供应商计费与采购周期；RRI / RRM 共用编码。' : '按货号维护日产能、运输自然日和单件用量；更新资料后由业务重新生成合同需求。'">
    <template #action><button type="button" class="im-primary" :disabled="!ws.canWrite || ws.locked" @click="open(category)"><Plus :size="15" />新增{{ category === 'material' ? '物料' : '货号' }}</button></template>
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
        <Fields :model="form" :fields="category === 'material' ? materialFields : productFields" />
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
      <button type="button" :disabled="ws.busy || !!ws.pending" @click="form = null">关闭表单</button>
    </form>
  </SectionPanel>
  </div>
</template>
