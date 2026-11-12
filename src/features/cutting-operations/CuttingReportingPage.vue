<script setup lang="ts">
import StatusPill from '@/components/common/StatusPill.vue'
import SectionPanel from '@/components/common/SectionPanel.vue'
import PageHeader from '@/components/common/PageHeader.vue'
import { Button } from '@/components/ui/button'
import { computed, inject, nextTick, onBeforeUnmount, onMounted, ref, useId } from 'vue'
import { RouterLink, onBeforeRouteLeave, routerKey, type LocationQueryRaw } from 'vue-router'
import { cuttingApi, errorMessage, type Access } from './api'
import { ordersApi, type CuttingOrder } from './ordersApi'
import { reportingApi, reportLabels, reportPermission, type ProductionInput, type ProductionView, type ReportAction, type ReportCommand, type ReportDocument, type ReportTask, type ReportKind } from './reportingApi'
import { CUTTING_BASE, CUTTING_FACTORY } from './navigation'
import { orderProductName, unclassifiedStyle, unclassifiedStyleHint } from './orderDisplay'
import { cuttingDestination, useCuttingLocation } from './location'
import CuttingLocationNotice from './CuttingLocationNotice.vue'
import CuttingHistoryPager from './CuttingHistoryPager.vue'
import CuttingTaskBoard from './CuttingTaskBoard.vue'
import CuttingSubnav from './CuttingSubnav.vue'
import CuttingPiecePaste from './CuttingPiecePaste.vue'
const formId = `cutting-reporting-${useId()}`
const fieldId = (name: string) => `${formId}-${name}`
const partField = (code: string, quantity: 'good' | 'rejected' | 'scrap') =>
  `part_${quantity}_${encodeURIComponent(code)}`

// Editable search text is applied only by an explicit query.
const appliedQuery=ref('')
const reportingView=ref('tasks')
const orderListOpen=ref(false)
const changesOnly=ref(false), ordersLoading=ref(false), ordersLoaded=ref(false), ordersError=ref('')
const failedOrdersPage=ref(1)
let ordersGeneration=0
const reportingTabs=[{id:'tasks',label:'每日任务'},{id:'records',label:'日报记录'},{id:'parts',label:'裁片配套'},{id:'external',label:'外发收回与验收'},{id:'handover',label:'交接与抽查'}]
function changeReportingView(value:string){
  // Switching views retains the mounted editor and its pending command.
  reportingView.value=value
}

const access=ref<Access|null>(null), rows=ref<CuttingOrder[]>([]), selected=ref<CuttingOrder|null>(null), result=ref<ProductionView|null>(null)
const loading=ref(false), saving=ref(false), error=ref(''), notice=ref(''), needsLogin=ref(false)
const locationError = ref('')
const ordersDestination = { path: `${CUTTING_BASE}/reporting`, query: { factory: CUTTING_FACTORY } }
const page=ref(1), total=ref(0), query=ref(''), asOf=ref('')
const entry=ref<ProductionInput|null>(null), documentId=ref(''), reason=ref(''), editingExisting=ref(false)
const decision=ref<ReportAction|null>(null), baseline=ref(''), frozenParts=ref<ReportTask['parts']>([])
const pending=ref<{id:string;action:ReportAction;body:ReportCommand;statisticsDate:string}|null>(null), uncertain=ref(false)
let alive=true, generation=0
const available=computed(()=>access.value?.enabled && access.value.orders_schema_ready && access.value.reporting_schema_ready)
const can=(permission:string)=>!!access.value?.permissions.includes(permission)
const receiptTime=new Intl.DateTimeFormat('zh-CN',{timeZone:'Asia/Shanghai',year:'numeric',month:'2-digit',day:'2-digit',hour:'2-digit',minute:'2-digit',second:'2-digit',hourCycle:'h23'})
function orderChanges(row:CuttingOrder){
  const old=row.current?.data.order
  if(!old||!row.needs_receipt)return []
  return ([['quantity','订单数量'],['requested_ship_date','交期']] as const).flatMap(([key,label])=>
    String(old[key]??'')===String(row.snapshot[key]??'') ? [] : [{label,old:old[key]??'—',current:row.snapshot[key]??'—'}])
}
const orderState=(row:CuttingOrder)=>row.needs_receipt?(row.snapshot.status==='cancelled'?'取消待确认':row.current?'变更待确认':'待签收'):
  row.snapshot.status==='cancelled'?'已取消':row.planning_summary?.published_version&&!row.planning_summary.published_stale?'已发布计划':'已接单'
const stateSnapshot=()=>JSON.stringify([entry.value,reason.value])
const unappliedPieces = ref(false)
const dirty=computed(()=>!!entry.value && (unappliedPieces.value || stateSnapshot()!==baseline.value))
const task=computed(()=>result.value?.tasks.find(t=>t.task_id===entry.value?.task_id))
const newReportsBlocked=computed(()=>!!selected.value?.needs_receipt||selected.value?.snapshot.status==='cancelled'||!!selected.value?.planning_summary?.published_stale)
const kindsFor=(t:ReportTask|undefined,mode:ProductionInput['mode'])=>Object.entries(reportLabels).filter(([kind])=>
  can(reportPermission(kind as ReportKind)) && (kind!=='daily'||!t?.historical) &&
  (!newReportsBlocked.value||kind!=='daily'&&!!t?.settlement_context) &&
  (kind!=='match'||mode==='parts') && (!['return','accept'].includes(kind)||(t?.settlement_context?.execution??t?.execution)==='outsourced'))
