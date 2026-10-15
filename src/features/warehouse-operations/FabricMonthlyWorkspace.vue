<script setup lang="ts">
import { computed, inject, onBeforeUnmount, ref, watch } from 'vue'
import { RouterLink, useRoute } from 'vue-router'
import { DialogRoot, DialogPortal, DialogOverlay, DialogContent, DialogTitle, DialogDescription } from 'reka-ui'
import { Download, RefreshCw } from '@lucide/vue'
import { isAxiosError } from 'axios'
import { useAuthStore } from '@/stores/auth'
import { getApiErrorMessage } from '@/lib/http'
import Button from '@/components/ui/button/Button.vue'
import { warehouseOperationsApi as api, type FabricMonthlyDetail, type FabricMonthlyQuery, type FabricMonthlyReport, type FabricMonthlyView } from '@/api/warehouseOperations'
import { monthlySearchKey } from './inventorySearch'

const props = defineProps<{ view: FabricMonthlyView }>()
const route = useRoute(), auth = useAuthStore(), headerSearch = inject(monthlySearchKey, undefined)
const thisMonth = () => new Intl.DateTimeFormat('sv-SE', { timeZone: 'Asia/Shanghai' }).format(new Date()).slice(0, 7)
const month = ref(thisMonth()), channel = ref<FabricMonthlyQuery['channel']>(''), party = ref(''), unit = ref('')
const dateOrder = ref<'ASC' | 'DESC'>('DESC'), result = ref<FabricMonthlyReport>(), appliedQuery = ref<FabricMonthlyQuery>()
const loading = ref(false), exporting = ref(false), error = ref(''), selected = ref<FabricMonthlyDetail>()
const mode = ref<'summary' | 'details'>('summary'), page = ref(0), pageSize = 25
const parties = ref<FabricMonthlyReport['parties']>([]), units = ref<string[]>([])
const search = computed(() => headerSearch?.search.value.trim() ?? '')
const direction = computed<FabricMonthlyQuery['direction']>(() => props.view === 'reconciliation' ? 'IN' : props.view === 'recipients' ? 'OUT' : '')
const title = computed(() => props.view === 'reconciliation' ? '供应商收料对账' : props.view === 'recipients' ? '领用方发料对账' : '收发数量汇总')
const description = computed(() => direction.value === 'IN' ? '按供应商核对本月实际收料与收料冲销，保留原单依据。' : direction.value === 'OUT' ? '按领用方核对实发、冲销与车间退料，查看实际净领用数量。' : '按业务月份查看实际收发；供应商进货与领用方发料分别汇总。')
const query = (): FabricMonthlyQuery => ({ month: month.value, direction: direction.value, channel: channel.value, party_key: party.value, search: search.value, unit: unit.value, date_order: dateOrder.value })
const ready = () => route.query.factory === 'huakang-c' && !!auth.currentUser?.id
const total = computed(() => (mode.value === 'summary' ? result.value?.summary.length : result.value?.details.length) ?? 0)
const pageCount = computed(() => Math.max(1, Math.ceil(total.value / pageSize)))
const summaryRows = computed(() => result.value?.summary.slice(page.value * pageSize, (page.value + 1) * pageSize) ?? [])
const detailRows = computed(() => result.value?.details.slice(page.value * pageSize, (page.value + 1) * pageSize) ?? [])
const hasFilters = computed(() => !!(search.value || channel.value || party.value || unit.value || dateOrder.value !== 'DESC' || month.value !== thisMonth()))
const kindLabel = (row: FabricMonthlyDetail) => `${row.correction ? '冲销 · ' : ''}${row.kind === 'RECEIPT' ? '供应商实收' : row.kind === 'ISSUE' ? '实际发料' : '车间退料'}`
const channelLabel = (row: FabricMonthlyDetail) => row.channel === 'SCAN' ? '送货 / 领料单' : row.origin === 'PROCUREMENT_RECEIVING' ? '采购实收' : '手工登记'
const sourceLink = computed(() => selected.value?.document_id ? { path: '/modules/pmc-warehouse/material-handover', query: { factory: 'huakang-c', tab: 'documents', document: selected.value.document_id } } : undefined)
let generation = 0, searchTimer: ReturnType<typeof setTimeout> | undefined
function invalidate() {
  generation++; clearTimeout(searchTimer); result.value = undefined; appliedQuery.value = undefined
  selected.value = undefined; error.value = ''; loading.value = false; exporting.value = false; page.value = 0
}
async function load() {
  invalidate()
  if (!ready()) return
  if (!/^\d{4}-(0[1-9]|1[0-2])$/.test(month.value)) { error.value = '请选择有效的核对月份。'; return }
  const epoch = generation, requested = query()
  loading.value = true
  try {
    const report = await api.monthly(requested)
    if (epoch === generation) {
      result.value = report; appliedQuery.value = requested
      parties.value = report.parties; units.value = report.units ?? report.totals.map(row => row.unit)
    }
  } catch (e) { if (epoch === generation) error.value = getApiErrorMessage(e) }
  finally { if (epoch === generation) loading.value = false }
}
function reset() {
  month.value = thisMonth(); channel.value = ''; party.value = ''; unit.value = ''; dateOrder.value = 'DESC'
  if (headerSearch) headerSearch.search.value = ''
}
async function download() {
  if (!result.value || !appliedQuery.value || loading.value || exporting.value || !ready()) return
  const epoch = generation, saved = result.value, requested = { ...appliedQuery.value }, savedTitle = title.value
  exporting.value = true; error.value = ''
  try {
    const file = await api.exportMonthly(requested, saved.version)
    if (epoch !== generation) return
    const url = URL.createObjectURL(file), link = document.createElement('a')
    link.href = url; link.download = `${saved.month}-${savedTitle}.xlsx`; link.click()
    setTimeout(() => URL.revokeObjectURL(url), 30000)
  } catch (e) { if (epoch === generation) error.value = isAxiosError(e) && e.response?.status === 409 ? '收发记录已变化，请刷新汇总后再导出。' : getApiErrorMessage(e) }
  finally { if (epoch === generation) exporting.value = false }
}
watch([() => props.view, () => route.query.factory, () => auth.currentUser?.id, () => auth.authorizationVersion], (_, previous) => {
  if (previous.length && (previous[1] !== route.query.factory || previous[2] !== auth.currentUser?.id || previous[3] !== auth.authorizationVersion) && headerSearch) headerSearch.search.value = ''
  party.value = ''; channel.value = ''; unit.value = ''; parties.value = []; units.value = []; mode.value = 'summary'; void load()
}, { immediate: true })
watch(month, () => { party.value = ''; unit.value = ''; parties.value = []; units.value = [] })
watch([month, channel, party, unit, dateOrder], load)
watch(search, () => { invalidate(); searchTimer = setTimeout(load, 250) }, { flush: 'sync' })
watch(() => headerSearch?.submitted.value, load)
watch(mode, () => { page.value = 0 })
onBeforeUnmount(() => { generation++; clearTimeout(searchTimer) })
</script>

