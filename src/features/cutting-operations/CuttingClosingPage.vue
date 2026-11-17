<script setup lang="ts">
import { computed, inject, nextTick, onBeforeUnmount, onMounted, provide, ref, useId, watch } from 'vue'
import { routeLocationKey, routerKey, type LocationQueryRaw } from 'vue-router'
import { closingPresentationKey, closingReportTabs, readClosingReportTab, type ClosingReadLocation, type ClosingReportTab } from './closingPresentation'
import PageHeader from '@/components/common/PageHeader.vue'
import SectionPanel from '@/components/common/SectionPanel.vue'
import { Button } from '@/components/ui/button'
import { cuttingApi, errorMessage, type Access } from './api'
import { ordersApi, type CuttingOrder } from './ordersApi'
import { closingApi, type ClosingPreview } from './closingApi'
import { orderProductName, unclassifiedStyle, unclassifiedStyleHint } from './orderDisplay'
import type { CuttingWorkspace } from './navigation'
import CuttingClosingReport from './CuttingClosingReport.vue'
import CuttingPeriodClosing from './CuttingPeriodClosing.vue'
import CuttingSettlement from './CuttingSettlement.vue'
import CuttingPayments from './CuttingPayments.vue'
import CuttingCutover from './CuttingCutover.vue'
import { useCuttingLocation } from './location'
import CuttingSubnav from './CuttingSubnav.vue'
import CuttingMonthlyOverview from './CuttingMonthlyOverview.vue'
// Editable search text is applied only by an explicit query.
const appliedQuery=ref('')
const formId=`cutting-closing-${useId()}`
const closingView=ref('overview')
const financialContext=ref(0)
let financialGeneration=0
let locationPending=true
async function changeClosingView(value:string){
 if(value==='overview'&&closingView.value==='overview')return
 locationPending=false
 restoringLocation=false
 financialGeneration++
 financialContext.value++
 if(failedPreview.value)result.value=undefined
 failedPreview.value=undefined
 closingView.value=value;await nextTick()
 if(value==='period')periodPanel.value?.activateMonth(month.value)
 if(value==='settlement')settlementPanel.value?.activateMonth(month.value)
 if(value==='payment')paymentPanel.value?.activateMonth(month.value)
 void persistOverviewLocation()
}
const closingTabs=[{id:'overview',label:'月结总览'},{id:'period',label:'内部月结'},{id:'settlement',label:'外发对账与结算'},{id:'payment',label:'付款与核销'},{id:'exports',label:'冻结报表'},{id:'opening',label:'历史期初'}]
const periodPanel=ref<InstanceType<typeof CuttingPeriodClosing>>()
const route=inject(routeLocationKey,undefined)
const router=inject(routerKey,undefined)
const presentationPaths=new Set<string>()
let restoringLocation=true
const appliedOverviewMonth=ref<string>()
provide(closingPresentationKey,path=>presentationPaths.has(path))
async function persistOverviewLocation(){
  if(!router||!route||restoringLocation)return
  const simple=['overview','exports'].includes(closingView.value)
  if(!simple){
    const target=closingView.value==='period'?periodPanel.value?.getLocation():closingView.value==='settlement'?settlementPanel.value?.getLocation():closingView.value==='payment'?paymentPanel.value?.getLocation():undefined
    if(target)return persistFinancialLocation(closingView.value,target)
    return
  }
  const preview=closingView.value==='overview'?result.value:undefined
  // Keep the last successful order link while its preview is being refreshed.
  const linkedOrder=route.query.line_id&&(route.query.view===undefined||route.query.view==='overview')
  if(!preview&&selected.value&&closingView.value==='overview'&&linkedOrder)return
  const appliedMonth=preview?.month??appliedOverviewMonth.value
  if(!appliedMonth)return
  const query={...route.query}
  query.view=closingView.value;query.month=appliedMonth
  for(const key of ['document_id','event_id','line_id','focus_kind','focus_id','report_tab'])delete query[key]
  if(preview){
    query.line_id=preview.line_id
    if(reportTab.value!=='production')query.report_tab=reportTab.value
  }
  await persistQuery(query)
}
async function persistFinancialLocation(kind:string,location:ClosingReadLocation){
  if(!router||!route||restoringLocation||closingView.value!==kind)return
  const query:LocationQueryRaw={...route.query,view:kind,month:location.month}
  for(const key of ['document_id','event_id','line_id','focus_kind','focus_id','report_tab'])delete query[key]
  if(location.id)query.document_id=location.id
  if(location.eventId)query.event_id=location.eventId
  await persistQuery(query)
}
async function persistQuery(query:LocationQueryRaw){
  if(!router||!route)return
  const target=router.resolve({path:route.path,query,hash:route.hash}).fullPath
  if(target===route.fullPath||presentationPaths.has(target))return
  presentationPaths.add(target)
  try{const failure=await router.replace({path:route.path,query,hash:route.hash});if(failure)presentationPaths.delete(target)}
  catch{presentationPaths.delete(target)}
}
function overviewLoaded(value:string){appliedOverviewMonth.value=value;void persistOverviewLocation()}
async function openMonthly(kind:'period'|'settlement'|'payment',targetMonth:string,id:string,eventId?:string){
  const ticket=++financialGeneration,context=++financialContext.value,previousView=closingView.value
  closingView.value=kind;await nextTick()
  const opened=kind==='period'?await periodPanel.value?.openPeriod(targetMonth,eventId)
    :kind==='settlement'?await settlementPanel.value?.openStatement(targetMonth,id,eventId)
    :await paymentPanel.value?.openPayment(targetMonth,id,eventId)
  if(!alive||ticket!==financialGeneration||context!==financialContext.value)return
  if(opened){
    const selected=kind==='period'?periodPanel.value?.getLocation():kind==='settlement'?settlementPanel.value?.getLocation():paymentPanel.value?.getLocation()
    month.value=selected?.month??targetMonth
    void persistFinancialLocation(kind,selected??{month:targetMonth,id:id||undefined,eventId})
  }
  else closingView.value=previousView
}
async function followFinancialLocation(){
  const view=route?.query.view,targetMonth=route?.query.month,id=route?.query.document_id,event=route?.query.event_id
  if(!['period','settlement','payment'].includes(String(view))||typeof targetMonth!=='string'||!/^\d{4}-(0[1-9]|1[0-2])$/.test(targetMonth))return
  await openMonthly(view as 'period'|'settlement'|'payment',targetMonth,typeof id==='string'?id:'',typeof event==='string'?event:undefined)
}
let navigationGeneration=0
async function loadLocation(){
  locationPending=true
  restoringLocation=true
  const ticket=++navigationGeneration
  const view=route?.query.view,targetMonth=route?.query.month
  closingView.value=closingTabs.some(tab=>tab.id===view)?String(view):'overview'
  if(route?.query.factory==='huakang-c'&&typeof targetMonth==='string'&&/^\d{4}-(0[1-9]|1[0-2])$/.test(targetMonth)&&targetMonth<=currentMonth)month.value=targetMonth
  await load(1,true)
  if(alive&&ticket===navigationGeneration&&locationPending&&access.value&&!error.value){
    await followFinancialLocation()
    if(alive&&ticket===navigationGeneration)locationPending=false
  }
  if(alive&&ticket===navigationGeneration){restoringLocation=false;if(!error.value&&access.value?.enabled&&['period','settlement','payment'].includes(closingView.value))void persistOverviewLocation()}
}
async function retryWorkspace(event:MouseEvent){
  if(loading.value)return
  const target=previewRetry.value
  if(target){await preview(target.order,target.month,target.tab,event,true);return}
  if(locationPending)await loadLocation()
  else await load(1)
}

