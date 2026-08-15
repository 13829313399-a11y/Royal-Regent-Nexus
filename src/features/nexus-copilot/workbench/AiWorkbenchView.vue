<script setup lang="ts">
import { computed, onMounted, ref, watch } from 'vue'
import { ChevronUp, RefreshCcw } from '@lucide/vue'
import { useRoute, useRouter } from 'vue-router'
import { isAIConversationId, type AIConversationMode } from '@/api/aiConversations'
import {
  createVisionComparisonTask,
  getAITaskCapabilities,
  isAITaskId,
} from '@/api/aiTasks'
import AiComposer from '@/features/ai-assistant/AiComposer.vue'
import AiMessageList from '@/features/ai-assistant/AiMessageList.vue'
import { useAIAssistantStore } from '@/features/ai-assistant/store'
import { useAIConversationsStore } from '@/features/ai-assistant/stores/conversations'
import { useAppStore } from '@/stores/app'
import { useAuthStore } from '@/stores/auth'
import ConversationList from '../components/ConversationList.vue'
import ConversationRetentionBadge from '../components/ConversationRetentionBadge.vue'
import ContextPicker from '../components/ContextPicker.vue'
import EvidencePanel from '../components/EvidencePanel.vue'
import TaskControls from '../components/TaskControls.vue'
import TaskList from '../components/TaskList.vue'
import TaskTimeline from '../components/TaskTimeline.vue'
import { useAITasksStore } from '../stores/tasks'
import { pageContextFromConversation } from '../conversation/conversationContext'
import { summarizeConversationRuntime } from '../conversation/conversationRuntimeStatus'
import InspectorPanel, { type InspectorTab } from './InspectorPanel.vue'
import WorkbenchHeader from './WorkbenchHeader.vue'
import WorkbenchShell from './WorkbenchShell.vue'

interface ComposerHandle {
  clear: () => void
  focus: () => void
}

const route = useRoute()
const router = useRouter()
const appStore = useAppStore()
const authStore = useAuthStore()
const assistantStore = useAIAssistantStore()
const conversationsStore = useAIConversationsStore()
const tasksStore = useAITasksStore()
const composer = ref<ComposerHandle | null>(null)
const initializing = ref(true)
const pageError = ref('')
const railCollapsed = ref(false)
const inspectorOpen = ref(true)
const inspectorWidth = ref(360)
const inspectorTab = ref<InspectorTab>('sources')
let initializationGeneration = 0

const persistenceAvailable = computed(() => (
  assistantStore.capabilities?.conversation_persistence === true
))
const taskExecutionAvailable = ref(false)
const visionComparisonStarting = ref(false)
const activeEvidence = computed(() => (
  conversationsStore.active?.messages.flatMap((message) => message.evidence) ?? []
))
const conversationContext = computed(() => (
  pageContextFromConversation(conversationsStore.active?.context_binding)
))
const contextPickerAvailable = computed(() => (
  assistantStore.capabilities?.conversation_context_enabled === true
))
const workbenchV2Enabled = computed(() => (
  assistantStore.capabilities?.workbench_v2_enabled === true
))
const inspectorCounts = computed<Record<InspectorTab, number>>(() => ({
  sources: activeEvidence.value.length,
  tasks: tasksStore.items.length,
  artifacts: assistantStore.turns.reduce(
    (total, turn) => total + turn.businessResults.filter(
      (result) => result.kind !== 'action_confirmation',
    ).length,
    0,
  ),
  actions: assistantStore.turns.reduce(
    (total, turn) => total + turn.businessResults.filter(
      (result) => result.kind === 'action_confirmation',
    ).length,
    0,
  ),
}))
const conversationRuntimeStatuses = computed(() => {
  const conversationId = conversationsStore.activeId
  if (!conversationId) return {}
  const results = assistantStore.turns.flatMap((turn) => turn.businessResults)
  return {
    [conversationId]: summarizeConversationRuntime(conversationId, tasksStore.items, results),
  }
})

