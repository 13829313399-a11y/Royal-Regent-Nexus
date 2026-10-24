<script setup lang="ts">
import { watchCuttingWorkspace } from './workspaceRefresh'
import { computed, inject, onBeforeUnmount, onMounted, ref, watch } from 'vue'
import { RouterLink, routeLocationKey } from 'vue-router'
import { Button } from '@/components/ui/button'
import SectionPanel from '@/components/common/SectionPanel.vue'
import StatusPill from '@/components/common/StatusPill.vue'
import CuttingMetrics from './CuttingMetrics.vue'
import CuttingSubnav from './CuttingSubnav.vue'
import { workspaceApi,businessDay,type TaskView } from './workspaceApi'
import { errorMessage } from './api'
import { cuttingDestination } from './location'
const props=defineProps<{reporting?:boolean}>()
const route=inject(routeLocationKey,undefined)
function linkedDay(){const value=route?.query.day;return route?.query.factory==='huakang-c'&&typeof value==='string'&&/^\d{4}-\d{2}-\d{2}$/.test(value)&&Number.isFinite(Date.parse(value))&&new Date(value).toISOString().slice(0,10)===value?value:businessDay()}
const day=ref(linkedDay()),query=ref(''),execution=ref(''),scope=ref('daily'),result=ref<TaskView>(),busy=ref(false),error=ref('')
const applied=ref({day:day.value,q:'',execution:'',scope:'daily'})
type TaskQuery=typeof applied.value & {page:number}
const failedQuery=ref<TaskQuery>(),currentPage=ref(1)
const unapplied=computed(()=>day.value!==applied.value.day||query.value!==applied.value.q||execution.value!==applied.value.execution)
let generation=0,alive=true
const tabs=computed(()=>props.reporting?[
  {id:'daily',label:'每日任务'},{id:'reported',label:'已填报任务'},{id:'unreported',label:'待填任务'},{id:'history',label:'计划外与历史实绩'},{id:'abnormal',label:'异常待办'},
]:[{id:'daily',label:'当日生产任务'},{id:'abnormal',label:'异常任务'},{id:'history',label:'历史与计划外实绩'}])
const viewLabel=(value:string)=>tabs.value.find(tab=>tab.id===value)?.label??value
const metrics=computed(()=>{const s=result.value?.stats;return props.reporting?[
  {label:'当日应报任务',value:s?.tasks??'—',unit:'项'},
  {label:'已填报任务',value:s?.reported??'—',unit:'项',hint:'已有生效日报，包含明确填零'},
  {label:'未填报任务',value:s?.unreported??'—',unit:'项',hint:'保存草稿不计入已填报'},
]:[
  {label:'当日生产任务',value:s?.tasks??'—',unit:'项'},
  {label:'当日计划',value:s?.planned??'—',unit:'套'},
  {label:'合格完成 / 交接',value:s?`${s.completed} / ${s.handed}`:'—',unit:'套',hint:'含当日历史与计划外有效实绩'},
  {label:'待处理异常',value:s?.abnormal??'—',unit:'项',hint:'同一任务多项异常仅计一次'},
]})
function exceptionLink(row:TaskView['data'][number],reason:string) {
  const date=result.value?.day??day.value
  const isReport=reason==='外发收回待验收'||reason==='已结束业务日未填报'
  const target=cuttingDestination(row.line_id,date.slice(0,7),isReport?'reporting':'planning','task',row.task_id)
  return {...target,query:{...target.query,day:date,...(isReport?{reporting_view:reason==='外发收回待验收'?'external':'records'}:{})}}
}
const exceptionLabels:Record<string,string>={'外发收回待验收':'收回与验收','已结束业务日未填报':'补填当日日报','计划依据已变更':'复核计划','计划已逾期未完成':'核对逾期计划','物料及前置条件待实际核定':'核定执行条件'}
async function load(page=1,apply=false){
  if(apply){applied.value={day:day.value,q:query.value,execution:execution.value,scope:scope.value};page=1}
  await read({...applied.value,page})
}
async function read(request:TaskQuery){
  const ticket=++generation;busy.value=true;error.value='';result.value=undefined;failedQuery.value=undefined;currentPage.value=request.page
  try{const value=await workspaceApi.tasks(request);if(alive&&ticket===generation)result.value=value}
  catch(e){if(alive&&ticket===generation){
    error.value=errorMessage(e)
    const status=(e as {response?:{status:number}}).response?.status
    if(status!==401&&status!==403)failedQuery.value={...request}
  }}
  finally{if(alive&&ticket===generation)busy.value=false}
}
function retry(){if(failedQuery.value&&!busy.value)void read({...failedQuery.value})}
function change(value:string){scope.value=value;applied.value={...applied.value,scope:value};void load(1)}
function resetFilters(){query.value='';execution.value='';applied.value={...applied.value,q:'',execution:''};void load(1)}
onMounted(()=>void load())
watch(()=>route?.query.day,()=>{day.value=linkedDay();applied.value={...applied.value,day:day.value};void load(1)})
onBeforeUnmount(()=>{alive=false;generation++})
watchCuttingWorkspace(()=>void load(currentPage.value))
</script>
<template>
  <div class="cutting-overview">
    <CuttingMetrics :items="metrics" />
    <SectionPanel :title="reporting?'每日任务与填报进度':'生产任务与异常跟进'" class="cutting-content-panel">
      <form class="order-toolbar" @submit.prevent="load(1,true)">
        <label>业务日期<input v-model="day" type="date" required /></label>
        <label>订单号／货号<input v-model="query" maxlength="80" placeholder="查询全部匹配订单" /></label>
        <label>执行方<select v-model="execution"><option value="">本厂与外发</option><option value="internal">本厂</option><option value="outsourced">外发</option></select></label>
        <Button type="submit" :disabled="busy">查询</Button>
        <Button type="button" variant="outline" :disabled="busy" @click="load(currentPage)">刷新当前结果</Button>
        <Button type="button" variant="outline" :disabled="busy" @click="resetFilters">清除订单／执行方筛选</Button>
      </form>
      <p v-if="unapplied" class="cutting-muted" role="status">筛选有未查询的修改，当前结果仍按上次查询条件展示。</p>
      <p class="cutting-muted">当前查询日期：{{applied.day}}。订单号／货号：{{applied.q||'全部'}}；执行方：{{applied.execution==='internal'?'本厂':applied.execution==='outsourced'?'外发':'本厂与外发'}}；视图：{{viewLabel(applied.scope)}}。查询应用当前输入；切换任务视图、翻页及刷新不提交未查询的日期、订单或执行方条件。</p>
      <CuttingSubnav :model-value="scope" :items="tabs" @update:model-value="change" />
      <p v-if="busy" role="status">正在核对有效计划与生产实绩…</p>
      <p v-if="error" role="alert">{{error}} <Button v-if="failedQuery" type="button" variant="outline" :disabled="busy" @click="retry">按原条件重试（第 {{failedQuery.page}} 页）</Button></p>
      <p v-if="failedQuery" class="cutting-muted">重试目标：{{failedQuery.day}}；订单号／货号 {{failedQuery.q||'全部'}}；执行方 {{failedQuery.execution==='internal'?'本厂':failedQuery.execution==='outsourced'?'外发':'本厂与外发'}}；{{viewLabel(failedQuery.scope)}}，第 {{failedQuery.page}} 页。保留尚未查询的新输入，重试不提交业务记录。</p>
      <p class="cutting-muted">应报任务以当日有效发布日计划为准；外厂自报不计合格完成。实收条件待核定不直接判为缺料。</p>
      <div class="cutting-table-scroll" tabindex="0" role="region" aria-label="生产任务列表"><table>
        <thead><tr><th>客户／订单</th><th>货号／任务</th><th>执行方</th><th>当日计划</th><th>合格完成／交接</th><th>填报状态</th><th>异常与核对</th><th>操作</th></tr></thead>
        <tbody><tr v-for="row in result?.data" :key="row.line_id+row.task_id">
          <td>{{row.customer}}<br />{{row.order_no}}</td><td>{{row.item_no}}<br />{{row.task_name}}</td>
          <td>{{row.resource_name}}<br />{{row.execution==='internal'?'本厂':'外发'}}</td>
          <td>{{row.planned}} 套</td><td>{{row.day_completed}} / {{row.day_handed}} 套</td>
          <td><StatusPill :label="row.reported?'已填报':row.planned?'未填报':'计划外实绩'" compact /></td>
          <td><p v-for="reason in row.reasons" :key="reason">{{reason}}</p><span v-if="!row.reasons.length">—</span></td>
          <td><div class="cutting-master-actions">
            <Button as-child size="sm" variant="outline"><RouterLink :to="{...cuttingDestination(row.line_id,(result?.day??day).slice(0,7),'reporting','task',row.task_id),query:{...cuttingDestination(row.line_id,(result?.day??day).slice(0,7),'reporting','task',row.task_id).query,day:result?.day??day}}">填数／查看</RouterLink></Button>
            <Button v-for="reason in row.reasons" :key="reason" as-child size="sm" variant="outline"><RouterLink :to="exceptionLink(row,reason)">{{exceptionLabels[reason]??'处理异常'}}</RouterLink></Button>
          </div></td>
        </tr></tbody>
      </table></div>
      <p v-if="result&&!result.total" class="cutting-no-records">当前筛选范围暂无任务。</p>
      <nav v-if="result" class="order-pagination" aria-label="生产任务分页"><span>第 {{result.page}} 页 · 共 {{result.total}} 项</span><Button variant="outline" :disabled="busy||result.page<=1" @click="load(result.page-1)">上一页</Button><Button variant="outline" :disabled="busy||result.page*50>=result.total" @click="load(result.page+1)">下一页</Button></nav>
    </SectionPanel>
  </div>
</template>
