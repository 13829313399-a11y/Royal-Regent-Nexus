<script setup lang="ts">
import CartonOrderStockFields from './CartonOrderStockFields.vue'
import { computed, onBeforeUnmount, reactive, ref, watch } from 'vue'
import { DialogRoot, DialogOverlay, DialogContent, DialogTitle, DialogDescription } from 'reka-ui'
import { Button } from '@/components/ui/button'
import { useAuthStore } from '@/stores/auth'
import { getApiErrorMessage } from '@/lib/http'
import { formatBusinessDate } from '@/lib/dateTime'
import { createRandomUuid } from '@/lib/randomUuid'
import { cartonOrderStockReturnApi, cartonSpecialStockActionsApi as api, type OrderStockReturnCommand, type OrderStockReturnLine, type SpecialStockAction, type SpecialStockCommand, type SpecialStockLine, type SpecialStockPreview, type SpecialStockResult, type SpecialStockUndo } from '@/api/cartonSpecialStockActions'

const props = defineProps<{ factoryId: string; requestId: string; requestNo: string; action: SpecialStockAction; regularOrder?: boolean; viewerKey?: string }>()
const emit = defineEmits<{ close: []; changed: [] }>()
const auth = useAuthStore()
type StockLine = SpecialStockLine | OrderStockReturnLine
type StockTarget = Pick<SpecialStockLine, 'receipt_line_id' | 'movement_id' | 'location_id'> | Pick<OrderStockReturnLine, 'order_line_id' | 'location_id'>
type StockPreview = Omit<SpecialStockPreview, 'lines'> & { lines: StockLine[] }
const preview = ref<StockPreview | null>(null), loading = ref(false), busy = ref(false), error = ref(''), storageBlocked = ref(false)
const sourceReadable = ref(false)
const result = ref<Pick<SpecialStockResult, 'action' | 'replenishment_request'> | null>(null), quantities = reactive<Record<string, string>>({})
const reason = ref(''), date = ref(''), responsibility = ref<'' | 'OWN' | 'SUPPLIER'>('')
type Pending = { sourceId: string; action: SpecialStockAction; kind?: undefined; body: SpecialStockCommand | SpecialStockUndo; display: SpecialStockLine[] }
  | { sourceId: string; action: 'RETURN'; kind: 'order'; body: OrderStockReturnCommand; display: OrderStockReturnLine[] }
const pending = ref<Pending | null>(null)
const title = computed(() => ({ RETURN: '订单退货', REPLENISH: '补单（原数量不变）', UNDO: '撤销未发货补单' })[props.action])
const regularReturn = computed(() => props.regularOrder && props.action === 'RETURN')
const scope = computed(() => JSON.stringify([props.factoryId, props.requestId, props.action, regularReturn.value, props.viewerKey, auth.currentUser?.id, auth.authorizationVersion, auth.authzMode, auth.currentUser?.identity?.effective_context_key, auth.currentUser?.identity?.employment_epoch]))
// Recovery follows the same actor/source across harmless permission refreshes.
// The live view still resets on every authorization/context change above.
const storageKey = computed(() => `${regularReturn.value ? 'carton-order-return' : 'carton-special-stock'}:${JSON.stringify([auth.currentUser?.id, auth.currentUser?.identity?.employment_epoch, props.factoryId, props.requestId, props.action])}`)
const canWrite = computed(() => ['read', 'order_write', 'inventory_write'].every(permission => ['carton', 'pmc-warehouse'].some(dept => auth.can(`carton_procurement:${permission}`, props.factoryId, dept))))
const permitted = computed(() => props.action === 'UNDO' ? preview.value?.replacement?.can_undo === true : props.action === 'RETURN' ? preview.value?.can_return === true : preview.value?.can_replenish === true)
const locked = computed(() => busy.value || loading.value || !!pending.value || !!result.value || storageBlocked.value || !canWrite.value || !sourceReadable.value)
const shownLines = computed(() => pending.value?.display || preview.value?.lines || [])
const blockers = computed(() => [...new Set([...(preview.value?.blockers || []), ...(props.action === 'UNDO' ? preview.value?.replacement?.blockers || [] : [])])])
const lineKey = (line: StockTarget) => JSON.stringify('order_line_id' in line
  ? [line.order_line_id, line.location_id] : [line.receipt_line_id, line.movement_id, line.location_id])
