<script setup lang="ts">
import { computed, nextTick, ref } from 'vue'
import { Copy, Check, MapPin, BookOpen, MoreHorizontal } from '@lucide/vue'
import { isNavigationFailure, NavigationFailureType, useRouter } from 'vue-router'
import { assistantApi } from './api'
import AssistantAttachment from './AssistantAttachment.vue'
import AssistantDocument from './AssistantDocument.vue'
import AssistantBusinessFacts from './AssistantBusinessFacts.vue'
import AssistantQuotePrefill from './AssistantQuotePrefill.vue'
import AssistantMenu from './AssistantMenu.vue'
import AssistantFeedback from './AssistantFeedback.vue'
import { quotePrefillTargets } from './quotePrefill'
import type { EvidencePart, UIAction } from './v2'
import { renderMarkdown } from './markdown'
import { sourceSummary } from './sourceSummary'
import { activeStates, stateLabels, type Message, type RunRelation } from './types'
import { relationLabels } from './relatedDraft'
import { factoryContexts } from '@/data/enterpriseMock'
const props = withDefaults(defineProps<{ message: Message; feedbackAvailable?:boolean; relatedDisabled?:boolean; menusActive?:boolean }>(),{feedbackAvailable:false,relatedDisabled:false,menusActive:true})
const emit = defineEmits<{ citation: [id: string]; sources: [evidence: EvidencePart]; saved: [id: string]; fileDeleted: []; excerpt: [runId: string, text: string]; parent: [runId: string]; nativeForm: []; related:[runId:string,kind:'revise'|'regenerate']; unavailable:[runId:string]; menu:[boolean] }>()
const router = useRouter()
const copied = ref(false), copyError = ref('')
const savingArtifact = ref(false)
const body = ref<HTMLElement>(), excerptOpen = ref(false), excerptText = ref('')
const actionsRoot=ref<HTMLElement>(), feedbackMounted=ref(false), feedbackOpen=ref(false)
const persisted=computed(()=>!!props.message.run_id&&!props.message.id.startsWith('answer-')&&!props.message.id.startsWith('pending-'))
const canOperate=computed(()=>persisted.value&&!props.message.unavailable&&!activeStates.includes(props.message.status))
const moreItems=computed(()=>props.message.role==='user'
  ? [{id:'revise',label:props.relatedDisabled?'回答进行中，暂不能编辑重问':'编辑重问',disabled:props.relatedDisabled}]
  : [{id:'regenerate',label:'重新生成新回答',disabled:props.relatedDisabled},
    {id:'save',label:'保存成果',disabled:savingArtifact.value||!text.value},
    {id:'checklist',label:'转检查清单',disabled:savingArtifact.value||!text.value},
    {id:'export',label:'导出 Markdown',disabled:!text.value},
    ...(hasBusinessData.value?[{id:'table',label:'保存数据表',disabled:savingArtifact.value||!text.value},{id:'chart',label:'保存指标图表',disabled:savingArtifact.value||!text.value}]:[]),
    {id:'feedback',label:props.feedbackAvailable?'反馈':'反馈功能待准备',disabled:!props.feedbackAvailable}])
