<script setup lang="ts">
import { computed, onBeforeUnmount, reactive, ref, watch } from 'vue'
import { Button } from '@/components/ui/button'
import StatusPill from '@/components/common/StatusPill.vue'
import CartonFilterBar from './CartonFilterBar.vue'
import { useAuthStore } from '@/stores/auth'
import { getApiErrorMessage } from '@/lib/http'
import { formatBusinessDate, formatBusinessDateTime } from '@/lib/dateTime'
import { factoryContexts } from '@/data/enterpriseMock'
import { cartonPriceCorrectionsApi as api, pendingPriceCorrection, type PendingPriceCorrection, type PriceCorrectionAction, type PriceCorrectionActionBody, type PriceCorrectionBlocker, type PriceCorrectionDetail, type PriceCorrectionImpact, type PriceCorrectionsWorkspace } from '@/api/cartonPriceCorrections'
import '@/features/carton-procurement/layout.css'

const props = withDefaults(defineProps<{ factoryId?: string; factories?: { factory_id: string }[]; internal?: boolean; receiptLineId?: string; viewerKey?: string }>(), { internal: false, factoryId: '', receiptLineId: '' })
const emit = defineEmits<{ changed: []; navigate: [blocker: PriceCorrectionBlocker, currency: string] }>()
const auth = useAuthStore()
const factories = computed(() => [...new Set(props.internal ? [props.factoryId].filter(Boolean) : props.factories?.map(row => row.factory_id) ?? [props.factoryId].filter(Boolean))])
const factory = ref(''), keyword = ref(''), status = ref<'PENDING' | 'ALL'>(props.receiptLineId ? 'ALL' : 'PENDING'), offset = ref(0), limit = 25
const workspace = ref<PriceCorrectionsWorkspace | null>(null), selected = ref<PriceCorrectionDetail | null>(null), impact = ref<PriceCorrectionImpact | null>(null)
const loading = ref(false), detailLoading = ref(false), busy = ref(false), error = ref(''), message = ref(''), action = ref<PriceCorrectionAction | ''>('')
const basis = ref<{ revision: number; fingerprint: string } | null>(null), pending = ref<PendingPriceCorrection | null>(null)
const form = reactive({ price: '', free: false, document: '', date: '', reason: '' })
const viewer = computed(() => JSON.stringify([props.viewerKey, auth.currentUser?.id, auth.authorizationVersion, auth.authzMode, auth.currentUser?.identity?.effective_context_key, auth.currentUser?.identity?.employment_epoch]))
const access = (permission: string) => ['carton', 'pmc-warehouse'].some(dept => auth.can(`carton_procurement:${permission}`, factory.value, dept))
const supplierAccess = (permission: string) => auth.can(`carton_supplier:${permission}`, '*', '*') && auth.can(`carton_supplier:${permission}`, factory.value, '*')
const canRead = computed(() => !!factory.value && (props.internal ? access('read') : supplierAccess('read')))
const canPropose = computed(() => props.internal && canRead.value && access('receipt_write') && access('inventory_write'))
const supervisor = computed(() => props.internal && canRead.value && ['inventory_write', 'closing_manage', 'order_adjust'].every(access))
const roleAllows = (value: PriceCorrectionAction) => props.internal ? value === 'FINAL_CONFIRM' ? supervisor.value : ['PROPOSE', 'WITHDRAW'].includes(value) && canPropose.value : ['SUPPLIER_CONFIRM', 'SUPPLIER_DISPUTE'].includes(value) && supplierAccess('approve')
const allowed = (value: PriceCorrectionAction) => !!selected.value?.allowed_actions.includes(value) && roleAllows(value)
const staleEditor = computed(() => !!basis.value && !!selected.value && (basis.value.revision !== selected.value.revision || basis.value.fingerprint !== selected.value.source_fingerprint))
const blockers = computed(() => props.internal ? impact.value?.blockers ?? selected.value?.blockers ?? [] : [])
const labels: Record<string, string> = { NONE: '尚未提议', PENDING_SUPPLIER: '待供应商确认', SUPPLIER_CONFIRMED: '供应商已确认，待主管生效', DISPUTED: '供应商有异议', WITHDRAWN: '已撤回，原价保留', APPLIED: '更正已生效', STALE: '批次价格依据变化，须重新提议', PROPOSE: '提出单价更正', SUPPLIER_CONFIRM: '确认本批新价', SUPPLIER_DISPUTE: '提出价格异议', FINAL_CONFIRM: '主管确认更正生效', WITHDRAW: '撤回本次提议', CONFIRMED: '已确认' }
const label = (value: string) => labels[value] || value
const movementLabel = (value: string) => ({ INBOUND: '入库', OUTBOUND: '出库', ADJUSTMENT: '调整', REVERSAL: '冲销' })[value as 'INBOUND'] || '其他流水'
const issueLabel = (value: string) => ({ USAGE: '领用', RETURN: '退货', LOSS: '损耗', LOAN: '借出', OTHER: '其他', UNKNOWN: '历史未分类', ORDER_ISSUE: '订单领用' })[value as 'USAGE'] || '其他用途'
const closingLabel = (value: string) => ({ DRAFT: '草稿', PENDING: '待核对', CONFIRMED: '已确认', LOCKED: '已锁账', SUPERSEDED: '历史版本' })[value as 'DRAFT'] || '待核实状态'
const sourceLabel = (value: string) => ({ RECEIPT: '收料凭证', ORDER_REPLENISHMENT: '补单责任出库', ORDER_SPLIT: '拆单承接', SPLIT_REVERSAL: '拆单冲销', ORDER: '订单作业', MANUAL: '人工登记', STOCKTAKE: '库存盘点' })[value as 'RECEIPT'] || '其他来源'
const price = (value?: string | null) => value == null ? '待核实' : value
const name = (id: string) => factoryContexts.find(row => row.id === id)?.name || id
const today = () => formatBusinessDate(new Date().toISOString())
let generation = 0, readSequence = 0, detailSequence = 0, operation = 0, controller = new AbortController()
function resetForm() { action.value = ''; basis.value = null; Object.assign(form, { price: '', free: false, document: '', date: '', reason: '' }) }
function begin(value: PriceCorrectionAction) {
  if (!allowed(value) || busy.value || pending.value || !selected.value) return
  action.value = value; basis.value = { revision: selected.value.revision, fingerprint: selected.value.source_fingerprint }
  Object.assign(form, { price: selected.value.proposed_unit_price ?? selected.value.current_unit_price ?? '', free: false, document: '', date: today(), reason: '' })
  error.value = ''
}
async function load() {
  if (!canRead.value) return
  const token = generation, read = ++readSequence
  loading.value = true; error.value = ''
  try {
    const result = await api.workspace(props.internal, { factory_id: factory.value, status: status.value, keyword: keyword.value.trim(), limit, offset: offset.value }, controller.signal)
    if (token !== generation || read !== readSequence) return
    workspace.value = result
  } catch (cause) { if (token === generation && read === readSequence) error.value = getApiErrorMessage(cause) }
  finally { if (token === generation && read === readSequence) loading.value = false }
}
async function open(line: string, preserveForm = false) {
  if (!canRead.value || busy.value) return
  const token = generation, read = ++detailSequence
  detailLoading.value = true; error.value = ''; impact.value = null
  if (!preserveForm) { resetForm(); selected.value = null }
  try {
    const result = await api.detail(props.internal, line, factory.value, controller.signal)
    if (token !== generation || read !== detailSequence) return
    selected.value = result
  } catch (cause) { if (token === generation && read === detailSequence) error.value = getApiErrorMessage(cause) }
  finally { if (token === generation && read === detailSequence) detailLoading.value = false }
}
async function refresh() { impact.value = null; await load(); if (selected.value) await open(selected.value.receipt_line_id, true) }
async function preview() {
  const row = selected.value
  if (!row?.proposal || !supervisor.value || busy.value || pending.value) return
  const token = generation, op = ++operation
  busy.value = true; error.value = ''; impact.value = null
  try {
    const result = await api.preview(row.receipt_line_id, { factory_id: factory.value, expected_revision: row.revision, source_fingerprint: row.source_fingerprint }, controller.signal)
    if (token !== generation) return
    selected.value = result; impact.value = result.impact ?? null
    if (action.value === 'FINAL_CONFIRM') resetForm()
  } catch (cause) { if (token === generation) error.value = getApiErrorMessage(cause) }
  finally { if (op === operation) busy.value = false }
}
async function write(retry = false) {
  const row = selected.value, currentAction = retry ? pending.value?.body.action : action.value
  if (busy.value || !canRead.value || !currentAction || !roleAllows(currentAction)) return
  if (!retry && (!row || !allowed(currentAction) || !basis.value || staleEditor.value || pending.value)) return
  if (!retry && form.reason.trim().length < 4) { error.value = '请填写至少四字的本次处理依据。'; return }
  if (!retry && currentAction === 'PROPOSE' && (!/^(?:0|[1-9]\d*)(?:\.\d{1,6})?$/.test(form.price.trim()) || !form.document.trim() || !form.date || form.date > today() || /^0(?:\.0+)?$/.test(form.price.trim()) && !form.free)) { error.value = '请核对新价（最多六位小数）、凭证号和非未来凭证日期；零价须明确免费依据。'; return }
  if (!retry && currentAction === 'FINAL_CONFIRM' && (!impact.value?.can_apply || !impact.value.impact_fingerprint)) { error.value = '请先取得最新可生效预览，并处理列出的阻挡。'; return }
  const content: Omit<PriceCorrectionActionBody, 'request_id'> = retry ? (({ request_id: ignored, ...original }) => original)(pending.value!.body) : {
    factory_id: factory.value, expected_revision: basis.value!.revision, source_fingerprint: basis.value!.fingerprint, action: currentAction, reason: form.reason.trim(),
    ...(currentAction === 'PROPOSE' ? { proposed_unit_price: form.price.trim(), free_confirmed: /^0(?:\.0+)?$/.test(form.price.trim()) && form.free, document_no: form.document.trim(), document_date: form.date } : {}),
    ...(currentAction === 'FINAL_CONFIRM' ? { impact_fingerprint: impact.value!.impact_fingerprint } : {}),
  }
  const line = retry ? pending.value!.receipt_line_id : row!.receipt_line_id, token = generation, op = ++operation
  detailSequence++; detailLoading.value = false
  busy.value = true; error.value = ''; message.value = ''
  try {
    const result = await api.act(props.internal, line, content, viewer.value, controller.signal)
    if (token !== generation) return
    selected.value = result; impact.value = supervisor.value ? result.impact ?? null : null; pending.value = null; resetForm()
    message.value = currentAction === 'FINAL_CONFIRM' ? '本批单价更正已生效，库存成本与应付已同步；原数量、凭证与真实付款保留。请继续核对受影响月结与核销。' : `${label(currentAction)}已保存；当前有效价格以主管最终生效为准。`
    emit('changed'); await load()
    if (error.value) error.value = `本次处理已保存，但更正清单刷新失败：${error.value}。请刷新查看，勿重复提交。`
  } catch (cause) {
    if (token !== generation) return
    error.value = getApiErrorMessage(cause); pending.value = pendingPriceCorrection(props.internal, factory.value, viewer.value)
    if (currentAction === 'FINAL_CONFIRM') impact.value = null
  } finally { if (op === operation) busy.value = false }
}
watch(factories, ids => { if (!ids.includes(factory.value)) factory.value = props.factoryId && ids.includes(props.factoryId) ? props.factoryId : ids[0] || '' }, { immediate: true })
watch(() => JSON.stringify([factory.value, props.internal, viewer.value, canRead.value]), () => {
  generation++; readSequence++; detailSequence++; operation++; controller.abort(); controller = new AbortController()
  workspace.value = null; selected.value = null; impact.value = null; offset.value = 0; busy.value = false; loading.value = false; detailLoading.value = false; error.value = ''; message.value = ''; resetForm()
  pending.value = pendingPriceCorrection(props.internal, factory.value, viewer.value)
  if (canRead.value) { void load(); if (props.receiptLineId) void open(props.receiptLineId) }
}, { immediate: true, flush: 'sync' })
watch(() => props.receiptLineId, line => { if (line && canRead.value) void open(line) })
watch(status, () => { if (offset.value) offset.value = 0; else void load() })
watch(offset, () => { void load() })
onBeforeUnmount(() => { generation++; operation++; controller.abort() })
defineExpose({ refresh, busy })
</script>

