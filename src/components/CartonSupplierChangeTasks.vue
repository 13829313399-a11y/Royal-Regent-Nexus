<script setup lang="ts">
import { computed, onBeforeUnmount, onMounted, reactive, ref, watch } from 'vue'
import { cartonSupplierChangesApi as api, type SupplierChangeAction, type SupplierChangeTask, type SupplierChangeLine } from '@/api/cartonSupplierChanges'
import { getApiErrorMessage } from '@/lib/http'
import { createRandomUuid } from '@/lib/randomUuid'
import { factoryContexts } from '@/data/enterpriseMock'

const props = withDefaults(defineProps<{ factoryId?: string; factories?: { factory_id: string }[]; viewerKey?: string; internal?: boolean; readOnly?: boolean; sourceId?: string; sourceKinds?: SupplierChangeTask['source_kind'][]; embedded?: boolean; showClosed?: boolean }>(), { factoryId: '', internal: false, embedded: false, showClosed: undefined })
const emit = defineEmits<{ changed: []; 'pending-state': [state: { loading: boolean; error: string; counts: Record<SupplierChangeTask['source_kind'], number>; stats: { pending: number; read: number; cancellation: number; disputed: number; overdue: number } }]; 'update:showClosed': [value: boolean] }>()
const tasks = ref<SupplierChangeTask[]>([]), loading = ref(false), busy = ref(false), error = ref(''), success = ref('')
const localShowClosed = ref(false)
const showClosed = computed({ get: () => props.showClosed ?? localShowClosed.value, set: value => { localShowClosed.value = value; emit('update:showClosed', value) } })
const readError = ref('')
const dates = reactive<Record<string, string>>({}), reasons = reactive<Record<string, string>>({}), requests = new Map<string, string>()
const factories = computed(() => [...new Set(props.factories?.map(row => row.factory_id) ?? (props.factoryId ? [props.factoryId] : []))].sort())
const context = computed(() => JSON.stringify([factories.value, props.viewerKey, props.internal, props.sourceId]))
const scoped = computed(() => tasks.value.filter(row => !props.sourceId || row.source_id === props.sourceId))
// Category selection only filters presentation; the scope, drafts and polling stay mounted.
const selected = computed(() => scoped.value.filter(row => !props.sourceKinds || props.sourceKinds.includes(row.source_kind)))
const pending = computed(() => selected.value.filter(row => row.pending))
const visible = computed(() => showClosed.value ? selected.value : pending.value)
const pendingLabel = computed(() => loading.value ? '读取中…' : readError.value ? '暂不可用' : `${pending.value.length} 项待确认`)
watch(() => ({ loading: loading.value, error: readError.value, counts: {
  REGULAR: scoped.value.filter(row => row.pending && row.source_kind === 'REGULAR').length,
  SPECIAL: scoped.value.filter(row => row.pending && row.source_kind === 'SPECIAL').length,
  REPLENISHMENT: scoped.value.filter(row => row.pending && row.source_kind === 'REPLENISHMENT').length,
}, stats: {
  pending: pending.value.length,
  read: pending.value.filter(row => row.read).length,
  cancellation: pending.value.filter(row => row.is_cancellation).length,
  disputed: selected.value.filter(row => row.status === 'DISPUTED').length,
  overdue: pending.value.filter(row => row.overdue).length,
} }), state => emit('pending-state', state), { immediate: true })
const key = (row: SupplierChangeTask) => `${row.factory_id}:${row.source_kind}:${row.source_id}`
const factoryName = (factory: string) => factoryContexts.find(row => row.id === factory)?.name || factory
const labels: Record<string, string> = { READ: '已读，不代表同意', PENDING: '待明确确认', PARTIAL: '部分纸品已接单，仍待整单确认', DISPUTED: '有异议，暂停执行', ACCEPTED: '已同意接单', CANCEL_ACKNOWLEDGED: '已收到停止通知', CLOSED_WITHOUT_ACCEPTANCE: '已完成，历史未记录接单', CLOSED_BY_CANCELLATION: '原单已取消，沿停止通知核实', PENDING_ISSUE: '内部变更待生成', SUPPLIER_ORIGIN: '供应商原送货来源' }
const material = (row: Partial<SupplierChangeLine> | SupplierChangeLine['before_material']) => row ? [row.packaging_type, row.paper_quality, row.specification, row.dimension_unit].filter(Boolean).join(' · ') : ''
let generation = 0, readSequence = 0, controller = new AbortController(), timer: ReturnType<typeof setInterval> | undefined
watch(context, () => {
  generation++; readSequence++; controller.abort(); controller = new AbortController(); tasks.value = []; error.value = ''; readError.value = ''; success.value = ''; busy.value = false; loading.value = false; requests.clear()
  for (const name of Object.keys(dates)) delete dates[name]
  for (const name of Object.keys(reasons)) delete reasons[name]
  void load()
}, { immediate: true })
async function load() {
  const token = generation, scopes = factories.value, sequence = ++readSequence
  if (!scopes.length || busy.value) return
  loading.value = true
  try {
    const results = await Promise.all(scopes.map(factory => api.list(factory, props.internal, controller.signal)))
    if (token !== generation || sequence !== readSequence) return
    tasks.value = results.flatMap(result => result.items)
    for (const row of tasks.value) {
      if (!(key(row) in dates)) dates[key(row)] = row.promised_date || row.planned_date
      if (!(key(row) in reasons)) reasons[key(row)] = ''
    }
    error.value = ''
    readError.value = ''
  } catch (cause) { if (token === generation && sequence === readSequence) { readError.value = getApiErrorMessage(cause); error.value = readError.value } }
  finally { if (token === generation && sequence === readSequence) loading.value = false }
}
async function respond(row: SupplierChangeTask, action: SupplierChangeAction) {
  if (busy.value || props.internal || props.readOnly) return
  if (action === 'ACCEPT' && !dates[key(row)]) { error.value = '请填写承诺交期。'; return }
  if (action === 'DISPUTE' && !reasons[key(row)]?.trim()) { error.value = '请填写具体异议。'; return }
  const token = generation
  const body = { factory_id: row.factory_id, source_kind: row.source_kind, source_id: row.source_id, expected_revision: row.expected_revision, action,
    ...(action === 'ACCEPT' ? { promised_date: dates[key(row)] } : {}), ...(action === 'DISPUTE' ? { reason: reasons[key(row)]?.trim() } : {}) }
  const signature = JSON.stringify(body)
  if (!requests.has(signature)) requests.set(signature, createRandomUuid())
  readSequence++; loading.value = false; busy.value = true; error.value = ''; success.value = ''
  try {
    await api.respond({ ...body, request_id: requests.get(signature)! }, controller.signal)
    if (token !== generation) return
    requests.delete(signature)
    success.value = action === 'READ' ? '已记录查看，待办仍须明确回应。' : action === 'ACK_CANCEL' ? '已确认收到停止通知；费用及赔偿仍须另行协商。' : action === 'DISPUTE' ? '异议已保留，此版本暂停执行。' : '已确认本版本全部纸品及承诺交期。'
    busy.value = false
    await load()
    if (token === generation) emit('changed')
  } catch (cause) { if (token === generation) error.value = getApiErrorMessage(cause) }
  finally { if (token === generation) busy.value = false }
}
function refreshOnFocus() { if (!busy.value && !loading.value) void load() }
defineExpose({ refresh: load })
onMounted(() => { timer = setInterval(refreshOnFocus, 45000); window.addEventListener('focus', refreshOnFocus) })
onBeforeUnmount(() => { generation++; controller.abort(); if (timer) clearInterval(timer); window.removeEventListener('focus', refreshOnFocus) })
</script>