async function returnActionFocus() {
  await nextTick()
  const trigger=actionsRoot.value?.querySelector<HTMLElement>('[aria-label="更多回答操作"],[aria-label="更多问题操作"]')
  if(trigger?.getClientRects().length&&!trigger.closest('[inert]'))trigger.focus({preventScroll:true})
}
async function moreSelected(id:string) {
  if(!canOperate.value)return
  if(id==='feedback'&&props.feedbackAvailable){feedbackMounted.value=true;feedbackOpen.value=true;return}
  if(id==='revise'||id==='regenerate'){await returnActionFocus();if(!props.relatedDisabled)emit('related',props.message.run_id,id);return}
  await returnActionFocus()
  if(id==='export')await exportAnswer()
  else if(id==='save')await save()
  else if(id==='checklist')await save(true)
  else if(id==='table'||id==='chart')await save(false,id)
}
async function closeFeedback(){feedbackOpen.value=false;await returnActionFocus()}
const relation = computed(() => props.message.content_parts.find(p => p.type === 'run_relation') as (RunRelation & {type:string}) | undefined)
function prepareExcerpt() {
  const selected = window.getSelection()
  const range = selected?.rangeCount ? selected.getRangeAt(0) : null
  excerptText.value = range && body.value?.contains(range.commonAncestorContainer) ? selected!.toString().slice(0,8000) : ''
  excerptOpen.value = true
}
const hasBusinessData = computed(() => props.message.content_parts.some(p => p.type === 'business_snapshot' && (p.result as {contract_version?: number})?.contract_version === 3))
const hasQuotePrefill = computed(() => quotePrefillTargets(props.message).length > 0)
const text = computed(() => props.message.content_parts.filter(p => p.type === 'text').map(p => p.text || '').join(''))
const reasoning = computed(() => props.message.content_parts.filter(p => p.type === 'reasoning').map(p => p.text || '').join(''))
const notices = computed(() => props.message.unavailable ? [] : props.message.content_parts.filter(p => p.type === 'run_notice'))
const evidence = computed(() => props.message.content_parts.find(p => p.type === 'evidence') as unknown as EvidencePart | undefined)
const actions = computed(() => (props.message.unavailable ? [] : props.message.content_parts.find(p => p.type === 'actions')?.items || []) as UIAction[])
const primaryActionCount = computed(() => actions.value.length > 4 ? 3 : actions.value.length)
const rendered = computed(() => props.message.content_parts.filter(p => p.type === 'text').map(p => renderMarkdown(p.text || '', evidence.value, String(p.part_id || ''), actions.value)).join(''))
const activity = computed(() => ['connecting','thinking','answering','tool_running'].includes(props.message.status) ? evidence.value?.activities.find(a => a.status === 'running')?.label : undefined)
const searchNotice = computed(() => evidence.value?.search.execution === 'unconfirmed' ? '本次未取得可核验的联网证据' : evidence.value?.search.execution === 'confirmed' && evidence.value.search.evidence_level === 'none' ? '已完成检索，暂未返回合适来源' : '')
const contextLabel = computed(() => {
  const context = props.message.context_descriptor
  if (!context) return ''
  const names: Record<string,string> = { portal:'系统门户','work-center':'事项工作台','injection-scheduling':'注塑排产','three-d-printing':'3D 打印','internal-quote':'内部报价','identity-management':'人员与权限','carton-supplier':'供应商协同','molding-sample':'工模手板','customer-orders':'客户订单','carton-procurement':'纸箱采购','carton-mark':'纸箱唛头','qc-inspection':'QC 验货','document-tools':'文档工具','uv-operations':'UV 生产','spray-production':'喷油生产' }
  const snapshot = props.message.content_parts.find(p => p.type === 'business_snapshot')?.result as { scope?: { label?: string } } | undefined
  return snapshot?.scope?.label ? `${names[context.module_id] || '业务查询'} · ${snapshot.scope.label}`
    : `页面：${names[context.module_id] || '页面说明'} · ${factoryContexts.find(f => f.id === context.factory_id)?.name || '通用说明'}`
})
async function copy(value: string) {
  try { await navigator.clipboard.writeText(value); copied.value = true; copyError.value = '' }
  catch { copyError.value = '当前浏览器无法直接复制，请选中文字后复制。' }
}
function codeClick(event: MouseEvent) {
  const recordButton = (event.target as HTMLElement).closest<HTMLElement>('[data-yl-action]')
  if (recordButton) void action(Number(recordButton.dataset.ylAction))
  const button = (event.target as HTMLElement).closest('[data-yl-copy-code]')
  if (button) void copy(button.closest('.yl-code')?.querySelector('code')?.textContent || '')
  if ((event.target as HTMLElement).closest('[data-yl-source]') && evidence.value) emit('sources', evidence.value)
}
async function exportAnswer() { try { const blob=await assistantApi.exportAnswer(props.message.run_id), url=URL.createObjectURL(blob); const a=document.createElement('a'); a.href=url; a.download='曜灵回答.md'; a.click(); setTimeout(() => URL.revokeObjectURL(url),1000) } catch(e) { copyError.value=e instanceof Error ? e.message : '导出失败' } }
async function save(checklist=false, kind?: 'table' | 'chart') {
  if (savingArtifact.value) return
  savingArtifact.value = true
  try {
    const content=checklist ? text.value.split('\n').filter(line => line.trim() && !line.startsWith('#')).map(line => `- [ ] ${line.replace(/^\s*[-*\d.]+\s+/, '')}`).join('\n') : text.value
    const snapshot=await assistantApi.snapshot(props.message.run_id)
    const a=await assistantApi.saveArtifact(snapshot.session_id,{source_run_id:props.message.run_id,title:kind === 'chart' ? '业务指标图表' : kind === 'table' ? '业务原查询数据表' : checklist ? '回答检查清单' : '曜灵研究成果',kind:kind || (checklist ? 'checklist' : 'research'),content})
    emit('saved',a.id)
  } catch(e) { copyError.value=e instanceof Error ? e.message : '保存失败' }
  finally { savingArtifact.value = false }
}
async function action(index: number) {
  try {
    const a=await assistantApi.action(props.message.run_id,index)
    if(a.type==='highlight') emit('citation',a.help_id)
    else if(a.type==='open_record') {
      emit('nativeForm'); await nextTick()
      const failure=await router.push({name:a.route_name,params:a.params,query:a.query})
      await nextTick()
      const active=document.activeElement as HTMLElement|null
      if ((!failure || isNavigationFailure(failure,NavigationFailureType.duplicated)) && (active===document.body || active?.closest('.yl-assistant'))) {
        const modal=[...document.querySelectorAll<HTMLElement>('[aria-modal="true"],dialog[open]')].some(e=>!e.closest('.yl-assistant') && e.getClientRects().length)
        const main=document.querySelector<HTMLElement>('#app main')
        if (!modal && main?.getClientRects().length && !main.closest('[inert]') && getComputedStyle(main).visibility!=='hidden') {
          if (!main.hasAttribute('tabindex')) main.tabIndex=-1
          main.focus({preventScroll:true})
        }
      }
    }
  } catch(e) { copyError.value=e instanceof Error ? e.message : '来源或权限已失效' }
}
</script>
<template>
  <article class="yl-message" :class="`yl-message-${message.role}`" :data-message-id="message.id" :data-run-id="message.run_id">
    <div class="yl-message-author"><span>{{ message.role === 'user' ? '你' : '曜灵' }}</span><small v-if="message.role === 'assistant'">{{ stateLabels[message.status] }}</small></div>
    <small v-if="message.context_descriptor" class="yl-frozen-context">{{ contextLabel }}</small>
    <div v-if="relation && !message.unavailable" class="yl-relation"><span>{{ relationLabels[relation.kind] }} · 原回答仍保留</span><button @click="emit('parent',relation.parent_run_id)">定位原回答</button></div>
    <p v-if="message.help_verification === 'legacy_version_only'" class="yl-notice">这段历史说明未保存来源指纹，不能据此确认当前规则，也不会作为新回答的依据。请重新查看已核对的本页说明。</p>
    <details v-if="reasoning" class="yl-reasoning"><summary>思考内容</summary><p>{{ reasoning }}</p></details>
    <div v-if="activity || searchNotice || evidence?.sources.length" class="yl-activity" role="status"><span>{{ activity || searchNotice || `${evidence?.sources.length} 项可回看的资料` }}</span><button v-if="evidence?.sources.length" @click="emit('sources',evidence)">查看来源 <BookOpen :size="14"/></button></div>
    <p v-if="!message.unavailable && sourceSummary(evidence)" class="yl-source-summary">{{ sourceSummary(evidence) }}</p>
    <AssistantBusinessFacts v-if="message.role === 'assistant'" :message="message" @sources="evidence && emit('sources',evidence)"/>
    <div v-if="message.role === 'user'" class="yl-user-text">{{ text }}</div>
    <!-- HTML is produced only by the html:false renderer; remote images are disabled. -->
    <div v-else ref="body" class="yl-markdown" @click="codeClick" v-html="rendered" />
    <p v-for="notice in notices" :key="String(notice.code)" class="yl-notice" role="status">{{ notice.text }}</p>
    <p v-if="!text && message.role === 'assistant'" class="yl-empty-answer">{{ ['cancelled','failed','interrupted'].includes(message.status) ? '尚未生成正文。' : '回答会显示在这里…' }}</p>
    <AssistantAttachment v-for="part in message.content_parts.filter(p => p.type === 'image_ref')" :key="String(part.attachment_id)" :id="String(part.attachment_id)"/>
    <AssistantDocument v-for="part in message.content_parts.filter(p => p.type === 'document_ref')" :key="String(part.file_id)" :id="String(part.file_id)" @deleted="emit('fileDeleted')"/>
    <div v-if="message.role === 'assistant' && message.help_citations.length" class="yl-citations"><button v-for="citation in message.help_citations" :key="citation.id" @click="emit('citation', citation.id)"><MapPin :size="13" /> 查看说明 · {{ citation.version }}</button></div>
    <div ref="actionsRoot" class="yl-message-primary"><button v-if="text" class="yl-copy" @click="copy(text)" :aria-label="copied ? '已复制' : message.role==='user' ? '复制问题' : '复制回答'"><Check v-if="copied" :size="14" /><Copy v-else :size="14" />{{ copied ? '已复制' : '复制' }}</button><button v-if="canOperate && message.role==='assistant'" :disabled="!text" @mousedown.prevent @click="prepareExcerpt">继续追问</button><AssistantMenu v-if="canOperate" :label="message.role==='user'?'更多问题操作':'更多回答操作'" :items="moreItems" :active="menusActive" @open="emit('menu',$event)" @select="moreSelected"><MoreHorizontal :size="14"/>更多</AssistantMenu></div>
    <div v-if="excerptOpen && !message.unavailable" class="yl-excerpt-editor"><label>要继续讨论的摘录<textarea v-model="excerptText" aria-label="原回答摘录" maxlength="8000" rows="3" placeholder="可先选中本回答中的文字再点摘录追问，也可在此填写摘录。"/></label><button :disabled="!excerptText.trim()" @click="emit('excerpt',message.run_id,excerptText.trim()); excerptOpen=false">带入输入区</button><button @click="excerptOpen=false">取消摘录</button></div>
    <AssistantFeedback v-if="feedbackMounted && !message.unavailable" :run-id="message.run_id" :open="feedbackOpen" :available="feedbackAvailable" @close="closeFeedback" @unavailable="emit('unavailable',message.run_id)"/>
    <AssistantQuotePrefill v-if="message.role==='assistant' && hasQuotePrefill" :message="message" @prepared="emit('nativeForm')"/>
    <div class="yl-answer-actions"><button v-for="(a,index) in actions.slice(0,primaryActionCount)" :key="index" @click="action(index)">{{ a.label }}</button></div>
    <details v-if="actions.length > primaryActionCount" class="yl-more-actions"><summary>其余 {{ actions.length - primaryActionCount }} 个入口</summary><div class="yl-answer-actions"><button v-for="(a,index) in actions.slice(primaryActionCount)" :key="index" @click="action(index + primaryActionCount)">{{ a.label }}</button></div></details>
    <p v-if="copyError" role="status" class="yl-muted">{{ copyError }}</p>
  </article>
</template>
