<script setup lang="ts">
import { computed } from 'vue'
import type { PlanTask, PlanTaskInput, ProductionPlan } from './planning'
const props = defineProps<{ previous: ProductionPlan; tasks: PlanTaskInput[]; removedReasons?: Record<string,string> }>()
const changes = computed(() => {
  const rows: Array<{ task: string; field: string; before: string; after: string }> = []
  const old = new Map(props.previous.tasks.map(t => [t.task_id,t]))
  const fields: Array<[keyof PlanTaskInput,string]> = [['name','任务名称'],['target_sets','目标套数'],['preparation_workdays','准备工作日'],['date_basis','日期依据'],['prerequisite_required','前置工序要求'],['prerequisite_date','前置预计就绪'],['actual_issue_date','实际领料日期'],['actual_issue_reference','领料凭据'],['actual_prerequisite_date','前置实际就绪'],['actual_prerequisite_reference','前置实际凭据'],['readiness_basis','物料支持依据'],['prerequisite_basis','前置说明'],['prerequisite_change_reason','取消前置要求依据'],['resource_change_basis','执行方凭据复核依据']]
  const display = (t: PlanTaskInput, key: keyof PlanTaskInput) => {
    const value = key === 'preparation_workdays' ? t[key] ?? 3 : key === 'prerequisite_required' ? t[key] ?? !!(t.prerequisite_date || t.actual_prerequisite_date) : key === 'date_basis' ? t[key] ?? 'estimated' : t[key]
    if (key === 'date_basis') return value === 'actual' ? '实际核定' : '提前预排'
    if (key === 'prerequisite_required') return value ? '需要' : '不需要'
    return String(value ?? '') || '未填写'
  }
  for (const next of props.tasks) {
    const prior = old.get(next.task_id)
    if (!prior) { rows.push({task:next.name,field:'新增任务',before:'无',after:`${next.target_sets}套`}); continue }
    old.delete(next.task_id)
    for (const [key,label] of fields) if (display(prior,key)!==display(next,key)) rows.push({task:next.name,field:label,before:display(prior,key),after:display(next,key)})
    if (prior.resource_id!==next.resource_id || prior.resource_version!==next.resource_version) rows.push({task:next.name,field:'执行方／资料版本',before:`${prior.resource.data.name} V${prior.resource_version}`,after:`${(next as Partial<PlanTask>).resource?.data.name ?? '已更换，请核对任务选择'} V${next.resource_version}`})
    const dates = new Set([...prior.days,...next.days].map(d => d.day))
    for (const day of [...dates].sort()) {
      const a=prior.days.find(d=>d.day===day)?.sets,b=next.days.find(d=>d.day===day)?.sets
      if(a!==b) rows.push({task:next.name,field:`日计划 ${day}`,before:a===undefined?'未排':`${a}套`,after:b===undefined?'移除':`${b}套`})
    }
    const materials=new Set([...prior.materials,...next.materials].map(m=>m.row))
    for (const row of materials) {
      const a=prior.materials.find(m=>m.row===row)?.expected_date,b=next.materials.find(m=>m.row===row)?.expected_date
      if(a!==b) rows.push({task:next.name,field:`物料行${row+1}预计日期`,before:a??'未填写',after:b??'未填写'})
    }
  }
  for (const task of old.values()) rows.push({task:task.name,field:'移除任务',before:`${task.target_sets}套`,after:props.removedReasons?.[task.task_id] ?? '已移除，请核对调整原因'})
  return rows
})
</script>
<template><section class="plan-diff"><h4>与当前发布计划 V{{ previous.version }} 的差异</h4><p>核对后保存／发布新版本，原计划与首次基准保留。</p>
  <div v-if="changes.length" class="cutting-table-scroll"><table><thead><tr><th>任务</th><th>变更项</th><th>原内容</th><th>本次内容</th></tr></thead><tbody><tr v-for="(r,i) in changes" :key="i"><td>{{ r.task }}</td><td>{{ r.field }}</td><td>{{ r.before }}</td><td>{{ r.after }}</td></tr></tbody></table></div>
  <p v-else>任务配置未发生变化；订单、BOM及采购依据版本仍须核对。</p>
</section></template>
