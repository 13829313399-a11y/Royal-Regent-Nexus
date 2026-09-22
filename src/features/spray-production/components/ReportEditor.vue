<script setup lang="ts">
import { computed, reactive, ref, watch } from 'vue'
import { Plus, X, Check, Users } from '@lucide/vue'
import { Button } from '@/components/ui/button'
import { useSprayWorkspace } from '../workspace'
import { documentNo, number, type Task, type Employee, type Demand } from '../contracts'
import WorkspaceDialog from './WorkspaceDialog.vue'
const props = defineProps<{ task: Task | null }>()
const emit = defineEmits<{ close: []; saved: [] }>()
const w = useSprayWorkspace()
const form = reactive({ processed: '', good: '', hold: '0', scrap: '0', normal: '', overtime: '0', reason: '', shift: '', document_no: documentNo('日报') })
const fields = ['processed','good','hold','scrap','normal','overtime'] as const
const labels = { processed:'加工数',good:'合格数',hold:'待判数',scrap:'报废数',normal:'正班数',overtime:'加班数' }
type Counts = Record<typeof fields[number],string>
const allocations = ref<(Counts & {task_allocation_id:string; line_id:string})[]>([])
const labor = ref<{employee_id:string;hours:string;overtime_hours:string;nonproductive_hours:string;weight:string;reason:string}[]>([])
const selectedEmployee = ref(''), error = ref(''), saving = ref(false)
const employees = computed(() => w.items<Employee>('employees'))
watch(() => props.task, task => {
  if (!task) return
  Object.assign(form,{processed:'',good:'',hold:'0',scrap:'0',normal:'',overtime:'0',reason:'',shift:'',document_no:documentNo('日报')})
  allocations.value = task.allocations.map(a=>({task_allocation_id:a.id,line_id:a.line_id,processed:'0',good:'0',hold:'0',scrap:'0',normal:'0',overtime:'0'}))
  labor.value = []; error.value = ''; void w.load(['employees'])
}, { immediate:true })
watch(form, () => { if (props.task) { w.dirty.value = true; if(allocations.value.length === 1) fields.forEach(field=>{ allocations.value[0]![field] = form[field] || '0' }) } })
watch(labor, () => { if(props.task) w.dirty.value=true }, {deep:true})
const balanced = computed(() => Number(form.processed) === Number(form.good)+Number(form.hold)+Number(form.scrap) && Number(form.processed) === Number(form.normal)+Number(form.overtime) && fields.every(field=>allocations.value.reduce((sum,a)=>sum+Number(a[field]),0) === Number(form[field])))
const lineLabel = (id:string) => { const demand=w.items<Demand>('demands').find(d=>d.lines.some(l=>l.id===id)); const line=demand?.lines.find(l=>l.id===id); return `${demand?.document_no ?? id.slice(0,8)} · ${line?.item_no ?? ''} ${line?.part ?? ''}` }
function addPerson() { if(!selectedEmployee.value || labor.value.some(l=>l.employee_id===selectedEmployee.value)) return; labor.value.push({employee_id:selectedEmployee.value,hours:'',overtime_hours:'0',nonproductive_hours:'0',weight:'1',reason:''}); selectedEmployee.value='' }
async function close() { if(w.dirty.value && !(await w.confirmDiscard('放弃尚未保存的报工？'))) return; w.dirty.value=false; emit('close') }
async function save(confirm=true) {
  if(!props.task) return false
  saving.value=true; error.value=''
  try {
    if(!balanced.value) throw new Error('请先核对加工、质量、正加班及订单分摊的合计')
    if(labor.value.some(person=>!person.hours)) throw new Error('请补充每位员工的实际工时；没有作业工时可填 0 并记录原因')
    await w.command('reports',{ document_no:form.document_no,business_date:w.businessDate.value,shift:form.shift,confirm,rows:[{task_id:props.task.id,...Object.fromEntries(fields.map(field=>[field,form[field]||'0'])),reason:form.reason,allocations:allocations.value.map(({line_id,...a})=>a),labor:labor.value}]})
    emit('saved'); emit('close'); return true
  } catch(cause) { error.value=w.explain(cause); return false } finally { saving.value=false }
}
watch(()=>props.task,task=>{w.saveDraft.value=task?()=>save(false):null})
</script>
<template>
  <WorkspaceDialog :open="!!task" title="登记生产实绩" wide @close="close">
    <form id="spray-report-form" @submit.prevent="save(true)">
      <div class="spray-report-identity"><span class="spray-badge">任务 {{ task?.id.slice(0,8) }}</span><strong>{{ task?.allocations.map(a=>lineLabel(a.line_id)).join(' / ') }}</strong><span>计划 {{ number(task?.quantity) }} · 已报 {{ number(task?.reported) }}</span></div>
      <div class="spray-report-layout"><div><div class="spray-form"><label>业务日期<input v-model="w.businessDate.value" type="date" required /></label><label>实际班次<input v-model="form.shift" required placeholder="按实际班次登记" /></label></div><section class="spray-report-section"><h3>本次数量</h3><div class="spray-quantity-grid"><label v-for="field in fields" :key="field" :class="field"><span>{{ labels[field] }}</span><input v-model="form[field]" inputmode="numeric" required :aria-label="labels[field]" /></label></div><p class="spray-report-check" :class="{invalid:!balanced}"><Check :size="15" />{{ balanced ? '数量关系与订单分摊一致' : '加工 = 合格 + 待判 + 报废 = 正班 + 加班' }}</p></section>
      <section v-if="allocations.length > 1" class="spray-report-section"><h3>分摊到各订单</h3><div class="spray-table-wrap"><table class="spray-table"><thead><tr><th>订单</th><th v-for="field in fields" :key="field">{{ labels[field] }}</th></tr></thead><tbody><tr v-for="allocation in allocations" :key="allocation.task_allocation_id"><td>{{ lineLabel(allocation.line_id) }}</td><td v-for="field in fields" :key="field"><input v-model="allocation[field]" inputmode="numeric" :aria-label="lineLabel(allocation.line_id)+labels[field]" /></td></tr></tbody></table></div></section>
      <section class="spray-report-section"><h3>异常与备注</h3><textarea v-model="form.reason" class="spray-report-note" placeholder="质量待判、报废、设备停机、无产值工时等原因" :required="Number(form.hold)>0 || Number(form.scrap)>0 || Number(form.processed)===0" /></section></div>
      <aside class="spray-report-labor"><header><Users :size="18" /><h3>参与人员与真实工时</h3><span>{{ labor.length }} 人</span></header><p>多人共同完成的产品只计算一次产量。</p><div class="spray-form"><label class="wide">增加参与人员<select v-model="selectedEmployee" @change="addPerson"><option value="">选择已登记员工</option><option v-for="employee in employees.filter(e=>!labor.some(l=>l.employee_id===e.id))" :key="employee.id" :value="employee.id">{{ employee.code }} · {{ employee.name }}</option></select></label></div><article v-for="(person,index) in labor" :key="person.employee_id"><header><strong>{{ employees.find(e=>e.id===person.employee_id)?.name }}</strong><button type="button" class="spray-icon-button" aria-label="移除员工" @click="labor.splice(index,1)"><X :size="15" /></button></header><div class="spray-form"><label>实际正班小时<input v-model="person.hours" inputmode="decimal" required /></label><label>加班小时<input v-model="person.overtime_hours" inputmode="decimal" /></label><label>分摊权重<input v-model="person.weight" inputmode="decimal" /></label><label>无产值工时<input v-model="person.nonproductive_hours" inputmode="decimal" /></label><label v-if="Number(person.nonproductive_hours)>0" class="wide">无产值原因<input v-model="person.reason" required /></label></div></article><div v-if="!labor.length" class="spray-muted">尚未填写人员；报工后仍需补齐实名工时，才可核对工资。</div><div class="spray-report-wage-note"><span class="spray-badge spray-badge--amber">工资待核对</span><p>报工保留生产和工时依据。工资按已确认版本另行试算、核对。</p></div></aside></div>
      <p v-if="error" class="spray-alert" role="alert">{{ error }}</p>
    </form><template #footer><span class="spray-muted spray-report-footer-note">确认后将按实际分摊转移批次库存</span><Button variant="outline" @click="close">取消</Button><Button variant="outline" :disabled="saving" @click="save(false)">保存草稿</Button><Button type="submit" form="spray-report-form" :disabled="saving || !balanced">{{ saving?'保存中…':'确认报工' }}</Button></template>
  </WorkspaceDialog>
</template>