<template>
  <section class="space-y-4" aria-label="收料单价更正工作区">
    <p class="text-xs leading-6 text-muted-foreground">仓管按确切实收批次提议，供应商确认新价和凭证，主管预览后最终生效。提议期间沿用当前有效价；不修改实物数量或真实付款。</p>
    <CartonFilterBar label="单价更正筛选">
      <label v-if="!internal">厂区<select v-model="factory" aria-label="价格更正厂区" :disabled="busy || !!pending" class="h-10 rounded-lg border bg-card px-3"><option v-for="id in factories" :key="id" :value="id">{{ name(id) }}</option></select></label>
      <label>查看范围<select v-model="status" aria-label="价格更正状态" :disabled="busy" class="h-10 rounded-lg border bg-card px-3"><option value="PENDING">待处理提议</option><option value="ALL">全部可核对批次及历史</option></select></label>
      <label class="min-w-0 flex-1">单据 / 合同 / 货号<input v-model="keyword" aria-label="价格更正关键词" class="h-10 w-full rounded-lg border bg-card px-3" @keydown.enter.prevent="offset = 0; load()"></label>
      <template #actions><Button type="button" variant="outline" :disabled="busy || loading || !canRead" @click="offset = 0; refresh()">查询 / 刷新更正</Button></template>
      <template #footer><span>{{ name(factory) }} · 待处理 {{ workspace?.pending_count ?? '—' }} 项；此数不代表全部采购欠数或未付款。</span></template>
    </CartonFilterBar>
    <p v-if="!canRead" class="rounded-lg bg-muted p-4 text-sm">没有当前厂区的价格更正查看权限。</p>
    <p v-if="error" role="alert" class="rounded-lg border border-red-200 bg-red-50 p-3 text-sm text-red-700">{{ error }}</p>
    <p v-if="message" role="status" class="text-sm text-teal-700">{{ message }}</p>
    <div v-if="pending && canRead" class="space-y-2 rounded-lg border border-amber-300 bg-amber-50 p-3 text-xs"><b>有原请求结果待核实</b><p>请先读取该批次核对；重试将使用原请求标识与原版本，不按刷新后的数据重新登记。</p><Button type="button" variant="outline" :disabled="busy || !roleAllows(pending.body.action)" @click="write(true)">重试原未确认请求</Button><Button type="button" variant="ghost" :disabled="busy" @click="open(pending.receipt_line_id)">核对原批次记录</Button></div>
    <p v-if="loading" class="p-4 text-sm text-muted-foreground">正在读取单价更正清单…</p>
    <div v-if="workspace && canRead" class="overflow-hidden rounded-xl border bg-card">
      <div class="carton-table-wrap overflow-x-auto"><table aria-label="收料价格更正清单" class="carton-table-fit w-full text-left text-xs"><thead class="bg-muted/50 text-muted-foreground"><tr><th class="p-3">原单与实收批次</th><th class="p-3">纸品 / 数量</th><th class="p-3">原价 / 当前 / 提议</th><th class="p-3">当前进度</th><th class="p-3">处理</th></tr></thead><tbody class="divide-y"><tr v-for="row in workspace.items" :key="row.receipt_line_id"><td data-label="原单与实收批次" class="p-3"><b>{{ row.document_no }}</b><p class="mt-1">验收 {{ row.acceptance_date }} · {{ row.customer_name }} · {{ row.contract_no }} · {{ row.item_no }}</p></td><td data-label="纸品 / 数量" class="p-3">{{ row.packaging_type }} {{ row.paper_quality }}<p class="mt-1">{{ row.specification }} · {{ row.quantity }} {{ row.unit }}</p></td><td data-label="原价 / 当前 / 提议" class="p-3 tabular-nums"><p>{{ internal ? '原入库价' : '原送货价' }} {{ price(internal ? row.raw_unit_price : row.original_supplier_unit_price) }}</p><p>当前应付价 {{ price(row.current_unit_price) }}</p><p>提议价 {{ price(row.proposed_unit_price) }} {{ row.currency }} / {{ row.unit }}</p></td><td data-label="当前进度" class="p-3"><StatusPill :label="label(row.status)" compact /></td><td data-label="处理" class="p-3"><Button type="button" variant="outline" size="sm" :disabled="busy || detailLoading" :aria-label="`核对价格批次 ${row.receipt_line_id}`" @click="open(row.receipt_line_id)">查看 / 处理</Button></td></tr><tr v-if="!workspace.items.length && !loading"><td colspan="5" class="p-8 text-center text-muted-foreground">{{ internal ? '当前范围没有价格更正记录。仓管可在“全部”中选择有效收料批次提议。' : '当前没有供应商可核对的已发布更正方案，请等待本厂提议。' }}</td></tr></tbody></table></div>
      <nav aria-label="价格更正分页" class="flex justify-end gap-3 border-t p-3 text-xs"><span>共 {{ workspace.total }} 项</span><Button variant="outline" size="sm" :disabled="busy || loading || !offset" @click="offset = Math.max(0, offset - limit)">上一页</Button><Button variant="outline" size="sm" :disabled="busy || loading || offset + limit >= workspace.total" @click="offset += limit">下一页</Button></nav>
    </div>
    <p v-if="detailLoading" class="p-3 text-sm text-muted-foreground">正在读取确切批次依据…</p>
    <article v-if="selected && canRead" class="space-y-4 rounded-xl border bg-card p-4" aria-label="单价更正批次详情">
      <p v-if="!internal && selected.blockers.length" class="rounded-lg bg-amber-50 p-3 text-xs text-amber-900">本厂尚有账务前置条件待处理；供应商只确认本批商务新价，不代表更正已经最终生效。</p>
      <div class="flex flex-wrap items-start justify-between gap-3"><div><h3 class="font-semibold">{{ selected.document_no }} · {{ selected.item_no }} · {{ selected.packaging_type }}</h3><p class="mt-1 text-xs text-muted-foreground">{{ selected.specification }} · 实收 {{ selected.quantity }} {{ selected.unit }} · {{ selected.currency }} · 验收 {{ selected.acceptance_date }}</p></div><Button type="button" size="sm" variant="ghost" :disabled="busy" @click="open(selected.receipt_line_id, true)">重新读取此批次</Button></div>
      <div class="grid gap-3 text-xs sm:grid-cols-3" aria-label="原价当前价与提议价"><div class="rounded-lg bg-muted/40 p-3">{{ internal ? '原始入库证据单价' : '供应商原始送货单价' }}<p class="mt-2 font-semibold tabular-nums">{{ price(internal ? selected.raw_unit_price : selected.original_supplier_unit_price) }} {{ selected.currency }} / {{ selected.unit }}</p></div><div class="rounded-lg bg-muted/40 p-3">当前有效应付单价<p class="mt-2 font-semibold tabular-nums">{{ price(selected.current_unit_price) }} {{ selected.currency }} / {{ selected.unit }}</p><p v-if="internal" class="mt-2">当前有效入库成本单价 {{ price(selected.current_cost_unit_price) }}</p></div><div class="rounded-lg bg-teal-50 p-3">{{ selected.status === 'APPLIED' ? '已生效更正价' : selected.status === 'WITHDRAWN' ? '历史提议价（已撤回）' : '本次提议新价（待最终生效）' }}<p class="mt-2 font-semibold tabular-nums">{{ price(selected.proposed_unit_price) }} {{ selected.currency }} / {{ selected.unit }}</p></div></div>
      <ol aria-label="单价更正三方流程" class="grid gap-3 text-xs sm:grid-cols-3"><li class="rounded-lg border p-3"><b>1 · 仓管提议</b><p class="mt-2">{{ selected.proposal ? `版本 ${selected.proposal.version} · ${selected.proposal.document_no} · ${selected.proposal.document_date}` : '尚未提出更正' }}</p><p v-if="selected.proposal" class="mt-2 whitespace-pre-wrap">{{ selected.proposal.reason }}</p></li><li class="rounded-lg border p-3"><b>2 · 供应商核对</b><p class="mt-2">{{ selected.status === 'STALE' ? '批次依据变化，原确认不可继续使用' : selected.proposal?.supplier_review ? `${label(selected.proposal.supplier_review.decision)} · ${selected.proposal.supplier_review.at}` : '待供应商确认确切批次及新价' }}</p><p v-if="selected.proposal?.supplier_review" class="mt-2 whitespace-pre-wrap">{{ selected.proposal.supplier_review.reason }}</p></li><li class="rounded-lg border p-3"><b>3 · 主管生效</b><p class="mt-2">{{ selected.status === 'APPLIED' ? '已生效，原始证据保留' : '尚未生效，沿用当前有效价' }}</p><p v-if="internal" class="mt-2">正常后续出入库只更新成本预览，不自动撤回同批次的供方确认。</p></li></ol>
      <div v-if="blockers.length" class="space-y-2 rounded-lg border border-amber-200 bg-amber-50 p-3 text-xs" aria-label="价格更正阻挡"><b>最终生效前须处理</b><div v-for="(blocker, index) in blockers" :key="index" class="flex flex-wrap items-center justify-between gap-2"><p>{{ blocker.period }} {{ blocker.message }}</p><Button v-if="internal && supervisor && ['INVENTORY_CLOSING', 'SUPPLIER_SETTLEMENT', 'ALLOCATION'].includes(blocker.kind)" type="button" variant="outline" size="sm" :disabled="busy" @click="emit('navigate', blocker, selected.currency)">{{ blocker.kind === 'INVENTORY_CLOSING' ? '去库存月份解锁' : blocker.kind === 'ALLOCATION' ? '去解除原核销' : '去原月份原因重核' }}</Button></div><p>不会自动解锁、重开或解除核销；完成后回来重新读取并预览。</p></div>
      <div class="flex flex-wrap gap-2"><Button v-if="allowed('PROPOSE') && selected.can_propose" type="button" variant="outline" :disabled="busy || !!pending" @click="begin('PROPOSE')">提出单价更正</Button><Button v-if="allowed('SUPPLIER_CONFIRM')" type="button" :disabled="busy || !!pending" @click="begin('SUPPLIER_CONFIRM')">确认本批新价</Button><Button v-if="allowed('SUPPLIER_DISPUTE')" type="button" variant="outline" :disabled="busy || !!pending" @click="begin('SUPPLIER_DISPUTE')">提出价格异议</Button><Button v-if="allowed('WITHDRAW')" type="button" variant="destructive" :disabled="busy || !!pending" @click="begin('WITHDRAW')">撤回本次提议</Button><Button v-if="supervisor && selected.proposal && !['APPLIED', 'WITHDRAWN', 'STALE'].includes(selected.status)" type="button" variant="outline" :disabled="busy || !!pending" @click="preview">预览成本与账单影响</Button></div>
      <section v-if="internal && supervisor && impact" class="space-y-3 border-t pt-4 text-xs" aria-label="主管成本与账单预览"><h4 class="font-semibold">最新成本与账单影响</h4><p>按完整相关账序重演；以下为服务端精确金额，保留计算精度，显示金额逐项舍入可能不直接相加。实物数量不变。</p><div class="grid gap-2 sm:grid-cols-3"><p>原批成本差 {{ impact.summary.source_cost_difference }} {{ impact.summary.currency }}</p><p>全部入库成本差 {{ impact.summary.inbound_cost_difference }}</p><p>领用等出库成本差 {{ impact.summary.outbound_cost_difference }}</p><p>其他成本差 {{ impact.summary.other_cost_difference }}</p><p>期末余存成本差 {{ impact.summary.ending_cost_difference }}</p><p>成本守恒差 {{ impact.summary.bridge_difference }}</p><p class="font-semibold">{{ impact.summary.payable_difference == null ? '原应付待核实，差额待核实' : `应付差额 ${impact.summary.payable_difference} ${impact.summary.currency}` }}</p></div><div class="carton-table-wrap overflow-x-auto"><table aria-label="受影响成本流水" class="carton-table-fit w-full text-left"><thead><tr><th class="p-2">业务凭证 / 记账时间</th><th class="p-2">类型 / 数量</th><th class="p-2">原成本</th><th class="p-2">更正后成本</th><th class="p-2">差额</th></tr></thead><tbody><tr v-for="row in impact.movements" :key="row.movement_id"><td data-label="业务凭证 / 记账时间" class="p-2">{{ row.document_no }}<p>{{ formatBusinessDateTime(row.occurred_at) }}</p></td><td data-label="类型 / 数量" class="p-2">{{ movementLabel(row.movement_type) }} · {{ issueLabel(row.issue_kind) }} · {{ sourceLabel(row.source_type) }} {{ row.quantity }} {{ row.unit }}</td><td data-label="原成本" class="p-2 tabular-nums">{{ row.old_cost_amount }}</td><td data-label="更正后成本" class="p-2 tabular-nums">{{ row.new_cost_amount }}</td><td data-label="差额" class="p-2 tabular-nums">{{ row.cost_difference }} {{ row.currency }}</td></tr></tbody></table></div><details><summary>各成本池余存与受影响库存月结</summary><p v-for="row in impact.pools" :key="row.id" class="mt-2">{{ row.customer_code }} · 余存 {{ row.quantity }} {{ row.unit }} · {{ row.old_amount }} → {{ row.new_amount }} · 差 {{ row.difference }} {{ row.currency }}</p><p v-for="row in impact.closings" :key="row.id" class="mt-2">{{ row.period }} · {{ row.customer_code }} · {{ closingLabel(row.status) }} · 原 {{ row.old_ending_amount }} → {{ row.new_ending_amount }} · 差 {{ row.amount_difference }} {{ row.currency }}</p></details><p class="text-muted-foreground">已付款和收款回执保留；新月结确认后须显式重新核销。降价可留下未分配预付，涨价可形成待付差额，不自动退款或扣款。</p><Button v-if="allowed('FINAL_CONFIRM')" type="button" :disabled="busy || !!pending || !impact.can_apply" @click="begin('FINAL_CONFIRM')">主管确认更正生效</Button></section>
      <form v-if="action" class="space-y-3 rounded-lg border bg-muted/30 p-4 text-xs" aria-label="单价更正处理表单" @submit.prevent="write()"><h4 class="font-semibold">{{ label(action) }}</h4><p v-if="staleEditor" role="alert" class="text-amber-800">依据已变化，请重新读取本批次并重新选择动作；已填内容保留供核对。</p><div v-if="action === 'PROPOSE'" class="grid gap-3 sm:grid-cols-3"><label>提议新单价 {{ selected.currency }} / {{ selected.unit }}<input v-model="form.price" required inputmode="decimal" aria-label="更正提议新单价" :disabled="busy || !!pending" class="mt-1 h-10 w-full rounded-lg border bg-card px-3"></label><label>价格依据凭证号<input v-model="form.document" required maxlength="128" aria-label="更正价格凭证号" :disabled="busy || !!pending" class="mt-1 h-10 w-full rounded-lg border bg-card px-3"></label><label>凭证日期<input v-model="form.date" type="date" required :max="today()" aria-label="更正价格凭证日期" :disabled="busy || !!pending" class="mt-1 h-10 w-full rounded-lg border bg-card px-3"></label><label v-if="/^0(?:\.0+)?$/.test(form.price)" class="flex items-start gap-2 sm:col-span-3"><input v-model="form.free" type="checkbox" aria-label="确认更正新价免费" :disabled="busy || !!pending">凭证明确此批免费，新单价为零</label></div><p v-if="action === 'FINAL_CONFIRM'" class="rounded-lg bg-amber-50 p-3 text-amber-900">本次将同步更正库存成本与本批应付；原凭证与真实资金不变。若又有正常出入库，须重新预览才能生效。</p><label class="block">本次处理依据（至少四字）<textarea v-model="form.reason" aria-label="单价更正处理依据" required minlength="4" maxlength="2000" rows="3" :disabled="busy || !!pending" class="mt-1 w-full rounded-lg border bg-card p-3" /></label><div class="flex justify-end gap-2"><Button type="button" variant="outline" :disabled="busy" @click="resetForm">取消本次填写</Button><Button type="submit" :disabled="busy || !!pending || staleEditor || !allowed(action) || action === 'FINAL_CONFIRM' && !impact?.can_apply">{{ busy ? '正在保存…' : action === 'FINAL_CONFIRM' ? '确认同步生效' : '保存本次处理' }}</Button></div></form>
      <details v-if="selected.versions?.length" class="rounded-lg border p-3 text-xs"><summary class="cursor-pointer font-semibold">历次价格方案（{{ selected.versions.length }}）</summary><div v-for="version in selected.versions" :key="version.id" class="mt-3 space-y-2 border-t pt-3"><b>版本 {{ version.version }} · {{ label(version.status) }} · {{ version.proposed_unit_price }} {{ selected.currency }} / {{ selected.unit }}</b><p>价格依据 {{ version.document_no }} · {{ version.document_date }} · {{ version.reason }}</p><p v-if="version.supplier_review">供应商 {{ label(version.supplier_review.decision) }} · {{ version.supplier_review.at }} · {{ version.supplier_review.reason }}</p></div></details>
      <details class="rounded-lg border p-3 text-xs"><summary class="cursor-pointer font-semibold">更正历史（{{ selected.history.length }}）</summary><p v-for="entry in selected.history" :key="entry.id" class="mt-3 whitespace-pre-wrap break-words border-t pt-2">{{ formatBusinessDateTime(entry.created_at) }} · {{ entry.actor_name }} · {{ label(entry.action) }} · {{ entry.reason }}</p></details>
    </article>
  </section>
</template>
