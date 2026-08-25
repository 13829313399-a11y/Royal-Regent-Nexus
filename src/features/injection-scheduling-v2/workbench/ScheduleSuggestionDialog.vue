<script setup lang="ts">
import { ref } from 'vue'
import { Sparkles, X } from '@lucide/vue'
import { useDialogFocus } from '../composables/useDialogFocus'
import type { SchedulePreview } from './types'
const props = defineProps<{ open: boolean; preview: SchedulePreview | null; loading: boolean; canApply: boolean }>()
const emit = defineEmits<{ close: []; preview: []; apply: [] }>()
const root = ref<HTMLElement | null>(null)
const { announcement } = useDialogFocus(() => props.open, root, {
  onEscape: () => emit('close'),
  initialFocus: () => root.value?.querySelector<HTMLElement>('[data-schedule-preview]') ?? null,
})
</script>
<template>
  <Teleport to="body"><div v-if="open" class="wb-modal-layer" @mousedown.self="emit('close')"><section ref="root" class="wb-modal wb-schedule-modal" role="dialog" aria-modal="true" aria-labelledby="wb-schedule-title" tabindex="-1"><p class="wb-sr-only" role="status" aria-live="polite">{{ announcement }}</p><header><div><p>单方案 · 简单贪心启发式</p><h2 id="wb-schedule-title">排期建议</h2></div><button type="button" class="wb-icon-button" aria-label="关闭排期建议" @click="emit('close')"><X :size="18" /></button></header><div v-if="!preview" class="wb-schedule-empty"><Sparkles :size="34" /><h3>按交期、A 级适配、换料换色和机台负载生成一份建议</h3><p>只会先生成预览；你确认“应用建议”前，当前规划不会改变。</p><button data-schedule-preview type="button" class="wb-primary-button" :disabled="loading" @click="emit('preview')">{{ loading ? '计算中…' : '生成建议' }}</button></div><div v-else class="wb-schedule-result"><div><span>建议排入</span><b>{{ preview.assignmentCount }}</b></div><div><span>仍未排</span><b>{{ preview.unscheduledCount }}</b></div><div><span>需注意</span><b>{{ preview.warningCount }}</b></div><p>这是一次性预览，已锁定任务不会被移动。</p></div><footer><button type="button" class="wb-secondary-button" @click="emit('close')">取消</button><button v-if="preview" type="button" class="wb-primary-button" :disabled="loading || !canApply" @click="emit('apply')">{{ loading ? '应用中…' : '应用建议' }}</button></footer></section></div></Teleport>
</template>