<template>
  <section class="fabric-monthly">
    <header class="monthly-heading"><div><h2>{{ title }}</h2><p>{{ description }}</p></div><div class="monthly-actions"><Button variant="outline" :disabled="loading" @click="load"><RefreshCw :size="14" />刷新</Button><Button :disabled="loading || exporting || !result || !result.details.length" @click="download"><Download :size="14" />{{ exporting ? '正在导出…' : '导出当前对账表' }}</Button></div></header>
    <div class="monthly-filters">
      <label>核对月份<input v-model="month" type="month" aria-label="月结核对月份" /></label>
      <label>登记来源<select v-model="channel" aria-label="月结登记方式"><option value="">全部来源</option><option value="MANUAL">采购 / 手工登记</option><option value="SCAN">送货 / 领料单</option></select></label>
      <label>{{ direction === 'IN' ? '供应商' : direction === 'OUT' ? '领用方' : '往来方' }}<select v-model="party" aria-label="月结往来方"><option value="">全部{{ direction === 'IN' ? '供应商' : direction === 'OUT' ? '领用方' : '往来方' }}</option><option v-for="item in parties" :key="item.key" :value="item.key">{{ !direction ? (item.direction === 'IN' ? '供应商 · ' : '领用方 · ') : '' }}{{ item.name || '原单未填写' }}</option></select></label>
      <label>原单位<select v-model="unit" aria-label="月结原单位"><option value="">全部单位</option><option v-for="value in units" :key="value">{{ value }}</option></select></label>
      <label>明细排序<select v-model="dateOrder" aria-label="月结明细排序"><option value="DESC">业务日期 · 最新在前</option><option value="ASC">业务日期 · 最早在前</option></select></label>
      <Button variant="ghost" :disabled="!hasFilters" @click="reset">重置筛选</Button>
    </div>
    <div class="monthly-context"><span>实时数量核对 · 未关账</span><span>合计与导出均包含当前筛选下的全部记录</span></div>
    <p v-if="error" class="monthly-message error" role="alert">{{ error }}</p><p v-if="loading" class="monthly-message" role="status">正在汇总实际收发记录…</p>
    <template v-if="result">
      <div v-if="result.totals.length" class="monthly-totals" aria-label="当前筛选数量合计"><article v-for="row in result.totals" :key="row.unit"><span class="unit-tag">{{ row.unit }}</span><div v-if="direction !== 'OUT'"><span>净实收</span><strong>{{ row.net_received }}</strong><small>实收 {{ row.received }} − 冲销 {{ row.receipt_reversed }}</small></div><div v-if="direction !== 'IN'"><span>净发料</span><strong>{{ row.net_outbound }}</strong><small>实发 {{ row.issued }} − 冲销 {{ row.issue_reversed }} − 退料 {{ row.returned }}</small></div><div v-if="!direction"><span>收发净增减</span><strong>{{ row.stock_change }}</strong><small>不含期初导入与盘点差异</small></div></article></div>
      <nav class="monthly-modes" aria-label="对账展示方式"><button :aria-pressed="mode === 'summary'" @click="mode = 'summary'">往来方 / 物料汇总 <span>{{ result.summary.length }}</span></button><button :aria-pressed="mode === 'details'" @click="mode = 'details'">收发明细 <span>{{ result.details.length }}</span></button><span>{{ result.month }}<template v-if="search"> · 关键字：{{ search }}</template></span></nav>
      <div v-if="!total" class="monthly-empty" role="status"><strong>暂无符合条件的实际收发记录</strong><p>可调整月份或筛选条件；尚未实际收发的送货单、领料申请不会计入。</p></div>
      <div v-else-if="mode === 'summary'" class="monthly-scroll" role="region" aria-label="往来方物料汇总" tabindex="0"><table><thead><tr><th>往来方 / 方向</th><th>物料名称 / 编码</th><th>单位</th><th class="number">凭证数</th><template v-if="direction === 'IN'"><th class="number">实收</th><th class="number">收料冲销</th></template><template v-if="direction === 'OUT'"><th class="number">实发</th><th class="number">发料冲销</th><th class="number">车间退料</th></template><th v-if="direction !== 'OUT'" class="number">净实收</th><th v-if="direction !== 'IN'" class="number">净发料</th></tr></thead><tbody><tr v-for="row in summaryRows" :key="JSON.stringify([row.direction,row.party_key,row.item_code,row.unit])"><td><strong>{{ row.party_name || '原单未填写' }}</strong><small>{{ row.direction === 'IN' ? '供应商收料' : '领用方发料' }}</small></td><td><strong>{{ row.item_name || '未记录名称' }}</strong><small>{{ row.item_code }}</small></td><td>{{ row.unit }}</td><td class="number">{{ row.document_count }}</td><template v-if="direction === 'IN'"><td class="number">{{ row.received }}</td><td class="number">{{ row.receipt_reversed }}</td></template><template v-if="direction === 'OUT'"><td class="number">{{ row.issued }}</td><td class="number">{{ row.issue_reversed }}</td><td class="number">{{ row.returned }}</td></template><td v-if="direction !== 'OUT'" class="number net">{{ row.direction === 'IN' ? row.net_received : '—' }}</td><td v-if="direction !== 'IN'" class="number net">{{ row.direction === 'OUT' ? row.net_outbound : '—' }}</td></tr></tbody></table></div>
      <div v-else class="monthly-scroll" role="region" aria-label="收发凭证明细" tabindex="0"><table><thead><tr><th>业务日期 / 类型</th><th>往来方</th><th>物料名称 / 编码</th><th class="number">数量 / 单位</th><th>来源单据 / 登记来源</th><th>操作</th></tr></thead><tbody><tr v-for="row in detailRows" :key="row.id"><td><strong>{{ row.date }}</strong><small :class="{ correction: row.correction }">{{ kindLabel(row) }}</small></td><td>{{ row.party_name || '原单未填写' }}</td><td><strong>{{ row.item_name || '未记录名称' }}</strong><small>{{ row.item_code }}</small></td><td class="number" :class="{ correction: row.correction }"><strong>{{ row.quantity }} {{ row.unit }}</strong></td><td>{{ row.source_no }}<small>{{ channelLabel(row) }}</small></td><td><Button variant="ghost" size="sm" :aria-label="`查看凭证 ${row.id}`" @click="selected = row">详情</Button></td></tr></tbody></table></div>
      <footer class="monthly-footer"><span>共 {{ total }} {{ mode === 'summary' ? '组' : '笔' }}<template v-if="total"> · 显示 {{ page * pageSize + 1 }}–{{ Math.min((page + 1) * pageSize, total) }}</template></span><div><Button variant="outline" size="sm" :disabled="page === 0" @click="page--">上一页</Button><span>{{ page + 1 }} / {{ pageCount }}</span><Button variant="outline" size="sm" :disabled="page + 1 >= pageCount" @click="page++">下一页</Button></div></footer>
    </template>
    <details class="monthly-basis"><summary>数量口径与使用说明</summary><p>净实收＝实收－收料冲销；净发料＝实发－发料冲销－车间退料。冲销归更正发生月份，原月份的收发事实保留。</p><p>合计、汇总、明细和导出使用相同筛选；查找某个单号时，仅合计匹配的凭证。凭证数按实际收发凭证计，同一送货单分批收货会有多笔记录。</p><p>“送货 / 领料单”包含从单据列表或扫码办理的收发；退料沿用原发料来源。原采购入库计入“采购 / 手工登记”。裁床接口领料 · 待接入。</p><p>期初、盘点及调仓不算进货或领料。供应商同名无法唯一识别时按原单名称独立列示。参考价格不代表应付金额，本页未确认或锁定月份。</p><div><RouterLink to="/modules/pmc-warehouse/fabric-warehouse/inventory?factory=huakang-c&view=order-summary">查看包含期初与盘点的收发结余 →</RouterLink></div></details>
    <DialogRoot :open="!!selected" @update:open="value => { if (!value) selected = undefined }"><DialogPortal><DialogOverlay class="monthly-overlay" /><DialogContent class="monthly-dialog"><template v-if="selected"><DialogTitle class="monthly-dialog-title">收发凭证详情</DialogTitle><DialogDescription class="monthly-dialog-description">{{ kindLabel(selected) }} · {{ selected.date }} · 保留原单记录，仅供核对</DialogDescription><dl><div><dt>归属方</dt><dd>{{ selected.party_name || '原单未填写' }}</dd></div><div><dt>原单往来方</dt><dd>{{ selected.recorded_party || '未记录' }}</dd></div><div><dt>物料</dt><dd>{{ selected.item_name }}<small>{{ selected.item_code }}</small></dd></div><div><dt>本笔数量</dt><dd>{{ selected.quantity }} {{ selected.unit }}</dd></div><div><dt>原单号</dt><dd>{{ selected.source_no }}</dd></div><div><dt>库存凭证</dt><dd>{{ selected.id }}</dd></div><div v-if="selected.original_id"><dt>关联原凭证</dt><dd>{{ selected.original_id }}</dd></div><div><dt>登记来源 / 经办人</dt><dd>{{ channelLabel(selected) }} · {{ selected.actor_name || '未记录' }}</dd></div><div><dt>归属依据</dt><dd>{{ selected.identity_basis }}</dd></div><div><dt>原单参考单价 / 计价单位</dt><dd>{{ selected.unit_price || '未记录' }} / {{ selected.price_unit || '未注明' }} · {{ selected.currency || '币种未注明' }}</dd></div><div v-if="selected.amount !== undefined && selected.amount !== ''"><dt>原入库单金额</dt><dd>{{ selected.amount }} {{ selected.currency }}</dd></div><div><dt>价格依据</dt><dd>{{ selected.price_note || '未填写' }}</dd></div></dl><p class="monthly-dialog-description">价格仅保留原单依据，不计算应付金额；冲销数量以本笔负数为准。</p><footer><RouterLink v-if="sourceLink" :to="sourceLink">查看关联交接单 ↗</RouterLink><Button variant="outline" @click="selected = undefined">关闭</Button></footer></template></DialogContent></DialogPortal></DialogRoot>
  </section>
