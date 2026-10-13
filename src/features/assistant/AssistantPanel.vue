<script setup lang="ts">
import { computed, nextTick, onMounted, onUnmounted, ref, watch } from 'vue'
import { ArrowUp, Square, Minus, Maximize2, Minimize2, History, Plus, Info, X, MapPin, ArrowDown, Download, Trash2, Pencil, PanelLeftClose, ImagePlus, GripVertical, RotateCcw, Globe, BriefcaseBusiness, FileText, Paperclip, BookOpen, Bookmark, Star } from '@lucide/vue'
import { useAssistantStore } from '@/stores/assistant'
import { acquireBodyScrollLock } from '@/lib/bodyScrollLock'
import { assistantApi } from './api'
import { availableTargetIds, revealTarget } from './anchors'
import { assistantSelection } from './selection'
import { activeStates, stateLabels, type Conversation, type HelpArticle, type PageContext, type PanelMode, type SendPayload } from './types'
import AssistantCore from './AssistantCore.vue'
import AssistantMessage from './AssistantMessage.vue'
import AssistantSources from './AssistantSources.vue'
import AssistantArtifacts from './AssistantArtifacts.vue'
import type { EvidencePart } from './v2'
import { clamp, defaultPanelHeight, panelBounds, panelMargin, type PanelPosition } from './layout'
const props = withDefaults(defineProps<{ mode: PanelMode; side: 'left' | 'right'; width: number; height?: number; position?: PanelPosition | null; focusOnOpen?: boolean; page: PageContext | null; pageTitle: string; suspended?: boolean }>(), { focusOnOpen: true })
const emit = defineEmits<{ mode: [PanelMode]; side: ['left' | 'right']; width: [number]; height: [number]; position: [PanelPosition | null]; 'layout-end': []; 'pointer-enter': [PointerEvent]; 'pointer-leave': [PointerEvent]; 'focus-change': [boolean] }>()
const store = useAssistantStore(), panel = ref<HTMLElement>(), scroller = ref<HTMLElement>(), composer = ref<HTMLTextAreaElement>()
const draft = computed({get: () => store.draftFor().text, set: value => { store.draftFor().text = value }}), tab = ref<'chat' | 'help' | 'pick'>('chat'), historyOpen = ref(false), aboutOpen = ref(false)
const help = ref<HelpArticle[]>([]), helpError = ref(''), selectedArticle = ref<HelpArticle | null>(null)
const localError = ref(''), useContext = ref(true), thinking = ref<'auto' | 'on' | 'off'>('auto'), showNew = ref(false)
const useSelection = ref(true)
const selection = computed(() => useContext.value ? assistantSelection(props.page?.module_id) : null)
const attachments = computed({ get: () => store.draftFor().attachments, set: value => { store.draftFor().attachments = value } }), uploading = ref(false), fileInput = ref<HTMLInputElement>()
const documents = computed(() => store.draftFor().documents), documentInput = ref<HTMLInputElement>()
const search = ref<'off'|'auto'|'on'>('off'), publicQuery = ref(''), intent = ref<SendPayload['intent']>('chat')
const sourcesOpen = ref(false), artifactsOpen = ref(false), artifactId = ref(''), selectedEvidence = ref<EvidencePart | null>(null)
const latestEvidence = computed(() => { const all=[...store.messages].reverse().flatMap(m=>m.content_parts).filter(p=>p.type==='evidence') as unknown as EvidencePart[]; return all.find(e=>e.run_id===selectedEvidence.value?.run_id) || all[0] || null })
let layerTrigger: HTMLElement | null = null
function closeLayers() { sourcesOpen.value=false; artifactsOpen.value=false; historyOpen.value=false; aboutOpen.value=false; void nextTick(() => layerTrigger?.isConnected ? layerTrigger.focus() : composer.value?.focus()) }
function showSources(value?: EvidencePart) { layerTrigger=document.activeElement as HTMLElement; if(value) selectedEvidence.value=value; sourcesOpen.value=true }
function showArtifacts(id='') { layerTrigger=document.activeElement as HTMLElement; artifactId.value=id; artifactsOpen.value=true }
watch([sourcesOpen, artifactsOpen, historyOpen, aboutOpen], async ([s,a,h,b]) => { if(s||a||h||b) { if (!(document.activeElement as HTMLElement)?.closest('.yl-inner-layer')) layerTrigger=document.activeElement as HTMLElement; await nextTick(); panel.value?.querySelector<HTMLElement>('.yl-inner-layer button')?.focus() } })
watch(draft, async () => { await nextTick(); if(composer.value) { composer.value.style.height='auto'; composer.value.style.height=Math.min(168,composer.value.scrollHeight)+'px' } })
const viewport = ref({ width: innerWidth, height: innerHeight, top: 0, left: 0 }), reducedMotion = ref(false)
const pickTargets = ref<{ id: string; label: string }[]>([]), highlight = ref<DOMRect | null>(null), guideIndex = ref(-1)
const renameId = ref(''), renameText = ref(''), deleteId = ref('')
let nearBottom = true, helpGeneration = 0, highlightElement: HTMLElement | null = null
let releaseLock: (() => void) | undefined, originalInert: boolean | undefined, oldFocus: HTMLElement | null = null
let pointer: { kind: 'drag' | 'resize' | 'corner'; id: number; target: HTMLElement; x: number; y: number; bounds: ReturnType<typeof panelBounds>; moved: boolean } | null = null
const manipulating = ref(false)
let previewing = false, connectorTimer: ReturnType<typeof setTimeout> | undefined
let keyboardNavigation = true
const connector = ref(false)
const connectionPath = computed(() => {
  if (!highlight.value || !panel.value || props.mode === 'edge') return ''
  const p = panel.value.getBoundingClientRect(), h = highlight.value
  const x = props.side === 'right' ? p.left : p.right, y = p.top + Math.min(350, p.height/2)
  const tx = Math.max(8, Math.min(viewport.value.width-8, props.side === 'right' ? h.right : h.left)), ty = Math.max(8, Math.min(viewport.value.height-8,h.top+Math.min(h.height/2,80)))
  return `M ${x} ${y} C ${(x+tx)/2} ${y}, ${(x+tx)/2} ${ty}, ${tx} ${ty}`
})
const modal = computed(() => props.mode === 'focus' || (props.mode !== 'edge' && viewport.value.width < 768))
const bounds = computed(() => panelBounds(viewport.value, props.width, props.height ?? defaultPanelHeight, props.position, props.side))
const sizeStyle = computed(() => ({ '--yl-width': `${bounds.value.width}px`, '--yl-height': `${bounds.value.height}px`, '--yl-vh': `${viewport.value.height}px`, '--yl-vtop': `${viewport.value.top}px`,
  ...(!modal.value ? { left: `${bounds.value.x}px`, top: `${bounds.value.y}px`, right: 'auto' } : {}) }))
