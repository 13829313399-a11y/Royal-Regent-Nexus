<script setup lang="ts">
import { computed, nextTick, onBeforeUnmount, onMounted, ref, toRaw, watch } from 'vue'
import { isAxiosError } from 'axios'
import { MessageSquarePlus, RefreshCw, Send, X, Inbox, CheckCheck, Paperclip } from '@lucide/vue'
import { DialogRoot, DialogPortal, DialogOverlay, DialogContent, DialogTitle, DialogDescription } from 'reka-ui'
import { Button } from '@/components/ui/button'
import { moduleFeedbackApi, feedbackAttachmentUrl, type FeedbackContext, type FeedbackCapabilities, type FeedbackTicket, type FeedbackDetail, type FeedbackStatus, type FeedbackView, type FeedbackAction, type FeedbackReply, type FeedbackCreate } from '@/api/moduleFeedback'
import { getApiErrorMessage } from '@/lib/http'
import { createRandomUuid } from '@/lib/randomUuid'
import { useAuthStore } from '@/stores/auth'
import FeedbackAttachments from './FeedbackAttachments.vue'
import { feedbackEmojis, feedbackMaterials, feedbackStatuses } from './feedbackLabels'

const props = defineProps<{ factoryId: string; factoryName: string; active: boolean }>()
const emit = defineEmits<{ unread: [count: number]; navigate: [] }>()
const auth = useAuthStore()
const capabilities = ref<FeedbackCapabilities | null>(null)
const view = ref<FeedbackView>('mine')
const status = ref<FeedbackStatus | ''>('')
const keyword = ref('')
const appliedKeyword = ref('')
const page = ref(1)
const items = ref<FeedbackTicket[]>([])
const total = ref(0)
const unreadMine = ref(0)
const unreadManage = ref(0)
const loading = ref(false)
const loadingDetail = ref(false)
const error = ref('')
const notice = ref('')
const selected = ref<FeedbackDetail | null>(null)
const hasNewMessages = ref(false)
const composing = ref(false)
const creating = ref(false)
const createError = ref('')
const createTitle = ref('')
const createBody = ref('')
const createCategory = ref<FeedbackTicket['category']>('bug')
const createEmoji = ref('🐞')
const createFiles = ref<File[]>([])
const createContext = ref<FeedbackContext>({})
const createAttachments = ref<InstanceType<typeof FeedbackAttachments> | null>(null)
const createEditing = ref(false)
const capturing = ref(false)
const replyBody = ref('')
const replyAction = ref<FeedbackAction>('reply')
const requestedMaterials = ref<string[]>([])
const providedMaterials = ref<string[]>([])
const releaseNote = ref('')
const replyFiles = ref<File[]>([])
const replyAttachments = ref<InstanceType<typeof FeedbackAttachments> | null>(null)
const replyEditing = ref(false)
const replyCapturing = ref(false)
const sending = ref(false)
const replyError = ref('')
const owner = computed(() => !!selected.value && selected.value.author_id === auth.currentUser?.id)
const developer = computed(() => capabilities.value?.can_manage && view.value === 'manage')
const canReply = computed(() => !!selected.value && selected.value.status !== 'resolved' && (owner.value || developer.value))
const hasCreateDraft = computed(() => !!(createTitle.value.trim() || createBody.value.trim() || createFiles.value.length))
const displayedCreateContext = computed(() => permittedContext(createContext.value))
const canCreate = computed(() => capabilities.value?.can_submit && createTitle.value.trim().length >= 2 && (createBody.value.trim().length > 0 || createFiles.value.length > 0) && !createEditing.value && !capturing.value)
const replyReady = computed(() => (!!replyBody.value.trim() || (replyAction.value === 'reply' && replyFiles.value.length > 0)) && !replyEditing.value && !replyCapturing.value
  && (replyAction.value !== 'request_info' || requestedMaterials.value.length > 0)
  && (replyAction.value !== 'ready' || !!releaseNote.value.trim()))
const actionLabels: Record<FeedbackAction, string> = { reply: '回复', start: '开始处理', request_info: '请求补充资料', ready: '修复上线，邀请验证', resolve: '确认已解决', reopen: '仍有问题，重新处理' }
let generation = 0, listSequence = 0, detailSequence = 0
let poll: ReturnType<typeof setInterval> | undefined
let createRequest: { fingerprint: string; id: string; payload: FeedbackCreate } | undefined
let replyRequest: { fingerprint: string; id: string; payload: FeedbackReply } | undefined

