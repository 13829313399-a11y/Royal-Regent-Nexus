<script setup lang="ts">
import { computed, inject, onBeforeUnmount, reactive, ref, watch } from 'vue'
import { parseDate } from '@internationalized/date'
import type { DateRange } from 'reka-ui'
import DateRangeFilter from '@/components/DateRangeFilter.vue'
import { RouterLink } from 'vue-router'
import { DialogRoot, DialogPortal, DialogOverlay, DialogContent, DialogTitle, DialogDescription } from 'reka-ui'
import { warehouseOperationsApi as api, type WarehouseDocument, type WarehouseOperationsWorkspace } from '@/api/warehouseOperations'
import { useAuthStore } from '@/stores/auth'
import { getApiErrorMessage } from '@/lib/http'
import Button from '@/components/ui/button/Button.vue'
import { activitySearchKey } from './inventorySearch'
import { activityLabel, activitySummary, filterActivity, operationTime, type ActivityFilters } from './activityLog'
import { operationLabels } from './operations'

const auth = useAuthStore(), headerSearch = inject(activitySearchKey, undefined)
const data = ref<WarehouseOperationsWorkspace>(), loading = ref(false), error = ref(''), selected = ref<WarehouseDocument>()
const page = ref(0), pageSize = 50
const filters = reactive<Omit<ActivityFilters, 'search'>>({ from: '', to: '', kind: '', actor: '', state: '', dateField: 'OPERATION', sort: 'DESC' })
const dates = computed<DateRange>({
  get: () => ({ start: filters.from ? parseDate(filters.from) : undefined, end: filters.to ? parseDate(filters.to) : undefined }),
  set: value => { filters.from = value.start?.toString() ?? ''; filters.to = value.end?.toString() ?? '' },
})
const query = computed(() => headerSearch?.search.value ?? '')
const rows = computed(() => [...new Map([...(data.value?.documents ?? []), ...(data.value?.original_receipts ?? [])].map(row => [row.id, row])).values()])
const kinds = computed(() => [...new Set(rows.value.map(row => row.kind))])
const actors = computed(() => [...new Set(rows.value.map(row => row.actor_name).filter(Boolean))].sort((a,b) => a.localeCompare(b, 'zh-CN')))
const filtered = computed(() => filterActivity(rows.value, { ...filters, search: query.value }))
const pageCount = computed(() => Math.max(1, Math.ceil(filtered.value.length / pageSize)))
const visible = computed(() => filtered.value.slice(page.value * pageSize, (page.value + 1) * pageSize))
const invalidDates = computed(() => !!filters.from && !!filters.to && filters.from > filters.to)
const hasFilters = computed(() => !!(query.value || filters.from || filters.to || filters.kind || filters.actor || filters.state || filters.sort !== 'DESC' || filters.dateField !== 'OPERATION'))
const related = computed(() => rows.value.find(row => row.id === (selected.value?.data.original_id || selected.value?.data.batch_id)))
const businessLink = computed(() => {
  if (!selected.value) return ''
  const row = selected.value
  if (row.read_only || row.data.original_id?.startsWith('FR-')) return '/modules/pmc-warehouse/fabric-warehouse/receipts?factory=huakang-c&view=history'
  const kind = row.kind === 'CORRECTION' ? row.data.reversed_kind : row.kind
  const view = kind === 'OPENING' ? 'opening' : kind === 'STOCKTAKE' ? 'stocktake' : kind === 'REQUEST' ? 'pending-issues' : 'movements'
  return `/modules/pmc-warehouse/fabric-warehouse/inventory?factory=huakang-c&view=${view}`
})
const material = (row:WarehouseDocument) => row.data.item_name || row.batch_snapshot?.item_name || '未记录物料名称'
function reset() {
  if (headerSearch) headerSearch.search.value = ''
  Object.assign(filters, { from:'', to:'', kind:'', actor:'', state:'', dateField:'OPERATION', sort:'DESC' })
}
watch([query, () => ({...filters})], () => { page.value = 0 })
let sequence = 0
async function load() {
  const ticket = ++sequence
  loading.value = true; error.value = ''; selected.value = undefined
  try { const response = await api.workspace('fabric'); if (ticket === sequence) { data.value = response; page.value = Math.min(page.value, pageCount.value - 1) } }
  catch (e) { if (ticket === sequence) { data.value = undefined; error.value = getApiErrorMessage(e) } }
  finally { if (ticket === sequence) loading.value = false }
}
watch([() => auth.currentUser?.id, () => auth.authorizationVersion], (_, previous) => { data.value = undefined; selected.value = undefined; page.value = 0; if (previous.length) reset(); void load() }, { immediate:true })
onBeforeUnmount(() => { sequence++ })
</script>

