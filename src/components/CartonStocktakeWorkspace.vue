<script setup lang="ts">
import CartonSelectionSummary from './CartonSelectionSummary.vue'
import { computed, onMounted, onBeforeUnmount, ref } from 'vue'
import { onBeforeRouteLeave, onBeforeRouteUpdate } from 'vue-router'
import { cartonProcurementApi, type CartonInventoryBalanceResponse } from '@/api/cartonProcurement'
import { cartonStocktakeApi, type StocktakeDetail, type StocktakeHeader, type StocktakeAction, type StocktakeStatus } from '@/api/cartonStocktake'
import { useAuthStore } from '@/stores/auth'
import { getApiErrorMessage } from '@/lib/http'

const props = defineProps<{ factoryId: string; initialPositionKeys?: string[] }>()
const emit = defineEmits<{ close: []; posted: [] }>()
const auth = useAuthStore()
const balances = ref<CartonInventoryBalanceResponse[]>([])
const documents = ref<StocktakeHeader[]>([])
const doc = ref<StocktakeDetail | null>(null)
const inventoryQuery = ref(''), documentStatus = ref<StocktakeStatus | ''>('')
const customer = ref(''), location = ref(''), chosen = ref<string[]>([])
const busy = ref(false), error = ref(''), message = ref(''), dirty = ref(false), acknowledged = ref(false)
const counts = ref<Record<string, { actual: string; reason: string }>>({})
const reviewReason = ref(''), offset = ref(0)
const cancelReason = ref('取消本次盘点')
const serviceReady = ref(false)
const openingSelection = ref(Boolean(props.initialPositionKeys?.length))
let active = true
const statusNames = { DRAFT: '待盘点', SUBMITTED: '待主管复核', POSTED: '已入账', CANCELLED: '已取消' }
const actionNames: Record<string, string> = { STOCKTAKE_CREATED: '生成盘点单', STOCKTAKE_SAVE: '保存草稿', STOCKTAKE_SUBMIT: '提交复核', STOCKTAKE_APPROVE: '复核入账', STOCKTAKE_RETURN: '退回重盘', STOCKTAKE_CANCEL: '取消盘点' }
const canWrite = computed(() => ['carton', 'pmc-warehouse'].some(dept => auth.can('carton_procurement:inventory_write', props.factoryId, dept)))
const supervisor = computed(() => canWrite.value && ['carton', 'pmc-warehouse'].some(dept => auth.can('carton_procurement:order_adjust', props.factoryId, dept)))
const own = computed(() => doc.value?.created_by === auth.currentUser?.id)
const editable = computed(() => doc.value?.status === 'DRAFT' && own.value && canWrite.value && !doc.value?.reconciliation_error)
const canApprove = computed(() => supervisor.value && !own.value && doc.value?.submitted_by !== auth.currentUser?.id && !doc.value?.reconciliation_error)
const customers = computed(() => [...new Map(balances.value.map(row => [row.customer_code, row.customer_name])).entries()])
const locations = computed(() => [...new Set(balances.value.map(row => row.latest_location))].sort())
const filtered = computed(() => balances.value.filter(row => (!customer.value || row.customer_code === customer.value) && (!location.value || (row.latest_location || '__empty') === location.value) && [row.contract_no, row.item_no, row.packaging_type, row.paper_quality, row.specification].join(' ').toLowerCase().includes(inventoryQuery.value.trim().toLowerCase())))
const selectedVisible = computed(() => filtered.value.length > 0 && filtered.value.every(row => chosen.value.includes((row.position_key || row.latest_movement_id))))
function selectVisible(checked: boolean) {
  const ids = filtered.value.map(row => (row.position_key || row.latest_movement_id))
  chosen.value = checked ? [...new Set([...chosen.value, ...ids])] : chosen.value.filter(id => !ids.includes(id))
}
function changed() { dirty.value = true; acknowledged.value = false }
function accept(result: StocktakeDetail, preserve = false) {
  const previous = counts.value
  doc.value = result
  counts.value = Object.fromEntries(result.lines.map(line => [line.id, preserve && previous[line.id] ? previous[line.id] : { actual: line.actual_quantity === null ? '' : String(line.actual_quantity), reason: line.reason }]))
  dirty.value = preserve
  acknowledged.value = false
  reviewReason.value = ''
  cancelReason.value = '取消本次盘点'
}
async function run(action: () => Promise<void>) {
  if (busy.value) return
  busy.value = true; error.value = ''; message.value = ''
  try { await action() } catch (err) { error.value = getApiErrorMessage(err); acknowledged.value = false }
  finally { busy.value = false }
}
async function load() {
  await run(async () => {
    const result = await Promise.allSettled([cartonProcurementApi.listInventoryBalances(props.factoryId), cartonStocktakeApi.list(props.factoryId, offset.value, documentStatus.value)])
    if (result[0].status === 'fulfilled') balances.value = result[0].value
    serviceReady.value = result[1].status === 'fulfilled'
    if (result[1].status === 'fulfilled') documents.value = result[1].value
    else {
      documents.value = []
      const failure = result[1].reason as { response?: { status?: number } }
      if (failure?.response?.status === 404) { error.value = '盘点服务尚未启用，请联系管理员启用后再生成盘点单。'; return }
      throw result[1].reason
    }
    if (result[0].status === 'rejected') throw result[0].reason
  })
}
function leave() { return !dirty.value || window.confirm('当前实盘填写尚未保存，确定离开吗？') }
async function open(id: string) {
  if (!leave()) return
  await run(async () => accept(await cartonStocktakeApi.detail(props.factoryId, id)))
}
async function refresh() {
  if (!doc.value) return
  const id = doc.value.id
  await run(async () => {
    const result = await cartonStocktakeApi.detail(props.factoryId, id)
    accept(result, result.status === 'DRAFT')
    message.value = '账面已刷新，填写值已保留供比较。请重新核对实盘、仓位和差异原因，再确认截止口径。'
  })
}
async function create() {
  if (!serviceReady.value || !canWrite.value || !chosen.value.length || chosen.value.length > 500) return
  await run(async () => accept(await cartonStocktakeApi.create(props.factoryId, chosen.value)))
}
async function initialize() {
  await load()
  if (!active) return
  const initial = [...new Set(props.initialPositionKeys ?? [])]
  if (initial.length) {
    chosen.value = initial
    const available = new Set(balances.value.map(row => row.position_key || row.latest_movement_id))
    if (!error.value && initial.every(key => available.has(key))) await create()
    else if (!error.value) error.value = '所选库存已变化，请返回台账刷新后重新选择。'
  }
  openingSelection.value = false
}
function difference(id: string, book: string | null) {
  if (book === null) return '—'
  const actual = counts.value[id]?.actual.trim() ?? ''
  return actual === '' || !Number.isFinite(Number(actual)) ? '未盘点' : Number((Number(actual) - Number(book)).toFixed(4)).toLocaleString('zh-CN', { maximumFractionDigits: 4 })
}
async function act(action: StocktakeAction) {
  const current = doc.value
  if (!current) return
  if (action === 'APPROVE' && !window.confirm('确认按本单差额入账？提交后的收发货将保留，入账后不能修改盘点单。')) return
  await run(async () => {
    const result = await cartonStocktakeApi.act(current.id, {
      factory_id: props.factoryId, expected_revision: current.revision, action,
      ledger_token: current.ledger_token, cutoff_acknowledged: acknowledged.value, reason: action === 'CANCEL' ? cancelReason.value : reviewReason.value,
      lines: current.lines.map(line => ({ id: line.id, actual_quantity: counts.value[line.id]?.actual.trim() || null, reason: counts.value[line.id]?.reason.trim() || '' })),
    })
    accept(result)
    message.value = action === 'SAVE' ? '草稿已保存。' : `盘点单${statusNames[result.status]}。`
    if (action === 'APPROVE') emit('posted')
  })
}
async function back() { if (leave()) { doc.value = null; dirty.value = false; chosen.value = []; await load() } }
async function page(step: number) { offset.value = Math.max(0, offset.value + step * 100); await load() }
function beforeUnload(event: BeforeUnloadEvent) {
  if (dirty.value) { event.preventDefault(); event.returnValue = '' }
}
onBeforeRouteLeave(() => !busy.value && leave())
onBeforeRouteUpdate((to, from) => {
  if (to.query.tab !== from.query.tab || to.query.factory !== from.query.factory) return !busy.value && leave()
})
onMounted(() => { void initialize(); window.addEventListener('beforeunload', beforeUnload) })
onBeforeUnmount(() => { active = false; window.removeEventListener('beforeunload', beforeUnload) })
</script>