defineProps<{workspace:CuttingWorkspace}>()
const currentMonth = new Intl.DateTimeFormat('sv-SE',{timeZone:'Asia/Shanghai',year:'numeric',month:'2-digit'}).format(new Date())
const month=ref(currentMonth),query=ref(''),page=ref(1),total=ref(0),rows=ref<CuttingOrder[]>([])
const access=ref<Access>(),selected=ref<CuttingOrder>(),result=ref<ClosingPreview>(),loading=ref(false),error=ref('')
const reportTab=ref<ClosingReportTab>('production')
const failedPreview=ref<{order:CuttingOrder;month:string;tab:ClosingReportTab}>()
const previewRetry=computed(()=>closingView.value==='overview'?failedPreview.value:undefined)
const previousResult=computed(()=>!!result.value&&(loading.value||!!previewRetry.value))
const previewReport=ref<InstanceType<typeof CuttingClosingReport>>()
const retryArea=ref<HTMLElement>()
let previewFocus:AbortController|undefined
function trackPreviewFocus(event?:MouseEvent){
  previewFocus?.abort()
  const origin=event?.currentTarget
  if(!(origin instanceof HTMLButtonElement)||origin!==document.activeElement)return
  const tracker=new AbortController()
  previewFocus=tracker
  const options={signal:tracker.signal}
  const cancel=()=>tracker.abort()
  document.addEventListener('focusin',cancel,options)
  document.addEventListener('pointerdown',cancel,options)
  document.addEventListener('keydown',event=>{if(event.key==='Tab')cancel()},options)
  return {origin,tracker}
}
function selectReportTab(tab:ClosingReportTab){
  reportTab.value=tab
  void persistOverviewLocation()
}
const accessUnavailable=ref(false)
const paymentPanel=ref<InstanceType<typeof CuttingPayments>>()
async function openPayment(targetMonth:string,id:string,eventId?:string){await openMonthly('payment',targetMonth,id,eventId)}
const settlementPanel=ref<InstanceType<typeof CuttingSettlement>>()
async function openSettlement(targetMonth:string,id:string,eventId?:string){await openMonthly('settlement',targetMonth,id,eventId)}
let generation=0,alive=true
const location=useCuttingLocation(()=>true,()=>{if(route&&presentationPaths.delete(route.fullPath))return;void loadLocation()})
onBeforeUnmount(()=>{alive=false;generation++;financialGeneration++;previewFocus?.abort()})
function clearPreview(){previewFocus?.abort();generation++;result.value=undefined;failedPreview.value=undefined;loading.value=false;error.value=''}
watch(month,()=>{financialContext.value++;clearPreview()},{flush:'sync'})
function restoredMonth(kind:'period'|'settlement'|'payment',targetMonth:string,context:number|undefined){
  if(!alive||context!==financialContext.value||closingView.value!==kind||loading.value||accessUnavailable.value||!access.value?.enabled)return
  const permission=kind==='period'?'cost_read':kind==='settlement'?'settlement_read':'payment_read'
  if(access.value.permissions.includes(permission))month.value=targetMonth
}
function recordLocated(kind:'period'|'settlement'|'payment',target:ClosingReadLocation,context:number|undefined){
  if(!alive||context!==financialContext.value||closingView.value!==kind||loading.value||!access.value?.enabled||accessUnavailable.value)return
  const permission=kind==='period'?'cost_read':kind==='settlement'?'settlement_read':'payment_read'
  if(!access.value.permissions.includes(permission))return
  month.value=target.month
  void persistFinancialLocation(kind,target)
}
function ready(rights:Access){return rights.enabled&&rights.permissions.includes('read')&&rights.orders_schema_ready&&rights.reporting_schema_ready&&rights.usage_schema_ready}
async function load(nextPage=1,followLocation=false,apply=false){
  previewFocus?.abort()
  if(apply){appliedQuery.value=query.value;nextPage=1}
  const target=followLocation?location.value:undefined
  if(target?.month)month.value=target.month
  reportTab.value='production'
  failedPreview.value=undefined
  const ticket=++generation;result.value=undefined;selected.value=undefined;rows.value=[];access.value=undefined;accessUnavailable.value=false;loading.value=true;error.value=''
  try{
    const rights=await cuttingApi.access();if(!alive||ticket!==generation)return;access.value=rights
    if(!ready(rights))return
    if(target){
      const order=await ordersApi.read(target.lineId);if(!alive||ticket!==generation)return
      rows.value=[order];page.value=1;total.value=1
      if(order.current)await preview(order,month.value,readClosingReportTab(route?.query.report_tab))
      return
    }
    const response=await ordersApi.list(nextPage,appliedQuery.value)
    if(alive&&ticket===generation){
      rows.value=response.data;page.value=response.page;total.value=response.total
      if(closingView.value==='overview')void persistOverviewLocation()
    }
  }catch(e){if(alive&&ticket===generation){const status=(e as {response?:{status?:number}}).response?.status;accessUnavailable.value=status!==401&&status!==403;access.value=undefined;error.value=errorMessage(e)}}
  finally{if(alive&&ticket===generation)loading.value=false}
}
async function preview(
  order=selected.value,
  requestedMonth=month.value,
  tab:ClosingReportTab=order?.line_id===selected.value?.line_id?reportTab.value:'production',
  event?:MouseEvent,
  retry=false,
){
  if(!order)return
  const ticket=++generation,viewGeneration=financialGeneration
  const focus=trackPreviewFocus(event)
  if(result.value?.line_id!==order.line_id||result.value.month!==requestedMonth)result.value=undefined
  selected.value=order;reportTab.value=tab;accessUnavailable.value=false;loading.value=true;error.value=''
  try{
    const rights=await cuttingApi.access();if(!alive||ticket!==generation)return
    if(!ready(rights)){access.value=rights;result.value=undefined;rows.value=[];selected.value=undefined;failedPreview.value=undefined;return}
    const withCosts=rights.permissions.includes('cost_read')
    if(!withCosts&&result.value?.costs!==undefined)result.value=undefined
    const response=await closingApi.read(order.line_id,requestedMonth,withCosts)
    if(alive&&ticket===generation){
      access.value=rights
      result.value=response
      failedPreview.value=undefined
      if(!restoringLocation&&closingView.value==='overview')locationPending=false
      if(closingView.value==='overview')void persistOverviewLocation()
    }
  }catch(e){
    if(!alive||ticket!==generation)return
    const status=(e as {response?:{status?:number}})?.response?.status
    const canRetry=closingView.value==='overview'&&viewGeneration===financialGeneration
      &&(status===undefined||status===408||status===429||status>=500)
    failedPreview.value=canRetry?{order,month:requestedMonth,tab}:undefined
    if(!canRetry){result.value=undefined;rows.value=[];selected.value=undefined}
    accessUnavailable.value=status!==401&&status!==403
    access.value=undefined
    error.value=errorMessage(e)
  }
  finally{
    if(alive&&ticket===generation)loading.value=false
    if(focus){
      await nextTick()
      const active=document.activeElement
      const shouldRestore=!focus.tracker.signal.aborted&&alive&&ticket===generation&&viewGeneration===financialGeneration
        &&closingView.value==='overview'&&(active===document.body||active===focus.origin)
      focus.tracker.abort()
      if(shouldRestore){
        if(previewRetry.value)retryArea.value?.querySelector('button')?.focus()
        else if(retry&&result.value)previewReport.value?.focusTitle()
        else if(!error.value)focus.origin.focus()
      }
    }
  }
}
onMounted(()=>void loadLocation())
</script>

