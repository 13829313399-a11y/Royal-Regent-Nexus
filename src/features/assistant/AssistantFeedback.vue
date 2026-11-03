<script setup lang="ts">
import { computed, nextTick, onUnmounted, ref, watch } from 'vue'
import { assistantApi, AssistantApiError, newRequestId } from './api'
import type { FeedbackCategory, FeedbackData, FeedbackRecord, FeedbackSave } from './types'
const props=defineProps<{runId:string;open:boolean;available:boolean}>()
const emit=defineEmits<{close:[];unavailable:[]}>()
const root=ref<HTMLElement>(), data=ref<FeedbackData|null>(null), categories=ref<FeedbackCategory[]>([]), sources=ref<string[]>([]), comment=ref('')
const revision=ref(0), loading=ref(false), saving=ref(false), error=ref(''), status=ref(''), uncertain=ref(false), preview=ref<FeedbackRecord|null>(null)
const frozen=ref<FeedbackSave|null>(null)
let generation=0, controller=new AbortController()
const options:{id:FeedbackCategory;label:string}[]=[{id:'factual',label:'事实错误'},{id:'off_topic',label:'没回答问题'},{id:'sources',label:'来源问题'},{id:'experience',label:'体验问题'}]
const locked=computed(()=>loading.value||saving.value||uncertain.value||!props.available||!data.value?.available)
const canSave=computed(()=>!locked.value&&(categories.value.length>0||!!comment.value.trim()))
function fail(e:unknown) {
  if(e instanceof AssistantApiError && [401,403,404,410].includes(e.status)) {
    comment.value='';sources.value=[];categories.value=[];data.value=null;preview.value=null;frozen.value=null
    emit('unavailable');return true
  }
  error.value=e instanceof Error?e.message:'暂时无法保存反馈，请稍后重试。';return false
}
function apply(record:FeedbackRecord|null) {
  revision.value=record?.revision||0;categories.value=[...(record?.categories||[])];sources.value=[...(record?.source_ids||[])];comment.value=record?.comment||''
  uncertain.value=false;frozen.value=null;preview.value=null
}
async function load(replace=false) {
  if(loading.value||saving.value)return
  const g=++generation;loading.value=true;error.value=''
  try {
    const value=await assistantApi.feedback(props.runId,controller.signal)
    if(g!==generation)return
    data.value=value
    if(!frozen.value && (replace||revision.value===0&&!comment.value&&!categories.value.length)) apply(value.feedback)
    else if(uncertain.value && value.feedback && frozen.value && value.feedback.revision===frozen.value.base_revision+1 &&
      value.feedback.comment===frozen.value.comment && JSON.stringify(value.feedback.categories)===JSON.stringify(frozen.value.categories) && JSON.stringify(value.feedback.source_ids)===JSON.stringify(frozen.value.source_ids)) {
      apply(value.feedback);status.value='反馈已保存。'
    } else if(value.feedback) preview.value=value.feedback
  } catch(e) {if(g===generation)fail(e)}
  finally {if(g===generation)loading.value=false}
}
async function save(retry=false) {
  if(saving.value || !props.available || !data.value?.available || !retry&&!canSave.value)return
  const request=retry?frozen.value:{client_request_id:newRequestId(),base_revision:revision.value,categories:[...categories.value],source_ids:[...sources.value],comment:comment.value}
  if(!request)return
  frozen.value=request;const g=++generation;saving.value=true;error.value='';status.value=''
  try {
    const result=await assistantApi.saveFeedback(props.runId,request,controller.signal)
    if(g!==generation)return
    apply(result);status.value='反馈已保存，仅关联这次回答。'
  } catch(e) {
    if(g!==generation || fail(e))return
    if(e instanceof AssistantApiError && e.status<500) {uncertain.value=false;frozen.value=null}
    else uncertain.value=true
  } finally {if(g===generation)saving.value=false}
}
async function replacePreview() {if(preview.value){apply(preview.value);error.value='';status.value='已载入保存的版本。'}}
async function overwritePreview() {
  if(!preview.value)return
  revision.value=preview.value.revision;preview.value=null;uncertain.value=false;frozen.value=null
  await save()
}
watch(()=>props.open,async value=>{
  if(!value)return
  const openedRun=props.runId
  await nextTick();if(props.open)root.value?.querySelector<HTMLElement>('button')?.focus({preventScroll:true})
  if(!data.value && props.available)await load()
  await nextTick();if(props.open&&props.runId===openedRun&&root.value?.contains(document.activeElement))root.value?.querySelector<HTMLElement>('input:not(:disabled),textarea:not(:disabled),button')?.focus({preventScroll:true})
},{immediate:true})
watch(()=>props.runId,()=>{generation++;controller.abort();controller=new AbortController();data.value=null;apply(null);error.value='';status.value='';loading.value=false;saving.value=false;if(props.open&&props.available)void load()})
onUnmounted(()=>{generation++;controller.abort()})
</script>
<template>
  <section v-show="open" ref="root" class="yl-feedback" :aria-labelledby="`yl-feedback-${runId}`" @keydown.esc.stop.prevent="emit('close')">
    <header><h4 :id="`yl-feedback-${runId}`">反馈这次回答</h4><button type="button" aria-label="关闭反馈" @click="emit('close')">关闭</button></header>
    <p class="yl-muted">关联原回答和所选来源；不会重新生成或修改原回答。</p>
    <p v-if="!available" role="status">反馈功能尚未准备完成，当前草稿会保留。</p>
    <p v-else-if="loading" role="status">正在读取已保存的反馈…</p>
    <p v-else-if="data && !data.available" role="status">回答结束或停止后可以提交反馈。</p>
    <fieldset :disabled="locked"><legend>问题类别（可选）</legend><label v-for="option in options" :key="option.id"><input v-model="categories" type="checkbox" :value="option.id"/>{{ option.label }}</label></fieldset>
    <details v-if="data?.sources.length"><summary>关联来源（可选，共 {{ data.sources.length }} 项；已选 {{ sources.length }} / 32）</summary><div class="yl-feedback-sources"><label v-for="source in data.sources" :key="source.source_id"><input v-model="sources" type="checkbox" :disabled="locked || sources.length>=32&&!sources.includes(source.source_id)" :value="source.source_id"/><span>{{ source.title }}<small v-if="!source.citation_eligible"> · 检索范围记录</small></span></label></div></details>
    <label class="yl-feedback-comment">补充说明（可选）<textarea v-model="comment" :disabled="locked" aria-label="反馈补充说明" rows="3" maxlength="2000" placeholder="说明哪里需要改进，也可以仅选择问题类别。"/></label>
    <small>{{ comment.length }} / 2000；请选择类别或填写说明。</small>
    <p v-if="error" role="alert">{{ error }}</p><p v-if="status" role="status">{{ status }}</p>
    <p v-if="uncertain" role="status">保存结果待确认，原请求和草稿已保留。可先查询，或按相同请求重试保存。</p>
    <div class="yl-feedback-buttons"><button type="button" :disabled="!canSave" :aria-busy="saving" @click="save()">{{ saving?'保存中…':'保存反馈' }}</button><button v-if="error||uncertain" type="button" :disabled="loading||saving" @click="load()">查询已保存反馈</button><button v-if="uncertain" type="button" :disabled="loading||saving||!available" @click="save(true)">按原请求重试保存</button></div>
    <div v-if="preview" class="yl-feedback-preview"><strong>服务端已保存版本 {{ preview.revision }}</strong><p>{{ preview.comment || '未填写补充说明' }}</p><p>{{ options.filter(o=>preview?.categories.includes(o.id)).map(o=>o.label).join('、') }}</p><button type="button" :disabled="loading||saving" @click="replacePreview">用已保存内容替换草稿</button><button type="button" :disabled="loading||saving||!available" @click="overwritePreview">以当前草稿替换已保存反馈</button></div>
  </section>
