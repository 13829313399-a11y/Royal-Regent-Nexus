<script setup lang="ts">
import { computed, inject, onBeforeUnmount, ref, watch } from 'vue'
import { parseDate } from '@internationalized/date'
import type { DateRange } from 'reka-ui'
import DateRangeFilter from '@/components/DateRangeFilter.vue'
import { onBeforeRouteLeave, onBeforeRouteUpdate } from 'vue-router'
import { isAxiosError } from 'axios'
import { Download, Upload, ClipboardCheck, RefreshCw } from '@lucide/vue'
import { fabricInventorySetupApi as api, type OpeningPreview, type OpeningRecord, type CountDocument, type CountAction, type SetupWorkspace } from '@/api/fabricInventorySetup'
import { warehouseOperationsApi, type WarehouseOperationsWorkspace } from '@/api/warehouseOperations'
import { useAuthStore } from '@/stores/auth'
import { getApiErrorMessage } from '@/lib/http'
import { warehouseRequestId } from './requestIdentity'
import { inventorySearchKey } from './inventorySearch'
import { remaining } from './operations'

const props = defineProps<{ mode: 'opening' | 'stocktake' }>()
const auth = useAuthStore()
const header = inject(inventorySearchKey, undefined)
const query = computed(() => header?.search.value.trim().toLocaleLowerCase() ?? '')
const data = ref<SetupWorkspace>(), stock = ref<WarehouseOperationsWorkspace>()
const loading = ref(false), busy = ref(false), error = ref(''), success = ref(''), frozen = ref(false)
const today = () => new Intl.DateTimeFormat('sv-SE', {timeZone:'Asia/Shanghai'}).format(new Date())
const cutoff = ref(today()), sourceNo = ref(''), file = ref<File>(), preview = ref<OpeningPreview>(), acknowledged = ref(false)
const openedImport = ref<OpeningRecord>(), doc = ref<CountDocument>(), initialDoc = ref(''), remoteDoc = ref<CountDocument>()
const countDate = ref(today()), postingConfirmed = ref(false), actionReason = ref(''), createReason = ref('日常库存盘点')
const warehouse = ref(''), location = ref(''), showZero = ref(false), selected = ref<string[]>([]), page = ref(0), historyStatus = ref('')
const historyFrom = ref(''), historyTo = ref('')
const historyDates = computed<DateRange>({
  get: () => ({ start: historyFrom.value ? parseDate(historyFrom.value) : undefined, end: historyTo.value ? parseDate(historyTo.value) : undefined }),
  set: value => { historyFrom.value = value.start?.toString() ?? ''; historyTo.value = value.end?.toString() ?? '' },
})
let generation = 0
let retry: (() => Promise<void>) | undefined
const canOperate = computed(() => !!data.value?.permissions.operate)
const canPost = computed(() => !!data.value?.permissions.correct)
const editable = computed(() => !!doc.value && doc.value.status === 'DRAFT' && canOperate.value && !busy.value && !frozen.value && !loading.value && !remoteDoc.value)
const canConfirmCount = computed(() => !!doc.value && doc.value.status === 'DRAFT' && !doc.value.stale && canPost.value && !busy.value && !frozen.value && !loading.value && !remoteDoc.value)
const dirty = computed(() => !!doc.value && doc.value.status === 'DRAFT' && JSON.stringify(doc.value.lines) !== initialDoc.value)
const warehouses = computed(() => [...new Set(stock.value?.locations?.map(row=>row.warehouse) ?? [])])
const locations = computed(() => stock.value?.locations?.filter(row=>!warehouse.value || row.warehouse===warehouse.value) ?? [])
const matches = (row:unknown) => JSON.stringify(row).toLocaleLowerCase().includes(query.value)
const available = computed(() => (stock.value?.stock ?? []).filter(row=>row.location_verified && (showZero.value || Number(row.quantity)>0) && (!warehouse.value || row.warehouse_name===warehouse.value) && (!location.value || row.location_id===location.value) && matches(row)))
const visible = computed(() => available.value.slice(page.value*50,page.value*50+50))
const allVisible = computed(() => !!visible.value.length && visible.value.every(row=>selected.value.includes(row.id)))
const history = computed(() => (data.value?.counts ?? []).filter(row=>(!historyStatus.value || row.status===historyStatus.value) && (!historyFrom.value || row.business_date>=historyFrom.value) && (!historyTo.value || row.business_date<=historyTo.value) && matches(row)))
const imports = computed(() => (data.value?.openings ?? []).filter(matches))
const stateNames = {DRAFT:'待盘点',POSTED:'已入账',CANCELLED:'已取消'}
const actionNames: Record<string,string> = {CREATE:'生成盘点单',SAVE:'保存实盘',REFRESH:'更新账面、清空实盘',POST:'确认入账',CANCEL:'取消盘点'}
const difference = (actual:string,book:string) => /^\d+(\.\d{1,6})?$/.test(actual) ? remaining(actual,book) : '未盘点'
function accept(result:CountDocument) { doc.value=JSON.parse(JSON.stringify(result)); remoteDoc.value=undefined; initialDoc.value=JSON.stringify(result.lines); postingConfirmed.value=false; actionReason.value=''; countDate.value=today() }
function openLatest() {
  if (!remoteDoc.value || busy.value || frozen.value || loading.value) return
  if (dirty.value && !window.confirm('打开最新盘点单会丢弃本页未保存的实盘填写，请先记录需要保留的内容。确定打开吗？')) return
  accept(remoteDoc.value); error.value=''; success.value='已打开最新盘点单，请按最新账面重新核对。'
}
function changed() { postingConfirmed.value=false }
function leave() {
  if (busy.value || frozen.value) { error.value='本次操作结果尚未确认，请先使用原请求重试。'; return false }
  return !dirty.value || window.confirm('实盘数量尚未保存，确定离开并丢弃本次填写吗？')
}
onBeforeRouteLeave(leave); onBeforeRouteUpdate(leave)
function beforeUnload(event:BeforeUnloadEvent) { if(dirty.value||busy.value||frozen.value) {event.preventDefault();event.returnValue=''} }
window.addEventListener('beforeunload',beforeUnload)
onBeforeUnmount(()=>{generation++;window.removeEventListener('beforeunload',beforeUnload)})
async function load(clearError=true) {
  const ticket=++generation
  loading.value=true;if(clearError)error.value=''
  try {
    const [records,batches]=await Promise.all([api.workspace(),warehouseOperationsApi.workspace('fabric')])
    if(ticket!==generation)return
    data.value=records;stock.value=batches
    const current = records.counts.find(row => row.id === doc.value?.id)
    if (current && doc.value) {
      if (current.revision > doc.value.revision) {
        postingConfirmed.value=false
        if (dirty.value || frozen.value) remoteDoc.value=current
        else accept(current)
      } else if (current.revision === doc.value.revision) {
        doc.value.stale=current.stale; doc.value.changed_batch_ids=current.changed_batch_ids; doc.value.legacy_scope=current.legacy_scope
        if(current.stale)postingConfirmed.value=false
      }
    }
    selected.value=selected.value.filter(id=>batches.stock.some(row=>row.id===id))
  } catch(e) {if(ticket===generation){data.value=undefined;stock.value=undefined;error.value=getApiErrorMessage(e)}}
  finally {if(ticket===generation)loading.value=false}
}
watch(()=>auth.currentUser?.id,()=>{generation++;doc.value=undefined;remoteDoc.value=undefined;preview.value=undefined;data.value=undefined;stock.value=undefined;selected.value=[];frozen.value=false;retry=undefined;void load()},{immediate:true})
watch(()=>auth.authorizationVersion,()=>{
  preview.value=undefined;acknowledged.value=false;postingConfirmed.value=false;data.value=undefined;stock.value=undefined
  if(retry)frozen.value=true
  void load()
})
watch([warehouse,location,showZero,query],()=>{page.value=0;selected.value=[]})
watch(warehouse,()=>{location.value=''})
watch([cutoff,sourceNo,file],()=>{preview.value=undefined;acknowledged.value=false;openedImport.value=undefined})
function chooseFile(event:Event) {file.value=(event.target as HTMLInputElement).files?.[0];error.value='';success.value=''}
function form() {const body=new FormData();body.set('factory_id','huakang-c');body.set('cutoff',cutoff.value);body.set('source_no',sourceNo.value.trim());if(file.value)body.set('file',file.value);return body}
async function download() {
  busy.value=true;error.value=''
  try {const blob=await api.template();const url=URL.createObjectURL(blob);const a=document.createElement('a');a.href=url;a.download='布料仓期初库存模板.xlsx';a.click();setTimeout(()=>URL.revokeObjectURL(url),1000)}
  catch(e){error.value=getApiErrorMessage(e)}finally{busy.value=false}
}
async function inspectFile() {
  if(!file.value||!sourceNo.value.trim()||!cutoff.value)return
  const ticket=generation;busy.value=true;error.value='';preview.value=undefined;acknowledged.value=false
  try {const result=await api.preview(form());if(ticket===generation)preview.value=result}
  catch(e){if(ticket===generation)error.value=getApiErrorMessage(e)}finally{busy.value=false}
}
async function mutate<T>(operation:()=>Promise<T>, completed:(result:T)=>void) {
  if(busy.value)return
  const ticket=generation;busy.value=true;error.value='';retry=()=>mutate(operation,completed)
  try {const result=await operation();if(ticket!==generation)return;frozen.value=false;retry=undefined;completed(result);void load()}
  catch(e){if(ticket!==generation)return;const status=isAxiosError(e)?e.response?.status:undefined
    if(status===undefined||status===408||status>=500){frozen.value=true;retry=()=>mutate(operation,completed);error.value='结果尚未确认，已锁定原内容。请使用原请求重试，避免重复入账。'}
    else{frozen.value=false;retry=undefined;error.value=getApiErrorMessage(e);if(status===409){preview.value=undefined;acknowledged.value=false;postingConfirmed.value=false;if(doc.value)await load(false)}if(status===403||status===401){doc.value=undefined;remoteDoc.value=undefined;data.value=undefined;stock.value=undefined}}
  }finally{busy.value=false}
}
function applyOpening() {
  if(!preview.value||preview.value.error_count||!acknowledged.value||!canPost.value)return
  const body=form();body.set('token',preview.value.token);body.set('request_id',warehouseRequestId());body.set('confirmed','true')
  void mutate(()=>api.apply(body),result=>{success.value=`期初导入完成：入账 ${result.posted_count} 行，重复跳过 ${result.skipped_count} 行。`;preview.value=undefined;file.value=undefined;openedImport.value=result;acknowledged.value=false})
}
function selectVisible(checked:boolean) {selected.value=checked?[...new Set([...selected.value,...visible.value.map(row=>row.id)])]:selected.value.filter(id=>!visible.value.some(row=>row.id===id))}
function createCount() {
  if(!selected.value.length||!createReason.value.trim()||!canOperate.value)return
  const body={factory_id:'huakang-c' as const,request_id:warehouseRequestId(),batch_ids:[...selected.value],reason:createReason.value.trim()}
  void mutate(()=>api.create(body),result=>{accept(result);success.value='已生成盘点单。逐批填写实盘，未清点的批次请留空。';selected.value=[]})
}
function act(action:CountAction['action']) {
  if(!doc.value || remoteDoc.value || loading.value || (action==='POST' ? (!canConfirmCount.value||!postingConfirmed.value) : !editable.value))return
  if(action==='REFRESH'&&!window.confirm('更新账面会清空已填实盘数量，需要重新清点。确定更新吗？'))return
  if(action==='POST'&&!window.confirm('确认实盘数量、截止日期及差异原因无误并入账？原始收发记录将保留。'))return
  const identifier=doc.value.id
  const body:CountAction={factory_id:'huakang-c',request_id:warehouseRequestId(),expected_revision:doc.value.revision,action,business_date:countDate.value,confirmed:action==='POST'&&postingConfirmed.value,reason:actionReason.value,lines:doc.value.lines.map(line=>({batch_id:line.batch_id,actual:line.actual.trim(),reason:line.reason.trim()}))}
  void mutate(()=>api.act(identifier,body),result=>{accept(result);success.value=action==='POST'?'盘点已入账，库存按差额调整，原流水保留。':action==='REFRESH'?'账面已更新，请重新清点并填写实盘。':action==='CANCEL'?'盘点单已取消，未改变库存。':'实盘草稿已保存。'})
}
function openCount(record:CountDocument){if(leave()){accept(record);error.value='';success.value=''}}
function closeCount(){if(leave())doc.value=undefined}
</script>

