<script setup lang="ts">
import { watchCuttingWorkspace } from './workspaceRefresh'
import {onBeforeUnmount,ref,watch} from 'vue'
import {workspaceApi,type PlanningView} from './workspaceApi'
import {errorMessage} from './api'
import CuttingMetrics from './CuttingMetrics.vue'
import {Button} from '@/components/ui/button'
const props=defineProps<{query:string;status:string;planStatus?:string;refresh?:number}>()
const result=ref<PlanningView>(),error=ref(''),busy=ref(false)
let generation=0,alive=true
async function load(){const ticket=++generation;result.value=undefined;error.value='';busy.value=true
  try{const value=await workspaceApi.planning({q:props.query,status:props.status||undefined,plan_status:props.planStatus||undefined});if(alive&&ticket===generation)result.value=value}
  catch(e){if(alive&&ticket===generation)error.value=errorMessage(e)}finally{if(alive&&ticket===generation)busy.value=false}}
watch(()=>[props.query,props.status,props.planStatus,props.refresh],()=>void load(),{immediate:true})
onBeforeUnmount(()=>{alive=false;generation++})
watchCuttingWorkspace(()=>void load())
</script>
<template>
  <div class="cutting-overview">
    <CuttingMetrics :items="[
      {label:'总订单数量',value:result?.stats.total??'—',unit:'笔',hint:'当前筛选内有效下发订单行'},
      {label:'已排期订单数量',value:result?.stats.scheduled??'—',unit:'笔',hint:`有效已发布且有日计划；部分排期 ${result?.stats.partial??'—'} 笔`},
      {label:'未排期订单数量',value:result?.stats.unscheduled??'—',unit:'笔',hint:`含仅草稿或已失效；待复核 ${result?.stats.review??'—'} 笔`},
    ]" />
    <p class="cutting-muted">总数＝已排期＋未排期，按订单行去重，统计不受当前页限制；取消订单不计入上述卡片，仍可在下方台账处理历史通知。</p>
    <p v-if="busy" role="status">正在核对排期统计…</p><p v-if="error" role="alert">{{error}} <Button variant="outline" size="sm" @click="load">重试统计</Button></p>
  </div>
</template>
