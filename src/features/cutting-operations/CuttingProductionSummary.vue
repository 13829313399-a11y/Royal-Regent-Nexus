<script setup lang="ts">
import { computed, onBeforeUnmount, ref, watch } from 'vue'
import { reportingApi, type ProductionView } from './reportingApi'
import { errorMessage } from './api'
import { cuttingDestination } from './location'
const props=defineProps<{lineId:string}>()
const data=ref<ProductionView|null>(null),error=ref('')
const reportDestination = computed(() => {
  const target = cuttingDestination(props.lineId, '', 'reporting')
  const day = data.value?.as_of
  return { ...target, query: { ...target.query, ...(day ? { day } : {}) } }
})
let generation=0,alive=true
watch(()=>props.lineId,async id=>{
  const request=++generation;data.value=null;error.value=''
  try{const response=await reportingApi.read(id);if(alive&&request===generation)data.value=response}
  catch(e){if(alive&&request===generation)error.value=errorMessage(e)}
},{immediate:true})
onBeforeUnmount(()=>{alive=false;generation++})
</script>
<template>
  <section class="cutting-master-line"><h3>实际生产与交数</h3><p v-if="error" role="alert">{{ error }}</p>
    <p v-if="data">截至 {{ data.as_of }}：合格完成 {{ data.summary.completed }} 套；实际交数（已交接）{{ data.summary.handed }} 套；未完成 {{ data.summary.remaining??'待核定' }} 套；累计计划差额（交接−计划）{{ data.summary.plan_difference }} 套。</p>
    <RouterLink :to="reportDestination">进入每日填数查看明细</RouterLink>
  </section>
</template>
