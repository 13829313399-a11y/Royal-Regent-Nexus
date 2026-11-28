<script setup lang="ts">
import { computed, onBeforeUnmount, ref, watch } from 'vue'
import { reportingApi, type ProductionView } from './reportingApi'
import { errorMessage } from './api'
import { cuttingDestination } from './location'
const props=defineProps<{lineId:string;asOf?:string;compact?:boolean}>()
const data=ref<ProductionView|null>(null),error=ref('')
const reportDestination = computed(() => {
  const target = cuttingDestination(props.lineId, '', 'reporting')
  const day = data.value?.as_of
  return { ...target, query: { ...target.query, ...(day ? { day } : {}) } }
})
let generation=0,alive=true
watch(()=>[props.lineId,props.asOf] as const,async ([id,day])=>{
  const request=++generation;data.value=null;error.value=''
  try{const response=await reportingApi.read(id,day);if(alive&&request===generation)data.value=response}
  catch(e){if(alive&&request===generation)error.value=errorMessage(e)}
},{immediate:true})
onBeforeUnmount(()=>{alive=false;generation++})
</script>
<template>
  <section v-if="compact" class="cutting-compact-production">
    <p v-if="error" role="alert">实绩暂不可读取：{{error}}</p>
    <template v-else-if="data"><p class="cutting-card-value">{{data.summary.completed}} <small>／ {{data.summary.order_sets??'待核定'}} 套</small></p><div v-if="data.summary.order_sets&&data.summary.order_sets>0" class="cutting-card-meter" role="meter" aria-label="订单合格完成进度" :aria-valuenow="Math.min(100,Math.round(data.summary.completed/data.summary.order_sets*100))" aria-valuemin="0" aria-valuemax="100"><span :style="{width:Math.min(100,data.summary.completed/data.summary.order_sets*100)+'%'}" /></div><p class="cutting-muted">截至 {{data.as_of}} · 已交接 {{data.summary.handed}} 套 · 待交接 {{data.summary.completed_unhanded}} 套</p></template><p v-else role="status">正在读取实绩…</p>
  </section>
  <section v-else class="cutting-master-line"><h3>实际生产与交数</h3><p v-if="error" role="alert">{{ error }}</p>
    <p v-if="data">截至 {{ data.as_of }}：合格完成 {{ data.summary.completed }} 套；实际交数（已交接）{{ data.summary.handed }} 套；未完成 {{ data.summary.remaining??'待核定' }} 套；累计计划差额（交接−计划）{{ data.summary.plan_difference }} 套。</p>
    <RouterLink :to="reportDestination">进入每日记录查看明细</RouterLink>
  </section>
</template>
