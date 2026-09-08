<script setup lang="ts">
import { Trash2, Undo2 } from '@lucide/vue'
import { Button } from '@/components/ui/button'
import type { Job } from '@/api/documentTools'

defineProps<{ job: Job; busy: boolean }>()
defineEmits<{ withdraw: [job: Job]; delete: [job: Job] }>()
</script>

<template>
  <div class="dt-task-actions">
    <Button
      v-if="
        ['queued', 'running', 'awaiting_input'].includes(job.execution_status)
      "
      variant="outline"
      size="sm"
      :disabled="busy || job.cancel_requested"
      @click="$emit('withdraw', job)"
      ><Undo2 :size="14" aria-hidden="true" />{{
        job.cancel_requested ? '正在撤回…' : '撤回任务'
      }}</Button
    >
    <Button
      variant="ghost"
      size="sm"
      class="dt-delete-action"
      :disabled="busy"
      @click="$emit('delete', job)"
      ><Trash2 :size="14" aria-hidden="true" />删除任务</Button
    >
  </div>
</template>