<template>
  <div class="inventory-setup">
    <header class="setup-heading"><div><h2>{{ mode==='opening'?'期初库存':'库存盘点' }}</h2><p>{{ mode==='opening'?'导入尚未登记的历史实物结余，先预览核对，再确认入账。':'按仓位和批次清点实物，保存实盘数量，核对差异后入账。' }}</p></div><div class="setup-actions"><button v-if="mode==='opening'" :disabled="busy||frozen||loading" @click="download"><Download :size="16"/>下载期初模板</button><button :disabled="busy||frozen||loading" @click="load()"><RefreshCw :size="15"/>刷新</button></div></header>
    <p v-if="error" class="setup-error" role="alert">{{ error }}</p><p v-if="success" class="setup-success" role="status">{{ success }}</p>
    <div v-if="frozen" class="setup-warning"><button :disabled="busy" @click="retry?.()">{{busy?'正在核对…':'用原请求重试'}}</button><span>确认结果前不能更换文件、修改内容或离开。</span></div>
    <p v-if="loading&&!data" class="setup-empty">正在加载库存资料…</p>
    <template v-if="data&&mode==='opening'">
      <ol class="setup-steps"><li>1 下载并填写模板</li><li>2 预览检查</li><li>3 确认期初入账</li></ol>
      <fieldset class="setup-filters" :disabled="busy||frozen||!canPost"><label>库存截止日<input v-model="cutoff" type="date" :max="today()" aria-label="库存截止日"/></label><label>原始清单编号<input v-model="sourceNo" maxlength="128" placeholder="例如：上线盘点-01" aria-label="原始清单编号"/></label><label class="setup-file">期初库存文件<input type="file" accept=".xlsx" aria-label="期初库存文件" @change="chooseFile"/></label><button class="primary" :disabled="!file||!cutoff||!sourceNo.trim()" @click="inspectFile"><Upload :size="16"/>预览导入</button></fieldset>
      <p class="setup-note">只导入未在本系统记过的历史结余。已入库实物用盘点核对，不能重复补为期初；不会增加采购实收或供应商本期进货。每次最多 1000 行。</p>
      <p v-if="!canPost" class="setup-note">当前账号可查看记录和下载模板；确认期初入账需要布料仓库存更正权限。</p>
      <section v-if="preview" class="setup-preview"><div class="setup-summary"><strong>待入账 {{preview.new_count}} 行</strong><span>重复跳过 {{preview.skip_count}} 行</span><span :class="{'error-text':preview.error_count}">待修正 {{preview.error_count}} 行</span><span v-for="(value,unit) in preview.totals" :key="unit">{{value}} {{unit}}</span></div>
        <div class="setup-table"><table><thead><tr><th>行 / 来源编号</th><th>物料</th><th>货号 / 客户 / 物料明细</th><th>仓位 / 缸号 / 卷号</th><th>期初数量</th><th>检查结果</th></tr></thead><tbody><tr v-for="row in preview.rows" :key="row.row_number"><td>{{row.row_number}} / {{row.source_line}}</td><td><strong>{{row.item_name}}</strong><small>{{row.item_code}}</small></td><td>{{row.style_no || '未记录'}}<small>{{row.customer_name || '未记录'}}</small><small>{{row.material_detail || '未记录'}}</small></td><td>{{row.location||`${row.warehouse} / ${row.location_code}`}}<small>{{row.lot||'—'}} / {{row.roll_no||'—'}}</small></td><td>{{row.quantity}} {{row.unit}}</td><td :class="{'error-text':row.action==='ERROR'}">{{row.action==='NEW'?'可入账':row.action==='SKIP'?'已导入，将跳过':row.errors.join('；')}}</td></tr></tbody></table></div>
        <div class="setup-footer"><label><input v-model="acknowledged" type="checkbox" :disabled="busy||frozen||!!preview.error_count"/>已核对截止日、仓位与实物，本清单不含已登记的库存</label><button class="primary" :disabled="busy||frozen||!acknowledged||!!preview.error_count||!preview.new_count" @click="applyOpening">确认导入期初库存</button></div>
      </section>
      <section class="setup-history"><h3>期初导入记录 <span>{{imports.length}} 笔</span></h3><p v-if="!imports.length" class="setup-empty">暂无期初导入记录</p><div v-else class="setup-table"><table><thead><tr><th>截止日 / 清单</th><th>原文件</th><th>入账 / 跳过</th><th>经办人</th><th>操作</th></tr></thead><tbody><tr v-for="row in imports" :key="row.id"><td>{{row.business_date}}<small>{{row.source_no}}</small></td><td>{{row.filename}}</td><td>{{row.posted_count}} / {{row.skipped_count}}</td><td>{{row.actor_name}}</td><td><button :disabled="busy||frozen" @click="openedImport=openedImport?.id===row.id?undefined:row">{{openedImport?.id===row.id?'收起':'详情'}}</button></td></tr></tbody></table></div>
        <div v-if="openedImport" class="setup-table setup-details"><h4>{{openedImport.source_no}} · 原始导入明细</h4><table><thead><tr><th>来源行</th><th>物料</th><th>货号 / 客户 / 物料明细</th><th>仓位 / 缸号 / 卷号</th><th>数量</th><th>结果</th></tr></thead><tbody><tr v-for="row in openedImport.rows" :key="row.source_line"><td>{{row.source_line}}</td><td>{{row.item_name}}<small>{{row.item_code}}</small></td><td>{{row.style_no || '未记录'}}<small>{{row.customer_name || '未记录'}}</small><small>{{row.material_detail || '未记录'}}</small></td><td>{{row.location}}<small>{{row.lot}} / {{row.roll_no}}</small></td><td>{{row.quantity}} {{row.unit}}</td><td>{{row.action==='NEW'?'已入账':'重复跳过'}}</td></tr></tbody></table><p class="setup-note">期初记录保留原始依据；数量有误请生成盘点单核对并按差额调整。</p></div>
      </section>
    </template>
    <template v-if="data&&mode==='stocktake'">
      <template v-if="!doc"><div class="setup-filters"><label>仓库<select v-model="warehouse" aria-label="盘点仓库"><option value="">全部仓库</option><option v-for="name in warehouses" :key="name">{{name}}</option></select></label><label>仓位<select v-model="location" aria-label="盘点仓位"><option value="">全部仓位</option><option v-for="place in locations" :key="place.id" :value="place.id">{{place.label}}</option></select></label><label><input v-model="showZero" type="checkbox"/>包含零库存批次</label><span>查找物料请使用顶部搜索</span></div>
        <div class="setup-selection"><span>已选 {{selected.length}} 个批次</span><label>盘点说明<input v-model="createReason" maxlength="1000" aria-label="盘点说明"/></label><button class="primary" :disabled="busy||frozen||loading||!canOperate||!selected.length||selected.length>500||!createReason.trim()" @click="createCount"><ClipboardCheck :size="16"/>生成盘点单</button></div>
        <p class="setup-note">每次最多 500 个批次。先选择仓位，再勾选本页全部或指定批次；筛选变化会清空选择。生成盘点单不会冻结日常收发，所选批次有变动时须更新账面并重盘，其他批次收发不影响本单。</p>
        <div class="setup-table"><table><thead><tr><th><input type="checkbox" :checked="allVisible" :disabled="busy||frozen||!canOperate" aria-label="选择本页全部批次" @change="selectVisible(($event.target as HTMLInputElement).checked)"/></th><th>物料</th><th>货号 / 客户 / 物料明细</th><th>仓库 / 仓位</th><th>缸号 / 卷号</th><th>账面数量</th></tr></thead><tbody><tr v-for="row in visible" :key="row.id"><td><input v-model="selected" type="checkbox" :value="row.id" :disabled="busy||frozen||!canOperate" :aria-label="`选择 ${row.item_name} ${row.lot} ${row.roll_no}`"/></td><td><strong>{{row.item_name}}</strong><small>{{row.item_code}}</small></td><td>{{row.style_no || '未记录'}}<small>{{row.customer_name || '未记录'}}</small><small>{{row.material_detail || '未记录'}}</small></td><td>{{row.location_label||row.location}}</td><td>{{row.lot||'—'}} / {{row.roll_no||'—'}}</td><td><strong>{{row.quantity}}</strong> {{row.unit}}</td></tr></tbody></table><p v-if="!visible.length" class="setup-empty">暂无符合条件的批次。历史实物尚未建账时，请先导入期初库存。</p></div>
        <div class="setup-footer"><span>共 {{available.length}} 个批次</span><div class="setup-actions"><button :disabled="page===0" @click="page--">上一页</button><span>{{page+1}} / {{Math.max(1,Math.ceil(available.length/50))}}</span><button :disabled="(page+1)*50>=available.length" @click="page++">下一页</button></div></div>
        <section class="setup-history"><h3>盘点记录</h3><div class="setup-filters"><label>状态<select v-model="historyStatus"><option value="">全部状态</option><option value="DRAFT">待盘点</option><option value="POSTED">已入账</option><option value="CANCELLED">已取消</option></select></label><div class="flex items-center gap-2 whitespace-nowrap text-xs"><span>盘点日期</span><DateRangeFilter v-model="historyDates" label="盘点记录日期范围" /></div><span>最新在前</span></div><div class="setup-table"><table><thead><tr><th>日期 / 盘点单</th><th>范围</th><th>状态</th><th>创建人</th><th>操作</th></tr></thead><tbody><tr v-for="row in history" :key="row.id"><td>{{row.business_date}}<small>{{row.id}}</small></td><td>{{row.lines.length}} 个批次<small>{{row.reason}}</small></td><td>{{stateNames[row.status]}}<small v-if="row.stale" class="error-text">账面有变动</small></td><td>{{row.actor_name}}</td><td><button :disabled="busy||frozen" @click="openCount(row)">{{row.status==='DRAFT'?'继续盘点':'查看详情'}}</button></td></tr></tbody></table><p v-if="!history.length" class="setup-empty">暂无符合条件的盘点记录</p></div></section>
      </template>
      <section v-else class="setup-count"><div class="setup-count-heading"><div><h3>{{stateNames[doc.status]}} · {{doc.lines.length}} 个批次</h3><p>{{doc.id}} · {{doc.business_date}} · {{doc.actor_name}}</p><p>{{doc.reason}}</p></div><button :disabled="busy||frozen" @click="closeCount">返回盘点列表</button></div><p v-if="doc.stale" class="setup-warning">{{ doc.legacy_scope ? '此旧盘点单沿用整仓校验，库存已有变动；更新账面后将改为所选批次校验。' : `所选范围内 ${doc.changed_batch_ids?.length || 0} 个批次的记录已变化，请核对下方标记，更新账面后重新清点本单。` }}</p><p class="setup-note">本单只核对所选批次；其他批次收发不影响新建或已更新的盘点单。实盘留空表示未盘点；实物为零请填 0。不同单位分别核对，差异行必须写明原因。已入账结果保留，不覆盖原收发流水。</p>
        <div v-if="remoteDoc" class="setup-warning" role="alert"><p>盘点单已被其他操作更新（最新状态：{{stateNames[remoteDoc.status]}}）。本页未保存的填写仍保留，请先记录需要保留的内容，再打开最新盘点单核对；不会自动覆盖或合并。</p><button :disabled="busy||frozen||loading" @click="openLatest">打开最新盘点单</button></div>
        <div class="setup-table"><table><thead><tr><th>物料 / 仓位</th><th>缸号 / 卷号</th><th>账面</th><th>实盘</th><th>盈亏差异</th><th>差异原因</th></tr></thead><tbody><tr v-for="(line,index) in doc.lines" :key="line.batch_id"><td><strong>{{line.snapshot.item_name}}</strong><small v-if="doc.changed_batch_ids?.includes(line.batch_id)" class="error-text">{{ doc.legacy_scope ? '旧范围需重新核对' : '盘点期间有变动' }}</small><small>{{line.snapshot.item_code}} · {{line.snapshot.location}}</small></td><td>{{line.snapshot.lot||'—'}} / {{line.snapshot.roll_no||'—'}}</td><td>{{line.snapshot.quantity}} {{line.snapshot.unit}}</td><td><input v-model="line.actual" class="quantity-input" inputmode="decimal" :aria-label="`实盘数量 ${index+1}`" :disabled="!editable" placeholder="未盘点" @input="changed"/></td><td>{{difference(line.actual,line.snapshot.quantity)}} {{line.snapshot.unit}}</td><td><input v-model="line.reason" :aria-label="`差异原因 ${index+1}`" :disabled="!editable" maxlength="1000" placeholder="有差异时必填" @input="changed"/></td></tr></tbody></table></div>
        <div v-if="doc.status==='DRAFT'" class="setup-count-actions"><label>盘点入账日期<input v-model="countDate" type="date" :max="today()" :disabled="busy||frozen" aria-label="盘点入账日期" @change="changed"/></label><div class="setup-actions"><button :disabled="!editable" @click="act('SAVE')">保存实盘草稿</button><button :disabled="!editable" @click="act('REFRESH')">更新账面并重盘</button></div><label class="confirm-count"><input v-model="postingConfirmed" type="checkbox" :disabled="!canConfirmCount"/>已核对全部实盘、差异原因与截止日期</label><button class="primary" :disabled="!canConfirmCount||!postingConfirmed" @click="act('POST')">确认盘点并入账</button><p v-if="!canPost" class="setup-note">实盘可先保存，再由有库存更正权限的人员核对入账。</p><details><summary>取消本次盘点</summary><div class="setup-actions"><input v-model="actionReason" placeholder="取消原因" :disabled="!editable" aria-label="取消原因"/><button :disabled="!editable||!actionReason.trim()" @click="act('CANCEL')">确认取消盘点</button></div></details></div>
        <details class="setup-audit"><summary>操作记录（{{doc.events.length}}）</summary><p v-for="(event,index) in doc.events" :key="index">{{actionNames[event.action]||event.action}} · {{event.actor_name}} · {{event.at}} {{event.reason}}</p></details>
      </section>
    </template>
  </div>
