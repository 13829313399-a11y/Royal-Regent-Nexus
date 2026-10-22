<script setup lang="ts">
import { computed, onBeforeUnmount, ref, watch } from 'vue'
import { Button } from '@/components/ui/button'
import StatusPill from '@/components/common/StatusPill.vue'
import { cartonScheduleCoverageApi as api, scheduleMissingStatusLabels as statusLabels, type ScheduleCoverageWorkspace, type ScheduleMissingCase, type ScheduleMissingDecision } from '@/api/cartonScheduleCoverage'
import { createRandomUuid } from '@/lib/randomUuid'
import { getApiErrorMessage } from '@/lib/http'
import '@/features/carton-procurement/layout.css'

const props = defineProps<{ factoryId: string; customerCode?: string; viewerKey?: string; search?: string }>()
const emit = defineEmits<{ 'update:customerCode': [value: string]; source: [batchId: string]; changed: [customerCode: string] }>()
const workspace = ref<ScheduleCoverageWorkspace | null>(null), selected = ref<ScheduleMissingCase | null>(null)
const loading = ref(false), busy = ref(false), error = ref(''), message = ref(''), showHistory = ref(false), offset = ref(0)
const decision = ref<ScheduleMissingDecision>('KEEP_REQUIRED'), reason = ref('')
const decisions = computed<ScheduleMissingDecision[]>(() => !selected.value?.can_review ? [] : selected.value.status === 'PENDING' ? ['KEEP_REQUIRED', 'SOURCE_OMISSION', 'NO_LONGER_REQUIRED'] : ['KEEP_REQUIRED', 'SOURCE_OMISSION', 'NO_LONGER_REQUIRED'].includes(selected.value.status) ? ['REOPEN'] : [])
const decisionLabel = (value: string) => value === 'REOPEN' ? '重新设为待核实（更正此前结论）' : statusLabels[value as keyof typeof statusLabels] || value
const context = computed(() => JSON.stringify([props.factoryId, props.customerCode, props.viewerKey]))
const rows = computed(() => workspace.value?.missing.items ?? [])
const total = computed(() => workspace.value?.missing.total ?? 0)
const limit = 20
let generation = 0, sequence = 0, controller = new AbortController(), timer: ReturnType<typeof setTimeout> | undefined
const requests = new Map<string, string>()
watch(context, () => {
  generation++; sequence++; controller.abort(); controller = new AbortController(); requests.clear(); workspace.value = null; selected.value = null
  offset.value = 0; busy.value = false; reason.value = ''; message.value = ''; error.value = ''; void load()
}, { immediate: true, flush: 'sync' })
watch([showHistory, () => props.search], () => {
  if (timer) clearTimeout(timer)
  sequence++; workspace.value = null; selected.value = null; offset.value = 0; reason.value = ''
  timer = setTimeout(() => { void load() }, 250)
})
async function load() {
  const token = generation, read = ++sequence
  loading.value = true; error.value = ''
  try {
    const result = await api.workspace(props.factoryId, { ...(props.customerCode && props.customerCode !== '全部客户' ? { customer_code: props.customerCode } : {}), status: showHistory.value ? 'ALL' : 'PENDING', keyword: props.search?.trim() || '', limit, offset: offset.value }, controller.signal)
    if (token === generation && read === sequence) workspace.value = result
  } catch (cause) { if (token === generation && read === sequence) { workspace.value = null; error.value = getApiErrorMessage(cause) } }
  finally { if (token === generation && read === sequence) loading.value = false }
}
async function open(row: ScheduleMissingCase) {
  if (loading.value || busy.value) return
  const token = generation, read = ++sequence
  loading.value = true; error.value = ''; message.value = ''; selected.value = null; reason.value = ''
  try {
    const result = await api.detail(props.factoryId, row.id, controller.signal)
    if (token !== generation || read !== sequence) return
    selected.value = result; decision.value = result.status === 'PENDING' ? 'KEEP_REQUIRED' : 'REOPEN'
  } catch (cause) { if (token === generation && read === sequence) error.value = getApiErrorMessage(cause) }
  finally { if (token === generation && read === sequence) loading.value = false }
}
async function refresh() { const row = selected.value, token = generation; await load(); if (token === generation && row && !error.value) await open(row) }
async function submit() {
  const row = selected.value
  if (!row || busy.value || loading.value || !decisions.value.includes(decision.value)) return
  if (reason.value.trim().length < 4) { error.value = '请填写至少四字的核实依据；本操作不变更正式订单。'; return }
  const token = generation
  const body = { factory_id: props.factoryId, expected_revision: row.revision, source_fingerprint: row.source_fingerprint, decision: decision.value, reason: reason.value.trim() }
  const identity = JSON.stringify([row.id, body]), request = requests.get(identity) || createRandomUuid(); requests.set(identity, request)
  busy.value = true; error.value = ''; message.value = ''
  try {
    const result = await api.review(row.id, { ...body, request_id: request }, controller.signal)
    if (token !== generation) return
    selected.value = result; requests.delete(identity); reason.value = ''; decision.value = result.status === 'PENDING' ? 'KEEP_REQUIRED' : 'REOPEN'
    message.value = '缺行核实记录已保存；正式采购单、需求、人工已下单标记和库存均未自动变更。'
    emit('changed', row.customer_code); await load()
    if (token === generation && error.value) error.value = `核实已保存，但列表刷新失败：${error.value}。请刷新核对，勿重复提交。`
  } catch (cause) { if (token === generation) error.value = getApiErrorMessage(cause) }
  finally { if (token === generation) busy.value = false }
}
function page(delta: number) { if (!busy.value && !loading.value) { offset.value += delta * limit; selected.value = null; reason.value = ''; void load() } }
onBeforeUnmount(() => { generation++; controller.abort(); if (timer) clearTimeout(timer) })
</script>

