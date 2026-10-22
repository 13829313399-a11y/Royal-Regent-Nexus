<script setup lang="ts">
import { nextTick, onBeforeUnmount, ref, watch } from 'vue'
import { X, Plus, Trash2 } from '@lucide/vue'
import { createRandomUuid } from '@/lib/randomUuid'
import { entities, str, type Entity } from '../contracts'
import CollectionFooter from './CollectionFooter.vue'
import { useUvWorkspace, UvError } from '../workspace'
import { useUvPresence } from '../composables/useUvPresence'
import { useUvReturnFocus } from '../composables/useUvReturnFocus'
import { useUvScrollLock } from '../composables/useUvScrollLock'
const props=defineProps<{run:Entity|null}>(),emit=defineEmits<{close:[];saved:[]}>(),w=useUvWorkspace(),dialog=ref<HTMLDialogElement|null>(null)
const presentation=useUvPresence(dialog),displayedRun=ref<Entity|null>(null)
const focus=useUvReturnFocus(dialog)
useUvScrollLock(()=>presentation.present.value)
const rows=ref<{key:string;task_id:string;batch_id:string;pass_index:number;slots:string;full_boards:number;tail_pieces:number;share:string}[]>([])
const evidence=ref(''),error=ref(''),saving=ref(false),uncertain=ref(false),conflict=ref(false),fields=ref<Record<string,string>>({})
const evidenceError=()=>fields.value['body.evidence']??fields.value.evidence
const fieldError=(index:number,name:string)=>fields.value['body.allocations.'+index+'.'+name]??fields.value['allocations.'+index+'.'+name]
let op=createRandomUuid(),submitted:Record<string,unknown>|null=null,session=0
function add(){rows.value.push({key:createRandomUuid(),task_id:'',batch_id:'',pass_index:1,slots:'',full_boards:0,tail_pieces:0,share:rows.value.length?'0':'1'})}
function clear(){dialog.value?.close();focus.restore();displayedRun.value=null;rows.value=[];evidence.value='';error.value='';fields.value={};saving.value=false;submitted=null;uncertain.value=false}
watch(()=>props.run?.id,async()=>{
  const value=props.run
  const version=++session
  if(!value){presentation.close(clear);return}
  if(presentation.present.value&&presentation.phase.value==='closing'&&displayedRun.value?.id===value.id){presentation.open();return}
  displayedRun.value={...value};rows.value=[];add();error.value='';fields.value={};evidence.value='';uncertain.value=false;conflict.value=false;saving.value=false;submitted=null;op=createRandomUuid()
  focus.capture();presentation.open();await nextTick();if(version!==session)return
  if(!dialog.value?.open)dialog.value?.showModal()
  if(!dialog.value?.contains(document.activeElement))dialog.value?.querySelector<HTMLElement>('select:not(:disabled),input:not(:disabled),button:not(:disabled)')?.focus()
  try{await w.load(['tasks','batches'])}catch(cause){if(version===session)error.value=w.explain(cause)}
},{immediate:true})
watch(w.contextVersion,()=>{session++;presentation.close(clear,true);emit('close')},{flush:'sync'})
onBeforeUnmount(()=>{session++;dialog.value?.close();focus.restore()})
async function submit(){
  if(saving.value||!displayedRun.value||presentation.phase.value==='closing'||!w.can('production_write'))return
  const version=session,run=displayedRun.value;saving.value=true;error.value='';fields.value={};conflict.value=false
  try{
    if(!uncertain.value)submitted={expected_version:run.version,evidence:evidence.value,allocations:rows.value.map(({key:_,...row})=>({...row,slots:row.slots.split(/[,，\s]+/).filter(Boolean).map(Number)}))}
    await w.command('runs/'+run.id+'/match',submitted!,op)
    if(version===session)emit('saved')
  }catch(cause){
    if(version!==session)return
    error.value=w.explain(cause);conflict.value=cause instanceof UvError&&cause.status===409
    if(cause instanceof UvError)fields.value=cause.fields
    uncertain.value=!(cause instanceof UvError)||cause.status>=500||cause.status===0
    if(!uncertain.value)op=createRandomUuid()
  }finally{if(version===session){saving.value=false;await nextTick();if(version===session)dialog.value?.querySelector<HTMLElement>('[aria-invalid="true"]')?.focus()}}
}
</script>
<template><dialog ref="dialog" class="uv-dialog uv-wide-dialog" :data-phase="presentation.phase.value" :aria-busy="saving" aria-labelledby="uv-match-title" @cancel.prevent="!saving&&emit('close')"><form v-if="displayedRun" @submit.prevent="submit"><header><div><span class="uv-context">运行证据 · {{str(displayedRun??undefined,'native_job_id')}}</span><h2 id="uv-match-title">核对任务归属</h2></div><button type="button" class="uv-icon-button" aria-label="关闭运行核对" :disabled="saving" @click="emit('close')"><X :size="20"/></button></header><div class="uv-dialog-body"><p class="uv-notice">拼版分配按遍次检查槽位互斥，份额总和必须为 1。板数 × 槽位数 + 尾板件数只形成加工参考，不自动确认良品。</p><CollectionFooter name="tasks"/><fieldset :disabled="saving||uncertain" class="uv-match-fields"><section v-for="(row,index) in rows" :key="row.key" class="uv-allocation-row"><div class="uv-form-grid"><label><span>任务</span><select v-model="row.task_id" :aria-invalid="!!fieldError(index,'task_id')" :aria-describedby="fieldError(index,'task_id')?row.key+'-errors':undefined" required @change="row.batch_id='' "><option value="">请选择任务</option><option v-for="task in w.items('tasks')" :key="task.id" :value="task.id">{{str(task,'code')}}</option></select></label><label><span>实体批次</span><select v-model="row.batch_id" :aria-invalid="!!fieldError(index,'batch_id')" :aria-describedby="fieldError(index,'batch_id')?row.key+'-errors':undefined" required><option value="">请选择批次</option><option v-for="batch in entities(w.items('tasks').find(task=>task.id===row.task_id)?.batches)" :key="batch.id" :value="batch.id">{{batch.id.slice(0,8)}} · {{batch.quantity}} pcs</option></select></label><label><span>工序遍次</span><input v-model.number="row.pass_index" :aria-invalid="!!fieldError(index,'pass_index')" :aria-describedby="fieldError(index,'pass_index')?row.key+'-errors':undefined" type="number" min="1" required/></label><label><span>槽位编号（逗号分隔）</span><input v-model="row.slots" :aria-invalid="!!fieldError(index,'slots')" :aria-describedby="fieldError(index,'slots')?row.key+'-errors':undefined" required placeholder="1,2,3"/></label><label><span>完整板数</span><input v-model.number="row.full_boards" :aria-invalid="!!fieldError(index,'full_boards')" :aria-describedby="fieldError(index,'full_boards')?row.key+'-errors':undefined" type="number" min="0" required/></label><label><span>尾板件数（pcs）</span><input v-model.number="row.tail_pieces" :aria-invalid="!!fieldError(index,'tail_pieces')" :aria-describedby="fieldError(index,'tail_pieces')?row.key+'-errors':undefined" type="number" min="0" required/></label><label><span>分摊份额（0–1）</span><input v-model="row.share" :aria-invalid="!!fieldError(index,'share')" :aria-describedby="fieldError(index,'share')?row.key+'-errors':undefined" inputmode="decimal" required/></label></div><p :id="row.key+'-errors'" v-if="['task_id','batch_id','pass_index','slots','full_boards','tail_pieces','share'].some(key=>fieldError(index,key))" class="uv-field-error">{{['task_id','batch_id','pass_index','slots','full_boards','tail_pieces','share'].map(key=>fieldError(index,key)).filter(Boolean).join('；')}}</p><button v-if="rows.length>1" type="button" class="uv-link" @click="rows.splice(index,1)"><Trash2 :size="14"/>删除此分配</button></section><button type="button" class="uv-button" @click="add"><Plus :size="15"/>追加拼版任务</button><label class="uv-block-label">核对依据<textarea v-model="evidence" :aria-invalid="!!evidenceError()" :aria-describedby="evidenceError()?'uv-match-evidence-error':undefined" required rows="3"/><small v-if="evidenceError()" id="uv-match-evidence-error" class="uv-field-error">{{evidenceError()}}</small></label></fieldset><p v-if="error" class="uv-error" role="alert">{{error}}</p><p v-if="conflict" class="uv-notice">记录版本已变化，输入已保留。请核对最新记录后重新确认；不会自动覆盖修改。</p><p v-if="uncertain" class="uv-notice">请求结果不确定。已锁定输入，重试沿用原操作编号。</p></div><footer><button type="button" class="uv-button" :disabled="saving" @click="emit('close')">取消</button><button class="uv-button primary" :disabled="saving||!w.can('production_write')">{{saving?'保存中…':uncertain?'重试同一操作':'确认归属'}}</button></footer></form></dialog></template>