const kindOptions=computed(()=>kindsFor(task.value,entry.value?.mode||'sets'))
const summary=computed(()=>result.value?.summary)
const orderTitle = computed(() => {
  if (!selected.value || !result.value) return '生产记录'
  const snapshot = selected.value.snapshot
  const product = orderProductName(snapshot)
  return product === '未填写' ? String(snapshot.reference_no ?? '生产记录') : product
})
const statisticsDatePending=computed(()=>!!result.value && asOf.value!==result.value.as_of)
const clone=<T,>(value:T):T=>JSON.parse(JSON.stringify(value)) as T
function discard() {
  if(saving.value||pending.value){error.value='请先核对原操作结果，再离开或切换。';return false}
  return !dirty.value||window.confirm('有未保存的填数或更正内容，确定放弃？')
}
onBeforeRouteLeave(discard)
const router = inject(routerKey, undefined)
const presentationPaths = new Set<string>()
const location = useCuttingLocation(discard, () => {
  if (router && presentationPaths.delete(router.currentRoute.value.fullPath)) return
  void loadWorkspace()
})
const planningDestination = computed(() => {
  const lineId = selected.value?.line_id ?? ''
  const month = location.value?.lineId === lineId ? location.value.month : undefined
  return cuttingDestination(lineId, month ?? '', 'planning')
})

async function persistStatisticsDate(lineId: string, day: string) {
  if (!router) return
  const route = router.currentRoute.value
  const query: LocationQueryRaw = { ...route.query, line_id: lineId, day }
  if (location.value?.lineId !== lineId) {
    for (const key of ['month', 'focus_kind', 'focus_id', 'reporting_view']) delete query[key]
  }
  const destination = { path: route.path, query, hash: route.hash }
  const target = router.resolve(destination).fullPath
  if (target === route.fullPath || presentationPaths.has(target)) return
  presentationPaths.add(target)
  try {
    const failure = await router.replace(destination)
    if (failure) presentationPaths.delete(target)
  } catch {
    presentationPaths.delete(target)
  }
}
function beforeUnload(e:BeforeUnloadEvent){if(dirty.value||pending.value||saving.value){e.preventDefault();e.returnValue=''}}
onMounted(()=>{window.addEventListener('beforeunload',beforeUnload);void loadWorkspace()})
onBeforeUnmount(()=>{alive=false;generation++;ordersGeneration++;window.removeEventListener('beforeunload',beforeUnload)})
function fail(e:unknown){error.value=errorMessage(e);if((e as {response?:{status?:number}}).response?.status===401)needsLogin.value=true}
async function loadWorkspace(){
  const request=++generation;loading.value=true;error.value='';locationError.value='';selected.value=null;result.value=null;entry.value=null;asOf.value=''
  orderListOpen.value=false;ordersGeneration++;ordersLoading.value=false;ordersLoaded.value=false;rows.value=[]
  let locatingOrder = false
  try{
    const rights=await cuttingApi.access();if(!alive||request!==generation)return
    access.value=rights;needsLogin.value=false;if(!available.value)return
    const target=location.value
    if(target){
      locatingOrder = true
      reportingView.value = target.reportingView ?? 'records'
      const order=await ordersApi.read(target.lineId);if(!alive||request!==generation)return
      if (!order.current) {
        locationError.value = '关联订单尚未签收，请先在排期区核对。'
        return
      }
      await select(order);return
    }
    reportingView.value='tasks'
  }catch(e){
    if (alive && request === generation) {
      if (locatingOrder && (e as { response?: { status?: number } }).response?.status !== 401) {
        locationError.value = errorMessage(e)
      } else {
        access.value = null
        fail(e)
      }
    }
  }
  finally{if(alive&&request===generation)loading.value=false}
}
async function loadOrders(nextPage=1,apply=false){
  if(apply)appliedQuery.value=query.value
  const request=++ordersGeneration
  ordersLoading.value=true;ordersError.value='';failedOrdersPage.value=nextPage
  try{
    const response=await ordersApi.list(nextPage,appliedQuery.value,'','',changesOnly.value)
    if(!alive||request!==ordersGeneration)return
    rows.value=response.data;total.value=response.total;page.value=response.page;ordersLoaded.value=true
  }catch(e){
    if(alive&&request===ordersGeneration){
      rows.value=[];total.value=0;ordersLoaded.value=false;ordersError.value=errorMessage(e)
      if((e as {response?:{status?:number}}).response?.status===401)needsLogin.value=true
    }
  }finally{if(alive&&request===ordersGeneration)ordersLoading.value=false}
}
async function showOrders(onlyChanges=false,keyword=''){
  const newScope=changesOnly.value!==onlyChanges||onlyChanges&&keyword!==appliedQuery.value
  changesOnly.value=onlyChanges
  if(newScope){query.value=keyword;appliedQuery.value=keyword;rows.value=[];ordersLoaded.value=false}
  orderListOpen.value=true
  void loadOrders(newScope||onlyChanges?1:page.value)
  await nextTick()
  if(alive&&orderListOpen.value)document.getElementById(fieldId('order_query'))?.focus({preventScroll:!onlyChanges})
}
function closeOrders(){
  orderListOpen.value=false
  document.getElementById(fieldId('orders_toggle'))?.focus({preventScroll:true})
}
async function select(row: CuttingOrder, intent: 'select' | 'statistics' | 'recover' = 'select') {
  if(!discard())return
  const refreshStatistics = intent === 'statistics'
  const target = location.value
  const sameOrder = selected.value?.line_id === row.line_id
  const targetDay = target?.lineId === row.line_id ? target.day : undefined
  const day = refreshStatistics ? (asOf.value || undefined) : ((sameOrder ? result.value?.as_of : undefined) ?? targetDay)
  if (!sameOrder) asOf.value = ''
  const request=++generation;selected.value=row;entry.value=null;error.value='';notice.value='';loading.value=true
  if (!refreshStatistics) result.value = null
  try {
    const documentId = target?.lineId === row.line_id && target.kind === 'report' ? target.id : undefined
    const response = await reportingApi.read(row.line_id, day, 1, undefined, documentId)
    if (!alive || request !== generation) return
    result.value = response
    if (intent !== 'recover') asOf.value = response.as_of
    needsLogin.value = false
    if (refreshStatistics) {
      await persistStatisticsDate(row.line_id, response.as_of)
    }
    return true
  } catch (e) {
    if (alive && request === generation) {
      fail(e)
      const status = (e as { response?: { status?: number } }).response?.status
      if (status === 401 || status === 403 || status === 404) result.value = null
    }
  } finally {
    if (alive && request === generation) loading.value = false
  }
}
async function openOrder(row: CuttingOrder) {
  if (await select(row) && selected.value?.line_id === row.line_id && result.value) {
    const chooser = document.getElementById(fieldId('orders'))
    const restoreFocus = chooser?.contains(document.activeElement)
    orderListOpen.value = false
    if (reportingView.value === 'tasks') changeReportingView('records')
    if (restoreFocus) {
      await nextTick()
      if (alive && (document.activeElement === document.body || chooser?.contains(document.activeElement))) {
        document.getElementById(fieldId('orders_toggle'))?.focus({ preventScroll: true })
      }
    }
  }
}