function queryConversationId() {
  const value = Array.isArray(route.query.conversation)
    ? route.query.conversation[0]
    : route.query.conversation
  return isAIConversationId(value) ? value : null
}

function queryTaskId() {
  const value = Array.isArray(route.query.task) ? route.query.task[0] : route.query.task
  return isAITaskId(value) ? value : null
}

async function updateConversationQuery(conversationId: string | null) {
  const rawValue = Array.isArray(route.query.conversation)
    ? route.query.conversation[0]
    : route.query.conversation
  if (conversationId ? rawValue === conversationId : rawValue == null) return
  await router.replace({
    name: 'ai-workbench',
    query: {
      ...(conversationId ? { conversation: conversationId } : {}),
      ...(tasksStore.activeId ? { task: tasksStore.activeId } : {}),
    },
  })
}

async function updateTaskQuery(taskId: string | null) {
  const rawValue = Array.isArray(route.query.task) ? route.query.task[0] : route.query.task
  if (taskId ? rawValue === taskId : rawValue == null) return
  await router.replace({
    name: 'ai-workbench',
    query: {
      ...(conversationsStore.activeId ? { conversation: conversationsStore.activeId } : {}),
      ...(taskId ? { task: taskId } : {}),
    },
  })
}

async function openConversation(conversationId: string, updateQuery = true) {
  pageError.value = ''
  try {
    const detail = await conversationsStore.open(conversationId)
    if (contextPickerAvailable.value) {
      await conversationsStore.loadContextOptions(detail.factory_scope)
    }
    assistantStore.bindConversation(detail.id, detail.mode, detail.messages)
    tasksStore.reset()
    if (taskExecutionAvailable.value) {
      try {
        await tasksStore.loadList(true, detail.id)
      } catch {
        pageError.value = '会话已恢复，但持久任务列表暂时不可用。'
      }
    }
    if (updateQuery) await updateConversationQuery(detail.id)
    return true
  } catch {
    assistantStore.clearConversation()
    tasksStore.reset()
    pageError.value = '会话不可访问，可能已删除或当前账号权限已变化。'
    if (updateQuery) await updateConversationQuery(null)
    return false
  }
}

async function initialize() {
  const generation = ++initializationGeneration
  initializing.value = true
  pageError.value = ''
  try {
    await assistantStore.loadCapabilities(true)
    if (generation !== initializationGeneration) return
    if (!assistantStore.canUse || !persistenceAvailable.value) {
      pageError.value = '当前账号尚未开放 AI 持续会话工作台。'
      return
    }
    try {
      taskExecutionAvailable.value = (await getAITaskCapabilities()).available
    } catch {
      taskExecutionAvailable.value = false
    }
    await conversationsStore.loadList(true)
    if (contextPickerAvailable.value) {
      await conversationsStore.loadContextOptions(String(appStore.activeProductionFactory.id))
    }
    if (generation !== initializationGeneration) return
    const requestedId = queryConversationId()
    const hasInvalidRequestedId = route.query.conversation != null && !requestedId
    if (hasInvalidRequestedId) {
      pageError.value = '会话链接无效，已安全忽略。'
      await updateConversationQuery(null)
    }
    const sharedId = assistantStore.activeConversationId
    if (requestedId) {
      await openConversation(requestedId, false)
    } else if (sharedId) {
      await openConversation(sharedId)
    } else if (taskExecutionAvailable.value) {
      await tasksStore.loadList(true, null)
    }
    const requestedTask = queryTaskId()
    if (route.query.task != null && !requestedTask) {
      pageError.value = '任务链接无效，已安全忽略。'
      await updateTaskQuery(null)
    } else if (requestedTask) {
      await openTask(requestedTask, false)
    }
  } catch {
    if (generation === initializationGeneration) {
      pageError.value = 'AI 工作台暂时无法加载，请稍后重试。'
    }
  } finally {
    if (generation === initializationGeneration) initializing.value = false
  }
}