function formatTime(value: string) {
  if (!value) return '—'
  const date = new Date(value)
  return Number.isNaN(date.getTime()) ? value : date.toLocaleString('zh-CN', { timeZone: 'Asia/Shanghai', hour12: false, month: '2-digit', day: '2-digit', hour: '2-digit', minute: '2-digit' })
}
function notifyUnread() { emit('unread', capabilities.value?.can_manage ? unreadManage.value : unreadMine.value) }
function contextRows(context: FeedbackContext) {
  return [
    ['所在页面', context.page], ['客户', context.customer_code], ['订单参考号', context.order_reference],
    ['产品编号', context.product_no], ['导入批次', context.batch_id], ['关联文件名', context.file_names?.join('、')],
    ['页面提示', context.error_message],
  ].filter((row): row is [string, string] => !!row[1])
}
function requestKey(previous: { fingerprint: string; id: string }, payload: unknown, files: File[]) {
  const fingerprint = JSON.stringify([payload, files.map(file => [file.name, file.size, file.lastModified])])
  return previous.fingerprint === fingerprint ? previous : { fingerprint, id: createRandomUuid() }
}
function resetReply() {
  replyBody.value = ''; replyAction.value = 'reply'; requestedMaterials.value = []; providedMaterials.value = []
  releaseNote.value = ''; replyFiles.value = []; replyError.value = ''; replyEditing.value = false
  replyRequest = undefined
}
function resetDraft() {
  createTitle.value = ''; createBody.value = ''; createFiles.value = []; createCategory.value = 'bug'
  createEmoji.value = '🐞'; createError.value = ''; createEditing.value = false; createRequest = undefined
}
function openComposer(context: FeedbackContext = {}) {
  createError.value = ''
  if (!hasCreateDraft.value) createContext.value = permittedContext(context)
  else createError.value = '已恢复未提交的草稿，关联资料保持原选择。'
  composing.value = true
}
function permittedContext(context: FeedbackContext): FeedbackContext {
  if (capabilities.value?.can_link_order) return structuredClone(toRaw(context))
  return { page: context.page, section: context.section, app_version: context.app_version }
}
defineExpose({ openComposer })
function closeComposer(open: boolean) { if (!creating.value && !capturing.value) composing.value = open }