function validTarget(line: StockTarget) {
  return typeof line?.location_id === 'string' && !!line.location_id && ('order_line_id' in line
    ? regularReturn.value && typeof line.order_line_id === 'string' && !!line.order_line_id
    : !regularReturn.value && typeof line.receipt_line_id === 'string' && !!line.receipt_line_id
      && typeof line.movement_id === 'string' && !!line.movement_id)
}
const lacksReplacementCost = (line: StockLine) => props.action === 'REPLENISH' && responsibility.value === 'SUPPLIER'
  && 'inventory_unit_price' in line && line.inventory_unit_price == null
const fieldRows = computed(() => shownLines.value.map(line => {
  const id = lineKey(line)
  const fromReceipt = 'receipt_no' in line
  const missingCost = lacksReplacementCost(line)
  return {
    id, label: `${line.packaging_type} · ${line.paper_quality} · ${line.specification} ${line.dimension_unit}`,
    location: line.location_label, available: Number(line.safe_quantity), unit: line.unit, quantity: quantities[id] || '',
    aria: `${fromReceipt ? line.receipt_no : props.requestNo} ${line.packaging_type} ${line.location_label} 本次数量`,
    context: fromReceipt ? `${line.receipt_no} · ${line.item_no || '未填写货号'} · 原库存单价 ${line.inventory_unit_price ?? '待核价'} ${line.currency}` : undefined,
    warning: [...line.blockers, ...(missingCost ? ['原库存成本待核实，不能登记免费换补。'] : [])].join('；'),
    disabled: line.blockers.length > 0 || missingCost,
  }
}))
const today = () => formatBusinessDate(new Date().toISOString())
const maxLines = 100
let generation = 0, sequence = 0, controller = new AbortController()
let returnDefaultsApplied = false

function readPending() {
  const raw = localStorage.getItem(storageKey.value)
  if (!raw) return
  const saved = JSON.parse(raw) as Pending
  const body = saved.body
  if (saved.sourceId !== props.requestId || saved.action !== props.action || body?.factory_id !== props.factoryId
      || saved.kind !== (regularReturn.value ? 'order' : undefined)
      || typeof body.request_id !== 'string' || !/^[A-Za-z0-9_-]{16,96}$/.test(body.request_id)
      || !Number.isInteger(body.expected_revision) || body.expected_revision < 1 || typeof body.reason !== 'string'
      || !Array.isArray(saved.display) || saved.display.length > maxLines) throw new Error('上次请求记录无法读取，请先核实原办理结果；原记录已保留。')
  if (props.action !== 'UNDO') {
    if (!('action' in body) || body.action !== props.action || typeof body.source_fingerprint !== 'string' || !body.source_fingerprint
      || !Array.isArray(body.lines) || !body.lines.length || body.lines.length > maxLines
      || body.lines.some(line => !validTarget(line) || typeof line.quantity !== 'string' || !Number.isFinite(Number(line.quantity)) || Number(line.quantity) <= 0)) throw new Error('上次请求内容不完整，请先核实原办理结果；原记录已保留。')
    if (saved.display.length !== body.lines.length || saved.display.some(line => !validTarget(line)
      || [line.location_label, line.packaging_type, line.paper_quality, line.specification, line.unit, line.safe_quantity].some(value => typeof value !== 'string')
      || ('receipt_line_id' in line && (typeof line.receipt_no !== 'string' || typeof line.currency !== 'string'))
      || !Array.isArray(line.blockers) || line.blockers.some(message => typeof message !== 'string')
      || !body.lines.some(item => lineKey(item) === lineKey(line)))) throw new Error('上次请求的纸品摘要不完整，请先核实原办理结果；原记录已保留。')
  }
  pending.value = saved
  reason.value = body.reason
  if ('action' in body) {
    date.value = body.return_date || ('required_date' in body ? body.required_date || '' : '')
    responsibility.value = 'responsibility' in body ? body.responsibility || '' : ''
    body.lines.forEach(line => { quantities[lineKey(line)] = line.quantity })
  }
}

