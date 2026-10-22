<script setup lang="ts">
import { inject, nextTick, onBeforeUnmount, onMounted, ref, watch } from 'vue'
import { routeLocationKey } from 'vue-router'
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
const closingView=ref('overview')
let financialGeneration=0
async function changeClosingView(value:string){
 financialGeneration++
 closingView.value=value;await nextTick()
 if(value==='period')periodPanel.value?.activateMonth(month.value)
 if(value==='settlement')settlementPanel.value?.activateMonth(month.value)
 if(value==='payment')paymentPanel.value?.activateMonth(month.value)
}
const closingTabs=[{id:'overview',label:'月结总览'},{id:'period',label:'内部月结'},{id:'settlement',label:'外发对账与结算'},{id:'payment',label:'付款与核销'},{id:'exports',label:'冻结报表'},{id:'opening',label:'历史期初'}]
const periodPanel=ref<InstanceType<typeof CuttingPeriodClosing>>()
const route=inject(routeLocationKey,undefined)
async function openMonthly(kind:'period'|'settlement'|'payment',targetMonth:string,id:string,eventId?:string){
  const ticket=++financialGeneration,previousView=closingView.value
  closingView.value=kind;await nextTick()
  const opened=kind==='period'?await periodPanel.value?.openPeriod(targetMonth,eventId)
    :kind==='settlement'?await settlementPanel.value?.openStatement(targetMonth,id,eventId)
    :await paymentPanel.value?.openPayment(targetMonth,id,eventId)
  if(!alive||ticket!==financialGeneration)return
  if(opened)month.value=targetMonth
  else closingView.value=previousView
}
async function followFinancialLocation(){
  const view=route?.query.view,targetMonth=route?.query.month,id=route?.query.document_id,event=route?.query.event_id
  if(!['period','settlement','payment'].includes(String(view))||typeof targetMonth!=='string'||!/^\d{4}-(0[1-9]|1[0-2])$/.test(targetMonth))return
  await openMonthly(view as 'period'|'settlement'|'payment',targetMonth,typeof id==='string'?id:'',typeof event==='string'?event:undefined)
}
let navigationGeneration=0
async function loadLocation(){
  const ticket=++navigationGeneration
  await load(1,true)
  if(alive&&ticket===navigationGeneration&&access.value)await followFinancialLocation()
}

defineProps<{workspace:CuttingWorkspace}>()
const currentMonth = new Intl.DateTimeFormat('sv-SE',{timeZone:'Asia/Shanghai',year:'numeric',month:'2-digit'}).format(new Date())
const month=ref(currentMonth),query=ref(''),page=ref(1),total=ref(0),rows=ref<CuttingOrder[]>([])
const access=ref<Access>(),selected=ref<CuttingOrder>(),result=ref<ClosingPreview>(),loading=ref(false),error=ref('')
const paymentPanel=ref<InstanceType<typeof CuttingPayments>>()
async function openPayment(targetMonth:string,id:string,eventId?:string){await openMonthly('payment',targetMonth,id,eventId)}
const settlementPanel=ref<InstanceType<typeof CuttingSettlement>>()
async function openSettlement(targetMonth:string,id:string,eventId?:string){await openMonthly('settlement',targetMonth,id,eventId)}
let generation=0,alive=true
const location=useCuttingLocation(()=>true,()=>{void loadLocation()})
onBeforeUnmount(()=>{alive=false;generation++;financialGeneration++})
function clearPreview(){generation++;result.value=undefined;loading.value=false;error.value=''}
watch(month,clearPreview,{flush:'sync'})
function ready(rights:Access){return rights.enabled&&rights.orders_schema_ready&&rights.reporting_schema_ready&&rights.usage_schema_ready}
async function load(nextPage=1,followLocation=false,apply=false){
  if(apply){appliedQuery.value=query.value;nextPage=1}
  const target=followLocation?location.value:undefined
  if(target?.month)month.value=target.month
  const ticket=++generation;result.value=undefined;selected.value=undefined;rows.value=[];access.value=undefined;loading.value=true;error.value=''
  try{
    const rights=await cuttingApi.access();if(!alive||ticket!==generation)return;access.value=rights
    if(!ready(rights))return
    if(target){
      const order=await ordersApi.read(target.lineId);if(!alive||ticket!==generation)return
      rows.value=[order];page.value=1;total.value=1
      if(order.current)await preview(order)
      return
    }
    const response=await ordersApi.list(nextPage,appliedQuery.value)
    if(alive&&ticket===generation){rows.value=response.data;page.value=response.page;total.value=response.total}
  }catch(e){if(alive&&ticket===generation){access.value=undefined;error.value=errorMessage(e)}}
  finally{if(alive&&ticket===generation)loading.value=false}
}
async function preview(order=selected.value){
  if(!order)return
  const ticket=++generation,requestedMonth=month.value;result.value=undefined;selected.value=order;loading.value=true;error.value=''
  try{
    const rights=await cuttingApi.access();if(!alive||ticket!==generation)return;access.value=rights
    if(!ready(rights)){rows.value=[];return}
    const response=await closingApi.read(order.line_id,requestedMonth,rights.permissions.includes('cost_read'))
    if(alive&&ticket===generation)result.value=response
  }catch(e){if(alive&&ticket===generation){result.value=undefined;rows.value=[];access.value=undefined;error.value=errorMessage(e)}}
  finally{if(alive&&ticket===generation)loading.value=false}
}
onMounted(()=>void loadLocation())
</script>