async function historyPage(next:number){
  if(!selected.value||!result.value||loading.value||saving.value||pending.value)return
  const request=++generation;loading.value=true;error.value=''
  try{
    const response=await reportingApi.read(selected.value.line_id,result.value.as_of,next,result.value.version)
    if(alive&&request===generation)result.value=response
  }catch(e){
    if(alive&&request===generation){
      fail(e)
      const status=(e as {response?:{status?:number}}).response?.status
      if(status===401||status===403){result.value=null;entry.value=null}
    }
  }finally{if(alive&&request===generation)loading.value=false}
}
function today(){return new Intl.DateTimeFormat('sv-SE',{timeZone:'Asia/Shanghai',year:'numeric',month:'2-digit',day:'2-digit'}).format(new Date())}
function start(t:ReportTask){
  if(!discard())return
  const mode=t.mode||(reportingView.value==='parts'?'parts':'sets')
  const preferred=t.historical||reportingView.value==='handover'?'handover':reportingView.value==='external'?(can('return_write')?'return':'accept'):'daily'
  const options=kindsFor(t,mode)
  const kind=(options.find(([key])=>key===preferred)||options[0])?.[0] as ReportKind|undefined
  if(!kind)return
  entry.value={task_id:t.task_id,plan_version:t.plan_version,day:result.value?.as_of||today(),mode,kind,sets:0,rejected:0,scrap:0,parts:[],evidence:'',exception_reason:''}
  frozenParts.value=clone(t.parts);documentId.value=crypto.randomUUID();reason.value='';editingExisting.value=false;decision.value=null
  normalize();baseline.value=stateSnapshot()
}
function edit(doc:ReportDocument, action:ReportAction|null=null){
  if(!discard())return
  const source=action==='discard'?doc.draft:action?doc.posted:(doc.draft||doc.posted)
  if(!source)return
  entry.value=clone(source.data.entry);frozenParts.value=clone(source.data.context.parts);documentId.value=doc.document_id
  reason.value='';editingExisting.value=true;decision.value=action;baseline.value=stateSnapshot()
}
function normalize(){
  if(!entry.value)return
  const e=entry.value
  if(!editingExisting.value&&!kindOptions.value.some(([kind])=>kind===e.kind)){
    const first=kindOptions.value[0]?.[0] as ReportKind|undefined
    if(first)e.kind=first
  }
  const settlement=task.value?.settlement_context
  if(!editingExisting.value && task.value){
    e.plan_version=e.kind!=='daily'&&settlement?settlement.plan_version:task.value.plan_version
    frozenParts.value=clone(e.kind!=='daily'&&settlement?settlement.parts:task.value.parts)
  }
  e.sets=0;e.rejected=0;e.scrap=0
  e.parts=e.kind==='daily'&&e.mode==='parts'?frozenParts.value.map(p=>({code:p.code,good:0,rejected:0,scrap:0})):[]
}
function cancel(){if(discard()){entry.value=null;decision.value=null}}
async function submit(action:ReportAction){
  if(saving.value || unappliedPieces.value)return
  if(!pending.value){
    if(!selected.value||!result.value||!entry.value)return
    if(!can(action==='review'?'report_review':reportPermission(entry.value.kind))){error.value='没有此业务类型的操作权限。';return}
    if(!reason.value.trim()){error.value='请填写本次提交、更正或抽查说明。';return}
    pending.value={id:selected.value.line_id,action,statisticsDate:result.value.as_of,body:{factory_id:CUTTING_FACTORY,operation_id:crypto.randomUUID(),expected_version:result.value.version,
      document_id:documentId.value,reason:reason.value,...(action==='save'||action==='post'?{entry:clone(entry.value)}:{})}}
    uncertain.value=false
  }
  generation++;loading.value=false;saving.value=true;error.value=''
  try{
    const operation = pending.value
    const response = await reportingApi.command(operation.id, operation.action, operation.body, operation.statisticsDate)
    if (!alive) return
    result.value=response;pending.value=null;uncertain.value=false;needsLogin.value=false;entry.value=null;decision.value=null
    notice.value='操作已保存。生效记录计入实绩，草稿不计产量；原版本可在历史中查看。'
  }catch(e){if(!alive)return;fail(e);const status=(e as {response?:{status?:number}}).response?.status
    if(status&&status>=400&&status<500&&status!==401)needsLogin.value=false
    if(!status||status>=500||status===408)uncertain.value=true
    if(!uncertain.value&&status&&status>=400&&status<500&&status!==401&&status!==408)pending.value=null
  }finally{saving.value=false}
}
async function recover(){
  if(!pending.value||saving.value)return
  saving.value=true;error.value=''
  try{
    const answer=await reportingApi.recover(pending.value.id,pending.value.action,pending.value.body);if(!alive)return
    pending.value=null;uncertain.value=false;needsLogin.value=false
    if(answer.state==='committed'){
      entry.value=null;decision.value=null;saving.value=false
      if(selected.value)await select(selected.value, 'recover')
      if (alive) notice.value = result.value ? '已核实原操作成功，已重新读取原截止日期的实绩。' : '已核实原操作成功，请重新读取实绩。'
    }
    else notice.value='已确认原操作未执行并停止；草稿保留，可修改后重新提交。'
  }catch(e){if(alive)fail(e)}finally{saving.value=false}
}
const effectiveEntry=(d:ReportDocument)=>(d.posted||d.draft||d.history[0])!.data.entry
</script>