function syncQuantities(lines: StockLine[]) {
  const previous = { ...quantities }
  Object.keys(quantities).forEach(key => delete quantities[key])
  if (props.action !== 'RETURN') return
  for (const line of lines) {
    if (line.blockers.length || Number(line.safe_quantity) <= 0) continue
    const key = lineKey(line)
    const value = returnDefaultsApplied ? previous[key] : line.safe_quantity
    if (value !== undefined && Number(value) <= Number(line.safe_quantity)) quantities[key] = value
  }
  returnDefaultsApplied = true
}

async function load() {
  if (busy.value || !canWrite.value || storageBlocked.value || result.value) return
  const token = generation, read = ++sequence
  loading.value = true; error.value = ''; preview.value = null; sourceReadable.value = false
  try {
    const sourceApi = regularReturn.value ? cartonOrderStockReturnApi : api
    const data = await sourceApi.preview(props.factoryId, props.requestId, controller.signal)
    if (token !== generation || read !== sequence) return
    if (data.source_request.id !== props.requestId) throw new Error('返回的订单来源不一致，请刷新核实。')
    preview.value = data; sourceReadable.value = true
    if (!pending.value) syncQuantities(data.lines)
  } catch (cause) { if (token === generation && read === sequence) error.value = getApiErrorMessage(cause) }
  finally { if (token === generation && read === sequence) loading.value = false }
}
watch(() => `${scope.value}:${canWrite.value}`, () => {
  generation++; sequence++; controller.abort(); controller = new AbortController()
  returnDefaultsApplied = false
  preview.value = null; sourceReadable.value = false; pending.value = null; result.value = null; error.value = ''; busy.value = false; loading.value = false; storageBlocked.value = false
  Object.keys(quantities).forEach(key => delete quantities[key]); reason.value = ''; date.value = today(); responsibility.value = ''
  if (!canWrite.value) return
  try { readPending() } catch (cause) { storageBlocked.value = true; error.value = getApiErrorMessage(cause); return }
  void load()
}, { immediate: true })
function close() { if (!busy.value) emit('close') }
async function submit() {
  if (busy.value || result.value || !canWrite.value || !sourceReadable.value || storageBlocked.value) return
  error.value = ''
  const recovering = pending.value !== null
  if (!pending.value) {
    if (loading.value || !preview.value || !permitted.value) return
    if (reason.value.trim().length < 4) { error.value = '请填写至少四字原因。'; return }
    const base = { factory_id: props.factoryId, request_id: createRandomUuid(), expected_revision: preview.value.source_request.revision, reason: reason.value.trim() }
    const source = { sourceId: props.requestId, action: props.action }
    let saved: Pending = { ...source, body: base, display: [] }
    if (props.action !== 'UNDO') {
      if (!/^\d{4}-\d{2}-\d{2}$/.test(date.value) || props.action === 'RETURN' && date.value > today()) { error.value = '请填写有效日期；实际退货日期不能晚于今天。'; return }
      if (props.action === 'REPLENISH' && !responsibility.value) { error.value = '请选择补单责任方。'; return }
      const invalid = preview.value.lines.some(line => {
        const text = (quantities[lineKey(line)] || '').trim(), value = Number(text)
        return text !== '' && (!/^\d+(?:\.\d{1,4})?$/.test(text) || !Number.isFinite(value) || value < 0 || value > Number(line.safe_quantity)
          || value > 0 && (line.blockers.length > 0 || lacksReplacementCost(line)))
      })
      if (invalid) { error.value = '请核对数量、可办理上限和来源；供应商责任补单须先明确原库存成本。'; return }
      const selected = preview.value.lines.filter(line => Number(quantities[lineKey(line)] || 0) > 0)
      if (!selected.length) { error.value = '请至少填写一条纸品的本次数量。'; return }
      if (selected.length > maxLines) { error.value = `一次最多登记 ${maxLines} 行，请将其余行改为 0 后分次办理。`; return }
      const commandBase = { ...base, source_fingerprint: preview.value.source_fingerprint }
      const enteredQuantity = (line: StockLine) => quantities[lineKey(line)]!.trim()
      if (regularReturn.value) {
        const display = selected.filter(line => 'order_line_id' in line)
        saved = { sourceId: source.sourceId, kind: 'order', action: 'RETURN', display,
          body: { ...commandBase, action: 'RETURN', return_date: date.value,
            lines: display.map(line => ({ order_line_id: line.order_line_id, location_id: line.location_id, quantity: enteredQuantity(line) })) } }
      } else {
        const display = selected.filter(line => 'receipt_line_id' in line)
        saved = { ...source, display, body: { ...commandBase, action: props.action,
          ...(props.action === 'RETURN' ? { return_date: date.value } : { required_date: date.value, responsibility: responsibility.value as 'OWN' | 'SUPPLIER' }),
          lines: display.map(line => ({ receipt_line_id: line.receipt_line_id, movement_id: line.movement_id, location_id: line.location_id, quantity: enteredQuantity(line) })) } }
      }
    }
    try { localStorage.setItem(storageKey.value, JSON.stringify(saved)); pending.value = saved }
    catch { storageBlocked.value = true; error.value = '无法保存本次请求，尚未提交；请核实浏览器存储后再打开。'; return }
  }
  const token = generation, key = storageKey.value, sent = pending.value!
  busy.value = true
  try {
    const data = sent.kind === 'order'
      ? await cartonOrderStockReturnApi.submit(sent.sourceId, sent.body, controller.signal)
      : sent.action === 'UNDO' ? await api.undo(sent.sourceId, sent.body as SpecialStockUndo, controller.signal)
        : await api.submit(sent.sourceId, sent.body as SpecialStockCommand, controller.signal)
    if (token !== generation || key !== storageKey.value) return
    result.value = data; pending.value = null
    try { localStorage.removeItem(key) } catch { /* The saved idempotent request remains safe to verify again. */ }
    emit('changed')
  } catch (cause) {
    if (token !== generation || key !== storageKey.value) return
    const status = (cause as { response?: { status?: number } }).response?.status, message = getApiErrorMessage(cause)
    if (!recovering && status && [400, 409, 422].includes(status) && !/提交标识|请求标识|请求内容|原请求|已用于/.test(message)) {
      try { localStorage.removeItem(key); pending.value = null } catch { storageBlocked.value = true }
      preview.value = null; sourceReadable.value = false
      error.value = `${message}，请重新核对可办理数量。`
    } else {
      if (status === 401 || status === 403 || status === 404) { preview.value = null; sourceReadable.value = false }
      error.value = `${message}；结果尚未确认，已保留原请求，请核对原结果或使用下方按钮重试。`
    }
  } finally { if (token === generation) busy.value = false }
}
onBeforeUnmount(() => { generation++; controller.abort() })
</script>

