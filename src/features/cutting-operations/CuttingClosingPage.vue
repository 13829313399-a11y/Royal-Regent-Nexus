<script setup lang="ts">
import { onBeforeUnmount, onMounted, ref } from 'vue'
import PageHeader from '@/components/common/PageHeader.vue'
import SectionPanel from '@/components/common/SectionPanel.vue'
import StatusPill from '@/components/common/StatusPill.vue'
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

defineProps<{workspace:CuttingWorkspace}>()
const currentMonth = new Intl.DateTimeFormat('sv-SE',{timeZone:'Asia/Shanghai',year:'numeric',month:'2-digit'}).format(new Date())
const month=ref(currentMonth),query=ref(''),page=ref(1),total=ref(0),rows=ref<CuttingOrder[]>([])
const access=ref<Access>(),selected=ref<CuttingOrder>(),result=ref<ClosingPreview>(),loading=ref(false),error=ref('')
const paymentPanel=ref<InstanceType<typeof CuttingPayments>>()
async function openPayment(month:string,id:string,eventId?:string){await paymentPanel.value?.openPayment(month,id,eventId)}
const settlementPanel=ref<InstanceType<typeof CuttingSettlement>>()
async function openSettlement(month:string,id:string,eventId?:string){await settlementPanel.value?.openStatement(month,id,eventId)}
let generation=0,alive=true
const location=useCuttingLocation(()=>true,()=>{void load(1,true)})
onBeforeUnmount(()=>{alive=false;generation++})
function clearPreview(){generation++;result.value=undefined;loading.value=false;error.value=''}
function ready(rights:Access){return rights.enabled&&rights.orders_schema_ready&&rights.reporting_schema_ready&&rights.usage_schema_ready}
async function load(nextPage=1,followLocation=false){
  const ticket=++generation;result.value=undefined;selected.value=undefined;rows.value=[];access.value=undefined;loading.value=true;error.value=''
  try{
    const rights=await cuttingApi.access();if(!alive||ticket!==generation)return;access.value=rights
    if(!ready(rights))return
    const target=followLocation?location.value:undefined
    if(target){
      if(target.month)month.value=target.month
      const order=await ordersApi.read(target.lineId);if(!alive||ticket!==generation)return
      rows.value=[order];page.value=1;total.value=1
      if(order.current)await preview(order)
      return
    }
    const response=await ordersApi.list(nextPage,query.value)
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
onMounted(()=>void load(1,true))
</script>

<template>
  <section class="cutting-page cutting-master">
    <PageHeader :title="workspace.title" description="按自然月核对生产、外发验收、领退料及实际耗用，追溯补录与更正。"><template #actions><StatusPill label="内部月结／外发结算／付款核销／报表导出 · P4b–P4e" /></template></PageHeader>
    <p class="cutting-notice">内部材料月结与外发加工费结算分别办理；下方订单预览提供实时核对，尚未冻结或锁月。付款登记与核销在下方独立办理，不操作银行。</p>
    <CuttingCutover :access="access" :access-loading="loading" @payment="openPayment" @settlement="openSettlement" />
    <CuttingPeriodClosing :access="access" :access-loading="loading" />
    <CuttingSettlement ref="settlementPanel" :access="access" :access-loading="loading" @payment="openPayment" />
    <CuttingPayments ref="paymentPanel" :access="access" :access-loading="loading" @settlement="openSettlement" />
    <p v-if="error" role="alert" class="cutting-error">{{error}}</p>
    <Button v-if="error" variant="outline" :disabled="loading" @click="load(1)">重新读取月结工作区</Button>
    <p v-if="loading" role="status">正在读取月度核对…</p>
    <p v-if="access&&!access.enabled" class="cutting-notice">月结前核对尚未启用。</p>
    <p v-else-if="access&&!ready(access)" class="cutting-notice">请先完成订单、每日填数及耗用的显式迁移；缺少依据时不以零数代替。</p>
    <template v-else-if="access&&ready(access)">
      <SectionPanel title="选择核对订单与月份" class="cutting-content-panel">
        <form class="order-toolbar" @submit.prevent="load(1)">
          <label>核对月份<input v-model="month" aria-label="核对月份" type="month" min="2000-01" :max="currentMonth" required @change="clearPreview" /></label>
          <label>订单号／货号<input v-model="query" maxlength="80" /></label>
          <Button type="submit" variant="outline" :disabled="loading">查询订单</Button>
          <Button v-if="selected" type="button" variant="outline" :disabled="loading||!month" @click="preview()">刷新所选订单核对</Button>
        </form>
        <div class="cutting-table-scroll" role="region" aria-label="月结核对订单" tabindex="0"><table>
          <thead><tr><th>客户</th><th>订单号</th><th>货号</th><th>货名</th><th>款式分类</th><th>操作</th></tr></thead>
          <tbody><tr v-for="order in rows" :key="order.line_id"><td>{{order.snapshot.customer_name}}</td><td>{{order.snapshot.reference_no}}</td><td>{{order.snapshot.product_no}}</td><td>{{orderProductName(order.snapshot)}}</td><td :title="unclassifiedStyleHint">{{unclassifiedStyle}}</td><td><Button size="sm" variant="outline" :disabled="loading||!month||!order.current" @click="preview(order)">{{order.current?'月度核对':'待签收订单'}}</Button></td></tr></tbody>
        </table></div>
        <p v-if="!rows.length&&!loading" class="cutting-no-records">暂无已下发裁床订单。</p>
        <nav class="order-pagination" aria-label="月结订单分页"><span>第 {{page}} 页 · 共 {{total}} 条</span><Button variant="outline" :disabled="loading||page<=1" @click="load(page-1)">上一页</Button><Button variant="outline" :disabled="loading||page*50>=total" @click="load(page+1)">下一页</Button></nav>
      </SectionPanel>
      <p v-if="selected">当前订单：{{selected.snapshot.reference_no}} · {{orderProductName(selected.snapshot)}}</p>
      <CuttingClosingReport v-if="result" :key="result.line_id+result.month" :value="result" />
    </template>
  </section>
</template>
