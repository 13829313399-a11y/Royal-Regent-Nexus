<script setup lang="ts">
import { computed, onBeforeUnmount, onMounted, reactive, ref, toRaw } from 'vue'
import { createQcRequestId, qcInspectionApi, type QcInspectionEventPayload, type QcInspectionOrder } from '@/api/qcInspection'
import { Button } from '@/components/ui/button'
import { getApiErrorMessage } from '@/lib/http'
import { useQcInspectionWorkspace } from './context'
import { inspectionToday } from './schedule'
import { bulkResultPayload, inspectionResults, inspectionTypes, type BulkResultForm } from './bulkResults'
const props = defineProps<{ orders: QcInspectionOrder[] }>()
const emit = defineEmits<{ close: []; saved: [ids: string[]] }>()
const context = useQcInspectionWorkspace()
const dialog = ref<HTMLDialogElement>()
const busy = ref(false)
const started = ref(false)
const error = ref('')
const form = reactive<BulkResultForm>({ date: inspectionToday(), result: '', inspector: '', note: '', eventType: '' })
const entries = reactive(props.orders.map(order => ({ order: structuredClone(toRaw(order)), status: 'pending', error: '' })))
const tasks = new Map<string, { payload: QcInspectionEventPayload; eventId?: string; eventRevision?: number; requestId: string }>()
const completed = computed(() => entries.filter(entry => entry.status === 'success').length)
const remaining = computed(() => entries.length - completed.value)
let disposed = false
onMounted(() => dialog.value?.showModal())
onBeforeUnmount(() => { disposed = true })
function close() { if (!busy.value) emit('close') }
async function save() {
  if (busy.value || !context.canResultWrite.value || !remaining.value) return
  if (!form.date || !inspectionResults[form.result] || !form.eventType || form.note.trim().length < 2) { error.value = '请填写实际验货日期、验货结果、新记录验货类型和至少两个字的登记说明。'; return }
  started.value = true; busy.value = true; error.value = ''
  const saved: string[] = []
  for (const entry of entries) {
    if (disposed || !context.canResultWrite.value) break
    if (entry.status === 'success') continue
    entry.status = 'saving'; entry.error = ''
    try {
      let task = tasks.get(entry.order.id)
      if (!task) {
        const events = await qcInspectionApi.listInspectionEvents(entry.order.id, entry.order.factory_id)
        if (disposed) break
        const latest = [...events].sort((a, b) => b.attempt_no - a.attempt_no)[0]
        task = { payload: bulkResultPayload(toRaw(entry.order), { ...form }, latest), eventId: latest?.id, eventRevision: latest?.revision, requestId: createQcRequestId() }
        tasks.set(entry.order.id, task)
      }
      if (task.eventId) await qcInspectionApi.updateInspectionEvent(entry.order.id, task.eventId, { ...task.payload, expected_revision: task.eventRevision!, reason: form.note.trim() }, task.requestId)
      else await qcInspectionApi.createInspectionEvent(entry.order.id, task.payload, task.requestId)
      entry.status = 'success'; saved.push(entry.order.id)
    } catch (cause) { entry.status = 'failed'; entry.error = getApiErrorMessage(cause) }
  }
  busy.value = false
  if (saved.length) emit('saved', saved)
}
</script>
<template>
  <dialog ref="dialog" class="qc-dialog" aria-labelledby="qc-bulk-result-title" @cancel.prevent="close">
    <header class="qc-dialog-header"><div><h2 id="qc-bulk-result-title">批量填写验货结果</h2><p class="qc-muted">已选择 {{ entries.length }} 条订单，请核对下方清单。相同结果可一次填写，不同结果请分批处理。</p></div><Button variant="ghost" :disabled="busy" @click="close">关闭</Button></header>
    <form class="qc-dialog-body" @submit.prevent="save">
      <fieldset :disabled="started" class="qc-form-grid">
        <label class="qc-field"><span>实际验货日期 *</span><input v-model="form.date" type="date" required></label>
        <label class="qc-field"><span>验货结果 *</span><select v-model="form.result" required><option value="">请选择结果</option><option v-for="(label, value) in inspectionResults" :key="value" :value="value">{{ label }}</option></select></label>
        <label class="qc-field"><span>验货员</span><input v-model="form.inspector" maxlength="128" placeholder="留空保留已有验货员"></label>
        <label class="qc-field"><span>新记录验货类型 *</span><select v-model="form.eventType" required><option value="">请选择类型</option><option v-for="(label, value) in inspectionTypes" :key="value" :value="value">{{ label }}</option></select><small>已有待验记录沿用原类型。</small></label>
        <label class="qc-field"><span>登记说明 *</span><textarea v-model="form.note" required minlength="2" maxlength="500" rows="2" placeholder="本次验货说明" /></label>
      </fieldset>
      <p class="qc-notice">提交后订单移出待验排期，可在全部验货记录中查看。异常结果会生成问题记录；缺陷、责任人及处置明细可进入订单或问题处理补充。</p>
      <p v-if="error" role="alert" class="qc-error">{{ error }}</p>
      <p v-if="started" role="status" class="qc-muted">已保存 {{ completed }} / {{ entries.length }} 条。{{ busy ? '正在逐条保存…' : remaining ? '未成功的订单保留在下方；重试不会重复登记成功项。数据冲突请关闭后刷新排期重新核对。' : '本批验货结果已全部保存。' }}</p>
      <div class="qc-table-scroll max-h-72"><table class="qc-table"><thead><tr><th>客户 / 合同</th><th>PO / 货号</th><th>处理情况</th></tr></thead><tbody><tr v-for="entry in entries" :key="entry.order.id"><td>{{ entry.order.customer_name }}<small>{{ entry.order.sales_contract_no }}</small></td><td>{{ entry.order.customer_po_no }}<small>{{ entry.order.customer_item_no }}</small></td><td>{{ { pending: '待提交', saving: '保存中', success: '已保存', failed: '未成功' }[entry.status] }}<small v-if="entry.error" class="!text-red-700">{{ entry.error }}</small></td></tr></tbody></table></div>
      <footer class="qc-dialog-footer"><Button type="button" variant="outline" :disabled="busy" @click="close">{{ started ? '关闭' : '取消' }}</Button><Button v-if="remaining" type="submit" :disabled="busy || !context.canResultWrite.value">{{ busy ? '正在保存…' : started ? `重试未成功的 ${remaining} 条` : `确认提交 ${entries.length} 条结果` }}</Button></footer>
    </form>
  </dialog>
</template>
