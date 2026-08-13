import { computed, onScopeDispose, ref } from 'vue'
import { defineStore } from 'pinia'
import {
  cancelAITask,
  getAITask,
  getAITaskEvents,
  listAITasks,
  resumeAITask,
  type AITaskDetail,
  type AITaskEvent,
  type AITaskSummary,
} from '@/api/aiTasks'

export const useAITasksStore = defineStore('aiTasks', () => {
  const items = ref<AITaskSummary[]>([])
  const active = ref<AITaskDetail | null>(null)
  const events = ref<AITaskEvent[]>([])
  const nextCursor = ref<string | null>(null)
  const loading = ref(false)
  const error = ref('')
  const conversationId = ref<string | null>(null)
  let recoveryTimer: ReturnType<typeof setTimeout> | null = null
  let recoveryGeneration = 0

  const activeId = computed(() => active.value?.id ?? null)
  const lastSequence = computed(() => events.value.at(-1)?.sequence ?? 0)
  const terminal = computed(() => ['COMPLETED', 'FAILED', 'CANCELLED'].includes(active.value?.state ?? ''))

  async function loadList(reset = true, forConversation?: string | null) {
    loading.value = true
    error.value = ''
    if (forConversation !== undefined) conversationId.value = forConversation
    try {
      const page = await listAITasks({
        conversationId: conversationId.value ?? undefined,
        cursor: reset ? undefined : nextCursor.value ?? undefined,
      })
      items.value = reset
        ? page.items
        : [...items.value, ...page.items].filter(
            (item, index, all) => all.findIndex((candidate) => candidate.id === item.id) === index,
          )
      nextCursor.value = page.next_cursor
    } catch {
      error.value = '任务列表暂时无法加载。'
      throw new Error(error.value)
    } finally {
      loading.value = false
    }
  }

  async function refreshActive() {
    const id = active.value?.id
    if (!id) return
    const detail = await getAITask(id)
    if (active.value?.id !== id) return
    active.value = detail
    const index = items.value.findIndex((item) => item.id === id)
    const summary: AITaskSummary = detail
    if (index >= 0) items.value[index] = summary
  }

  async function recoverEvents() {
    const id = active.value?.id
    if (!id) return
    const page = await getAITaskEvents(id, lastSequence.value)
    if (active.value?.id !== id) return
    const known = new Set(events.value.map((item) => item.sequence))
    events.value.push(...page.items.filter((item) => !known.has(item.sequence)))
    events.value.sort((left, right) => left.sequence - right.sequence)
    await refreshActive()
  }

  function stopRecovery() {
    recoveryGeneration += 1
    if (recoveryTimer) clearTimeout(recoveryTimer)
    recoveryTimer = null
  }

  function startRecovery() {
    stopRecovery()
    const generation = recoveryGeneration
    const tick = async () => {
      if (generation !== recoveryGeneration || !active.value || terminal.value) return
      try {
        await recoverEvents()
      } catch {
        error.value = '任务事件续接失败；将继续重试。'
      }
      if (generation === recoveryGeneration && active.value && !terminal.value) {
        recoveryTimer = setTimeout(tick, 1_500)
      }
    }
    recoveryTimer = setTimeout(tick, 1_500)
  }

  async function open(taskId: string) {
    stopRecovery()
    loading.value = true
    error.value = ''
    try {
      active.value = await getAITask(taskId)
      events.value = (await getAITaskEvents(taskId)).items
      startRecovery()
      return active.value
    } catch {
      active.value = null
      events.value = []
      error.value = '任务不可访问，可能已删除或当前权限已变化。'
      throw new Error(error.value)
    } finally {
      loading.value = false
    }
  }

  async function cancel() {
    if (!active.value || loading.value) return
    loading.value = true
    try {
      active.value = await cancelAITask(active.value)
      await recoverEvents()
    } finally {
      loading.value = false
    }
  }

  async function resume() {
    if (!active.value || loading.value) return
    loading.value = true
    try {
      active.value = await resumeAITask(active.value)
      await recoverEvents()
      startRecovery()
    } finally {
      loading.value = false
    }
  }

  function reset() {
    stopRecovery()
    items.value = []
    active.value = null
    events.value = []
    nextCursor.value = null
    loading.value = false
    error.value = ''
    conversationId.value = null
  }

  onScopeDispose(stopRecovery)
  return {
    items, active, activeId, events, nextCursor, loading, error, lastSequence, terminal,
    loadList, open, refreshActive, recoverEvents, cancel, resume, startRecovery,
    stopRecovery, reset,
  }
})