<template>
  <div class="fabric-activity-log">
    <header class="activity-heading"><div><h2>操作日志</h2><p>按操作时间追溯已登记业务，查看经办人、原单和办理依据。</p></div><Button variant="outline" :disabled="loading" @click="load">刷新</Button></header>
    <div class="activity-filters">
      <label>日期口径<select v-model="filters.dateField" aria-label="日志日期口径"><option value="OPERATION">操作时间</option><option value="BUSINESS">业务日期</option></select></label>
      <div class="flex items-center gap-2 whitespace-nowrap text-xs"><span>日期范围</span><DateRangeFilter v-model="dates" label="日志日期范围" /></div>
      <label>业务类型<select v-model="filters.kind" aria-label="日志业务类型"><option value="">全部类型</option><option v-for="kind in kinds" :key="kind" :value="kind">{{operationLabels[kind]}}</option></select></label>
      <label>经办人<select v-model="filters.actor" aria-label="日志经办人"><option value="">全部经办人</option><option v-for="actor in actors" :key="actor">{{actor}}</option></select></label>
      <label>记录状态<select v-model="filters.state" aria-label="日志记录状态"><option value="">全部状态</option><option value="ACTIVE">未冲销</option><option value="REVERSED">原单已冲销</option></select></label>
      <label>排序<select v-model="filters.sort" aria-label="日志排序"><option value="DESC">{{filters.dateField==='OPERATION'?'最新操作在前':'业务日期最新在前'}}</option><option value="ASC">{{filters.dateField==='OPERATION'?'最早操作在前':'业务日期最早在前'}}</option></select></label>
      <Button variant="ghost" :disabled="!hasFilters" @click="reset">重置筛选</Button>
    </div>
    <p v-if="invalidDates" class="activity-error" role="alert">开始日期不能晚于结束日期，请调整后查看。</p>
    <p v-if="error" class="activity-error" role="alert">{{error}}</p><p v-if="loading" class="activity-note" role="status">正在读取操作日志…</p>
    <template v-if="data">
      <div class="activity-count"><span>共 {{filtered.length}} 条记录<span v-if="hasFilters"> · 已筛选</span></span><span>时间按北京时间显示</span></div>
      <div class="activity-table" role="region" aria-label="布料仓操作日志" tabindex="0"><table><thead><tr><th>操作时间 / 业务日期</th><th>经办人</th><th>业务 / 状态</th><th>物料 / 来源凭证</th><th>操作内容 / 原因</th><th>操作</th></tr></thead><tbody><tr v-for="row in visible" :key="row.id">
        <td><strong>{{operationTime(row.occurred_at) || '未记录操作时间'}}</strong><small>业务日期 {{row.business_date}}</small></td><td>{{row.actor_name || '未记录'}}</td>
        <td><strong>{{activityLabel(row)}}</strong><small class="activity-status" :class="{reversed:row.reversed}">{{row.reversed?'原单已冲销':row.kind==='CORRECTION'?'已完成冲销':'已登记'}}</small></td>
        <td><strong>{{material(row)}}</strong><small>{{row.data.item_code || row.batch_snapshot?.item_code}}</small><small>{{row.data.source_no || '未另填外部凭证'}}</small></td>
        <td class="activity-summary">{{activitySummary(row)}}<small v-if="row.data.reason">{{row.data.reason}}</small></td><td><Button size="sm" variant="outline" @click="selected=row">详情</Button></td>
      </tr></tbody></table></div>
      <div v-if="!filtered.length && !loading" class="activity-empty"><strong>{{hasFilters?'没有符合条件的记录':'暂无操作日志'}}</strong><p>{{hasFilters?'调整条件或重置筛选后再查看。':'办理收发、仓位核实、期初或盘点入账后会显示在这里。'}}</p><Button v-if="hasFilters" variant="outline" @click="reset">清空筛选</Button></div>
      <footer class="activity-footer"><span>共 {{filtered.length}} 条<span v-if="filtered.length"> · 显示 {{page*pageSize+1}}–{{Math.min((page+1)*pageSize,filtered.length)}}</span></span><div><Button size="sm" variant="outline" :disabled="loading||page===0" @click="page--">上一页</Button><span>{{page+1}} / {{pageCount}}</span><Button size="sm" variant="outline" :disabled="loading||page+1>=pageCount" @click="page++">下一页</Button></div></footer>
    </template>
    <details class="activity-scope"><summary>记录范围与查看方式</summary><p>本页汇总已登记收发、仓位核实、历史质检、期初和盘点入账；采购实收按批次列示。业务日期是单据所属日期，操作时间是实际登记时间。</p><p>只提供查询和追溯。更正从原业务页面办理；采购导入及撤销、基础资料修改、盘点草稿保存与取消，请到对应页面查看记录。</p></details>
    <DialogRoot :open="!!selected" @update:open="open=>{if(!open)selected=undefined}"><DialogPortal><DialogOverlay class="activity-overlay"/><DialogContent v-if="selected" class="activity-dialog"><header><div><DialogTitle>操作详情 · {{activityLabel(selected)}}</DialogTitle><DialogDescription>查看记录和原单依据，历史内容保留。</DialogDescription></div><Button variant="outline" @click="selected=undefined">关闭</Button></header>
      <div class="activity-detail"><dl><div><dt>操作时间</dt><dd>{{operationTime(selected.occurred_at)||'未记录'}}</dd></div><div><dt>业务日期</dt><dd>{{selected.business_date}}</dd></div><div><dt>经办人</dt><dd>{{selected.actor_name||'未记录'}}</dd></div><div><dt>当前记录状态</dt><dd>{{selected.reversed?'原单已冲销，原记录保留':'记录保留'}}</dd></div><div class="wide"><dt>记录编号</dt><dd>{{selected.id}}</dd></div><div class="wide"><dt>物料</dt><dd>{{material(selected)}} · {{selected.data.item_code||selected.batch_snapshot?.item_code}}</dd></div><div class="wide"><dt>操作内容</dt><dd>{{activitySummary(selected)}}</dd></div><div><dt>来源凭证 / 行号</dt><dd>{{selected.data.source_no||'未另填外部凭证'}} / {{selected.data.source_line||'—'}}</dd></div><div><dt>原单 / 原批次</dt><dd>{{selected.data.original_id||selected.data.batch_id||'—'}}</dd></div><div><dt>往来单位 / 领用方</dt><dd>{{selected.data.counterparty||'—'}}</dd></div><div><dt>缸号 / 卷号</dt><dd>{{selected.data.lot||selected.batch_snapshot?.lot||'—'}} / {{selected.data.roll_no||selected.batch_snapshot?.roll_no||'—'}}</dd></div><div class="wide"><dt>原因 / 依据</dt><dd>{{selected.data.reason||'未另填原因'}}</dd></div></dl></div>
      <footer><Button v-if="related" variant="outline" @click="selected=related">查看关联原单</Button><RouterLink :to="businessLink" @click="selected=undefined">前往原业务页面 ↗</RouterLink></footer>
    </DialogContent></DialogPortal></DialogRoot>
  </div>