<template>
  <section class="cutting-page cutting-review-page cutting-master reporting-page">
    <CuttingLocationNotice :location="location" :selected-id="result?selected?.line_id:undefined" />
    <PageHeader title="每日记录" description="查看当日任务、生产日报、裁片配套、外发验收与交接进度。">
      <template v-if="available&&!needsLogin&&!locationError" #actions>
        <Button :id="fieldId('orders_toggle')" type="button" :aria-expanded="orderListOpen" :aria-controls="fieldId('orders')" @click="orderListOpen?closeOrders():showOrders()">选择生产订单</Button>
      </template>
    </PageHeader>
    <p v-if="error" role="alert" class="cutting-error">{{ error }}</p><p v-if="notice" role="status">{{ notice }}</p>
    <p v-if="loading" role="status">正在读取生产记录…</p>
    <div v-if="needsLogin"><p>登录已失效，填报内容暂时隐藏。请在新标签页重新登录，再重试或核对原操作。</p><a href="/login" target="_blank" rel="noopener">重新登录</a></div>
    <div v-if="pending" class="cutting-master-actions"><Button variant="outline" :disabled="saving" @click="submit(pending.action)">重试原操作</Button><Button variant="outline" :disabled="saving" @click="recover">核对保存结果／停止未执行操作</Button></div>
    <p v-if="!loading&&access&&!available&&!needsLogin">每日记录尚未启用。需完成 0155 迁移，并为生产岗位分别授予填报、抽查、外发收回、外发验收或交接权限。</p>
    <SectionPanel v-if="locationError" title="无法定位关联订单" class="cutting-content-panel">
      <p role="alert" class="cutting-error">{{ locationError }}</p>
      <template #action><Button as-child variant="outline"><RouterLink :to="ordersDestination">返回当日任务</RouterLink></Button></template>
    </SectionPanel>
    <template v-else-if="available&&!needsLogin">
      <div class="report-workspace">
        <SectionPanel :id="fieldId('orders')" v-show="orderListOpen" :title="changesOnly?'订单变更待确认':'选择生产订单'" subtitle="首次有效下发自动接单。影响生产的订单变更由裁床确认。" class="cutting-content-panel report-orders" @keydown.esc.stop="closeOrders">
          <template #action>
            <div class="cutting-master-actions"><Button v-if="changesOnly" variant="outline" @click="showOrders()">查看全部订单</Button><Button variant="outline" @click="closeOrders">收起</Button></div>
          </template>
          <div class="report-orders-body">
          <form class="report-order-filter" @submit.prevent="loadOrders(1,true)">
            <label :for="fieldId('order_query')">订单／货号
              <input :id="fieldId('order_query')" name="order_query" v-model="query" maxlength="80" />
            </label>
            <Button variant="outline" :disabled="ordersLoading">查询订单</Button>
          </form>
          <p v-if="ordersLoading" role="status">正在读取生产订单…</p>
          <div v-else-if="ordersError" role="alert">{{ordersError}} <Button variant="outline" @click="loadOrders(failedOrdersPage)">按原条件重试</Button></div>
          <ul v-if="rows.length&&!ordersLoading" class="report-order-list" aria-label="生产订单">
            <li v-for="row in rows" :key="row.line_id" :class="{ 'report-order-selected': selected?.line_id===row.line_id, 'report-order-pending': row.needs_receipt }">
              <div class="report-order-heading">
                <strong>{{ row.snapshot.reference_no }}</strong>
                <StatusPill :label="orderState(row)" :tone="row.needs_receipt?'amber':undefined" compact />
              </div>
              <p>{{ row.snapshot.product_no }} · {{ orderProductName(row.snapshot) }}</p>
              <p>{{ row.snapshot.customer_name }} · <span :title="unclassifiedStyleHint">{{ unclassifiedStyle }}</span></p>
              <details v-if="row.current?.data.receipt" class="report-order-evidence"><summary>接单记录</summary><p>{{ row.current.data.receipt.mode==='automatic'?'首次下发自动接单':'裁床人工确认' }} · 下发 V{{ row.current.data.receipt.source_version }} · {{ receiptTime.format(new Date(row.current.data.receipt.received_at)) }}</p></details>
              <details v-if="row.needs_receipt&&row.current" class="report-order-evidence"><summary>查看变更依据</summary>
                <p>已接 V{{ row.current.data.order.version ?? row.current.data.receipt?.source_version ?? '—' }} · 待确认 V{{ row.source_version }}</p>
                <p v-for="change in orderChanges(row)" :key="change.label">{{ change.label }} <strong>{{ change.old }} → {{ change.current }}</strong></p>
                <p v-if="row.snapshot.change_reason">变更说明 {{ row.snapshot.change_reason }}</p>
              </details>
              <div class="cutting-master-actions">
                <Button v-if="row.current" variant="outline" size="sm" :aria-current="selected?.line_id===row.line_id?'true':undefined" :disabled="saving||!!pending" @click="openOrder(row)">{{row.needs_receipt?'查看原记录':'查看记录'}}</Button>
                <Button v-if="row.needs_receipt" as-child variant="outline" size="sm"><RouterLink :to="cuttingDestination(row.line_id,'','planning')">前往排期确认</RouterLink></Button>
              </div>
            </li>
          </ul>
          <p v-if="!rows.length&&ordersLoaded&&!ordersLoading" class="cutting-no-records">{{appliedQuery?'当前筛选范围无匹配订单。':changesOnly?'当前没有待确认的订单变更。':'暂无已下发订单，请先由业务下发至裁床部。'}}<Button v-if="appliedQuery" variant="outline" @click="query='';loadOrders(1,true)">清除筛选</Button></p>
          <nav v-if="ordersLoaded" class="cutting-pagination" aria-label="每日记录订单分页"><span>第 {{ page }} 页 · 共 {{ total }} 条</span><div class="cutting-master-actions"><Button variant="outline" :disabled="page<=1||ordersLoading" @click="loadOrders(page-1)">上一页</Button><Button variant="outline" :disabled="page*50>=total||ordersLoading" @click="loadOrders(page+1)">下一页</Button></div></nav>
          </div>
      </SectionPanel>
        <CuttingSubnav v-if="selected" :model-value="reportingView" :items="reportingTabs" label="每日记录工作视图" @update:model-value="changeReportingView" />
        <CuttingTaskBoard v-show="reportingView==='tasks'" reporting>
          <template #order-changes="{ count, query: keyword }"><Button variant="outline" size="sm" @click="showOrders(true,keyword)"><StatusPill :label="`订单变更待确认 · ${count} 笔`" tone="amber" compact /></Button></template>
        </CuttingTaskBoard>
        <SectionPanel v-show="reportingView!=='tasks'||!!entry||!!pending" class="cutting-content-panel report-main" :title="orderTitle">
          <template v-if="selected&&result" #action><Button as-child variant="outline"><RouterLink :to="planningDestination">返回该订单排期</RouterLink></Button></template>
          <div v-if="selected&&result&&summary" class="report-detail">
            <p class="report-order-meta">{{ selected.snapshot.reference_no }} · 货号 {{ selected.snapshot.product_no }} · <span :title="unclassifiedStyleHint">{{ unclassifiedStyle }}</span></p>
            <p v-if="selected.needs_receipt" class="cutting-notice">订单变更待裁床确认。可追溯原记录，请先在生产排期确认新版本，再按有效计划填写新日报。</p>
            <p v-else-if="selected.planning_summary?.published_stale" class="cutting-notice">计划依据已变更。请在生产排期复核并重新发布，再填写新日报。</p>
        <form class="report-statistics-filter" @submit.prevent="select(selected!, 'statistics')"><label :for="fieldId('statistics_date')">统计截至日期<input :id="fieldId('statistics_date')" name="statistics_date" v-model="asOf" type="date" :max="today()" :disabled="loading||saving||!!pending" /></label><Button variant="outline" :disabled="loading||saving||!!pending">刷新统计</Button></form>
        <p v-if="statisticsDatePending" role="status">日期尚未应用。当前统计及新填报的默认日期仍为 {{ result.as_of }}。</p>
            <dl class="report-totals">
              <div><dt>订单总套数</dt><dd>{{ summary.order_sets ?? '待核定' }} <small v-if="summary.order_sets!=null">套</small></dd></div>
              <div><dt>合格完成</dt><dd>{{ summary.completed }} <small>套</small></dd></div>
              <div><dt>实际交数</dt><dd>{{ summary.actual_delivery }} <small>套</small></dd></div>
              <div><dt>未完成</dt><dd>{{ summary.remaining ?? '待核定' }} <small v-if="summary.remaining!=null">套</small></dd></div>
            </dl>
            <details class="report-statistics-details">
              <summary>统计明细与口径</summary>
              <p>截至 {{ result.as_of }}。实际交数按已交接套数统计；未完成＝订单总套数−合格完成，超产保留负数。</p>
              <p>当日完成／交接 {{ summary.day_completed }}／{{ summary.day_handed }} 套 · 待交接 {{ summary.completed_unhanded }} 套 · 累计计划差额（交接−计划）{{ summary.plan_difference }} 套</p>
              <div class="cutting-table-scroll" tabindex="0" role="region" aria-label="月度汇总，可横向滚动"><table><thead><tr><th>月份</th><th>计划</th><th>完成</th><th>交接</th></tr></thead><tbody><tr v-for="(m,month) in summary.months" :key="month"><td>{{ month }}</td><td>{{ m.planned }}</td><td>{{ m.completed }}</td><td>{{ m.handed }}</td></tr></tbody></table></div>
            </details>
          </div>
          <p v-if="!result&&reportingView!=='tasks'&&!loading&&!error" class="cutting-no-records">请选择生产订单，查看任务与生产记录。</p>
          <div v-if="selected&&result" v-show="reportingView!=='tasks'||!!entry||!!pending" class="report-detail">
        <h3>执行任务</h3>
        <p v-if="reportingView==='parts'">仅列按裁片核套或尚未确定报数方式的任务；已固定直接报套的任务不能改用裁片核套。</p>
        <p v-if="reportingView==='external'">文员负责收回，主管负责验收；操作按钮沿用各自独立授权。</p>
        <div v-for="t in result.tasks" v-show="(reportingView!=='external'||(t.settlement_context?.execution??t.execution)==='outsourced')&&(reportingView!=='parts'||t.mode!=='sets')" :key="t.task_id" :data-cutting-task="t.task_id" class="cutting-master-line">
          <div class="report-task-heading">
            <div>
              <h4>{{ t.name }} · {{ t.execution==='internal'?'本厂':'外发' }} <StatusPill :label="t.mode==='parts'?'按裁片核套':t.mode==='sets'?'直接报完整套数':'首次填报时确定'" compact /></h4>
              <p>{{ t.historical?'历史任务':'计划 V'+t.plan_version }} · 目标 {{ t.target_sets }} 套</p>
            </div>
            <Button v-if="(!t.historical||t.settlement_context)&&kindsFor(t,t.mode||'sets').length" :disabled="loading||saving||!!pending" @click="start(t)">{{ t.historical?'办理历史余额':'填报此任务' }}</Button>
          </div>
          <p v-if="t.settlement_context">以下实绩余额归属：{{ t.settlement_context.resource_name }} · {{ t.settlement_context.execution==='outsourced'?'外发':'本厂' }} · 冻结 BOM V{{ t.settlement_context.bom_version }}／计划 V{{ t.settlement_context.plan_version }}。计划变更不转移原执行方的数量。</p>
          <div class="report-task-balance">
            <span>合格完成 <strong>{{ t.balance?.completed ?? 0 }}</strong> 套</span>
            <span>已交接 <strong>{{ t.balance?.handed ?? 0 }}</strong> 套</span>
            <span v-if="t.mode!=='sets'">可新增核套 <strong>{{ t.balance?.matchable ?? 0 }}</strong> 套</span>
            <template v-if="t.mode==='parts'">
              <span v-for="p in (t.settlement_context?.parts??t.parts)" :key="p.code">{{ p.name }}余 <strong>{{ t.balance?.loose[p.code]??0 }}</strong> 片（不良 {{ t.balance?.part_rejected[p.code]??0 }}／报废 {{ t.balance?.part_scrap[p.code]??0 }}）</span>
            </template>
          </div>
          <p v-if="(t.settlement_context?.execution??t.execution)==='outsourced'">外厂报称 {{ t.balance?.claimed ?? 0 }} · 实收 {{ t.balance?.returned ?? 0 }} · 验收合格 {{ t.balance?.accepted ?? 0 }} · 不合格 {{ t.balance?.rejected ?? 0 }} · 待验 {{ (t.balance?.returned??0)-(t.balance?.accepted??0)-(t.balance?.rejected??0) }}</p>
        </div>
        <p v-if="!result.tasks.length">暂无已发布任务，请先在排期页发布任务与日计划。</p>
        <form v-if="entry" class="cutting-master-form report-form" @submit.prevent="submit(decision||'post')">
          <h3>{{ decision==='review'?'主管抽查':decision==='void'?'作废生效记录':decision==='discard'?'放弃已保存草稿':editingExisting?'编辑／更正原记录':'新增生产记录' }}</h3>
          <fieldset :disabled="saving||!!pending">
            <template v-if="!decision">
              <div class="cutting-master-fields"><label :for="fieldId('business_day')">生产／业务日期<input :id="fieldId('business_day')" name="business_day" v-model="entry.day" type="date" :max="today()" required /></label><label :for="fieldId('report_mode')">报数方式<select :id="fieldId('report_mode')" name="report_mode" v-model="entry.mode" :disabled="editingExisting||!!task?.mode" @change="normalize"><option value="sets">直接报完整套数</option><option value="parts">按裁片核套</option></select></label><label :for="fieldId('report_kind')">业务类型<select :id="fieldId('report_kind')" name="report_kind" v-model="entry.kind" :disabled="editingExisting" @change="normalize"><option v-for="[key,label] in kindOptions" :key="key" :value="key">{{ label }}</option></select></label></div>
              <p v-if="entry.kind==='daily'">填写当日新增数量，不填累计数；零表示明确无产出，未填日报仍视为未报。</p>
              <CuttingPiecePaste v-if="entry.kind==='daily' && entry.mode==='parts' && entry.parts.length" :key="documentId" :pieces="entry.parts" :day="entry.day" @pending="unappliedPieces = $event" @apply="entry.parts = $event" />
              <div v-if="entry.kind==='daily'&&entry.mode==='parts'" class="cutting-table-scroll" tabindex="0" role="region" aria-label="业务明细，可横向滚动"><table><thead><tr><th>部件／每套片数</th><th>合格新增片数</th><th>不良片数</th><th>报废片数</th></tr></thead><tbody><tr v-for="p in entry.parts" :key="p.code"><td>{{ p.code }} · {{ frozenParts.find(r=>r.code===p.code)?.name }} / {{ frozenParts.find(r=>r.code===p.code)?.pieces_per_set }}</td><td><input :id="fieldId(partField(p.code, 'good'))" :name="partField(p.code, 'good')" v-model.number="p.good" :aria-label="p.code+'合格片数'" type="number" min="0" max="1000000000" step="1" required /></td><td><input :id="fieldId(partField(p.code, 'rejected'))" :name="partField(p.code, 'rejected')" v-model.number="p.rejected" :aria-label="p.code+'不良片数'" type="number" min="0" max="1000000000" step="1" required /></td><td><input :id="fieldId(partField(p.code, 'scrap'))" :name="partField(p.code, 'scrap')" v-model.number="p.scrap" :aria-label="p.code+'报废片数'" type="number" min="0" max="1000000000" step="1" required /></td></tr></tbody></table></div>
              <div v-else class="cutting-master-fields"><label :for="fieldId('sets')">{{ entry.kind==='accept'?'验收合格套数':'本次套数' }}<input :id="fieldId('sets')" name="sets" v-model.number="entry.sets" type="number" min="0" max="1000000000" step="1" required /></label><label v-if="entry.kind==='daily'||entry.kind==='accept'" :for="fieldId('rejected_sets')">不良／验收不合格套数<input :id="fieldId('rejected_sets')" name="rejected_sets" v-model.number="entry.rejected" type="number" min="0" max="1000000000" step="1" required /></label><label v-if="entry.kind==='daily'" :for="fieldId('scrap_sets')">报废套数<input :id="fieldId('scrap_sets')" name="scrap_sets" v-model.number="entry.scrap" type="number" min="0" max="1000000000" step="1" required /></label></div>
              <p v-if="entry.kind==='match'">当前可配 {{ task?.balance?.matchable??0 }} 套；按冻结 BOM 配比消耗散片，重复核套会被拦截。</p>
              <label :for="fieldId('evidence')">现场依据／核套人／收回验收或交接凭据<textarea :id="fieldId('evidence')" name="evidence" v-model="entry.evidence" maxlength="500" required /></label><label :for="fieldId('exception_reason')">超产或实际条件未核定的说明<textarea :id="fieldId('exception_reason')" name="exception_reason" v-model="entry.exception_reason" maxlength="500" /></label>
            </template>
            <p v-else>原业务：{{ reportLabels[entry.kind] }}，{{ entry.day }}，{{ entry.sets }} 套。操作保留原记录及全部版本。</p>
            <label :for="fieldId('reason')">本次提交／更正／抽查说明<textarea :id="fieldId('reason')" name="reason" v-model="reason" maxlength="500" required /></label>
            <p v-if="unappliedPieces" role="status">请先校验并应用粘贴内容，或清空后继续。</p>
            <div class="cutting-master-actions"><Button variant="outline" v-if="!decision&&can(reportPermission(entry.kind))" type="button" :disabled="unappliedPieces" @click="submit('save')">保存草稿</Button><Button v-if="can(decision==='review'?'report_review':reportPermission(entry.kind))" type="submit" :disabled="unappliedPieces">{{ decision?'确认操作':'提交生效' }}</Button><Button variant="outline" type="button" @click="cancel">取消编辑</Button></div>
          </fieldset>
        </form>
        <h3>日报与业务记录</h3>
        <p>记录列表保留全部日期；上方统计按截止日计算。草稿及更正草稿不覆盖原生效数量。</p>
        <CuttingHistoryPager v-if="result.history_pagination" :value="result.history_pagination" :busy="loading||saving||!!pending" @page="historyPage" />
        <p v-if="!result.documents.length" class="cutting-no-records">暂无生产记录。</p>
        <div v-else class="report-record-list">
          <div class="report-record-row report-record-header" aria-hidden="true"><span>业务日期</span><span>记录类型</span><span>数量</span><span>状态</span><span></span></div>
          <details v-for="doc in result.documents" :key="doc.document_id" :data-cutting-report="doc.document_id">
            <summary class="report-record-row">
              <span>{{ effectiveEntry(doc).day }}</span>
              <span>{{ reportLabels[effectiveEntry(doc).kind] }}</span>
              <span>{{ effectiveEntry(doc).mode==='parts'&&effectiveEntry(doc).kind==='daily'?'裁片明细':effectiveEntry(doc).sets+' 套' }}</span>
              <StatusPill :label="doc.voided?'已作废':doc.posted?'已生效':'未生效'" compact />
              <span class="report-record-expand">详情</span>
            </summary>
            <div class="report-record-detail">
              <p>{{ (doc.posted||doc.draft||doc.history[0])?.data.context.task_name }} · {{ doc.review?'主管已抽查':'尚未抽查' }}<template v-if="doc.draft"> · 有草稿</template></p>
          <div class="cutting-master-actions" v-if="!doc.voided"><template v-if="can(reportPermission(effectiveEntry(doc).kind))"><Button variant="outline" :disabled="loading||saving||!!pending" @click="edit(doc)">编辑／更正</Button><Button variant="outline" v-if="doc.draft" :disabled="loading||saving||!!pending" @click="edit(doc,'discard')">放弃草稿</Button><Button variant="outline" v-if="doc.posted" :disabled="loading||saving||!!pending" @click="edit(doc,'void')">作废</Button></template><Button variant="outline" v-if="doc.posted&&can('report_review')" :disabled="loading||saving||!!pending" @click="edit(doc,'review')">主管抽查</Button></div>
          <details><summary>版本与操作依据</summary><article v-for="event in doc.history" :key="event.id"><p>V{{ event.version }} · {{ {save:'保存草稿',post:'提交生效',void:'作废',review:'主管抽查',discard:'放弃草稿'}[event.action] }} · {{ event.actor_id }} · {{ event.created_at }}</p><p>{{ event.reason }}；{{ event.data.entry.evidence }}；{{ event.data.entry.exception_reason }}</p><p>{{ event.data.entry.day }} · {{ event.data.entry.sets }} 套／不良 {{ event.data.entry.rejected }}／报废 {{ event.data.entry.scrap }} · BOM V{{ event.data.context.bom_version }} · {{ event.data.context.resource_name }}</p><p v-for="p in event.data.entry.parts" :key="p.code">{{ p.code }}：合格 {{ p.good }}／不良 {{ p.rejected }}／报废 {{ p.scrap }} 片</p></article></details>
            </div>
          </details>
        </div>
          </div>
        </SectionPanel>
      </div>
    </template>
  </section>