async function refresh(background = false) {
  const token = ++listSequence, scope = generation, factory = props.factoryId, selectedView = view.value
  if (!background) { loading.value = true; error.value = '' }
  try {
    const caps = await moduleFeedbackApi.capabilities(factory)
    if (scope !== generation || token !== listSequence) return
    capabilities.value = caps
    if (!caps.can_link_order && !caps.can_manage && selected.value?.context.order_id) selected.value.context = permittedContext(selected.value.context)
    if (!caps.can_manage && selectedView === 'manage') { view.value = 'mine'; items.value = []; selected.value = null; await refresh(background); return }
    if (!caps.can_submit && !caps.can_manage) { items.value = []; selected.value = null; total.value = 0; unreadMine.value = unreadManage.value = 0; notifyUnread(); return }
    const result = await moduleFeedbackApi.list(factory, selectedView, { status: status.value, q: appliedKeyword.value, page: page.value, page_size: props.active ? 20 : 1 })
    if (scope !== generation || token !== listSequence || selectedView !== view.value) return
    if (props.active) { items.value = result.items; total.value = result.total }
    if (selectedView === 'mine') unreadMine.value = result.unread_count
    else unreadManage.value = result.unread_count
    if (caps.can_manage) {
      const otherView = selectedView === 'mine' ? 'manage' : 'mine'
      const other = await moduleFeedbackApi.list(factory, otherView, { page_size: 1 })
      if (scope !== generation || token !== listSequence) return
      if (otherView === 'mine') unreadMine.value = other.unread_count
      else unreadManage.value = other.unread_count
    }
    notifyUnread()
    if (selected.value && props.active && !sending.value && !loadingDetail.value) {
      const ticketId = selected.value.id
      const latest = await moduleFeedbackApi.detail(ticketId, factory)
      if (scope === generation && token === listSequence && selected.value?.id === ticketId) {
        selected.value.context = latest.context
        hasNewMessages.value = latest.revision > selected.value.revision
      }
    }
  } catch (cause) {
    if (scope !== generation || token !== listSequence) return
    error.value = `反馈读取失败：${getApiErrorMessage(cause)}`
    // Do not leave previously authorized conversations visible after a failed scope check.
    items.value = []; selected.value = null; total.value = 0; capabilities.value = null
    unreadMine.value = unreadManage.value = 0; notifyUnread()
  } finally { if (scope === generation && token === listSequence) loading.value = false }
}
async function selectTicket(id: string, preserveReply = false) {
  if (sending.value) return
  const token = ++detailSequence, scope = generation, factory = props.factoryId
  loadingDetail.value = true; error.value = ''
  if (!preserveReply) { selected.value = null; resetReply() }
  try {
    const detail = await moduleFeedbackApi.detail(id, factory)
    if (scope !== generation || token !== detailSequence || !props.active) return
    selected.value = detail; hasNewMessages.value = false
    await nextTick()
    if (scope !== generation || token !== detailSequence || !props.active || document.visibilityState !== 'visible') return
    await moduleFeedbackApi.read(id, factory, detail.revision)
    if (scope !== generation || token !== detailSequence) return
    await refresh(true)
  } catch (cause) {
    if (scope === generation && token === detailSequence) { error.value = getApiErrorMessage(cause); selected.value = null }
  } finally { if (scope === generation && token === detailSequence) loadingDetail.value = false }
}
async function createFeedback() {
  if (!canCreate.value || creating.value) return
  const scope = generation, factory = props.factoryId
  const intent = { factory_id: factory, module: 'customer-order-center', title: createTitle.value.trim(), body: createBody.value.trim(), category: createCategory.value, emoji: createEmoji.value }
  const key = requestKey(createRequest ?? { fingerprint: '', id: '' }, intent, createFiles.value)
  // Permission changes affect displayed context, but never replace an unknown-outcome request.
  if (createRequest?.id !== key.id) createRequest = { ...key, payload: { ...intent, context: permittedContext(createContext.value), client_request_id: key.id } }
  const pending = createRequest!
  creating.value = true; createError.value = ''
  try {
    const result = await moduleFeedbackApi.create(pending.payload, createFiles.value)
    if (scope !== generation) return
    resetDraft(); composing.value = false; view.value = 'mine'; status.value = ''; page.value = 1; keyword.value = appliedKeyword.value = ''
    resetReply(); selected.value = result; notice.value = '反馈已提交。后续回复会显示在这里，顶部也会提示未读消息。'
    emit('navigate'); await refresh(); await selectTicket(result.id)
  } catch (cause) {
    if (scope !== generation) return
    const statusCode = isAxiosError(cause) ? cause.response?.status : undefined
    if (statusCode && statusCode >= 400 && statusCode < 500 && statusCode !== 408) createRequest = undefined
    createError.value = getApiErrorMessage(cause)
  }
  finally { if (scope === generation) creating.value = false }
}
function prepareAction(action: FeedbackAction) {
  replyAction.value = action; replyError.value = ''
  const templates: Record<FeedbackAction, string> = {
    reply: '已收到你的反馈，正在核查。', start: '已复现问题，正在处理。有进展会在这里回复。',
    request_info: '为了确认问题，请补充下面勾选的资料。', ready: '修复已上线，请按原操作步骤再次验证，并告诉我们结果。',
    resolve: '已按原操作步骤验证，问题已解决。', reopen: '按原操作步骤验证后，仍存在问题：',
  }
  replyBody.value = templates[action]
}
async function sendReply() {
  if (!selected.value || !replyReady.value || sending.value) return
  const ticket = selected.value, scope = generation, factory = props.factoryId
  const intent = { action: replyAction.value, body: replyBody.value.trim(),
    requested_materials: replyAction.value === 'request_info' ? requestedMaterials.value : [],
    provided_materials: owner.value ? providedMaterials.value : [], release_note: replyAction.value === 'ready' ? releaseNote.value.trim() : '' }
  const key = requestKey(replyRequest ?? { fingerprint: '', id: '' }, { factory, ticket: ticket.id, ...intent }, replyFiles.value)
  // An unknown network outcome must replay the exact request, even after refreshing the conversation.
  if (replyRequest?.id !== key.id) replyRequest = { ...key, payload: { ...intent, expected_revision: ticket.revision, client_request_id: key.id } }
  const pending = replyRequest!
  sending.value = true; replyError.value = ''
  try {
    const result = await moduleFeedbackApi.reply(ticket.id, factory, pending.payload, replyFiles.value)
    if (scope !== generation || selected.value?.id !== ticket.id) return
    selected.value = result; hasNewMessages.value = false; resetReply(); notice.value = '回复已发送。'
    await nextTick()
    if (scope === generation && props.active && document.visibilityState === 'visible') await moduleFeedbackApi.read(ticket.id, factory, result.revision)
    if (scope === generation) await refresh(true)
  } catch (cause) {
    if (scope !== generation) return
    const statusCode = isAxiosError(cause) ? cause.response?.status : undefined
    if (statusCode && statusCode >= 400 && statusCode < 500 && statusCode !== 408) replyRequest = undefined
    replyError.value = `${getApiErrorMessage(cause)}；输入内容已保留，${statusCode === 409 ? '请先刷新对话再发送' : '可重试发送确认结果'}。`
  }
  finally { if (scope === generation) sending.value = false }
}
function changeView(next: FeedbackView) {
  if (sending.value) return
  view.value = next; page.value = 1; selected.value = null; detailSequence++; resetReply(); void refresh()
}
function search() { page.value = 1; appliedKeyword.value = keyword.value.trim(); void refresh() }
watch(() => props.active, active => {
  if (active) { if (selected.value) void selectTicket(selected.value.id, true); else void refresh() }
  else { detailSequence++; loadingDetail.value = false }
})
watch(() => props.factoryId, () => {
  generation++; detailSequence++; listSequence++; capabilities.value = null; items.value = []; selected.value = null
  composing.value = false; creating.value = false; sending.value = false; loadingDetail.value = false
  resetDraft(); resetReply(); view.value = 'mine'; page.value = 1; keyword.value = appliedKeyword.value = ''; status.value = ''
  unreadMine.value = unreadManage.value = 0; notifyUnread(); void refresh()
})
watch(() => auth.currentUser?.id, () => { generation++; detailSequence++; selected.value = null; items.value = []; composing.value = false; resetDraft(); resetReply(); void refresh() })
onMounted(() => { void refresh(); poll = setInterval(() => { if (document.visibilityState === 'visible' && !sending.value && !creating.value && !loading.value && !loadingDetail.value) void refresh(true) }, 30000) })
onBeforeUnmount(() => { generation++; if (poll) clearInterval(poll) })
</script>

