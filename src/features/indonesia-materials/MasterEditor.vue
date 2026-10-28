<script setup lang="ts">
import type { Data, MaterialRecord } from '@/api/indonesiaMaterials'
import type { Field } from './forms'
import Fields from './Fields.vue'
import MaterialDetailsFields from './MaterialDetailsFields.vue'
import UsageInput from './UsageInput.vue'
import { useMaterials } from './workspace'
const props = defineProps<{ form: Data; editing?: MaterialRecord; legacy?: boolean; fields: Field[]; imageReaders: number; switching?: boolean }>()
const emit = defineEmits<{ save: []; close: []; reading: [value: boolean]; add: [existing: boolean]; editMaterial: [item: Data]; deleteMaterial: [item: Data]; undoDelete: [item: Data] }>()
const ws = useMaterials()
function materialFor(item: Data) { return ws.kind('material').find(row => row.id === item.material_id) }
function productNames(item: Data) { return ws.kind('product').filter(row => row.data.materials.some((recipe: Data) => recipe.material_id === item.material_id)).map(row => row.data.code).join('、') }
function availableMaterials(item: Data) { return ws.kind('material').filter(row => !props.form.material_deletions.some((deleted: Data) => deleted.material_id === row.id) && (row.id === item.material_id || !props.form.materials.some((other: Data) => other !== item && other.material_id === row.id))) }
</script>
<template>
  <form class="im-editor im-stack" @submit.prevent="emit('save')">
    <h3>{{ editing ? '维护' : '新增' }}{{ legacy ? '物料资料' : '货号资料' }}<span v-if="!legacy" class="im-tag">{{ form.code || '新货号' }} · {{ form.customer || '请选择客人' }}</span></h3>
    <fieldset :disabled="!ws.canWrite || ws.locked || switching" class="im-stack">
      <MaterialDetailsFields v-if="legacy" :model="form" :existing="!!editing" @reading="emit('reading', $event)" />
      <template v-else>
        <Fields :model="form" :fields="fields" />
        <div class="im-recipe-heading"><div><h3>货号下的物料明细</h3><p class="im-note">资料与单件用量随货号一起保存；相同编码请“选用已有物料”。</p></div><div class="im-row-actions"><button type="button" @click="emit('add', false)">添加物料</button><button type="button" @click="emit('add', true)">选用已有物料</button></div></div>
        <p v-if="!form.materials.length" class="im-recipe-empty">此货号还没有物料，点击“添加物料”开始填写。</p>
        <article v-for="(item, index) in form.materials" :key="item._key" class="im-recipe-card" :data-material-id="item.material_id" :aria-label="`物料 ${Number(index) + 1}`">
          <div class="im-recipe-heading"><div><span class="im-tag">物料 {{ Number(index) + 1 }}</span><strong>{{ item.material?.name || materialFor(item)?.data.name || '待填写物料' }}</strong><small v-if="item.material_id">{{ materialFor(item)?.data.code }}</small></div><div class="im-row-actions"><button v-if="item.material_id" type="button" :disabled="!!imageReaders" @click="form.materials.splice(Number(index), 1)">移除关联</button><button type="button" class="im-danger-text" :disabled="!!imageReaders" @click="emit('deleteMaterial', item)">删除物料资料</button></div></div>
          <div class="im-fields im-recipe-usage">
            <label v-if="!item.material" class="im-field"><span>已有物料 *</span><select v-model="item.material_id" aria-label="用量物料" required><option value="">请选择物料</option><option v-for="material in availableMaterials(item)" :key="material.id" :value="material.id">{{ ws.materialName(material.id) }}（{{ material.data.unit }}）</option></select></label>
            <label class="im-field"><span>每件成品用量 *</span><UsageInput v-model="item.usage" /></label>
            <p class="im-note">每 1 {{ form.unit || '件' }} 成品使用 {{ item.usage || '—' }} {{ item.material?.unit || materialFor(item)?.data.unit || '物料单位' }}；上下调整每次 1。</p>
          </div>
          <template v-if="item.material">
            <p v-if="item.material_id" class="im-message">此物料共用于货号：{{ productNames(item) || form.code }}。修改物料资料会更新共用基础资料，已建合同及采购快照保持原值。</p>
            <MaterialDetailsFields :model="item.material" :existing="!!item.material_id" @reading="emit('reading', $event)" />
          </template>
          <template v-else-if="materialFor(item)">
            <dl class="im-material-facts"><div><dt>规格／单位</dt><dd>{{ materialFor(item)!.data.specification || '—' }} / {{ materialFor(item)!.data.unit }}</dd></div><div><dt>单个净重</dt><dd>{{ materialFor(item)!.data.net_weight_kg ?? '待维护' }} kg</dd></div><div><dt>供应商／单价</dt><dd>{{ materialFor(item)!.data.supplier || '待维护' }} / {{ materialFor(item)!.data.price }} {{ materialFor(item)!.data.currency }}</dd></div></dl>
            <button type="button" @click="emit('editMaterial', item)">{{ ws.canWrite ? '编辑物料资料' : '查看物料资料' }}</button>
          </template>
        </article>
        <div v-if="form.material_deletions.length" class="im-pending-material-deletions im-stack"><h3>待删除物料（保存后生效）</h3><p class="im-note">只处理下列物料，货号及其他物料保留。已保存物料删除后可在“已删除物料”恢复；有其他货号或合同、采购引用时不能删除。</p><div v-for="item in form.material_deletions" :key="item._key" class="im-recipe-heading"><span>{{ item.material?.code || materialFor(item)?.data.code || '未保存的新物料' }} · {{ item.material?.name || materialFor(item)?.data.name || '待填写物料' }}</span><button type="button" :disabled="!!imageReaders" @click="emit('undoDelete', item)">撤销删除</button></div></div>
      </template>
      <div class="im-actions"><button type="submit" class="im-primary" :disabled="!!imageReaders">保存资料</button><span v-if="!legacy" class="im-note">货号、物料资料、用量及待删除物料一次保存</span></div>
    </fieldset>
    <button type="button" :disabled="ws.busy || !!ws.pending || !!imageReaders || switching" @click="emit('close')">关闭表单</button>
  </form>
</template>
