<script setup lang="ts">
import { ListChecks, RefreshCcw } from '@lucide/vue'
import type { AITaskSummary } from '@/api/aiTasks'

defineProps<{
  items: AITaskSummary[]
  activeId: string | null
  loading: boolean
  available: boolean
  hasMore: boolean
}>()
const emit = defineEmits<{
  select: [taskId: string]
  refresh: []
  loadMore: []
}>()

const stateLabels: Record<string, string> = {
  CREATED: '已创建', UNDERSTOOD: '已理解', PLANNED: '已规划', RUNNING: '执行中',
  WAITING_INPUT: '等待输入', VERIFYING: '核验中', COMPLETED: '已完成',
  CANCELLING: '取消中', CANCELLED: '已取消', FAILED: '失败', RETRY_PENDING: '等待重试',
}
</script>

<template>
  <section class="flex min-h-0 flex-col border-b border-slate-200 bg-white" aria-labelledby="task-list-title">
    <div class="flex items-center gap-2 px-3 py-2.5">
      <ListChecks class="size-4 text-sky-700" aria-hidden="true" />
      <h2 id="task-list-title" class="flex-1 text-xs font-bold text-slate-900">持久任务</h2>
      <button
        type="button"
        class="flex size-7 items-center justify-center rounded-lg text-slate-500 hover:bg-slate-100 focus-visible:outline focus-visible:outline-2 focus-visible:outline-sky-600"
        aria-label="刷新任务列表"
        :disabled="loading || !available"
        @click="emit('refresh')"
      >
        <RefreshCcw class="size-3.5" :class="loading ? 'animate-spin' : ''" aria-hidden="true" />
      </button>
    </div>
    <p v-if="!available" class="px-3 pb-3 text-[11px] leading-5 text-amber-700">
      任务 Worker 未开放；会话功能仍可正常使用。
    </p>
    <p v-else-if="!items.length && !loading" class="px-3 pb-4 text-xs text-slate-500">当前会话还没有持久任务。</p>
    <div v-else class="max-h-64 space-y-1 overflow-y-auto px-2 pb-2" data-task-list>
      <button
        v-for="task in items"
        :key="task.id"
        type="button"
        class="block w-full rounded-xl px-2.5 py-2 text-left focus-visible:outline focus-visible:outline-2 focus-visible:outline-sky-600"
        :class="task.id === activeId ? 'bg-sky-50 text-sky-950' : 'hover:bg-slate-50'"
        @click="emit('select', task.id)"
      >
        <span class="flex items-center gap-2 text-xs font-semibold">
          <span class="truncate">{{ task.primary_skill_id }}</span>
          <span class="ml-auto shrink-0 rounded-full bg-slate-100 px-1.5 py-0.5 text-[10px] text-slate-600">
            {{ stateLabels[task.state] ?? task.state }}
          </span>
        </span>
        <span class="mt-1 block text-[10px] text-slate-500">
          {{ task.task_type }} · {{ task.worker_status }} · {{ task.step_count }} 步
        </span>
      </button>
      <button
        v-if="hasMore"
        type="button"
        class="w-full rounded-lg py-1.5 text-xs font-semibold text-sky-700 hover:bg-sky-50 focus-visible:outline focus-visible:outline-2 focus-visible:outline-sky-600"
        @click="emit('loadMore')"
      >
        加载更多任务
      </button>
    </div>
  </section>
</template>