<template>
  <section class="space-y-4" aria-label="排期缺行待核实">
    <header class="rounded-xl border border-amber-200 bg-card p-4"><div class="flex flex-wrap items-start justify-between gap-3"><div><h2 class="text-base font-semibold">缺行待核实</h2><p class="mt-2 text-xs leading-5 text-muted-foreground">仅已确认全量覆盖段内的缺行进入此清单。核实结果不自动取消正式订单，也不扣减采购需求或库存。</p></div><Button type="button" variant="outline" size="sm" :disabled="busy || loading" @click="refresh">刷新核实清单</Button></div><div class="mt-3 flex flex-wrap items-center gap-4 text-xs"><label>客户<select :value="customerCode || '全部客户'" :disabled="busy" aria-label="缺行核实客户" class="ml-2 h-9 rounded-lg border border-input bg-card px-3" @change="emit('update:customerCode', ($event.target as HTMLSelectElement).value)"><option value="全部客户">全部客户</option><option v-for="customer in workspace?.customers || []" :key="customer.customer_code" :value="customer.customer_code">{{ customer.customer_name }}{{ customer.status === 'INACTIVE' ? '（已停用）' : '' }}</option></select></label><label class="flex items-center gap-2"><input v-model="showHistory" type="checkbox" :disabled="busy" aria-label="显示已核实缺行历史">显示已核实、重新出现与撤回历史</label><span v-if="workspace" class="text-muted-foreground">{{ showHistory ? '当前筛选' : '待核实' }} {{ total }} 项</span></div></header>
    <p v-if="error" role="alert" class="rounded-lg border border-red-200 bg-red-50 p-3 text-sm text-red-700">{{ error }}</p><p v-if="message" role="status" class="rounded-lg border border-teal-200 bg-teal-50 p-3 text-sm text-teal-800">{{ message }}</p>
    <p v-if="loading && !workspace" role="status" class="p-6 text-sm text-muted-foreground">正在读取完整范围内的缺行核实记录…</p>
    <div v-if="rows.length" class="overflow-hidden rounded-xl border bg-card"><div class="carton-table-wrap overflow-x-auto"><table aria-label="排期缺行清单" class="carton-table-fit w-full text-left text-xs"><thead class="bg-muted/50 text-muted-foreground"><tr><th class="p-3">客户 / 合同 / 货号</th><th class="p-3">上次来源</th><th class="p-3">本次全量范围</th><th class="p-3">核实状态</th><th class="p-3">处理</th></tr></thead><tbody class="divide-y"><tr v-for="row in rows" :key="row.id"><td data-label="客户 / 合同 / 货号" class="break-words p-3"><b>{{ row.customer_name }} · {{ row.contract_no }}</b><p class="mt-1">{{ row.item_no }} · SO / 客户PO {{ row.source_reference || row.customer_po || '未记录' }}</p></td><td data-label="上次来源" class="p-3"><p>{{ row.source_rows.length }} 行原始记录，数量分开保留</p><p class="mt-1 text-muted-foreground">上次客户交期 {{ row.source_rows[0]?.customer_due_date || row.source_rows[0]?.source_customer_due_date || '日期待核实' }}</p></td><td data-label="本次全量范围" class="p-3 tabular-nums"><b>版本 {{ row.as_of_date }}</b><p class="mt-1">客户交期 {{ row.coverage_start }} 至 {{ row.coverage_end }}（含首尾）</p></td><td data-label="核实状态" class="p-3"><StatusPill :label="statusLabels[row.status]" :tone="row.status === 'PENDING' ? 'amber' : 'slate'" compact /><p class="mt-2 text-muted-foreground">{{ row.can_operate_source ? '原来源仍按采购守卫核对' : '不能沿旧来源新建或标记已下单' }}</p></td><td data-label="处理" class="p-3"><Button type="button" variant="outline" size="sm" :disabled="busy || loading" :aria-label="`核实缺行 ${row.contract_no} ${row.item_no}`" @click="open(row)">查看与核实</Button></td></tr></tbody></table></div><nav class="flex items-center justify-end gap-3 border-t p-3 text-xs" aria-label="缺行核实分页"><span>第 {{ Math.floor(offset / limit) + 1 }} 页 · 共 {{ total }} 项</span><Button type="button" size="sm" variant="outline" :disabled="busy || loading || offset === 0" @click="page(-1)">上一页</Button><Button type="button" size="sm" variant="outline" :disabled="busy || loading || offset + limit >= total" @click="page(1)">下一页</Button></nav></div>
    <p v-else-if="workspace && !loading && !error" class="rounded-xl border bg-card p-8 text-center text-sm text-muted-foreground">{{ showHistory ? '没有匹配的缺行核实记录。' : '当前没有待核实缺行；这不代表所有客户已声明完整覆盖。' }}</p>
    <article v-if="selected" class="space-y-4 rounded-xl border border-amber-200 bg-card p-4" aria-label="缺行核实详情"><div class="flex items-center justify-between gap-3"><h3 class="text-sm font-semibold">{{ selected.customer_name }} · {{ selected.contract_no }} · {{ selected.item_no }}</h3><Button type="button" size="sm" variant="ghost" :disabled="busy" @click="selected = null">收起</Button></div><p class="text-xs text-muted-foreground">{{ decisionLabel(selected.status) }}。缺行不是业务明确退单；正式订单须沿原流程单独变更。</p><div class="rounded-lg bg-muted/40 p-3 text-xs"><b>当前显式关联与人工标记</b><p class="mt-1">现存显式关联订单 {{ selected.current_order_ids ? selected.current_order_ids.join('、') || '无' : '待核实' }} · 当前人工已下单 {{ selected.current_manual_marked === true ? '有' : selected.current_manual_marked === false ? '无' : '待核实' }}</p><p class="mt-1 text-muted-foreground">仅依据已保存的来源关联与人工标记，不代表重新匹配了全部 PO。</p></div><Button type="button" size="sm" variant="outline" :disabled="busy" @click="emit('source', selected.batch_id)">查看本次全量比较与排除依据</Button>
      <div v-if="selected.current_sources?.length" class="space-y-2 text-xs" aria-label="当前逐行来源证据"><p v-for="source in selected.current_sources" :key="`${source.batch_id}:${source.source_sheet}:${source.source_row}`" class="rounded-lg bg-muted/40 p-3">当前来源 {{ source.source_sheet }} 第 {{ source.source_row }} 行 · 现存订单 {{ source.current_order_ids.join('、') || '无' }} · 人工已下单 {{ source.current_manual_marked ? '有' : '无' }}{{ source.manual_review_required ? '（需求变化待复核）' : '' }}<button type="button" class="ml-2 underline" :disabled="busy" @click="emit('source', source.batch_id)">查看当前来源</button></p></div>
      <div v-if="selected.basis_changed" class="space-y-2 rounded-lg border border-amber-200 bg-amber-50 p-3 text-xs"><b>原比较基线已变化，请按仍有效来源重新核实。下方最初快照保留，不代表当前有效需求。</b><p v-for="row in selected.effective_source_rows || []" :key="`${row.batch_id}:${row.source_sheet}:${row.source_row}`">有效来源 {{ row.source_sheet }} 第 {{ row.source_row }} 行 · 数量 {{ row.quantity ?? '待核实' }} · 客户交期 {{ row.customer_due_date || row.source_customer_due_date || '待核实' }}<button type="button" class="ml-2 underline" :disabled="busy" @click="emit('source', row.batch_id)">查看有效来源</button></p></div><div class="space-y-2"><h4 class="text-xs font-semibold">最初发现时的来源快照（各原行分别保留）</h4><div v-for="row in selected.source_rows" :key="`${row.batch_id}:${row.source_sheet}:${row.source_row}`" class="flex flex-wrap items-center justify-between gap-3 rounded-lg bg-muted/40 p-3 text-xs"><div><b>{{ row.source_sheet }} · 第 {{ row.source_row }} 行</b><p class="mt-1">原数量 {{ row.quantity ?? '待核实' }} · 原客户交期 {{ row.customer_due_date || row.source_customer_due_date || '待核实' }} · {{ row.source_reference || row.customer_po || 'PO未记录' }}</p><p v-if="row.order_id || row.manual_ordered" class="mt-1 text-muted-foreground">{{ row.order_id ? '原导入快照记录过正式订单关联，请查看当前关联状态' : '原导入快照记录过人工已下单依据，请查看当前标记状态' }}</p></div><Button type="button" size="sm" variant="outline" :disabled="busy" @click="emit('source', row.batch_id)">查看此行原来源</Button></div></div>
      <form v-if="decisions.length" class="space-y-3 rounded-lg border border-input p-3 text-xs" aria-label="缺行核实表单" @submit.prevent="submit"><label class="block space-y-1"><span class="font-semibold">核实结论</span><select v-model="decision" :disabled="busy || loading" aria-label="缺行核实结论" class="h-10 w-full rounded-lg border border-input bg-card px-3"><option v-for="value in decisions" :key="value" :value="value">{{ decisionLabel(value) }}</option></select></label><label class="block space-y-1"><span class="font-semibold">核实依据 / 原因</span><textarea v-model="reason" :disabled="busy || loading" required minlength="4" maxlength="2000" rows="2" aria-label="缺行核实原因" class="w-full rounded-lg border border-input bg-card px-3 py-2" /></label><p class="text-muted-foreground">“不再需要”仅核实业务来源；已存在的采购单不会被取消或减量，仍须单独办理。</p><Button size="sm" :disabled="busy || loading">{{ busy ? '正在保存核实…' : '保存核实结论' }}</Button></form><p v-else class="rounded-lg bg-muted/50 p-3 text-xs text-muted-foreground">此记录当前只读；权限、客户责任及可核实状态由后端校验。</p>
      <details class="rounded-lg border border-input p-3 text-xs"><summary class="cursor-pointer font-semibold">历次核实记录（{{ selected.history.length }}）</summary><p v-for="entry in selected.history" :key="entry.id" class="mt-3 whitespace-pre-wrap break-words border-t pt-2">{{ entry.created_at }} · {{ entry.actor_name }} · {{ decisionLabel(entry.decision) }} · {{ entry.reason }}</p></details>
    </article>
  </section>
</template>