</template>

<style scoped>
.inventory-setup{background:#fff;border-radius:12px;color:#0f172a;font-size:13px}.setup-heading,.setup-count-heading{display:flex;justify-content:space-between;gap:16px;align-items:flex-start;padding:22px 24px;border-bottom:1px solid #e2e8f0}.setup-heading h2{font-size:19px;margin:0 0 8px}.setup-heading p,.setup-count-heading p{color:#64748b;margin:5px 0}.setup-actions,.setup-filters,.setup-selection,.setup-footer,.setup-summary{display:flex;align-items:center;gap:12px;flex-wrap:wrap}.setup-actions button,button{display:inline-flex;align-items:center;justify-content:center;gap:6px;background:#fff;border:1px solid #dbe3ec;border-radius:7px;padding:8px 12px;font-weight:600;cursor:pointer;white-space:nowrap}button.primary{background:#0f766e;color:white;border-color:#0f766e}button:disabled{opacity:.45;cursor:not-allowed}input:not([type=checkbox]),select{border:1px solid #dbe3ec;background:#f8fafc;border-radius:6px;padding:8px 10px;min-height:34px;max-width:100%;color:#0f172a}input[type=checkbox]{accent-color:#0f766e;width:15px;height:15px;vertical-align:middle}label{display:inline-flex;align-items:center;gap:8px}input:focus,select:focus,button:focus-visible{outline:2px solid #14b8a6;outline-offset:2px}.setup-filters{padding:16px 24px;border:0;border-bottom:1px solid #e2e8f0;background:#f8fafc}.setup-filters>label{white-space:nowrap}.setup-file{flex:1;min-width:300px}.setup-file input{flex:1;width:0;min-width:0}.setup-filters>span{color:#64748b;font-size:12px}.setup-steps{display:flex;gap:40px;flex-wrap:wrap;list-style:none;margin:0;padding:18px 24px;color:#0f766e;font-weight:600}.setup-note{padding:10px 24px;color:#64748b;line-height:1.8;margin:0;font-size:12px}.setup-error,.setup-success,.setup-warning{margin:14px 24px;padding:12px 14px;border-radius:7px;line-height:1.7}.setup-error{background:#fff1f2;color:#b91c1c}.setup-success{background:#f0fdfa;color:#0f766e}.setup-warning{background:#fffbeb;color:#92400e}.setup-summary{padding:16px 24px;background:#f0fdfa;color:#0f766e}.setup-table{overflow:auto;max-height:580px}.setup-table table{width:100%;border-collapse:collapse;text-align:left;white-space:nowrap}.setup-table th{position:sticky;top:0;background:#f8fafc;color:#64748b;font-size:12px;font-weight:500;z-index:1}.setup-table th,.setup-table td{padding:13px 20px;border-bottom:1px solid #edf2f7}.setup-table td:last-child{white-space:normal;min-width:140px;max-width:350px}.setup-table small{display:block;color:#64748b;font-size:12px;margin-top:5px}.setup-table .error-text,.error-text{color:#b91c1c}.setup-footer{justify-content:space-between;padding:16px 24px;border-top:1px solid #e2e8f0}.setup-footer label{font-size:12px;color:#475569}.setup-history{border-top:1px solid #e2e8f0}.setup-history h3{font-size:15px;padding:20px 24px 10px;margin:0}.setup-history h3 span{font-weight:400;color:#64748b;font-size:12px}.setup-details{background:#f8fafc;border:1px solid #cbd5e1;margin:16px 24px;border-radius:8px}.setup-details h4{padding:12px 20px;margin:0}.setup-selection{padding:16px 24px}.setup-selection>span{color:#0f766e;font-weight:600}.setup-selection label{flex:1}.setup-selection input{min-width:160px;flex:1}.setup-empty{padding:38px 24px;text-align:center;color:#64748b}.setup-count-actions{padding:18px 24px;display:flex;align-items:center;gap:16px;flex-wrap:wrap;border-top:1px solid #e2e8f0}.setup-count-actions details{width:100%;color:#64748b}.setup-count-actions details .setup-actions{padding-top:12px}.setup-count-actions .confirm-count{flex-basis:100%}.setup-count-actions .setup-note{padding:0}.quantity-input{width:120px}.setup-audit{padding:18px 24px;color:#64748b;border-top:1px solid #e2e8f0}.setup-audit p{padding:6px 0}summary{cursor:pointer}.setup-count-heading h3{font-size:16px;margin:0 0 10px}@media(max-width:720px){.setup-heading,.setup-count-heading{padding:16px;flex-direction:column}.setup-filters,.setup-selection,.setup-footer,.setup-steps,.setup-count-actions{padding:14px 16px;gap:12px}.setup-steps{font-size:12px}.setup-filters>label{flex-wrap:wrap}.setup-note{padding:10px 16px}.setup-table th,.setup-table td{padding:12px}.setup-footer>label{align-items:flex-start}.setup-heading .setup-actions{width:100%}.setup-selection label{flex-basis:100%}}
</style>