</template>

<style scoped>
.report-workspace {
  display: grid;
  grid-template-columns: minmax(0, 1fr);
  gap: 14px;
}
.report-orders, .report-main, .report-detail { min-width: 0; }
.report-orders-body { display: flex; flex-direction: column; gap: 16px; }
.report-detail { display: flex; flex-direction: column; gap: 12px; }
.report-order-filter, .report-statistics-filter, .report-task-heading {
  display: flex;
  align-items: end;
  flex-wrap: wrap;
  gap: 10px;
}
.report-order-filter label { flex: 0 1 270px; }
.report-order-filter [data-slot='button'],
.report-statistics-filter [data-slot='button'] { align-self: end; }
.report-statistics-filter label { flex-direction: row; align-items: center; gap: 10px; }
.report-statistics-filter input { width: auto; min-width: 140px; }
.report-order-list { display: grid; grid-template-columns: repeat(auto-fit, minmax(min(100%, 270px), 1fr)); gap: 8px; padding: 0; margin: 0; list-style: none; }
.report-order-list:has(> li:only-child) { grid-template-columns: minmax(0, 680px); }
.report-order-list li { min-width: 0; padding: 12px; border: 1px solid var(--border); border-radius: 10px; overflow-wrap: anywhere; }
.report-order-selected { background: var(--accent); box-shadow: inset 3px 0 var(--primary); }
.report-order-list .report-order-pending { border-color: #d3a968; }
.report-order-evidence summary { padding-block: 4px; color: var(--primary); }
.report-order-evidence[open] > p { margin-top: 2px; }
.report-order-heading { display: flex; flex-wrap: wrap; align-items: center; justify-content: space-between; gap: 4px 10px; }
.report-order-list [data-slot='button'] { margin-top: 6px; }
.report-order-meta, .report-order-list p, .report-record-detail p, .report-statistics-details p { color: var(--muted-foreground); }
.report-totals {
  display: grid;
  grid-template-columns: repeat(4, minmax(0, 1fr));
  margin: 0;
  border: 1px solid var(--border);
  border-radius: var(--radius);
}
.report-totals div { padding: 10px 14px; }
.report-totals div + div { border-inline-start: 1px solid var(--border); }
.report-totals dt { color: var(--muted-foreground); font-size: 13px; }
.report-totals dd { margin: 0; font-size: 26px; font-weight: 650; font-variant-numeric: tabular-nums; }
.report-totals small { font-size: 13px; }
.report-totals div:nth-child(2) dd { color: var(--primary); }
.report-task-heading { justify-content: space-between; align-items: start; }
.report-task-heading h4 { display: flex; flex-wrap: wrap; align-items: center; gap: 8px; }
.report-task-balance {
  display: flex;
  flex-wrap: wrap;
  gap: 6px 16px;
  margin-top: 10px;
  padding: 8px 12px;
  border-radius: var(--radius);
  background: var(--muted);
}
.report-record-list { border: 1px solid var(--border); border-radius: var(--radius); }
.report-record-row {
  display: grid;
  grid-template-columns: minmax(90px, 1.1fr) minmax(0, 1.4fr) minmax(0, 1fr) minmax(0, 1fr) auto;
  gap: 8px;
  align-items: center;
  justify-items: start;
  padding: 10px 12px;
}
.report-record-row::-webkit-details-marker { display: none; }
.report-record-header { background: var(--muted); font-size: 13px; font-weight: 600; }
.report-record-list > details { border-top: 1px solid var(--border); }
.report-record-expand { color: var(--primary); white-space: nowrap; }
.report-record-detail { padding: 0 12px 12px; }
.report-form fieldset { display: flex; flex-direction: column; gap: 14px; }
.reporting-page article { padding: 12px; border-bottom: 1px solid var(--border); overflow-wrap: anywhere; }
.reporting-page td input { width: 100px; }
.reporting-page p { font-size: 13px; line-height: 1.7; }

@media (max-width: 640px) {
  .report-totals { grid-template-columns: repeat(2, minmax(0, 1fr)); }
  .report-totals div:nth-child(3) { border-inline-start: 0; }
  .report-totals div:nth-child(n+3) { border-top: 1px solid var(--border); }
  .report-record-row { grid-template-columns: repeat(2, minmax(0, 1fr)); }
  .report-record-header { display: none; }
  .report-record-expand { grid-column: 1 / -1; }
}
</style>
