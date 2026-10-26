<script setup lang="ts">
import { computed, nextTick, onBeforeUnmount, ref, useId, watch } from 'vue'
import { X, Check, AlertTriangle } from '@lucide/vue'
import { createRandomUuid } from '@/lib/randomUuid'
import { forms, type FormField } from '../forms'
import CollectionFooter from './CollectionFooter.vue'
import { num, str, today, utcInput, type Entity } from '../contracts'
import { useUvWorkspace, UvError } from '../workspace'
import { useUvPresence } from '../composables/useUvPresence'
import { useUvReturnFocus } from '../composables/useUvReturnFocus'
import { useUvScrollLock } from '../composables/useUvScrollLock'
import { useUvNavigationGuard } from '../navigationGuard'
const props=defineProps<{action:string|null;target?:Entity|null;preset?:Record<string,unknown>}>()
const emit=defineEmits<{close:[];saved:[result:Entity]}>()
const w=useUvWorkspace(), dialog=ref<HTMLDialogElement|null>(null), draft=ref<Record<string,string|number|boolean>>({})
const presentation=useUvPresence(dialog), displayedAction=ref<string|null>(null), displayedTarget=ref<Entity|null>(null)
const focus=useUvReturnFocus(dialog)
useUvScrollLock(()=>presentation.present.value)
const error=ref(''), fields=ref<Record<string,string>>({}), saving=ref(false), uncertain=ref(false), conflict=ref(false), result=ref<Entity|null>(null)
const fieldPrefix='uv-form-'+useId(), fieldError=(key:string)=>fields.value['body.'+key]??fields.value[key]
let operationId=createRandomUuid(), submitted:Record<string,unknown>|null=null, session=0
const form=computed(()=>displayedAction.value?forms[displayedAction.value]:undefined)
const visibleFields=computed(()=>form.value?.fields.filter(field=>!(field.source==='pricing-policies'&&!w.can('cost_read'))&&!(field.source==='wage-policies'&&!w.can('payroll_read')))??[])
const editable=computed(()=>!saving.value&&!uncertain.value&&presentation.phase.value!=='closing')
useUvNavigationGuard(()=>{
  if(!props.action)return true
  w.notification.value=saving.value||uncertain.value?'请先完成保存或核对同一操作的回执。':'请先保存或关闭当前表单，再打开其他来源。'
  return false
})
function clear(){dialog.value?.close();focus.restore();displayedAction.value=null;displayedTarget.value=null;draft.value={};result.value=null;submitted=null;fields.value={};error.value='';saving.value=false;uncertain.value=false}
function dismiss(immediate=false){session++;presentation.close(clear,immediate)}
function close(){if(!saving.value)emit('close')}
watch([()=>props.action,()=>props.target?.id],async([action])=>{
  const version=++session
  if(!action){presentation.close(clear);return}
  if(presentation.present.value&&presentation.phase.value==='closing'&&displayedAction.value===action&&displayedTarget.value?.id===props.target?.id){
    presentation.open();return
  }
  displayedAction.value=action;displayedTarget.value=props.target?{...props.target}:null
  error.value='';fields.value={};result.value=null;saving.value=false;uncertain.value=false;conflict.value=false;operationId=createRandomUuid();submitted=null
  draft.value=Object.fromEntries(visibleFields.value.map(field=>[field.key,props.preset?.[field.key]??field.default??(field.type==='date'?today():field.type==='checkbox'?false:'')])) as Record<string,string|number|boolean>
  focus.capture();presentation.open()
  await nextTick();if(version!==session)return
  if(!dialog.value?.open)dialog.value?.showModal()
  if(!dialog.value?.contains(document.activeElement))dialog.value?.querySelector<HTMLElement>('input:not(:disabled),select:not(:disabled),textarea:not(:disabled),button:not(:disabled)')?.focus()
  try{
    const sources=[...new Set(visibleFields.value.flatMap(field=>field.source?[field.source]:[]))]
    if(action==='ink')sources.push('ink/balances')
    if(action==='reverse')sources.push('batches')
    await w.load(sources)
  }catch(cause){if(version===session)error.value=w.explain(cause)}
},{immediate:true})
watch(w.contextVersion,()=>{dismiss(true);emit('close')},{flush:'sync'})
onBeforeUnmount(()=>{session++;dialog.value?.close();focus.restore()})
function options(field:FormField):[string,string][]{
  if(field.options)return field.options
  if(!field.source)return []
  return w.items(field.source).filter(row=>field.source!=='file-versions'||(row.role==='production'&&row.confirmed_at)).map(row=>[row.id,[str(row,'code',''),str(row,'name',''),str(row,'product_snapshot',''),field.source==='batches'?'批次 '+row.id.slice(0,8)+' · 良品 '+num(row,'good')+' / 待检 '+num(row,'pending'):'',row.revision?'V'+row.revision:''].filter(Boolean).join(' · ')||row.id])
}
function expectedVersion(){
  if(draft.value.run_id)return w.items('runs').find(row=>row.id===draft.value.run_id)?.version??0
  if(draft.value.batch_id)return w.items('batches').find(row=>row.id===draft.value.batch_id)?.version??0
  if(displayedAction.value==='reverse')return w.items('batches').find(row=>row.id===displayedTarget.value?.batch_id)?.version??0
  if(displayedAction.value==='ink')return w.items('ink/balances').find(row=>row.sku_id===draft.value.sku_id&&row.lot===draft.value.lot&&row.location===draft.value.location)?.version??0
  return displayedTarget.value?.version??0
}
function values(){
  const body:Record<string,unknown>={expected_version:expectedVersion()}
  for(const field of visibleFields.value){
    const raw=draft.value[field.key]
    if(raw===''&&!field.required)continue
    body[field.key]=field.type==='number'?Number(raw):field.type==='datetime-local'?utcInput(String(raw)):field.type==='intervals'?String(raw).split(/\r?\n/).filter(Boolean).map(line=>line.split(/[,，]/).map(value=>utcInput(value.trim()))):raw
  }
  if(draft.value.other_batch_id)body.other_version=w.items('batches').find(row=>row.id===draft.value.other_batch_id)?.version??0
  return body
}
async function showFailure(cause:unknown,version:number){
  if(version!==session)return
  error.value=w.explain(cause)
  if(cause instanceof UvError){fields.value=cause.fields;conflict.value=cause.status===409;uncertain.value=cause.status>=500||cause.status===0}
  else uncertain.value=!(cause instanceof DOMException&&cause.name==='AbortError')
  if(!uncertain.value)operationId=createRandomUuid()
}
async function submit(){
  if(saving.value||presentation.phase.value==='closing'||!form.value||!w.can(form.value.permission))return
  const version=session, current=form.value
  saving.value=true;error.value='';fields.value={};conflict.value=false
  const path=current.path.replace(':id',displayedAction.value?.includes('Period')?str(displayedTarget.value??undefined,'period',''):displayedTarget.value?.id??'')
  try{
    if(!uncertain.value)submitted=values()
    const response=await w.command<Entity>(path,submitted!,operationId,current.method??'POST')
    if(version!==session)return
    result.value=response;uncertain.value=false;emit('saved',response)
    if(!response.pairing_code)emit('close')
  }catch(cause){await showFailure(cause,version)}
  finally{if(version===session){saving.value=false;await nextTick();if(version===session)dialog.value?.querySelector<HTMLElement>('[aria-invalid="true"]')?.focus()}}
}
async function checkReceipt(){
  if(saving.value)return
  const version=session;saving.value=true;error.value=''
  try{
    const response=await w.request<Entity>('receipts/'+operationId)
    if(version!==session)return
    result.value=response.data;uncertain.value=false;emit('saved',response.data)
    await w.refresh()
    if(version===session&&!response.data.pairing_code)emit('close')
  }catch(cause){if(version===session)error.value=cause instanceof UvError&&cause.status===404?'回执尚未生成；可用相同操作编号重试，系统会防止重复入账。':w.explain(cause)}
  finally{if(version===session)saving.value=false}
}
</script>
<template>
  <dialog ref="dialog" class="uv-dialog" :data-phase="presentation.phase.value" :aria-busy="saving" aria-labelledby="uv-action-title" @cancel.prevent="close">
    <form v-if="form" @submit.prevent="submit">
      <header><div><span class="uv-context">华康 A · {{form.target?'业务确认':'新建记录'}}</span><h2 id="uv-action-title">{{form.title}}</h2></div><button type="button" class="uv-icon-button" aria-label="关闭表单" :disabled="saving" @click="close"><X :size="20"/></button></header>
      <div class="uv-dialog-body">
        <p v-if="form.notice" class="uv-notice">{{form.notice}}</p>
        <div v-if="result?.pairing_code" class="uv-success"><Check :size="22"/><h3>代理身份已创建</h3><p>请在现场代理中输入此配对码。有效期 15 分钟。</p><code class="uv-pair-code">{{result.pairing_code}}</code><p>配对后返回此处绑定采集源。</p></div>
        <fieldset v-else :disabled="!editable" class="uv-form-grid">
          <label v-for="field in visibleFields" :key="field.key" :class="{'uv-form-wide':field.type==='textarea'||field.type==='checkbox'}">
            <span>{{field.label}}<b v-if="field.required" aria-hidden="true"> *</b></span>
            <select v-if="field.type==='select'" :aria-invalid="!!fieldError(field.key)" :aria-describedby="fieldError(field.key)?fieldPrefix+'-'+field.key:undefined" v-model="draft[field.key]" :required="field.required"><option value="">{{field.required?'请选择':'暂不设置'}}</option><option v-for="[value,text] in options(field)" :key="value" :value="value">{{text}}</option></select>
            <textarea v-else-if="field.type==='textarea'||field.type==='intervals'" :aria-invalid="!!fieldError(field.key)" :aria-describedby="fieldError(field.key)?fieldPrefix+'-'+field.key:undefined" :value="String(draft[field.key]??'')" @input="draft[field.key]=($event.target as HTMLTextAreaElement).value" :required="field.required" rows="3" />
            <input v-else-if="field.type==='checkbox'" :aria-invalid="!!fieldError(field.key)" :aria-describedby="fieldError(field.key)?fieldPrefix+'-'+field.key:undefined" v-model="draft[field.key]" type="checkbox" />
            <input v-else :aria-invalid="!!fieldError(field.key)" :aria-describedby="fieldError(field.key)?fieldPrefix+'-'+field.key:undefined" v-model="draft[field.key]" :type="field.type==='decimal'?'text':field.type??'text'" :inputmode="field.type==='decimal'?'decimal':undefined" :required="field.required" :step="field.type==='number'?1:undefined" :min="field.type==='number'?0:undefined" />
            <CollectionFooter v-if="field.source" :name="field.source"/><small v-if="field.help">{{field.help}}</small><small v-if="fieldError(field.key)" :id="fieldPrefix+'-'+field.key" class="uv-field-error">{{fieldError(field.key)}}</small>
          </label>
        </fieldset>
        <div v-if="error" class="uv-error" role="alert"><AlertTriangle :size="18"/><div>{{error}}<p v-if="conflict">输入已保留。请关闭表单核对最新记录，再重新确认；系统不会覆盖他人的修改。</p></div></div>
        <p v-if="uncertain" class="uv-notice">结果尚不确定，当前输入已锁定。重试会使用相同操作编号，避免重复入账。</p>
      </div>
      <footer><button type="button" class="uv-button" :disabled="saving" @click="close">{{result?'完成':'取消'}}</button><button v-if="uncertain" type="button" class="uv-button" :disabled="saving" @click="checkReceipt">核对上次回执</button><button v-if="!result" type="submit" class="uv-button primary" :disabled="saving||!w.can(form.permission)" :aria-busy="saving">{{saving?'正在保存…':uncertain?'重试同一操作':'确认保存'}}</button></footer>
    </form>
  </dialog>
</template>