</template>

<style scoped>
.fabric-activity-log{color:#0f172a;background:#fff;font-size:13px}.activity-heading{display:flex;align-items:center;justify-content:space-between;gap:16px;padding:24px;border-bottom:1px solid #e2e8f0}.activity-heading h2{font-size:20px;font-weight:700;line-height:1.4}.activity-heading p{font-size:13px;color:#64748b;margin-top:6px}.activity-heading button{font-size:13px}.activity-filters{display:flex;flex-wrap:wrap;align-items:center;gap:12px 16px;padding:14px 24px;border-bottom:1px solid #e2e8f0}.activity-filters label{display:flex;align-items:center;gap:8px;font-size:12px;white-space:nowrap}.activity-filters input,.activity-filters select{font:inherit;min-height:36px;min-width:0;max-width:180px;border:1px solid #e2e8f0;border-radius:7px;padding:7px 10px;background:#f8fafc;color:#334155}.activity-filters input:focus,.activity-filters select:focus{outline:2px solid #99f6e4;outline-offset:1px}.activity-count,.activity-footer{display:flex;flex-wrap:wrap;justify-content:space-between;align-items:center;gap:12px;padding:14px 24px;font-size:12px;color:#64748b}.activity-footer{border-top:1px solid #e2e8f0}.activity-footer>div{display:flex;align-items:center;gap:12px}.activity-table{overflow:auto}.activity-table table{width:100%;border-collapse:collapse;text-align:left}.activity-table th{font-size:12px;font-weight:500;color:#64748b;background:#f8fafc;padding:12px 20px;white-space:nowrap}.activity-table td{vertical-align:top;padding:16px 20px;border-top:1px solid #edf2f7;min-width:100px}.activity-table strong{font-size:13px;font-weight:600}.activity-table td:first-child{white-space:nowrap;font-variant-numeric:tabular-nums}.activity-table small{display:block;color:#64748b;font-size:12px;margin-top:5px;overflow-wrap:anywhere}.activity-summary{min-width:210px!important;max-width:340px;white-space:pre-wrap;overflow-wrap:anywhere}.activity-table .activity-status{display:inline-block;padding:2px 6px;border-radius:5px;background:#f0fdfa;color:#0f766e}.activity-table .reversed{background:#fff7ed;color:#9a3412}.activity-error{padding:12px 24px;background:#fff1f2;color:#b91c1c}.activity-note{padding:12px 24px;color:#64748b}.activity-empty{text-align:center;padding:48px 24px}.activity-empty p{margin:10px 0 16px;color:#64748b}.activity-scope{padding:14px 24px;border-top:1px solid #e2e8f0;color:#64748b;font-size:12px;background:#f8fafc}.activity-scope summary{cursor:pointer}.activity-scope p{margin-top:8px;line-height:1.8}.activity-overlay{position:fixed;inset:0;background:#0f172a66;z-index:90}.activity-dialog{position:fixed;top:50%;left:50%;transform:translate(-50%,-50%);z-index:91;width:min(840px,calc(100% - 32px));max-height:90dvh;display:flex;flex-direction:column;background:white;border:1px solid #e2e8f0;border-radius:12px;color:#0f172a;font:inherit;box-shadow:0 20px 60px #0003}.activity-dialog header,.activity-dialog footer{display:flex;justify-content:space-between;align-items:center;gap:16px;padding:20px 24px;border-bottom:1px solid #e2e8f0}.activity-dialog header h2{font-size:18px;font-weight:700}.activity-dialog header p{font-size:13px;color:#64748b;margin-top:6px}.activity-dialog footer{border-bottom:0;border-top:1px solid #e2e8f0;justify-content:flex-end;font-size:13px}.activity-dialog a{color:#0f766e}.activity-detail{padding:24px;overflow:auto}.activity-detail dl{display:grid;grid-template-columns:1fr 1fr;gap:20px}.activity-detail dt{font-size:12px;color:#64748b;margin-bottom:6px}.activity-detail dd{font-size:13px;white-space:pre-wrap;overflow-wrap:anywhere}.wide{grid-column:1/-1}@media(max-width:760px){.activity-heading,.activity-filters,.activity-count,.activity-footer,.activity-scope{padding:16px}.activity-heading h2{font-size:18px}.activity-filters label{flex:1;min-width:220px;justify-content:space-between}.activity-filters input,.activity-filters select{flex:1;max-width:180px}.activity-detail dl{grid-template-columns:1fr}.activity-table td,.activity-table th{padding:12px 16px}}
</style>
