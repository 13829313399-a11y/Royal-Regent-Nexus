<script setup lang="ts">
import { ref, watch } from 'vue'
import { Button } from '@/components/ui/button'
import { useSprayWorkspace } from '../workspace'
import { type Entity } from '../contracts'
import WorkspaceDialog from './WorkspaceDialog.vue'
const props=defineProps<{report:Entity|null}>(),emit=defineEmits<{close:[];saved:[]}>(),w=useSprayWorkspace()
const fields=['processed','good','hold','scrap','normal','overtime'] as const
const labels=['加工','合格','待判','报废','正班','加班']
type Counts=Record<typeof fields[number],string>
type DraftRow=Counts&{task_id:string;reason:string;allocations:(Counts&{task_allocation_id:string})[];labor:Record<string,unknown>[]}
const draft=ref<{document_no:string;business_date:string;shift:string;source_ref:string;rows:DraftRow[]}|null>(null),reason=ref(''),error=ref(''),busy=ref(false)
const pick=(row:Record<string,unknown>,keys:readonly string[])=>Object.fromEntries(keys.map(key=>[key,row[key]]))
watch(()=>props.report,report=>{reason.value='';error.value='';draft.value=report?{document_no:String(report.document_no),business_date:String(report.business_date),shift:String(report.shift),source_ref:String(report.source_ref??''),rows:(report.rows as Entity[]).map(row=>({...pick(row,fields),task_id:String(row.task_id),reason:String(row.reason??''),allocations:(row.allocations as Entity[]).map(a=>pick(a,[...fields,'task_allocation_id'])),labor:(row.labor as Entity[]).map(l=>pick(l,['employee_id','hours','overtime_hours','nonproductive_hours','weight','personal_quantity','reason']))} as DraftRow))}:null})
async function close(){if(w.dirty.value&&!(await w.confirmDiscard('放弃日报草稿的本次修改？')))return;w.dirty.value=false;emit('close')}
async function save(){if(!draft.value||!props.report)return;busy.value=true;error.value='';try{await w.command(`reports/${props.report.id}/amend`,{...draft.value,reason:reason.value,confirm:false},props.report.version);emit('saved');emit('close')}catch(cause){error.value=w.explain(cause)}finally{busy.value=false}}
</script>
<template>
 <WorkspaceDialog :open="!!report" title="核对日报草稿" wide @close="close"><form v-if="draft" id="spray-draft-report" class="spray-form" @input="w.dirty.value=true" @submit.prevent="save"><label>日报编号<input v-model="draft.document_no" required/></label><label>业务日期<input v-model="draft.business_date" type="date" required/></label><label>实际班次<input v-model="draft.shift" required/></label><label>修改依据<input v-model="reason" required/></label><section v-for="(row,index) in draft.rows" :key="index" class="wide"><h3>任务 {{row.task_id.slice(0,8)}}</h3><div class="spray-quantity-grid"><label v-for="(field,i) in fields" :key="field">{{labels[i]}}<input v-model="row[field]" inputmode="decimal" required/></label></div><div class="spray-table-wrap"><table class="spray-table"><thead><tr><th>订单分摊</th><th v-for="label in labels" :key="label">{{label}}</th></tr></thead><tbody><tr v-for="allocation in row.allocations" :key="allocation.task_allocation_id"><td>{{allocation.task_allocation_id.slice(0,8)}}</td><td v-for="(field,i) in fields" :key="field"><input v-model="allocation[field]" inputmode="decimal" :aria-label="`第${index+1}行分摊${labels[i]}`" required/></td></tr></tbody></table></div><label>异常与备注<textarea v-model="row.reason"/></label></section><p class="wide spray-muted">每行数量及每列分摊必须守恒。人员工时在“核对工时”中维护；本次保存仍为草稿。</p><p v-if="error" class="spray-alert wide" role="alert">{{error}}</p></form><template #footer><Button variant="outline" @click="close">返回</Button><Button type="submit" form="spray-draft-report" :disabled="busy">保存草稿修改</Button></template></WorkspaceDialog>
</template>