</template>

<style scoped>
.fabric-monthly{color:var(--foreground);font-size:13px}.monthly-heading{display:flex;align-items:center;justify-content:space-between;gap:16px;padding:24px;border-bottom:1px solid var(--border)}h2{font-size:20px;line-height:1.4;font-weight:700}.monthly-heading p{color:var(--muted-foreground);line-height:1.6;margin:6px 0 0}.monthly-actions{display:flex;flex-wrap:wrap;gap:8px;flex-shrink:0}.monthly-actions button{font-size:13px}.monthly-filters{display:flex;align-items:center;gap:12px;flex-wrap:wrap;padding:14px 24px;border-bottom:1px solid var(--border)}.monthly-filters label{display:flex;align-items:center;gap:8px;font-size:12px;color:var(--muted-foreground)}.monthly-filters input,.monthly-filters select{height:36px;max-width:230px;min-width:0;border:1px solid var(--border);border-radius:7px;padding:0 10px;background:var(--muted);color:var(--foreground);font-size:12px}.monthly-context{display:flex;justify-content:space-between;gap:12px;flex-wrap:wrap;padding:12px 24px;background:#f8fafc;color:#64748b;font-size:12px}.monthly-context span:first-child{color:#0f766e}.monthly-totals{display:grid;gap:12px;padding:16px 24px}.monthly-totals article{display:flex;gap:22px;align-items:center;border:1px solid #e2e8f0;border-radius:9px;padding:16px;background:#f8fafc}.monthly-totals article>div{flex:1;border-left:1px solid #e2e8f0;padding-left:22px;min-width:0}.monthly-totals span{color:#64748b;font-size:12px}.monthly-totals strong{display:block;font-size:24px;font-weight:700;color:#0f766e;font-variant-numeric:tabular-nums;overflow-wrap:anywhere}.monthly-totals small{font-size:11px}.monthly-totals .unit-tag{color:#0f766e;font-size:14px;font-weight:600}.monthly-modes{display:flex;gap:8px;align-items:center;flex-wrap:wrap;padding:10px 24px;border-top:1px solid var(--border);border-bottom:1px solid var(--border)}.monthly-modes button{padding:8px 12px;border-radius:6px;color:#64748b;cursor:pointer}.monthly-modes button[aria-pressed=true]{background:#f0fdfa;color:#0f766e;font-weight:600}.monthly-modes button span{font-size:11px;margin-left:5px}.monthly-modes>span{margin-left:auto;font-size:12px;color:#64748b;overflow-wrap:anywhere}.monthly-scroll{overflow:auto}table{width:100%;min-width:800px;border-collapse:collapse;text-align:left}th{background:#f8fafc;color:#64748b;font-size:12px;font-weight:500;white-space:nowrap}th,td{padding:14px 18px;border-bottom:1px solid #edf2f7;vertical-align:top}td{max-width:250px;overflow-wrap:anywhere}td strong{font-weight:600}small{display:block;color:#64748b;margin-top:5px;font-size:12px}.number{text-align:right;font-variant-numeric:tabular-nums;white-space:nowrap}.net{font-weight:700;color:#0f766e}.correction{color:#b45309}.monthly-footer,.monthly-footer>div{display:flex;align-items:center;gap:12px}.monthly-footer{justify-content:space-between;padding:16px 24px;color:#64748b;font-size:12px}.monthly-empty{padding:54px 24px;text-align:center}.monthly-empty strong{font-size:16px}.monthly-empty p{color:#64748b;margin-top:12px}.monthly-basis{padding:14px 24px;border-top:1px solid var(--border);background:#f8fafc;color:#64748b;font-size:12px;line-height:1.8}.monthly-basis summary{cursor:pointer}.monthly-basis p{margin-top:8px}.monthly-basis a{display:inline-block;margin-top:8px;color:#0f766e}.monthly-message{padding:18px 24px;color:#64748b}.error{color:#b91c1c}.monthly-overlay{position:fixed;inset:0;background:#0f172a55;z-index:80}.monthly-dialog{position:fixed;z-index:81;left:50%;top:50%;transform:translate(-50%,-50%);width:min(720px,calc(100vw - 32px));max-height:85vh;overflow:auto;background:white;border:1px solid #e2e8f0;border-radius:12px;padding:24px;color:#0f172a;font-size:13px}.monthly-dialog-title{font-size:20px;font-weight:700}.monthly-dialog-description{font-size:12px;line-height:1.6;color:#64748b;margin:8px 0 16px}.monthly-dialog dl{display:grid;grid-template-columns:1fr 1fr;gap:18px}.monthly-dialog dt{color:#64748b;font-size:12px;margin-bottom:5px}.monthly-dialog dd{overflow-wrap:anywhere}.monthly-dialog footer{display:flex;align-items:center;justify-content:flex-end;gap:20px;padding-top:18px}.monthly-dialog a{color:#0f766e}@media(max-width:760px){.monthly-heading{padding:20px 16px;align-items:flex-start;flex-direction:column}h2{font-size:18px}.monthly-filters,.monthly-context,.monthly-modes,.monthly-footer,.monthly-basis{padding-left:16px;padding-right:16px}.monthly-filters label{flex:1;min-width:calc(50% - 12px);align-items:stretch;flex-direction:column}.monthly-filters input,.monthly-filters select{width:100%;max-width:100%}.monthly-totals{padding:16px}.monthly-totals article{flex-wrap:wrap;gap:12px}.monthly-totals .unit-tag{width:100%}.monthly-totals article>div{min-width:100px;padding-left:12px}.monthly-totals strong{font-size:21px}.monthly-modes>span{width:100%;margin-left:0}.monthly-dialog{padding:20px}.monthly-dialog dl{grid-template-columns:1fr}}
</style>
