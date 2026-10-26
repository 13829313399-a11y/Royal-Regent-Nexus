<script setup lang="ts">
import { computed, ref } from 'vue'
import { Plus, Users } from '@lucide/vue'
import type { Data, MaterialRecord } from '@/api/indonesiaMaterials'
import MaterialsPanel from './MaterialsPanel.vue'
import Fields from './Fields.vue'
import { customerDefaults, customerFields, inputData } from './forms'
import { customerProducts, fixedCustomers } from './catalog'
import { useMaterials } from './workspace'
import { useMaterialDraft } from './useDraft'
import { newDraftId, recordDraftId, recordRef, restoreRecord } from './draftPersistence'
const emit = defineEmits<{ products: [customer: string] }>()
const ws = useMaterials()
const customers = computed(() => fixedCustomers(ws.records, false))
const deletedCustomers = computed(() => ws.records.filter(row => row.kind === 'customer' && row.data.deleted))
const editing = ref<MaterialRecord>()
const form = ref<Data | null>(null)
const draft = useMaterialDraft(() => form.value, {
  id: 'customer', multiple: true, capture: () => form.value ? { form: form.value, editing: recordRef(editing.value) } : null,
  restore: saved => { const row = restoreRecord(ws.records, saved.editing, 'customer'); const data = inputData(customerDefaults, saved.form); editing.value = row; form.value = data },
  reset: () => { form.value = null; editing.value = undefined },
})
const fields = computed(() => customerFields.map(field => ({ ...field, readonly: field.key === 'name' && !!editing.value })))
function open(row?: MaterialRecord) { return draft.openRecord(row ? recordDraftId('customer', 'edit', row.id) : newDraftId('customer'), () => { editing.value = row; form.value = inputData(customerDefaults, row?.data) }) }
function close() { if (!draft.switching.value && draft.permitDiscard()) form.value = null }
async function save() { if (form.value) await draft.run('customer_save', form.value, editing.value, () => { form.value = null }) }
async function remove() {
  if (!editing.value || (ws.locked || draft.switching.value) || !window.confirm(`删除客人 ${editing.value.data.name}？仅无货号及合同引用时可删除，删除后仍可恢复。`)) return
  await draft.run('customer_delete', {}, editing.value, () => { form.value = null })
}
defineExpose({ permitDiscard: draft.permitDiscard })
</script>
<template>
  <MaterialsPanel title="固定客人" subtitle="按当前厂区维护送印尼的客人，再为客人配置货号与物料用量。">
    <template #action><button type="button" class="im-primary" :disabled="!ws.canWrite || (ws.locked || draft.switching.value)" @click="open()"><Plus :size="15" />新增固定客人</button></template>
    <p class="im-catalog-path">当前厂区 <span>→</span> 固定客人 <span>→</span> 客人货号 <span>→</span> 物料及单件用量</p>
    <div v-if="customers.length" class="im-scroll"><table><thead><tr><th>固定客人</th><th>使用状态</th><th>上印尼货号</th><th>备注</th><th>操作</th></tr></thead><tbody>
      <tr v-for="customer in customers" :key="customer.id" :data-customer-id="customer.id"><td><strong>{{ customer.data.name }}</strong></td><td><span class="im-tag" :class="customer.data.status === 'inactive' ? 'im-tag-amber' : ''">{{ customer.data.status === 'active' ? '启用' : '停用' }}</span></td><td>{{ customerProducts(ws.records, customer.data.name).length }} 款</td><td>{{ customer.data.notes || '—' }}</td><td><div class="im-inline"><button type="button" :disabled="(ws.locked || draft.switching.value)" @click="emit('products', customer.data.name)">维护客人货号</button><button type="button" :disabled="(ws.locked || draft.switching.value)" @click="open(customer)">{{ ws.canWrite ? '编辑客人' : '查看客人' }}</button></div></td></tr>
    </tbody></table></div>
    <div v-else-if="!form" class="im-onboarding"><span class="im-empty-icon"><Users :size="28" /></span><h3>先维护本厂区的固定客人</h3><p>新增客人后，配置该客人的成品货号，再绑定各货号所需物料和单件用量。</p><p>客人与 RRI / RRM 接收方分别管理；每次出货仍只选一个接收方。</p></div>
    <form v-if="form" class="im-editor im-stack" @submit.prevent="save"><h3>{{ editing ? '维护' : '新增' }}固定客人</h3><fieldset :disabled="!ws.canWrite || (ws.locked || draft.switching.value)" class="im-stack"><Fields :model="form" :fields="fields" /><p class="im-note">客人名称用于关联货号和合同，建立后保留原名。停用后暂停新业务选择，已有合同和出货记录继续保留。</p><div class="im-actions"><button type="submit" class="im-primary">保存固定客人</button><button v-if="editing" type="button" class="im-danger-text" @click="remove">删除客人</button></div></fieldset><button type="button" :disabled="(ws.locked || draft.switching.value)" @click="close">关闭客人表单</button></form>
    <details v-if="deletedCustomers.length" class="im-deleted-list"><summary>已删除客人（{{ deletedCustomers.length }}）</summary><p v-for="row in deletedCustomers" :key="row.id">{{ row.data.name }} <button type="button" :disabled="!ws.canWrite || (ws.locked || draft.switching.value)" @click="ws.run('customer_restore', {}, row)">恢复客人</button></p></details>
  </MaterialsPanel>
</template>