async function createConversation(mode: AIConversationMode) {
  pageError.value = ''
  try {
    const created = await conversationsStore.create({
      mode,
      factoryScope: String(appStore.activeProductionFactory.id),
      title: mode === 'PERSISTENT' ? '新持久会话' : '临时会话',
    })
    await openConversation(created.id)
    composer.value?.focus()
  } catch {
    pageError.value = '新会话创建失败，请确认当前厂区仍在 Pilot 范围内。'
  }
}

async function removeConversation(conversationId: string) {
  pageError.value = ''
  try {
    await conversationsStore.remove(conversationId)
    if (assistantStore.activeConversationId === conversationId) assistantStore.clearConversation()
    const next = conversationsStore.items[0]
    if (next) await openConversation(next.id)
    else await updateConversationQuery(null)
    if (!next) tasksStore.reset()
  } catch {
    pageError.value = '会话删除失败，请稍后重试。'
  }
}

async function changeContext(option: import('@/api/aiConversations').AIContextOption | null) {
  if (!conversationsStore.active || assistantStore.isStreaming) return
  pageError.value = ''
  try {
    await conversationsStore.setContext(pageContextFromConversation(option))
  } catch {
    pageError.value = '上下文切换未通过服务端权限验证，请刷新后重试。'
  }
}

async function manageConversation(
  conversationId: string,
  change: { title?: string; pinned?: boolean; archived?: boolean },
) {
  pageError.value = ''
  try {
    await conversationsStore.updateMetadata(conversationId, change)
  } catch {
    pageError.value = '会话信息更新失败，可能已在其他窗口发生变化，请刷新后重试。'
  }
}

async function openTask(taskId: string, updateQuery = true) {
  try {
    await tasksStore.open(taskId)
    if (updateQuery) await updateTaskQuery(taskId)
    return true
  } catch {
    pageError.value = tasksStore.error
    if (updateQuery) await updateTaskQuery(null)
    return false
  }
}

async function cancelTask() {
  try {
    await tasksStore.cancel()
  } catch {
    pageError.value = '任务取消请求失败，请刷新状态后重试。'
  }
}

async function resumeTask() {
  try {
    await tasksStore.resume()
  } catch {
    pageError.value = '任务恢复失败；权限、版本或数据新鲜度可能已经变化。'
  }
}

async function compareVisionObservation() {
  const task = tasksStore.active
  if (!task || visionComparisonStarting.value) return
  visionComparisonStarting.value = true
  pageError.value = ''
  try {
    const created = await createVisionComparisonTask({
      observationTaskId: task.id,
      factoryId: task.factory_scope,
    })
    await tasksStore.loadList(true, null)
    await openTask(created.id)
  }
  catch {
    pageError.value = '正式 Backlog 核对任务创建失败；没有读取或修改业务数据。'
  }
  finally {
    visionComparisonStarting.value = false
  }
}

async function refreshActiveConversation() {
  const conversationId = conversationsStore.activeId
  if (!conversationId) return
  await openConversation(conversationId, false)
}

async function loadOlderMessages() {
  try {
    await conversationsStore.loadOlderMessages()
    const detail = conversationsStore.active
    if (detail) assistantStore.bindConversation(detail.id, detail.mode, detail.messages)
  } catch {
    pageError.value = conversationsStore.error
  }
}

async function sendMessage(prompt: string) {
  if (!conversationsStore.active) await createConversation('PERSISTENT')
  const active = conversationsStore.active
  if (!active) return
  composer.value?.clear()
  const completed = await assistantStore.sendMessage(prompt, conversationContext.value)
  if (active.mode === 'PERSISTENT') {
    await openConversation(active.id, false)
  } else {
    await conversationsStore.loadList(true)
  }
  if (!completed && !assistantStore.lastError) {
    pageError.value = '本次连接已中断，已保留可恢复的会话状态。'
  }
}

