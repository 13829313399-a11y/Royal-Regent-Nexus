<script setup lang="ts">
import { computed, nextTick, ref, watch } from 'vue'
import { X, Check, AlertTriangle } from '@lucide/vue'
import { createRandomUuid } from '@/lib/randomUuid'
import { forms, type FormField } from '../forms'
import CollectionFooter from './CollectionFooter.vue'
import { num, str, today, utcInput, type Entity } from '../contracts'
import { useUvWorkspace, UvError } from '../workspace'
const props=defineProps<{action:string|null;target?:Entity|null;preset?:Record<string,unknown>}>()
const emit=defineEmits<{close:[];saved:[result:Entity]}>()
const w=useUvWorkspace(), dialog=ref<HTMLDialogElement>(), draft=ref<Record<string,string|number|boolean>>({})
const error=ref(''), fields=ref<Record<string,string>>({}), saving=ref(false), uncertain=ref(false), conflict=ref(false), result=ref<Entity|null>(null)
let operationId=createRandomUuid(), submitted:Record<string,unknown>|null=null
const form=computed(()=>props.action?forms[props.action]:undefined)
const visibleFields=computed(()=>form.value?.fields.filter(field=>!(field.source==='pricing-policies'&&!w.can('cost_read'))&&!(field.source==='wage-policies'&&!w.can('payroll_read')))??[])
const editable=computed(()=>!saving.value&&!uncertain.value)
function close() { if(saving.value) return; dialog.value?.close(); emit('close') }
watch(()=>props.action,async action=>{
  if(!action) { dialog.value?.close(); return }
  error.value=''; fields.value={}; result.value=null; uncertain.value=false; conflict.value=false; operationId=createRandomUuid(); submitted=null
  draft.value=Object.fromEntries(visibleFields.value.map(field=>[field.key, props.preset?.[field.key] ?? field.default ?? (field.type==='date'?today():field.type==='checkbox'?false:'')])) as Record<string,string|number|boolean>
  await nextTick(); if(!dialog.value?.open) dialog.value?.showModal()
  try {
    const sources=[...new Set(visibleFields.value.flatMap(field=>field.source?[field.source]:[]))]
    if(action==='ink') sources.push('ink/balances')
    if(action==='reverse') sources.push('batches')
    await w.load(sources)
  } catch(cause) {error.value=w.explain(cause)}
})
watch(w.contextVersion,()=>{dialog.value?.close();emit('close')})
function options(field:FormField):[string,string][] {
  if(field.options) return field.options
  if(!field.source) return []
  return w.items(field.source).filter(row=>field.source!=='file-versions'||(row.role==='production'&&row.confirmed_at)).map(row=>[row.id,[str(row,'code',''),str(row,'name',''),str(row,'product_snapshot',''),field.source==='batches'?`批次 ${row.id.slice(0,8)} · 良品 ${num(row,'good')} / 待检 ${num(row,'pending')}`:'',row.revision?`V${row.revision}`:''].filter(Boolean).join(' · ')||row.id])
}
function expectedVersion() {
  if(draft.value.run_id) return w.items('runs').find(row=>row.id===draft.value.run_id)?.version??0
  if(draft.value.batch_id) return w.items('batches').find(row=>row.id===draft.value.batch_id)?.version??0
  if(props.action==='reverse') return w.items('batches').find(row=>row.id===props.target?.batch_id)?.version??0
  if(props.action==='ink') return w.items('ink/balances').find(row=>row.sku_id===draft.value.sku_id&&row.lot===draft.value.lot&&row.location===draft.value.location)?.version??0
  return props.target?.version??0
}
function values() {
  const body:Record<string,unknown>={expected_version:expectedVersion()}
  for(const field of visibleFields.value) {
    const raw=draft.value[field.key]
    if(raw===''&&!field.required) continue
    body[field.key]=field.type==='number'?Number(raw):field.type==='datetime-local'?utcInput(String(raw)):field.type==='intervals'?String(raw).split(/\r?\n/).filter(Boolean).map(line=>line.split(/[,，]/).map(value=>utcInput(value.trim()))):raw
  }
  if(draft.value.other_batch_id) body.other_version=w.items('batches').find(row=>row.id===draft.value.other_batch_id)?.version??0
  return body
}
async function submit() {
  if(!form.value||!w.can(form.value.permission)) return
  saving.value=true; error.value=''; fields.value={}; conflict.value=false
  const path=form.value.path.replace(':id',props.action?.includes('Period')?str(props.target??undefined,'period',''):props.target?.id??'')
  if(!uncertain.value) submitted=values()
  try {
    const response=await w.command<Entity>(path,submitted!,operationId,form.value.method??'POST')
    result.value=response; uncertain.value=false; emit('saved',response)
    if(!response.pairing_code) closeAfterSave()
  } catch(cause) {
    error.value=w.explain(cause)
    if(cause instanceof UvError) { fields.value=cause.fields; conflict.value=cause.status===409; uncertain.value=cause.status>=500||cause.status===0 }
    else uncertain.value=!(cause instanceof DOMException&&cause.name==='AbortError')
    if(!uncertain.value) operationId=createRandomUuid()
  } finally {saving.value=false}
}
function closeAfterSave() {dialog.value?.close();emit('close')}
async function checkReceipt() {
  try {const response=await w.request<Entity>('receipts/'+operationId); result.value=response.data;uncertain.value=false;emit('saved',response.data);await w.refresh();closeAfterSave()}
  catch(cause) {error.value=cause instanceof UvError&&cause.status===404?'回执尚未生成；可用相同操作编号重试，系统会防止重复入账。':w.explain(cause)}
}
</script>
<template>
  <dialog ref="dialog" class="uv-dialog" @cancel.prevent="close">
    <form v-if="form" @submit.prevent="submit">
      <header><div><span class="uv-context">华康 A · {{form.target?'业务确认':'新建记录'}}</span><h2>{{form.title}}</h2></div><button type="button" class="uv-icon-button" aria-label="关闭表单" @click="close"><X :size="20"/></button></header>
      <div class="uv-dialog-body">
        <p v-if="form.notice" class="uv-notice">{{form.notice}}</p>
        <div v-if="result?.pairing_code" class="uv-success"><Check :size="22"/><h3>代理身份已创建</h3><p>请在现场代理中输入此配对码。有效期 15 分钟。</p><code class="uv-pair-code">{{result.pairing_code}}</code><p>配对后返回此处绑定采集源。</p></div>
        <fieldset v-else :disabled="!editable" class="uv-form-grid">
          <label v-for="field in visibleFields" :key="field.key" :class="{'uv-form-wide':field.type==='textarea'||field.type==='checkbox'}">
            <span>{{field.label}}<b v-if="field.required" aria-hidden="true"> *</b></span>
            <select v-if="field.type==='select'" v-model="draft[field.key]" :required="field.required"><option value="">{{field.required?'请选择':'暂不设置'}}</option><option v-for="[value,text] in options(field)" :key="value" :value="value">{{text}}</option></select>
            <textarea v-else-if="field.type==='textarea'||field.type==='intervals'" :value="String(draft[field.key]??'')" @input="draft[field.key]=($event.target as HTMLTextAreaElement).value" :required="field.required" rows="3" />
            <input v-else-if="field.type==='checkbox'" v-model="draft[field.key]" type="checkbox" />
            <input v-else v-model="draft[field.key]" :type="field.type==='decimal'?'text':field.type??'text'" :inputmode="field.type==='decimal'?'decimal':undefined" :required="field.required" :step="field.type==='number'?1:undefined" :min="field.type==='number'?0:undefined" />
            <CollectionFooter v-if="field.source" :name="field.source"/><small v-if="field.help">{{field.help}}</small><small v-if="fields['body.'+field.key]" class="uv-field-error">{{fields['body.'+field.key]}}</small>
          </label>
        </fieldset>
        <div v-if="error" class="uv-error" role="alert"><AlertTriangle :size="18"/><div>{{error}}<p v-if="conflict">输入已保留。请关闭表单核对最新记录，再重新确认；系统不会覆盖他人的修改。</p></div></div>
        <p v-if="uncertain" class="uv-notice">结果尚不确定，当前输入已锁定。重试会使用相同操作编号，避免重复入账。</p>
      </div>
      <footer><button type="button" class="uv-button" @click="close">{{result?'完成':'取消'}}</button><button v-if="uncertain" type="button" class="uv-button" @click="checkReceipt">核对上次回执</button><button v-if="!result" type="submit" class="uv-button primary" :disabled="saving||!w.can(form.permission)">{{saving?'正在保存…':uncertain?'重试同一操作':'确认保存'}}</button></footer>
    </form>
  </dialog>
</template>