<template>
  <section v-if="active" class="feedback-hub" aria-label="反馈与答复">
    <header class="feedback-hub__header">
      <div><p class="feedback-hub__eyebrow">{{ factoryName }} · 客户订单中心</p><h2>反馈与答复</h2><p>把问题、截图和资料放在一起，持续跟进每一次回复。</p></div>
      <Button type="button" :disabled="!capabilities?.can_submit" @click="openComposer({ page: '反馈与答复', section: 'feedback' })"><MessageSquarePlus class="size-4" /> 新建反馈</Button>
    </header>
    <p v-if="notice" class="feedback-hub__notice" role="status">{{ notice }}<button type="button" aria-label="关闭反馈提示" @click="notice = ''">×</button></p>
    <p v-if="error" class="feedback-hub__error" role="alert">{{ error }} <button type="button" @click="refresh()">重新加载</button></p>
    <p v-if="capabilities && !capabilities.can_submit && !capabilities.can_manage" class="feedback-hub__empty">当前账号暂不能使用本厂区反馈。请确认员工厂区归属已审核，或联系管理员核对反馈权限。</p>
    <template v-if="capabilities?.can_submit || capabilities?.can_manage">
      <div class="feedback-hub__toolbar">
        <div class="feedback-hub__tabs" aria-label="反馈视图">
          <button type="button" :aria-pressed="view === 'mine'" @click="changeView('mine')">我的反馈 <b v-if="unreadMine">{{ unreadMine }}</b></button>
          <button v-if="capabilities.can_manage" type="button" :aria-pressed="view === 'manage'" @click="changeView('manage')">开发者处理 <b v-if="unreadManage">{{ unreadManage }}</b></button>
        </div>
        <form class="feedback-hub__filters" @submit.prevent="search">
          <select v-model="status" aria-label="筛选反馈状态" @change="search"><option value="">全部状态</option><option v-for="(label, value) in feedbackStatuses" :key="value" :value="value">{{ label }}</option></select>
          <input v-model="keyword" type="search" maxlength="100" aria-label="搜索反馈" placeholder="搜索标题或问题描述" />
          <Button type="submit" variant="outline" size="sm">搜索</Button>
          <Button type="button" variant="ghost" size="icon" aria-label="刷新反馈" :disabled="loading" @click="refresh()"><RefreshCw class="size-4" /></Button>
        </form>
      </div>
      <div class="feedback-hub__layout">
        <aside class="feedback-hub__inbox" aria-label="反馈列表">
          <p class="feedback-hub__list-title">{{ view === 'mine' ? '我提交的反馈' : '本厂区反馈' }} <span>{{ total }} 条</span></p>
          <p v-if="loading" class="feedback-hub__empty" role="status">正在读取…</p>
          <p v-else-if="!items.length" class="feedback-hub__empty"><Inbox class="size-8" />{{ keyword || status ? '没有符合筛选条件的反馈' : '暂无反馈' }}</p>
          <button v-for="ticket in items" :key="ticket.id" type="button" class="feedback-hub__ticket" :class="{ selected: selected?.id === ticket.id }" :disabled="sending" @click="selectTicket(ticket.id)">
            <span class="feedback-hub__ticket-top"><span :class="['feedback-status', ticket.status]">{{ feedbackStatuses[ticket.status] }}</span><span v-if="ticket.unread" class="feedback-unread">有新消息</span></span>
            <strong>{{ ticket.emoji }} {{ ticket.title }}</strong><small>{{ ticket.author_name }} · {{ formatTime(ticket.updated_at) }}</small>
          </button>
          <div v-if="total > 20" class="feedback-hub__pages"><button type="button" :disabled="page <= 1 || loading" @click="page--; refresh()">上一页</button><span>{{ page }} / {{ Math.ceil(total / 20) }}</span><button type="button" :disabled="page * 20 >= total || loading" @click="page++; refresh()">下一页</button></div>
        </aside>
        <section class="feedback-hub__conversation" aria-label="反馈详情">
          <p v-if="loadingDetail && !selected" class="feedback-hub__empty">正在读取对话…</p>
          <div v-else-if="!selected" class="feedback-hub__welcome"><MessageSquarePlus class="size-10" /><h3>选择一条反馈开始查看</h3><p>回复、补充资料和处理进度会保留在同一条对话中。</p></div>
          <template v-else>
            <header class="feedback-hub__detail-head"><div><span :class="['feedback-status', selected.status]">{{ feedbackStatuses[selected.status] }}</span><h3>{{ selected.emoji }} {{ selected.title }}</h3><p>{{ selected.author_name }} · {{ formatTime(selected.created_at) }}<span v-if="selected.assigned_name"> · 处理人：{{ selected.assigned_name }}</span></p></div><Button type="button" variant="ghost" size="sm" :disabled="sending || loadingDetail" @click="selectTicket(selected.id, true)">刷新对话</Button></header>
            <details v-if="contextRows(selected.context).length" class="feedback-context"><summary>已关联资料 · {{ selected.context.page || '客户订单中心' }}</summary><dl><template v-for="[label, value] in contextRows(selected.context)" :key="label"><dt>{{ label }}</dt><dd>{{ value }}</dd></template></dl></details>
            <p v-if="hasNewMessages" class="feedback-hub__new-reply" role="status"><button type="button" @click="selectTicket(selected.id, true)">有新回复，点击查看（保留当前输入）</button></p>
            <div class="feedback-hub__messages" aria-label="反馈对话记录">
              <article v-for="message in selected.messages" :key="message.id" class="feedback-message" :class="{ 'feedback-message--developer': message.actor_kind === 'developer' }">
                <header><strong>{{ message.actor_name }}</strong><span>{{ message.actor_kind === 'developer' ? '开发者' : '反馈用户' }}</span><time>{{ formatTime(message.created_at) }}</time></header>
                <p>{{ message.body }}</p>
                <p v-if="message.release_note" class="feedback-message__release">上线说明：{{ message.release_note }}</p>
                <ul v-if="message.requested_materials?.length" class="feedback-message__materials"><li v-for="material in message.requested_materials" :key="material">需要补充：{{ feedbackMaterials[material] || material }}</li></ul>
                <p v-if="message.provided_materials?.length" class="feedback-message__provided">已补充：{{ message.provided_materials.map(key => feedbackMaterials[key] || key).join('、') }}</p>
                <div v-if="message.attachments.length" class="feedback-message__attachments"><a v-for="attachment in message.attachments" :key="attachment.id" :href="feedbackAttachmentUrl(selected, attachment)" target="_blank" rel="noopener noreferrer"><img v-if="attachment.content_type.startsWith('image/')" :src="feedbackAttachmentUrl(selected, attachment)" :alt="attachment.file_name" loading="lazy" /><span><Paperclip class="size-3" />{{ attachment.file_name }}</span></a></div>
              </article>
            </div>
            <section v-if="selected.requested_materials.length" class="feedback-checklist"><h4>资料收集清单</h4><p v-for="key in selected.requested_materials" :key="key"><CheckCheck v-if="selected.provided_materials.includes(key)" class="size-4" /><span v-else class="feedback-checklist__pending">○</span>{{ feedbackMaterials[key] || key }}<small>{{ selected.provided_materials.includes(key) ? '用户已补充' : '待补充' }}</small></p></section>
            <div v-if="selected.status === 'resolved'" class="feedback-hub__resolved"><CheckCheck class="size-5" /><span>用户已确认解决，全部记录仍可查看。</span><Button v-if="owner" type="button" variant="outline" size="sm" @click="prepareAction('reopen')">仍有问题</Button></div>
            <form v-if="canReply || (owner && replyAction === 'reopen')" class="feedback-reply" @submit.prevent="sendReply" @paste="replyAttachments?.paste($event)">
              <div v-if="developer && selected.status !== 'resolved'" class="feedback-reply__quick"><span>快捷回复</span><button v-for="action in (['reply', 'start', 'request_info', 'ready'] as const)" :key="action" type="button" :disabled="sending" :aria-pressed="replyAction === action" @click="prepareAction(action)">{{ actionLabels[action] }}</button></div>
              <div v-if="owner && selected.status === 'awaiting_verification'" class="feedback-reply__verify"><strong>请按原操作步骤验证</strong><Button type="button" size="sm" :disabled="sending" @click="prepareAction('resolve')">问题已解决</Button><Button type="button" variant="outline" size="sm" :disabled="sending" @click="prepareAction('reopen')">仍有问题</Button></div>
              <fieldset v-if="replyAction === 'request_info'"><legend>勾选需要用户补充的资料</legend><label v-for="key in capabilities.material_options" :key="key"><input v-model="requestedMaterials" type="checkbox" :value="key" :disabled="sending" />{{ feedbackMaterials[key] || key }}</label></fieldset>
              <fieldset v-if="owner && selected.status === 'needs_info'"><legend>本次已补充哪些资料？请附上文件或在下方说明</legend><label v-for="key in selected.requested_materials.filter(key => !selected?.provided_materials.includes(key))" :key="key"><input v-model="providedMaterials" type="checkbox" :value="key" :disabled="sending" />{{ feedbackMaterials[key] || key }}</label></fieldset>
              <label v-if="replyAction === 'ready'" class="feedback-field">已上线版本或修复说明<input v-model="releaseNote" maxlength="1000" :disabled="sending" placeholder="说明已经在哪个环境上线，以及修复了什么" required /></label>
              <label class="feedback-field">{{ actionLabels[replyAction] }}<textarea v-model="replyBody" :disabled="sending" maxlength="5000" rows="4" placeholder="回复内容或补充操作步骤、期望结果；也可以在这里粘贴截图" :required="replyAction !== 'reply' || !replyFiles.length" /></label>
              <FeedbackAttachments ref="replyAttachments" v-model="replyFiles" :disabled="sending" @editing="replyEditing = $event" @capturing="replyCapturing = $event" />
              <p v-if="replyError" class="feedback-hub__error" role="alert">{{ replyError }}</p>
              <footer><small>发送后对方会在“反馈与答复”收到未读提醒。</small><Button type="submit" :disabled="!replyReady || sending"><Send class="size-4" />{{ sending ? '正在发送…' : '发送回复' }}</Button></footer>
            </form>
          </template>
        </section>
      </div>
    </template>
  </section>

  <DialogRoot :open="composing" @update:open="closeComposer">
    <DialogPortal>
      <DialogOverlay class="fixed inset-0 z-[120] bg-slate-950/40" :class="{ invisible: capturing }" />
      <DialogContent class="feedback-compose fixed left-1/2 top-1/2 z-[121] flex max-h-[90dvh] w-[calc(100%-1.5rem)] max-w-3xl -translate-x-1/2 -translate-y-1/2 flex-col overflow-hidden rounded-xl bg-white text-slate-900 shadow-xl" :class="{ invisible: capturing }" @interact-outside.prevent @escape-key-down="event => { if (creating || capturing) event.preventDefault() }">
        <header class="feedback-compose__header"><div><DialogTitle class="text-lg font-bold">反馈问题或建议</DialogTitle><DialogDescription class="mt-1 text-sm text-slate-500">{{ factoryName }} · 客户订单中心 · 关闭窗口会保留本次草稿</DialogDescription></div><Button type="button" variant="ghost" size="icon" aria-label="关闭反馈窗口" :disabled="creating || capturing" @click="closeComposer(false)"><X class="size-5" /></Button></header>
        <form class="feedback-compose__form" @submit.prevent="createFeedback" @paste="createAttachments?.paste($event)">
          <p v-if="!capabilities?.can_submit" class="feedback-hub__error">{{ capabilities ? '当前账号暂不能提交本厂区反馈，请确认员工厂区归属已审核，或联系管理员核对反馈权限。' : '正在确认权限；若长时间未完成，请进入反馈与答复重新加载。' }}</p>
          <p v-else-if="!capabilities.can_link_order" class="text-sm leading-6 text-slate-500">可直接描述问题或添加资料，系统不会自动关联订单数据。</p>
          <fieldset class="feedback-emojis"><legend>这次使用感觉如何？</legend><button v-for="item in feedbackEmojis" :key="item.emoji" type="button" :disabled="creating" :aria-pressed="createEmoji === item.emoji" @click="createEmoji = item.emoji; createCategory = item.category"><span>{{ item.emoji }}</span>{{ item.label }}</button></fieldset>
          <div class="feedback-compose__row"><label class="feedback-field">反馈标题<input v-model="createTitle" :disabled="creating" minlength="2" maxlength="120" placeholder="例如：BuzzBee 订单装箱数识别不正确" required /></label><label class="feedback-field">类型<select v-model="createCategory" :disabled="creating"><option value="bug">功能问题</option><option value="question">使用咨询</option><option value="suggestion">改进建议</option></select></label></div>
          <label class="feedback-field">问题描述<textarea v-model="createBody" :disabled="creating" rows="4" maxlength="5000" placeholder="你做了什么？哪里不对？希望得到什么结果？也可以直接粘贴截图。" /></label>
          <FeedbackAttachments ref="createAttachments" v-model="createFiles" :disabled="creating" @editing="createEditing = $event" @capturing="capturing = $event" />
          <details v-if="contextRows(displayedCreateContext).length" class="feedback-context" open><summary>随反馈发送的关联资料</summary><dl><template v-for="[label, value] in contextRows(displayedCreateContext)" :key="label"><dt>{{ label }}</dt><dd>{{ value }}</dd></template></dl><p>这里只关联页面、订单及文件名；原始文件需要你在上方主动添加。</p></details>
          <p v-if="createError" class="feedback-hub__error" role="alert">{{ createError }}</p>
          <footer class="feedback-compose__footer"><Button type="button" variant="ghost" :disabled="creating || !hasCreateDraft" @click="resetDraft">清空草稿</Button><Button type="submit" :disabled="!canCreate || creating"><Send class="size-4" />{{ creating ? '正在提交…' : '提交反馈' }}</Button></footer>
        </form>
      </DialogContent>
    </DialogPortal>
  </DialogRoot>
</template>

<style src="./feedback.css"></style>
