<script setup lang="ts">
import { ref, watch, onBeforeUnmount } from 'vue'
import { X } from '@lucide/vue'
import { useSprayWorkspace } from '../workspace'
import { usePassportPanel } from '../usePassportPanel'
import { number, dateTime, stateLabel, type Task } from '../contracts'

type TaskRecord = Task & {
  step: { name:string; input_unit:string; output_unit:string; output_ratio:string }
  resource: { name:string; code:string }
  allocations: (Task['allocations'][number] & {demand_id:string; document_no:string; item_no:string; part:string; unit:string})[]
  reports: {id:string; document_no:string; business_date:string; processed:string; good:string; hold:string; scrap:string}[]
  reports_total:number
}
const w=useSprayWorkspace(), {panel,focus}=usePassportPanel(w.taskPassportId)
const task=ref<TaskRecord|null>(null), failed=ref(''), loading=ref(false), asOf=ref('')
let sequence=0
async function load(refocus=false) {
  const id=w.taskPassportId.value, factory=w.factory.value, context=w.contextVersion.value, current=++sequence
  task.value=null; failed.value=''; asOf.value=''; w.verifiedTaskId.value=null
  if(id)w.assistantRecord.value=null
  if (!id || !w.ready.value) {loading.value=false;return}
  loading.value=true
  const valid=()=>current===sequence && context===w.contextVersion.value && id===w.taskPassportId.value && w.ready.value
  try {
    const response=await w.query<TaskRecord>('tasks/'+encodeURIComponent(id),{},'task-passport')
    if (!valid()) return
    if(response.data.id!==id || response.data.factory_id!==factory) throw new Error('返回的任务与所选来源不一致，请重试。')
    task.value=response.data; asOf.value=response.meta.as_of; w.verifiedTaskId.value=id
    w.assistantRecord.value={id,kind:'task',label:response.data.step.name+' · '+id.slice(0,8)}
  } catch(cause) {if(valid()) failed.value=w.explain(cause)}
  finally {if(valid()){loading.value=false;if(refocus)void focus()}}
}
watch([w.taskPassportId,w.ready,w.contextVersion],()=>void load(),{immediate:true,flush:'sync'})
onBeforeUnmount(()=>{sequence++;task.value=null;w.verifiedTaskId.value=null})
</script>
<template>
  <dialog ref="panel" class="spray-passport spray-workspace" tabindex="-1" aria-label="喷油任务档案" :aria-busy="loading" @keydown.esc.prevent="w.taskPassportId.value=null" @cancel.prevent="w.taskPassportId.value=null">
    <header><span class="spray-eyebrow">喷油任务档案 · 只读</span><button class="spray-icon-button" aria-label="关闭喷油任务档案" @click="w.taskPassportId.value=null"><X :size="18" /></button></header>
    <div v-if="failed" class="spray-alert" role="alert"><p>{{failed}}</p><button class="spray-secondary" @click="load(true)">重试读取任务</button></div>
    <p v-else-if="loading" class="spray-empty" role="status">正在读取原任务…</p>
    <template v-else-if="task">
      <h2>{{task.step.name}}</h2><p class="spray-muted">{{task.resource.name}} · {{task.resource.code}}</p>
      <dl class="spray-passport__facts"><div><dt>任务状态</dt><dd>{{stateLabel[task.status]??task.status}}</dd></div><div><dt>记录版本</dt><dd>V{{task.version}}</dd></div><div><dt>计划开始</dt><dd>{{dateTime(task.start_at)}}</dd></div><div><dt>计划结束</dt><dd>{{dateTime(task.end_at)}}</dd></div><div><dt>源记录更新</dt><dd>{{dateTime(task.updated_at)}}</dd></div><div><dt>本次读取</dt><dd>{{dateTime(asOf)}}（上海）</dd></div></dl>
      <div class="spray-passport__numbers"><div><small>工序任务量</small><strong>{{number(task.quantity)}} <em>{{task.step.input_unit}}</em></strong></div><div><small>已确认处理量</small><strong>{{number(task.reported)}} <em>{{task.step.input_unit}}</em></strong></div></div>
      <p class="spray-muted spray-source-note">这是本工序工作量，多工序和返工不能累加作为合格成品。输出按确认比例 {{task.step.output_ratio}} 换算为{{task.step.output_unit}}。</p>
      <section><h3>需求与实体分配</h3><p class="spray-muted">合并任务包含以下全部分配。</p><article v-for="allocation in task.allocations" :key="allocation.id" class="spray-source-allocation"><button class="spray-text-button" @click="w.passportId.value=allocation.demand_id">{{allocation.document_no}} · {{allocation.item_no}} / {{allocation.part}}</button><p>分配 {{number(allocation.quantity)}} {{allocation.unit}} · 已消耗 {{number(allocation.consumed)}} {{allocation.unit}}</p></article></section>
      <section><h3>已确认日报 <small>{{task.reports.length}} / {{task.reports_total}}</small></h3><p class="spray-muted">仅列最近25条未冲销记录，以下数量均为{{task.step.input_unit}}投入，日报合格不一定是最终成品。</p><p v-if="!task.reports.length" class="spray-empty">尚无已确认日报。</p><article v-for="report in task.reports" :key="report.id" class="spray-source-allocation"><strong>{{report.document_no}}</strong><p>{{report.business_date}} · 处理 {{number(report.processed)}}</p><p>合格 {{number(report.good)}} · 待判 {{number(report.hold)}} · 报废 {{number(report.scrap)}}</p></article></section>
      <p v-if="task.note" class="spray-source-note">{{task.note}}</p>
    </template>
  </dialog>
</template>
