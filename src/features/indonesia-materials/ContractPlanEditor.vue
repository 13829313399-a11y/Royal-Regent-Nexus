<script setup lang="ts">
import { nextTick, ref } from 'vue'
import type { Data, MaterialRecord } from '@/api/indonesiaMaterials'
import { useMaterials } from './workspace'
import { useMaterialDraft } from './useDraft'
import { recordDraftId, recordRef, restoreRecord } from './draftPersistence'
import { setNumberText } from './forms'
import { focusFollowup } from './focusFollowup'
const emit = defineEmits<{ select: [id: string] }>()
const ws = useMaterials()
const targetReady = ref(false)
const editing = ref<MaterialRecord>(), form = ref<Data | null>(null), host = ref<HTMLElement | null>(null)
const draft = useMaterialDraft(() => form.value, {
  id: 'planning', multiple: true,
  capture: () => form.value && editing.value ? { form: form.value, editing: recordRef(editing.value), label: `${editing.value.data.contract_no} · PO ${editing.value.data.po_no || '未填写'} · 计划参数` } : null,
  restore: async saved => {
    const order = restoreRecord(ws.records, saved.editing, 'order')
    if (!order) throw new Error('原合同不存在，计划草稿仍保留。')
    targetReady.value = false; emit('select', order.id); await nextTick()
    editing.value = order; form.value = saved.form; targetReady.value = true
  },
  reset: () => { form.value = null; editing.value = undefined },
})
async function open(id: string) {
  const order = ws.record(id), board = ws.board.find(r => r.id === id)
  if (!order || !board) return
  const product = ws.kind('product').find(r => r.data.customer === order.data.customer && r.data.code === order.data.item_no)
  if (!product || !board.demands.length) { ws.error = '请先补齐货号与物料用量，再生成合同需求。'; return }
  const wasReady = targetReady.value
  targetReady.value = false
  const opened = await draft.openRecord(recordDraftId('planning', 'edit', id), () => {
    editing.value = order
    form.value = { product_id: product.id, product_version: product.version, daily_capacity: product.data.daily_capacity ?? '', transport_days: product.data.transport_days ?? 25,
      materials: board.demands.map(d => { const material = ws.record(d.material_id); return { material_id: d.material_id, expected_version: material?.version ?? 0, procurement_days: material?.data.procurement_days ?? '' } }) }
  })
  await nextTick()
  if (opened) { emit('select', id); await nextTick(); targetReady.value = true; await nextTick(); focusFollowup(host.value) }
  else targetReady.value = wasReady
}
async function save() {
  if (!form.value || !editing.value) return
  const id = editing.value.id
  if (await draft.run('order_plan_save', form.value, editing.value, () => { form.value = null; editing.value = undefined })) {
    ws.notice = '计划参数已保存，本合同回料期限与采购开始日期已更新。'
    emit('select', id)
  }
}
function close() { if (!draft.switching.value && draft.permitDiscard()) form.value = null }
defineExpose({ open, hide: () => { targetReady.value = false } })
</script>
<template>
  <Teleport v-if="form && editing && targetReady" :to="`#im-plan-slot-${editing.id}`">
    <form ref="host" class="im-editor im-stack im-inline-plan" aria-label="当前合同计划参数" @submit.prevent="save">
      <div class="im-section-label"><h3>本合同计划参数</h3><span class="im-note">已填写资料自动带出</span></div>
      <fieldset :disabled="ws.locked || !ws.canWrite || draft.switching.value" class="im-stack">
        <div class="im-fields"><label class="im-field"><span>日产能 *</span><input :value="form.daily_capacity" @input="setNumberText(form, 'daily_capacity', $event)" type="number" min="0.00000001" max="1000000000000" step="any" required></label><label class="im-field"><span>运输自然日 *</span><input v-model.number="form.transport_days" type="number" min="0" max="3650" step="1" required></label></div>
        <div class="im-fields"><label v-for="material in form.materials" :key="material.material_id" class="im-field"><span>{{ ws.materialName(material.material_id) }} · 采购周期（自然日） *</span><input v-model.number="material.procurement_days" :aria-label="`${ws.materialName(material.material_id)} 采购周期`" type="number" min="0" max="3650" step="1" required></label></div>
        <div class="im-actions"><button class="im-primary" type="submit">保存并更新本合同</button><span class="im-note">同时维护默认参数；其他合同单独确认更新</span></div>
      </fieldset>
      <button type="button" :disabled="ws.locked || draft.switching.value" @click="close">收起参数</button>
    </form>
  </Teleport>
</template>
