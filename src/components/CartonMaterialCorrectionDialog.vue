<script setup lang="ts">
import { computed, nextTick, onBeforeUnmount, reactive, ref, watch } from 'vue'
import { materialCorrectionApi as api, type CorrectionContext, type CorrectedMaterial, type CorrectionCreate, type CorrectionAction, type MaterialCorrection } from '@/api/cartonMaterialCorrection'
import { useAuthStore } from '@/stores/auth'
import { getApiErrorMessage } from '@/lib/http'
import { createRandomUuid } from '@/lib/randomUuid'
const props = defineProps<{ factoryId: string; orderNo: string; supplier?: boolean; recordId?: string }>()
const emit = defineEmits<{ close: []; changed: [] }>()
const auth = useAuthStore(), dialog = ref<HTMLElement | null>(null)
const data = ref<CorrectionContext | null>(null), records = ref<MaterialCorrection[]>([])
const lineId = ref(''), reason = ref('填错了'), note = ref(''), verified = ref(false), error = ref(''), success = ref('')
const busy = ref(false), loading = ref(false)
const after = reactive<CorrectedMaterial>({ packaging_type: '', paper_quality: '', specification: '', dimension_unit: 'cm' })
const labels = { packaging_type: '纸品类型', paper_quality: '纸质', specification: '规格', dimension_unit: '尺寸单位' }
const states = { PENDING: '待供应商确认', RETURNED: '退回仓库核实', APPROVED: '已确认生效', WITHDRAWN: '已撤回' }
const canWrite = computed(() => {
  void auth.authorizationVersion
  if (!auth.currentUser) return false
  return props.supplier ? auth.can('carton_supplier:approve', props.factoryId, '*') :
  ['carton', 'pmc-warehouse'].some(d => auth.can('carton_procurement:order_write', props.factoryId, d)) &&
  ['carton', 'pmc-warehouse'].some(d => auth.can('carton_procurement:order_adjust', props.factoryId, d) || auth.can('carton_procurement:inventory_write', props.factoryId, d))
})
const viewer = computed(() => JSON.stringify([props.factoryId, props.orderNo, props.recordId, auth.currentUser?.id, auth.currentUser?.identity?.effective_context_key, auth.currentUser?.identity?.employment_epoch, auth.authorizationVersion, canWrite.value]))
const current = computed(() => props.supplier ? records.value.find(row => row.id === props.recordId) : records.value.find(row => ['PENDING', 'RETURNED'].includes(row.status)))
const before = computed(() => data.value?.lines.find(line => line.id === lineId.value))
const canCreate = computed(() => !props.supplier && !!data.value?.issue_id && ['PENDING_SUPPLIER','PARTIALLY_RECEIVED'].includes(data.value?.status ?? '') && !current.value)
const pending = ref<{ kind: 'create'; body: CorrectionCreate } | { kind: 'action'; id: string; body: CorrectionAction } | null>(null)
const locked = computed(() => busy.value || loading.value || !!pending.value || !canWrite.value)
let generation = 0, controller = new AbortController()
const returnFocus = document.activeElement instanceof HTMLElement ? document.activeElement : null
watch(lineId, () => { if (before.value) Object.assign(after, { packaging_type: before.value.packaging_type, paper_quality: before.value.paper_quality, specification: before.value.specification, dimension_unit: before.value.dimension_unit === 'in' ? 'inch' : before.value.dimension_unit || '' }) })
async function load() {
  const token = generation; loading.value = true
  try {
    if (props.supplier) {
      const rows = await api.supplierList(props.factoryId, controller.signal)
      if (token !== generation) return
      records.value = rows.filter(row => row.order_no === props.orderNo)
    } else {
      const value = await api.context(props.factoryId, props.orderNo, controller.signal)
      if (token !== generation) return
      data.value = value; records.value = value.records; lineId.value = value.lines[0]?.id || ''
    }
  } catch (cause) { if (token === generation) error.value = getApiErrorMessage(cause) }
  finally { if (token === generation) loading.value = false }
}
watch(viewer, () => { generation++; controller.abort(); controller = new AbortController(); data.value = null; records.value = []; pending.value = null; lineId.value = ''; reason.value = '填错了'; note.value = ''; verified.value = false; error.value = ''; success.value = ''; busy.value = false; void load() }, { immediate: true })
async function submit(action?: CorrectionAction['action']) {
  if (busy.value || !canWrite.value || loading.value) return
  error.value = ''; success.value = ''
  if (!pending.value) {
    if (action) {
      if (!current.value) { error.value = '请刷新并选择需要处理的更正申请'; return }
      if (action !== 'RETURN' && !verified.value) { error.value = '请先勾选核实确认'; return }
      pending.value = { kind: 'action', id: current.value.id, body: { factory_id: props.factoryId, request_id: createRandomUuid(), expected_revision: current.value.revision, action, note: note.value.trim(), verified: verified.value } }
    } else {
      if (!data.value || !canCreate.value || !before.value) { error.value = '请选择需要更正的纸品'; return }
      pending.value = { kind: 'create', body: { factory_id: props.factoryId, request_id: createRandomUuid(), expected_revision: data.value.revision, issue_id: data.value.issue_id, order_line_id: lineId.value, after: { ...after }, reason: reason.value.trim() || '填错了' } }
    }
  }
  const token = generation, operation = pending.value
  busy.value = true
  try {
    if (operation.kind === 'create') await api.create(props.orderNo, operation.body, controller.signal)
    else await api.act(operation.id, operation.body, !!props.supplier, controller.signal)
    if (token !== generation) return
    pending.value = null; note.value = ''; verified.value = false
    success.value = operation.kind === 'create' ? '已提交供应商确认，原资料保留，涉及纸品已暂停发货和正式入库。' : '处理已保存，双方资料及待办已更新。'
    emit('changed'); await load()
  } catch (cause) {
    if (token !== generation) return
    error.value = getApiErrorMessage(cause)
    const status = (cause as { response?: { status?: number } }).response?.status
    if (status && status >= 400 && status < 500) pending.value = null
  } finally { if (token === generation) busy.value = false }
}
function close() { if (!busy.value) emit('close') }
function keys(event: KeyboardEvent) {
  if (event.key === 'Escape') { event.stopPropagation(); close() }
  if (event.key !== 'Tab') return
  const nodes = [...dialog.value!.querySelectorAll<HTMLElement>('button:not(:disabled), input:not(:disabled), select:not(:disabled), textarea:not(:disabled)')]
  if (event.shiftKey && document.activeElement === nodes[0]) { event.preventDefault(); nodes.at(-1)?.focus() }
  else if (!event.shiftKey && document.activeElement === nodes.at(-1)) { event.preventDefault(); nodes[0]?.focus() }
}
void nextTick(() => dialog.value?.querySelector<HTMLElement>('button')?.focus())
onBeforeUnmount(() => { generation++; controller.abort(); returnFocus?.focus() })
</script>
<template>
  <div class="fixed inset-0 z-[100] flex items-center justify-center bg-slate-950/45 p-4" @click.self="close">
    <section ref="dialog" role="dialog" aria-modal="true" aria-label="纸品资料更正" class="max-h-[90vh] w-full max-w-3xl overflow-auto rounded-2xl bg-white p-5 shadow-xl" @keydown="keys">
      <div class="flex items-start justify-between gap-3"><div><h2 class="text-lg font-bold">纸品资料更正</h2><p class="mt-1 text-xs text-slate-500">仓库申请 → 供应商确认 → 双方同时生效。采购数量、单价和已入库记录保留。</p></div><button type="button" :disabled="busy" aria-label="关闭纸品资料更正" @click="close">关闭</button></div>
      <p v-if="error" role="alert" class="mt-3 rounded-lg bg-red-50 p-3 text-sm text-red-700">{{ error }}</p>
      <p v-if="success" role="status" class="mt-3 rounded-lg bg-teal-50 p-3 text-sm text-teal-800">{{ success }}</p>
      <p v-if="loading" class="py-4 text-sm">正在核对当前资料…</p>
      <div v-if="current" class="mt-4 rounded-xl border border-amber-200 bg-amber-50 p-4">
        <p class="font-bold">{{ current.contract_no }} · {{ current.item_no }} · {{ states[current.status] }}</p>
        <p class="mt-2 whitespace-pre-wrap text-sm">更正原因：{{ current.reason }}</p>
        <table class="mt-3 w-full text-left text-sm"><thead><tr><th class="p-2">项目</th><th class="p-2">原资料</th><th class="p-2">申请更正为</th></tr></thead><tbody><tr v-for="(label, key) in labels" :key="key" class="border-t border-amber-200"><th class="p-2 font-normal">{{ label }}</th><td class="break-all p-2">{{ current.before[key] || '未填写' }}</td><td class="break-all p-2 font-semibold text-teal-800">{{ current.after[key] }}</td></tr></tbody></table>
        <p class="mt-2 text-xs">{{ current.created_by_name }} · {{ current.created_at }}<span v-if="current.response_note">；处理说明：{{ current.response_note }}</span></p>
        <div v-if="['PENDING','RETURNED'].includes(current.status)" class="mt-3 text-sm">
          <p class="text-amber-800">此纸品暂停发货和正式入库。已到货先保留验收凭证，资料及实物核实一致后再入库。</p>
          <label class="mt-3 block">处理说明（选填）<textarea v-model="note" :disabled="locked" aria-label="更正处理说明" rows="2" maxlength="1000" class="mt-1 w-full rounded-lg border bg-white p-2" /></label>
          <label class="mt-2 flex items-start gap-2"><input v-model="verified" type="checkbox" :disabled="locked" class="mt-1"><span>{{ supplier ? '已核对更正内容；如已生产或到货，已确认实物与更正资料一致。' : '已核实可以撤回申请，恢复原资料执行；退回后需重新申请的，撤回后立即重新填写。' }}</span></label>
          <div class="mt-3 flex flex-wrap gap-2"><template v-if="supplier && current.status === 'PENDING'"><button type="button" :disabled="locked" class="rounded-lg bg-teal-700 px-4 py-2 text-white disabled:opacity-40" @click="submit('APPROVE')">同意更正并生效</button><button type="button" :disabled="locked" class="rounded-lg border bg-white px-4 py-2 disabled:opacity-40" @click="submit('RETURN')">退回仓库核实</button></template><button v-else-if="!supplier" type="button" :disabled="locked" class="rounded-lg border bg-white px-4 py-2 disabled:opacity-40" @click="submit('WITHDRAW')">撤回申请</button></div>
        </div>
      </div>
      <p v-if="!loading && data && !canCreate && !current && !supplier" class="mt-4 rounded-lg bg-slate-50 p-3 text-sm text-slate-600">{{ data.status === 'COMPLETED' ? '订单已完成。已入库资料需按原收料冲销及更正验收流程处理；此处可查看历史记录。' : '此入口适用于已下单、仍有待收需求的订单，请先核对订单状态与采购版本。' }}</p>
      <form v-if="canCreate" class="mt-4 space-y-3" @submit.prevent="submit()"><label class="block text-sm">需要更正的纸品<select v-model="lineId" :disabled="locked" aria-label="更正纸品" class="mt-1 h-10 w-full rounded-lg border px-2"><option v-for="line in data?.lines" :key="line.id" :value="line.id">{{ line.packaging_type }} · {{ line.paper_quality }} · {{ line.specification }} {{ line.dimension_unit || '单位未填写' }}</option></select></label>
        <div class="grid gap-3 sm:grid-cols-2"><label v-for="key in (['packaging_type','paper_quality','specification'] as const)" :key="key" class="text-sm">{{ labels[key] }}<input v-model="after[key]" :aria-label="`更正后${labels[key]}`" :disabled="locked" :maxlength="key === 'packaging_type' ? 64 : key === 'paper_quality' ? 128 : 255" required class="mt-1 h-10 w-full rounded-lg border px-3"></label><label class="text-sm">尺寸单位<select v-model="after.dimension_unit" aria-label="更正后尺寸单位" required :disabled="locked" class="mt-1 h-10 w-full rounded-lg border px-3"><option value="" disabled>请选择单位</option><option value="cm">cm</option><option value="inch">英寸</option><option value="mm">mm</option></select></label></div>
        <p class="text-xs text-amber-800">单位录错时保留正确数字并改单位；实际换算时请同时填写换算后的数字，此处不自动乘除。</p>
        <label class="block text-sm">更正原因（选填）<textarea v-model="reason" aria-label="纸品更正原因" :disabled="locked" maxlength="1000" placeholder="填错了" rows="2" class="mt-1 w-full rounded-lg border p-2" /></label><button :disabled="locked" class="rounded-lg bg-teal-700 px-4 py-2 text-sm text-white disabled:opacity-40">提交供应商确认</button>
      </form>
      <div v-if="pending && !busy" class="mt-3 rounded-lg bg-blue-50 p-3 text-sm">提交结果尚未确认，填写内容已锁定。<button type="button" class="ml-2 font-bold text-teal-700" @click="submit()">按原请求重试</button></div>
      <details v-if="records.length" class="mt-5 border-t pt-3"><summary class="cursor-pointer text-sm font-bold">更正记录（{{ records.length }}）</summary><article v-for="row in [...records].reverse()" :key="row.id" class="mt-3 rounded-lg border p-3 text-xs"><b>{{ states[row.status] }} · {{ row.before.packaging_type }} → {{ row.after.packaging_type }}</b><p class="mt-1">{{ row.before.paper_quality }} · {{ row.before.specification }} {{ row.before.dimension_unit }} → {{ row.after.paper_quality }} · {{ row.after.specification }} {{ row.after.dimension_unit }}</p><p class="mt-1">{{ row.reason }}；{{ row.created_by_name }} · {{ row.created_at }}</p><p v-if="row.response_note" class="mt-1">{{ row.resolved_by_name }} · {{ row.resolved_at }}：{{ row.response_note }}</p><p v-if="row.corrected_document_no" class="mt-1 text-teal-700">更正采购单：{{ row.corrected_document_no }}，数量不增加</p></article></details>
    </section>
  </div>
</template>