<template>
  <section class="cutting-page cutting-review-page cutting-master">
    <PageHeader :title="workspace.title" description="内部月结、外发加工费与付款分别办理，实时核对和冻结快照分别追溯。" />
    <CuttingSubnav :model-value="closingView" @update:model-value="changeClosingView" :items="closingTabs" label="月结工作视图" />
    <p class="cutting-notice">内部材料月结与外发加工费结算分别办理。实时核对不代表锁月；冻结报表按所选版本追溯，当前有效状态以版本提示为准。付款登记与核销不操作银行。</p>
    <CuttingMonthlyOverview v-model:month="month" v-if="access?.enabled" v-show="closingView==='overview'||closingView==='exports'" :access="access" :exports-only="closingView==='exports'" @open="openMonthly" @loaded="overviewLoaded" />
    <div v-show="closingView==='opening'"><CuttingCutover :access="access" :access-loading="loading" @payment="openPayment" @settlement="openSettlement" /></div>
    <div v-show="closingView==='period'"><CuttingPeriodClosing ref="periodPanel" :access="access" :access-loading="loading" :access-unavailable="accessUnavailable" :navigation-context="financialContext" @located="(target,context)=>recordLocated('period',target,context)" @restored="(target,context)=>restoredMonth('period',target,context)" /></div>
    <div v-show="closingView==='settlement'"><CuttingSettlement ref="settlementPanel" :access="access" :access-loading="loading" :access-unavailable="accessUnavailable" :navigation-context="financialContext" @located="(target,context)=>recordLocated('settlement',target,context)" @restored="(target,context)=>restoredMonth('settlement',target,context)" @payment="openPayment" /></div>
    <div v-show="closingView==='payment'"><CuttingPayments ref="paymentPanel" :access="access" :access-loading="loading" :access-unavailable="accessUnavailable" :navigation-context="financialContext" @located="(target,context)=>recordLocated('payment',target,context)" @restored="(target,context)=>restoredMonth('payment',target,context)" @settlement="openSettlement" /></div>
    <div v-if="error||previewRetry" ref="retryArea" class="space-y-3">
      <p v-if="error" role="alert" class="cutting-error">{{previousResult?`刷新失败，仍显示上次结果。${error}`:error}}</p>
      <p v-if="previewRetry" class="cutting-notice cutting-read-target"><span>重试目标：{{previewRetry.order.snapshot.reference_no}} · {{previewRetry.month}} · {{closingReportTabs[previewRetry.tab]}}</span></p>
      <Button variant="outline" :disabled="loading" @click="retryWorkspace">{{previewRetry?'重试原订单预览':'重新读取月结工作区'}}</Button>
    </div>
    <p v-if="loading" role="status">{{previousResult?'正在刷新月度核对，仍显示上次结果…':'正在读取月度核对…'}}</p>
    <p v-if="access&&!access.enabled" class="cutting-notice">月结前核对尚未启用。</p>
    <p v-else-if="access&&!ready(access)" class="cutting-notice">请先完成订单、每日填数及耗用的显式迁移；缺少依据时不以零数代替。</p>
    <div v-if="(access&&ready(access))||previousResult" v-show="closingView==='overview'" class="cutting-overview">
      <SectionPanel v-if="access&&ready(access)" title="实时核对 · 选择订单与月份" class="cutting-content-panel">
        <form class="order-toolbar" @submit.prevent="load(1,false,true)">
          <label :for="`${formId}-month`">核对月份<input :id="`${formId}-month`" name="month" v-model="month" aria-label="核对月份" type="month" min="2000-01" :max="currentMonth" required @change="clearPreview" /></label>
          <label :for="`${formId}-query`">订单号／货号<input :id="`${formId}-query`" name="order_q" v-model="query" maxlength="80" /></label>
          <Button type="submit" variant="outline" :disabled="loading">查询订单</Button>
          <Button v-if="selected" type="button" variant="outline" :disabled="loading||!month" @click="preview(selected,month,reportTab,$event)">刷新所选订单核对</Button>
        </form>
        <div class="cutting-table-scroll" role="region" aria-label="月结核对订单" tabindex="0"><table>
          <thead><tr><th>客户</th><th>订单号</th><th>货号</th><th>货名</th><th>款式分类</th><th>操作</th></tr></thead>
          <tbody><tr v-for="order in rows" :key="order.line_id"><td>{{order.snapshot.customer_name}}</td><td>{{order.snapshot.reference_no}}</td><td>{{order.snapshot.product_no}}</td><td>{{orderProductName(order.snapshot)}}</td><td :title="unclassifiedStyleHint">{{unclassifiedStyle}}</td><td><Button size="sm" variant="outline" :disabled="loading||!month||!order.current" @click="preview(order,month,undefined,$event)">{{order.current?'月度核对':'待签收订单'}}</Button></td></tr></tbody>
        </table></div>
        <p v-if="!rows.length&&!loading&&!error" class="cutting-no-records">{{appliedQuery?'当前筛选无匹配订单，请清除筛选后查看。':'暂无已下发裁床订单。'}}<Button v-if="appliedQuery" variant="outline" @click="query='';load(1,false,true)">清除筛选</Button></p>
        <nav class="order-pagination" aria-label="月结订单分页"><span>第 {{page}} 页 · 共 {{total}} 条</span><Button variant="outline" :disabled="loading||page<=1" @click="load(page-1)">上一页</Button><Button variant="outline" :disabled="loading||page*50>=total" @click="load(page+1)">下一页</Button></nav>
      </SectionPanel>
      <p v-if="selected">当前订单：{{selected.snapshot.reference_no}} · {{orderProductName(selected.snapshot)}}</p>
      <CuttingClosingReport v-if="result" ref="previewReport" :key="result.line_id+result.month" :tab="reportTab" :value="result" :previous-result="previousResult" @update:tab="selectReportTab" />
    </div>
  </section>
</template>