async function retryLastTextRequest() {
  const completed = await assistantStore.retryLastTextRequest(conversationContext.value)
  if (completed && conversationsStore.active?.mode === 'PERSISTENT') {
    await openConversation(conversationsStore.active.id, false)
  }
}

watch(
  () => route.query.conversation,
  () => {
    if (initializing.value) return
    const requestedId = queryConversationId()
    if (requestedId && requestedId !== conversationsStore.activeId) {
      void openConversation(requestedId, false)
    }
  },
)

watch(
  inspectorCounts,
  (counts, previous) => {
    const total = Object.values(counts).reduce((sum, count) => sum + count, 0)
    const previousTotal = previous
      ? Object.values(previous).reduce((sum, count) => sum + count, 0)
      : 0
    if (total === 0) inspectorOpen.value = false
    else if (previousTotal === 0) inspectorOpen.value = true
  },
  { immediate: true },
)

watch(
  () => route.query.task,
  () => {
    if (initializing.value) return
    const requestedId = queryTaskId()
    if (requestedId && requestedId !== tasksStore.activeId) void openTask(requestedId, false)
  },
)

watch(
  () => authStore.sessionVersion,
  () => {
    conversationsStore.reset()
    tasksStore.reset()
    taskExecutionAvailable.value = false
    assistantStore.resetForSession()
    void initialize()
  },
)

onMounted(() => void initialize())
</script>

