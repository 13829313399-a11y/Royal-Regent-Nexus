<script setup lang="ts">
import { onBeforeUnmount, onMounted, ref } from 'vue'
import { onBeforeRouteLeave } from 'vue-router'
import PageHeader from '@/components/common/PageHeader.vue'
import SectionPanel from '@/components/common/SectionPanel.vue'
import { Button } from '@/components/ui/button'
import { cuttingApi, errorMessage, type Access } from './api'
import { ordersApi, type CuttingOrder } from './ordersApi'
import CuttingMaterialUsage from './CuttingMaterialUsage.vue'
import type { CuttingWorkspace } from './navigation'
import { orderProductName, unclassifiedStyle, unclassifiedStyleHint } from './orderDisplay'
import { useCuttingLocation } from './location'
import CuttingLocationNotice from './CuttingLocationNotice.vue'
import CuttingCostOverview from './CuttingCostOverview.vue'
import CuttingSubnav from './CuttingSubnav.vue'
const costView=ref('orders')
const costTabs=[{id:'orders',label:'订单费用'},{id:'issues',label:'耗用与原批次'},{id:'allocation',label:'完工与在制归属'},{id:'pending',label:'待计价与核对'},{id:'history',label:'成本变更历史'}]
async function openCost(lineId:string){
  if(!discard())return
  const ticket=++generation;loading.value=true;error.value=''
  try{const order=await ordersApi.read(lineId);if(alive&&ticket===generation){selected.value=order;costView.value='issues'}}
  catch(e){if(alive&&ticket===generation)error.value=errorMessage(e)}
  finally{if(alive&&ticket===generation)loading.value=false}
}
defineProps<{workspace:CuttingWorkspace}>()
const access=ref<Access>(),rows=ref<CuttingOrder[]>([]),selected=ref<CuttingOrder>(),query=ref(''),page=ref(1),total=ref(0),loading=ref(false),error=ref('')
const editor=ref<InstanceType<typeof CuttingMaterialUsage>>()
let alive=true,generation=0
function discard(){return editor.value?.discard()??true}
onBeforeRouteLeave(discard)
const location=useCuttingLocation(discard,()=>{void load(1,true,true)})
onBeforeUnmount(()=>{alive=false;generation++})
async function load(nextPage=page.value,navigation=false,followLocation=false){
  if(!navigation&&!discard())return
  const ticket=++generation;selected.value=undefined;rows.value=[];loading.value=true;error.value=''
  try{const rights=await cuttingApi.access();if(!alive||ticket!==generation)return;access.value=rights
    if(!rights.enabled||!rights.usage_schema_ready||!rights.permissions.includes('cost_read')){rows.value=[];return}
    const target=followLocation?location.value:undefined
    if(target){const order=await ordersApi.read(target.lineId);if(alive&&ticket===generation){rows.value=[order];total.value=1;page.value=1;selected.value=order;costView.value=target.costView??'issues'}return}
    const result=await ordersApi.list(nextPage,query.value);if(alive&&ticket===generation){rows.value=result.data;page.value=result.page;total.value=result.total}
  }catch(e){if(alive&&ticket===generation){rows.value=[];error.value=errorMessage(e)}}finally{if(alive&&ticket===generation)loading.value=false}
}
function select(order:CuttingOrder){if(!loading.value&&discard())selected.value=order}
onMounted(()=>void load(1,false,true))
</script>
<template>
  <section class="cutting-page cutting-master">
    <CuttingLocationNotice :location="location" :selected-id="selected?.line_id" />
    <PageHeader :title="workspace.title" description="按真实耗用核对本厂、外发材料费用，确认完工及在制归属，追溯原批次成本。" />
    <CuttingSubnav v-model="costView" :items="costTabs" label="物料费用工作视图" />
    <p v-if="error" role="alert" class="cutting-error">{{error}}</p><p v-if="loading" role="status">正在读取费用工作区…</p>
    <p v-if="access&&!access.enabled" class="cutting-notice">实际材料费用尚未启用，当前不能录入或计价。</p>
    <p v-else-if="access&&!access.usage_schema_ready" class="cutting-notice">P3b 需先完成 0156 显式迁移，当前未接通，不以零费用代替未知。</p>
    <p v-else-if="access&&!access.permissions.includes('cost_read')" class="cutting-notice">查看材料费用需单独授予成本查询权限；生产耗用可在物料工作区按已有耗用权限登记。</p>
    <template v-else-if="access?.enabled&&access.usage_schema_ready">
      <CuttingCostOverview v-show="costView==='orders'" @open="openCost" />
      <SectionPanel v-show="costView!=='orders'" title="选择费用核对订单" class="cutting-content-panel">
        <form class="order-toolbar" @submit.prevent="load(1)"><label>订单号／货号<input v-model="query" maxlength="80" /></label><Button type="submit" variant="outline" :disabled="loading">查询／刷新</Button></form>
        <div class="cutting-table-scroll" role="region" aria-label="费用订单，可横向滚动" tabindex="0"><table><thead><tr><th>客户</th><th>生产／订单号</th><th>货号</th><th>货名</th><th>款式分类</th><th>操作</th></tr></thead><tbody><tr v-for="order in rows" :key="order.line_id"><td>{{order.snapshot.customer_name}}</td><td>{{order.snapshot.reference_no}}</td><td>{{order.snapshot.product_no}}</td><td class="cutting-order-product-name">{{ orderProductName(order.snapshot) }}</td><td :title="unclassifiedStyleHint">{{ unclassifiedStyle }}</td><td><Button size="sm" variant="outline" :disabled="loading" @click="select(order)">查看耗用与费用</Button></td></tr></tbody></table></div>
        <p v-if="!rows.length&&!loading" class="cutting-no-records">暂无已下发裁床订单。</p>
        <nav class="order-pagination" aria-label="费用订单分页"><span>第 {{page}} 页 · 共 {{total}} 条</span><Button variant="outline" :disabled="loading||page<=1" @click="load(page-1)">上一页</Button><Button variant="outline" :disabled="loading||page*50>=total" @click="load(page+1)">下一页</Button></nav>
      </SectionPanel>
      <p v-if="selected">货名：{{ orderProductName(selected.snapshot) }} · 款式分类：<span :title="unclassifiedStyleHint">{{ unclassifiedStyle }}</span></p>
      <CuttingMaterialUsage v-if="selected?.current" ref="editor" :key="selected.line_id" :line-id="selected.line_id" :permissions="access.permissions" with-costs :view="costView" />
      <p v-else-if="selected" class="cutting-notice">请先签收订单并完成工程及领料依据。</p>
    </template>
  </section>
</template>