<template>
  <section class="cutting-page cutting-master">
    <PageHeader :title="workspace.title" description="内部月结、外发加工费与付款分别办理，实时核对和冻结快照分别追溯。" />
    <CuttingSubnav :model-value="closingView" @update:model-value="changeClosingView" :items="closingTabs" label="月结工作视图" />
    <p class="cutting-notice">内部材料月结与外发加工费结算分别办理；下方订单预览提供实时核对，尚未冻结或锁月。付款登记与核销在下方独立办理，不操作银行。</p>
    <CuttingMonthlyOverview v-model:month="month" v-if="access?.enabled" v-show="closingView==='overview'||closingView==='exports'" :access="access" :exports-only="closingView==='exports'" @open="openMonthly" />
    <div v-show="closingView==='opening'"><CuttingCutover :access="access" :access-loading="loading" @payment="openPayment" @settlement="openSettlement" /></div>
    <div v-show="closingView==='period'"><CuttingPeriodClosing ref="periodPanel" :access="access" :access-loading="loading" /></div>
    <div v-show="closingView==='settlement'"><CuttingSettlement ref="settlementPanel" :access="access" :access-loading="loading" @payment="openPayment" /></div>
    <div v-show="closingView==='payment'"><CuttingPayments ref="paymentPanel" :access="access" :access-loading="loading" @settlement="openSettlement" /></div>
    <p v-if="error" role="alert" class="cutting-error">{{error}}</p>
    <Button v-if="error" variant="outline" :disabled="loading" @click="load(1)">重新读取月结工作区</Button>
    <p v-if="loading" role="status">正在读取月度核对…</p>
    <p v-if="access&&!access.enabled" class="cutting-notice">月结前核对尚未启用。</p>
    <p v-else-if="access&&!ready(access)" class="cutting-notice">请先完成订单、每日填数及耗用的显式迁移；缺少依据时不以零数代替。</p>
    <template v-else-if="access&&ready(access)">
      <div v-show="closingView==='overview'" class="cutting-overview">
      <SectionPanel title="实时核对 · 选择订单与月份" class="cutting-content-panel">
        <form class="order-toolbar" @submit.prevent="load(1,false,true)">
          <label>核对月份<input v-model="month" aria-label="核对月份" type="month" min="2000-01" :max="currentMonth" required @change="clearPreview" /></label>
          <label>订单号／货号<input v-model="query" maxlength="80" /></label>
          <Button type="submit" variant="outline" :disabled="loading">查询订单</Button>
          <Button v-if="selected" type="button" variant="outline" :disabled="loading||!month" @click="preview()">刷新所选订单核对</Button>
        </form>
        <div class="cutting-table-scroll" role="region" aria-label="月结核对订单" tabindex="0"><table>
          <thead><tr><th>客户</th><th>订单号</th><th>货号</th><th>货名</th><th>款式分类</th><th>操作</th></tr></thead>
          <tbody><tr v-for="order in rows" :key="order.line_id"><td>{{order.snapshot.customer_name}}</td><td>{{order.snapshot.reference_no}}</td><td>{{order.snapshot.product_no}}</td><td>{{orderProductName(order.snapshot)}}</td><td :title="unclassifiedStyleHint">{{unclassifiedStyle}}</td><td><Button size="sm" variant="outline" :disabled="loading||!month||!order.current" @click="preview(order)">{{order.current?'月度核对':'待签收订单'}}</Button></td></tr></tbody>
        </table></div>
        <p v-if="!rows.length&&!loading&&!error" class="cutting-no-records">{{appliedQuery?'当前筛选无匹配订单，请清除筛选后查看。':'暂无已下发裁床订单。'}}<Button v-if="appliedQuery" variant="outline" @click="query='';load(1,false,true)">清除筛选</Button></p>
        <nav class="order-pagination" aria-label="月结订单分页"><span>第 {{page}} 页 · 共 {{total}} 条</span><Button variant="outline" :disabled="loading||page<=1" @click="load(page-1)">上一页</Button><Button variant="outline" :disabled="loading||page*50>=total" @click="load(page+1)">下一页</Button></nav>
      </SectionPanel>
      <p v-if="selected">当前订单：{{selected.snapshot.reference_no}} · {{orderProductName(selected.snapshot)}}</p>
      <CuttingClosingReport v-if="result" :key="result.line_id+result.month" :value="result" />
      </div>
    </template>
  </section>
</template>
