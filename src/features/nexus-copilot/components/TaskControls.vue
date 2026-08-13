<script setup lang="ts">
import { Play, RefreshCcw, X } from '@lucide/vue'
import type { AITaskDetail } from '@/api/aiTasks'

const props = defineProps<{ task: AITaskDetail; loading: boolean }>()
const emit = defineEmits<{ cancel: []; resume: []; refresh: [] }>()

const cancellable = () => ['PLANNED', 'RUNNING', 'WAITING_INPUT'].includes(props.task.state)
const resumable = () => ['FAILED', 'WAITING_INPUT'].includes(props.task.state)
</script>

<template>
  <div class="flex flex-wrap items-center gap-2 border-t border-slate-200 px-3 py-2" data-task-controls>
    <button
      type="button"
      class="inline-flex items-center gap-1 rounded-lg border border-slate-200 px-2 py-1.5 text-[11px] font-semibold text-slate-600 hover:bg-slate-50 focus-visible:outline focus-visible:outline-2 focus-visible:outline-sky-600"
      :disabled="loading"
      @click="emit('refresh')"
    >
      <RefreshCcw class="size-3" aria-hidden="true" />刷新
    </button>
    <button
      v-if="resumable()"
      type="button"
      class="inline-flex items-center gap-1 rounded-lg bg-sky-700 px-2 py-1.5 text-[11px] font-semibold text-white hover:bg-sky-800 focus-visible:outline focus-visible:outline-2 focus-visible:outline-sky-600"
      :disabled="loading"
      @click="emit('resume')"
    >
      <Play class="size-3" aria-hidden="true" />恢复
    </button>
    <button
      v-if="cancellable()"
      type="button"
      class="inline-flex items-center gap-1 rounded-lg bg-rose-700 px-2 py-1.5 text-[11px] font-semibold text-white hover:bg-rose-800 focus-visible:outline focus-visible:outline-2 focus-visible:outline-rose-600"
      :disabled="loading"
      @click="emit('cancel')"
    >
      <X class="size-3" aria-hidden="true" />请求取消
    </button>
    <p v-if="task.state === 'CANCELLING'" class="w-full text-[10px] leading-4 text-amber-700">
      已记录取消意图；正在进行的外部调用返回后才会确认最终停止状态。
    </p>
    <p v-else-if="['COMPLETED', 'FAILED', 'CANCELLED'].includes(task.state)" class="w-full text-[10px] text-slate-500">
      终态：{{ task.state }}。进度来自服务端持久记录。
    </p>
  </div>
</template>
