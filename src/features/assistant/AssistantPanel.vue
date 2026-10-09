<script setup lang="ts">
import { computed, nextTick, onMounted, onUnmounted, ref, watch } from 'vue'
import { ArrowUp, Square, Minus, Maximize2, Minimize2, History, Plus, Info, X, MapPin, ChevronRight, ArrowDown, Download, Trash2, Pencil, PanelLeftClose, ImagePlus, GripVertical } from '@lucide/vue'
import { useAssistantStore } from '@/stores/assistant'
import { acquireBodyScrollLock } from '@/lib/bodyScrollLock'
import { assistantApi } from './api'
import { availableTargetIds, revealTarget } from './anchors'
import { activeStates, stateLabels, type Conversation, type HelpArticle, type PageContext, type PanelMode, type SendPayload } from './types'
import AssistantCore from './AssistantCore.vue'
import AssistantMessage from './AssistantMessage.vue'
const props = defineProps<{ mode: PanelMode; side: 'left' | 'right'; width: number; page: PageContext | null; pageTitle: string; suspended?: boolean }>()
const emit = defineEmits<{ mode: [PanelMode]; side: ['left' | 'right']; width: [number] }>()
const store = useAssistantStore(), panel = ref<HTMLElement>(), scroller = ref<HTMLElement>(), composer = ref<HTMLTextAreaElement>()
const draft = ref(''), tab = ref<'chat' | 'help' | 'pick'>('chat'), historyOpen = ref(false), aboutOpen = ref(false)
const help = ref<HelpArticle[]>([]), helpError = ref(''), selectedArticle = ref<HelpArticle | null>(null)
const localError = ref(''), useContext = ref(true), thinking = ref<'auto' | 'on' | 'off'>('auto'), showNew = ref(false)
const attachments = ref<{ id: string; url: string; name: string }[]>([]), uploading = ref(false), fileInput = ref<HTMLInputElement>()
const viewport = ref({ width: innerWidth, height: innerHeight, top: 0 }), reducedMotion = ref(false)
const pickTargets = ref<{ id: string; label: string }[]>([]), highlight = ref<DOMRect | null>(null), guideIndex = ref(-1)
const renameId = ref(''), renameText = ref(''), deleteId = ref('')
let nearBottom = true, helpGeneration = 0, highlightElement: HTMLElement | null = null
let releaseLock: (() => void) | undefined, originalInert: boolean | undefined, oldFocus: HTMLElement | null = null
let pointer: { kind: 'drag' | 'resize'; x: number; width: number } | null = null
let previewing = false, connectorTimer: ReturnType<typeof setTimeout> | undefined
const connector = ref(false)
const connectionPath = computed(() => {
  if (!highlight.value || !panel.value || props.mode === 'edge') return ''
  const p = panel.value.getBoundingClientRect(), h = highlight.value
  const x = props.side === 'right' ? p.left : p.right, y = p.top + Math.min(350, p.height/2)
  const tx = Math.max(8, Math.min(viewport.value.width-8, props.side === 'right' ? h.right : h.left)), ty = Math.max(8, Math.min(viewport.value.height-8,h.top+Math.min(h.height/2,80)))
  return `M ${x} ${y} C ${(x+tx)/2} ${y}, ${(x+tx)/2} ${ty}, ${tx} ${ty}`
})
const modal = computed(() => props.mode === 'focus' || (props.mode !== 'edge' && viewport.value.width < 768))
const sizeStyle = computed(() => ({ '--yl-width': `${props.width}px`, '--yl-vh': `${viewport.value.height}px`, '--yl-vtop': `${viewport.value.top}px` }))
const canChat = computed(() => store.capabilities?.configuration_status === 'configured' && store.capabilities.schema_status === 'ready')
const connectionLabel = computed(() => store.capabilities?.schema_status !== 'ready' ? '数据准备待完成' : !canChat.value ? '模型连接待配置' : store.capabilities?.connection_status === 'verified' ? '模型连接已验证' : '模型连接待验证')
const guide = computed(() => selectedArticle.value?.steps[guideIndex.value])
function resizeViewport() { viewport.value = { width: window.visualViewport?.width || innerWidth, height: window.visualViewport?.height || innerHeight, top: window.visualViewport?.offsetTop || 0 }; updateHighlight() }
function unlock() {
  releaseLock?.(); releaseLock = undefined
  const root = document.getElementById('app')
  if (root && originalInert !== undefined) root.inert = originalInert
  originalInert = undefined
}
watch(modal, async value => {
  unlock()
  if (value) {
    releaseLock = acquireBodyScrollLock()
    const root = document.getElementById('app'); if (root) { originalInert = root.inert; root.inert = true }
    await nextTick(); panel.value?.focus()
  }
}, { immediate: true })
watch(() => props.mode, async (value, previous) => {
  if (value !== 'edge' && previous === 'edge') { oldFocus = document.activeElement as HTMLElement; await store.refreshCapabilities(); await nextTick(); composer.value?.focus() }
  if (value === 'edge' && !previewing) { clearHighlight(); guideIndex.value = -1; tab.value = 'chat'; oldFocus?.focus() }
  if (value !== 'edge') previewing = false
})
watch(() => props.suspended, value => { if (value) { clearHighlight(); guideIndex.value = -1; previewing = false } })
watch(reducedMotion, value => { try { localStorage.setItem('yl-assistant-reduced-motion', String(value)) } catch { /* optional preference */ } })
watch(() => props.page, () => { useContext.value = true; help.value = []; selectedArticle.value = null; guideIndex.value = -1; clearHighlight(); if (tab.value !== 'chat') void loadHelp() }, { deep: true })
watch(() => store.selectedId, () => { draft.value = ''; resetAttachments(); showNew.value = false; nearBottom = true; void bottom() })
watch(() => store.messages.map(m => m.content_parts.map(p => p.text || '').join('')).join('').length, () => { if (nearBottom) void bottom(); else showNew.value = true })
async function bottom() { await nextTick(); if (scroller.value) scroller.value.scrollTop = scroller.value.scrollHeight; showNew.value = false; nearBottom = true }
function onScroll() { const el = scroller.value; if (el) nearBottom = el.scrollHeight-el.scrollTop-el.clientHeight < 90 }
async function loadHelp() {
  const g = ++helpGeneration, page = props.page
  helpError.value = ''
  if (!page) { help.value = []; helpError.value = '本页说明尚未接入。你仍可以自由提问。'; return }
  try { const result = await assistantApi.help(page); if (g === helpGeneration) help.value = result.items }
  catch (e) { if (g === helpGeneration) helpError.value = e instanceof Error ? e.message : '本页说明暂不可用。' }
}
async function showHelp() { tab.value = 'help'; await loadHelp() }
async function citation(id: string) {
  const g = ++helpGeneration
  try { const article = await assistantApi.article(id); if (g === helpGeneration) { selectedArticle.value = article; tab.value = 'help' } }
  catch (e) { localError.value = e instanceof Error ? e.message : '说明不可用。' }
}
async function pick() {
  tab.value = 'pick'; selectedArticle.value = null; await loadHelp()
  pickTargets.value = availableTargetIds().filter(id => help.value.some(a => a.anchor_id === id)).map(id => ({ id, label: help.value.find(a => a.anchor_id === id)?.title || id }))
  if (!pickTargets.value.length) helpError.value = '这个页面暂时没有可定位的已注册区域。可以查看本页说明或描述你的问题。'
}
async function locate(id: string) {
  try {
    // Only an audience-filtered article can supply a semantic target ID.
    const article = help.value.find(a => a.anchor_id === id) || (selectedArticle.value?.steps.some(s => s.anchor_id === id) ? selectedArticle.value : null)
    if (!article) throw new Error('这个目标没有当前可用的说明。')
    previewing = viewport.value.width < 768
    if (modal.value) { emit('mode', previewing ? 'edge' : 'side'); await nextTick() }
    highlightElement = await revealTarget(id); selectedArticle.value = article; tab.value = 'help'; updateHighlight()
    connector.value = true; clearTimeout(connectorTimer); connectorTimer = setTimeout(() => { connector.value = false }, 1800)
  } catch (e) { clearHighlight(); guideIndex.value = -1; if (previewing) emit('mode', 'side'); localError.value = e instanceof Error ? e.message : '无法定位。' }
}
function updateHighlight() {
  if (!highlightElement?.isConnected || !highlightElement.getClientRects().length) { clearHighlight(); return }
  highlight.value = highlightElement.getBoundingClientRect()
}
function clearHighlight() { highlightElement = null; highlight.value = null; connector.value = false }
function previewEscape(event: KeyboardEvent) { if (props.mode === 'edge' && highlight.value && event.key === 'Escape') { clearHighlight(); guideIndex.value = -1; previewing = false } }
function pickClick(event: MouseEvent) {
  if (tab.value !== 'pick' || (event.target as HTMLElement).closest('.yl-assistant')) return
  const target = (event.target as HTMLElement).closest<HTMLElement>('[data-yl-help]')
  event.preventDefault(); event.stopPropagation()
  if (target?.dataset.ylHelp && pickTargets.value.some(t => t.id === target.dataset.ylHelp)) void locate(target.dataset.ylHelp)
  else { localError.value = '这里还没有精确说明，可以描述你想问的内容。'; tab.value = 'help' }
}
async function guideStep(index: number) {
  guideIndex.value = index
  if (guide.value) await locate(guide.value.anchor_id)
  else clearHighlight()
}
function keydown(event: KeyboardEvent) {
  if (props.mode === 'edge' || event.isComposing) return
  if (event.key === 'Escape') {
    event.preventDefault(); event.stopPropagation()
    if (historyOpen.value || aboutOpen.value) { historyOpen.value = false; aboutOpen.value = false }
    else if (highlight.value || tab.value === 'pick') { clearHighlight(); guideIndex.value = -1; tab.value = 'help' }
    else emit('mode', props.mode === 'focus' ? 'side' : 'edge')
  }
  if (modal.value && event.key === 'Tab') {
    const elements = [...(panel.value?.querySelectorAll<HTMLElement>('button:not(:disabled),textarea:not(:disabled),input:not(:disabled),select,a[href],[tabindex="0"]') || [])].filter(el => !!el.getClientRects().length)
    const first = elements[0], last = elements.at(-1)
    if (event.shiftKey && (document.activeElement === first || document.activeElement === panel.value)) { event.preventDefault(); last?.focus() }
    else if (!event.shiftKey && document.activeElement === last) { event.preventDefault(); first?.focus() }
  }
}
async function send() {
  if (!draft.value.trim() || store.busy || uploading.value) return
  const input: Omit<SendPayload,'client_request_id'> = { text: draft.value, attachment_ids: attachments.value.map(a => a.id), profile_id: 'default', thinking: thinking.value, web_search: 'off',
    intent: selectedArticle.value ? 'explain_element' : tab.value === 'help' ? 'explain_page' : 'chat',
    page_context: useContext.value && props.page ? { ...props.page, ...(selectedArticle.value ? { help_id: selectedArticle.value.id } : {}) } : null }
  draft.value = ''; resetAttachments(); tab.value = 'chat'; nearBottom = true
  await store.submit(input)
}
function enter(event: KeyboardEvent) { if (event.key === 'Enter' && !event.shiftKey && !event.isComposing && event.keyCode !== 229) { event.preventDefault(); void send() } }
async function retry() {
  const run = store.currentRun
  if (!run?.payload.text) return
  await store.recover()
  if (activeStates.includes(run.state)) return
  await store.submit(run.payload, run.runId ? undefined : run.payload)
}
async function newChat() { await store.newSession(); historyOpen.value = false; tab.value = 'chat'; composer.value?.focus() }
async function exportChat() {
  const id = store.selectedId
  try {
    const blob = await assistantApi.export(id), url = URL.createObjectURL(blob)
    if (store.selectedId !== id) { URL.revokeObjectURL(url); return }
    const link = document.createElement('a'); link.href = url; link.download = '曜灵-完整会话.md'; link.click(); setTimeout(() => URL.revokeObjectURL(url), 1000)
  } catch (e) { localError.value = e instanceof Error ? e.message : '导出未完成。' }
}
async function rename(row: Conversation) { try { await store.rename(row, renameText.value); renameId.value = '' } catch (e) { localError.value = e instanceof Error ? e.message : '改名未完成。' } }
async function remove(row: Conversation) { try { await store.remove(row); deleteId.value = '' } catch (e) { localError.value = e instanceof Error ? e.message : '删除未完成。' } }
function resetAttachments() { attachments.value.forEach(a => URL.revokeObjectURL(a.url)); attachments.value = [] }
async function upload(files: File[]) {
  // Allow choosing the same file again after removal or a failed upload.
  if (fileInput.value) fileInput.value.value = ''
  if (!store.capabilities?.profiles[0]?.vision) { localError.value = '当前模型尚未验证图片理解。'; return }
  uploading.value = true
  try {
    const sid = store.selectedId || await store.newSession()
    if (!sid) return
    for (const file of files.slice(0, 8-attachments.value.length)) {
      const row = await assistantApi.upload(sid, file)
      if (sid !== store.selectedId) return
      attachments.value.push({ id: row.id, name: file.name, url: URL.createObjectURL(file) })
    }
  } catch (e) { localError.value = e instanceof Error ? e.message : '图片上传未完成。' }
  finally { uploading.value = false }
}
async function removeImage(index: number) { const image = attachments.value[index]; if (!image) return; try { await assistantApi.removeAttachment(image.id); URL.revokeObjectURL(image.url); attachments.value.splice(index,1) } catch (e) { localError.value = e instanceof Error ? e.message : '移除未完成。' } }
function paste(event: ClipboardEvent) { const files = [...(event.clipboardData?.files || [])]; if (files.length) { event.preventDefault(); void upload(files) } }
function pointerDown(event: PointerEvent, kind: 'drag' | 'resize') { if (event.button !== 0 || modal.value) return; pointer = { kind, x: event.clientX, width: props.width }; (event.currentTarget as HTMLElement).setPointerCapture(event.pointerId) }
function pointerMove(event: PointerEvent) {
  if (!pointer) return
  if (pointer.kind === 'resize') emit('width', Math.max(360, Math.min(600, pointer.width+(event.clientX-pointer.x)*(props.side === 'left' ? 1 : -1))))
  else if (Math.abs(event.clientX-pointer.x)>30) emit('side', event.clientX < innerWidth/2 ? 'left' : 'right')
}
onMounted(() => {
  try { reducedMotion.value = localStorage.getItem('yl-assistant-reduced-motion') === 'true' } catch { /* optional preference */ }
  window.addEventListener('keydown', previewEscape)
  oldFocus = document.activeElement as HTMLElement; resizeViewport()
  window.addEventListener('resize', resizeViewport); window.visualViewport?.addEventListener('resize', resizeViewport); window.visualViewport?.addEventListener('scroll', resizeViewport)
  window.addEventListener('scroll', updateHighlight, true); document.addEventListener('click', pickClick, true)
  void store.history(); void nextTick(() => composer.value?.focus())
})
onUnmounted(() => { helpGeneration++; clearTimeout(connectorTimer); window.removeEventListener('keydown', previewEscape); unlock(); resetAttachments(); window.removeEventListener('resize', resizeViewport); window.visualViewport?.removeEventListener('resize', resizeViewport); window.visualViewport?.removeEventListener('scroll', resizeViewport); window.removeEventListener('scroll', updateHighlight, true); document.removeEventListener('click', pickClick, true) })
</script>
<template>
  <div :class="{ 'yl-reduced': reducedMotion }">
    <div v-if="modal" class="yl-backdrop" @click="emit('mode', 'side')" />
    <section v-show="mode !== 'edge'" ref="panel" class="yl-panel" :class="{ 'yl-focus': mode === 'focus', 'yl-mobile': viewport.width < 768 }" :style="sizeStyle" role="dialog" :aria-modal="modal || undefined" aria-label="曜灵 · Nexus AI" tabindex="-1" @keydown="keydown">
      <header class="yl-header">
        <div class="yl-header-top"><AssistantCore :active="store.anyBusy" /><div class="yl-brand"><strong>曜灵</strong><span>Nexus AI</span></div>
          <div class="yl-header-actions"><button aria-label="历史会话" title="历史会话" @click="historyOpen = !historyOpen; store.history()"><History :size="18" /></button><button aria-label="新建对话" title="新建对话" :disabled="store.creating || store.capabilities?.schema_status !== 'ready'" @click="newChat"><Plus :size="19" /></button><button :aria-label="mode === 'focus' ? '退出专注阅读' : '专注阅读'" @click="emit('mode', mode === 'focus' ? 'side' : 'focus')"><Minimize2 v-if="mode === 'focus'" :size="17" /><Maximize2 v-else :size="17" /></button><button aria-label="收起曜灵" @click="emit('mode', 'edge')"><Minus :size="20" /></button></div>
        </div>
        <div class="yl-header-bottom"><span class="yl-connection"><i />{{ store.currentRun && store.busy ? stateLabels[store.currentRun.state] : connectionLabel }}</span><button class="yl-drag" aria-label="拖动舱头，或按左右方向键停靠" @pointerdown="pointerDown($event, 'drag')" @pointermove="pointerMove" @pointerup="pointer = null" @pointercancel="pointer = null" @keydown.left="emit('side', 'left')" @keydown.right="emit('side', 'right')"><GripVertical :size="14" />拖动停靠</button><button aria-label="关于与连接状态" @click="aboutOpen = !aboutOpen"><Info :size="16" /></button></div>
      </header>
      <div v-if="page && useContext" class="yl-context"><span>当前页面</span><b>{{ pageTitle }}</b><button aria-label="移除页面上下文" @click="useContext = false; selectedArticle = null"><X :size="13" /></button></div>
      <div v-else class="yl-context"><span>自由交流</span><b>从你的问题开始</b><button v-if="page" @click="useContext = true">带上本页</button></div>
      <nav class="yl-tabs" aria-label="助手能力"><button :class="{ active: tab === 'chat' }" @click="tab = 'chat'">聊一聊</button><button :class="{ active: tab === 'help' }" @click="showHelp">讲解本页</button><button :class="{ active: tab === 'pick' }" @click="pick"><MapPin :size="14" />指给我看</button></nav>
      <div ref="scroller" class="yl-scroll" @scroll="onScroll">
        <div v-if="tab === 'chat' && !store.messages.length && !store.loading" class="yl-welcome">
          <div class="yl-welcome-core"><AssistantCore /></div><h2>让思路，亮起来。</h2><p>我是曜灵。可以陪你想问题，<br>也可以带你看懂这个页面。</p>
          <div class="yl-welcome-actions"><button @click="showHelp"><span>看懂当前页面<small>字段、状态与操作步骤</small></span><ChevronRight :size="17" /></button><button @click="draft = '帮我写一封友好的邀请函'; composer?.focus()"><span>一起想点东西<small>写作、学习、代码与灵感</small></span><ChevronRight :size="17" /></button><button @click="pick"><span>解释这个地方<small>选择一个已注册的页面元素</small></span><MapPin :size="17" /></button></div>
          <p v-if="!canChat" class="yl-unconfigured">曜灵的模型连接尚未完成。<br>你仍可查看本页操作说明。</p>
        </div>
        <template v-if="tab === 'chat'">
          <button v-if="store.cursors[store.selectedId]" class="yl-load-more" @click="store.selectSession(store.selectedId, true)">加载更早的消息</button>
          <p v-if="store.loading" class="yl-muted">正在读取对话…</p>
          <AssistantMessage v-for="message in store.messages" :key="message.id" :message="message" @citation="citation" />
          <p v-if="store.currentRun?.omittedTurns" class="yl-notice">本轮使用近期完整对话，{{ store.currentRun.omittedTurns }} 轮较早内容未发送给模型；完整记录仍可导出。</p>
          <div v-if="store.currentRun?.error" class="yl-run-notice" role="status"><strong>{{ stateLabels[store.currentRun.state] }}</strong><p>{{ store.currentRun.error }}</p><div><button @click="store.recover()">查询保存结果</button><button v-if="!store.busy && store.currentRun.payload.text && store.currentRun.retryable" @click="retry">重试生成</button></div></div>
        </template>
        <section v-else class="yl-help">
          <h2>{{ tab === 'pick' ? '指一个地方，我来解释' : '把这一页，讲清楚' }}</h2><p class="yl-muted">说明来自维护过的系统规则，不包含实际订单、价格或产量。</p>
          <p v-if="helpError" class="yl-notice">{{ helpError }}</p>
          <template v-if="tab === 'pick'"><p>可以点击页面已注册区域，或使用下列键盘可达的目标。</p><button v-for="target in pickTargets" :key="target.id" class="yl-help-target" @click="locate(target.id)"><MapPin :size="16" />{{ target.label }}</button><button @click="tab = 'help'">退出选择</button></template>
          <template v-else>
            <button v-if="selectedArticle" class="yl-text-button" @click="selectedArticle = null">返回本页说明</button>
            <article v-for="article in selectedArticle ? [selectedArticle] : help" :key="article.id" class="yl-help-card">
              <small>{{ article.status === 'verified' ? '已核对说明' : '部分说明待核对' }}</small><h3>{{ article.title }}</h3><p>{{ article.summary }}</p><div class="yl-help-content">{{ article.content }}</div><footer><span>{{ article.source_label }}</span><button @click="selectedArticle = article; locate(article.anchor_id)"><MapPin :size="14" />定位</button></footer><div class="yl-help-actions"><button @click="selectedArticle = article; draft = `请详细解释：${article.title}`; tab = 'chat'; composer?.focus()">继续追问</button><button v-if="article.steps.length" @click="selectedArticle = article; guideStep(0)">带我看一遍</button></div>
            </article>
          </template>
        </section>
      </div>
      <button v-if="showNew && tab === 'chat'" class="yl-new-content" @click="bottom">有新内容 <ArrowDown :size="14" /></button>
      <div v-if="localError || store.error" role="status" class="yl-error"><span>{{ localError || store.error }}</span><button aria-label="关闭提示" @click="localError = ''; store.error = ''"><X :size="14" /></button></div>
      <form class="yl-composer" @submit.prevent="send">
        <div v-if="attachments.length" class="yl-attachments"><figure v-for="(image,index) in attachments" :key="image.id"><img :src="image.url" :alt="image.name" /><button type="button" aria-label="移除图片" @click="removeImage(index)"><X :size="13" /></button></figure></div>
        <textarea ref="composer" v-model="draft" rows="2" aria-label="给曜灵的问题" placeholder="随便问我，或让我讲解当前页面……" @keydown="enter" @paste="paste" />
        <div class="yl-composer-actions"><div><button v-if="store.capabilities?.profiles[0]?.vision" type="button" aria-label="上传图片" :disabled="uploading" @click="fileInput?.click()"><ImagePlus :size="18" /></button><input ref="fileInput" hidden type="file" accept="image/png,image/jpeg,image/webp" multiple @change="upload(Array.from(($event.target as HTMLInputElement).files || []))" /><select v-if="store.capabilities?.profiles[0]?.thinking === 'toggle'" v-model="thinking" aria-label="思考模式"><option value="auto">自动思考</option><option value="on">深度思考</option><option value="off">直接回答</option></select><span v-else class="yl-muted">{{ store.capabilities?.profiles[0]?.thinking === 'always' ? '深度思考' : '自由提问' }}</span></div><button v-if="store.busy" type="button" class="yl-send" aria-label="停止生成" @click="store.stop()"><Square :size="17" /></button><button v-else class="yl-send" type="submit" aria-label="发送问题" :disabled="!draft.trim() || !canChat || uploading || store.creating"><ArrowUp :size="21" /></button></div>
        <p class="yl-disclosure">消息、主动上传的图片及选用的说明会交给配置的模型服务。</p>
      </form>
      <div v-if="historyOpen" class="yl-inner-layer"><header><h2>你的对话</h2><button aria-label="关闭历史" @click="historyOpen = false"><X :size="18" /></button></header><button class="yl-primary" @click="newChat">开启新对话 <Plus :size="17" /></button><div class="yl-history-list"><article v-for="row in store.sessions" :key="row.id"><template v-if="renameId === row.id"><input v-model="renameText" aria-label="对话名称" maxlength="160" @keydown.enter="rename(row)" /><button @click="rename(row)">保存</button><button @click="renameId = ''">取消</button></template><template v-else><button class="yl-history-title" :disabled="row.deletion_state !== 'active'" @click="store.selectSession(row.id); historyOpen = false; tab = 'chat'"><strong>{{ row.title }}</strong><small>{{ row.deletion_state === 'pending' ? '正在删除，稍后刷新重试清理' : new Date(row.updated_at*1000).toLocaleString('zh-CN') }}</small></button><button aria-label="重命名对话" @click="renameId = row.id; renameText = row.title"><Pencil :size="15" /></button><button aria-label="删除对话" @click="deleteId = row.id"><Trash2 :size="15" /></button></template><div v-if="deleteId === row.id" class="yl-delete-confirm"><p>删除此对话和附件？生成会同时停止。</p><button @click="remove(row)">确认删除</button><button @click="deleteId = ''">保留</button></div></article><p v-if="!store.sessions.length" class="yl-muted">还没有对话，从一个问题开始。</p></div><button v-if="store.historyCursor" @click="store.history(true)">更多历史</button><button v-if="store.selectedId" class="yl-export" @click="exportChat"><Download :size="16" />导出当前完整会话 Markdown</button></div>
      <div v-if="aboutOpen" class="yl-inner-layer"><header><h2>关于曜灵</h2><button aria-label="关闭关于" @click="aboutOpen = false"><X :size="18" /></button></header><AssistantCore /><h3>曜灵 · Nexus AI</h3><p>可以自由交流，也可以讲解有依据的系统规则。</p><dl><dt>模型服务</dt><dd>千问 · OpenAI 兼容协议</dd><dt>实际模型</dt><dd>{{ store.capabilities?.model || '尚未配置' }}</dd><dt>连接</dt><dd>{{ connectionLabel }}</dd><dt>联网与图片</dt><dd>{{ store.capabilities?.profiles[0]?.vision ? '图片已验证；联网暂不可用' : '尚未验证，暂不可用' }}</dd></dl><p>不会自动抓取整页内容。这里的说明不代表读取了实际订单、价格或生产数据。独立图片翻译应用暂未接入此入口。</p><label><input v-model="reducedMotion" type="checkbox" /> 减少装饰动效</label><button @click="emit('side', side === 'left' ? 'right' : 'left')"><PanelLeftClose :size="16" />移到{{ side === 'right' ? '左' : '右' }}侧</button><button @click="store.refreshCapabilities()">刷新连接状态</button></div>
      <div v-if="!modal" class="yl-resize" role="separator" aria-label="调整曜灵宽度" aria-orientation="vertical" :aria-valuenow="width" aria-valuemin="360" aria-valuemax="600" tabindex="0" @pointerdown="pointerDown($event,'resize')" @pointermove="pointerMove" @pointerup="pointer = null" @pointercancel="pointer = null" @keydown.left.prevent="emit('width',Math.max(360,width-20))" @keydown.right.prevent="emit('width',Math.min(600,width+20))" />
    </section>
    <div v-if="highlight" class="yl-target-outline" :style="{ left: `${Math.max(0,highlight.left-4)}px`, top: `${Math.max(0,highlight.top-4)}px`, width: `${Math.min(viewport.width,highlight.width+8)}px`, height: `${Math.min(viewport.height,highlight.height+8)}px` }" aria-hidden="true" />
    <svg v-if="connector && connectionPath && !reducedMotion" class="yl-connector" aria-hidden="true"><path :d="connectionPath" /></svg>
    <div v-if="guide" class="yl-guide" role="region" aria-label="页面操作引导"><strong>{{ guideIndex+1 }} · {{ guide.title }}</strong><p>{{ guide.description }}</p><small>{{ guide.precondition }} · {{ guide.completion }}</small><div><button :disabled="guideIndex === 0" @click="guideStep(guideIndex-1)">上一步</button><button @click="guideStep(guideIndex+1)">{{ guideIndex+1 === selectedArticle?.steps.length ? '完成引导' : '下一步 / 跳过' }}</button><button @click="guideIndex = -1; clearHighlight()">退出</button></div></div>
    <div v-else-if="highlight && mode === 'edge'" class="yl-guide"><strong>{{ selectedArticle?.title }}</strong><div><button @click="emit('mode','side')">返回说明</button><button @click="clearHighlight()">结束定位</button></div></div>
  </div>
</template>