<template>
  <section :class="embedded ? 'min-w-0' : 'rounded-xl border border-amber-200 bg-amber-50/60 p-4'" aria-label="供应商变更待办">
    <div class="flex flex-wrap items-center justify-between gap-2">
      <component :is="embedded ? 'p' : 'h2'" class="text-sm font-semibold text-slate-900"><template v-if="!embedded">{{ internal ? '供应商待确认跟进' : '订单与变更待办' }} · </template>{{ pendingLabel }}<span v-if="!loading && !readError && pending.some(row => row.overdue)" class="ml-2 text-xs text-amber-800">隔日未确认 {{ pending.filter(row => row.overdue).length }} 项</span></component>
      <div class="flex flex-wrap items-center gap-3 text-xs"><label><input v-model="showClosed" type="checkbox" class="mr-1" aria-label="显示已完成回执">显示已完成回执</label><button type="button" :disabled="busy || loading" class="rounded-lg border border-slate-300 bg-white px-3 py-2 disabled:opacity-40" @click="load">刷新待办</button></div>
    </div>
    <p class="mt-2 text-xs text-slate-600">已读只表示查看。新订单、数量、交期及资料变更须明确同意或提出异议；停止通知单独确认收到，费用与赔偿仍须另行协商。</p>
    <p v-if="error" role="alert" class="mt-3 text-sm text-red-700">待办读取或回应失败：{{ error }}；请刷新核对，勿据此认定已同意。</p>
    <p v-if="success" role="status" class="mt-3 text-sm text-teal-800">{{ success }}</p>
    <p v-if="loading && !tasks.length" role="status" class="mt-3 text-xs text-slate-500">正在读取版本回执…</p>
    <p v-else-if="!visible.length && !error" class="mt-3 text-xs text-slate-600">{{ showClosed ? '暂无可查看的版本回执。' : '当前没有待明确确认的版本。' }}</p>
    <div class="mt-3 divide-y" :class="embedded ? 'divide-slate-200' : 'divide-amber-200'">
      <details v-for="row in visible" :key="key(row)" class="py-3">
        <summary class="cursor-pointer break-words text-xs leading-6 [overflow-wrap:anywhere]"><b>{{ factoryName(row.factory_id) }} · {{ row.document_no }}</b><span class="ml-2">{{ row.source_kind === 'SPECIAL' ? '样板 / 杂单' : row.source_kind === 'REPLENISHMENT' ? `补单 · ${row.responsibility === 'SUPPLIER' ? '供应商责任' : '我方责任'}` : '正式订单' }}</span><span class="ml-2 font-semibold" :class="row.is_cancellation || row.status === 'DISPUTED' ? 'text-red-800' : 'text-amber-900'">{{ row.is_cancellation && row.pending ? '待确认收到停止通知' : labels[row.status] || row.status }}</span><span class="ml-2 text-slate-500">{{ row.read ? '已读，回执单独记录' : '未记录查看' }}<template v-if="row.overdue"> · 已隔 {{ row.age_days }} 天</template></span></summary>
        <div class="mt-3 space-y-3 text-xs">
          <p class="break-all text-slate-600">来源 {{ row.order_no }} · 生成 {{ row.created_at.slice(0, 16).replace('T', ' ') }}</p>
          <p class="text-slate-600">以下对比上次发布的版本；上次发布不代表供应商已经同意。</p>
          <p>计划交期：{{ row.before_date || '首次下单' }} → <b>{{ row.planned_date || '待核实' }}</b><span v-if="row.material_changed" class="ml-2 text-amber-800">印刷资料版本有变化，请查看本单箱唛</span></p>
          <p v-if="row.customer_due_date && row.customer_due_date !== row.before_customer_due_date">客户交期：{{ row.before_customer_due_date || '首次记录' }} → <b>{{ row.customer_due_date }}</b></p>
          <p v-if="row.change_reason" class="whitespace-pre-wrap break-words text-slate-700">内部变更说明：{{ row.change_reason }}</p>
          <div v-for="line in row.lines" :key="line.id" class="grid gap-1 border-l-2 border-amber-200 pl-3 sm:grid-cols-2"><div class="min-w-0 break-words"><b>{{ material(line) }}</b><p v-if="line.before_material && material(line.before_material) && material(line.before_material) !== material(line)" class="text-amber-900">原资料：{{ material(line.before_material) }}</p></div><p class="tabular-nums sm:text-right">数量 {{ line.before_quantity }} → <b>{{ line.quantity }} {{ line.unit }}</b></p></div>
          <p v-if="row.reason" class="whitespace-pre-wrap break-words text-red-800">供应商异议：{{ row.reason }}</p>
          <p v-if="row.responded_at" class="text-slate-600">回应 {{ row.responded_by }} · {{ row.responded_at }}<span v-if="row.promised_date"> · 承诺 {{ row.promised_date }}</span></p>
          <details v-if="row.publication_history?.length" class="rounded-lg border border-slate-200 bg-white/70 p-3">
            <summary class="cursor-pointer font-semibold">历次发布与回执（{{ row.publication_history.length }}）</summary>
            <div v-for="entry in row.publication_history" :key="entry.source_id" class="mt-3 space-y-1 border-t border-slate-200 pt-2">
              <p class="break-all"><b>{{ entry.document_no }}</b> · {{ entry.created_at }} · {{ entry.superseded ? '已被后续版本替代，只读' : '本次版本' }}</p>
              <p>{{ entry.status === 'PENDING' ? '未记录明确同意' : labels[entry.status] || entry.status }} · {{ entry.read ? '已读' : '未记录已读' }}<span v-if="entry.responded_at"> · {{ entry.responded_by }} {{ entry.responded_at }}</span></p>
              <p>计划交期 {{ entry.planned_date || '未记录' }}</p>
              <p v-for="paper in entry.lines" :key="paper.id" class="break-words">{{ paper.packaging_type }} · {{ paper.paper_quality }} · {{ paper.specification }} · {{ paper.quantity }} {{ paper.unit }}</p>
              <p v-if="entry.reason" class="whitespace-pre-wrap break-words text-red-800">异议：{{ entry.reason }}</p>
              <details v-if="entry.response_history?.length" class="pl-3">
                <summary class="cursor-pointer text-slate-600">本版本回应轨迹</summary>
                <p v-for="(response, index) in entry.response_history" :key="index" class="mt-1 whitespace-pre-wrap break-words text-slate-700">{{ labels[response.status] || response.status }} · {{ response.actor_name }} · {{ response.created_at }}<span v-if="response.promised_date"> · 承诺 {{ response.promised_date }}</span><span v-if="response.reason"> · {{ response.reason }}</span></p>
              </details>
            </div>
          </details>
          <template v-if="!internal && !readOnly && row.pending">
            <button v-if="!row.read" type="button" :disabled="busy || loading" class="rounded-lg border border-slate-300 bg-white px-3 py-2 disabled:opacity-40" @click="respond(row, 'READ')">记录已读（不代表同意）</button>
            <div v-if="row.can_respond" class="flex flex-wrap items-end gap-3">
              <template v-if="!row.is_cancellation"><label class="block space-y-1"><span class="block font-semibold">承诺交期 *</span><input v-model="dates[key(row)]" type="date" :aria-label="`${row.document_no}承诺交期`" :disabled="busy" class="h-9 rounded-lg border border-slate-300 bg-white px-3 focus:border-teal-600 focus:ring-2 focus:ring-teal-600/20"></label><button type="button" :disabled="busy || loading" class="h-9 rounded-lg bg-teal-700 px-3 font-semibold text-white disabled:opacity-40" @click="respond(row, 'ACCEPT')">{{ row.status === 'DISPUTED' ? '重新同意本版本全部纸品' : '同意本版本全部纸品并接单' }}</button></template>
              <button v-else type="button" :disabled="busy || loading" class="h-9 rounded-lg border border-red-300 bg-white px-3 font-semibold text-red-800 disabled:opacity-40" @click="respond(row, 'ACK_CANCEL')">确认收到停止通知</button>
              <label class="block min-w-0 flex-1 space-y-1"><span class="block font-semibold">异议说明</span><textarea v-model="reasons[key(row)]" :aria-label="`${row.document_no}异议说明`" :disabled="busy" rows="2" maxlength="1000" class="w-full rounded-lg border border-slate-300 bg-white px-3 py-2 focus:border-teal-600 focus:ring-2 focus:ring-teal-600/20" /></label><button type="button" :disabled="busy || loading" class="h-9 rounded-lg border border-amber-400 bg-white px-3 font-semibold text-amber-900 disabled:opacity-40" @click="respond(row, 'DISPUTE')">提出异议并暂停执行</button>
            </div>
            <p v-else class="text-slate-600">{{ row.status === 'PENDING_ISSUE' ? '内部变更尚未发布，请等待最新采购版本；旧承诺暂停执行。' : '当前账号可查看；请由有供应商接单确认权限的人员明确回应。' }}</p>
          </template>
          <p v-else-if="readOnly && row.pending" class="text-slate-600">本页只读；请返回订单行或供应商协同工作台处理接单、异议及停止通知。</p>
          <p v-else-if="internal && row.pending" class="font-semibold text-amber-900">{{ row.status === 'PENDING_ISSUE' ? '请按此单号生成最新供应商采购版本；发布后再取得明确回执。' : '请按以上厂区、单号和差异联系供应商核实，待明确回执后继续执行。' }}</p>
        </div>
      </details>
    </div>
  </section>
</template>
