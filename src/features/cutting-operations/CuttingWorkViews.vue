<script setup lang="ts">
import { inject } from 'vue'
import { RouterLink, routeLocationKey } from 'vue-router'
import { CUTTING_BASE, CUTTING_FACTORY } from './navigation'
defineProps<{ active:'daily'|'planning'|'history' }>()
const views=[{id:'daily',path:'dashboard',label:'当日任务'},{id:'planning',path:'planning',label:'订单与排期'},{id:'history',path:'reporting',label:'历史记录'}]
const route=inject(routeLocationKey,undefined)
function target(view:typeof views[number]) {
  const query:Record<string,string>={factory:CUTTING_FACTORY}
  for(const key of ['day','task_day','month','line_id','focus_kind','focus_id','task_query_day','task_q','task_execution','task_scope']){
    const value=route?.query[key]
    if(typeof value==='string')query[key]=value
  }
  if(view.id==='daily'){
    query.day=query.task_day??query.day??''
    for(const key of ['line_id','focus_kind','focus_id','task_query_day','month'])delete query[key]
    if(!query.day)delete query.day
  }
  if(view.id==='history')query.reporting_view='records'
  return {path:`${CUTTING_BASE}/${view.path}`,query}
}
</script>
<template>
  <nav class="cutting-work-views" aria-label="生产工作台视图"><RouterLink v-for="view in views" :key="view.id" :to="target(view)" :aria-current="active===view.id?'page':undefined">{{view.label}}</RouterLink></nav>
</template>