</template>
<style scoped>
.yl-feedback{min-width:0;max-width:100%;margin:12px 0;padding:12px;border:1px solid var(--yl-line);border-radius:12px;background:var(--yl-panel);overflow-wrap:anywhere}.yl-feedback header{display:flex;align-items:center;justify-content:space-between;gap:8px}.yl-feedback h4{margin:0;font-size:14px}.yl-feedback p{font-size:12px;line-height:1.65}.yl-feedback fieldset{display:flex;flex-wrap:wrap;gap:8px 12px;padding:8px 0;border:0;font-size:12px}.yl-feedback legend{font-weight:600}.yl-feedback label{display:flex;gap:6px;align-items:flex-start;min-height:32px}.yl-feedback input{margin-top:3px;flex-shrink:0}.yl-feedback .yl-feedback-comment{display:block;font-size:12px}.yl-feedback textarea{display:block;width:100%;box-sizing:border-box;min-height:84px;border:1px solid var(--yl-line);border-radius:8px;padding:8px;font:inherit;margin:6px 0;resize:vertical}.yl-feedback small{font-size:11px;color:var(--yl-muted)}.yl-feedback button{min-height:40px;padding:7px 10px;border:1px solid var(--yl-line);border-radius:8px;color:var(--yl-deep);background:var(--yl-paper)}.yl-feedback button:disabled{opacity:.55}.yl-feedback-buttons{display:flex;flex-wrap:wrap;gap:8px;margin-top:10px}.yl-feedback summary{min-height:40px;padding:10px 0;cursor:pointer;font-size:12px}.yl-feedback-sources{max-height:180px;overflow:auto;font-size:12px}.yl-feedback-preview{margin-top:12px;padding-top:10px;border-top:1px solid var(--yl-line);font-size:12px}.yl-feedback-preview button{margin:4px}.yl-feedback :focus-visible{outline:2px solid var(--yl-jade);outline-offset:2px}@media(max-width:767px){.yl-feedback button,.yl-feedback label{min-height:44px}}
</style>