<template>
  <div class="flex min-h-dvh flex-col bg-slate-100 text-slate-950" data-ai-workbench>
    <WorkbenchHeader :factory-label="appStore.activeProductionFactory.shortName" />

    <div v-if="initializing" class="flex flex-1 items-center justify-center p-8 text-sm text-slate-500" role="status">
      正在加载 AI 工作台…
    </div>
    <div v-else-if="!persistenceAvailable" class="flex flex-1 items-center justify-center p-8">
      <div class="max-w-md rounded-2xl border border-amber-200 bg-amber-50 p-6 text-center text-sm leading-6 text-amber-900">
        {{ pageError || '当前未开放 AI 持续会话。' }}
      </div>
    </div>
    <WorkbenchShell
      v-else
      :rail-collapsed="railCollapsed"
      :inspector-open="inspectorOpen"
      :inspector-width="inspectorWidth"
      :controls-enabled="workbenchV2Enabled"
      @toggle-rail="railCollapsed = !railCollapsed"
      @toggle-inspector="inspectorOpen = !inspectorOpen"
      @inspector-width="inspectorWidth = $event"
    >
      <template #rail>
        <ConversationList
          class="h-full"
          :items="conversationsStore.items"
          :active-id="conversationsStore.activeId"
          :loading="conversationsStore.loading"
          :has-more="Boolean(conversationsStore.nextCursor)"
          :management-enabled="workbenchV2Enabled"
          :runtime-statuses="conversationRuntimeStatuses"
          @select="openConversation"
          @create="createConversation"
          @delete="removeConversation"
          @rename="(id, title) => manageConversation(id, { title })"
          @pin="(id, pinned) => manageConversation(id, { pinned })"
          @archive="(id, archived) => manageConversation(id, { archived })"
          @load-more="conversationsStore.loadList(false)"
        />
      </template>

      <main class="flex min-h-0 min-w-0 flex-col bg-slate-50" aria-label="AI 长会话">
        <details class="border-b border-slate-200 bg-white lg:hidden">
          <summary class="cursor-pointer px-4 py-2.5 text-xs font-semibold text-slate-700 focus-visible:outline focus-visible:outline-2 focus-visible:outline-inset focus-visible:outline-sky-600">
            会话列表与新建选项
          </summary>
          <ConversationList
            class="max-h-[55dvh] border-t border-slate-200"
            :items="conversationsStore.items"
            :active-id="conversationsStore.activeId"
            :loading="conversationsStore.loading"
            :has-more="Boolean(conversationsStore.nextCursor)"
            :management-enabled="workbenchV2Enabled"
            :runtime-statuses="conversationRuntimeStatuses"
            @select="openConversation"
            @create="createConversation"
            @delete="removeConversation"
            @rename="(id, title) => manageConversation(id, { title })"
            @pin="(id, pinned) => manageConversation(id, { pinned })"
            @archive="(id, archived) => manageConversation(id, { archived })"
            @load-more="conversationsStore.loadList(false)"
          />
        </details>
        <div class="flex flex-col gap-2 border-b border-slate-200 bg-white px-4 py-2.5 sm:flex-row sm:items-center sm:px-5">
          <div class="w-full min-w-0 sm:flex-1">
            <p class="truncate text-sm font-bold text-slate-900">
              {{ conversationsStore.active?.title ?? '选择或创建会话' }}
            </p>
            <p v-if="conversationsStore.active" class="mt-0.5 text-[11px] leading-4 text-slate-500">
              厂区 {{ conversationsStore.active.factory_scope }} · 会话内容仅供交流，不构成正式业务记录
            </p>
          </div>
          <div v-if="conversationsStore.active" class="flex w-full min-w-0 flex-wrap items-center gap-2 sm:w-auto sm:flex-nowrap">
            <ConversationRetentionBadge :mode="conversationsStore.active.mode" />
            <ContextPicker
              v-if="contextPickerAvailable"
              :model-value="conversationsStore.active.context_binding"
              :options="conversationsStore.contextOptions"
              :disabled="assistantStore.isStreaming"
              :loading="conversationsStore.loading"
              @change="changeContext"
            />
            <button
              type="button"
              class="ml-auto flex size-8 shrink-0 items-center justify-center rounded-lg text-slate-500 hover:bg-slate-100 hover:text-slate-900 focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-sky-600 sm:ml-0"
              aria-label="重新加载当前会话"
              :disabled="conversationsStore.loading"
              @click="refreshActiveConversation"
            >
              <RefreshCcw class="size-3.5" :class="conversationsStore.loading ? 'animate-spin' : ''" aria-hidden="true" />
            </button>
          </div>
        </div>

        <details class="border-b border-slate-200 bg-white xl:hidden">
          <summary class="cursor-pointer px-4 py-2.5 text-xs font-semibold text-slate-700 focus-visible:outline focus-visible:outline-2 focus-visible:outline-inset focus-visible:outline-sky-600">
            查看证据与权限状态
          </summary>
          <EvidencePanel
            heading-id="evidence-panel-mobile-title"
            class="max-h-[48dvh] border-l-0 border-t border-slate-200"
            :evidence="activeEvidence"
            :inaccessible="conversationsStore.evidenceAccessChanged"
            :loading="conversationsStore.loading"
            @refresh="refreshActiveConversation"
          />
        </details>

        <details class="border-b border-slate-200 bg-white xl:hidden">
          <summary class="cursor-pointer px-4 py-2.5 text-xs font-semibold text-slate-700 focus-visible:outline focus-visible:outline-2 focus-visible:outline-inset focus-visible:outline-sky-600">
            查看持久任务与进度
          </summary>
          <TaskList
            :items="tasksStore.items"
            :active-id="tasksStore.activeId"
            :loading="tasksStore.loading"
            :available="taskExecutionAvailable"
            :has-more="Boolean(tasksStore.nextCursor)"
            @select="openTask"
            @refresh="tasksStore.loadList(true, conversationsStore.activeId)"
            @load-more="tasksStore.loadList(false)"
          />
          <template v-if="tasksStore.active">
            <TaskTimeline
              :task="tasksStore.active"
              :events="tasksStore.events"
              :comparing-vision="visionComparisonStarting"
              class="max-h-[48dvh]"
              @compare-vision="compareVisionObservation"
            />
            <TaskControls
              :task="tasksStore.active"
              :loading="tasksStore.loading"
              @cancel="cancelTask"
              @resume="resumeTask"
              @refresh="tasksStore.recoverEvents"
            />
          </template>
        </details>

        <div v-if="pageError || conversationsStore.error" class="border-b border-rose-200 bg-rose-50 px-4 py-2 text-xs text-rose-700" role="alert">
          {{ pageError || conversationsStore.error }}
        </div>

        <button
          v-if="conversationsStore.active?.next_message_cursor"
          type="button"
          class="mx-auto mt-3 inline-flex items-center gap-1 rounded-lg border border-slate-200 bg-white px-3 py-1.5 text-xs font-semibold text-slate-600 hover:bg-slate-50 focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-sky-600"
          @click="loadOlderMessages"
        >
          <ChevronUp class="size-3.5" aria-hidden="true" />
          加载更早消息
        </button>

        <div
          v-if="conversationsStore.active?.summary"
          class="mx-4 mt-3 rounded-xl border border-violet-200 bg-violet-50 px-3 py-2 text-xs leading-5 text-violet-900 sm:mx-5"
          data-safe-stage-summary
        >
          <p class="font-semibold">安全阶段摘要（非权威）</p>
          <p class="mt-1 whitespace-pre-wrap">{{ conversationsStore.active.summary.text }}</p>
          <p class="mt-1 text-[11px] text-violet-700">不展示模型私有思维过程；正式事实需重新调用业务工具。</p>
        </div>

        <section
          v-if="conversationsStore.active && !assistantStore.messages.length"
          class="mx-auto grid w-full max-w-3xl gap-3 px-4 py-8 sm:grid-cols-3 sm:px-6"
          data-workbench-empty-state
          aria-label="开始使用 AI 工作台"
        >
          <button
            type="button"
            class="rounded-2xl border border-slate-200 bg-white p-4 text-left shadow-sm hover:border-sky-300 hover:bg-sky-50 focus-visible:outline focus-visible:outline-2 focus-visible:outline-sky-600"
            @click="sendMessage('查询当前业务上下文中的关键状态，并标明数据时间和来源。')"
          >
            <span class="text-sm font-bold text-slate-900">查询业务</span>
            <span class="mt-1 block text-xs leading-5 text-slate-500">按当前权限读取正式状态、数量与版本。</span>
          </button>
          <button
            type="button"
            class="rounded-2xl border border-slate-200 bg-white p-4 text-left shadow-sm hover:border-violet-300 hover:bg-violet-50 focus-visible:outline focus-visible:outline-2 focus-visible:outline-violet-600"
            @click="sendMessage('基于当前已验证信息给出最多三条重点分析和下一步建议。')"
          >
            <span class="text-sm font-bold text-slate-900">分析与建议</span>
            <span class="mt-1 block text-xs leading-5 text-slate-500">区分正式事实、流程知识与 AI 推断。</span>
          </button>
          <button
            type="button"
            class="rounded-2xl border border-slate-200 bg-white p-4 text-left shadow-sm hover:border-amber-300 hover:bg-amber-50 focus-visible:outline focus-visible:outline-2 focus-visible:outline-amber-600"
            @click="composer?.focus()"
          >
            <span class="text-sm font-bold text-slate-900">文件工作</span>
            <span class="mt-1 block text-xs leading-5 text-slate-500">在支持的页面中使用受控文件与图片流程。</span>
          </button>
        </section>

        <AiMessageList
          v-if="assistantStore.messages.length || !conversationsStore.active"
          :messages="assistantStore.messages"
          :turns="assistantStore.turns"
          :feedback-enabled="assistantStore.capabilities?.feedback_enabled === true"
          :factory-id="conversationsStore.active?.factory_scope"
          :rich-text-enabled="assistantStore.capabilities?.rich_message_renderer_enabled === true"
          :presentation-enabled="assistantStore.capabilities?.presentation_blocks_enabled === true"
        >
          <div
            v-if="assistantStore.lastError || assistantStore.canRetry"
            class="mx-4 mt-2 rounded-xl border border-amber-200 bg-amber-50 px-3 py-2 text-xs leading-5 text-amber-900 sm:mx-5"
          >
            <p v-if="assistantStore.lastError" role="alert">{{ assistantStore.lastError }}</p>
            <button
              v-if="assistantStore.canRetry"
              type="button"
              class="mt-1 inline-flex items-center gap-1 font-semibold text-sky-700 focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-sky-600"
              @click="retryLastTextRequest"
            >
              <RefreshCcw class="size-3.5" aria-hidden="true" />
              仅重试上一条文字
            </button>
          </div>
        </AiMessageList>

        <AiComposer
          ref="composer"
          :disabled="!assistantStore.canUse"
          :streaming="assistantStore.isStreaming"
          @cancel="assistantStore.cancelActiveRequest"
          @send="sendMessage"
        />
      </main>

      <template #inspector>
        <InspectorPanel
          :active-tab="inspectorTab"
          :counts="inspectorCounts"
          @tab="inspectorTab = $event"
        >
          <template #sources>
            <EvidencePanel
              heading-id="evidence-panel-desktop-title"
              class="min-h-0 border-l-0"
              :evidence="activeEvidence"
              :inaccessible="conversationsStore.evidenceAccessChanged"
              :loading="conversationsStore.loading"
              @refresh="refreshActiveConversation"
            />
          </template>
          <template #tasks>
            <TaskList
              :items="tasksStore.items"
              :active-id="tasksStore.activeId"
              :loading="tasksStore.loading"
              :available="taskExecutionAvailable"
              :has-more="Boolean(tasksStore.nextCursor)"
              @select="openTask"
              @refresh="tasksStore.loadList(true, conversationsStore.activeId)"
              @load-more="tasksStore.loadList(false)"
            />
            <template v-if="tasksStore.active">
              <TaskTimeline
                :task="tasksStore.active"
                :events="tasksStore.events"
                :comparing-vision="visionComparisonStarting"
                @compare-vision="compareVisionObservation"
              />
              <TaskControls
                :task="tasksStore.active"
                :loading="tasksStore.loading"
                @cancel="cancelTask"
                @resume="resumeTask"
                @refresh="tasksStore.recoverEvents"
              />
            </template>
          </template>
          <template #artifacts>
            <div class="space-y-2 p-3">
              <template v-for="turn in assistantStore.turns" :key="turn.id">
                <article
                  v-for="result in turn.businessResults.filter((item) => item.kind !== 'action_confirmation')"
                  :key="result.id"
                  class="rounded-xl border border-slate-200 bg-slate-50 p-3"
                >
                  <p class="text-xs font-bold text-slate-900">{{ result.title }}</p>
                  <p class="mt-1 text-xs leading-5 text-slate-600">{{ result.summary }}</p>
                </article>
              </template>
              <p v-if="!inspectorCounts.artifacts" class="py-8 text-center text-xs text-slate-500">当前会话还没有可查看的产物。</p>
            </div>
          </template>
          <template #actions>
            <div class="space-y-2 p-3">
              <template v-for="turn in assistantStore.turns" :key="turn.id">
                <article
                  v-for="result in turn.businessResults.filter((item) => item.kind === 'action_confirmation')"
                  :key="result.id"
                  class="rounded-xl border border-amber-200 bg-amber-50 p-3"
                >
                  <p class="text-xs font-bold text-amber-950">{{ result.title }}</p>
                  <p class="mt-1 text-xs leading-5 text-amber-800">{{ result.summary }}</p>
                </article>
              </template>
              <p v-if="!inspectorCounts.actions" class="py-8 text-center text-xs text-slate-500">没有待处理的确认操作。</p>
            </div>
          </template>
        </InspectorPanel>
      </template>
    </WorkbenchShell>
  </div>
</template>
