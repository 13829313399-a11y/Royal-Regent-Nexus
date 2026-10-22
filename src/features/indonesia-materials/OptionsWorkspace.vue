<script setup lang="ts">
import { computed, ref } from 'vue'
import type { Data, MaterialRecord } from '@/api/indonesiaMaterials'
import MaterialsPanel from './MaterialsPanel.vue'
import Fields from './Fields.vue'
import type { Field } from './forms'
import { inputData } from './forms'
import { maintainedOptions, optionGroups } from './options'
import { useMaterials } from './workspace'
import { useMaterialDraft } from './useDraft'
import { newDraftId, recordDraftId, recordRef, restoreRecord } from './draftPersistence'
const ws = useMaterials(), group = ref('category'), query = ref('')
const form = ref<Data | null>(null), editing = ref<MaterialRecord>()
const named = ref(false)
type OptionItem = { data: Data; record?: MaterialRecord }
const optionInput = (data?: Data) => inputData({ group: group.value, value: '', status: 'active', billing_basis: 'quantity', kg_per_unit: '1' }, data)
const draft = useMaterialDraft(() => form.value, {
  id: 'options', multiple: true, capture: () => form.value ? { form: form.value, editing: recordRef(editing.value), group: group.value, named: named.value, label: `${optionGroups.find(item => item.value === form.value?.group)?.label || '选项'} · ${form.value.value || '新选项'}` } : null,
  restore: saved => { editing.value = restoreRecord(ws.records, saved.editing, 'option'); form.value = optionInput(saved.form); group.value = saved.group; named.value = !!saved.named },
  reset: () => { form.value = null; editing.value = undefined },
})
const rows = computed(() => maintainedOptions(ws.records, ws.optionDefaults, group.value).filter(item => item.data.value.toLowerCase().includes(query.value.toLowerCase())))
const deletedRows = computed(() => maintainedOptions(ws.records, ws.optionDefaults, group.value, true).filter(item => item.data.deleted && item.record && item.data.value.toLowerCase().includes(query.value.toLowerCase())))
const fields = computed<Field[]>(() => [
  { key: 'group', label: '选项分类', type: 'select', required: true, readonly: true, options: optionGroups },
  { key: 'value', label: '选项名称', required: true, readonly: named.value },
  { key: 'status', label: '使用状态', type: 'select', readonly: !ws.has('options_manage'), options: [{ value: 'active', label: '启用' }, { value: 'inactive', label: '停用' }] },
  ...(form.value?.group === 'customs_unit' ? [
    { key: 'billing_basis', label: '计价依据', type: 'select' as const, readonly: !ws.has('options_manage'), options: [{ value: 'quantity', label: '按件数' }, { value: 'weight', label: '按千克换算' }] },
    ...(form.value?.billing_basis === 'weight' ? [{ key: 'kg_per_unit', label: '每报关单位对应千克数', type: 'number' as const, readonly: !ws.has('options_manage'), required: true, min: '0.00000001', step: 'any' }] : []),
  ] : []),
])
async function changeGroup(event: Event) { const next = (event.target as HTMLSelectElement).value; if (next === group.value) return; if (!await draft.openRecord(newDraftId('options'), () => { form.value = null; editing.value = undefined; group.value = next })) (event.target as HTMLSelectElement).value = group.value }
function open(item?: OptionItem) {
  return draft.openRecord(item ? recordDraftId('options', 'edit', item.data.group, item.data.value) : newDraftId('options'), () => {
    editing.value = item?.record; named.value = !!item; form.value = optionInput(item?.data)
  })
}
async function save() { if (form.value) await draft.run('option_save', form.value, editing.value, () => { form.value = null }) }
async function remove(item?: OptionItem) {
  if (!ws.has('options_manage') || (ws.locked || draft.switching.value)) return
  const original = item?.data ?? (named.value ? form.value : null)
  if (!original || !window.confirm(`删除选项“${original.value}”？删除后不再用于新录入，可在当前分类的“已删除选项”中恢复；历史资料和已保存计价不变。`)) return
  if (item && !await open(item)) return
  const data = editing.value ? {} : { group: original.group, value: original.value }
  await draft.run('option_delete', data, editing.value, () => { form.value = null })
}
function close() { if (!draft.switching.value && draft.permitDiscard()) form.value = null }
defineExpose({ permitDiscard: draft.permitDiscard })
</script>
<template>
  <MaterialsPanel title="基础选项" subtitle="全部厂区使用同一份选项；保存对全厂生效，历史资料及已确认文件保留原值。">
    <template #action><button type="button" class="im-primary" :disabled="!ws.canWrite || (ws.locked || draft.switching.value)" @click="open()">新增选项</button></template>
    <div class="im-fields"><label class="im-field"><span>资料分类</span><select :value="group" :disabled="(ws.locked || draft.switching.value)" @change="changeGroup"><option v-for="item in optionGroups" :key="item.value" :value="item.value">{{ item.label }}</option></select></label><label class="im-field"><span>搜索选项</span><input v-model="query" type="search" placeholder="输入名称关键词"></label></div>
    <div class="im-scroll"><table><thead><tr><th>选项名称</th><th>状态</th><th v-if="group === 'customs_unit'">计价规则</th><th>操作</th></tr></thead><tbody><tr v-for="item in rows" :key="item.data.value" :data-option-value="item.data.value"><td>{{ item.data.value }}</td><td>{{ item.data.status === 'active' ? '启用' : '停用' }}</td><td v-if="group === 'customs_unit'">{{ item.data.billing_basis === 'weight' ? `每单位 ${item.data.kg_per_unit} kg` : '按件数' }}</td><td><div class="im-inline"><button type="button" :disabled="(ws.locked || draft.switching.value)" @click="open(item)">{{ ws.canWrite ? '编辑选项' : '查看选项' }}</button><button v-if="ws.has('options_manage')" type="button" class="im-danger-text" :disabled="(ws.locked || draft.switching.value)" @click="remove(item)">删除选项</button></div></td></tr></tbody></table></div>
    <p v-if="!rows.length" class="im-empty">暂无符合的选项，可新增维护。</p>
    <form v-if="form" class="im-editor im-stack" @submit.prevent="save"><h3>维护基础选项</h3><fieldset :disabled="!ws.canWrite || (ws.locked || draft.switching.value)" class="im-stack"><Fields :model="form" :fields="fields" /><p v-if="form.group === 'customs_unit'" class="im-note">KGM 每单位 1 kg；TNE 每单位 1000 kg；PCE 按件。规则只用于后续录入，不重算历史采购。</p><div class="im-actions"><button type="submit" class="im-primary">保存选项</button><button v-if="named && ws.has('options_manage')" type="button" class="im-danger-text" @click="remove()">删除选项</button></div></fieldset><button type="button" :disabled="(ws.locked || draft.switching.value)" @click="close">关闭选项表单</button></form>
    <details v-if="deletedRows.length" class="im-deleted-list"><summary>已删除选项（{{ deletedRows.length }}）</summary><p v-for="item in deletedRows" :key="item.data.value">{{ item.data.value }} <button type="button" :disabled="!ws.has('options_manage') || (ws.locked || draft.switching.value)" @click="ws.run('option_restore', {}, item.record)">恢复选项</button></p><p class="im-note">恢复后保留删除前的使用状态和计价规则。</p></details>
  </MaterialsPanel>
</template>
