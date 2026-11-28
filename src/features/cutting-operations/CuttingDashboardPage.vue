<script setup lang="ts">
import { computed, inject, onBeforeUnmount, onMounted, ref, useId } from 'vue'
import { routeLocationKey, routerKey, RouterLink, type LocationQueryRaw } from 'vue-router'
import { Button } from '@/components/ui/button'
import CuttingTaskBoard from './CuttingTaskBoard.vue'
import CuttingVisualCard from './CuttingVisualCard.vue'
import CuttingProductionSummary from './CuttingProductionSummary.vue'
import CuttingWorkViews from './CuttingWorkViews.vue'
import { cuttingApi, errorMessage, type Access } from './api'
import { workspaceApi, businessDay, type PlanningView } from './workspaceApi'
import { cuttingDestination, cuttingQueryDay, type TaskFilters } from './location'
import { orderProductName } from './orderDisplay'
import { watchCuttingWorkspace } from './workspaceRefresh'
import { CUTTING_BASE, CUTTING_FACTORY } from './navigation'
const route=inject(routeLocationKey,undefined)
const router=inject(routerKey,undefined)
const appliedTaskDay=ref<string>()
const day=computed(()=>appliedTaskDay.value??cuttingQueryDay(route?.query.day)??businessDay())
function taskLoaded(filters:TaskFilters){
  appliedTaskDay.value=filters.day
  if(!router||!route)return
  const query:LocationQueryRaw={...route.query,day:filters.day,task_q:filters.q||undefined,task_execution:filters.execution||undefined,task_scope:filters.scope==='daily'?undefined:filters.scope}
  delete query.task_day;delete query.task_query_day
  const target={path:route.path,query}
  if(router.resolve(target).fullPath!==route.fullPath)void router.replace(target)
}
const id=`cutting-workbench-${useId()}`
const result=ref<PlanningView>(),access=ref<Access>(),error=ref(''),busy=ref(false),query=ref(''),applied=ref('')
let generation=0,alive=true
async function load(apply=false){
  const target=apply?query.value:applied.value,ticket=++generation
  busy.value=true;error.value=''
  try{
    const rights=await cuttingApi.access();if(!alive||ticket!==generation)return
    access.value=rights
    if(!rights.enabled||!rights.orders_schema_ready){result.value=undefined;return}
    const value=await workspaceApi.planning({page:1,q:target})
    if(alive&&ticket===generation){result.value=value;applied.value=target}
  }catch(e){if(alive&&ticket===generation){error.value=errorMessage(e);result.value=undefined
    const status=(e as {response?:{status?:number}}).response?.status
    if(status===401||status===403){access.value=undefined;window.dispatchEvent(new Event('cutting-authorization-recheck'))}
  }}
  finally{if(alive&&ticket===generation)busy.value=false}
}
onMounted(()=>void load());onBeforeUnmount(()=>{alive=false;generation++})
watchCuttingWorkspace(()=>void load())
</script>
<template>
  <section class="cutting-page cutting-review-page cutting-workbench">
    <header class="cutting-page-heading"><div><h1>生产工作台</h1><p>订单进度、生产排期与每日记录，一处办理。</p></div></header>
    <CuttingWorkViews active="daily" />
    <p v-if="error" class="cutting-error" role="alert">{{error}} <button type="button" class="cutting-detail-link" :disabled="busy" @click="load()">重新读取订单进度</button></p>
    <p v-if="access&&!access.enabled" class="cutting-notice">生产工作台尚未启用，请联系授权负责人。</p>
    <template v-if="access?.enabled&&access.orders_schema_ready">
      <div class="cutting-workbench-summary" aria-label="订单排期汇总"><span>总订单 <strong>{{result?.stats.total??'—'}}</strong> 笔</span><span>已排期 <strong>{{result?.stats.scheduled??'—'}}</strong> 笔</span><span>未排期 <strong>{{result?.stats.unscheduled??'—'}}</strong> 笔</span><span>部分排期 <strong>{{result?.stats.partial??'—'}}</strong> 笔</span></div>
      <div class="cutting-workbench-body">
      <section aria-label="订单进度" class="cutting-workbench-orders">
        <div class="cutting-card-section-heading"><h2>订单进度</h2><form class="order-toolbar" @submit.prevent="load(true)"><label :for="id">订单／货号<input :id="id" v-model="query" name="workbench_order_q" maxlength="80" /></label><Button type="submit" :disabled="busy">查询订单</Button></form><RouterLink class="cutting-detail-link" :to="{path:`${CUTTING_BASE}/planning`,query:{factory:CUTTING_FACTORY}}">全部订单 →</RouterLink></div>
        <p v-if="busy" role="status">正在读取订单进度…</p><p v-if="query!==applied" role="status" class="cutting-muted">订单筛选尚未应用。</p>
        <div class="cutting-visual-grid">
          <CuttingVisualCard v-for="row in result?.data.slice(0,3)" :key="row.line_id" :title="String(row.snapshot.reference_no??'未填写订单号')" :eyebrow="`${row.snapshot.customer_name??''} · ${orderProductName(row.snapshot)}`" :status="row.needs_receipt?'待确认':row.planning_summary?.published_stale?'排期待复核':row.planning_summary?.published_version?'计划已发布':'待排期'" :to="{...cuttingDestination(row.line_id,day.slice(0,7),'planning'),query:{...cuttingDestination(row.line_id,day.slice(0,7),'planning').query,day,task_day:day}}">
            <p>订单 {{row.snapshot.quantity??'—'}} {{row.snapshot.order_unit??'原单单位'}} · 工程目标 {{row.current?.data.target_sets??'待核定'}} <span v-if="row.current?.data.target_sets!=null">套</span></p>
            <CuttingProductionSummary v-if="access.reporting_schema_ready&&row.current" :line-id="row.line_id" :as-of="day" compact />
          </CuttingVisualCard>
        </div>
        <p v-if="result&&!result.data.length" class="cutting-no-records">{{applied?'当前筛选无匹配订单，请清除筛选后查询。':'暂无已下发裁床订单。'}}</p>
      </section>
      <CuttingTaskBoard cards reporting @loaded-query="taskLoaded" />
      </div>
    </template>
  </section>
</template>