const canChat = computed(() => store.capabilities?.configuration_status === 'configured' && store.capabilities.schema_status === 'ready')
const connectionLabel = computed(() => store.capabilities?.schema_status !== 'ready' ? '数据准备待完成' : !canChat.value ? '模型连接待配置' : store.capabilities?.connection_status === 'verified' ? '模型连接已验证' : '模型连接待验证')
const guide = computed(() => selectedArticle.value?.steps[guideIndex.value])
function resizeViewport() { pointerEnd(); viewport.value = { width: window.visualViewport?.width || innerWidth, height: window.visualViewport?.height || innerHeight, top: window.visualViewport?.offsetTop || 0, left: window.visualViewport?.offsetLeft || 0 }; updateHighlight() }
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
  pointerEnd()
  if (value !== 'edge' && previous === 'edge') {
    oldFocus = document.activeElement as HTMLElement
    await store.refreshCapabilities(); await nextTick()
    if (props.mode !== 'edge') {
      // A hidden scroller has zero dimensions; reveal first, then follow the
      // answer that arrived in the background unless the reader scrolled up.
      if (nearBottom) await bottom()
      if (props.focusOnOpen !== false) composer.value?.focus()
    }
  }
  if (value === 'edge' && !previewing) { clearHighlight(); guideIndex.value = -1; tab.value = 'chat'; if (panel.value?.contains(document.activeElement)) oldFocus?.focus() }
  if (value !== 'edge') previewing = false
})
watch(() => props.suspended, value => { if (value) { clearHighlight(); guideIndex.value = -1; previewing = false } })
watch(reducedMotion, value => { try { localStorage.setItem('yl-assistant-reduced-motion', String(value)) } catch { /* optional preference */ } })
watch(() => props.page, () => { useContext.value = true; useSelection.value=true; help.value = []; selectedArticle.value = null; guideIndex.value = -1; clearHighlight(); if (tab.value !== 'chat') void loadHelp() }, { deep: true })
watch(() => store.selectedId, () => { selectedEvidence.value=null; showNew.value = false; nearBottom = true; void bottom() })
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
  pickTargets.value = availableTargetIds().filter(id => help.value.some(a => a.anchor_id === id || a.steps.some(s => s.anchor_id === id))).map(id => ({ id, label: help.value.flatMap(a => a.steps).find(s => s.anchor_id === id)?.title || help.value.find(a => a.anchor_id === id)?.title || id }))
  if (!pickTargets.value.length) helpError.value = '这个页面暂时没有可定位的已注册区域。可以查看本页说明或描述你的问题。'
}
async function locate(id: string) {
  try {
    // Only an audience-filtered article can supply a semantic target ID.
    const article = selectedArticle.value?.steps.some(s => s.anchor_id === id) ? selectedArticle.value : help.value.find(a => a.anchor_id === id || a.steps.some(s => s.anchor_id === id))
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
function previewEscape(event: KeyboardEvent) { if (event.key === 'Tab') keyboardNavigation = true; if (props.mode === 'edge' && highlight.value && event.key === 'Escape') { clearHighlight(); guideIndex.value = -1; previewing = false } }
function updateFocus(target: EventTarget | null) {
  emit('focus-change', target instanceof HTMLElement && !!panel.value?.contains(target) && (keyboardNavigation || !!target.closest('input,textarea,select,[contenteditable="true"]')))
}
function pointerFocus() { keyboardNavigation = false; updateFocus(document.activeElement) }
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
  keyboardNavigation = true; updateFocus(document.activeElement)
  if (event.key === 'Escape') {
    event.preventDefault(); event.stopPropagation()
    if (historyOpen.value || aboutOpen.value || sourcesOpen.value || artifactsOpen.value) closeLayers()
    else if (highlight.value || tab.value === 'pick') { clearHighlight(); guideIndex.value = -1; tab.value = 'help' }
    else emit('mode', props.mode === 'focus' ? 'side' : 'edge')
  }
  if ((modal.value || historyOpen.value || aboutOpen.value || sourcesOpen.value || artifactsOpen.value) && event.key === 'Tab') {
    const scope=panel.value?.querySelector<HTMLElement>('.yl-inner-layer') || panel.value
    const elements = [...(scope?.querySelectorAll<HTMLElement>('button:not(:disabled),textarea:not(:disabled),input:not(:disabled),select,a[href],[tabindex="0"]') || [])].filter(el => !!el.getClientRects().length)
    const first = elements[0], last = elements.at(-1)
    if (event.shiftKey && (document.activeElement === first || document.activeElement === panel.value)) { event.preventDefault(); last?.focus() }
    else if (!event.shiftKey && document.activeElement === last) { event.preventDefault(); first?.focus() }
  }
}
async function send() {
  if (!draft.value.trim() || store.busy || uploading.value) return
  if(documents.value.some(d => d.parse_status !== 'ready')) { localError.value='资料还未解析完成，请刷新资料状态或移除失败文件。'; return }
  const savedDraft=store.draftFor(), originalText=draft.value, savedImages=[...attachments.value], savedDocuments=[...documents.value], generation=store.identityGeneration
  const selected = useSelection.value ? selection.value : null
  const context = selected || publicQuery.value.trim() ? {selection_id:selected?.selection_id || 'public-query',resources:selected?.resources || [],filters:{...selected?.filters,...(publicQuery.value.trim() ? {public_query:publicQuery.value} : {})}} : null
  const input: Omit<SendPayload,'client_request_id'> = { protocol_version:2, text: draft.value, document_ids:documents.value.map(d => d.id), attachment_ids: attachments.value.map(a => a.id), profile_id: 'default', thinking: thinking.value, web_search: search.value,
    context_selection:context,
    intent: selectedArticle.value ? 'explain_element' : tab.value === 'help' ? 'explain_page' : intent.value,
    page_context: useContext.value && props.page ? { ...props.page, ...(selectedArticle.value ? { help_id: selectedArticle.value.id } : {}) } : null }
  savedDraft.text=''; savedDraft.attachments=[]; savedDraft.documents=[]; tab.value = 'chat'; nearBottom = true
  const submitted=store.submit(input)
  // Sending replaces the focused send button with Stop; keep keyboard focus in
  // the dialog so Escape and Tab continue to work during streaming.
  await nextTick()
  if(generation===store.identityGeneration && props.mode!=='edge') composer.value?.focus()
  await submitted
  if(generation!==store.identityGeneration) return
  if(store.currentRun?.state==='failed' && !store.currentRun.runId) { const target=store.draftFor(); if(!target.text) { target.text=originalText; target.attachments=savedImages; target.documents=savedDocuments } }
  else savedImages.forEach(a=>URL.revokeObjectURL(a.url))
  if(search.value==='on') search.value=store.capabilities?.search?.supported_modes.includes('auto') ? 'auto' : 'off'
  intent.value='chat'
}
function enter(event: KeyboardEvent) { if (event.key === 'Enter' && !event.shiftKey && !event.isComposing && event.keyCode !== 229) { event.preventDefault(); void send() } }
async function retry() {
  const run = store.currentRun
  if (!run?.payload.text) return
  await store.recover()
  if (activeStates.includes(run.state)) return
  await store.submit(run.payload, run.runId ? undefined : run.payload)
}
async function newChat() { await store.newSession(); historyOpen.value = false; tab.value = 'chat'; intent.value='chat'; composer.value?.focus() }
async function older() { const el=scroller.value; if(!el) return; const top=el.scrollTop, height=el.scrollHeight; const follow=nearBottom; nearBottom=false; await store.selectSession(store.selectedId,true); await nextTick(); el.scrollTop=top+el.scrollHeight-height; nearBottom=follow }
function suggestion(kind: SendPayload['intent']) { intent.value=kind; if(kind==='explain_page') { void showHelp(); return }; if(kind==='analyze_files') { documentInput.value?.click(); return }; if(kind==='research' && store.capabilities?.search?.supported_modes.includes('auto')) search.value='auto'; draft.value=kind==='my_work' ? '请查询当前范围的工作，说明已确认事实、未知信息和下一步。' : '请查一下千问官方联网搜索如何返回来源。'; composer.value?.focus() }
async function favorite(row: Conversation) { try { await assistantApi.favorite(row.id,!row.favorite); row.favorite=!row.favorite } catch(e) { localError.value=e instanceof Error ? e.message : '收藏失败' } }
function reviseLast() { const question=[...store.messages].reverse().find(m=>m.role==='user'); if(question) { draft.value=question.content_parts.filter(p=>p.type==='text').map(p=>p.text||'').join(''); composer.value?.focus() } }
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
  const generation=store.identityGeneration, caret=composer.value?.selectionStart
  try {
    const sid = store.selectedId || await store.newSession(true)
    if (!sid) return
    const target=store.draftFor(sid)
    for (const file of files.slice(0, 8-target.attachments.length)) {
      const row = await assistantApi.upload(sid, file)
      if (generation!==store.identityGeneration) return
      target.attachments.push({ id: row.id, name: file.name, url: URL.createObjectURL(file) })
    }
    if(sid===store.selectedId && caret!==undefined) { await nextTick(); composer.value?.setSelectionRange(caret,caret) }
  } catch (e) { localError.value = e instanceof Error ? e.message : '图片上传未完成。' }
  finally { uploading.value = false }
}
async function uploadDocuments(selected: File[]) {
  if(documentInput.value) documentInput.value.value=''
  const generation=store.identityGeneration
  uploading.value=true
  try { const sid=store.selectedId || await store.newSession(true); if(!sid || generation!==store.identityGeneration) return; const target=store.draftFor(sid)
    for(const file of selected.slice(0,8-target.documents.length)) { const value=await assistantApi.uploadDocument(sid,file); if(generation!==store.identityGeneration) return; target.documents.push(value) }
    if(!target.text) target.text='请分析这些文件，引用具体页码或行号，整理主要发现。'
    intent.value='analyze_files'; await refreshDocuments()
  } catch(e) { localError.value=e instanceof Error ? e.message : '上传失败' } finally { uploading.value=false }
}
let documentTimer: ReturnType<typeof setTimeout> | undefined, documentGeneration=0
const pendingDocuments = () => documents.value.some(d => d.parse_status==='queued' || d.parse_status==='parsing')
function scheduleDocuments(token:number) {
  clearTimeout(documentTimer)
  if(token===documentGeneration && props.mode!=='edge' && pendingDocuments()) documentTimer=setTimeout(() => { void refreshDocuments() },1000)
}
watch(() => [store.identityGeneration,store.selectedId,props.mode,documents.value.map(d=>`${d.id}:${d.parse_status}`).join(',')], () => scheduleDocuments(++documentGeneration), {immediate:true})
onUnmounted(() => { documentGeneration++; clearTimeout(documentTimer) })
async function refreshDocuments() {
  clearTimeout(documentTimer)
  const token=++documentGeneration, generation=store.identityGeneration, target=store.draftFor(), sid=store.selectedId
  const current=() => token===documentGeneration && generation===store.identityGeneration && sid===store.selectedId
  try {
    for(const d of [...target.documents]) {
      try { const value=await assistantApi.document(d.id); if(!current()) return; if(target.documents.includes(d)) Object.assign(d,value) }
      catch(e) { if(current()) localError.value=e instanceof Error ? e.message : '资料状态不可用' }
    }
  } finally { if(current()) scheduleDocuments(token) }
}
async function removeDocument(id:string) {
  const target=store.draftFor(), generation=store.identityGeneration
  try { await assistantApi.removeDocument(id); if(generation===store.identityGeneration) target.documents=target.documents.filter(d=>d.id!==id) }
  catch(e) { if(generation===store.identityGeneration) localError.value=e instanceof Error ? e.message : '删除失败' }
}
async function removeImage(index: number) { const image = attachments.value[index]; if (!image) return; try { await assistantApi.removeAttachment(image.id); URL.revokeObjectURL(image.url); attachments.value.splice(index,1) } catch (e) { localError.value = e instanceof Error ? e.message : '移除未完成。' } }
function paste(event: ClipboardEvent) { const files = [...(event.clipboardData?.files || [])]; if (files.length) { event.preventDefault(); void upload(files) } }
function pointerDown(event: PointerEvent, kind: 'drag' | 'resize' | 'corner') {
  if (event.button !== 0 || modal.value || props.mode === 'edge' || pointer) return
  if (kind === 'drag' && (event.target as Element).closest('button:not(.yl-drag),input,textarea,select,a')) return
  event.preventDefault()
  const target = event.currentTarget as HTMLElement
  pointer = { kind, id: event.pointerId, target, x: event.clientX, y: event.clientY, bounds: { ...bounds.value }, moved: false }
  target.setPointerCapture(event.pointerId)
}
function pointerMove(event: PointerEvent) {
  if (!pointer || pointer.id !== event.pointerId) return
  const dx = event.clientX - pointer.x, dy = event.clientY - pointer.y, b = pointer.bounds
  if (!pointer.moved && Math.hypot(dx, dy) < 4) return
  pointer.moved = true; manipulating.value = true
  if (pointer.kind === 'drag') {
    const next = panelBounds(viewport.value, b.width, b.height, { x: b.x + dx, y: b.y + dy }, props.side)
    emit('position', { x: next.x, y: next.y })
  } else {
    const fromLeft = pointer.kind === 'resize' && props.side === 'right'
    const maxWidth = fromLeft ? b.x + b.width - viewport.value.left - panelMargin : viewport.value.left + viewport.value.width - panelMargin - b.x
    const width = clamp(b.width + dx * (fromLeft ? -1 : 1), 360, Math.min(600, maxWidth))
    emit('width', width)
    emit('position', { x: fromLeft ? b.x + b.width - width : b.x, y: b.y })
    if (pointer.kind === 'corner') emit('height', clamp(b.height + dy, Math.min(360, viewport.value.height - panelMargin * 2), Math.min(820, viewport.value.top + viewport.value.height - panelMargin - b.y)))
  }
}
function pointerEnd(event?: PointerEvent) {
  if (!pointer || (event && pointer.id !== event.pointerId)) return
  const finished = pointer; pointer = null; manipulating.value = false
  if (finished.target.hasPointerCapture(finished.id)) finished.target.releasePointerCapture(finished.id)
  if (finished.moved) {
    const b = bounds.value
    emit('side', b.x + b.width / 2 < viewport.value.left + viewport.value.width / 2 ? 'left' : 'right')
    // Snap only near an edge, after releasing the pointer.
    const left = viewport.value.left + panelMargin, right = viewport.value.left + viewport.value.width - panelMargin - b.width
    if (finished.kind === 'drag' && event?.type === 'pointerup') emit('position', { x: b.x - left < 16 ? left : right - b.x < 16 ? right : b.x, y: b.y })
    emit('layout-end')
  }
}
function resetLayout() {
  emit('position', null); emit('side', 'right'); emit('width', 460); emit('height', defaultPanelHeight); emit('layout-end')
}
function switchSide() {
  const side = props.side === 'right' ? 'left' : 'right'
  emit('side', side)
  emit('position', { x: side === 'left' ? viewport.value.left + panelMargin : viewport.value.left + viewport.value.width - panelMargin - bounds.value.width, y: bounds.value.y })
  emit('layout-end')
}
function layoutKey(event: KeyboardEvent, resize = false) {
  if (modal.value) return
  if (event.key === 'Home') { event.preventDefault(); resetLayout(); return }
  if (!['ArrowLeft', 'ArrowRight', 'ArrowUp', 'ArrowDown'].includes(event.key)) return
  event.preventDefault()
  const step = event.shiftKey ? 50 : 20, b = bounds.value
  const dx = event.key === 'ArrowLeft' ? -step : event.key === 'ArrowRight' ? step : 0
  const dy = event.key === 'ArrowUp' ? -step : event.key === 'ArrowDown' ? step : 0
  if (resize) {
    const width = clamp(b.width + dx, 360, Math.min(600, viewport.value.left + viewport.value.width - panelMargin - b.x))
    const height = clamp(b.height + dy, Math.min(360, viewport.value.height - panelMargin * 2), Math.min(820, viewport.value.top + viewport.value.height - panelMargin - b.y))
    emit('width', width); emit('height', height); emit('position', { x: b.x, y: b.y })
  } else {
    const next = panelBounds(viewport.value, b.width, b.height, { x: b.x + dx, y: b.y + dy }, props.side)
    emit('position', { x: next.x, y: next.y }); emit('side', next.x + b.width / 2 < viewport.value.left + viewport.value.width / 2 ? 'left' : 'right')
  }
  emit('layout-end')
}
onMounted(() => {
  try { reducedMotion.value = localStorage.getItem('yl-assistant-reduced-motion') === 'true' } catch { /* optional preference */ }
  window.addEventListener('keydown', previewEscape)
  oldFocus = document.activeElement as HTMLElement; resizeViewport()
  window.addEventListener('resize', resizeViewport); window.visualViewport?.addEventListener('resize', resizeViewport); window.visualViewport?.addEventListener('scroll', resizeViewport)
  window.addEventListener('scroll', updateHighlight, true); document.addEventListener('click', pickClick, true)
  void store.history(); void nextTick(() => { if (props.focusOnOpen !== false) composer.value?.focus() })
})
onUnmounted(() => { pointerEnd(); helpGeneration++; clearTimeout(connectorTimer); window.removeEventListener('keydown', previewEscape); unlock(); window.removeEventListener('resize', resizeViewport); window.visualViewport?.removeEventListener('resize', resizeViewport); window.visualViewport?.removeEventListener('scroll', resizeViewport); window.removeEventListener('scroll', updateHighlight, true); document.removeEventListener('click', pickClick, true) })
</script>
<template>
  <div :class="{ 'yl-reduced': reducedMotion }">
    <div v-if="modal" class="yl-backdrop" @click="emit('mode', 'side')" />
    <section v-show="mode !== 'edge'" ref="panel" class="yl-panel" :class="{ 'yl-focus': mode === 'focus', 'yl-mobile': viewport.width < 768, 'yl-manipulating': manipulating }" :style="sizeStyle" role="dialog" :aria-modal="modal || undefined" aria-label="曜灵 · Nexus AI" tabindex="-1" @keydown="keydown" @pointerdown.capture="pointerFocus" @pointerenter="emit('pointer-enter', $event)" @pointerleave="emit('pointer-leave', $event)" @focusin="updateFocus($event.target)" @focusout="updateFocus($event.relatedTarget)">
      <aside class="yl-session-rail"><div class="yl-rail-brand"><AssistantCore/><div><strong>曜灵</strong><small>NEXUS AI</small></div></div><button class="yl-rail-new" @click="newChat"><Plus :size="18"/>开启新会话</button><small>会话记录</small><div class="yl-rail-list"><button v-for="row in store.sessions" :key="row.id" :class="{active:row.id===store.selectedId}" @click="store.selectSession(row.id); tab='chat'"><BookOpen :size="14"/><span>{{ row.title }}</span><Star v-if="row.favorite" :size="13"/></button></div><button @click="historyOpen=true">检索与管理历史</button><button @click="showArtifacts()"><Bookmark :size="15"/>我的成果</button><p>一点灵感，一次协作。<br>让每个问题都有下一步。</p></aside>
      <main class="yl-conversation">
      <header class="yl-header" :class="{ 'yl-movable': !modal }" @pointerdown="pointerDown($event, 'drag')" @pointermove="pointerMove" @pointerup="pointerEnd" @pointercancel="pointerEnd" @lostpointercapture="pointerEnd">
        <div class="yl-header-top"><AssistantCore :active="store.anyBusy" /><div class="yl-brand"><strong>曜灵</strong><span>Nexus AI</span></div>
          <div class="yl-header-actions"><button aria-label="历史会话" title="历史会话" @click="historyOpen = !historyOpen; store.history()"><History :size="18" /></button><button aria-label="查看资料与来源" title="资料与来源" @click="showSources()"><BookOpen :size="18"/></button><button aria-label="新建对话" title="新建对话" :disabled="store.creating || store.capabilities?.schema_status !== 'ready'" @click="newChat"><Plus :size="19" /></button><button :aria-label="mode === 'focus' ? '退出专注阅读' : '专注阅读'" @click="emit('mode', mode === 'focus' ? 'side' : 'focus')"><Minimize2 v-if="mode === 'focus'" :size="17" /><Maximize2 v-else :size="17" /></button><button aria-label="关于与连接状态" @click="aboutOpen=true"><Info :size="16"/></button><button aria-label="收起曜灵" @click="emit('mode', 'edge')"><Minus :size="20" /></button></div>
        </div>
        <span v-if="store.busy" class="yl-sr-only" role="status">{{ stateLabels[store.currentRun!.state] }}</span>
      </header>
      <div v-if="page && useContext" class="yl-context"><span>当前页面</span><b>{{ pageTitle }}</b><button aria-label="移除页面上下文" @click="useContext = false; selectedArticle = null"><X :size="13" /></button></div>
      <div v-else class="yl-context"><span>自由交流</span><b>从你的问题开始</b><button v-if="page" @click="useContext = true">带上本页</button></div>
      <div v-if="selection && useSelection" class="yl-context"><span>选择范围</span><b>{{ selection.resources.length ? `已选 ${selection.resources.length} 条记录` : '本页当前筛选' }}</b><button aria-label="移除选中记录和筛选" @click="useSelection=false"><X :size="13"/></button></div>
      <nav v-if="tab!=='chat'" class="yl-tabs" aria-label="助手能力"><button @click="tab = 'chat'">聊一聊</button><button :class="{ active: tab === 'help' }" @click="showHelp">讲解本页</button><button :class="{ active: tab === 'pick' }" @click="pick"><MapPin :size="14" />指给我看</button></nav>
      <div ref="scroller" class="yl-scroll" @scroll="onScroll">
        <div v-if="tab === 'chat' && !store.messages.length && !store.loading" class="yl-welcome">
          <div class="yl-welcome-core"><AssistantCore /></div><h2>有问题，交给曜灵。</h2><p>从一个想法，到清楚的答案，再到下一步。</p>
          <div class="yl-welcome-actions"><button @click="suggestion('research')"><Globe :size="22"/><span>联网查证<small>查新知，核对信息<br>让每个结论有据可循</small></span></button><button @click="suggestion('my_work')"><BriefcaseBusiness :size="22"/><span>我的工作<small>聚合待办与异常<br>看清今天的优先事项</small></span></button><button @click="showHelp"><BookOpen :size="22"/><span>讲解页面<small>从字段到操作<br>陪你一步步上手</small></span></button><button @click="suggestion('analyze_files')"><FileText :size="22"/><span>文件与分析<small>带上资料来聊<br>把信息整理成成果</small></span></button></div>
          <button class="yl-welcome-hint" @click="draft='帮我写一封友好的邀请函'; composer?.focus()">也可以聊写作、学习、代码与灵感</button>
          <p v-if="!canChat" class="yl-unconfigured">曜灵的模型连接尚未完成。<br>你仍可查看本页操作说明。</p>
        </div>
        <template v-if="tab === 'chat'">
          <button v-if="store.cursors[store.selectedId]" class="yl-load-more" @click="older">加载更早的消息</button>
          <p v-if="store.loading" class="yl-muted">正在读取对话…</p>
          <AssistantMessage v-for="message in store.messages" :key="message.id" :message="message" @citation="citation" @sources="showSources" @saved="showArtifacts"/>
          <div v-if="store.messages.length && !store.busy" class="yl-tail-actions"><button @click="reviseLast"><Pencil :size="14"/>修订末尾问题</button><button v-if="store.currentRun?.payload.text" @click="store.submit(store.currentRun.payload)"><RotateCcw :size="14"/>重新生成新回答</button></div>
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
        <div v-if="documents.length" class="yl-document-chips"><div v-for="doc in documents" :key="doc.id"><FileText :size="14"/><span>{{ doc.name }} · {{ {queued:'排队中',parsing:'解析中',ready:'可分析',failed:'解析失败'}[doc.parse_status] || doc.parse_status }}{{ doc.error_code ? ` (${doc.error_code})` : '' }}</span><button type="button" aria-label="删除文件及其派生资料" @click="removeDocument(doc.id)"><X :size="14"/></button></div><button type="button" @click="refreshDocuments">刷新资料状态</button></div>
        <div v-if="attachments.length" class="yl-attachments"><figure v-for="(image,index) in attachments" :key="image.id"><img :src="image.url" :alt="image.name" /><button type="button" aria-label="移除图片" @click="removeImage(index)"><X :size="13" /></button></figure></div>
        <textarea ref="composer" v-model="draft" :disabled="store.creating" rows="2" aria-label="给曜灵的问题" placeholder="问一个问题，或把工作交给曜灵…" @keydown="enter" @paste="paste" />
        <input v-if="search!=='off'" v-model="publicQuery" class="yl-public-query" aria-label="单独的公开检索词" placeholder="混合私有资料时：单独填写公开检索词" maxlength="4000"/>
        <div class="yl-composer-actions"><div><button type="button" aria-label="上传文档" :disabled="uploading || store.creating || !store.capabilities?.materials?.available" @click="documentInput?.click()"><Paperclip :size="18"/></button><input ref="documentInput" hidden type="file" accept=".txt,.md,.csv,.pdf" multiple @change="uploadDocuments(Array.from(($event.target as HTMLInputElement).files || []))"/><select v-model="search" aria-label="联网模式"><option value="off">关闭</option><option value="auto" :disabled="!store.capabilities?.search?.supported_modes.includes('auto')">自动</option><option value="on" :disabled="!store.capabilities?.search?.supported_modes.includes('on')">本次联网</option></select><button v-if="store.capabilities?.profiles[0]?.vision" type="button" aria-label="上传图片" :disabled="uploading || store.creating" @click="fileInput?.click()"><ImagePlus :size="18" /></button><input ref="fileInput" hidden type="file" accept="image/png,image/jpeg,image/webp" multiple @change="upload(Array.from(($event.target as HTMLInputElement).files || []))" /><select v-if="store.capabilities?.profiles[0]?.thinking === 'toggle'" v-model="thinking" aria-label="思考模式"><option value="auto">自动思考</option><option value="on">深度思考</option><option value="off">直接回答</option></select><span v-else class="yl-muted">{{ store.capabilities?.profiles[0]?.thinking === 'always' ? '深度思考' : '自由提问' }}</span></div><button v-if="store.busy" type="button" class="yl-send" aria-label="停止生成" @click="store.stop()"><Square :size="17" /></button><button v-else class="yl-send" type="submit" aria-label="发送问题" :disabled="!draft.trim() || !canChat || uploading || store.creating"><ArrowUp :size="21" /></button></div>
        <p class="yl-disclosure">选用的资料会交给配置的模型服务；公开检索独立取词。</p>
      </form>
      </main>
      <aside class="yl-context-rail"><div class="yl-rail-tabs"><button @click="selectedEvidence=null">资料来源</button><button @click="showArtifacts()">我的成果</button></div><div class="yl-page-card"><small>当前页面</small><strong>{{ pageTitle || '自由交流' }}</strong><p>解释字段、定位操作，<br>把下一步讲清楚。</p><button @click="showHelp">讲解本页</button><button @click="pick">指给我看</button></div><AssistantSources :evidence="latestEvidence || null"/></aside>
      <div v-if="sourcesOpen" class="yl-inner-layer yl-source-layer"><header><h2>资料与来源</h2><button aria-label="关闭来源" @click="closeLayers"><X :size="18"/></button></header><AssistantSources :evidence="latestEvidence || null"/><button @click="showArtifacts(); sourcesOpen=false">我的私有成果</button></div>
      <div v-if="artifactsOpen" class="yl-inner-layer"><header><h2>我的私有成果</h2><button aria-label="关闭成果" @click="closeLayers"><X :size="18"/></button></header><AssistantArtifacts :selected="artifactId"/></div>
      <div v-if="historyOpen" class="yl-inner-layer"><header><h2>你的对话</h2><button aria-label="关闭历史" @click="closeLayers"><X :size="18" /></button></header><div class="yl-history-search"><input v-model="store.historyQuery" aria-label="检索会话" placeholder="搜索标题或当前可见正文" @keydown.enter="store.history()"/><button @click="store.history()">搜索</button><label><input v-model="store.favoritesOnly" type="checkbox" @change="store.history()"/>只看收藏</label></div><button class="yl-primary" @click="newChat">开启新对话 <Plus :size="17" /></button><div class="yl-history-list"><article v-for="row in store.sessions" :key="row.id"><template v-if="renameId === row.id"><input v-model="renameText" aria-label="对话名称" maxlength="160" @keydown.enter="rename(row)" /><button @click="rename(row)">保存</button><button @click="renameId = ''">取消</button></template><template v-else><button class="yl-history-title" :disabled="row.deletion_state !== 'active'" @click="store.selectSession(row.id); historyOpen = false; tab = 'chat'"><strong>{{ row.title }}</strong><small>{{ row.deletion_state === 'pending' ? '正在删除，稍后刷新重试清理' : new Date(row.updated_at*1000).toLocaleString('zh-CN') }}</small></button><button :aria-label="row.favorite ? '取消收藏' : '收藏会话'" @click="favorite(row)"><Star :size="15" :fill="row.favorite ? 'currentColor' : 'none'"/></button><button aria-label="重命名对话" @click="renameId = row.id; renameText = row.title"><Pencil :size="15" /></button><button aria-label="删除对话" @click="deleteId = row.id"><Trash2 :size="15" /></button></template><div v-if="deleteId === row.id" class="yl-delete-confirm"><p>删除此对话和附件？生成会同时停止。</p><button @click="remove(row)">确认删除</button><button @click="deleteId = ''">保留</button></div></article><p v-if="!store.sessions.length" class="yl-muted">还没有对话，从一个问题开始。</p></div><button v-if="store.historyCursor" :disabled="store.historyBusy" @click="store.history(true)">更多历史</button><button v-if="store.selectedId" class="yl-export" @click="exportChat"><Download :size="16" />导出当前完整会话 Markdown</button></div>
      <div v-if="aboutOpen" class="yl-inner-layer"><header><h2>关于曜灵</h2><button aria-label="关闭关于" @click="closeLayers"><X :size="18" /></button></header><AssistantCore /><h3>曜灵 · Nexus AI</h3><p>可以自由交流，也可以讲解有依据的系统规则。</p><dl><dt>模型服务</dt><dd>千问 · OpenAI 兼容协议</dd><dt>实际模型</dt><dd>{{ store.capabilities?.model || '尚未配置' }}</dd><dt>连接</dt><dd>{{ connectionLabel }}</dd><dt>联网与图片</dt><dd>{{ store.capabilities?.search?.verification === 'verified' ? '联网已有精确组合验证记录' : '联网组合尚未验证，普通问答可继续' }}</dd></dl><p>只读业务查询按当前身份和厂区取数；公开检索与私有资料分开处理。文件支持TXT、MD、CSV和文本PDF。能力验证记录不是实时健康状态。</p><label><input v-model="reducedMotion" type="checkbox" /> 减少装饰动效</label><button @click="switchSide"><PanelLeftClose :size="16" />移到{{ side === 'right' ? '左' : '右' }}侧</button><button @click="store.refreshCapabilities()">刷新能力状态</button><button v-if="!modal" class="yl-drag" aria-label="移动曜灵浮窗" @keydown="layoutKey($event)"><GripVertical :size="14"/>方向键移动浮窗</button><button v-if="!modal" aria-label="恢复浮窗位置和大小" @click="resetLayout"><RotateCcw :size="14"/>恢复位置和大小</button><button @click="showArtifacts(); aboutOpen=false">我的私有成果</button></div>
      <div v-if="!modal" class="yl-resize" role="separator" aria-label="调整曜灵宽度" aria-orientation="vertical" :aria-valuenow="width" aria-valuemin="360" aria-valuemax="600" tabindex="0" @pointerdown="pointerDown($event,'resize')" @pointermove="pointerMove" @pointerup="pointerEnd" @pointercancel="pointerEnd" @lostpointercapture="pointerEnd" @keydown.left.prevent="emit('width',Math.max(360,width-20)); emit('layout-end')" @keydown.right.prevent="emit('width',Math.min(600,width+20)); emit('layout-end')" />
      <button v-if="!modal" class="yl-resize-corner" aria-label="调整曜灵大小" title="拖动调整宽高；方向键微调，Home 恢复" @pointerdown="pointerDown($event,'corner')" @pointermove="pointerMove" @pointerup="pointerEnd" @pointercancel="pointerEnd" @lostpointercapture="pointerEnd" @keydown="layoutKey($event, true)"><span aria-hidden="true">◢</span></button>
    </section>
    <div v-if="highlight" class="yl-target-outline" :style="{ left: `${Math.max(0,highlight.left-4)}px`, top: `${Math.max(0,highlight.top-4)}px`, width: `${Math.min(viewport.width,highlight.width+8)}px`, height: `${Math.min(viewport.height,highlight.height+8)}px` }" aria-hidden="true" />
    <svg v-if="connector && connectionPath && !reducedMotion" class="yl-connector" aria-hidden="true"><path :d="connectionPath" /></svg>
    <div v-if="guide" class="yl-guide" role="region" aria-label="页面操作引导"><strong>{{ guideIndex+1 }} · {{ guide.title }}</strong><p>{{ guide.description }}</p><small>{{ guide.precondition }} · {{ guide.completion }}</small><div><button :disabled="guideIndex === 0" @click="guideStep(guideIndex-1)">上一步</button><button @click="guideStep(guideIndex+1)">{{ guideIndex+1 === selectedArticle?.steps.length ? '完成引导' : '下一步 / 跳过' }}</button><button @click="guideIndex = -1; clearHighlight()">退出</button></div></div>
    <div v-else-if="highlight && mode === 'edge'" class="yl-guide"><strong>{{ selectedArticle?.title }}</strong><div><button @click="emit('mode','side')">返回说明</button><button @click="clearHighlight()">结束定位</button></div></div>
  </div>
</template>
