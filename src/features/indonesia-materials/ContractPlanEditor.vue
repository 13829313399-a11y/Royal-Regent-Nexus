<script setup lang="ts">
import { computed, nextTick, ref } from 'vue'
import type { Data, MaterialRecord } from '@/api/indonesiaMaterials'
import { useMaterials } from './workspace'
import { useMaterialDraft } from './useDraft'
import { recordDraftId, recordRef, restoreRecord } from './draftPersistence'
import { setNumberText } from './forms'
import { focusFollowup } from './focusFollowup'
import { planningMaterials } from './planning'
const emit = defineEmits<{ select: [id: string] }>()
const ws = useMaterials()
const targetReady = ref(false)
const editing = ref<MaterialRecord>(), form = ref<Data | null>(null), host = ref<HTMLElement | null>(null)
const catalog = computed(() => {
  const board = ws.board.find(row => row.id === editing.value?.id)
  return board ? planningMaterials(board, ws.records) : undefined
})
const stale = computed(() => form.value && catalog.value && (!form.value.sync_materials
  || form.value.product_version !== catalog.value.product?.version
  || catalog.value.materials.length !== form.value.materials.length
  || catalog.value.materials.some(m => !m || !form.value!.materials.some((entry: Data) => entry.material_id === m.id && entry.expected_version === m.version))))
function loadLatest() {
  if (!form.value || !catalog.value?.product || catalog.value.materials.some(m => !m) || ws.locked || !ws.canWrite) return
  const previous: Data[] = form.value.materials
  form.value = { ...form.value, sync_materials: true, product_version: catalog.value.product.version,
    materials: catalog.value.materials.map(m => ({ material_id: m!.id, expected_version: m!.version,
      procurement_days: previous.find(entry => entry.material_id === m!.id)?.procurement_days ?? m!.data.procurement_days ?? '' })) }
}
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
  const { product, materials } = planningMaterials(board, ws.records)
  if (!product || !materials.length || materials.some(m => !m)) { ws.error = '请先补齐货号与物料用量，再生成合同需求。'; return }
  const wasReady = targetReady.value
  targetReady.value = false
  const opened = await draft.openRecord(recordDraftId('planning', 'edit', id), () => {
    editing.value = order
    form.value = { product_id: product.id, product_version: product.version, sync_materials: true, daily_capacity: product.data.daily_capacity ?? '', transport_days: product.data.transport_days ?? 25,
      materials: materials.map(material => ({ material_id: material!.id, expected_version: material!.version, procurement_days: material!.data.procurement_days ?? '' })) }
  })
  await nextTick()
  if (opened) { emit('select', id); await nextTick(); targetReady.value = true; await nextTick(); focusFollowup(host.value) }
  else targetReady.value = wasReady
}
async function save() {
  if (!form.value || !editing.value || stale.value) return
  const id = editing.value.id
  const payload = { ...form.value, materials: form.value.materials.map((m: Data) => ({ ...m, procurement_days: m.procurement_days === '' ? null : m.procurement_days })) }
  if (await draft.run('order_plan_save', payload, editing.value, () => { form.value = null; editing.value = undefined })) {
    ws.notice = '本合同计划与物料已更新，回料模板可下载最新清单。'
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
        <div v-if="stale" class="im-inline" role="status"><span>资料已变化，载入后保留已填参数并补齐新增物料。</span><button type="button" @click="loadLatest">载入最新物料与版本</button></div>
        <p v-if="catalog?.addedIds.length" class="im-note">本次补入 {{ catalog.addedIds.length }} 种新物料；采购周期可稍后补填，不影响同步物料及下载回料表。</p>
        <div class="im-fields"><label class="im-field"><span>日产能 *</span><input :value="form.daily_capacity" @input="setNumberText(form, 'daily_capacity', $event)" type="number" min="0.00000001" max="1000000000000" step="any" required></label><label class="im-field"><span>运输自然日 *</span><input v-model.number="form.transport_days" type="number" min="0" max="3650" step="1" required></label></div>
        <div class="im-fields"><label v-for="material in form.materials" :key="material.material_id" class="im-field"><span>{{ ws.materialName(material.material_id) }} · 采购周期（自然日）</span><input v-model.number="material.procurement_days" :aria-label="`${ws.materialName(material.material_id)} 采购周期`" type="number" min="0" max="3650" step="1" placeholder="可稍后补填"></label></div>
        <div class="im-actions"><button class="im-primary" type="submit" :disabled="!!stale">保存并更新本合同</button><span class="im-note">同时维护默认参数；其他合同单独确认更新</span></div>
      </fieldset>
      <button type="button" :disabled="ws.locked || draft.switching.value" @click="close">收起参数</button>
    </form>
  </Teleport>
</template>
