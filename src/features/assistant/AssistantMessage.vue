<script setup lang="ts">
import { computed, ref } from 'vue'
import { Copy, Check, MapPin, Download, BookOpen, Bookmark, ListChecks } from '@lucide/vue'
import { useRouter } from 'vue-router'
import { assistantApi } from './api'
import AssistantAttachment from './AssistantAttachment.vue'
import AssistantDocument from './AssistantDocument.vue'
import type { EvidencePart, UIAction } from './v2'
import { renderMarkdown } from './markdown'
import { sourceSummary } from './sourceSummary'
import { stateLabels, type Message } from './types'
import { factoryContexts } from '@/data/enterpriseMock'
const props = defineProps<{ message: Message }>()
const emit = defineEmits<{ citation: [id: string]; sources: [evidence: EvidencePart]; saved: [id: string]; fileDeleted: [] }>()
const router = useRouter()
const copied = ref(false), copyError = ref('')
const text = computed(() => props.message.content_parts.filter(p => p.type === 'text').map(p => p.text || '').join(''))
const reasoning = computed(() => props.message.content_parts.filter(p => p.type === 'reasoning').map(p => p.text || '').join(''))
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
async function save(checklist=false) {
  try {
    const content=checklist ? text.value.split('\n').filter(line => line.trim() && !line.startsWith('#')).map(line => `- [ ] ${line.replace(/^\s*[-*\d.]+\s+/, '')}`).join('\n') : text.value
    const snapshot=await assistantApi.snapshot(props.message.run_id)
    const a=await assistantApi.saveArtifact(snapshot.session_id,{source_run_id:props.message.run_id,title:checklist ? '回答检查清单' : '曜灵研究成果',kind:checklist ? 'checklist' : 'research',content})
    emit('saved',a.id)
  } catch(e) { copyError.value=e instanceof Error ? e.message : '保存失败' }
}
async function action(index: number) { try { const a=await assistantApi.action(props.message.run_id,index); if(a.type==='highlight') emit('citation',a.help_id); else if(a.type==='open_record') await router.push({name:a.route_name,params:a.params,query:a.query}) } catch(e) { copyError.value=e instanceof Error ? e.message : '来源或权限已失效' } }
</script>
<template>
  <article class="yl-message" :class="`yl-message-${message.role}`" :data-message-id="message.id">
    <div class="yl-message-author"><span>{{ message.role === 'user' ? '你' : '曜灵' }}</span><small v-if="message.role === 'assistant'">{{ stateLabels[message.status] }}</small></div>
    <small v-if="message.context_descriptor" class="yl-frozen-context">{{ contextLabel }}</small>
    <p v-if="message.help_verification === 'legacy_version_only'" class="yl-notice">这段历史说明未保存来源指纹，不能据此确认当前规则，也不会作为新回答的依据。请重新查看已核对的本页说明。</p>
    <details v-if="reasoning" class="yl-reasoning"><summary>思考内容</summary><p>{{ reasoning }}</p></details>
    <div v-if="activity || searchNotice || evidence?.sources.length" class="yl-activity" role="status"><span>{{ activity || searchNotice || `${evidence?.sources.length} 项可回看的资料` }}</span><button v-if="evidence?.sources.length" @click="emit('sources',evidence)">查看来源 <BookOpen :size="14"/></button></div>
    <p v-if="!message.unavailable && sourceSummary(evidence)" class="yl-source-summary">{{ sourceSummary(evidence) }}</p>
    <div v-if="message.role === 'user'" class="yl-user-text">{{ text }}</div>
    <!-- HTML is produced only by the html:false renderer; remote images are disabled. -->
    <div v-else class="yl-markdown" @click="codeClick" v-html="rendered" />
    <p v-if="!text && message.role === 'assistant'" class="yl-empty-answer">{{ ['cancelled','failed','interrupted'].includes(message.status) ? '尚未生成正文。' : '回答会显示在这里…' }}</p>
    <AssistantAttachment v-for="part in message.content_parts.filter(p => p.type === 'image_ref')" :key="String(part.attachment_id)" :id="String(part.attachment_id)"/>
    <AssistantDocument v-for="part in message.content_parts.filter(p => p.type === 'document_ref')" :key="String(part.file_id)" :id="String(part.file_id)" @deleted="emit('fileDeleted')"/>
    <div v-if="message.role === 'assistant' && message.help_citations.length" class="yl-citations"><button v-for="citation in message.help_citations" :key="citation.id" @click="emit('citation', citation.id)"><MapPin :size="13" /> 查看说明 · {{ citation.version }}</button></div>
    <button v-if="text" class="yl-copy" @click="copy(text)" :aria-label="copied ? '已复制回答' : '复制回答'"><Check v-if="copied" :size="14" /><Copy v-else :size="14" />{{ copied ? '已复制' : '复制' }}</button>
    <div v-if="message.role==='assistant' && !message.unavailable && !message.id.startsWith('answer-') && text && !['connecting','answering','thinking','tool_running'].includes(message.status)" class="yl-answer-actions"><button @click="exportAnswer"><Download :size="14"/>导出 Markdown</button><button @click="save()"><Bookmark :size="14"/>保存成果</button><button @click="save(true)"><ListChecks :size="14"/>转检查清单</button></div>
    <div class="yl-answer-actions"><button v-for="(a,index) in actions.slice(0,primaryActionCount)" :key="index" @click="action(index)">{{ a.label }}</button></div>
    <details v-if="actions.length > primaryActionCount" class="yl-more-actions"><summary>其余 {{ actions.length - primaryActionCount }} 个入口</summary><div class="yl-answer-actions"><button v-for="(a,index) in actions.slice(primaryActionCount)" :key="index" @click="action(index + primaryActionCount)">{{ a.label }}</button></div></details>
    <p v-if="copyError" role="status" class="yl-muted">{{ copyError }}</p>
  </article>
</template>