<template>
  <section class="space-y-4 rounded-xl border border-teal-200 bg-white p-5 shadow-sm" aria-label="库存盘点工作台">
    <header class="flex flex-wrap items-center justify-between gap-3">
      <div><h2 class="text-lg font-bold text-slate-950">库存盘点<span v-if="doc" class="ml-3 rounded-full bg-teal-50 px-3 py-1 text-xs text-teal-700">{{ statusNames[doc.status] }}</span></h2><p class="mt-1 text-xs text-slate-500">选择库存 → 填写实盘 → 主管复核 → 差额入账</p></div>
      <div class="flex gap-2"><button v-if="doc" :disabled="busy" class="secondary" @click="back">盘点单列表</button><button :disabled="busy" class="secondary" @click="leave() && emit('close')">返回库存台账</button></div>
    </header>
    <p v-if="error" role="alert" class="rounded-lg bg-red-50 p-3 text-sm text-red-700">{{ error }}<button v-if="doc" :disabled="busy" class="ml-3 underline" @click="refresh">刷新并重新核对</button></p>
    <p v-if="message" role="status" class="rounded-lg bg-teal-50 p-3 text-sm text-teal-800">{{ message }}</p>
    <p v-if="busy" role="status" class="text-sm text-slate-500">正在处理…</p>
    <template v-if="!doc && !openingSelection">
      <div class="flex flex-wrap items-center gap-3 rounded-lg bg-slate-50 p-3">
        <label>客户 <select v-model="customer" aria-label="盘点客户"><option value="">全部客户</option><option v-for="[code, name] in customers" :key="code" :value="code">{{ name }}</option></select></label>
        <label>仓位 <select v-model="location" aria-label="盘点仓位"><option value="">全部仓位</option><option v-for="place in locations" :key="place" :value="place || '__empty'">{{ place || '未设置仓位' }}</option></select></label>
        <input v-model="inventoryQuery" aria-label="盘点库存搜索" placeholder="合同 / 货号 / 纸品" class="h-9 rounded border px-3"><button type="button" class="secondary" @click="customer = ''; location = ''; inventoryQuery = ''">清空筛选</button>
        <span class="ml-auto text-xs text-slate-500">已选 {{ chosen.length }} 条 / 最多 500 条</span><button class="primary" :disabled="busy || !serviceReady || !canWrite || !chosen.length || chosen.length > 500" @click="create">生成盘点单</button>
      </div>
      <CartonSelectionSummary :rows="balances.filter(row => chosen.includes(row.position_key || row.latest_movement_id)).map(row => ({ id: row.position_key || row.latest_movement_id, label: `${row.customer_name} · ${row.contract_no} · ${row.item_no} · ${row.latest_location}` }))" :visible-ids="filtered.map(row => row.position_key || row.latest_movement_id)" @clear="chosen = []" @remove="chosen = chosen.filter(id => id !== $event)" />
      <div class="max-h-80 overflow-auto rounded-lg border border-slate-200"><table class="min-w-[900px]"><colgroup><col style="width:44px"><col style="width:8%"><col style="width:22%"><col style="width:18%"><col><col style="width:13%"><col style="width:110px"></colgroup><thead><tr><th><input type="checkbox" aria-label="全选盘点筛选结果" :checked="selectedVisible" :indeterminate="!selectedVisible && filtered.some(row => chosen.includes(row.position_key || row.latest_movement_id))" @change="selectVisible(($event.target as HTMLInputElement).checked)"></th><th>客户</th><th>合同号</th><th>货号</th><th>纸品 / 纸质 / 规格</th><th>仓位</th><th class="text-right">账面数量</th></tr></thead><tbody>
        <tr v-for="row in filtered" :key="(row.position_key || row.latest_movement_id)"><td><input v-model="chosen" type="checkbox" :value="(row.position_key || row.latest_movement_id)" :aria-label="`盘点 ${row.contract_no} ${row.item_no} ${row.packaging_type}`"></td><td>{{ row.customer_name }}</td><td>{{ row.contract_no }}</td><td>{{ row.item_no }}</td><td>{{ row.packaging_type }} · {{ row.paper_quality }} · {{ row.specification }}</td><td>{{ row.latest_location || '未设置' }}</td><td class="text-right font-semibold">{{ Number(row.balance).toLocaleString() }} {{ row.unit }}</td></tr>
        <tr v-if="!filtered.length"><td colspan="7" class="text-center text-slate-400">没有符合条件的库存</td></tr>
      </tbody></table></div>
      <div class="border-t pt-4"><div class="mb-2 flex flex-wrap items-center justify-between gap-3"><h3 class="font-bold">盘点记录</h3><label class="block text-xs">状态 <select v-model="documentStatus" :disabled="busy" aria-label="盘点记录状态" @change="offset = 0; load()"><option value="">全部状态</option><option v-for="(label, value) in statusNames" :key="value" :value="value">{{ label }}</option></select></label></div><p class="my-2 text-xs text-slate-500">同一库存同时只能有一张进行中的盘点单，可打开草稿继续填写。</p>
        <div class="overflow-auto rounded-lg border border-slate-200"><table class="stocktake-records min-w-[850px]"><colgroup><col><col style="width:180px"><col style="width:100px"><col style="width:180px"><col style="width:120px"></colgroup><thead><tr><th>盘点单号</th><th>创建人 / 时间</th><th>状态</th><th>复核人 / 时间</th><th class="text-right">操作</th></tr></thead><tbody><tr v-for="item in documents" :key="item.id"><td class="font-mono text-xs">{{ item.id }}</td><td>{{ item.created_by_name }}<small>{{ item.created_at.replace('T', ' ').slice(0, 19) }}</small></td><td>{{ statusNames[item.status] }}</td><td>{{ item.reviewed_by_name || '—' }}<small>{{ item.reviewed_at.replace('T', ' ').slice(0, 19) }}</small></td><td class="text-right"><button class="secondary whitespace-nowrap" :disabled="busy" @click="open(item.id)">查看 / 处理</button></td></tr><tr v-if="!documents.length"><td colspan="5" class="text-center text-slate-400">暂无盘点记录</td></tr></tbody></table></div>
        <div class="mt-3 flex justify-end gap-2"><button class="secondary" :disabled="busy || offset === 0" @click="page(-1)">上一页</button><button class="secondary" :disabled="busy || documents.length < 100" @click="page(1)">下一页</button></div>
      </div>
    </template>
    <template v-else-if="doc">
      <div class="rounded-lg bg-slate-50 p-3 text-xs leading-6 text-slate-600"><div class="font-mono">{{ doc.id }}</div><div>创建人 {{ doc.created_by_name }} · {{ doc.created_at.replace('T', ' ').slice(0, 19) }}</div><div v-if="doc.submitted_at">提交人 {{ doc.submitted_by_name }} · 盘点截止 {{ doc.submitted_at.replace('T', ' ').slice(0, 19) }}</div><div v-if="doc.reviewed_at">复核人 {{ doc.reviewed_by_name }} · {{ doc.reviewed_at.replace('T', ' ').slice(0, 19) }}</div><div v-if="doc.note" class="text-amber-700">退回 / 取消说明：{{ doc.note }}</div></div>
      <div v-if="doc.status === 'DRAFT'" class="rounded-lg border border-amber-200 bg-amber-50 p-3 text-sm leading-6 text-amber-900">账面截止：{{ doc.cutoff_at.replace('T', ' ').slice(0, 19) }}。请以此时点核对实物；期间有收发货或调仓，先刷新并重新核对。空白表示未盘，实际没有库存请填 0。<button class="ml-2 underline" :disabled="busy" @click="refresh">刷新账面</button></div>
      <p v-if="doc.reconciliation_error" role="alert" class="rounded-lg bg-red-50 p-3 text-sm text-red-700">{{ doc.reconciliation_error }}</p>
      <p v-if="doc.status === 'DRAFT' && doc.basis_changed" role="alert" class="rounded-lg bg-amber-50 p-3 text-sm font-semibold text-amber-800">上次填写后有收发货或仓位变化，原实盘数字仅供参考。请对照上次账面重新核对，不能直接沿用旧数字提交。</p>
      <p v-if="doc.status !== 'DRAFT'" class="text-sm text-slate-600">复核按已提交差额入账，保留提交后的正常收发货。盘盈按当前平均库存成本计价；无可用成本时标记缺价，核价后才能关账。</p>
      <div class="overflow-auto"><table class="min-w-[1080px]"><thead><tr><th>客户 / 合同</th><th>货号 / 纸品</th><th>纸质 / 规格</th><th>仓位</th><th>建单账面</th><th>{{ doc.status === 'DRAFT' ? '当前账面' : '盘点账面' }}</th><th>实盘数量</th><th>差异</th><th>差异原因</th></tr></thead><tbody>
        <tr v-for="line in doc.lines" :key="line.id"><td>{{ line.customer_name }}<small>{{ line.contract_no }}</small></td><td>{{ line.item_no }}<small>{{ line.packaging_type }}</small></td><td>{{ line.paper_quality }}<small>{{ line.specification }}</small></td><td>{{ line.latest_location || '未设置' }}<small v-if="line.location_changed" class="text-red-600">仓位已变化</small></td><td>{{ Number(line.initial_quantity) }} {{ line.unit }}<small v-if="doc.status === 'DRAFT' && doc.basis_changed">上次账面 {{ Number(line.count_book_quantity) }}</small></td><td>{{ doc.status === 'DRAFT' && line.current_quantity === null ? '—' : Number(doc.status === 'DRAFT' ? line.current_quantity : line.count_book_quantity) }} {{ line.unit }}</td>
          <td><input v-if="editable && counts[line.id]" v-model="counts[line.id]!.actual" :disabled="busy" inputmode="decimal" class="w-28" :aria-label="`实盘数量 ${line.id}`" placeholder="未盘点" @input="changed"><span v-else>{{ line.actual_quantity === null ? '未盘点' : Number(line.actual_quantity) }}</span></td>
          <td class="font-semibold text-teal-700">{{ doc.status === 'DRAFT' ? difference(line.id, line.current_quantity) : Number(line.difference) }}</td><td><input v-if="editable && counts[line.id]" v-model="counts[line.id]!.reason" :disabled="busy" class="w-44" :aria-label="`差异原因 ${line.id}`" placeholder="有差异必填" maxlength="1000" @input="changed"><span v-else>{{ line.reason || '—' }}</span></td>
        </tr>
      </tbody></table></div>
      <footer class="space-y-3 rounded-lg bg-slate-50 p-4">
        <label v-if="editable" class="flex items-start gap-2 text-sm"><input v-model="acknowledged" :disabled="busy" type="checkbox" class="mt-1">我已逐项核对实盘数量与上方账面截止时点一致，并核对期间收发货。</label>
        <div class="flex flex-wrap items-center gap-2"><template v-if="editable"><button class="secondary" :disabled="busy" @click="act('SAVE')">保存草稿</button><button class="primary" :disabled="busy || !acknowledged" @click="act('SUBMIT')">提交主管复核</button></template>
          <template v-if="doc.status === 'SUBMITTED' && canApprove"><button class="primary" :disabled="busy" @click="act('APPROVE')">复核并差额入账</button></template>
          <p v-if="doc.status === 'SUBMITTED' && !canApprove" class="text-sm text-slate-500">等待另一位有复核权限的主管处理。</p>
          <template v-if="['DRAFT', 'SUBMITTED'].includes(doc.status) && canWrite && (own || supervisor)">
            <template v-if="doc.status === 'SUBMITTED' && supervisor"><input v-model="reviewReason" :disabled="busy" aria-label="盘点退回原因" placeholder="请说明哪些项目需要重盘" class="w-64" maxlength="1000"><button class="secondary" :disabled="busy || !reviewReason.trim()" @click="act('RETURN')">退回重盘</button></template>
            <label class="ml-auto text-xs">取消原因（可修改）<input v-model="cancelReason" :disabled="busy" aria-label="盘点取消原因" class="ml-2 w-48" maxlength="1000"></label><button class="secondary" :disabled="busy || !cancelReason.trim()" @click="act('CANCEL')">取消盘点</button>
          </template>
        </div>
      </footer>
      <details class="text-xs text-slate-500"><summary class="cursor-pointer">操作记录（{{ doc.events.length }}）</summary><p v-for="(event, index) in doc.events" :key="index" class="mt-2">{{ event.at.replace('T', ' ').slice(0, 19) }} · {{ event.actor }} · {{ actionNames[event.action] || event.action }} {{ event.detail.reason }}</p></details>
    </template>
  </section>
</template>

<style scoped>
table { width: 100%; text-align: left; font-size: 12px; border-collapse: collapse; }
th { background: #f8fafc; color: #64748b; font-size: 11px; white-space: nowrap; }
tbody tr:hover { background: #f8fafc; }
.stocktake-records td { vertical-align: middle; }
th, td { padding: 12px; border-bottom: 1px solid #f1f5f9; }
small { display: block; margin-top: 4px; color: #64748b; }
label { font-size: 12px; color: #475569; }
input:not([type=checkbox]), select { border: 1px solid #e2e8f0; border-radius: 8px; padding: 8px; background: white; font-size: 12px; }
input[type=checkbox] { accent-color: #0f766e; width: 16px; height: 16px; }
button.primary, button.secondary { border-radius: 8px; padding: 9px 12px; font-size: 12px; font-weight: 600; }
.primary { background: #0f766e; color: white; }
.secondary { border: 1px solid #e2e8f0; background: white; color: #475569; }
button:disabled { opacity: .4; cursor: not-allowed; }
</style>