<template>
  <DialogRoot :open="true" @update:open="!$event && close()">
    <DialogOverlay class="fixed inset-0 z-[75] bg-slate-950/45" />
    <DialogContent class="fixed left-1/2 top-1/2 z-[76] flex max-h-[90dvh] w-[calc(100%-2rem)] max-w-5xl -translate-x-1/2 -translate-y-1/2 flex-col overflow-hidden rounded-2xl border bg-white shadow-xl" @escape-key-down="busy && $event.preventDefault()" @interact-outside="busy && $event.preventDefault()">
      <header class="flex shrink-0 items-start justify-between gap-3 border-b p-4">
        <div><DialogTitle class="text-lg font-semibold text-slate-950">{{ title }}</DialogTitle><DialogDescription class="mt-1 text-xs text-slate-600">{{ requestNo }} · {{ action === 'RETURN' ? '按纸品和仓位核对本次退货数量' : '按原收料纸品和仓位核对本次数量' }}</DialogDescription></div>
        <Button variant="outline" size="sm" :disabled="busy" @click="close">关闭</Button>
      </header>
      <form class="flex min-h-0 flex-1 flex-col" @submit.prevent="submit">
        <div class="min-h-0 space-y-4 overflow-y-auto p-4">
          <p v-if="!canWrite" role="alert" class="rounded-lg bg-amber-50 p-3 text-sm text-amber-900">此操作需要本厂订单和库存权限，请联系负责人核实。</p>
          <p v-if="error" role="alert" class="rounded-lg border border-red-200 bg-red-50 p-3 text-sm text-red-700">{{ error }}</p>
          <div v-if="result" role="status" class="space-y-2 rounded-lg border border-teal-200 bg-teal-50 p-4 text-sm text-teal-900">
            <template v-if="result.action === 'REPLENISH'"><p>补单 {{ result.replenishment_request?.request_no }} 已建立，等待供应商确认接单。</p><p>原订单数量保留，本次换补出库已记账；后续按补单收料。</p></template>
            <p v-else-if="result.action === 'RETURN'">已登记实际退货。原需求数量保留，请在“月结对账 → 退货签收与退款”继续核对供应商签收及退款。</p>
            <p v-else>未发货补单已撤销，换补出库已冲回；供应商须确认收到停止通知。</p>
          </div>
          <template v-else-if="canWrite">
            <p v-if="action === 'RETURN'" class="rounded-lg bg-slate-50 p-3 text-xs leading-6 text-slate-600">默认填各仓位可退数量。只退一部分就改数量，不退的填 0。原需求和已收记录保留，月结按实际退货日期登记。</p>
            <p v-else-if="action === 'REPLENISH'" class="rounded-lg bg-slate-50 p-3 text-xs leading-6 text-slate-600">换补先扣减所选原库存，再生成独立补单，原订单数量不变。选择我方责任时按新收料计价；供应商责任为免费换补，保留原库存成本，不新增货款。</p>
            <p v-else class="rounded-lg bg-amber-50 p-3 text-xs leading-6 text-amber-900">只可撤销从未发货的补单，同时冲回原换补出库并通知供应商停止。已有送货、收料或关账事项时须先处理相关凭证。</p>
            <p v-if="pending" role="status" class="rounded-lg border border-amber-200 bg-amber-50 p-3 text-sm text-amber-900">上次办理结果待核对，本次内容已冻结。重试沿用原请求，不重复扣库存或建立补单。</p>
            <div v-if="!pending || !sourceReadable" class="flex flex-wrap items-center justify-between gap-2"><span class="text-xs text-slate-500">{{ loading ? '正在核对原收料与仓位…' : '仅列出有完整来源依据的可办理数量；来源不清须先核实。' }}</span><Button type="button" variant="outline" size="sm" :disabled="loading || busy || storageBlocked" @click="load">重新核对来源</Button></div>
            <ul v-if="blockers.length && !pending" role="alert" class="space-y-1 rounded-lg bg-amber-50 p-3 text-xs text-amber-900"><li v-for="message in blockers" :key="message">{{ message }}</li></ul>
            <template v-if="sourceReadable">
            <CartonOrderStockFields v-if="action !== 'UNDO'" :replenishment="action === 'REPLENISH'" v-model:responsibility="responsibility" v-model:date="date" :date-label="action === 'RETURN' ? '实际退货日期' : '补单交期'" :max-date="action === 'RETURN' ? today() : undefined" :disabled="locked" :lines="fieldRows" @quantity="(id, value) => quantities[id] = value" />
            <label class="block text-xs font-semibold text-slate-700">办理原因 *<textarea v-model="reason" :disabled="locked" aria-label="办理原因" required minlength="4" maxlength="500" rows="2" class="mt-1 w-full rounded-lg border border-slate-200 bg-white p-3" placeholder="请填写至少四字的实际原因" /></label>
            </template>
          </template>
        </div>
        <footer class="flex shrink-0 flex-wrap justify-end gap-2 border-t bg-white p-4"><Button type="button" variant="outline" :disabled="busy" @click="close">{{ result ? '返回订单' : '取消' }}</Button><Button v-if="!result" type="submit" :disabled="busy || loading || !canWrite || !sourceReadable || storageBlocked || !pending && !permitted">{{ busy ? '正在办理…' : pending ? '核对原结果 / 重试' : action === 'RETURN' ? '确认实际退货' : action === 'UNDO' ? '确认撤销补单' : '确认补单并登记换补出库' }}</Button></footer>
      </form>
    </DialogContent>
  </DialogRoot>
</template>
